"""Workflow registry and runner tests, including the static CRS-coherence
check and the road_fetch_and_buffer MVP scenario end-to-end (fake OSM)."""
from __future__ import annotations

import pytest

from ageo.application.orchestration.trace import TracePhase
from ageo.application.tools.errors import (
    WorkflowParamError,
    WorkflowRegistrationError,
)
from ageo.application.tools.registry import registry
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.application.workflows.spec import WorkflowParam, WorkflowSpec, WorkflowStep


def test_geodetically_incoherent_workflow_rejected_at_registration(crs_info) -> None:
    """An OSM fetch (EPSG:4326) piped straight into buffer_metric must be
    impossible to register - this is the compile-time geodetic guarantee."""
    bad = WorkflowSpec(
        name="naive_buffer",
        summary="fetch roads and buffer them without reprojecting (WRONG)",
        params=(
            WorkflowParam(name="place", kind="string"),
            WorkflowParam(name="buffer_m", kind="float"),
        ),
        steps=(
            WorkflowStep(id="boundary", tool="fetch_osm_boundary",
                         params={"place_name": "$params.place"}),
            WorkflowStep(id="roads", tool="fetch_osm_features",
                         params={"boundary": "$steps.boundary.layer", "key": "highway"}),
            WorkflowStep(id="buffered", tool="buffer_metric",
                         params={"layer": "$steps.roads.layer",
                                 "distance_m": "$params.buffer_m"}),
        ),
    )
    workflow_registry = WorkflowRegistry(registry, crs_info)
    with pytest.raises(WorkflowRegistrationError, match="metric"):
        workflow_registry.register(bad)


def test_broken_step_reference_rejected(crs_info) -> None:
    bad = WorkflowSpec(
        name="broken_ref",
        summary="references a step that does not exist",
        steps=(
            WorkflowStep(id="report", tool="validate_geometry",
                         params={"layer": "$steps.ghost.layer"}),
        ),
    )
    workflow_registry = WorkflowRegistry(registry, crs_info)
    with pytest.raises(WorkflowRegistrationError, match="ghost"):
        workflow_registry.register(bad)


def test_bundled_workflows_register_cleanly(workflows) -> None:
    assert "road_fetch_and_buffer" in workflows.names()
    assert "preflight_quality_check" in workflows.names()


def test_road_fetch_and_buffer_end_to_end(runner, ctx, trace) -> None:
    """The MVP scenario: 'Kutahya'daki Ataturk Caddesi icin 25 m buffer uygula'."""
    outputs = runner.run(
        "road_fetch_and_buffer",
        {"place": "Kutahya, Turkey", "street_name": "Ataturk", "buffer_m": 25.0},
    )

    all_roads = ctx.read(outputs["all_roads"])
    assert len(all_roads) == 4

    selected = ctx.read(outputs["selected_roads"])
    assert len(selected) == 1
    assert selected["name"].iloc[0] == "Ataturk Caddesi"

    buffered = ctx.read(outputs["buffered"])
    assert buffered.crs.to_epsg() == 4326  # display CRS
    assert (buffered.geometry.geom_type == "Polygon").all()

    phases = trace.phases()
    assert phases[0] == TracePhase.WORKFLOW_STARTED.value
    assert phases[-1] == TracePhase.WORKFLOW_FINISHED.value
    assert TracePhase.GUARD_FAILED.value not in phases


def test_runner_rejects_non_metric_target_srid(runner) -> None:
    """The 'srid_metric' parameter contract: a geographic CRS cannot even
    start the workflow, let alone reach the buffer step."""
    with pytest.raises(WorkflowParamError, match="not a projected metric CRS"):
        runner.run(
            "road_fetch_and_buffer",
            {
                "place": "Kutahya, Turkey",
                "street_name": "Ataturk",
                "buffer_m": 25.0,
                "target_srid": "EPSG:4326",
            },
        )


def test_missing_required_param_rejected(runner) -> None:
    with pytest.raises(WorkflowParamError, match="street_name"):
        runner.run("road_fetch_and_buffer", {"place": "Kutahya", "buffer_m": 25.0})


def test_preflight_quality_check(runner, ctx, tmp_path) -> None:
    import geopandas as gpd
    from shapely.geometry import Polygon

    source = tmp_path / "input.geojson"
    gpd.GeoDataFrame(
        {"name": ["a"]},
        geometry=[Polygon([(29.9, 39.4), (30.0, 39.4), (30.0, 39.5), (29.9, 39.5)])],
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")

    outputs = runner.run("preflight_quality_check", {"path": str(source)})
    assert len(ctx.read(outputs["layer"])) == 1
