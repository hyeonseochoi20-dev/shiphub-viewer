#!/usr/bin/env python3
"""
조선 BIM/CAD 경량화 변환 서비스
- IfcOpenShell로 IFC → glTF 변환
- DXF → glTF 변환 (ezdxf)
- B-REP → Tessellation (형상 10분의 1 압축)
- 파일 시스템 감시
"""

import ifcopenshell
import ifcopenshell.geom
import json
import os
import sys
import sqlite3
import struct
import threading
import ezdxf
from pathlib import Path
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

import production_data as pdata

sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)
# 프론트(web-viewer)가 배포 환경에서는 다른 도메인(Vercel)에 떠있으므로 CORS 허용.
# 이 API는 인증이 없는 포트폴리오용 공개 데모라 오리진을 넓게 허용해도 새로 노출되는
# 권한은 없다(브라우저 CORS는 서버 접근 자체를 막지 않고 XHR/fetch의 same-origin만 완화한다).
CORS(app)

# 설정
INPUT_DIR = Path("input_models")
OUTPUT_DIR = Path("output_models")
DB_FILE = Path("conversion.db")
LOD_LEVEL = 3  # 1=10분의1, 2=1분의1, 3=원본

observer = None
watch_handle = None

# 지원 포맷 모듈 레지스트리 - 조선해양 전용 CAD/설계 시스템의 네이티브 포맷을 우선 대상으로 한다.
# 출력은 단순 glTF가 아니라 SLF(ShipHub Lightweight Format) - glTF 2.0을 확장해 선종/블록/공정 등
# 조선 특화 메타데이터를 함께 담는 뷰어 전용 경량 포맷으로 포지셔닝한다 (물리적으로는 여전히
# glTF 2.0 호환 .gltf/.bin 파일이며, 메타데이터는 glTF의 extras/extensions 슬롯에 실린다).
MODULES = [
    {"id": "ifc", "name": "IFC (BIM)", "ext": [".ifc"], "engine": "IfcOpenShell", "status": "active"},
    {"id": "dxf", "name": "DXF (2D/3D 도면)", "ext": [".dxf"], "engine": "ezdxf", "status": "active"},
    {"id": "step218", "name": "STEP AP218 (Ship Structures)", "ext": [".stp", ".step"], "engine": "Open Cascade (예정)", "status": "planned"},
    {"id": "tribon", "name": "AVEVA Marine / Tribon", "ext": [".xml", ".mdb"], "engine": "예정", "status": "planned"},
    {"id": "cadmatic", "name": "CADMATIC Hull/Outfitting", "ext": [".cmt"], "engine": "예정", "status": "planned"},
    {"id": "foran", "name": "FORAN", "ext": [".fbm"], "engine": "예정", "status": "planned"},
    {"id": "rvt", "name": "Revit (RVT, 해양플랜트 설비동)", "ext": [".rvt"], "engine": "IFC 익스포트 경유", "status": "planned"},
]

OUTPUT_FORMAT = {
    "name": "SLF (ShipHub Lightweight Format)",
    "base": "glTF 2.0",
    "description": "선종/척/공정/블록 등 조선 특화 메타데이터를 glTF extras에 함께 실어 나르는 뷰어 전용 경량 포맷",
}

# IFC → glTF 변환 설정
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)


