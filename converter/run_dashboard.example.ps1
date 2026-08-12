# ShipHub 생산관리 대시보드 실행 스크립트 (템플릿)
# 이 파일을 run_dashboard.ps1로 복사한 뒤 아래 값을 실제 MariaDB 접속정보로 채워 넣으세요.
# run_dashboard.ps1은 .gitignore에 등록되어 있어 커밋되지 않습니다.

$env:MARIADB_HOST = "<YOUR_MARIADB_HOST>"
$env:MARIADB_PORT = "<YOUR_MARIADB_PORT>"
$env:MARIADB_USER = "<YOUR_MARIADB_USER>"
$env:MARIADB_PASSWORD = "<YOUR_MARIADB_PASSWORD>"

Set-Location $PSScriptRoot
streamlit run app.py --server.headless true --server.port 8501
