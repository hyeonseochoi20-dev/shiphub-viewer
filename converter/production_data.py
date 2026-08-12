#!/usr/bin/env python3
"""
ShipHub 생산 DB(MariaDB) 조회 + 예측 모델 공용 로직
- mcp_server.py(MCP 도구)와 converter.py(Flask REST API)가 동일한 이 모듈을 재사용해서
  쿼리/모델 학습 로직이 여러 곳에 따로 구현되는 것을 막는다.
- app.py(Streamlit)는 @st.cache_data 기반 캐싱이 이 모듈의 전역 캐시와 성격이 달라 별도 유지.

주의: find_similar_blocks는 실제 3D 형상 임베딩이 아니라 메타데이터 기반 최근접 이웃 검색이다.
"""
import os

import pandas as pd
import sqlalchemy as sa
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DB_URL = "mysql+pymysql://{user}:{password}@{host}:{port}/shiphub?charset=utf8mb4".format(
    user=os.environ.get("MARIADB_USER", "root"),
    password=os.environ.get("MARIADB_PASSWORD", ""),
    host=os.environ.get("MARIADB_HOST", "localhost"),
    port=os.environ.get("MARIADB_PORT", "3306"),
)
engine = sa.create_engine(DB_URL, pool_pre_ping=True)

MODEL_NUMERIC_COLS = ["triangle_count", "file_size_mb", "lod_level", "planned_days"]
CATEGORICAL_COLS = ["department", "process_stage", "priority", "ship_type"]

# schema.sql의 v_production_records 뷰 = fact_production_block과 4개 dim_* 테이블을 조인한
# 평탄화 뷰. 동일한 JOIN을 여기서 다시 텍스트로 중복 작성하지 않고 뷰 하나만 SELECT한다.
JOIN_SQL = "SELECT * FROM v_production_records"

_cache = {}  # 프로세스 생애주기 동안 1회만 로드/학습해서 재사용


def load_df(force=False):
    if force or "df" not in _cache:
        with engine.connect() as conn:
            df = pd.read_sql(sa.text(JOIN_SQL + ";"), conn)
        df["qa_defect_count"] = df["qa_defect_count"].fillna(0)
        df["file_size_mb"] = df["file_size_mb"].fillna(0)
        _cache["df"] = df
        _cache.pop("models", None)
    return _cache["df"]


def get_models():
    """지연 회귀/QA 분류 모델 + 인코더/스케일러 + 최근접이웃 인덱스를 최초 호출 시 1회 학습해서 캐싱.

    MCP/REST API는 512MB 메모리 제한이 있는 서버(Render 무료 티어)에서도 돌아가야 하므로,
    n_jobs=-1(멀티프로세스 - 워커마다 학습 데이터를 pickle로 복제해서 메모리를 배로 먹음)을 피하고
    n_estimators/학습 표본 수를 줄인다 - EDA용 전체 정밀도가 필요한 app.py(별도 배포)와는 다른 용도라
    라이브 데모 예측 품질에는 사실상 영향이 없다."""
    if "models" in _cache:
        return _cache["models"]

    df = load_df()
    train_df = df.sample(n=min(len(df), 4000), random_state=0) if len(df) > 4000 else df

    oh_enc = OneHotEncoder(sparse_output=False)
    oh_enc.fit(train_df[CATEGORICAL_COLS])
    scaler = StandardScaler()
    scaler.fit(train_df[MODEL_NUMERIC_COLS])

    def transform(d):
        oh = pd.DataFrame(oh_enc.transform(d[CATEGORICAL_COLS]), columns=oh_enc.get_feature_names_out(), index=d.index)
        sc = pd.DataFrame(scaler.transform(d[MODEL_NUMERIC_COLS]), columns=MODEL_NUMERIC_COLS, index=d.index)
        return pd.concat([sc, oh], axis=1)

    X_train = transform(train_df)
    reg = RandomForestRegressor(n_estimators=80, max_depth=12, random_state=0, n_jobs=1)
    reg.fit(X_train, train_df["delay_days"])

    clf = RandomForestClassifier(n_estimators=80, max_depth=12, random_state=0, n_jobs=1)
    clf.fit(X_train, (train_df["qa_status"] == "합격").astype(int))

    # 유사 블록 검색(find_similar_blocks)은 df의 아무 block_id나 인덱싱할 수 있어야 하므로
    # NearestNeighbors 인덱스만은 표본이 아니라 전체 데이터로 만든다 (RF 학습과 달리 메모리 부담이 적음)
    X_full = transform(df)
    nn = NearestNeighbors(n_neighbors=11, metric="euclidean")
    nn.fit(X_full)

    _cache["models"] = {"oh_enc": oh_enc, "scaler": scaler, "X": X_full, "reg": reg, "clf": clf, "nn": nn}
    return _cache["models"]


