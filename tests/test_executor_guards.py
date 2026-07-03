"""Executor guard tests: the structural guarantees.

The headline test: buffering in EPSG:4326 is impossible, and the trace
records exactly why.
"""
from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from ageo.application.orchestration.trace import TracePhase
from ageo.application.tools.errors import CrsGuardViolation, GeometryGuardViolation

BOWTIE = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])  # self-intersecting, invalid


def test_buffer_in_epsg4326_is_structurally_impossible(executor, ctx, trace) -> None:
    roads = gpd.GeoDataFrame(
        geometry=[LineString([(29.95, 39.42), (29.99, 39.43)])], crs="EPSG:4326"
    )
    ref = ctx.write(roads, name="roads_4326")

    with pytest.raises(CrsGuardViolation) as excinfo:
        executor.execute("buffer_metric", {"layer": ref, "distance_m": 25.0})

    assert "EPSG:4326" in str(excinfo.value)
    assert TracePhase.GUARD_FAILED.value in trace.phases()
    assert TracePhase.TOOL_FINISHED.value not in trace.phases()


def test_calculate_area_in_epsg4326_is_structurally_impossible(executor, ctx) -> None:
    parcel = gpd.GeoDataFrame(
        geometry=[
            Polygon([
                (29.95, 39.42),
                (29.96, 39.42),
                (29.96, 39.43),
                (29.95, 39.43),
            ])
        ],
        crs="EPSG:4326",
    )
    ref = ctx.write(parcel, name="parcel_4326")

    with pytest.raises(CrsGuardViolation, match="EPSG:4326"):
        executor.execute("calculate_area", {"layer": ref})


def test_calculate_area_rejects_non_polygon_layers(executor, ctx) -> None:
    roads = gpd.GeoDataFrame(
        geometry=[LineString([(500000, 4360000), (500010, 4360010)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(roads, name="roads")

    with pytest.raises(GeometryGuardViolation, match="polygon"):
        executor.execute("calculate_area", {"layer": ref})


def test_calculate_length_in_epsg4326_is_structurally_impossible(executor, ctx) -> None:
    roads = gpd.GeoDataFrame(
        geometry=[LineString([(29.95, 39.42), (29.99, 39.43)])],
        crs="EPSG:4326",
    )
    ref = ctx.write(roads, name="roads_4326")

    with pytest.raises(CrsGuardViolation, match="EPSG:4326"):
        executor.execute("calculate_length", {"layer": ref})


def test_calculate_length_rejects_non_line_layers(executor, ctx) -> None:
    parcel = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(parcel, name="parcel")

    with pytest.raises(GeometryGuardViolation, match="line"):
        executor.execute("calculate_length", {"layer": ref})


def test_buffer_after_reproject_succeeds(executor, ctx) -> None:
    roads = gpd.GeoDataFrame(
        geometry=[LineString([(29.95, 39.42), (29.99, 39.43)])], crs="EPSG:4326"
    )
    ref = ctx.write(roads, name="roads_4326")

    reprojected = executor.execute(
        "reproject", {"layer": ref, "target_srid": "EPSG:5254"}
    )
    buffered = executor.execute(
        "buffer_metric", {"layer": reprojected.layer, "distance_m": 25.0}
    )
    result = ctx.read(buffered.layer)
    assert result.crs.to_epsg() == 5254
    assert (result.geometry.geom_type == "Polygon").all()


def test_invalid_geometry_blocked_until_repaired(executor, ctx) -> None:
    broken = gpd.GeoDataFrame(geometry=[BOWTIE], crs="EPSG:5254")
    ref = ctx.write(broken, name="broken")

    with pytest.raises(GeometryGuardViolation, match="repair_geometry"):
        executor.execute("buffer_metric", {"layer": ref, "distance_m": 10.0})

    repaired = executor.execute("repair_geometry", {"layer": ref})
    buffered = executor.execute(
        "buffer_metric", {"layer": repaired.layer, "distance_m": 10.0}
    )
    assert buffered.feature_count == 1


def test_geometry_class_guard_rejects_line_mask_for_clip(executor, ctx) -> None:
    layer = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5254")
    line_mask = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:5254")
    layer_ref = ctx.write(layer, name="points")
    mask_ref = ctx.write(line_mask, name="line_mask")

    with pytest.raises(GeometryGuardViolation, match="polygon"):
        executor.execute("clip", {"layer": layer_ref, "mask": mask_ref})


def test_undefined_crs_blocks_metric_operations(executor, ctx) -> None:
    no_crs = gpd.GeoDataFrame(geometry=[Point(500000, 4365000)], crs=None)
    ref = ctx.write(no_crs, name="mystery")

    with pytest.raises(CrsGuardViolation, match="no resolvable CRS"):
        executor.execute("buffer_metric", {"layer": ref, "distance_m": 5.0})
