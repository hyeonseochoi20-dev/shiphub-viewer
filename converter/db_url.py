# -*- coding: utf-8 -*-
"""PostgreSQL 접속 URL 조립 — app.py / production_data.py / setup_postgres.py 공용.

Neon·Supabase 같은 관리형 서비스는 DATABASE_URL 하나만 준다. 그래서 그 값을
최우선으로 쓰고, 없으면 표준 PG* 환경변수로 조립한다. 관리형 서비스가 주는
'postgresql://' 스킴은 SQLAlchemy에서 psycopg3 드라이버를 명시해야 하므로
'postgresql+psycopg://'로 바꿔 준다.
"""
import os


def build_db_url():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        for old in ("postgresql+psycopg://", "postgresql://", "postgres://"):
            if raw.startswith(old):
                return "postgresql+psycopg://" + raw[len(old):]
        return raw
    return (
        "postgresql+psycopg://{user}:{password}@{host}:{port}/{db}".format(
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
            db=os.environ.get("PGDATABASE", "shiphub"),
        )
    )


def has_db_config():
    """접속 정보가 아예 없으면 DB 연결을 시도하지 않는다.
    없는 호스트에 붙으려다 수십 초씩 멈추는 것을 막기 위한 가드."""
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("PGHOST"))
