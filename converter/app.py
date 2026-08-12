#!/usr/bin/env python3
"""
조선소 생산관리 데이터 - 머신러닝 프로젝트 Streamlit 대시보드

교안 6단계 구성을 그대로 따른다:
1. 데이터 정의 -> 2. 데이터 준비 -> 3. 데이터 전처리 -> 4. 데이터 분석 -> 5. 학습/예측/평가 -> 6. 성능 향상
+ 7. 실시간 예측 (학습된 모델을 실제로 사용해보는 캡스톤 섹션)

실행: streamlit run app.py
"""
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import sqlalchemy as sa
import streamlit as st
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score, r2_score, root_mean_squared_error
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

BASE = Path(__file__).parent

# 교안 68~70p에서 다룬 pymysql/SQLAlchemy 연결 패턴 그대로 사용.
# 연결 정보는 환경변수로 오버라이드 가능 (setup_mariadb.py와 동일한 기본값).
DB_URL = "mysql+pymysql://{user}:{password}@{host}:{port}/shiphub?charset=utf8mb4".format(
    user=os.environ.get("MARIADB_USER", "root"),
    password=os.environ.get("MARIADB_PASSWORD", ""),
    host=os.environ.get("MARIADB_HOST", "localhost"),
    port=os.environ.get("MARIADB_PORT", "3306"),
)
engine = sa.create_engine(DB_URL, pool_pre_ping=True)

st.set_page_config(page_title="조선소 생산관리 ML 대시보드", page_icon="⚓", layout="wide")

# 전처리/EDA 단계에서 보여주는 전체 수치형 컬럼 (설명용)
NUMERIC_COLS = ["triangle_count", "file_size_mb", "lod_level", "planned_days", "actual_days", "qa_defect_count"]
# 실제 모델 입력 피처 - actual_days(=delay_days+planned_days로 target과 수학적으로 직결)와
# qa_defect_count(qa_status를 결정짓는 규칙 자체)는 데이터 누수(data leakage)이므로 제외
MODEL_NUMERIC_COLS = ["triangle_count", "file_size_mb", "lod_level", "planned_days"]
CATEGORICAL_COLS = ["department", "process_stage", "priority", "ship_type"]

# Barker 표기법 ERD (schema.sql 물리 스키마 기준 - 실선/까마귀발=필수·다수, 점선=선택)
ERD_SVG_BARKER = """
<div style="border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:20px;background:rgba(255,255,255,0.02);overflow-x:auto;">
<svg viewBox="0 0 1000 700" style="width:100%;height:auto;min-width:760px;font-family:inherit;">
  <defs>
    <marker id="crow2" markerWidth="20" markerHeight="20" refX="18" refY="10" orient="auto">
      <path d="M0,2 L18,10 L0,18" fill="none" stroke="#9ca3af" stroke-width="1.4"/>
    </marker>
  </defs>

  <line x1="140" y1="150" x2="140" y2="192" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>
  <line x1="140" y1="192" x2="140" y2="220" stroke="#e5e7eb" stroke-width="1.6" marker-end="url(#crow2)"/>

  <polyline points="140,320 140,365 350,365 350,420" fill="none" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>
  <line x1="350" y1="365" x2="350" y2="420" stroke="#e5e7eb" stroke-width="1.6" marker-end="url(#crow2)"/>

  <line x1="480" y1="150" x2="480" y2="300" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>
  <line x1="480" y1="300" x2="480" y2="420" stroke="#e5e7eb" stroke-width="1.6" marker-end="url(#crow2)"/>

  <polyline points="580,150 580,300 800,300" fill="none" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>
  <line x1="800" y1="300" x2="800" y2="420" stroke="#e5e7eb" stroke-width="1.6" marker-end="url(#crow2)"/>

  <polyline points="830,130 830,365 610,365" fill="none" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="5 4"/>
  <line x1="610" y1="365" x2="610" y2="420" stroke="#e5e7eb" stroke-width="1.6" marker-end="url(#crow2)"/>

  <line x1="132" y1="160" x2="148" y2="160" stroke="#9ca3af" stroke-width="1.6"/>
  <line x1="132" y1="365" x2="148" y2="365" stroke="#9ca3af" stroke-width="1.6"/>
  <line x1="472" y1="160" x2="488" y2="160" stroke="#9ca3af" stroke-width="1.6"/>
  <line x1="572" y1="160" x2="588" y2="160" stroke="#9ca3af" stroke-width="1.6"/>
  <line x1="822" y1="140" x2="838" y2="140" stroke="#9ca3af" stroke-width="1.6"/>

  <g>
    <rect x="40" y="40" width="200" height="110" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.18)" stroke-width="1.4"/>
    <rect x="40" y="40" width="200" height="34" rx="4" fill="rgba(96,165,250,0.14)"/>
    <text x="140" y="55" text-anchor="middle" font-size="12.5" font-weight="700" fill="#60a5fa">dim_ship_type</text>
    <text x="140" y="68" text-anchor="middle" font-size="10" fill="#7d8ba3">선종</text>
    <text x="52" y="90" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">ship_type_id · 선종ID</text>
    <text x="52" y="106" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">name · 선종명</text>
    <text x="52" y="122" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">complexity_multiplier · 난이도계수</text>
    <text x="52" y="138" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">contract_value_krw · 계약금액</text>
  </g>

  <g>
    <rect x="400" y="40" width="220" height="110" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.18)" stroke-width="1.4"/>
    <rect x="400" y="40" width="220" height="34" rx="4" fill="rgba(96,165,250,0.14)"/>
    <text x="510" y="55" text-anchor="middle" font-size="12.5" font-weight="700" fill="#60a5fa">dim_department</text>
    <text x="510" y="68" text-anchor="middle" font-size="10" fill="#7d8ba3">담당 부서</text>
    <text x="412" y="90" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">department_id · 부서ID</text>
    <text x="412" y="106" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">name · 부서명</text>
    <text x="412" y="122" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">hourly_cost_krw · 시간당인건비</text>
  </g>

  <g>
    <rect x="720" y="40" width="200" height="90" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.18)" stroke-width="1.4"/>
    <rect x="720" y="40" width="200" height="34" rx="4" fill="rgba(96,165,250,0.14)"/>
    <text x="820" y="55" text-anchor="middle" font-size="12.5" font-weight="700" fill="#60a5fa">dim_process_stage</text>
    <text x="820" y="68" text-anchor="middle" font-size="10" fill="#7d8ba3">공정 단계</text>
    <text x="732" y="90" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">stage_id · 공정ID</text>
    <text x="732" y="106" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">name · 공정명</text>
  </g>

  <g>
    <rect x="40" y="220" width="200" height="100" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.18)" stroke-width="1.4"/>
    <rect x="40" y="220" width="200" height="34" rx="4" fill="rgba(96,165,250,0.14)"/>
    <text x="140" y="235" text-anchor="middle" font-size="12.5" font-weight="700" fill="#60a5fa">dim_vessel</text>
    <text x="140" y="248" text-anchor="middle" font-size="10" fill="#7d8ba3">건조 선박</text>
    <text x="52" y="270" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">vessel_id · 선박ID</text>
    <text x="52" y="286" font-size="10.5" font-family="ui-monospace,monospace" fill="#e0a355">ship_type_id (FK) · 선종ID</text>
    <text x="52" y="302" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">vessel_code · 선박코드</text>
  </g>

  <g>
    <rect x="260" y="420" width="360" height="230" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.24)" stroke-width="1.6"/>
    <rect x="260" y="420" width="360" height="36" rx="4" fill="rgba(96,165,250,0.18)"/>
    <text x="440" y="436" text-anchor="middle" font-size="13" font-weight="700" fill="#60a5fa">fact_production_block</text>
    <text x="440" y="450" text-anchor="middle" font-size="10.5" fill="#7d8ba3">생산 블록 실적</text>
    <text x="272" y="472" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">block_id · 블록ID</text>
    <text x="272" y="488" font-size="10.5" font-family="ui-monospace,monospace" fill="#e0a355">vessel_id (FK) · 선박ID</text>
    <text x="272" y="504" font-size="10.5" font-family="ui-monospace,monospace" fill="#e0a355">stage_id (FK) · 공정ID</text>
    <text x="272" y="520" font-size="10.5" font-family="ui-monospace,monospace" fill="#e0a355">department_id (FK) · 부서ID</text>
    <text x="272" y="536" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">block_name · 블록명 / priority · 우선순위</text>
    <text x="272" y="552" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">triangle_count · 삼각형수 / file_size_mb · 파일크기</text>
    <text x="272" y="568" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">planned_days · 계획일수 / actual_days · 실제일수</text>
    <text x="272" y="584" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">delay_days · 지연일수 / qa_defect_count · QA결함수</text>
    <text x="272" y="600" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">qa_status · QA상태 / created_at · 생성일시</text>
  </g>

  <g>
    <rect x="700" y="420" width="240" height="180" rx="4" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.24)" stroke-width="1.6"/>
    <rect x="700" y="420" width="240" height="36" rx="4" fill="rgba(96,165,250,0.18)"/>
    <text x="820" y="436" text-anchor="middle" font-size="13" font-weight="700" fill="#60a5fa">fact_review_session</text>
    <text x="820" y="450" text-anchor="middle" font-size="10.5" fill="#7d8ba3">경량뷰 검토 세션</text>
    <text x="712" y="472" font-size="10.5" font-family="ui-monospace,monospace" fill="#93c5fd">session_id · 세션ID</text>
    <text x="712" y="488" font-size="10.5" font-family="ui-monospace,monospace" fill="#e0a355">department_id (FK) · 부서ID</text>
    <text x="712" y="504" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">month · 월 / review_type · 검토유형</text>
    <text x="712" y="520" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">triangle_count · 삼각형수</text>
    <text x="712" y="536" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">traditional_load_min · 기존로딩(분)</text>
    <text x="712" y="552" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">lightweight_load_sec · 경량로딩(초)</text>
    <text x="712" y="568" font-size="10.5" font-family="ui-monospace,monospace" fill="#9ca3af">cost_saved_krw · 절감비용</text>
  </g>
</svg>
</div>
"""


