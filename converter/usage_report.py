#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사용량 리포트 — 로그를 '이 시스템은 쓰이고 있다'는 근거로 바꾼다.

로그는 남기는 것보다 읽어내는 게 목적이다. 예산·존치 심사에서 필요한 건
파일 더미가 아니라 "월 몇 명이 몇 번, 어떤 기능을 썼는가" 한 장이다.

사용법
    python usage_report.py                     # 전체 기간
    python usage_report.py --days 30           # 최근 30일
    python usage_report.py --format csv        # 스프레드시트로 옮길 때
    python usage_report.py --log-dir /var/log/shiphub
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def read_events(log_dir: Path, days: int | None = None):
    """JSON Lines 로그를 읽어 이벤트를 하나씩 내보낸다.

    회전된 백업(.jsonl.1 등)까지 함께 읽는다. 한 줄이 깨져 있어도(쓰는 도중
    프로세스가 죽으면 생길 수 있다) 그 줄만 건너뛰고 계속한다.
    """
    cutoff = None
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for path in sorted(log_dir.glob("*.jsonl*")):
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue                 # 깨진 줄은 버리고 진행
                    if cutoff:
                        try:
                            if datetime.fromisoformat(ev["ts"]) < cutoff:
                                continue
                        except (KeyError, ValueError):
                            pass
                    yield ev
        except OSError:
            continue


def summarize(events):
    """이벤트 목록을 심사에 쓸 수 있는 지표로 접는다."""
    s = {
        "total": 0,
        "by_month": defaultdict(lambda: {"events": 0, "users": set(), "sessions": set()}),
        "by_event": Counter(),
        "sections": Counter(),
        "api_paths": Counter(),
        "errors": Counter(),
        "latency": defaultdict(list),
        "users": set(),
        "sessions": set(),
        "first": None,
        "last": None,
    }
    for ev in events:
        s["total"] += 1
        ts = ev.get("ts", "")
        month = ts[:7]
        s["by_event"][ev.get("event", "?")] += 1

        m = s["by_month"][month]
        m["events"] += 1
        if ev.get("client"):
            m["users"].add(ev["client"]); s["users"].add(ev["client"])
        if ev.get("session"):
            m["sessions"].add(ev["session"]); s["sessions"].add(ev["session"])

        if ev.get("event") == "section_view" and ev.get("section"):
            s["sections"][ev["section"]] += 1
        if ev.get("event") == "http_request":
            s["api_paths"][ev.get("path", "?")] += 1
            if int(ev.get("status", 0)) >= 400:
                s["errors"][f"{ev.get('status')} {ev.get('path','')}"] += 1
        if isinstance(ev.get("latency_ms"), (int, float)):
            s["latency"][ev.get("event", "?")].append(ev["latency_ms"])
        if ts:
            s["first"] = min(s["first"] or ts, ts)
            s["last"] = max(s["last"] or ts, ts)
    return s


def pct(values, q):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * q))]


def print_text(s):
    if not s["total"]:
        print("기록된 이벤트가 없습니다. 서비스를 한 번 실행한 뒤 다시 확인하세요.")
        return
    print("=" * 68)
    print(" ShipHub 사용량 리포트")
    print("=" * 68)
    print(" 기간        %s ~ %s" % ((s["first"] or "")[:10], (s["last"] or "")[:10]))
    print(" 총 이벤트   %d건" % s["total"])
    print(" 순 사용자   %d명 (익명 해시 기준)" % len(s["users"]))
    print(" 총 세션     %d회" % len(s["sessions"]))

    print("\n[월별 추이]")
    print(" %-9s %10s %10s %10s" % ("월", "이벤트", "순 사용자", "세션"))
    for month in sorted(s["by_month"]):
        m = s["by_month"][month]
        print(" %-9s %10d %10d %10d" % (month, m["events"], len(m["users"]), len(m["sessions"])))

    if s["sections"]:
        print("\n[대시보드 탭별 열람]")
        for k, v in s["sections"].most_common():
            print("  %-28s %6d회" % (k[:28], v))

    if s["api_paths"]:
        print("\n[API 호출 상위]")
        for k, v in s["api_paths"].most_common(10):
            print("  %-38s %6d회" % (k[:38], v))

    if s["latency"]:
        print("\n[응답 시간]")
        print("  %-22s %8s %8s %8s" % ("이벤트", "건수", "중앙", "p95"))
        for k, v in sorted(s["latency"].items(), key=lambda x: -len(x[1]))[:8]:
            print("  %-22s %8d %7.0fms %7.0fms" % (k[:22], len(v), pct(v, .5), pct(v, .95)))

    if s["errors"]:
        print("\n[오류 응답]")
        for k, v in s["errors"].most_common(8):
            print("  %-38s %6d회" % (k[:38], v))
    print()


def print_csv(s):
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["월", "이벤트수", "순사용자", "세션수"])
    for month in sorted(s["by_month"]):
        m = s["by_month"][month]
        w.writerow([month, m["events"], len(m["users"]), len(m["sessions"])])


def main():
    ap = argparse.ArgumentParser(description="ShipHub 사용량 리포트")
    ap.add_argument("--log-dir", default=os.environ.get(
        "SHIPHUB_LOG_DIR", str(Path(__file__).parent / "logs")))
    ap.add_argument("--days", type=int, default=None, help="최근 N일만 집계")
    ap.add_argument("--format", choices=["text", "csv"], default="text")
    a = ap.parse_args()

    d = Path(a.log_dir)
    if not d.exists():
        print("로그 디렉터리가 없습니다: %s" % d); return 1
    s = summarize(read_events(d, a.days))
    (print_csv if a.format == "csv" else print_text)(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
