#!/usr/bin/env python3
"""간단한 테스트 DXF 파일 생성"""

import ezdxf

def create_test_dxf():
    # 새 DXF 문서 생성
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    # 간단한 선박 개략 도형 (직사각형 + 선체 라인)
    # 갑판
    msp.add_lwpolyline([(-25, 0, 0), (25, 0, 0), (25, 2, 0), (-25, 2, 0)], close=True)

    # 선체 측면
    msp.add_line((-20, -5, 0), (-20, 5, 0))
    msp.add_line((20, -5, 0), (20, 5, 0))
    msp.add_line((0, -5, 0), (0, 5, 0))

    # 저장
    doc.saveas("input_models/test_ship.dxf")
    print("테스트 DXF 파일 생성: input_models/test_ship.dxf")

if __name__ == "__main__":
    import os
    os.makedirs("input_models", exist_ok=True)
    create_test_dxf()