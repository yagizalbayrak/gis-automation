"""Overlay, aggregation, join and packaging tool tests."""
from __future__ import annotations

import json

import geopandas as gpd
import pytest
from pydantic import ValidationError
from shapely.geometry import Point, Polygon

from ageo.application.tools.errors import ToolExecutionError

SQUARE_A = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])       # 2x2 at origin
SQUARE_B = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])       # 2x2 shifted
SQUARE_ADJACENT = Polygon([(2, 0), (4, 0), (4, 2), (2, 2)])  # touches SQUARE_A


def _layer(ctx, geoms, crs="EPSG:5254", **columns):
    gdf = gpd.GeoDataFrame(columns or None, geometry=list(geoms), crs=crs)
    return ctx.write(gdf, name="test")


def test_intersect_area(executor, ctx) -> None:
    a = _layer(ctx, [SQUARE_A], zone=["a"])
    b = _layer(ctx, [SQUARE_B], region=["b"])
    out = executor.execute("intersect", {"layer": a, "other": b})
    result = ctx.read(out.layer)
    assert out.feature_count == 1
    assert result.geometry.iloc[0].area == pytest.approx(1.0)
    assert {"zone", "region"} <= set(result.columns)


def test_difference_area(executor, ctx) -> None:
    a = _layer(ctx, [SQUARE_A])
    b = _layer(ctx, [SQUARE_B])
    out = executor.execute("difference", {"layer": a, "other": b})
    assert ctx.read(out.layer).geometry.iloc[0].area == pytest.approx(3.0)


def test_overlay_rejects_crs_mismatch(executor, ctx) -> None:
    a = _layer(ctx, [SQUARE_A], crs="EPSG:5254")
    b = _layer(ctx, [SQUARE_B], crs="EPSG:32635")
    with pytest.raises(ToolExecutionError, match="crs_mismatch"):
        executor.execute("intersect", {"layer": a, "other": b})


def test_dissolve_by_field(executor, ctx) -> None:
    layer = _layer(
        ctx, [SQUARE_A, SQUARE_ADJACENT, SQUARE_B], category=["x", "x", "y"]
    )
    out = executor.execute("dissolve", {"layer": layer, "by": "category"})
    result = ctx.read(out.layer)
    assert out.feature_count == 2
    merged = result[result["category"] == "x"].geometry.iloc[0]
    assert merged.area == pytest.approx(8.0)  # two adjacent 2x2 squares fused


def test_spatial_join_within(executor, ctx) -> None:
    points = _layer(ctx, [Point(0.5, 0.5), Point(10, 10)], site=["s1", "s2"])
    zones = _layer(ctx, [SQUARE_A], zone_name=["core"])
    out = executor.execute(
        "spatial_join",
        {"layer": points, "other": zones, "predicate": "within"},
    )
    result = ctx.read(out.layer)
    assert out.feature_count == 1
    assert result["zone_name"].iloc[0] == "core"
    assert result["site"].iloc[0] == "s1"


def test_package_outputs_manifest(executor, ctx, tmp_path) -> None:
    roads = _layer(ctx, [SQUARE_A], name=["a"])
    sites = _layer(ctx, [Point(1, 1)], name=["p"])
    target = tmp_path / "delivery"

    out = executor.execute(
        "package_outputs",
        {
            "layers": (roads, sites),
            "names": ("roads", "sites"),
            "directory": str(target),
        },
    )

    assert (target / "roads.gpkg").exists()
    assert (target / "sites.gpkg").exists()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["format"] == "GPKG"
    assert [layer["srid"] for layer in manifest["layers"]] == ["EPSG:5254"] * 2
    assert manifest["layers"][0]["feature_count"] == 1
    assert len(out.files) == 2


def test_package_outputs_rejects_mismatched_names(executor, ctx) -> None:
    roads = _layer(ctx, [SQUARE_A])
    with pytest.raises(ValidationError, match="same length"):
        executor.execute(
            "package_outputs",
            {"layers": (roads,), "names": ("a", "b"), "directory": "/tmp/x"},
        )


def test_package_outputs_guards_each_layer_in_collection(executor, ctx) -> None:
    """Collection inputs get the same CRS guard as single inputs: one
    CRS-less layer poisons the whole package request."""
    from ageo.application.tools.errors import CrsGuardViolation

    good = _layer(ctx, [SQUARE_A])
    bad = _layer(ctx, [SQUARE_B], crs=None)
    with pytest.raises(CrsGuardViolation):
        executor.execute(
            "package_outputs",
            {"layers": (good, bad), "names": ("g", "b"), "directory": "/tmp/x"},
        )
