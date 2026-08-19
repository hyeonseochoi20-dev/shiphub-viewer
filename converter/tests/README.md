# 테스트

```bash
cd converter
python -m pytest tests/ -q          # 전체
python -m pytest tests/ -v          # 어떤 항목이 무엇을 검증하는지 보면서
```

의존성은 `pytest` 하나뿐이다. DB나 네트워크를 타지 않으므로 오프라인에서도 돈다.

| 파일 | 대상 | 왜 이걸 테스트하는가 |
|---|---|---|
| `test_obs.py` | `obs.py` | 로깅은 "실패해도 본체를 막지 않는" 설계라, 조용히 아무것도 안 남기는 고장을 눈으로 못 잡는다 |
| `test_usage_report.py` | `usage_report.py` | 집계가 틀리면 "월 몇 명이 썼다"는 근거 자체가 무너진다. 특히 순 사용자 수의 중복 제거 |