def row_to_dict(row):
    d = row.to_dict()
    d["created_at"] = str(d["created_at"])
    return {k: (None if pd.isna(v) else v) for k, v in d.items()}


def get_filter_options():
    df = load_df()
    return {
        "ship_type": sorted(df["ship_type"].unique().tolist()),
        "department": sorted(df["department"].unique().tolist()),
        "process_stage": sorted(df["process_stage"].unique().tolist()),
        "priority": ["High", "Medium", "Low"],
        "qa_status": ["합격", "불합격"],
    }


def query_blocks(ship_type=None, department=None, priority=None, qa_status=None, min_delay_days=None, limit=20):
    df = load_df()
    out = df
    if ship_type:
        out = out[out["ship_type"] == ship_type]
    if department:
        out = out[out["department"] == department]
    if priority:
        out = out[out["priority"] == priority]
    if qa_status:
        out = out[out["qa_status"] == qa_status]
    if min_delay_days is not None:
        out = out[out["delay_days"] >= float(min_delay_days)]
    out = out.sort_values("delay_days", ascending=False).head(min(int(limit), 200))
    return [row_to_dict(r) for _, r in out.iterrows()]


def get_block_detail(block_id):
    df = load_df()
    row = df[df["block_id"] == int(block_id)]
    if row.empty:
        return None
    return row_to_dict(row.iloc[0])


def predict_delay(triangle_count, file_size_mb, lod_level, planned_days, department, process_stage, priority, ship_type):
    m = get_models()
    num = pd.DataFrame([{
        "triangle_count": triangle_count, "file_size_mb": file_size_mb,
        "lod_level": lod_level, "planned_days": planned_days,
    }])
    num_scaled = pd.DataFrame(m["scaler"].transform(num[MODEL_NUMERIC_COLS]), columns=MODEL_NUMERIC_COLS)
    cat = pd.DataFrame([{
        "department": department, "process_stage": process_stage,
        "priority": priority, "ship_type": ship_type,
    }])
    cat_encoded = pd.DataFrame(m["oh_enc"].transform(cat[CATEGORICAL_COLS]), columns=m["oh_enc"].get_feature_names_out())
    X_input = pd.concat([num_scaled, cat_encoded], axis=1).reindex(columns=m["X"].columns, fill_value=0)

    pred_delay = float(m["reg"].predict(X_input)[0])
    pred_qa_prob = float(m["clf"].predict_proba(X_input)[0][1])
    risk = "고위험" if pred_delay > 5 else ("주의" if pred_delay > 2 else "양호")
    return {
        "predicted_delay_days": round(pred_delay, 1),
        "qa_pass_probability": round(pred_qa_prob, 3),
        "risk_level": risk,
    }


def find_similar_blocks(block_id, top_k=5):
    df = load_df()
    m = get_models()
    idx_matches = df.index[df["block_id"] == int(block_id)]
    if len(idx_matches) == 0:
        return None
    pos = df.index.get_loc(idx_matches[0])

    k = min(int(top_k), 20) + 1
    distances, indices = m["nn"].kneighbors(m["X"].iloc[[pos]], n_neighbors=min(k, len(df)))
    results = []
    for dist, i in zip(distances[0], indices[0]):
        row = df.iloc[i]
        if int(row["block_id"]) == int(block_id):
            continue
        item = row_to_dict(row)
        item["similarity_distance"] = round(float(dist), 4)
        results.append(item)
    return results[:top_k]


def get_fleet_summary():
    df = load_df()
    g = df.groupby("ship_type").agg(
        vessels=("vessel_id", "nunique"),
        blocks=("block_id", "count"),
        avg_delay_days=("delay_days", "mean"),
        qa_pass_rate=("qa_status", lambda s: (s == "합격").mean()),
        contract_value_krw=("contract_value_krw", "mean"),
    ).reset_index()
    g["avg_delay_days"] = g["avg_delay_days"].round(2)
    g["qa_pass_rate"] = g["qa_pass_rate"].round(3)
    return g.to_dict(orient="records")


# 선종별 일반적인 제원 참고표 - DB에 넣어둔 개별 척의 실측치가 아니라 해당 선종 클래스의
# 통상적인 제원(재화중량톤/화물창 용량 등)이다. 개별 계약 척과는 다를 수 있음을 명시해서 노출한다.
TYPICAL_SPECS = {
    "LNG운반선": "약 174,000㎥급 화물창 (재화중량톤 약 95,000DWT급) - 대형 LNG운반선 통상 제원",
    "원유운반선(VLCC)": "약 300,000~320,000DWT급 - VLCC(Very Large Crude Carrier) 통상 제원",
    "가스운반선": "약 80,000~84,000㎥급 (LPG) - 대형 가스운반선(VLGC) 통상 제원",
    "컨테이너선": "약 20,000~24,000TEU급 - 메가 컨테이너선 통상 제원",
    "에탄운반선": "약 87,000㎥급 - 대형 에탄운반선(VLEC) 통상 제원",
    "해양플랜트(FLNG등)": "연산 250~340만톤급 LNG 처리 능력 - FLNG(부유식 액화천연가스 생산설비) 통상 제원",
}


