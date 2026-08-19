# -*- coding: utf-8 -*-
"""ML 학습 로직 — Streamlit에 의존하지 않는 순수 함수 모음.

왜 분리했나
    이 함수들은 원래 app.py 안에서 @st.cache_resource가 붙은 채로 살았다. 그러면
    Streamlit 런타임 없이는 호출조차 할 수 없어 단위 테스트가 불가능하고, 학습 로직을
    고칠 때마다 대시보드를 띄워 눈으로 확인하는 수밖에 없었다.

    여기에는 캐싱도 UI도 두지 않는다. 데이터를 받아 모델과 지표를 돌려주는 일만 한다.
    캐싱은 app.py 쪽에서 얇은 래퍼로 감싸 붙인다 - 관심사를 나누면 이쪽은 pytest로,
    저쪽은 화면으로 각각 확인할 수 있다.

호출 규약
    반환값의 순서와 형태는 app.py가 기대하는 것과 정확히 같게 유지한다.
    (이번 분리는 동작을 바꾸지 않는 순수 이동이다.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score, f1_score, mean_absolute_error, mean_squared_error,
    r2_score, root_mean_squared_error,
)
from sklearn.model_selection import train_test_split

# 학습/검증 분리 기준 — 세 모델이 같은 분할을 쓰도록 한곳에 모아 둔다.
# 값이 흩어져 있으면 한쪽만 고쳤을 때 지표가 서로 비교 불가능해진다.
TEST_SIZE = 0.2
RANDOM_STATE = 0

# 무료 호스팅(512MB) 대응 상수. n_jobs=1은 joblib이 워커를 fork하며 학습 데이터를
# 복제하는 것을 막고, 트리 수/깊이 제한은 트리 구조 자체의 메모리를 줄인다.
RF_SMALL = dict(n_estimators=80, max_depth=12, random_state=RANDOM_STATE, n_jobs=1)


def train_regression_models(X_full, y_delay):
    """st.tabs()는 보이는 탭과 무관하게 스크립트 전체가 매번 재실행되므로, 캐싱 없이는
    사이드바 필터를 하나만 건드려도 RandomForest 포함 4개 모델이 매번 처음부터
    재학습됐다(실측 약 100초+). X_full/y_delay 내용이 실제로 바뀔 때만 재학습되도록 캐싱한다.

    n_jobs=1(단일 스레드) + n_estimators=80 + max_depth=12: joblib이 n_jobs=-1로 워커
    프로세스를 fork하면 워커마다 학습 데이터를 복제해서 메모리를 배로 먹고, 트리 개수·깊이
    제한이 없으면 단일 스레드라도 트리 구조 자체가 메모리를 많이 먹는다 - Render 무료
    티어(512MB) OOM으로 "Oh no. Error running app"가 떴던 원인. production_data.py의
    동일 이슈 수정과 같은 처방(정확도 손실은 미미하고 EDA 결론에 영향 없음)."""
    X_train, X_test, y_train, y_test = train_test_split(X_full, y_delay, test_size=0.2, random_state=0)
    models = {
        "LinearRegression": LinearRegression(),
        "Ridge(alpha=1.0)": Ridge(alpha=1.0),
        "Lasso(alpha=0.1)": Lasso(alpha=0.1),
        "ElasticNet(alpha=0.1)": ElasticNet(alpha=0.1, l1_ratio=0.5),
        "RandomForestRegressor": RandomForestRegressor(n_estimators=80, max_depth=12, random_state=0, n_jobs=1),
    }
    results = []
    fitted = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        results.append({
            "모델": name,
            "MAE": round(mean_absolute_error(y_test, pred), 3),
            "MSE": round(mean_squared_error(y_test, pred), 3),
            "RMSE": round(root_mean_squared_error(y_test, pred), 3),
            "R²": round(r2_score(y_test, pred), 3),
        })
        fitted[name] = model
    return X_train, X_test, y_train, y_test, fitted, pd.DataFrame(results)


def train_classification_models(X_full, y_qa):
    Xc_train, Xc_test, yc_train, yc_test = train_test_split(X_full, y_qa, test_size=0.2, random_state=0)
    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "RandomForestClassifier": RandomForestClassifier(n_estimators=80, max_depth=12, random_state=0, n_jobs=1),
    }
    results = []
    fitted = {}
    for name, model in models.items():
        model.fit(Xc_train, yc_train)
        pred = model.predict(Xc_test)
        results.append({
            "모델": name,
            "Accuracy": round(accuracy_score(yc_test, pred), 3),
            "F1": round(f1_score(yc_test, pred), 3),
        })
        fitted[name] = model
    return Xc_test, yc_test, fitted, pd.DataFrame(results)


def train_aggregate_model(df):
    """분석 단위를 블록 -> 척x공정으로 올린 지연 예측 모델.

    블록 하나의 지연은 재작업(결함 발생 건수)·대기(야드 혼잡)·기상이 각각 독립적인
    확률변수라 개별 예측의 상한이 낮다. 그런데 그 변동은 서로 독립이므로 여러 블록을
    묶으면 평균으로 상쇄된다 - 통계적으로 당연한 결과다. 그리고 현장이 실제로 묻는 것도
    "이 블록이 늦나"가 아니라 "이 배의 이 공정이 며칠 밀리나"이다(크리티컬 패스도
    척x공정 단위로 계산한다). 그래서 같은 데이터를 집계 단위만 바꿔 다시 학습한다.

    피처는 전부 착수 전에 알 수 있는 값이다 - 물량(블록수/삼각형 합), 계획일수,
    우선순위 구성, 착수 시기(계절), 공정. 실적 컬럼은 하나도 쓰지 않는다.
    """
    PW = {"High": 0.35, "Medium": 1.0, "Low": 1.55}
    d = df.copy()
    m = pd.to_datetime(d["created_at"]).dt.month
    d["_season"] = np.where(m.isin([12, 1, 2]), 1.0, np.where(m.isin([6, 7]), 0.8, 0.25))
    d["_pri"] = d["priority"].map(PW)
    d["_logtri"] = np.log10(d["triangle_count"] / 20000 + 1)

    g = d.groupby(["vessel_id", "process_stage"])
    X = pd.DataFrame({
        "블록수": g.size(),
        "삼각형_합": g["triangle_count"].sum(),
        "삼각형_평균": g["triangle_count"].mean(),
        "복잡도_로그평균": g["_logtri"].mean(),
        "파일크기_합": g["file_size_mb"].sum(),
        "계획일수_합": g["planned_days"].sum(),
        "계획일수_평균": g["planned_days"].mean(),
        "우선순위_가중": g["_pri"].mean(),
        "계절위험_평균": g["_season"].mean(),
        "LOD_평균": g["lod_level"].mean(),
    })
    X = X.join(pd.get_dummies(X.index.get_level_values("process_stage"), prefix="공정").set_index(X.index))
    X = X.fillna(0)
    y = g["delay_days"].sum()

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
    models = {
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=300, max_depth=8, min_samples_leaf=3, random_state=0, n_jobs=1),
        "LinearRegression": LinearRegression(),
    }
    results, fitted = [], {}
    for name, model in models.items():
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        results.append({
            "모델": name,
            "MAE": round(mean_absolute_error(yte, pred), 2),
            "RMSE": round(root_mean_squared_error(yte, pred), 2),
            "R2": round(r2_score(yte, pred), 3),
        })
        fitted[name] = model
    base = np.full(len(yte), ytr.mean())
    results.insert(0, {"모델": "기준선(평균값)", "MAE": round(mean_absolute_error(yte, base), 2),
                       "RMSE": round(root_mean_squared_error(yte, base), 2), "R2": 0.0})
    # 공정 더미만 썼을 때 - "공정만 알아도 나오는 것 아니냐"는 반문에 답하기 위한 대조군
    stage_cols = [c for c in X.columns if c.startswith("공정_")]
    only_stage = RandomForestRegressor(n_estimators=300, max_depth=8, min_samples_leaf=3,
                                       random_state=0, n_jobs=1).fit(Xtr[stage_cols], ytr)
    r2_stage = r2_score(yte, only_stage.predict(Xte[stage_cols]))
    return X, y, Xte, yte, fitted, pd.DataFrame(results), r2_stage