DEV_COST_KRW = 15_000_000  # 1인 개발 약 3개월 파트타임 투입 공수 추정치

CUSTOM_CSS = """
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Pretendard", "Malgun Gothic", sans-serif;
    word-break: keep-all;
    overflow-wrap: break-word;
}

.block-container { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1280px; }

/* 히어로 */
.eyebrow {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase;
    color: #60a5fa; margin-bottom: 12px;
}
.eyebrow::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: #3b82f6; box-shadow: 0 0 8px 2px rgba(59,130,246,0.65); }

.hero-title {
    font-size: 2.05rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1.28;
    background: linear-gradient(180deg, #ffffff 0%, #9aa5ba 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    margin-bottom: 10px;
}
.hero-sub { color: #8b8b93; font-size: 0.93rem; line-height: 1.65; max-width: 760px; margin-bottom: 1.6rem; }

/* 섹션 헤더 (숫자 배지 + 타이틀) */
.sec-head { display: flex; align-items: center; gap: 13px; margin: 1.4rem 0 1.1rem 0; }
.sec-num {
    display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 9px;
    background: rgba(59,130,246,0.10); border: 1px solid rgba(59,130,246,0.28); color: #60a5fa;
    font-weight: 700; font-size: 0.86rem; flex-shrink: 0;
}
.sec-title { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.015em; color: #f4f4f5; }
.sec-sub { font-size: 0.8rem; color: #8b8b93; margin-top: 1px; }
.card-title { font-size: 1.02rem; font-weight: 700; color: #f4f4f5; letter-spacing: -0.01em; margin-bottom: 2px; }

/* 글래스 카드 (st.container(border=True)) */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(255,255,255,0.018);
    box-shadow: 0 16px 40px -20px rgba(0,0,0,0.7);
}

/* 메트릭 - 슬라이더 조작 등으로 리렌더될 때마다 살짝 pop + glow, "값이 방금 바뀌었다"는 걸 시각적으로 알려줌 */
@keyframes metricPop {
    0% { transform: scale(0.94); opacity: 0.35; }
    55% { transform: scale(1.025); }
    100% { transform: scale(1); opacity: 1; }
}
@keyframes metricGlow {
    0% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }
    30% { box-shadow: 0 0 0 5px rgba(59,130,246,0.16); }
    100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }
}
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.022);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 0.85rem 1.05rem 0.65rem 1.05rem;
    animation: metricGlow 0.8s ease-out;
}
[data-testid="stMetricLabel"] { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: #8b8b93 !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 700; color: #f4f4f5; animation: metricPop 0.5s cubic-bezier(.2,.8,.3,1); }

/* 히어로 메트릭 - 카드당 가장 중요한 숫자 하나만 훨씬 크게, 나머지는 보조 정보로 */
.hero-metric-wrap {
    display: flex; align-items: baseline; gap: 14px; margin: 2px 0 18px 0;
    padding: 20px 24px; border-radius: 14px;
    background: linear-gradient(135deg, rgba(59,130,246,0.13), rgba(59,130,246,0.02));
    border: 1px solid rgba(59,130,246,0.28);
    animation: metricGlow 0.9s ease-out;
}
.hero-metric-label { font-size: 0.76rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: #8b8b93; }
.hero-metric-value {
    font-size: clamp(2rem, 4vw, 2.7rem); font-weight: 800; letter-spacing: -0.02em; line-height: 1.15;
    background: linear-gradient(135deg, #60a5fa, #a5d8ff 65%, #e0f2fe);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    animation: metricPop 0.55s cubic-bezier(.2,.8,.3,1);
    font-variant-numeric: tabular-nums;
}
.hero-metric-sub { font-size: 0.8rem; color: #8b8b93; margin-top: 4px; }

/* 탭 */
[data-testid="stTabs"] button[role="tab"] { font-weight: 600; font-size: 0.87rem; color: #8b8b93; }
[data-testid="stTabs"] button[aria-selected="true"] p { color: #f4f4f5 !important; }
[data-baseweb="tab-highlight"] { background-color: #3b82f6 !important; height: 2px !important; }

/* 코드 블록 */
div[data-testid="stCodeBlock"] pre { border-radius: 10px !important; font-size: 0.8rem !important; border: 1px solid rgba(255,255,255,0.06); }

/* 버튼 */
.stButton > button, .stFormSubmitButton > button {
    border-radius: 9px !important; font-weight: 600 !important; border: 1px solid rgba(255,255,255,0.10) !important;
}

h2, h3, h4 { letter-spacing: -0.012em; }

/* 배경 은은한 앰비언트 글로우 - 전체적으로 너무 밋밋해 보이는 것 방지 */
[data-testid="stAppViewContainer"] > .main {
    background-image: radial-gradient(circle at 15% 0%, rgba(59,130,246,0.07) 0%, transparent 45%);
    background-attachment: fixed;
}

/* 사이드바 - 삼성중공업 톤앤매너에 맞는 하늘색 강조색을 그대로 살린다 (primaryColor, config.toml 참고) */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.014);
    border-right: 1px solid rgba(255,255,255,0.06);
}

/* 슬라이더 썸 포커스링만 강조색과 어울리게 살짝 다듬음 */
[data-testid="stSlider"] [role="slider"] { box-shadow: 0 0 0 4px rgba(59,130,246,0.18) !important; }

/* 글래스 카드 호버 시 살짝 떠오르는 느낌 */
[data-testid="stVerticalBlockBorderWrapper"] { transition: border-color 0.25s ease, transform 0.25s ease; }
[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: rgba(59,130,246,0.22) !important; }
</style>
"""


def section(num, title, subtitle=None):
    """숫자 배지 + 타이틀의 정갈한 섹션 헤더 (이모지 대신 사용)"""
    sub_html = f'<div class="sec-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="sec-head"><span class="sec-num">{num}</span>'
        f'<div><div class="sec-title">{title}</div>{sub_html}</div></div>',
        unsafe_allow_html=True,
    )


def hero_metric(label, value, sub=None):
    """카드 안에서 가장 강조하고 싶은 숫자 하나를 큼직하게 - 리렌더될 때마다 pop 애니메이션 재생"""
    sub_html = f'<div class="hero-metric-sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="hero-metric-wrap"><div>'
        f'<div class="hero-metric-label">{label}</div>'
        f'<div class="hero-metric-value">{value}</div>'
        f"{sub_html}</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 2. 데이터 준비 - MariaDB 정규화 스키마(dim_*/fact_*)를 JOIN하는 뷰에서 조회
# ---------------------------------------------------------------------------
# 이 두 상수는 실제 실행되는 쿼리가 아니라 2번 탭에서 st.code로 JOIN 과정을 보여주기 위한 문서용 텍스트다.
# 실제 조회는 schema.sql에 정의된 v_production_records/v_review_sessions 뷰(동일한 JOIN을 DB에 한 번만
# 정의해둔 것)를 그대로 SELECT해서, 이 JOIN 로직이 production_data.py와 두 번 중복되지 않게 한다.
PRODUCTION_JOIN_SQL = """
SELECT
    b.block_id, st.name AS ship_type, st.contract_value_krw, v.vessel_code AS vessel_id, b.block_name,
    ps.name AS process_stage, d.name AS department, b.priority, b.triangle_count,
    b.file_size_mb, b.lod_level, b.planned_days, b.actual_days, b.delay_days,
    b.qa_defect_count, b.qa_status, b.created_at
FROM fact_production_block b
JOIN dim_vessel v        ON v.vessel_id = b.vessel_id
JOIN dim_ship_type st     ON st.ship_type_id = v.ship_type_id
JOIN dim_process_stage ps ON ps.stage_id = b.stage_id
JOIN dim_department d     ON d.department_id = b.department_id
""".strip()

REVIEW_SESSION_JOIN_SQL = """
SELECT s.session_id, d.name AS department, s.month, s.review_type, s.triangle_count,
       s.traditional_load_min, s.lightweight_load_sec, d.hourly_cost_krw, s.cost_saved_krw
FROM fact_review_session s
JOIN dim_department d ON d.department_id = s.department_id
""".strip()


@st.cache_data
def load_data():
    with engine.connect() as conn:
        return pd.read_sql(sa.text("SELECT * FROM v_production_records;"), conn)


@st.cache_data
def load_roi():
    """3D 뷰어 경량화 변환(glTF+LOD)이 실제로 절감하는 부서별 리뷰 로딩 시간/비용 - 6개월 온보딩 램프업 시계열"""
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sa.text(
                "SELECT session_id AS id, department, month, review_type, triangle_count, "
                "traditional_load_min, lightweight_load_sec, cost_saved_krw FROM v_review_sessions;"
            ), conn)
    except sa.exc.SQLAlchemyError:
        df = pd.DataFrame()
    return df


# ---------------------------------------------------------------------------
# 사이드바 - 필터 + 새로고침 (교안 20p 매출 대시보드 패턴)
# ---------------------------------------------------------------------------
raw_df = load_data()
roi_df = load_roi()

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div style="font-size:1.05rem;font-weight:700;letter-spacing:-0.01em;margin-bottom:0.6rem;">필터</div>', unsafe_allow_html=True)
    ship_types = st.multiselect("선종", sorted(raw_df["ship_type"].unique()), default=sorted(raw_df["ship_type"].unique()))
    departments = st.multiselect("부서", sorted(raw_df["department"].unique()), default=sorted(raw_df["department"].unique()))
    stages = st.multiselect("공정 단계", sorted(raw_df["process_stage"].unique()), default=sorted(raw_df["process_stage"].unique()))
    period = st.select_slider("기간", ["최근 30일", "최근 90일", "최근 180일", "전체"], value="전체")

    st.divider()
    st.subheader("전처리 옵션")
    missing_method = st.radio(
        "결측치 처리 방식",
        ["0으로 채우기 (fillna)", "평균으로 채우기", "결측 행 제거 (dropna)"],
        index=0,
    )
    remove_outliers = st.checkbox("삼각형 수 이상치 제거 (IQR)", value=False)

    st.divider()
    if st.button("데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown('<div class="eyebrow">ShipHub · Production Intelligence</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-title">경량 3D 뷰어 파이프라인이 만드는 데이터, 그걸로 하는 예측</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-sub">ShipHub 3D 뷰어가 IFC/DXF 원본을 glTF+LOD로 압축할 때 남기는 형상 복잡도 메타데이터'
    '(삼각형 수·파일 크기)가 아래 머신러닝 모델의 입력이 되고, 그 예측 결과가 실제 부서 업무 시간·비용 절감으로'
    ' 이어집니다. <b>3D 시각화와 이 대시보드는 하나의 데이터 흐름</b>입니다.</div>',
    unsafe_allow_html=True,
)

