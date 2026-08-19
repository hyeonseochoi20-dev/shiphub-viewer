# -*- coding: utf-8 -*-
"""obs.py 단위 테스트.

로깅 모듈은 '실패해도 본체를 막지 않는다'는 설계라, 조용히 아무것도 안 남기는
고장을 눈으로는 못 잡는다. 그래서 오히려 테스트가 꼭 필요한 부분이다.
"""
import json
import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def obs(tmp_path, monkeypatch):
    """테스트마다 로그 디렉터리를 새로 잡고 모듈을 다시 읽어들인다.

    obs 는 임포트 시점에 환경변수를 읽어 상수로 굳히므로, 환경을 바꾼 뒤
    reload 하지 않으면 이전 설정이 남는다.
    """
    monkeypatch.setenv("SHIPHUB_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SHIPHUB_LOG_STDOUT", "0")
    monkeypatch.delenv("SHIPHUB_SYSLOG", raising=False)
    monkeypatch.setenv("SHIPHUB_HASH_SALT", "test-salt")
    for m in [m for m in sys.modules if m == "obs"]:
        del sys.modules[m]
    import obs as _obs
    _obs._LOGGERS.clear()
    return _obs


def _lines(tmp_path, service="svc"):
    p = Path(tmp_path) / f"{service}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ── 기록이 실제로 남는가 ────────────────────────────────────────────────
def test_이벤트가_JSON_한_줄로_남는다(obs, tmp_path):
    log = obs.get_logger("svc")
    obs.log_event(log, "query", rows=1234, tab="5")
    rows = _lines(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["event"] == "query" and r["rows"] == 1234 and r["tab"] == "5"
    assert r["level"] == "INFO" and r["service"] == "svc"
    assert "ts" in r and "host" in r


def test_한글과_특수문자가_깨지지_않는다(obs, tmp_path):
    log = obs.get_logger("svc")
    obs.log_event(log, "query", 부서="생산관리(가공/건조)", 선종="LNG운반선")
    assert _lines(tmp_path)[0]["부서"] == "생산관리(가공/건조)"


def test_직렬화_불가능한_값도_기록된다(obs, tmp_path):
    """set 이나 객체가 섞여 들어와도 로그가 통째로 유실되면 안 된다."""
    log = obs.get_logger("svc")
    obs.log_event(log, "odd", payload={1, 2, 3})
    assert "payload" in _lines(tmp_path)[0]


# ── 익명화 ─────────────────────────────────────────────────────────────
def test_같은_사용자는_같은_해시_다른_사용자는_다른_해시(obs):
    a1, a2, b = obs.anon("최현서"), obs.anon("최현서"), obs.anon("김철수")
    assert a1 == a2 and a1 != b
    assert "최현서" not in a1 and len(a1) == 16


def test_빈_값은_None(obs):
    assert obs.anon(None) is None and obs.anon("") is None


def test_소금이_다르면_해시도_다르다(tmp_path, monkeypatch):
    """로그가 유출돼도 사전 공격으로 원문을 못 찾게 하는 장치가 실제로 동작하는지."""
    def build(salt):
        monkeypatch.setenv("SHIPHUB_HASH_SALT", salt)
        monkeypatch.setenv("SHIPHUB_LOG_DIR", str(tmp_path))
        sys.modules.pop("obs", None)
        import obs as m
        return m.anon("최현서")
    assert build("salt-a") != build("salt-b")


# ── 소요시간 계측 ───────────────────────────────────────────────────────
def test_timed가_성공을_기록한다(obs, tmp_path):
    log = obs.get_logger("svc")
    with obs.timed(log, "train", model="RF"):
        pass
    r = _lines(tmp_path)[0]
    assert r["ok"] is True and r["model"] == "RF" and r["latency_ms"] >= 0


def test_timed가_예외를_기록하고_다시_던진다(obs, tmp_path):
    """관측이 예외를 삼켜버리면 진짜 장애가 숨는다 — 반드시 다시 던져야 한다."""
    log = obs.get_logger("svc")
    with pytest.raises(ValueError):
        with obs.timed(log, "train"):
            raise ValueError("boom")
    r = _lines(tmp_path)[0]
    assert r["ok"] is False and r["level"] == "ERROR"
    assert r["error_type"] == "ValueError" and "boom" in r["error_msg"]


# ── 견고성 ─────────────────────────────────────────────────────────────
def test_같은_로거를_두_번_받아도_중복_기록되지_않는다(obs, tmp_path):
    """Streamlit 은 상호작용마다 스크립트를 다시 실행한다.
    핸들러가 매번 붙으면 로그가 2줄, 3줄로 불어난다."""
    obs.log_event(obs.get_logger("svc"), "a")
    obs.log_event(obs.get_logger("svc"), "b")
    assert len(_lines(tmp_path)) == 2


def test_로그를_못_쓰는_상황에서도_예외가_나지_않는다(obs):
    """디스크가 차거나 권한이 없어도 서비스는 계속 돌아야 한다."""
    class Broken(logging.Logger):
        def log(self, *a, **k): raise OSError("disk full")
    obs.log_event(Broken("x"), "query")     # 예외가 새어나오면 실패


def test_세션_아이디는_매번_다르다(obs):
    ids = {obs.new_session_id() for _ in range(50)}
    assert len(ids) == 50 and all(len(i) == 12 for i in ids)
