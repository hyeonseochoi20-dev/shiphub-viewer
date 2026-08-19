# -*- coding: utf-8 -*-
"""usage_report.py 단위 테스트.

집계가 틀리면 "월 몇 명이 썼다"는 근거 자체가 무너진다. 특히 순 사용자 수는
중복 제거가 핵심이라 반드시 검증해야 한다.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import usage_report as ur


def write(tmp_path, rows, name="api.jsonl"):
    (tmp_path / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return tmp_path


def ev(ts, event="http_request", **kw):
    return {"ts": ts, "event": event, **kw}


def test_순_사용자는_중복을_제거한다(tmp_path):
    """같은 사람이 100번 써도 1명으로 세야 한다 - 사용량을 부풀리지 않기 위해."""
    write(tmp_path, [ev("2026-08-01T10:00:00+00:00", client="a") for _ in range(100)]
                    + [ev("2026-08-01T11:00:00+00:00", client="b")])
    s = ur.summarize(ur.read_events(tmp_path))
    assert s["total"] == 101 and len(s["users"]) == 2


def test_월별로_나뉜다(tmp_path):
    write(tmp_path, [ev("2026-07-15T10:00:00+00:00", client="a"),
                     ev("2026-08-02T10:00:00+00:00", client="a"),
                     ev("2026-08-03T10:00:00+00:00", client="b")])
    s = ur.summarize(ur.read_events(tmp_path))
    assert s["by_month"]["2026-07"]["events"] == 1
    assert s["by_month"]["2026-08"]["events"] == 2
    assert len(s["by_month"]["2026-08"]["users"]) == 2


def test_깨진_줄은_건너뛰고_나머지를_읽는다(tmp_path):
    """로그를 쓰는 도중 프로세스가 죽으면 마지막 줄이 잘린다.
    그 한 줄 때문에 전체 리포트가 실패하면 안 된다."""
    p = tmp_path / "api.jsonl"
    p.write_text('{"ts":"2026-08-01T10:00:00+00:00","event":"a"}\n'
                 '{"ts":"2026-08-01T10:00:01","event":  <<깨짐\n'
                 '{"ts":"2026-08-01T10:00:02+00:00","event":"b"}\n', encoding="utf-8")
    s = ur.summarize(ur.read_events(tmp_path))
    assert s["total"] == 2


def test_회전된_백업_파일도_함께_읽는다(tmp_path):
    write(tmp_path, [ev("2026-08-01T10:00:00+00:00")], "api.jsonl")
    write(tmp_path, [ev("2026-07-01T10:00:00+00:00")], "api.jsonl.1")
    assert ur.summarize(ur.read_events(tmp_path))["total"] == 2


def test_days_옵션이_오래된_기록을_제외한다(tmp_path):
    now = datetime.now(timezone.utc)
    write(tmp_path, [ev((now - timedelta(days=1)).isoformat()),
                     ev((now - timedelta(days=100)).isoformat())])
    assert ur.summarize(ur.read_events(tmp_path, days=30))["total"] == 1
    assert ur.summarize(ur.read_events(tmp_path))["total"] == 2


def test_오류_응답만_따로_집계한다(tmp_path):
    write(tmp_path, [ev("2026-08-01T10:00:00+00:00", path="/api/ai/faq", status=200),
                     ev("2026-08-01T10:00:01+00:00", path="/api/ai/faq", status=500),
                     ev("2026-08-01T10:00:02+00:00", path="/api/ai/faq", status=500)])
    s = ur.summarize(ur.read_events(tmp_path))
    assert sum(s["errors"].values()) == 2 and s["api_paths"]["/api/ai/faq"] == 3


def test_탭별_열람_집계(tmp_path):
    write(tmp_path, [ev("2026-08-01T10:00:00+00:00", "section_view", section="5. 학습·예측·평가"),
                     ev("2026-08-01T10:01:00+00:00", "section_view", section="5. 학습·예측·평가"),
                     ev("2026-08-01T10:02:00+00:00", "section_view", section="1. 데이터 정의")])
    s = ur.summarize(ur.read_events(tmp_path))
    assert s["sections"]["5. 학습·예측·평가"] == 2


def test_백분위수_계산(tmp_path):
    assert ur.pct([], 0.5) == 0.0
    assert ur.pct([10, 20, 30, 40, 100], 0.5) == 30
    assert ur.pct([10, 20, 30, 40, 100], 0.95) == 100


def test_빈_디렉터리도_예외_없이_처리된다(tmp_path):
    s = ur.summarize(ur.read_events(tmp_path))
    assert s["total"] == 0 and not s["users"]
