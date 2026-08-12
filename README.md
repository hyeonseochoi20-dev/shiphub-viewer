# ShipHub Viewer

조선소 BIM/CAD 경량화 3D 뷰어 + 생산관리 ML 대시보드.

## 구성

- `converter/` — IFC/DXF → SLF(경량 포맷) 변환 서비스(Flask), 생산관리 Streamlit 대시보드(`app.py`), MariaDB 스키마·마이그레이션, MCP 서버.
- `web-viewer/` — React/Three.js 기반 3D 뷰어 (탑재 시뮬레이션, 단면, 계측, AI 쿼리 패널 등).

## 실행 준비

### converter/

```
pip install -r converter/requirements.txt
```

`converter/run_dashboard.example.ps1`, `converter/run_migration.example.ps1`을 각각 `run_dashboard.ps1`, `run_migration.ps1`로 복사한 뒤 MariaDB 접속정보(`MARIADB_HOST`/`PORT`/`USER`/`PASSWORD`)를 채워 넣으세요. 두 파일은 `.gitignore`에 등록되어 있어 커밋되지 않습니다.

```
# 최초 1회: 스키마/샘플 데이터 적재
./converter/run_migration.ps1

# 변환 서비스
python converter/converter.py

# 생산관리 대시보드
./converter/run_dashboard.ps1
```

MCP 서버를 AI 클라이언트에 등록하려면 `converter/mcp_config_example.json`을 참고해 값을 채운 뒤 사용하세요.

### web-viewer/

```
cd web-viewer
npm install
npm run dev
```