if len(roi_df):
    latest_month = roi_df["month"].max()
    latest = roi_df[roi_df["month"] == latest_month]
    by_dept = (
        latest.groupby("department")
        .agg(
            sessions=("id", "count"),
            cost_saved=("cost_saved_krw", "sum"),
            avg_trad_min=("traditional_load_min", "mean"),
            avg_lite_sec=("lightweight_load_sec", "mean"),
        )
        .reset_index()
    )
    monthly_saving = by_dept["cost_saved"].sum()
    avg_cost_per_session = monthly_saving / by_dept["sessions"].sum() if by_dept["sessions"].sum() else 0

    with st.container(border=True):
        st.markdown('<div class="card-title">전사 확산 시 예상 효과 (추정)</div>', unsafe_allow_html=True)
        st.caption(
            f"단가는 파일럿 {by_dept.shape[0]}개 부서 · {int(by_dept['sessions'].sum())}건/월 실측 데이터에서 검증된 "
            f"세션당 ₩{avg_cost_per_session:,.0f} 절감을 그대로 사용합니다. 인력 규모 기본값은 삼성중공업 실제 임직원 수 "
            "9,640명(2023 사업보고서, DART 전자공시) 중 도면/형상 검토 업무 비중을 40%로 가정한 값입니다. "
            "슬라이더를 움직이면 전사 확산 규모에 따라 즉시 재계산됩니다."
        )

        s1, s2, s3, s4 = st.columns(4)
        eng_headcount = s1.slider("엔지니어링·생산관리 인력", 500, 9640, 3800, step=100)
        reviews_per_day = s2.slider("1인당 일평균 검토 횟수", 1, 5, 2)
        working_days = s3.slider("월 근무일수", 18, 26, 22)
        cad_license_price = s4.slider("중량 CAD 라이선스 5년 TCO(원/카피)", 20_000_000, 150_000_000, 80_000_000, step=5_000_000)

        enterprise_sessions = eng_headcount * reviews_per_day * working_days
        enterprise_monthly_saving = enterprise_sessions * avg_cost_per_session
        enterprise_annual_saving = enterprise_monthly_saving * 12

        replace_ratio = st.slider("검토 전용 인력 중 '풀 CAD 라이선스 → 경량 뷰어' 대체 비율", 0, 100, 40, format="%d%%")
        license_avoided = eng_headcount * (replace_ratio / 100) * cad_license_price

        hero_metric(
            "연간 절감 + 라이선스 회피 합산",
            f"₩{enterprise_annual_saving + license_avoided:,.0f}",
            f"검토 세션 {enterprise_sessions:,.0f}건/월 기준",
        )
        e1, e2 = st.columns(2)
        e1.metric("전사 연간 검토시간 절감액(추정)", f"₩{enterprise_annual_saving:,.0f}")
        e2.metric("회피된 CAD 라이선스 비용(추정)", f"₩{license_avoided:,.0f}")

        st.caption(
            "참고: Siemens NX 롤 기반 라이선스는 기본형 시트당 약 $9,000 + 연 유지보수 20%로 공개되어 있으나(공급사 발표 기준), "
            "조선업 실무에서 쓰는 CAD+CAM+CAE 통합 엔터프라이즈 구성은 비공개 협상가로 이보다 수 배 높은 것이 일반적입니다. "
            "위 슬라이더의 8,000만원은 '5년 보유비용(TCO)' 관점의 추정 범위이며, 설계 변경 없이 형상만 확인하면 되는 "
            "검토 전용 인력까지 전부 풀 라이선스를 지급할 필요가 없어 경량 glTF+LOD 뷰어로 대체하는 흐름이 실제 업계 트렌드입니다."
        )

    if "contract_value_krw" in raw_df.columns:
        DELAY_PENALTY_RATE = 0.0013  # 0.13%/일 - 지방자치단체를 당사자로 하는 계약에 관한 법률 시행규칙상 지체상금 표준요율
        vessel_delay = (
            raw_df.groupby(["vessel_id", "ship_type", "contract_value_krw"])["delay_days"]
            .mean()
            .reset_index()
        )
        vessel_delay["exposure_krw"] = (
            vessel_delay["contract_value_krw"] * DELAY_PENALTY_RATE * vessel_delay["delay_days"].clip(lower=0)
        )
        total_exposure = vessel_delay["exposure_krw"].sum()
        total_contract_value = vessel_delay["contract_value_krw"].sum()

        with st.container(border=True):
            st.markdown('<div class="card-title">조기 지연 예측의 계약적 가치 — 지체상금 회피</div>', unsafe_allow_html=True)
            st.caption(
                f"현재 {vessel_delay.shape[0]}척(선종별 계약금액은 2026년 실제 SHI 수주 공시·시장가 기준, "
                "1번 탭 데이터 정의 참고)의 평균 블록 지연일수를 지체상금 법정 표준요율(계약금액 × 0.13%/일)로 "
                "환산한 노출액입니다. 이 대시보드의 지연 예측 모델(5번 탭 회귀 모델)로 조기에 잡아낼 수 있는 지연 "
                "비율을 슬라이더로 조절해보세요."
            )
            prevent_ratio = st.slider("조기 예측으로 방지 가능한 지연 비율", 0, 100, 30, format="%d%%")
            prevented_value = total_exposure * (prevent_ratio / 100)

            hero_metric(
                f"조기예측 방지 가치 ({prevent_ratio}%)",
                f"₩{prevented_value:,.0f}",
                f"전체 노출액 ₩{total_exposure:,.0f} 중",
            )
            p1, p2 = st.columns(2)
            p1.metric("전체 지체상금 노출액", f"₩{total_exposure:,.0f}")
            p2.metric("계약금액 대비 노출 비율", f"{(total_exposure / total_contract_value * 100):.3f}%" if total_contract_value else "-")

    with st.expander("파일럿 실측 데이터 상세 보기"):
        annual_saving = monthly_saving * 12
        roi_pct = (annual_saving - DEV_COST_KRW) / DEV_COST_KRW * 100
        payback_months = DEV_COST_KRW / monthly_saving if monthly_saving else None

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("파일럿 연간 절감액(실측)", f"₩{annual_saving:,.0f}")
        k2.metric("파일럿 ROI", f"{roi_pct:.1f}%")
        k3.metric("투자회수기간", f"{payback_months:.1f}개월" if payback_months else "-")
        k4.metric("평균 리뷰 로딩시간", f"{by_dept['avg_trad_min'].mean():.1f}분 → {by_dept['avg_lite_sec'].mean():.1f}초")

        c1, c2 = st.columns([1.3, 1])
        with c1:
            st.caption(f"{latest_month} 기준 · 월별 절감액 추이 (부서 순차 온보딩 → 정상 가동 램프업)")
            trend = roi_df.groupby("month")["cost_saved_krw"].sum()
            st.line_chart(trend)
        with c2:
            st.caption("부서별 이번 달 절감액")
            st.bar_chart(by_dept.set_index("department")["cost_saved"])

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    ["1. 데이터 정의", "2. 데이터 준비", "3. 데이터 전처리", "4. 데이터 분석(EDA)", "5. 학습·예측·평가", "6. 성능 향상", "7. 실시간 예측", "8. 기술 스택"]
)