def get_faq_answers():
    """미리 정의한 5가지 질문에 대한 답 - 라이브 DB 집계 + 정적 참고자료를 섞어 구성.
    실제 개별 척 제원(DWT 등)은 DB에 없으므로, 있는 것(형상/압축/블록수)은 라이브로 계산하고
    없는 것(선종별 통상 제원)은 '참고용 일반 제원'이라고 명시해서 혼동을 막는다."""
    df = load_df()
    total_blocks = len(df)
    total_vessels = df["vessel_id"].nunique()
    total_ship_types = df["ship_type"].nunique()
    avg_triangle = df["triangle_count"].mean()

    return [
        {
            "question": "지금 총 몇 개의 형상(블록)을 관리하고 있어?",
            "answer": f"현재 {total_ship_types}개 선종 · {total_vessels}척 · 블록 {total_blocks:,}개를 MariaDB에서 관리하고 있습니다.",
        },
        {
            "question": "원본 CAD 대비 압축률이 어느 정도야?",
            "answer": (
                "변환 파이프라인(converter.py)이 IFC/DXF의 B-REP 형상을 Tessellation으로 변환하면서 "
                "LOD 1 기준 원본 대비 약 10분의 1 크기로 압축하는 것을 설계 목표로 합니다 "
                "(정확한 압축률은 형상 복잡도에 따라 달라짐)."
            ),
        },
        {
            "question": "형상 메쉬(삼각형) 수는 평균 얼마나 돼?",
            "answer": f"현재 데이터셋 전체 블록의 평균 삼각형 수는 약 {avg_triangle:,.0f}개입니다 (선종별 형상 복잡도 배율이 반영되어 편차가 큼).",
        },
        {
            "question": "선종별 대표 제원(재화중량톤/용량)이 어떻게 돼?",
            "answer": "\n".join(f"- {k}: {v}" for k, v in TYPICAL_SPECS.items()),
            "note": "개별 계약 척의 실측 제원이 아니라 해당 선종 클래스의 통상적인 참고 제원입니다.",
        },
        {
            "question": "지금 API로 뭘 조회할 수 있어?",
            "answer": (
                "- query_blocks: 선종/부서/우선순위/QA상태로 블록 필터 조회\n"
                "- get_block_detail: 블록 하나의 전체 메타데이터\n"
                "- predict_delay: 새 블록 정보 입력 → 지연일수/QA합격확률 예측\n"
                "- find_similar_blocks: 메타데이터 기반 유사 블록 검색\n"
                "- get_fleet_summary: 선종별 척수/블록수/평균지연/QA합격률\n"
                "- get_roi_summary: 부서별 실측 ROI 요약\n"
                "(MCP 도구와 REST API(/api/ai/*) 양쪽에서 동일하게 제공됩니다)"
            ),
        },
    ]


def get_roi_summary():
    with engine.connect() as conn:
        latest_month = conn.execute(sa.text("SELECT MAX(month) FROM fact_review_session")).scalar()
        rows = conn.execute(sa.text("""
            SELECT d.name AS department, COUNT(*) AS sessions, SUM(s.cost_saved_krw) AS cost_saved
            FROM fact_review_session s
            JOIN dim_department d ON d.department_id = s.department_id
            WHERE s.month = :m
            GROUP BY d.name
        """), {"m": latest_month}).mappings().all()
        rows = [{"department": r["department"], "sessions": int(r["sessions"]), "cost_saved": int(r["cost_saved"])} for r in rows]

    dev_cost_krw = 15_000_000
    monthly_saving = sum(r["cost_saved"] for r in rows)
    annual_saving = monthly_saving * 12
    roi_pct = ((annual_saving - dev_cost_krw) / dev_cost_krw * 100) if dev_cost_krw else None
    payback_months = (dev_cost_krw / monthly_saving) if monthly_saving else None

    return {
        "latest_month": latest_month,
        "by_department": rows,
        "monthly_saving_krw": monthly_saving,
        "annual_saving_krw": annual_saving,
        "roi_pct": round(roi_pct, 1) if roi_pct is not None else None,
        "payback_months": round(payback_months, 1) if payback_months is not None else None,
    }
