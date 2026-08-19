# -*- coding: utf-8 -*-
"""관측(Observability) 공용 모듈 — 구조화 로그 · 사용량 계측.

왜 필요한가
    사내 시스템은 "쓰이고 있다"는 증거가 없으면 사용량 저조를 이유로 정리된다.
    그런데 지금 이 프로젝트에는 누가 언제 무엇을 조회했는지 남는 곳이 없다.
    이 모듈은 그 증거를 남기는 최소 단위다.

설계 원칙
    1) JSON Lines 로 남긴다. 한 줄 = 한 이벤트라 grep·jq·Elastic·Loki 어디에든 그대로 넣을 수 있고,
       사람이 읽을 수도 있다. CSV는 필드가 늘어날 때마다 깨지고, 평문은 파싱이 어렵다.
    2) 파일과 syslog 로 동시에 보낸다. 파일은 로컬 보관용, syslog 는 사내 수집기(rsyslog/WSL)로
       흘려보내기 위한 것이다. 수집기가 없으면 syslog 핸들러만 조용히 빠진다.
    3) 개인정보를 남기지 않는다. 사용자 식별자는 해시로만 남기고 원문은 저장하지 않는다.
       "몇 명이 몇 번 썼는가"를 증명하는 데 실명은 필요 없다.
    4) 로깅이 실패해도 본체는 계속 돈다. 관측 때문에 서비스가 죽으면 본말전도다.

쓰는 법
    from obs import get_logger, log_event, timed

    log = get_logger("dashboard")
    log_event(log, "query", tab="5", rows=1234, latency_ms=87)

    with timed(log, "model_train", model="RandomForest"):
        model.fit(X, y)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import logging.handlers
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── 설정 (환경변수로 덮어쓸 수 있게 둔다 — 배포처마다 경로/수집기가 다르다) ──────────
LOG_DIR      = Path(os.environ.get("SHIPHUB_LOG_DIR", Path(__file__).parent / "logs"))
LOG_LEVEL    = os.environ.get("SHIPHUB_LOG_LEVEL", "INFO").upper()
SYSLOG_ADDR  = os.environ.get("SHIPHUB_SYSLOG")      # 예: "127.0.0.1:514" 또는 "/dev/log"
MAX_BYTES    = int(os.environ.get("SHIPHUB_LOG_MAX_BYTES", 10 * 1024 * 1024))
BACKUP_COUNT = int(os.environ.get("SHIPHUB_LOG_BACKUPS", 10))
SALT         = os.environ.get("SHIPHUB_HASH_SALT", "shiphub")

HOSTNAME = socket.gethostname()
SERVICE_VERSION = os.environ.get("SHIPHUB_VERSION", "dev")


def anon(value: str | None) -> str | None:
    """식별자를 되돌릴 수 없는 짧은 해시로 바꾼다.

    같은 사람은 항상 같은 값이 되므로 '순 사용자 수'는 셀 수 있지만,
    로그만 봐서는 누구인지 알 수 없다. 소금(salt)을 환경변수로 두어
    로그가 유출돼도 사전 공격으로 원문을 복원하기 어렵게 한다.
    """
    if not value:
        return None
    return hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()[:16]


class JsonFormatter(logging.Formatter):
    """로그 레코드를 한 줄짜리 JSON 으로 만든다.

    표준 필드(시각·수준·서비스·호스트)를 항상 넣고, log_event 가 붙인
    추가 필드(extra)를 같은 평면에 펼친다. 중첩을 만들지 않는 이유는
    로그 수집기에서 필드 색인을 걸기 쉬워서다.
    """

    # LogRecord 가 기본으로 갖는 속성들 — 이건 결과에 넣지 않는다
    _SKIP = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": record.name,
            "host": HOSTNAME,
            "version": SERVICE_VERSION,
            "event": getattr(record, "event", record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k in self._SKIP or k in out or k.startswith("_"):
                continue
            try:
                json.dumps(v)          # 직렬화 안 되는 값은 문자열로 눕힌다
                out[k] = v
            except (TypeError, ValueError):
                out[k] = str(v)
        if record.exc_info:
            out["error"] = self.formatException(record.exc_info)[-2000:]
        return json.dumps(out, ensure_ascii=False)


def _syslog_handler() -> logging.Handler | None:
    """사내 수집기로 보내는 핸들러. 주소가 없거나 못 붙으면 None 을 돌려준다.

    수집기가 없다고 서비스가 죽으면 안 되므로 실패를 삼킨다 — 파일 로그는 계속 남는다.
    """
    if not SYSLOG_ADDR:
        return None
    try:
        if SYSLOG_ADDR.startswith("/"):            # 리눅스/WSL 유닉스 소켓
            addr: str | tuple[str, int] = SYSLOG_ADDR
        else:
            host, _, port = SYSLOG_ADDR.partition(":")
            addr = (host, int(port or 514))
        h = logging.handlers.SysLogHandler(address=addr,
                                           facility=logging.handlers.SysLogHandler.LOG_LOCAL0)
        h.setFormatter(JsonFormatter())
        return h
    except Exception:
        return None


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(service: str) -> logging.Logger:
    """서비스별 로거를 만든다(같은 이름이면 재사용).

    핸들러를 두 번 붙이면 로그가 두 줄씩 찍히므로 캐시해 둔다 —
    Streamlit 은 스크립트를 매 상호작용마다 다시 실행하기 때문에 특히 중요하다.
    """
    if service in _LOGGERS:
        return _LOGGERS[service]

    log = logging.getLogger(service)
    log.setLevel(LOG_LEVEL)
    log.propagate = False                          # 루트로 새어나가 중복 출력되는 것을 막는다

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / f"{service}.jsonl", maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        log.addHandler(fh)
    except Exception:
        pass                                       # 디스크 문제로 서비스를 막지 않는다

    sh = _syslog_handler()
    if sh:
        log.addHandler(sh)

    if os.environ.get("SHIPHUB_LOG_STDOUT", "1") == "1":
        ch = logging.StreamHandler()
        ch.setFormatter(JsonFormatter())
        log.addHandler(ch)

    _LOGGERS[service] = log
    return log


def new_session_id() -> str:
    """브라우저 세션 하나를 가리키는 임의 식별자. 개인정보가 아니다."""
    return uuid.uuid4().hex[:12]


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    """이벤트 한 건을 남긴다. 실패해도 호출한 쪽을 막지 않는다."""
    try:
        logger.log(level, event, extra={"event": event, **fields})
    except Exception:
        pass


@contextlib.contextmanager
def timed(logger: logging.Logger, event: str, **fields):
    """블록 실행 시간을 재서 남긴다. 예외가 나면 실패로 기록하고 다시 던진다.

    "얼마나 자주 쓰이는가"만큼 "얼마나 오래 걸리는가"도 중요하다 —
    느려서 안 쓰게 되는 경우를 이 수치로 잡아낼 수 있다.
    """
    t0 = time.perf_counter()
    try:
        yield
    except Exception as e:
        log_event(logger, event, level=logging.ERROR,
                  latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                  ok=False, error_type=type(e).__name__, error_msg=str(e)[:300], **fields)
        raise
    else:
        log_event(logger, event,
                  latency_ms=round((time.perf_counter() - t0) * 1000, 1), ok=True, **fields)