# ---------------------------------------------------------------------------
# 1. 데이터 정의
# ---------------------------------------------------------------------------
with tab1:
    section("01", "데이터 정의", "수집 방법과 컬럼 사전")
    st.markdown(f"""
**수집 방법**: 조선 BIM/CAD 경량화 변환 서비스(`converter.py`)가 IFC/DXF 파일을 glTF로 변환할 때마다
형상 복잡도(삼각형 수, 파일 크기)를 MariaDB에 기록한다. 이 실제 변환 파이프라인의 출력 구조를 그대로 정규화된
스키마로 삼아, 동일한 통계적 특성(형상이 복잡할수록 공정 지연·QA 결함이 늘어나는 상관관계)을 갖는 가상 생산 레코드를
`setup_mariadb.py`로 생성했다 (`np.random.default_rng` 시드 고정으로 재현 가능).

현재 조선소 동시 수주잔량을 흉내내어 **선종 {raw_df['ship_type'].nunique()}종 · 동시 건조 {raw_df['vessel_id'].nunique()}척 ·
블록 {len(raw_df):,}건** 규모로 구성했다. 선종 구성과 척수는 2026년 삼성중공업 실제 상선 수주 공시
(LNG운반선 14척·원유운반선 12척·가스운반선 4척·컨테이너선 2척·에탄운반선 2척, 뉴스핌·edaily 등 보도)와
평균 건조기간(약 2~3년)을 반영해 "현재 동시 건조 중" 규모로 확장 추정했고, 선종별 계약금액도 실제 공시
(LNG운반선 1척 3,855억원, 2026-06)와 최근 시장가를 근거로 설정했다 — 아래 `contract_value_krw`는
3번 탭의 지체상금(계약 지연배상금, 법정 표준요율 0.13%/일) 회피 가치 계산에 쓰인다.
""")
    col_doc = pd.DataFrame([
        ("ship_type", "object", "선종 (LNG운반선/VLCC/가스운반선/컨테이너선/에탄운반선/해양플랜트)"),
        ("contract_value_krw", "int64", "선종별 대표 계약금액(원) - 실제 SHI 수주 공시/시장가 기준"),
        ("vessel_id", "object", "동시 건조 중인 개별 선박(척) 식별자"),
        ("block_name", "object", "블록 식별자 (척ID + B/E/S + 번호)"),
        ("process_stage", "object", "공정 단계 (절단/조립/탑재/의장/도장/시운전)"),
        ("department", "object", "담당 부서"),
        ("priority", "object", "우선순위 (High/Medium/Low)"),
        ("triangle_count", "int64", "변환된 형상의 삼각형 수 (복잡도 지표)"),
        ("file_size_mb", "float64", "변환 파일 크기 - 일부 결측(로그 유실 가정)"),
        ("lod_level", "int64", "LOD 레벨 (1~3)"),
        ("planned_days", "int64", "계획 공정 일수"),
        ("actual_days", "int64", "실제 공정 일수"),
        ("delay_days", "float64", "지연일수 (실제-계획), 회귀 예측 타깃"),
        ("qa_defect_count", "float64", "QA 결함 수 - 일부 결측(미검수 가정)"),
        ("qa_status", "object", "QA 합격/불합격, 분류 예측 타깃"),
        ("created_at", "object", "생성 시각 (최근 180일 분산)"),
    ], columns=["컬럼", "타입", "설명"])
    st.dataframe(col_doc, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# 2. 데이터 준비
# ---------------------------------------------------------------------------
with tab2:
    section("02", "데이터 준비", "정규화 스키마 · JOIN 쿼리 · df.head() / shape / describe() / info()")

    with st.container(border=True):
        st.markdown('<div class="card-title">스키마 설계 (개념적 → 논리적 → 물리적) — ERD (Barker 표기법)</div>', unsafe_allow_html=True)
        st.caption("실선+까마귀발=필수·다수, 점선=선택 · fact_* 테이블은 FK가 전부 NOT NULL(필수), dim_* 쪽은 자식 0개 가능(선택)")
        st.markdown(ERD_SVG_BARKER, unsafe_allow_html=True)

    st.markdown("**실제 JOIN 쿼리** (4개 테이블을 조인해서 분석용 평탄화 테이블을 만든다)")
    st.code(f"""
import sqlalchemy as sa
import pandas as pd

engine = sa.create_engine("mysql+pymysql://root:***@localhost:3306/shiphub")

query = \"\"\"
{PRODUCTION_JOIN_SQL}
\"\"\"
df = pd.read_sql(sa.text(query), engine.connect())
""", language="python")
    st.caption("실제 운영 코드에서는 이 JOIN을 매번 다시 적지 않고, `schema.sql`에 뷰(`v_production_records`)로 한 번만 정의해두고 `SELECT * FROM v_production_records`로 재사용한다.")

    c1, c2 = st.columns([1, 1])
    with c1:
        st.write("**df.head()**")
        st.dataframe(raw_df.head(), use_container_width=True)
    with c2:
        st.write("**df.shape**")
        st.write(raw_df.shape)
        st.write("**df.describe()**")
        st.dataframe(raw_df[NUMERIC_COLS + ["delay_days"]].describe().round(2), use_container_width=True)

    st.write("**df.info() 대응 - dtype / 결측치 현황**")
    info_df = pd.DataFrame({
        "dtype": raw_df.dtypes.astype(str),
        "non_null": raw_df.notna().sum(),
        "null_count": raw_df.isnull().sum(),
    })
    st.dataframe(info_df, use_container_width=True)

# ---------------------------------------------------------------------------
# 3. 데이터 전처리 (핵심 섹션)
# ---------------------------------------------------------------------------
with tab3:
    section("03", "데이터 전처리", "결측치 · datetime · 파생변수 · 인코딩 · 스케일링 · 누수 방지")
    df = raw_df.copy()

    st.subheader("3-1. 결측치 확인 및 처리")
    st.code("df.isnull().sum()", language="python")
    null_counts = df.isnull().sum()
    null_counts = null_counts[null_counts > 0]
    if len(null_counts):
        st.bar_chart(null_counts)
        null_pct = (null_counts / len(df) * 100)
        st.caption(
            "막대 높이 = 결측치 개수. "
            + " · ".join(f"`{c}` 전체의 {p:.1f}%" for c, p in null_pct.items())
            + f" — 두 컬럼 다 10% 미만이라 행을 통째로 버리기(dropna)보다 채워 넣는(fillna) 쪽이 데이터 손실이 적다."
        )
    else:
        st.write("결측치 없음")

    before_rows = len(df)
    if missing_method == "0으로 채우기 (fillna)":
        st.code("df['qa_defect_count'] = df['qa_defect_count'].fillna(0)\ndf['file_size_mb'] = df['file_size_mb'].fillna(0)", language="python")
        df["qa_defect_count"] = df["qa_defect_count"].fillna(0)
        df["file_size_mb"] = df["file_size_mb"].fillna(0)
    elif missing_method == "평균으로 채우기":
        st.code("df['qa_defect_count'] = df['qa_defect_count'].fillna(df['qa_defect_count'].mean())\ndf['file_size_mb'] = df['file_size_mb'].fillna(df['file_size_mb'].mean())", language="python")
        df["qa_defect_count"] = df["qa_defect_count"].fillna(df["qa_defect_count"].mean())
        df["file_size_mb"] = df["file_size_mb"].fillna(df["file_size_mb"].mean())
    else:
        st.code("df = df.dropna(subset=['qa_defect_count', 'file_size_mb'])", language="python")
        df = df.dropna(subset=["qa_defect_count", "file_size_mb"])

    st.write(f"처리 전 {before_rows}행 → 처리 후 **{len(df)}행** (결측치 {missing_method} 적용)")

    st.subheader("3-2. datetime 변환 및 파생 변수")
    st.code("""
df['created_at'] = pd.to_datetime(df['created_at'])
df['month'] = df['created_at'].dt.month
df['weekday'] = df['created_at'].dt.day_name()
""", language="python")
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["month"] = df["created_at"].dt.month
    df["weekday"] = df["created_at"].dt.day_name()
    df["quarter"] = df["created_at"].dt.quarter

    st.subheader("3-3. 파생 변수 생성 (행 단위 apply)")
    st.code("""
def risk_group(row):
    if row['priority'] == 'High' or row['delay_days'] > 5:
        return '고위험'
    elif row['delay_days'] > 2:
        return '주의'
    else:
        return '양호'

df['지연위험군'] = df.apply(risk_group, axis=1)
""", language="python")

    def risk_group(row):
        if row["priority"] == "High" or row["delay_days"] > 5:
            return "고위험"
        elif row["delay_days"] > 2:
            return "주의"
        else:
            return "양호"

    df["지연위험군"] = df.apply(risk_group, axis=1)
    st.dataframe(df["지연위험군"].value_counts().rename("건수"), use_container_width=True)

    if remove_outliers:
        st.subheader("3-4. 이상치 제거 (IQR)")
        q1, q3 = df["triangle_count"].quantile(0.25), df["triangle_count"].quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        st.code(f"Q1={q1:.0f}, Q3={q3:.0f}, IQR={iqr:.0f} → 허용범위 [{lo:.0f}, {hi:.0f}]", language="text")
        before = len(df)
        df = df[(df["triangle_count"] >= lo) & (df["triangle_count"] <= hi)]
        st.write(f"이상치 제거: {before}행 → {len(df)}행")

    st.subheader("3-5. 범주형 인코딩 (OneHotEncoder)")
    st.code("""
from sklearn.preprocessing import OneHotEncoder

oh_enc = OneHotEncoder(sparse_output=False)
oh_res = oh_enc.fit_transform(df[['department', 'process_stage', 'priority']])
oh_df = pd.DataFrame(oh_res, columns=oh_enc.get_feature_names_out())
""", language="python")
    oh_enc = OneHotEncoder(sparse_output=False)
    oh_res = oh_enc.fit_transform(df[CATEGORICAL_COLS])
    oh_df = pd.DataFrame(oh_res, columns=oh_enc.get_feature_names_out(), index=df.index)
    st.dataframe(oh_df.head(), use_container_width=True)

    cat_cardinalities = {c: df[c].nunique() for c in CATEGORICAL_COLS}
    st.info(
        f"**`fit_transform`이 실제로 한 일**: `fit()` 단계에서 `{CATEGORICAL_COLS}` 4개 컬럼 각각에 어떤 값들이 있는지 스캔해서 "
        f"카테고리 목록(사전)을 학습한다 — "
        + ", ".join(f"`{c}` {n}종" for c, n in cat_cardinalities.items())
        + f" (합계 {sum(cat_cardinalities.values())}종). `transform()` 단계에서는 그 사전을 기준으로 "
        f"각 행을 '해당하면 1, 아니면 0'인 이진 컬럼 **{oh_df.shape[1]}개**로 펼친다 "
        f"({df.shape[1]}개였던 원본 컬럼 수와 무관하게, 범주형 4개 컬럼만 {oh_df.shape[1]}개로 확장됨).\n\n"
        "왜 이렇게 하나: `department='기본설계'`처럼 문자열을 숫자로 그냥 1,2,3... 라벨링하면 모델이 "
        "'부서 3이 부서 1보다 크다'는 식으로 존재하지도 않는 순서/크기 관계를 학습해버린다. "
        "원핫인코딩은 각 카테고리를 독립된 0/1 축으로 분리해서 이 문제를 없앤다 — 대신 컬럼 수가 늘어나는 트레이드오프가 있다."
    )

    st.subheader("3-6. 스케일링 (StandardScaler)")
    st.code("""
from sklearn.preprocessing import StandardScaler

st_scaler = StandardScaler()
num_cols = ['triangle_count', 'file_size_mb', 'lod_level', 'planned_days', 'actual_days', 'qa_defect_count']
scaled = st_scaler.fit_transform(df[num_cols])
""", language="python")
    st_scaler = StandardScaler()
    scaled = st_scaler.fit_transform(df[NUMERIC_COLS])
    scaled_df = pd.DataFrame(scaled, columns=NUMERIC_COLS, index=df.index)
    c1, c2 = st.columns(2)
    with c1:
        st.write("**스케일링 전**")
        st.dataframe(df[NUMERIC_COLS].describe().round(2).loc[["mean", "std"]], use_container_width=True)
    with c2:
        st.write("**스케일링 후** (평균 0 / 표준편차 1)")
        st.dataframe(scaled_df.describe().round(2).loc[["mean", "std"]], use_container_width=True)

    raw_ranges = df[NUMERIC_COLS].agg(["min", "max"])
    biggest_col = raw_ranges.loc["max"].idxmax()
    st.info(
        f"**`fit_transform`이 실제로 한 일**: `fit()` 단계에서 `{NUMERIC_COLS}` 6개 컬럼 각각의 평균(mean)과 표준편차(std)를 계산해서 "
        f"저장한다. `transform()` 단계에서는 그 값으로 모든 셀에 `(x - 평균) / 표준편차` 공식(z-score)을 적용한다.\n\n"
        f"왜 필요한가: 스케일링 전에는 `{biggest_col}`처럼 값이 수만~수십만 단위인 컬럼과 `lod_level`처럼 1~3 단위인 컬럼이 "
        f"같은 표에 섞여 있다. 이 상태로 거리·기울기 기반 모델(Linear/Ridge/Logistic Regression)에 넣으면 "
        f"값의 '크기'가 클 뿐인 컬럼이 실제로는 더 중요하지 않은데도 모델에 더 큰 영향을 미치게 된다. "
        "스케일링 후에는 모든 컬럼이 평균 0 · 표준편차 1로 같은 척도가 되어 이 왜곡이 사라진다 "
        "(단, RandomForest 같은 트리 기반 모델은 값의 크기가 아니라 순서로 분기하기 때문에 스케일링 여부에 영향을 받지 않는다 — "
        "그래도 여기서는 여러 모델을 동일 조건에서 비교하기 위해 전부 스케일링된 입력을 사용한다)."
    )

    st.subheader("3-7. 데이터 누수(Data Leakage) 방지")
    st.markdown("""
`actual_days`는 `delay_days = actual_days - planned_days`로 **타깃과 수학적으로 직결**되어 있고,
`qa_defect_count`는 `qa_status = '불합격' if qa_defect_count > 5 else '합격'` 규칙으로 **타깃을 그대로 결정**한다.
두 컬럼을 모델 입력에 포함시키면 R²/정확도가 비정상적으로 완벽하게 나오는 **데이터 누수**가 발생하므로,
학습 피처에서 명시적으로 제외하고 예측 시점에 실제로 알 수 있는 값만 사용한다.
""")
    st.code("""
model_scaler = StandardScaler()
model_num_cols = ['triangle_count', 'file_size_mb', 'lod_level', 'planned_days']  # actual_days, qa_defect_count 제외
model_scaled = model_scaler.fit_transform(df[model_num_cols])
""", language="python")
    model_scaler = StandardScaler()
    model_scaled = model_scaler.fit_transform(df[MODEL_NUMERIC_COLS])
    model_scaled_df = pd.DataFrame(model_scaled, columns=MODEL_NUMERIC_COLS, index=df.index)

    X_full = pd.concat([model_scaled_df, oh_df], axis=1)
    st.subheader("3-8. 최종 학습용 피처 테이블")
    st.write(f"결측치 처리 → datetime 변환 → 파생변수 → 인코딩 → 누수 컬럼 제외 스케일링을 모두 거친 최종 X shape: **{X_full.shape}**")
    st.dataframe(X_full.head(), use_container_width=True)
    st.caption(
        f"컬럼 구성: 스케일링된 수치형 {len(MODEL_NUMERIC_COLS)}개(`{', '.join(MODEL_NUMERIC_COLS)}`) "
        f"+ 원핫인코딩된 범주형 {oh_df.shape[1]}개 = 총 {X_full.shape[1]}개 피처, {X_full.shape[0]:,}행. "
        "이 표의 각 행이 RandomForest/LinearRegression 등 5번 탭 모델에 그대로 들어가는 X(입력 행렬)다."
    )
    st.caption(
        "**참고(방법론 한계)**: 여기서는 `fit_transform`을 train/test 분할 이전, 전체 데이터에 대해 한 번에 수행한다. "
        "엄밀한 실무 파이프라인이라면 `train_test_split` 이후 훈련셋에만 `fit`하고 테스트셋에는 `transform`만 적용해야 "
        "테스트셋 정보가 스케일러/인코더 학습에 전혀 섞이지 않는다. 이번 프로젝트는 범주가 고정돼 있고 스케일이 크게 "
        "흔들리지 않는 데이터라 실질적 영향은 미미하지만, 데이터 누수를 논할 때 같이 짚어야 하는 지점이라 명시해둔다."
    )

    st.session_state["proc_df"] = df
    st.session_state["X_full"] = X_full
    st.session_state["model_scaler"] = model_scaler
    st.session_state["oh_enc"] = oh_enc

# ---------------------------------------------------------------------------
# 4. 데이터 분석 (EDA)
# ---------------------------------------------------------------------------
with tab4:
    section("04", "데이터 분석", "EDA · 상관관계 · 분포")
    df = st.session_state.get("proc_df", raw_df.copy())

    # 사이드바 필터 적용 (선종/부서/공정/기간)
    fdf = df[df["ship_type"].isin(ship_types) & df["department"].isin(departments) & df["process_stage"].isin(stages)]
    if "created_at" in fdf.columns and period != "전체":
        days = {"최근 30일": 30, "최근 90일": 90, "최근 180일": 180}[period]
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        fdf = fdf[pd.to_datetime(fdf["created_at"]) >= cutoff]

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("레코드 수", f"{len(fdf):,}")
        c2.metric("평균 지연일", f"{fdf['delay_days'].mean():.2f}일")
        c3.metric("QA 합격률", f"{(fdf['qa_status'] == '합격').mean() * 100:.1f}%")
        c4.metric("평균 삼각형 수", f"{fdf['triangle_count'].mean():,.0f}")

    st.subheader("변수별 기술통계")
    st.code("df[num_cols].describe()", language="python")
    st.dataframe(fdf[NUMERIC_COLS + ["delay_days"]].describe().round(2), use_container_width=True)

    st.subheader("변수별 분포 (수치형 - 히스토그램)")
    st.code("for col in num_cols: sns.histplot(df[col], kde=True)", language="python")
    dist_cols = NUMERIC_COLS + ["delay_days"]
    hist_rows = [dist_cols[i:i + 3] for i in range(0, len(dist_cols), 3)]
    for row in hist_rows:
        cols = st.columns(3)
        for col_slot, col_name in zip(cols, row):
            with col_slot:
                fig_h, ax_h = plt.subplots(figsize=(4, 3))
                sns.histplot(fdf[col_name].dropna(), kde=True, ax=ax_h, color="#60a5fa")
                ax_h.set_title(col_name, fontsize=10)
                ax_h.set_xlabel("")
                st.pyplot(fig_h)

    delay_skew = fdf["delay_days"].skew()
    tri_skew = fdf["triangle_count"].skew()
    delay_shape = "오른쪽으로 긴 꼬리(양의 왜도)" if delay_skew > 0.3 else ("왼쪽으로 긴 꼬리(음의 왜도)" if delay_skew < -0.3 else "좌우 대칭에 가까움")
    tri_shape = "오른쪽으로 긴 꼬리" if tri_skew > 0.3 else ("왼쪽으로 긴 꼬리" if tri_skew < -0.3 else "좌우 대칭에 가까움")
    pct_over5 = (fdf["delay_days"] > 5).mean() * 100
    st.info(
        f"**읽는 법**: 막대가 특정 구간에 몰려있으면 대부분의 블록이 그 값대에 있다는 뜻이고, "
        f"꼬리가 한쪽으로 길게 늘어지면(왜도, skewness) 소수의 극단값이 존재한다는 뜻이다.\n\n"
        f"- `delay_days`(지연일수)는 왜도 **{delay_skew:.2f}** → **{delay_shape}**. "
        f"전체 블록의 **{pct_over5:.1f}%**가 5일 넘게 지연되는 '롱테일' 형태로, "
        f"평균만 보면 위험을 과소평가하기 쉽다 (그래서 회귀 예측에서 RMSE/R²를 같이 봐야 함).\n"
        f"- `triangle_count`(삼각형 수, 형상 복잡도)는 왜도 **{tri_skew:.2f}** → **{tri_shape}**. "
        f"이는 대부분 블록이 비슷한 복잡도지만 일부 초대형/초정밀 블록이 평균을 끌어올린다는 뜻으로, "
        f"뒤에 나오는 상관관계·피처중요도 분석에서 `triangle_count`가 왜 핵심 변수인지의 배경이 된다."
    )

    st.subheader("변수별 분포 (범주형 - 빈도)")
    st.code("for col in cat_cols: sns.countplot(x=col, data=df)", language="python")
    cat_cols_row = st.columns(len(CATEGORICAL_COLS))
    for col_slot, col_name in zip(cat_cols_row, CATEGORICAL_COLS):
        with col_slot:
            st.caption(f"**{col_name}**")
            st.bar_chart(fdf[col_name].value_counts())

    balance_lines = []
    for col_name in CATEGORICAL_COLS:
        vc = fdf[col_name].value_counts()
        ratio = vc.max() / vc.min() if vc.min() > 0 else float("inf")
        tag = "균형적" if ratio < 1.5 else ("약간 불균형" if ratio < 3 else "뚜렷하게 불균형")
        balance_lines.append(f"- `{col_name}`: 최다 **{vc.idxmax()}**({vc.max():,}건) vs 최소 **{vc.idxmin()}**({vc.min():,}건), 비율 {ratio:.1f}배 → **{tag}**")
    st.info(
        "**읽는 법**: 막대 높이가 서로 비슷하면 균형 데이터, 한쪽이 압도적으로 크면 불균형 데이터다. "
        "특히 분류 모델(QA 합격/불합격)을 만들 때 클래스 불균형이 심하면 Accuracy가 높아도 소수 클래스를 못 맞출 수 있어 "
        "F1-score를 같이 봐야 한다 (5번 탭에서 실제로 그렇게 처리함).\n\n" + "\n".join(balance_lines)
    )

    st.subheader("상관관계 히트맵")
    st.code("sns.heatmap(df[num_cols].corr(), annot=True, cmap='RdBu_r')", language="python")
    corr = fdf[NUMERIC_COLS + ["delay_days"]].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1, ax=ax)
    st.pyplot(fig)

    delay_corr = corr["delay_days"].drop("delay_days").sort_values(key=abs, ascending=False)
    top_delay_var, top_delay_val = delay_corr.index[0], delay_corr.iloc[0]
    st.info(
        "**읽는 법**: 1에 가까울수록 진한 빨강(강한 양의 상관), -1에 가까울수록 진한 파랑(강한 음의 상관), "
        "0에 가까우면 흰색(관계 없음). 대각선은 항상 1(자기 자신)이라 무시하면 된다.\n\n"
        f"- `delay_days`(지연일수)와 가장 상관이 큰 변수는 **{top_delay_var}**(r={top_delay_val:+.2f})로, "
        + ("절댓값이 0.3을 넘지 않아 **단일 변수만으로는 지연을 설명하기 어렵다** — 이것이 여러 변수를 조합하는 머신러닝 모델을 쓰는 이유다."
           if abs(top_delay_val) < 0.3 else
           f"{'값이 클수록 지연도 커지는' if top_delay_val > 0 else '값이 클수록 오히려 지연이 줄어드는'} 경향이 있다.") + "\n"
        "- `triangle_count`(삼각형 수)와 `file_size_mb`(파일 크기)는 원래 같은 형상 데이터에서 나온 지표라 상관이 높게 나오기 쉬운데, "
        "이 둘을 모델에 같이 넣으면 다중공선성(multicollinearity)으로 회귀계수 해석이 왜곡될 수 있어 "
        "실제 모델에서는 트리 기반(RandomForest) 모델을 우선 비교한다 (트리 모델은 다중공선성에 상대적으로 덜 민감)."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("부서별 평균 지연일")
        dept_delay = fdf.groupby("department")["delay_days"].mean().sort_values(ascending=False)
        st.bar_chart(dept_delay)
        st.caption(f"**{dept_delay.index[0]}**이 평균 {dept_delay.iloc[0]:.2f}일로 가장 지연이 크고, **{dept_delay.index[-1]}**이 {dept_delay.iloc[-1]:.2f}일로 가장 양호하다.")
    with c2:
        st.subheader("선종별 블록 수 · 평균 복잡도")
        ship_tri = fdf.groupby("ship_type")["triangle_count"].mean().sort_values(ascending=False)
        st.bar_chart(ship_tri)
        st.caption(f"**{ship_tri.index[0]}**의 평균 삼각형 수가 가장 많아(약 {ship_tri.iloc[0]:,.0f}개) 형상이 가장 복잡한 선종이다 — 계약금액·난이도계수가 높은 것과 일치하는지 1번 탭과 비교해볼 것.")
    with c3:
        st.subheader("우선순위별 지연일 분포")
        fig2, ax2 = plt.subplots(figsize=(5, 4))
        sns.boxplot(x="priority", y="delay_days", data=fdf, order=["High", "Medium", "Low"], ax=ax2)
        st.pyplot(fig2)
        med_high = fdf[fdf["priority"] == "High"]["delay_days"].median()
        med_low = fdf[fdf["priority"] == "Low"]["delay_days"].median()
        st.caption(
            f"박스는 중간 50%(1~3분위) 구간, 가운데 선은 중앙값. High 우선순위 중앙값 {med_high:.1f}일 vs Low {med_low:.1f}일"
            + (" — 우선순위를 높여도 실제 지연이 크게 줄지 않는다는 뜻일 수 있어 공정 자체 개선이 더 중요할 수 있다." if med_high >= med_low - 0.5 else " — 우선순위 지정이 실제로 지연 완화에 효과가 있는 것으로 보인다.")
        )

    st.subheader("월별 평균 지연일 추이")
    monthly_series = fdf.groupby(pd.to_datetime(fdf["created_at"]).dt.to_period("M").astype(str))["delay_days"].mean()
    st.line_chart(monthly_series)
    if len(monthly_series) >= 2:
        trend = monthly_series.iloc[-1] - monthly_series.iloc[0]
        st.caption(
            f"첫 달 {monthly_series.iloc[0]:.2f}일 → 마지막 달 {monthly_series.iloc[-1]:.2f}일"
            + (f" (**{trend:+.2f}일**, 지연이 늘어나는 추세)" if trend > 0.2 else (f" (**{trend:+.2f}일**, 지연이 줄어드는 추세)" if trend < -0.2 else " — 뚜렷한 추세 없이 안정적."))
        )

    if "contract_value_krw" in fdf.columns:
        st.subheader("선종별 계약금액 · 지체상금 노출액")
        st.caption("계약금액은 1번 탭 출처 참고 · 지체상금 = 계약금액 × 0.13%/일(법정 표준요율) × 평균 지연일수")
        ship_fin = (
            fdf.groupby("ship_type")
            .agg(계약금액=("contract_value_krw", "mean"), 평균지연일=("delay_days", "mean"))
            .reset_index()
        )
        ship_fin["지체상금노출액"] = ship_fin["계약금액"] * 0.0013 * ship_fin["평균지연일"].clip(lower=0)
        cf1, cf2 = st.columns(2)
        with cf1:
            st.caption("선종별 대표 계약금액(원)")
            st.bar_chart(ship_fin.set_index("ship_type")["계약금액"])
        with cf2:
            st.caption("선종별 척당 평균 지체상금 노출액(원)")
            st.bar_chart(ship_fin.set_index("ship_type")["지체상금노출액"])

        top_exposure = ship_fin.sort_values("지체상금노출액", ascending=False).iloc[0]
        st.info(
            f"**시사점**: 왼쪽 그래프는 '얼마짜리 배인가'(계약 규모), 오른쪽은 '지금 속도로 계속 지연되면 위약금이 얼마나 쌓이는가'(리스크 금액)다. "
            f"두 그래프의 순위가 다르다는 게 핵심 — 계약금액이 가장 큰 선종이 꼭 리스크가 가장 큰 선종은 아니다. "
            f"지금 기준으로는 **{top_exposure['ship_type']}**의 지체상금 노출액이 가장 커서(척당 약 {top_exposure['지체상금노출액']:,.0f}원), "
            f"공정 관리 우선순위를 정할 때 '비싼 배'가 아니라 '지연×계약금액이 큰 배'를 먼저 봐야 한다는 근거가 된다."
        )

    with st.expander("원본 필터 데이터 보기"):
        st.dataframe(fdf, use_container_width=True)

# ---------------------------------------------------------------------------
# 5. 머신러닝 학습 / 예측 / 평가
# ---------------------------------------------------------------------------
with tab5:
    section("05", "학습 · 예측 · 평가", "회귀/분류 모델 비교, 피처 중요도")
    df = st.session_state.get("proc_df", raw_df.copy())
    X_full = st.session_state.get("X_full")
    if X_full is None:
        st.warning("먼저 '3. 데이터 전처리' 탭을 열어 전처리를 실행하세요.")
    else:
        y_delay = df["delay_days"]
        y_qa = (df["qa_status"] == "합격").astype(int)

        st.code("""
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)
""", language="python")
        X_train, X_test, y_train, y_test = train_test_split(X_full, y_delay, test_size=0.2, random_state=0)
        Xc_train, Xc_test, yc_train, yc_test = train_test_split(X_full, y_qa, test_size=0.2, random_state=0)

        st.subheader("5-1. 지연일수 회귀 모델 비교")
        st.code("""
models = {
    'LinearRegression': LinearRegression(),
    'Ridge': Ridge(alpha=1.0),
    'RandomForestRegressor': RandomForestRegressor(n_estimators=200, random_state=0, n_jobs=-1),
}
for name, model in models.items():
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    rmse = root_mean_squared_error(y_test, pred)
    r2 = r2_score(y_test, pred)
""", language="python")

        reg_models = {
            "LinearRegression": LinearRegression(),
            "Ridge(alpha=1.0)": Ridge(alpha=1.0),
            "RandomForestRegressor": RandomForestRegressor(n_estimators=200, random_state=0, n_jobs=-1),
        }
        reg_results = []
        fitted_reg = {}
        for name, model in reg_models.items():
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            reg_results.append({"모델": name, "RMSE": round(root_mean_squared_error(y_test, pred), 3), "R²": round(r2_score(y_test, pred), 3)})
            fitted_reg[name] = model
        reg_result_df = pd.DataFrame(reg_results)
        with st.container(border=True):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.dataframe(reg_result_df, hide_index=True, use_container_width=True)
            with c2:
                st.bar_chart(reg_result_df.set_index("모델")["R²"])

            best_reg_name = reg_result_df.loc[reg_result_df["R²"].idxmax(), "모델"]
            best_r2 = reg_result_df["R²"].max()
            worst_r2 = reg_result_df["R²"].min()
            st.success(f"최고 성능 회귀 모델: **{best_reg_name}** (R²={best_r2:.3f})")
            st.info(
                f"**R²와 RMSE가 뭘 의미하나**: R²(결정계수)는 '실제 지연일수 변동 중 모델이 설명해내는 비율'이다. "
                f"R²={best_r2:.2f}는 지연일수 편차의 약 **{best_r2*100:.0f}%**를 모델이 설명한다는 뜻이고, "
                f"나머지 {(1-best_r2)*100:.0f}%는 모델이 못 잡아내는 우연/미측정 요인이다. "
                f"RMSE는 '평균적으로 며칠 정도 틀리는가'를 원래 단위(일)로 보여준다 — "
                f"{best_reg_name}의 RMSE는 예측이 실제 지연일수와 평균 {reg_result_df.loc[reg_result_df['모델']==best_reg_name, 'RMSE'].values[0]:.2f}일 정도 차이난다는 뜻.\n\n"
                + (f"트리 기반인 **RandomForestRegressor**가 선형모델(LinearRegression/Ridge)보다 R²가 "
                   f"{best_r2 - reg_result_df.loc[reg_result_df['모델'].str.contains('Linear'), 'R²'].values[0]:+.3f} 높다는 건, "
                   f"지연일수와 입력 변수들의 관계가 **직선(선형)이 아니라 조건부·비선형적**이라는 뜻이다 "
                   f"(예: '삼각형 수가 많으면서 동시에 우선순위가 낮을 때만' 지연이 확 커지는 식의 상호작용은 선형모델이 못 잡는다)."
                   if "RandomForest" in best_reg_name else
                   f"선형모델(**{best_reg_name}**)이 RandomForest보다 낫거나 비슷하다는 건, 데이터 안 관계가 비교적 단순·선형적이라 "
                   f"복잡한 트리 모델이 오히려 노이즈에 과적합했을 가능성을 시사한다.")
            )

        st.subheader("5-2. RandomForest 피처 중요도")
        rf = fitted_reg["RandomForestRegressor"]
        importance = pd.Series(rf.feature_importances_, index=X_full.columns).sort_values(ascending=False).head(10)
        st.bar_chart(importance)
        top3 = importance.head(3)
        st.info(
            "**읽는 법**: 막대가 길수록 RandomForest가 예측할 때 그 피처를 더 자주/결정적으로 사용했다는 뜻이다 "
            "(트리를 분기시킬 때 그 피처가 오차를 얼마나 줄였는지의 누적 기여도).\n\n"
            f"가장 영향력 큰 3개는 **{top3.index[0]}**({top3.iloc[0]*100:.1f}%), **{top3.index[1]}**({top3.iloc[1]*100:.1f}%), "
            f"**{top3.index[2]}**({top3.iloc[2]*100:.1f}%)로, 이 셋의 합이 전체 중요도의 {top3.sum()*100:.1f}%를 차지한다. "
            "실무적으로는 '지연을 줄이려면 어디를 먼저 손봐야 하는가'에 대한 데이터 기반 우선순위이기도 하다 — "
            "상위 피처가 원핫인코딩된 특정 부서/공정 단계라면, 해당 부서·공정의 병목을 먼저 조사해야 한다는 뜻이다."
        )

        st.subheader("5-3. QA 합격 여부 분류 모델 비교")
        clf_models = {
            "LogisticRegression": LogisticRegression(max_iter=1000),
            "RandomForestClassifier": RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1),
        }
        clf_results = []
        fitted_clf = {}
        for name, model in clf_models.items():
            model.fit(Xc_train, yc_train)
            pred = model.predict(Xc_test)
            clf_results.append({
                "모델": name,
                "Accuracy": round(accuracy_score(yc_test, pred), 3),
                "F1": round(f1_score(yc_test, pred), 3),
            })
            fitted_clf[name] = model
        clf_result_df = pd.DataFrame(clf_results)
        st.dataframe(clf_result_df, hide_index=True, use_container_width=True)
        pass_rate = yc_test.mean() * 100
        best_clf_name = clf_result_df.loc[clf_result_df["F1"].idxmax(), "모델"]
        st.info(
            f"**Accuracy와 F1을 같이 보는 이유**: 테스트셋에서 실제 합격 비율이 **{pass_rate:.1f}%**다. "
            + (f"합격이 압도적으로 많은 불균형 데이터라, '무조건 합격이라고 찍는' 바보 모델도 Accuracy {pass_rate:.1f}%가 나온다. "
               f"그래서 Accuracy만으로는 모델이 실제로 불합격 케이스를 잡아내는지 알 수 없고, "
               f"합격/불합격 각각을 얼마나 정확히·놓치지 않고 맞히는지를 종합한 F1-score를 같이 봐야 한다."
               if pass_rate > 70 or pass_rate < 30 else
               f"합격/불합격 비율이 비교적 균형적이라 Accuracy도 어느 정도 신뢰할 수 있지만, "
               f"F1-score는 두 클래스를 고르게 잘 맞히는지까지 확인해준다.") + "\n\n"
            f"**{best_clf_name}**가 F1 기준 최고 성능(F1={clf_result_df['F1'].max():.3f}) — "
            "실시간 예측(7번 탭)의 QA 합격확률 예측은 이 표에서 학습된 RandomForestClassifier를 사용한다."
        )

        st.session_state["fitted_reg"] = fitted_reg
        st.session_state["fitted_clf"] = fitted_clf
        st.session_state["best_reg_name"] = best_reg_name
        st.session_state["X_columns"] = list(X_full.columns)

