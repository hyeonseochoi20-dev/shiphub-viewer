#!/usr/bin/env python3
"""
MariaDB 스키마 생성 + 데이터 적재
- schema.sql (개념적/논리적/물리적 스키마 설계 문서 겸 물리 DDL)을 실행해 정규화된
  차원(dim_*)/사실(fact_*) 테이블을 만들고, 기존 SQLite 버전과 동일한 통계 특성을 갖는
  생산 블록 + 리뷰세션 데이터를 정규화된 형태로 채운다.

연결 정보는 환경변수로 오버라이드 가능 (기본값은 로컬 기본 설치 기준):
  MARIADB_HOST (기본 localhost) / MARIADB_PORT (기본 3306)
  MARIADB_USER (기본 root) / MARIADB_PASSWORD (기본 빈 문자열)

실행: python setup_mariadb.py
"""
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pymysql

BASE = Path(__file__).parent

DB_CONFIG = dict(
    host=os.environ.get("MARIADB_HOST", "localhost"),
    port=int(os.environ.get("MARIADB_PORT", "3306")),
    user=os.environ.get("MARIADB_USER", "root"),
    password=os.environ.get("MARIADB_PASSWORD", ""),
    charset="utf8mb4",
)

# 삼성중공업 실제 주력 선종 기준 - 척수/계약금액은 2026년 실제 수주 공시를 반영해 구성
# (선종, 동시 건조 척수, 척당 블록수 범위, 형상 복잡도 배율, 대표 계약금액(원))
#
# 척수 근거: 2026년 상선 수주 공시 기준 LNG운반선 14척·원유운반선 12척·가스운반선 4척·
#   컨테이너선 2척·에탄운반선 2척(뉴스핌/edaily 등 2026-06~08 보도) + 건조기간(약 2~3년)을
#   고려해 이전 연도 잔량까지 포함한 "현재 동시 건조 중" 규모로 확장 추정.
#   해양플랜트는 2026년 해양 부문 수주목표(82억 달러) 반영.
# 계약금액 근거: LNG운반선 3,855억원은 2026-06 삼성중공업 실제 수주 공시(뉴스핌).
#   그 외 선종은 최근 시황 기준 시장가 추정치(각주 표기, 개별 계약과 다를 수 있음).
SHIP_TYPES = [
    ("LNG운반선", 20, (240, 320), 1.35, 385_500_000_000),
    ("원유운반선(VLCC)", 16, (220, 300), 1.00, 140_000_000_000),
    ("가스운반선", 6, (160, 220), 1.10, 100_000_000_000),
    ("컨테이너선", 4, (260, 360), 1.15, 200_000_000_000),
    ("에탄운반선", 3, (150, 200), 1.20, 110_000_000_000),
    ("해양플랜트(FLNG등)", 4, (200, 300), 1.60, 2_500_000_000_000),
]
DEPARTMENTS = [
    ("생산관리(가공/건조)", 55000),
    ("생산관리(의장)", 52000),
    ("품질(의장품질관리)", 58000),
    ("기본설계", 62000),
    ("자동화솔루션", 60000),
]
STAGES = ["절단", "조립", "탑재", "의장", "도장", "시운전"]
PRIORITIES = ["High", "Medium", "Low"]
BLOCK_PREFIXES = ["B", "E", "S"]
REVIEW_TYPES = ["설계검토", "간섭검사", "공정검토", "QA검수", "협력사공유"]

# ROI 램프업(온보딩 시점, 정상 가동까지 개월수) - generate_roi_data.py와 동일 스토리
ROI_MONTHS = 6
RAMP = [0.30, 0.52, 0.70, 0.85, 0.95, 1.0]
ONBOARD_MONTH = {"자동화솔루션": 0, "기본설계": 1, "생산관리(의장)": 1, "품질(의장품질관리)": 2, "생산관리(가공/건조)": 3}
TARGET_SESSIONS = {"생산관리(가공/건조)": 25, "생산관리(의장)": 20, "품질(의장품질관리)": 30, "기본설계": 18, "자동화솔루션": 22}


