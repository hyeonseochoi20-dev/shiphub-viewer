# -*- coding: utf-8 -*-
"""임포트 회귀 테스트.

app.py의 최상위 임포트가 깨지면 Streamlit Cloud에서 앱 전체가 ImportError로 죽는다.
그런데 이 오류는 로컬에서 개별 모듈만 임포트해 보면 잡히지 않는다 - 실제로
has_db_config 를 db_url 이 아닌 obs 에서 가져오도록 잘못 쓴 커밋이 배포까지 나갔다.
Streamlit 런타임 없이 임포트 문만 뽑아 실행해서 그 부류를 막는다.
"""
import ast
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _import_statements(path: Path):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    return [ast.get_source_segment(src, n) for n in tree.body
            if isinstance(n, (ast.Import, ast.ImportFrom))]


@pytest.mark.parametrize("module", ["app.py", "converter.py", "production_data.py",
                                    "ml_core.py", "obs.py", "usage_report.py"])
def test_최상위_임포트가_전부_성공한다(module):
    path = ROOT / module
    if not path.exists():
        pytest.skip(f"{module} 없음")
    stmts = _import_statements(path)
    assert stmts, f"{module}에 임포트 문이 없다"
    exec(compile("\n".join(stmts), f"<{module} imports>", "exec"), {})


def test_모든_모듈이_구문_오류_없이_파싱된다():
    for p in ROOT.glob("*.py"):
        ast.parse(io.open(p, encoding="utf-8").read(), filename=str(p))