# ---------------------------------------------------------------------------
# 6. 성능 향상
# ---------------------------------------------------------------------------
with tab6:
    section("06", "성능 향상", "GridSearchCV · 다항 특성")
    X_full = st.session_state.get("X_full")
    df = st.session_state.get("proc_df")
    if X_full is None or df is None:
        st.warning("먼저 '3. 데이터 전처리'와 '5. 학습·예측·평가' 탭을 순서대로 열어주세요.")
    else:
        y_delay = df["delay_days"]
        X_train, X_test, y_train, y_test = train_test_split(X_full, y_delay, test_size=0.2, random_state=0)

        base_rf = RandomForestRegressor(n_estimators=200, random_state=0, n_jobs=-1)
        base_rf.fit(X_train, y_train)
        base_r2 = r2_score(y_test, base_rf.predict(X_test))
        base_rmse = root_mean_squared_error(y_test, base_rf.predict(X_test))

        st.subheader("6-1. GridSearchCV 하이퍼파라미터 튜닝")
        st.code("""
parameters = {
    'max_depth': [None, 5, 10],
    'min_samples_split': [2, 5, 9],
    'min_samples_leaf': [1, 5, 10],
}
grid = GridSearchCV(RandomForestRegressor(n_estimators=100, random_state=0),
                     param_grid=parameters, scoring='r2', cv=3, n_jobs=-1)
grid.fit(X_train, y_train)
""", language="python")

        if st.button("GridSearchCV 실행 (수십 초 소요)"):
            with st.spinner(f"{len(X_train):,}행 학습 데이터에 대해 그리드서치 중... (전체 코어 병렬 사용)"):
                parameters = {
                    "max_depth": [None, 5, 10],
                    "min_samples_split": [2, 5, 9],
                    "min_samples_leaf": [1, 5, 10],
                }
                grid = GridSearchCV(
                    RandomForestRegressor(n_estimators=100, random_state=0),
                    param_grid=parameters, scoring="r2", cv=3, n_jobs=-1,
                )
                grid.fit(X_train, y_train)
                best = grid.best_estimator_
                tuned_r2 = r2_score(y_test, best.predict(X_test))
                tuned_rmse = root_mean_squared_error(y_test, best.predict(X_test))

            c1, c2 = st.columns(2)
            with c1:
                st.metric("튜닝 전 R²", f"{base_r2:.3f}")
                st.metric("튜닝 전 RMSE", f"{base_rmse:.3f}")
            with c2:
                st.metric("튜닝 후 R²", f"{tuned_r2:.3f}", delta=f"{tuned_r2 - base_r2:+.3f}")
                st.metric("튜닝 후 RMSE", f"{tuned_rmse:.3f}", delta=f"{tuned_rmse - base_rmse:+.3f}", delta_color="inverse")
            st.write("**최적 하이퍼파라미터**")
            st.json(grid.best_params_)
            st.session_state["fitted_reg"] = {**st.session_state.get("fitted_reg", {}), "RandomForest(Tuned)": best}

            r2_gain = tuned_r2 - base_r2
            st.info(
                f"**GridSearchCV가 한 일**: `max_depth`(트리 최대 깊이) 3가지 × `min_samples_split`(분기에 필요한 최소 샘플 수) 3가지 × "
                f"`min_samples_leaf`(리프 노드 최소 샘플 수) 3가지 = 총 **27가지 조합**을, "
                f"각각 3-fold 교차검증(cv=3, 데이터를 3등분해서 번갈아 검증)으로 27×3=81번 학습·평가해 "
                f"R²가 가장 높은 조합을 자동으로 골랐다.\n\n"
                + (f"R²가 기본 대비 **{r2_gain:+.3f}** 개선됐다 — "
                   f"기본 RandomForest(`n_estimators=200`, 깊이 제한 없음)가 이미 최적에 가까웠거나, "
                   f"이 데이터 규모에서는 하이퍼파라미터보다 피처 자체(어떤 변수를 쓰는지)가 성능을 더 좌우한다는 뜻일 수 있다."
                   if abs(r2_gain) < 0.01 else
                   (f"R²가 기본 대비 **{r2_gain:+.3f}** 개선됐다 — 트리 깊이·분기 조건을 제한해서 훈련 데이터에 대한 과적합을 줄인 결과로 해석할 수 있다."
                    if r2_gain > 0 else
                    f"오히려 R²가 **{r2_gain:+.3f}** 낮아졌다 — GridSearchCV는 교차검증 평균 기준으로 최적을 고르기 때문에, "
                    f"이 특정 테스트셋 하나에서는 기본 설정보다 살짝 못할 수 있다(과적합 방지와 특정 테스트셋 성능은 다른 문제)."))
            )

        st.subheader("6-2. 다항 특성 (Polynomial Features) 실험")
        st.caption("선형모델(Ridge)에 `x1×x2` 같은 변수 간 곱셈항을 추가해서, 선형모델도 비선형 관계 일부를 표현할 수 있게 하는 기법이다.")
        degree = st.slider("차수(degree)", 1, 3, 2)
        st.code(f"""
poly = PolynomialFeatures(degree={degree}, include_bias=False)
X_train_poly = poly.fit_transform(X_train)
ridge = Ridge(alpha=10)
ridge.fit(X_train_poly, y_train)
""", language="python")
        poly = PolynomialFeatures(degree=degree, include_bias=False)
        X_train_poly = poly.fit_transform(X_train)
        X_test_poly = poly.transform(X_test)
        ridge_poly = Ridge(alpha=10)
        ridge_poly.fit(X_train_poly, y_train)
        poly_r2 = r2_score(y_test, ridge_poly.predict(X_test_poly))
        st.metric(f"{degree}차 다항 + Ridge R²", f"{poly_r2:.3f}", delta=f"{poly_r2 - base_r2:+.3f} (기본 RF 대비)")
        st.info(
            f"**`fit_transform`이 한 일**: 원래 {X_train.shape[1]}개였던 피처를 {degree}차 조합(제곱항·교차항 포함)으로 늘려 "
            f"**{X_train_poly.shape[1]}개**로 확장한 뒤, 그 확장된 입력으로 Ridge 회귀를 학습했다.\n\n"
            + (f"차수를 올렸는데도 RandomForest(R²={base_r2:.3f})를 못 따라간다면, 이 문제는 몇 개 변수의 단순 곱셈 조합보다 "
               f"'조건에 따라 다른 규칙이 적용되는' 트리 구조 쪽이 더 잘 맞는 문제라는 뜻이다. "
               "차수를 3까지 올리면 피처 수가 급격히 늘어나 훈련 데이터에 과적합될 위험도 커지므로, "
               "R²가 계속 오르지 않는다면 무작정 차수를 높이는 게 답이 아니다."
               if poly_r2 <= base_r2 else
               f"기본 RandomForest보다도 R²가 높게 나왔다 — 이 피처 조합에서는 몇몇 변수의 곱셈 관계(교차항)가 "
               "지연일수를 설명하는 데 실제로 중요하다는 신호다.")
        )