def init_db():
    """변환 메타데이터 DB 초기화"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            input_path TEXT,
            output_path TEXT,
            lod_level INTEGER,
            original_size_mb REAL,
            compressed_size_mb REAL,
            triangle_count INTEGER,
            converted_at TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()


def convert_ifc_to_gltf(input_path, output_path, lod_level=LOD_LEVEL):
    """IFC 파일을 glTF로 변환 (LOD 적용)"""
    print(f"Converting {input_path} to glTF (LOD Level {lod_level})...")

    try:
        model = ifcopenshell.open(input_path)

        # 모든 형상 요소 수집
        vertices = []
        faces = []
        colors = []  # 정점 1개당 [r,g,b,a] 1개 (glTF COLOR_0 요구사항)

        products = model.by_type("IfcProduct")
        for product in products:
            if product.is_a("IfcElement"):
                shape = ifcopenshell.geom.create_shape(settings, product)
                if shape and shape.geometry:
                    verts = list(shape.geometry.verts)
                    faces_idx = list(shape.geometry.faces)

                    # 부품별로 이어붙일 때 face 인덱스가 전체 정점 배열 기준이 되도록 오프셋 적용
                    # (오프셋 없이 이어붙이면 두 번째 부품부터 face가 엉뚱한 정점을 가리키게 됨)
                    vertex_offset = len(vertices) // 3
                    faces.extend(idx + vertex_offset for idx in faces_idx)

                    vertices.extend(verts)

                    color = extract_color(product)
                    colors.extend(color for _ in range(len(verts) // 3))

        # glTF + 실제 정점 바이너리(.bin) 생성
        gltf_data, buffer_bytes = create_gltf_json(vertices, faces, colors, mode=4)

        bin_path = output_path.with_suffix('.bin')
        with open(bin_path, 'wb') as f:
            f.write(buffer_bytes)
        gltf_data['buffers'][0]['uri'] = bin_path.name

        with open(output_path, 'w') as f:
            json.dump(gltf_data, f)

        # DB 기록
        record_conversion(input_path, output_path, len(faces) // 3, lod_level)

        return True

    except Exception as e:
        print(f"Conversion error: {e}")
        return False


def extract_color(product):
    """제품 재질에서 색상 추출"""
    try:
        if hasattr(product, 'Representation') and product.Representation:
            for rep in product.Representation.Representations:
                for item in rep.Items:
                    if hasattr(item, 'StyledBy') and item.StyledBy:
                        for style in item.StyledBy:
                            if hasattr(style, 'Styles'):
                                for fill_style in style.Styles:
                                    if fill_style.is_a('IfcFillAreaStyle'):
                                        for fill in fill_style.FillStyles:
                                            if hasattr(fill, 'Colour'):
                                                # RGB 색상 반환
                                                return [fill.Colour[0], fill.Colour[1], fill.Colour[2], 1.0]
    except Exception:
        pass
    return [0.8, 0.8, 0.8, 1.0]  # 기본 회색


def create_gltf_json(vertices, faces, colors, mode=4):
    """glTF JSON + 실제 정점 바이너리(.bin bytes) 생성
    vertices: flat [x,y,z, x,y,z, ...] (float)
    faces: flat 인덱스 목록 (mode=4 삼각형이면 3개씩, mode=1 라인이면 2개씩)
    colors: 정점당 [r,g,b,a] (0~1 float), len(colors) == len(vertices)//3 이어야 함
    """
    vertex_count = len(vertices) // 3
    if vertex_count < 1:
        raise ValueError("추출된 형상 정보가 없습니다 (지오메트리가 있는 요소를 찾지 못함)")
    if len(colors) != vertex_count:
        # 색상 수가 안 맞으면 기본 회색으로 채움 (렌더링이 깨지지 않도록 방어)
        colors = (colors + [[0.8, 0.8, 0.8, 1.0]] * vertex_count)[:vertex_count]

    pos_bytes = struct.pack(f'<{len(vertices)}f', *vertices)
    color_bytes = struct.pack(
        f'<{vertex_count * 4}B',
        *[min(255, max(0, round(c * 255))) for rgba in colors for c in rgba]
    )
    index_bytes = struct.pack(f'<{len(faces)}H', *faces)

    pos_offset = 0
    color_offset = len(pos_bytes)
    index_offset = color_offset + len(color_bytes)
    buffer_bytes = pos_bytes + color_bytes + index_bytes

    xs, ys, zs = vertices[0::3], vertices[1::3], vertices[2::3]

    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": 0, "COLOR_0": 1},
                "indices": 2,
                "mode": mode
            }]
        }],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": vertex_count,
                "type": "VEC3",
                "max": [max(xs), max(ys), max(zs)],
                "min": [min(xs), min(ys), min(zs)]
            },
            {
                "bufferView": 1,
                "componentType": 5121,
                "normalized": True,
                "count": vertex_count,
                "type": "VEC4"
            },
            {
                "bufferView": 2,
                "componentType": 5123,
                "count": len(faces),
                "type": "SCALAR"
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset, "byteLength": len(pos_bytes)},
            {"buffer": 0, "byteOffset": color_offset, "byteLength": len(color_bytes)},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes)}
        ],
        "buffers": [{"uri": "model.bin", "byteLength": len(buffer_bytes)}]
    }
    return gltf, buffer_bytes


def record_conversion(input_path, output_path, triangle_count, lod_level):
    """변환 기록 DB 저장"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''
        INSERT INTO conversions (filename, input_path, output_path, lod_level,
        original_size_mb, compressed_size_mb, triangle_count, converted_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        Path(input_path).name,
        str(input_path),
        str(output_path),
        lod_level,
        os.path.getsize(input_path) / (1024*1024),
        os.path.getsize(output_path) / (1024*1024),
        triangle_count,
        datetime.now().isoformat(),
        'completed'
    ))

    conn.commit()
    conn.close()