def month_labels(n):
    today = datetime.now()
    labels = []
    for i in range(n - 1, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12
            y -= 1
        labels.append(f"{y}-{m:02d}")
    return labels


def run_schema(cursor):
    sql = (BASE / "schema.sql").read_text(encoding="utf-8")
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            cursor.execute(stmt)


def main(seed=42):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as c:
            run_schema(c)
            conn.commit()

            c.execute("USE shiphub")

            # --- 차원 테이블 ---
            ship_type_ids = {}
            for name, _, _, mult, contract_value in SHIP_TYPES:
                c.execute(
                    "INSERT INTO dim_ship_type (name, complexity_multiplier, contract_value_krw) VALUES (%s, %s, %s)",
                    (name, mult, contract_value),
                )
                ship_type_ids[name] = c.lastrowid

            dept_ids = {}
            for name, cost in DEPARTMENTS:
                c.execute(
                    "INSERT INTO dim_department (name, hourly_cost_krw) VALUES (%s, %s)",
                    (name, cost),
                )
                dept_ids[name] = c.lastrowid

            stage_ids = {}
            for name in STAGES:
                c.execute("INSERT INTO dim_process_stage (name) VALUES (%s)", (name,))
                stage_ids[name] = c.lastrowid

            conn.commit()

            # --- 척(dim_vessel) + 생산 블록(fact_production_block) ---
            rng = np.random.default_rng(seed)
            random.seed(seed)
            block_seq = 0
            block_rows = []

            for ship_type, vessel_count, (blk_lo, blk_hi), mult, _contract_value in SHIP_TYPES:
                st_id = ship_type_ids[ship_type]
                for v in range(1, vessel_count + 1):
                    vessel_code = f"{ship_type.split('(')[0]}-{v:02d}"
                    c.execute(
                        "INSERT INTO dim_vessel (ship_type_id, vessel_code) VALUES (%s, %s)",
                        (st_id, vessel_code),
                    )
                    vessel_id = c.lastrowid

                    n_blocks = int(rng.integers(blk_lo, blk_hi + 1))
                    for _ in range(n_blocks):
                        block_seq += 1
                        block_name = f"{vessel_code}-{random.choice(BLOCK_PREFIXES)}{block_seq:05d}"
                        stage = random.choice(STAGES)
                        dept = random.choice(list(dept_ids.keys()))
                        priority = random.choices(PRIORITIES, weights=[0.2, 0.5, 0.3])[0]

                        triangle_count = int(rng.lognormal(mean=10, sigma=1.1) * mult)
                        file_size_mb = max(0.1, round(triangle_count / 45000 + rng.normal(0, 0.3), 2))
                        lod_level = random.choice([1, 2, 3])
                        planned_days = max(3, int(rng.normal(14, 4)))

                        complexity_factor = triangle_count / 100000
                        priority_factor = {"High": -1.5, "Medium": 0.0, "Low": 1.5}[priority]
                        delay_days = round(complexity_factor * 3 + priority_factor + rng.normal(0, 1.5), 1)
                        delay_days = max(-3.0, delay_days)
                        actual_days = round(planned_days + delay_days)

                        qa_defect_count = max(0, int(rng.normal(complexity_factor * 4, 2)))
                        qa_status = "불합격" if qa_defect_count > 5 else "합격"

                        days_ago = int(rng.integers(0, 180))
                        created_at = datetime.now() - timedelta(days=days_ago, hours=int(rng.integers(0, 24)))

                        qa_defect_value = None if rng.random() < 0.05 else qa_defect_count
                        file_size_value = None if rng.random() < 0.03 else file_size_mb

                        block_rows.append((
                            vessel_id, stage_ids[stage], dept_ids[dept], block_name, priority,
                            triangle_count, file_size_value, lod_level, planned_days, actual_days,
                            delay_days, qa_defect_value, qa_status, created_at,
                        ))

            c.executemany(
                """INSERT INTO fact_production_block
                (vessel_id, stage_id, department_id, block_name, priority, triangle_count,
                 file_size_mb, lod_level, planned_days, actual_days, delay_days,
                 qa_defect_count, qa_status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                block_rows,
            )
            conn.commit()

            # --- 리뷰 세션(fact_review_session) - 부서 순차 온보딩 램프업 ---
            months = month_labels(ROI_MONTHS)
            session_rows = []
            for dept, dept_id in dept_ids.items():
                onboard = ONBOARD_MONTH[dept]
                target = TARGET_SESSIONS[dept]
                for idx, month in enumerate(months):
                    months_active = idx - onboard
                    if months_active < 0:
                        continue
                    ramp = RAMP[min(months_active, len(RAMP) - 1)]
                    sessions = max(1, round(target * ramp + rng.normal(0, 1.2)))
                    hourly_cost = dict(DEPARTMENTS)[dept]

                    for _ in range(sessions):
                        review_type = random.choice(REVIEW_TYPES)
                        t_count = int(rng.lognormal(mean=10.5, sigma=1.0))
                        traditional_min = max(5.0, t_count / 3000 + rng.normal(0, 3))
                        lightweight_sec = max(1.0, t_count / 150000 + rng.normal(0, 0.5))
                        time_saved_min = round(traditional_min - lightweight_sec / 60, 1)
                        cost_saved = round(time_saved_min / 60 * hourly_cost)

                        session_rows.append((
                            dept_id, month, review_type, t_count,
                            round(traditional_min, 1), round(lightweight_sec, 2),
                            time_saved_min, cost_saved,
                        ))

            c.executemany(
                """INSERT INTO fact_review_session
                (department_id, month, review_type, triangle_count, traditional_load_min,
                 lightweight_load_sec, time_saved_min, cost_saved_krw)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                session_rows,
            )
            conn.commit()

            print(f"완료: 블록 {len(block_rows):,}건, 리뷰세션 {len(session_rows):,}건 적재 (MariaDB shiphub 스키마)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
