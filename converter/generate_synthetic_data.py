#!/usr/bin/env python3
"""
가상 생산관리/QA 데이터셋 생성 (SQLite 오프라인 버전 - 참고/백업용, 실서비스는 setup_mariadb.py 사용)
- 변환 메타데이터(형상 복잡도)와 공정관리/QA 지표 사이에 실제 상관관계를 심어서
  scikit-learn으로 의미 있는 상관관계/예측 분석이 가능하도록 구성
- 선종별 척수/계약금액은 실제 삼성중공업 2026년 수주 공시 및 시장 데이터를 참고해 구성했다
  (정확한 출처는 SHIP_TYPES 주석 참고, setup_mariadb.py와 동일 파라미터 사용)
"""
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

DB_FILE = Path(__file__).parent / "conversion.db"

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
    ("LNG운반선", 20, (240, 320), 1.35, 385_500_000_000),      # 실측: 2026-06 SHI 수주 공시
    ("원유운반선(VLCC)", 16, (220, 300), 1.00, 140_000_000_000),  # 추정 시장가
    ("가스운반선", 6, (160, 220), 1.10, 100_000_000_000),          # 추정 시장가
    ("컨테이너선", 4, (260, 360), 1.15, 200_000_000_000),          # 추정 시장가 (대형 메가컨테이너선)
    ("에탄운반선", 3, (150, 200), 1.20, 110_000_000_000),          # 추정 시장가
    ("해양플랜트(FLNG등)", 4, (200, 300), 1.60, 2_500_000_000_000),  # 추정 (해양 부문 특성상 초고가)
]

# 삼성중공업 실제 채용공고에서 확인된 부문/직무 명칭 기준 (생산관리, 품질, 설계, 자동화솔루션)
DEPARTMENTS = ["생산관리(가공/건조)", "생산관리(의장)", "품질(의장품질관리)", "기본설계", "자동화솔루션"]
STAGES = ["절단", "조립", "탑재", "의장", "도장", "시운전"]
PRIORITIES = ["High", "Medium", "Low"]
BLOCK_PREFIXES = ["B", "E", "S"]  # Block / Erection / Superstructure

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

# 공정단계별 지연 경향 (하류 공정일수록 상류 트레이드 대기·외부요인 영향이 커짐 - 도장/시운전은
# 기상·선행공정 지연에 취약, 절단/조립은 예측 가능한 정형 작업이라 지연폭이 작음)
STAGE_DELAY_FACTOR = {"절단": -0.3, "조립": -0.1, "탑재": 0.2, "의장": 0.3, "도장": 0.6, "시운전": 0.9}
# 부서별 지연 경향 (자동화솔루션은 아직 전 공정 롤아웃이 끝나지 않아 수작업 병행 구간에서
# 산발적 지연이 발생 - 완전 원인은 아니지만 약한 상관관계로 반영)
DEPT_DELAY_FACTOR = {
    "생산관리(가공/건조)": 0.0, "생산관리(의장)": 0.1, "품질(의장품질관리)": -0.2,
    "기본설계": -0.1, "자동화솔루션": 0.7,
}


def init_table(conn):
    conn.execute("DROP TABLE IF EXISTS production_records")
    conn.execute(
        """CREATE TABLE production_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ship_type TEXT,
            contract_value_krw INTEGER,
            vessel_id TEXT,
            block_name TEXT,
            process_stage TEXT,
            department TEXT,
            priority TEXT,
            triangle_count INTEGER,
            file_size_mb REAL,
            lod_level INTEGER,
            planned_days INTEGER,
            actual_days INTEGER,
            delay_days REAL,
            qa_defect_count INTEGER,
            qa_status TEXT,
            created_at TEXT
        )"""
    )
    conn.commit()


