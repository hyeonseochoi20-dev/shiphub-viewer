#!/usr/bin/env python3
"""
경량 가시화 도입에 따른 부서별 효용성/ROI 가상 데이터셋 생성 (SQLite 오프라인 버전 - 참고/백업용)
- 실서비스(app.py)는 MariaDB(setup_mariadb.py로 적재)의 fact_review_session을 사용한다.
  이 스크립트는 MariaDB 없이 로컬에서 빠르게 데이터를 살펴보고 싶을 때 쓰는 오프라인 백업 경로다.
- 기존 방식(원본 중량 CAD 파일 오픈)과 변환 후 경량 가시화(glTF+LOD) 로딩 시간 차이를
  형상 복잡도에 비례하도록 구성하고, 절감 시간 -> 절감 비용 -> 부서별 ROI로 환산
- 도입 첫 달부터 전 부서가 100% 활용했다고 하면 비현실적이므로, 부서별 온보딩 시점이
  다르고 월별로 활용도가 점진 증가(램프업)하는 6개월 시계열로 구성
"""
import random
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np

DB_FILE = Path(__file__).parent / "conversion.db"

# 삼성중공업 실제 채용공고 기준 부문/직무 명칭 (부서명, 정상 가동시 월간 검토 세션 수, 시간당 인건비 KRW, 온보딩 시작월 인덱스)
# 자동화솔루션이 파일럿 부서로 가장 먼저 도입, 이후 순차 확산되는 것이 실제 신기술 롤아웃과 일치
DEPARTMENTS = [
    ("자동화솔루션", 22, 60000, 0),
    ("기본설계", 18, 62000, 1),
    ("생산관리(의장)", 20, 52000, 1),
    ("품질(의장품질관리)", 30, 58000, 2),
    ("생산관리(가공/건조)", 25, 55000, 3),
]

REVIEW_TYPES = ["설계검토", "간섭검사", "공정검토", "QA검수", "협력사공유"]

MONTHS = 6
# 온보딩 이후 월차별 활용도 램프업 곡선 (0개월차=파일럿 적응기, 4개월차 이후 정상 가동)
RAMP = [0.30, 0.52, 0.70, 0.85, 0.95, 1.0]


def _month_labels(n):
    today = date.today()
    y, m = today.year, today.month
    labels = []
    for i in range(n - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        labels.append(f"{yy}-{mm:02d}")
    return labels


def init_table(conn):
    conn.execute("DROP TABLE IF EXISTS visualization_roi")
    conn.execute(
        """CREATE TABLE visualization_roi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT,
            month TEXT,
            review_type TEXT,
            triangle_count INTEGER,
            traditional_load_min REAL,
            lightweight_load_sec REAL,
            time_saved_min REAL,
            hourly_cost_krw INTEGER,
            cost_saved_krw REAL
        )"""
    )
    conn.commit()


def generate(seed=7):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    conn = sqlite3.connect(DB_FILE)
    init_table(conn)

    month_labels = _month_labels(MONTHS)
    rows = []

    for dept, target_sessions, hourly_cost, onboard_month in DEPARTMENTS:
        for month_idx, month in enumerate(month_labels):
            months_active = month_idx - onboard_month
            if months_active < 0:
                continue  # 아직 온보딩 전 - 도입 실적 없음
            ramp = RAMP[min(months_active, len(RAMP) - 1)]
            sessions = max(1, round(target_sessions * ramp + rng.normal(0, 1.2)))

            for _ in range(sessions):
                review_type = random.choice(REVIEW_TYPES)
                triangle_count = int(rng.lognormal(mean=10.5, sigma=1.0))

                # 기존 방식: 원본 중량 CAD 파일 오픈 (형상 복잡도에 비례, 최소 5분)
                traditional_min = max(5.0, triangle_count / 3000 + rng.normal(0, 3))
                # 변환 후 경량 가시화(glTF + LOD 압축): 초 단위 로딩
                lightweight_sec = max(1.0, triangle_count / 150000 + rng.normal(0, 0.5))

                time_saved_min = round(traditional_min - lightweight_sec / 60, 1)
                cost_saved = round(time_saved_min / 60 * hourly_cost)

                rows.append(
                    (
                        dept, month, review_type, triangle_count,
                        round(traditional_min, 1), round(lightweight_sec, 2),
                        time_saved_min, hourly_cost, cost_saved,
                    )
                )

    conn.executemany(
        """INSERT INTO visualization_roi
        (department, month, review_type, triangle_count, traditional_load_min, lightweight_load_sec,
         time_saved_min, hourly_cost_krw, cost_saved_krw)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"가시화 ROI 레코드 {len(rows)}건 생성 완료 (부서 {len(DEPARTMENTS)}개, {MONTHS}개월 램프업 시계열)")


if __name__ == "__main__":
    generate()
