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
from collections import Counter
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

# 부서가 실제로 관여하는 공정단계만 허용 (기본설계는 절단/조립 착수 전 설계검토 단계까지만 관여,
# 생산관리(가공/건조)는 선체 조립 단계, 생산관리(의장)/품질은 의장 이후 단계, 자동화솔루션은
# 스캔·로봇용접 자동화가 실제 배치된 선체 가공 단계에서만 개입 - 이미 지나간 절단 단계에
# 자동화솔루션팀이나 도장 단계에 기본설계팀이 붙는 등의 비현실적 조합을 막는다)
DEPT_STAGES = {
    "생산관리(가공/건조)": ["절단", "조립", "탑재"],
    "생산관리(의장)": ["의장", "도장", "시운전"],
    "품질(의장품질관리)": ["의장", "도장", "시운전"],
    "기본설계": ["절단", "조립"],
    "자동화솔루션": ["절단", "조립", "탑재"],
}

# 공정단계 특성 - 지연을 '상수 오프셋'으로 주는 대신, 지연이 실제로 발생하는 세 가지 경로의
# 민감도로 표현한다. 부서는 지연의 직접 원인이 아니다(부서가 느려서 늦는 게 아니라, 그 부서가
# 맡은 공정이 어떤 성격이냐에 따라 늦는다) - 그래서 부서별 상수는 아예 두지 않고,
# DEPT_STAGES를 통해 간접적으로만 드러나게 한다.
#   congestion: 야드 자원(크레인·도크·인력) 경합에 얼마나 노출되는가
#   weather   : 옥외 작업 비중 - 혹한기/장마철에 얼마나 밀리는가
#   rework    : QA 결함 1건이 재작업으로 이어질 때 걸리는 시간 배수
STAGE_PROFILE = {
    "절단":   {"congestion": 0.6, "weather": 0.0, "rework": 0.5},
    "조립":   {"congestion": 0.9, "weather": 0.1, "rework": 0.9},
    "탑재":   {"congestion": 1.4, "weather": 0.4, "rework": 1.0},
    "의장":   {"congestion": 1.2, "weather": 0.2, "rework": 1.3},
    "도장":   {"congestion": 0.7, "weather": 1.0, "rework": 0.8},
    "시운전": {"congestion": 1.0, "weather": 0.6, "rework": 1.5},
}

# 우선순위는 '작업 속도'가 아니라 '대기열 순번'에만 작용한다 - 우선순위를 높인다고 용접이
# 빨라지지는 않고, 크레인·도크를 먼저 잡을 뿐이다. 그래서 상수 덧셈이 아니라 대기시간에
# 곱해지는 배수로 들어가고, 결과적으로 "혼잡할 때만 우선순위가 의미 있다"는 상호작용이 생긴다.
PRIORITY_WAIT_MULT = {"High": 0.35, "Medium": 1.0, "Low": 1.55}


