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

/* 사이드바 필터 위젯 - 기본 스트림릿 테마의 primaryColor(진한 파랑)가 선택박스 배경/테두리/포커스링/
   체크박스/라디오/드롭다운 옵션 하이라이트 등 거의 모든 인터랙티브 요소에 그대로 노출되어 "커스텀 안 하고
   기본 스트림릿 그대로 쓴 것" 같은 인상을 줬음. 사이드바 안에서는 파랑 강조색을 전부 중성 회색 계열로 눌러준다. */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.014);
    border-right: 1px solid rgba(255,255,255,0.06);
}

/* 선택박스(멀티셀렉트/셀렉트박스) 컨트롤 전체 - 자식 depth 상관없이 전부 중성 회색으로 */
[data-testid="stSidebar"] [data-baseweb="select"],
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] div[class] {
    background-color: rgba(255,255,255,0.05) !important;
    border-color: rgba(255,255,255,0.10) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"]:focus-within,
[data-testid="stSidebar"] [data-baseweb="select"]:hover {
    border-color: rgba(255,255,255,0.24) !important;
    box-shadow: none !important;
}

/* 선택된 값 칩(태그) */
[data-testid="stSidebar"] [data-baseweb="tag"] {
    background-color: rgba(255,255,255,0.11) !important;
    border: 1px solid rgba(255,255,255,0.16) !important;
    color: #d4d4d8 !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] span { color: #d4d4d8 !important; }
[data-testid="stSidebar"] [data-baseweb="tag"] svg { fill: #a1a1aa !important; }

/* 드롭다운을 펼쳤을 때 나오는 옵션 목록 - 호버/선택된 옵션 배경이 파랑이었던 것을 중성 회색으로 */
[data-baseweb="popover"] [role="listbox"] { background-color: #16161a !important; border: 1px solid rgba(255,255,255,0.1) !important; }
[data-baseweb="popover"] [role="option"] { background-color: transparent !important; color: #d4d4d8 !important; }
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"] { background-color: rgba(255,255,255,0.08) !important; }

/* 체크박스/라디오 - 선택된(checked) 상태의 파란 배경을 중성 톤으로 */
[data-testid="stSidebar"] [role="radiogroup"] label { color: #d4d4d8; }
[data-testid="stSidebar"] [data-baseweb="radio"] div:first-child,
[data-testid="stSidebar"] [data-baseweb="checkbox"] div:first-child {
    border-color: rgba(255,255,255,0.28) !important;
}
[data-testid="stSidebar"] [aria-checked="true"] > div:first-child {
    background-color: rgba(255,255,255,0.65) !important;
    border-color: rgba(255,255,255,0.65) !important;
}

/* 슬라이더 - 트랙/썸을 좀 더 또렷하게. 사이드바(기간 select_slider)는 채워진 트랙 색까지 파랑이라 눈에 띄었어서 회색 계열로 낮춤 */
[data-testid="stSlider"] [data-baseweb="slider"] > div > div { background: rgba(255,255,255,0.12) !important; }
[data-testid="stSlider"] [role="slider"] { box-shadow: 0 0 0 4px rgba(59,130,246,0.18) !important; }
[data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] div[class] { background-color: rgba(255,255,255,0.16) !important; }
[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"] {
    background-color: #9aa1ac !important;
    box-shadow: 0 0 0 4px rgba(255,255,255,0.12) !important;
}

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

    st.subheader("변수별 분포 (범주형 - 빈도)")
    st.code("for col in cat_cols: sns.countplot(x=col, data=df)", language="python")
    cat_cols_row = st.columns(len(CATEGORICAL_COLS))
    for col_slot, col_name in zip(cat_cols_row, CATEGORICAL_COLS):
        with col_slot:
            st.caption(f"**{col_name}**")
            st.bar_chart(fdf[col_name].value_counts())

    st.subheader("상관관계 히트맵")
    st.code("sns.heatmap(df[num_cols].corr(), annot=True, cmap='RdBu_r')", language="python")
    corr = fdf[NUMERIC_COLS + ["delay_days"]].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1, ax=ax)
    st.pyplot(fig)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("부서별 평균 지연일")
        st.bar_chart(fdf.groupby("department")["delay_days"].mean())
    with c2:
        st.subheader("선종별 블록 수 · 평균 복잡도")
        st.bar_chart(fdf.groupby("ship_type")["triangle_count"].mean())
    with c3:
        st.subheader("우선순위별 지연일 분포")
        fig2, ax2 = plt.subplots(figsize=(5, 4))
        sns.boxplot(x="priority", y="delay_days", data=fdf, order=["High", "Medium", "Low"], ax=ax2)
        st.pyplot(fig2)

    st.subheader("월별 평균 지연일 추이")
    monthly = pd.to_datetime(fdf["created_at"]).dt.to_period("M").astype(str)
    st.line_chart(fdf.groupby(monthly)["delay_days"].mean())

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
            st.success(f"최고 성능 회귀 모델: **{best_reg_name}** (R²={reg_result_df['R²'].max():.3f})")

        st.subheader("5-2. RandomForest 피처 중요도")
        rf = fitted_reg["RandomForestRegressor"]
        importance = pd.Series(rf.feature_importances_, index=X_full.columns).sort_values(ascending=False).head(10)
        st.bar_chart(importance)

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

        st.subheader("6-2. 다항 특성 (Polynomial Features) 실험")
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
