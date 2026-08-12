# MariaDB 스키마/데이터 재적재 스크립트 (템플릿) - 기존 데이터는 전부 DROP 후 재생성됨
# 이 파일을 run_migration.ps1로 복사한 뒤 아래 값을 실제 MariaDB 접속정보로 채워 넣으세요.
# run_migration.ps1은 .gitignore에 등록되어 있어 커밋되지 않습니다.

$env:MARIADB_HOST = "<YOUR_MARIADB_HOST>"
$env:MARIADB_PORT = "<YOUR_MARIADB_PORT>"
$env:MARIADB_USER = "<YOUR_MARIADB_USER>"
$env:MARIADB_PASSWORD = "<YOUR_MARIADB_PASSWORD>"

Set-Location $PSScriptRoot
python setup_mariadb.py
