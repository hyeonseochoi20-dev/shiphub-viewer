#!/usr/bin/env python3
"""실제 형상(벽체)이 있는 테스트 IFC 파일 생성 - ifcopenshell 고레벨 API 사용"""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.aggregate
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.style
import ifcopenshell.api.material


def create_test_ifc():
    model = ifcopenshell.api.run("project.create_file", version="IFC4")

    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Ship Test Project")
    ifcopenshell.api.run("unit.assign_unit", model)

    model_ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Ship Deck")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Ship Hull")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Deck Level")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    # 실제 형상이 있는 벽체 3개 (선체 격벽을 흉내)
    for i in range(3):
        wall = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcWallStandardCase", name=f"Bulkhead {i + 1}"
        )
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])

        representation = ifcopenshell.api.run(
            "geometry.add_wall_representation", model, context=body_ctx,
            length=20.0, height=5.0, thickness=0.3,
        )
        ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=representation)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", model, product=wall,
            matrix=[[1, 0, 0, 0], [0, 1, 0, i * 6.0], [0, 0, 1, 0], [0, 0, 0, 1]],
        )

    model.write("input_models/test_ship.ifc")
    print("실지오메트리 포함 테스트 IFC 파일 생성: input_models/test_ship.ifc (벽체 3개)")


if __name__ == "__main__":
    import os
    os.makedirs("input_models", exist_ok=True)
    create_test_ifc()
