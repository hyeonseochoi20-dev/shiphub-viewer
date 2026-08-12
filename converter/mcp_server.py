#!/usr/bin/env python3
"""
ShipHub 생산관리 MCP 서버
- Claude Desktop/Claude Code 같은 MCP 클라이언트가 이 프로젝트의 MariaDB 데이터와
  학습된 예측 모델을 도구(tool)로 바로 호출해서 조회할 수 있게 노출한다.
- 실제 쿼리/모델 로직은 production_data.py에 있다 (converter.py의 REST API와 공유).

주의: "유사 블록 검색"은 실제 3D 형상(포인트클라우드/메시)에 대한 딥러닝 임베딩이 아니라,
이미 변환 파이프라인에서 나오는 메타데이터(삼각형 수·선종·공정·복잡도 등) 기반 최근접 이웃
검색이다. 진짜 형상 기반 유사도(PyTorch 포인트클라우드 임베딩 등)는 학습된 모델이 없어
이 프로젝트 범위에서는 정직하게 미구현 상태로 남겨둔다.

실행: python mcp_server.py (stdio transport, MCP 클라이언트 설정에서 이 명령을 등록)
"""
from mcp.server import MCPServer

import production_data as pdata

mcp = MCPServer(
    name="shiphub-production",
    description=(
        "ShipHub 조선소 생산관리 DB(MariaDB) 조회 + 지연/QA 예측 모델 + 메타데이터 기반 "
        "유사 블록 검색 도구. 3D 뷰어/Streamlit 대시보드와 동일한 데이터를 사용한다."
    ),
)


@mcp.tool()
def query_blocks(
    ship_type: str | None = None,
    department: str | None = None,
    priority: str | None = None,
    qa_status: str | None = None,
    min_delay_days: float | None = None,
    limit: int = 20,
) -> list[dict]:
    """조건에 맞는 생산 블록 목록을 조회한다 (선종/부서/우선순위/QA상태/최소지연일수로 필터링).

    limit은 최대 200으로 제한된다.
    """
    return pdata.query_blocks(ship_type, department, priority, qa_status, min_delay_days, limit)


@mcp.tool()
def get_block_detail(block_id: int) -> dict:
    """block_id로 특정 블록의 전체 메타데이터(선종/척/공정/부서/형상 복잡도/지연/QA)를 조회한다."""
    result = pdata.get_block_detail(block_id)
    return result if result is not None else {"error": f"block_id={block_id} 를 찾을 수 없습니다"}


@mcp.tool()
def predict_delay(
    triangle_count: int,
    file_size_mb: float,
    lod_level: int,
    planned_days: int,
    department: str,
    process_stage: str,
    priority: str,
    ship_type: str,
) -> dict:
    """새 블록의 형상/공정 정보를 입력하면 예상 지연일수와 QA 합격 확률을 예측한다.
    (대시보드 7번 탭 '실시간 예측'과 동일한 RandomForest 모델, 데이터 누수 컬럼 제외)
    """
    return pdata.predict_delay(triangle_count, file_size_mb, lod_level, planned_days, department, process_stage, priority, ship_type)


@mcp.tool()
def find_similar_blocks(block_id: int, top_k: int = 5) -> dict:
    """지정한 block_id와 메타데이터(형상 복잡도·선종·공정·부서·우선순위)가 가장 비슷한 블록들을 찾는다.

    주의: 실제 3D 형상(지오메트리) 임베딩 기반 유사도가 아니라, 변환 파이프라인 메타데이터
    피처 공간에서의 최근접 이웃(Nearest Neighbors) 검색이다. top_k는 최대 20으로 제한된다.
    """
    results = pdata.find_similar_blocks(block_id, top_k)
    if results is None:
        return {"error": f"block_id={block_id} 를 찾을 수 없습니다"}
    return {
        "method": "메타데이터 기반 최근접 이웃 (실제 3D 형상 임베딩 아님)",
        "query_block_id": block_id,
        "results": results,
    }


@mcp.tool()
def get_roi_summary() -> dict:
    """파일럿 부서 실측 데이터 기준 최신 월 ROI 요약(연간 절감액/ROI%/투자회수기간)을 반환한다."""
    return pdata.get_roi_summary()


@mcp.tool()
def get_faq_answers() -> list[dict]:
    """자주 묻는 질문 5가지(형상 개수/압축률/평균 메쉬수/선종별 통상 제원/사용 가능한 API 목록)에 대한 답을 반환한다."""
    return pdata.get_faq_answers()


@mcp.tool()
def get_fleet_summary() -> list[dict]:
    """선종별 척수/블록수/평균 지연일수/QA 합격률/계약금액을 요약한다."""
    return pdata.get_fleet_summary()


if __name__ == "__main__":
    import asyncio

    asyncio.run(mcp.run_stdio_async())
