# -*- coding: utf-8 -*-
"""ml_core.py 단위 테스트.

app.py에서 떼어낸 학습 로직이 '이전과 똑같이' 동작하는지를 못박는 것이 목적이다.
분리 자체는 동작을 바꾸지 않는 이동이었으므로, 여기서 검증할 것은 두 가지다.
  1) 반환값의 순서·형태가 app.py가 기대하는 것과 같은가 (여기가 어긋나면 대시보드가 깨진다)
  2) 같은 입력에 같은 결과가 나오는가 (random_state 고정이 실제로 먹히는가)

실제 DB가 없어도 돌도록 합성 데이터를 만들어 쓴다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ml_core


@pytest.fixture(scope="module")
def df():
    """생산 블록 데이터의 최소 형태. 실제 스키마의 컬럼명을 그대로 쓴다."""
    rng = np.random.default_rng(0)
    n = 400
    return pd.DataFrame({
        "vessel_id": rng.choice([f"V{i:02d}" for i in range(8)], n),
        "process_stage": rng.choice(["절단", "조립", "탑재", "의장", "도장", "시운전"], n),
        "department": rng.choice(["기본설계", "생산관리(의장)", "품질(의장품질관리)"], n),
        "ship_type": rng.choice(["LNG운반선", "컨테이너선"], n),
        "priority": rng.choice(["High", "Medium", "Low"], n),
        "triangle_count": rng.integers(3000, 200000, n),
        "file_size_mb": rng.uniform(0.5, 8.0, n).round(2),
        "lod_level": rng.choice([1, 2, 3], n),
        "planned_days": rng.integers(5, 30, n),
        "delay_days": rng.normal(2, 2.5, n).round(1),
        "qa_status": rng.choice(["합격", "불합격"], n, p=[0.78, 0.22]),
        "created_at": pd.date_range("2026-02-20", periods=n, freq="10h"),
    })


@pytest.fixture(scope="module")
def xy(df):
    """app.py의 3번 탭이 만드는 것과 같은 모양의 설계행렬."""
    from sklearn.preprocessing import StandardScaler
    num = ["triangle_count", "file_size_mb", "lod_level", "planned_days"]
    cat = ["department", "process_stage", "priority", "ship_type"]
    sc = StandardScaler()
    X = pd.concat([pd.DataFrame(sc.fit_transform(df[num]), columns=num, index=df.index),
                   pd.get_dummies(df[cat], columns=cat)], axis=1)
    return X, df["delay_days"], (df["qa_status"] == "합격").astype(int)


# ── 반환 계약 (여기가 어긋나면 대시보드가 깨진다) ──────────────────────────
def test_회귀_반환_형태가_app이_기대하는_대로다(xy):
    X, y, _ = xy
    Xtr, Xte, ytr, yte, fitted, res = ml_core.train_regression_models(X, y)
    assert len(Xtr) + len(Xte) == len(X)
    assert set(res.columns) == {"모델", "MAE", "MSE", "RMSE", "R²"}
    assert "RandomForestRegressor" in fitted and len(res) == 5


def test_분류_반환_형태(xy):
    X, _, yq = xy
    Xte, yte, fitted, res = ml_core.train_classification_models(X, yq)
    assert set(res.columns) == {"모델", "Accuracy", "F1"}
    assert "RandomForestClassifier" in fitted and len(res) == 2


def test_집계모델_반환_형태(df):
    X, y, Xte, yte, fitted, res, r2_stage = ml_core.train_aggregate_model(df)
    assert set(res.columns) == {"모델", "MAE", "RMSE", "R2"}
    assert res.iloc[0]["모델"] == "기준선(평균값)"      # 첫 행이 기준선이라는 전제로 화면을 그린다
    assert -1.0 <= r2_stage <= 1.0


# ── 재현성 ──────────────────────────────────────────────────────────────
def test_같은_입력이면_같은_결과가_나온다(xy):
    """random_state 고정이 실제로 먹히는지. 안 먹히면 새로고침마다 지표가 바뀌어
    보고서에 적은 수치를 재현할 수 없게 된다."""
    X, y, _ = xy
    a = ml_core.train_regression_models(X, y)[5]
    b = ml_core.train_regression_models(X, y)[5]
    pd.testing.assert_frame_equal(a, b)


# ── 집계 모델의 성질 ────────────────────────────────────────────────────
def test_집계는_척과_공정_조합_수만큼_행이_된다(df):
    X, y, *_ = ml_core.train_aggregate_model(df)
    expected = df.groupby(["vessel_id", "process_stage"]).ngroups
    assert len(X) == expected == len(y)


def test_집계_피처에_실적_컬럼이_섞이지_않는다(df):
    """착수 전에 알 수 없는 값이 들어가면 누수다 - 이 프로젝트가 한 번 겪은 실패라
    회귀 방지 테스트로 못박아 둔다."""
    X, *_ = ml_core.train_aggregate_model(df)
    leaky = ["delay", "actual", "qa_defect", "지연", "실적"]
    bad = [c for c in X.columns if any(k in str(c).lower() for k in leaky)]
    assert not bad, f"누수 가능 컬럼: {bad}"


def test_집계모델이_기준선보다_낫다(df):
    """묶어서 예측하는 것이 평균만 찍는 것보다 나아야 한다.
    이게 뒤집히면 '단위를 올려 성능이 올랐다'는 보고서의 주장이 무너진다."""
    *_, res, _ = ml_core.train_aggregate_model(df)
    base = res[res["모델"] == "기준선(평균값)"].iloc[0]["MAE"]
    best = res[res["모델"] != "기준선(평균값)"]["MAE"].min()
    assert best <= base