class IFCHandler(FileSystemEventHandler):
    """파일 감시 핸들러"""

    def on_created(self, event):
        if not event.is_directory:
            input_path = Path(event.src_path)
            if input_path.suffix.lower() == '.ifc':
                print(f"New IFC file detected: {event.src_path}")
                output_path = OUTPUT_DIR / (input_path.stem + ".gltf")
                convert_ifc_to_gltf(event.src_path, output_path)
            elif input_path.suffix.lower() == '.dxf':
                print(f"New DXF file detected: {event.src_path}")
                output_path = OUTPUT_DIR / (input_path.stem + ".gltf")
                convert_dxf_to_gltf(event.src_path, output_path)


@app.route('/api/stats')
def stats():
    """StatusPanel(3D 뷰어 우측 상단)이 폴링하는 요약 통계 - 실제 변환 이력 기준
    (이 엔드포인트가 없어서 프론트가 하드코딩된 가짜 수치로 계속 폴백하고 있었음)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM conversions WHERE status = 'completed'")
    conversion_count = c.fetchone()[0]
    c.execute("SELECT converted_at FROM conversions ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    with batch_lock:
        queue = sum(1 for item in batch_state["items"] if item["status"] in ("pending", "processing"))

    return jsonify({
        'conversionCount': conversion_count,
        'lastConverted': row[0] if row else '-',
        'queue': queue,
    })


@app.route('/api/modules')
def modules():
    """지원 포맷 모듈 목록 API"""
    return jsonify(MODULES)


@app.route('/api/settings')
def get_settings():
    """현재 입출력 폴더/LOD 설정 조회 API"""
    return jsonify({
        'input_dir': str(INPUT_DIR),
        'output_dir': str(OUTPUT_DIR),
        'lod_level': LOD_LEVEL,
    })


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """입력/출력 폴더를 OS 탐색기로 직접 연다 (백엔드가 사용자 PC에서 로컬로 실행되므로 가능)"""
    which = (request.get_json(force=True) or {}).get('dir', 'input')
    target = INPUT_DIR if which == 'input' else OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(target.resolve()))
    except AttributeError:
        return jsonify({'error': 'Windows 탐색기 연동은 이 OS에서 지원되지 않습니다'}), 400
    except OSError as e:
        return jsonify({'error': f'탐색기를 열 수 없습니다: {e}'}), 400
    return jsonify({'opened': str(target.resolve())})


@app.route('/api/settings/input-dir', methods=['POST'])
def set_input_dir():
    """입력 폴더 경로 변경 API - watchdog 감시 대상을 새 경로로 재설정"""
    global INPUT_DIR, watch_handle

    data = request.get_json(force=True) or {}
    new_path = (data.get('path') or '').strip()
    if not new_path:
        return jsonify({'error': '경로를 입력해주세요'}), 400

    path = Path(new_path)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return jsonify({'error': f'폴더를 생성/접근할 수 없습니다: {e}'}), 400

    INPUT_DIR = path

    if observer is not None:
        if watch_handle is not None:
            observer.unschedule(watch_handle)
        watch_handle = observer.schedule(IFCHandler(), str(INPUT_DIR), recursive=False)

    print(f"입력 폴더 변경: {INPUT_DIR}")
    return jsonify({'input_dir': str(INPUT_DIR)})


@app.route('/api/browse')
def browse():
    """폴더 내 파일 목록 조회 API (input|output)"""
    which = request.args.get('dir', 'input')
    target = INPUT_DIR if which == 'input' else OUTPUT_DIR
    if not target.exists():
        return jsonify([])
    items = []
    for f in sorted(target.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file():
            items.append({
                'name': f.name,
                'size_kb': round(f.stat().st_size / 1024, 1),
                'modified_at': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return jsonify(items)


@app.route('/api/models')
def models():
    """변환된 모델 목록 API"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT filename, output_path, lod_level FROM conversions WHERE status="completed" ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()

    return jsonify([{
        'name': r[0],
        'url': f'/models/{r[0].replace(".ifc", ".gltf").replace(".dxf", ".gltf")}',
        'lod': r[2]
    } for r in rows])