def generate(seed=42):
    conn = sqlite3.connect(DB_FILE)
    init_table(conn)

    rng = np.random.default_rng(seed)
    random.seed(seed)
    rows = []
    block_seq = 0

    for ship_type, vessel_count, (blk_lo, blk_hi), complexity_mult, contract_value in SHIP_TYPES:
        for v in range(1, vessel_count + 1):
            vessel_id = f"{ship_type.split('(')[0]}-{v:02d}"
            n_blocks = int(rng.integers(blk_lo, blk_hi + 1))

            for _ in range(n_blocks):
                block_seq += 1
                block_name = f"{vessel_id}-{random.choice(BLOCK_PREFIXES)}{block_seq:05d}"
                dept = random.choice(DEPARTMENTS)
                stage = random.choice(DEPT_STAGES[dept])
                priority = random.choices(PRIORITIES, weights=[0.2, 0.5, 0.3])[0]

                # 형상 복잡도 (실제 변환 파이프라인의 triangle_count를 흉내낸 가상값) - 선종별 배율 적용
                triangle_count = int(rng.lognormal(mean=10, sigma=1.1) * complexity_mult)
                file_size_mb = max(0.1, round(triangle_count / 45000 + rng.normal(0, 0.3), 2))
                lod_level = random.choice([1, 2, 3])

                planned_days = max(3, int(rng.normal(14, 4)))

                # 복잡도가 높을수록 지연 증가, 우선순위 높으면 지연 감소 (+ 공정단계/부서의 약한 영향)
                complexity_factor = triangle_count / 100000
                priority_factor = {"High": -1.2, "Medium": 0.0, "Low": 1.2}[priority]
                stage_factor = STAGE_DELAY_FACTOR[stage]
                dept_factor = DEPT_DELAY_FACTOR[dept]
                # 노이즈 표준편차를 체계적 요인들의 합과 비슷한 크기로 잡아, 회귀모델이
                # 생성식을 그대로 역산하지 않고 "부분적으로만 설명 가능한" 현실적인 관계가 되게 한다
                delay_days = round(
                    complexity_factor * 3 + priority_factor + stage_factor + dept_factor
                    + rng.normal(0, 2.2),
                    1,
                )
                delay_days = max(-6.0, delay_days)
                actual_days = round(planned_days + delay_days)

                # 복잡도가 높을수록 QA 결함 수 증가
                qa_defect_count = max(0, int(rng.normal(complexity_factor * 4, 2)))
                qa_status = "불합격" if qa_defect_count > 5 else "합격"

                # 최근 180일에 걸쳐 분산 - 요일/월별 분석(datetime 전처리 실습)이 의미를 가지려면
                # 전 레코드가 동일 시각이어서는 안 됨
                days_ago = int(rng.integers(0, 180))
                created_at = (datetime.now() - timedelta(days=days_ago, hours=int(rng.integers(0, 24)))).isoformat()

                # 실제 현장 데이터처럼 일부 결측치를 의도적으로 섞음(전처리 실습용):
                # QA 결함수 - 아직 미검수라 값이 없는 경우 / 파일 크기 - 변환 로그 유실로 기록 누락된 경우
                qa_defect_value = None if rng.random() < 0.05 else qa_defect_count
                file_size_value = None if rng.random() < 0.03 else file_size_mb

                rows.append(
                    (
                        ship_type, contract_value, vessel_id, block_name, stage, dept, priority,
                        triangle_count, file_size_value, lod_level,
                        planned_days, actual_days, delay_days,
                        qa_defect_value, qa_status, created_at,
                    )
                )

    conn.executemany(
        """INSERT INTO production_records
        (ship_type, contract_value_krw, vessel_id, block_name, process_stage, department, priority,
         triangle_count, file_size_mb, lod_level, planned_days, actual_days,
         delay_days, qa_defect_count, qa_status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    n_vessels = sum(v for _, v, _, _, _ in SHIP_TYPES)
    print(f"가상 생산 데이터 {len(rows):,}건 생성 완료 (선종 {len(SHIP_TYPES)}종 · 동시 건조 {n_vessels}척): {DB_FILE}")


if __name__ == "__main__":
    generate()