def season_factor(month):
    """혹한기(12~2월) 도장 품질 이슈·장마철(6~7월) 옥외작업 중단을 반영한 계절 가중치."""
    if month in (12, 1, 2):
        return 1.0
    if month in (6, 7):
        return 0.8
    return 0.25

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

                    # 블록별 담당 부서·공정을 먼저 확정한 뒤, 공정별로 몇 개가 동시에 물려 있는지 센다.
                    assign = []
                    for _ in range(n_blocks):
                        d = random.choice(list(dept_ids.keys()))
                        assign.append((d, random.choice(DEPT_STAGES[d])))
                    stage_cnt = Counter(st for _, st in assign)

                    # 같은 척·같은 공정의 블록들은 같은 크레인·도크·인력을 두고 경쟁한다.
                    # 이 '야드 혼잡도'를 순수 난수로 두면 회귀가 손댈 수 없는 몫이 되어버리는데,
                    # 실제 조선소는 어느 공정에 물량이 몰려 있는지를 알 수 있다. 그래서 혼잡도를
                    # '그 공정에 배정된 동시 물량 / 평균 물량'에 연동시키고 잔여 변동만 난수로 둔다
                    # - 관측 가능한 부분은 모델이 배울 수 있고, 나머지만 진짜 노이즈로 남는다.
                    avg_cnt = max(1.0, n_blocks / len(STAGES))
                    yard_load = {
                        s: (stage_cnt.get(s, 0) / avg_cnt) ** 1.6 * float(rng.lognormal(0.0, 0.12))
                        for s in STAGES
                    }

                    for bi in range(n_blocks):
                        block_seq += 1
                        block_name = f"{vessel_code}-{random.choice(BLOCK_PREFIXES)}{block_seq:05d}"
                        dept, stage = assign[bi]
                        priority = random.choices(PRIORITIES, weights=[0.2, 0.5, 0.3])[0]
                        prof = STAGE_PROFILE[stage]

                        triangle_count = int(rng.lognormal(mean=10, sigma=1.1) * mult)
                        file_size_mb = max(0.1, round(triangle_count / 45000 + rng.normal(0, 0.3), 2))
                        lod_level = random.choice([1, 2, 3])
                        planned_days = max(3, int(rng.normal(14, 4)))

                        days_ago = int(rng.integers(0, 180))
                        created_at = datetime.now() - timedelta(days=days_ago, hours=int(rng.integers(0, 24)))

                        # --- (1) QA 결함: 복잡한 형상일수록 결함이 늘지만 선형이 아니라 로그로
                        # 포화한다(2배 복잡하다고 결함이 2배가 되지는 않는다). 카운트 변수이므로 푸아송.
                        defect_rate = 0.8 + 5.2 * np.log10(triangle_count / 20000 + 1)
                        qa_defect_count = int(rng.poisson(defect_rate))

                        # QA 판정: '결함 N개 이상이면 불합격' 같은 딱 떨어지는 임계값을 쓰면
                        # 판정이 결함 수의 함수가 되어버려 분류 모델이 그 규칙만 외운다(데이터 누수).
                        # 실제 검사는 결함 건수뿐 아니라 심각도·공정 특성·검사자 재량이 함께
                        # 작용하므로 로지스틱 확률로 판정한다.
                        z = (-3.35 + 0.60 * qa_defect_count
                             + 0.55 * (prof["rework"] - 1.0)
                             + 0.45 * float(rng_qa.normal()))
                        p_fail = 1.0 / (1.0 + np.exp(-z))
                        qa_status = "불합격" if rng_qa.random() < p_fail else "합격"

                        # --- (2) 재작업: 결함이 나야 비로소 다시 손을 댄다. 결함 1건당 소요가
                        # 지수분포라 몇 건만 겹쳐도 꼬리가 길어진다(복합 푸아송).
                        rework_days = float(
                            sum(rng.gamma(3.0, 0.7 / 3.0) for _ in range(qa_defect_count))
                        ) * prof["rework"]

                        # --- (3) 대기: 야드가 혼잡할수록 늘고, 우선순위는 여기에만 작용한다.
                        wait_days = (
                            prof["congestion"] * yard_load[stage]
                            * PRIORITY_WAIT_MULT[priority] * float(rng.gamma(3.0, 1.0 / 3.0))
                        )

                        # --- (4) 기상: 옥외 비중이 큰 공정만, 그것도 계절을 탄다.
                        weather_days = (
                            prof["weather"] * season_factor(created_at.month)
                            * float(rng.gamma(3.0, 1.2 / 3.0))
                        )

                        # --- (5) 계획에 잡아둔 여유: 대부분의 지연은 여기서 흡수되고, 남는 것만
                        # 실제 지연으로 드러난다. 여유가 넉넉하면 조기 완료(음수)도 나온다.
                        slack_days = float(rng.normal(1.3, planned_days * 0.10))

                        delay_days = round(rework_days + wait_days + weather_days - slack_days, 1)
                        delay_days = max(-6.0, delay_days)
                        actual_days = max(1, round(planned_days + delay_days))

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