# ---------------------------------------------------------------------------
# 7. 실시간 예측
# ---------------------------------------------------------------------------
with tab7:
    section("07", "실시간 예측", "학습된 모델로 즉시 추론")
    st.caption("학습된 모델에 새 블록 정보를 입력하면 예상 지연일수 / QA 합격 확률을 즉시 예측합니다")

    if "fitted_reg" not in st.session_state:
        st.warning("먼저 '5. 학습·예측·평가' 탭을 열어 모델을 학습시키세요.")
    else:
        with st.form("predict_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                in_ship = st.selectbox("선종", sorted(raw_df["ship_type"].unique()))
                in_dept = st.selectbox("부서", sorted(raw_df["department"].unique()))
            with c2:
                in_stage = st.selectbox("공정 단계", sorted(raw_df["process_stage"].unique()))
                in_priority = st.selectbox("우선순위", ["High", "Medium", "Low"])
            with c3:
                in_triangle = st.number_input("삼각형 수", min_value=100, max_value=2_000_000, value=50000, step=1000)
                in_planned = st.number_input("계획 일수", min_value=1, max_value=60, value=14)
            with c4:
                in_lod = st.selectbox("LOD 레벨", [1, 2, 3])
            submitted = st.form_submit_button("예측하기", use_container_width=True, type="primary")

        if submitted:
            model_scaler = st.session_state["model_scaler"]
            oh_enc = st.session_state["oh_enc"]

            num_input = pd.DataFrame([{
                "triangle_count": in_triangle,
                "file_size_mb": in_triangle / 45000,
                "lod_level": in_lod,
                "planned_days": in_planned,
            }])
            num_scaled = pd.DataFrame(model_scaler.transform(num_input[MODEL_NUMERIC_COLS]), columns=MODEL_NUMERIC_COLS)
            cat_input = pd.DataFrame([{
                "department": in_dept, "process_stage": in_stage, "priority": in_priority, "ship_type": in_ship,
            }])
            cat_encoded = pd.DataFrame(oh_enc.transform(cat_input[CATEGORICAL_COLS]), columns=oh_enc.get_feature_names_out())
            X_input = pd.concat([num_scaled, cat_encoded], axis=1).reindex(columns=st.session_state["X_columns"], fill_value=0)

            best_model = st.session_state["fitted_reg"][st.session_state["best_reg_name"]]
            pred_delay = best_model.predict(X_input)[0]

            clf = st.session_state["fitted_clf"]["RandomForestClassifier"]
            pred_qa_prob = clf.predict_proba(X_input)[0][1]

            with st.container(border=True):
                c1, c2 = st.columns(2)
                c1.metric("예상 지연일수", f"{pred_delay:.1f}일")
                c2.metric("QA 합격 확률", f"{pred_qa_prob * 100:.1f}%")
                if pred_delay > 5:
                    st.error("고위험: 계획 대비 5일 이상 지연 가능성이 높습니다")
                elif pred_delay > 2:
                    st.warning("주의: 소폭 지연 가능성이 있습니다")
                else:
                    st.success("양호: 계획대로 진행될 가능성이 높습니다")

# ---------------------------------------------------------------------------
# 8. 기술 스택
# ---------------------------------------------------------------------------
with tab8:
    section("08", "기술 스택", "3D 뷰어부터 이 대시보드까지 — 처음부터 끝까지 쓴 것 전부")
    st.markdown(
        '<div class="hero-sub" style="margin-bottom:1.4rem;">'
        '1인 개발 · 예산 ₩0 · 100% 오픈소스/무료 소프트웨어로 구성했습니다. '
        '아래는 프로젝트를 진행한 순서 그대로, 3D 뷰어 → 변환 파이프라인 → 생산 데이터/ROI → '
        'DB 정규화 → 머신러닝 대시보드 → AI 에이전트 연동까지 사용한 전체 스택입니다.'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown('<div class="card-title">프로젝트 진행 순서</div>', unsafe_allow_html=True)
        timeline = [
            "① 3D 뷰어 — React + Three.js로 경량 형상 렌더링 기반 구축",
            "② 변환 파이프라인 — IFC/DXF → glTF(SLF) 배치 변환 서비스",
            "③ 생산 데이터/ROI 모델링 — 가상 생산 레코드 + 경량화 도입 효용성 시뮬레이션",
            "④ SQLite → MariaDB 마이그레이션 — 정규화 스키마(dim_*/fact_*)로 재설계",
            "⑤ 머신러닝 대시보드 — 전처리·EDA·회귀/분류 예측을 갖춘 이 Streamlit 앱",
            "⑥ AI 에이전트 연동 — MCP 서버 + REST API로 생산 DB/예측모델을 도구화",
        ]
        for t in timeline:
            st.markdown(f"<div style='padding:3px 0;color:#c4c4cc;font-size:0.86rem;'>{t}</div>", unsafe_allow_html=True)

    STACK_LAYERS = [
        ("3D 뷰어 (Frontend)", [
            ("React 18", "3D 뷰어 UI 프레임워크"),
            ("Vite", "빌드 도구 · 개발 서버"),
            ("Three.js", "WebGL 기반 3D 렌더링 엔진"),
            ("React Three Fiber", "Three.js의 React 렌더러"),
            ("@react-three/drei", "OrbitControls·Html·useGLTF·GizmoHelper 등 R3F 헬퍼"),
            ("TailwindCSS", "유틸리티 기반 CSS"),
            ("react-icons", "아이콘 세트"),
        ]),
        ("변환 파이프라인 (Backend)", [
            ("Python 3.12", "전체 백엔드 런타임"),
            ("Flask", "REST API 서버 (변환/배치/AI 쿼리)"),
            ("watchdog", "PollingObserver 기반 입력 폴더 감시"),
            ("IfcOpenShell", "IFC(BIM) 파싱 · 형상/색상 추출"),
            ("ezdxf", "DXF 도면 파싱"),
            ("struct (표준 라이브러리)", "glTF 바이너리(.bin) 직접 패킹"),
        ]),
        ("데이터베이스", [
            ("MariaDB 11.2", "정규화 스키마(dim_*/fact_*), Cloudtype 클라우드 호스팅"),
            ("SQLAlchemy", "쿼리 엔진 · 커넥션 관리"),
            ("PyMySQL", "MariaDB 드라이버"),
            ("SQLite", "로컬 오프라인 백업 경로용 (generate_*.py)"),
        ]),
        ("머신러닝 · 데이터 분석", [
            ("pandas / numpy", "데이터 적재 · 전처리 · 피처 엔지니어링"),
            ("scikit-learn", "RandomForest·LinearRegression·Ridge·LogisticRegression·GridSearchCV·NearestNeighbors 등"),
            ("matplotlib / seaborn", "상관관계 히트맵 · 분포 시각화"),
        ]),
        ("대시보드", [
            ("Streamlit", "지금 보고 있는 이 인터랙티브 대시보드"),
        ]),
        ("AI 에이전트 연동", [
            ("MCP (Model Context Protocol)", "mcp_server.py - 7개 도구를 AI 클라이언트에 노출"),
            ("Flask REST API (/api/ai/*)", "3D 뷰어 내 AI 쿼리 패널이 직접 호출하는 동일 로직"),
        ]),
        ("인프라", [
            ("Cloudtype", "MariaDB 무료 클라우드 호스팅"),
            ("총 라이선스 비용", "₩0 (100% 오픈소스/무료 소프트웨어)"),
        ]),
    ]

    cols = st.columns(2)
    for i, (layer, items) in enumerate(STACK_LAYERS):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f'<div class="card-title">{layer}</div>', unsafe_allow_html=True)
                st.dataframe(
                    pd.DataFrame(items, columns=["구성", "역할"]),
                    hide_index=True, use_container_width=True,
                )