@app.route('/models/<path:filename>')
def serve_output_model(filename):
    """변환 결과물(glTF/bin) 정적 서빙 - 이 라우트가 없으면 /api/models가 반환하는 URL이 전부 404가 됨"""
    return send_from_directory(OUTPUT_DIR.resolve(), filename)


def convert_dxf_to_gltf(input_path, output_path, lod_level=LOD_LEVEL):
    """DXF 파일을 glTF로 변환 (LOD 적용)"""
    print(f"Converting {input_path} to glTF (LOD Level {lod_level})...")

    try:
        doc = ezdxf.readfile(input_path)
        msp = doc.modelspace()

        vertices = []
        faces = []  # LINES 모드용 정점 쌍 인덱스
        colors = []  # 정점 1개당 [r,g,b,a] 1개

        # DXF 라인/폴리선을 선분(LINES)으로 변환 - 도면 개체는 면이 아니라 선이므로 mode=1(LINES)
        for entity in msp:
            if entity.dxftype() == 'LINE':
                base = len(vertices) // 3
                vertices.extend([entity.dxf.start.x, entity.dxf.start.y, entity.dxf.start.z or 0])
                vertices.extend([entity.dxf.end.x, entity.dxf.end.y, entity.dxf.end.z or 0])
                colors.extend([[0.3, 0.7, 0.3, 1.0]] * 2)  # 초록색
                faces.extend([base, base + 1])

            elif entity.dxftype() == 'LWPOLYLINE':
                points = list(entity.get_points('xy'))
                base = len(vertices) // 3
                for point in points:
                    vertices.extend([point[0], point[1], 0])
                    colors.append([0.8, 0.8, 0.8, 1.0])  # 회색
                for i in range(len(points) - 1):
                    faces.extend([base + i, base + i + 1])

        # glTF + 실제 정점 바이너리(.bin) 생성 (mode=1: LINES)
        gltf_data, buffer_bytes = create_gltf_json(vertices, faces, colors, mode=1)

        bin_path = output_path.with_suffix('.bin')
        with open(bin_path, 'wb') as f:
            f.write(buffer_bytes)
        gltf_data['buffers'][0]['uri'] = bin_path.name

        with open(output_path, 'w') as f:
            json.dump(gltf_data, f)

        record_conversion(input_path, output_path, len(faces) // 2, lod_level)
        return True

    except Exception as e:
        print(f"DXF Conversion error: {e}")
        return False


CONVERTERS = {".ifc": convert_ifc_to_gltf, ".dxf": convert_dxf_to_gltf}

batch_lock = threading.Lock()
batch_state = {"running": False, "stop_requested": False, "items": []}


def _run_batch():
    """input_models 폴더의 대기 파일을 순서대로 변환 - 백그라운드 스레드에서 실행되어 Flask 서버를 막지 않는다"""
    try:
        for item in batch_state["items"]:
            with batch_lock:
                if batch_state["stop_requested"]:
                    break
                item["status"] = "processing"
                item["progress"] = 50

            input_path = Path(item["input_path"])
            output_path = OUTPUT_DIR / (input_path.stem + ".gltf")
            converter = CONVERTERS.get(input_path.suffix.lower())
            ok = converter(str(input_path), output_path) if converter else False

            with batch_lock:
                item["status"] = "completed" if ok else "error"
                item["progress"] = 100 if ok else 0
    finally:
        with batch_lock:
            batch_state["running"] = False
            batch_state["stop_requested"] = False


@app.route('/api/batch-status')
def batch_status():
    """배치 변환 진행 상태 조회 API - 프론트에서 주기적으로 폴링"""
    with batch_lock:
        return jsonify({"running": batch_state["running"], "items": batch_state["items"]})


@app.route('/api/batch-start', methods=['POST'])
def batch_start():
    """input_models 폴더의 미변환 IFC/DXF 파일을 스캔해서 일괄 변환 시작"""
    with batch_lock:
        if batch_state["running"]:
            return jsonify({"error": "이미 배치 변환이 진행 중입니다"}), 409

        files = sorted(
            (f for f in INPUT_DIR.iterdir() if f.is_file() and f.suffix.lower() in CONVERTERS),
            key=lambda p: p.stat().st_mtime,
        )
        if not files:
            return jsonify({"error": "input_models 폴더에 변환할 IFC/DXF 파일이 없습니다"}), 400

        batch_state["items"] = [
            {"id": i, "filename": f.name, "input_path": str(f), "status": "pending", "progress": 0}
            for i, f in enumerate(files)
        ]
        batch_state["running"] = True
        batch_state["stop_requested"] = False

    threading.Thread(target=_run_batch, daemon=True).start()
    return jsonify({"running": True, "items": batch_state["items"]})


@app.route('/api/batch-stop', methods=['POST'])
def batch_stop():
    """진행 중인 배치 변환을 현재 파일까지만 처리하고 중단"""
    with batch_lock:
        if not batch_state["running"]:
            return jsonify({"stopping": False, "error": "진행 중인 배치가 없습니다"}), 400
        batch_state["stop_requested"] = True
    return jsonify({"stopping": True})


# ---------------------------------------------------------------------------
# AI 쿼리 API - MariaDB 생산 DB 조회 + 예측 모델 (production_data.py 공용 로직)
# 3D 뷰어의 AI 쿼리 패널이 이 엔드포인트들을 직접 호출한다 (MCP 없이 로컬 REST로 충분한 경우).
# ---------------------------------------------------------------------------
@app.route('/api/ai/filters')
def ai_filters():
    """쿼리 폼 드롭다운용 - 선종/부서/공정/우선순위/QA상태 선택지 목록"""
    try:
        return jsonify(pdata.get_filter_options())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/blocks')
def ai_query_blocks():
    """조건에 맞는 생산 블록 목록 조회"""
    try:
        results = pdata.query_blocks(
            ship_type=request.args.get('ship_type') or None,
            department=request.args.get('department') or None,
            priority=request.args.get('priority') or None,
            qa_status=request.args.get('qa_status') or None,
            min_delay_days=request.args.get('min_delay_days') or None,
            limit=request.args.get('limit', 20),
        )
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/blocks/<int:block_id>')
def ai_block_detail(block_id):
    """블록 하나의 전체 메타데이터"""
    try:
        result = pdata.get_block_detail(block_id)
        if result is None:
            return jsonify({"error": f"block_id={block_id} 를 찾을 수 없습니다"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/blocks/<int:block_id>/similar')
def ai_similar_blocks(block_id):
    """메타데이터 기반 최근접 이웃 유사 블록 검색 (실제 3D 형상 임베딩 아님)"""
    try:
        results = pdata.find_similar_blocks(block_id, int(request.args.get('top_k', 5)))
        if results is None:
            return jsonify({"error": f"block_id={block_id} 를 찾을 수 없습니다"}), 404
        return jsonify({"method": "메타데이터 기반 최근접 이웃 (실제 3D 형상 임베딩 아님)", "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/predict', methods=['POST'])
def ai_predict():
    """새 블록 정보를 입력하면 예상 지연일수 / QA 합격확률을 예측"""
    try:
        data = request.get_json(force=True) or {}
        result = pdata.predict_delay(
            triangle_count=int(data['triangle_count']),
            file_size_mb=float(data['file_size_mb']),
            lod_level=int(data['lod_level']),
            planned_days=int(data['planned_days']),
            department=data['department'],
            process_stage=data['process_stage'],
            priority=data['priority'],
            ship_type=data['ship_type'],
        )
        return jsonify(result)
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"입력값 오류: {e}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/faq')
def ai_faq():
    """미리 정의한 5가지 질문 - 답을 바로 보여주는 데모용 프리셋 (라이브 집계 + 정적 참고자료 혼합)"""
    try:
        return jsonify(pdata.get_faq_answers())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/fleet-summary')
def ai_fleet_summary():
    """선종별 척수/블록수/평균 지연/QA합격률/계약금액 요약"""
    try:
        return jsonify(pdata.get_fleet_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/roi-summary')
def ai_roi_summary():
    """부서별 실측 ROI 요약 (경량뷰 도입 전/후 리뷰 소요시간·비용 절감)"""
    try:
        return jsonify(pdata.get_roi_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # 초기화
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    init_db()

    # 파일 감시 시작
    observer = Observer()
    watch_handle = observer.schedule(IFCHandler(), str(INPUT_DIR), recursive=False)
    observer.start()

    print("BIM Converter Service Started...")
    print(f"Input: {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")

    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()