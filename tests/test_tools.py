"""Deterministic tool correctness tests."""
from __future__ import annotations

import math

import geopandas as gpd
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

from ageo.application.tools.errors import ToolExecutionError

KUTAHYA_LON, KUTAHYA_LAT = 29.98, 39.42


def test_reproject_matches_pyproj_reference(executor, ctx) -> None:
    point = gpd.GeoDataFrame(
        geometry=[Point(KUTAHYA_LON, KUTAHYA_LAT)], crs="EPSG:4326"
    )
    ref = ctx.write(point, name="kutahya_point")

    out = executor.execute("reproject", {"layer": ref, "target_srid": "EPSG:5254"})

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5254", always_xy=True)
    expected_x, expected_y = transformer.transform(KUTAHYA_LON, KUTAHYA_LAT)
    actual = ctx.read(out.layer).geometry.iloc[0]
    assert actual.x == pytest.approx(expected_x, abs=1e-6)
    assert actual.y == pytest.approx(expected_y, abs=1e-6)


def test_buffer_area_is_geodetically_sane(executor, ctx) -> None:
    # A 25 m buffer around a point must have area ~ pi * 25^2 in a metric CRS.
    point = gpd.GeoDataFrame(geometry=[Point(480000.0, 4363000.0)], crs="EPSG:5254")
    ref = ctx.write(point, name="site")

    out = executor.execute("buffer_metric", {"layer": ref, "distance_m": 25.0})

    area = ctx.read(out.layer).geometry.iloc[0].area
    assert area == pytest.approx(math.pi * 25.0**2, rel=0.01)


def test_calculate_area_adds_metric_area_attribute(executor, ctx) -> None:
    parcels = gpd.GeoDataFrame(
        {"parcel_id": ["a", "b"]},
        geometry=[
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            Polygon([(20, 0), (25, 0), (25, 4), (20, 4)]),
        ],
        crs="EPSG:5254",
    )
    ref = ctx.write(parcels, name="parcels")

    out = executor.execute("calculate_area", {"layer": ref, "output_field": "area_m2"})

    measured = ctx.read(out.layer)
    assert out.feature_count == 2
    assert out.total_area_m2 == pytest.approx(120.0)
    assert tuple(measured["area_m2"]) == pytest.approx((100.0, 20.0))
    assert out.table == ({"area_m2": 100.0}, {"area_m2": 20.0})


def test_calculate_area_can_report_hectares(executor, ctx) -> None:
    park = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(park, name="park")

    out = executor.execute(
        "calculate_area",
        {"layer": ref, "output_field": "area_ha", "unit": "ha"},
    )

    measured = ctx.read(out.layer)
    assert out.total_area_m2 == pytest.approx(10_000.0)
    assert measured["area_ha"].iloc[0] == pytest.approx(1.0)
    assert out.table == ({"area_ha": 1.0},)


def test_calculate_length_adds_metric_length_attribute(executor, ctx) -> None:
    paths = gpd.GeoDataFrame(
        {"name": ["short", "long"]},
        geometry=[
            LineString([(0, 0), (3, 4)]),
            LineString([(10, 0), (10, 12)]),
        ],
        crs="EPSG:5254",
    )
    ref = ctx.write(paths, name="paths")

    out = executor.execute("calculate_length", {"layer": ref})

    measured = ctx.read(out.layer)
    assert out.feature_count == 2
    assert out.total_length_m == pytest.approx(17.0)
    assert tuple(measured["length_m"]) == pytest.approx((5.0, 12.0))
    assert out.table == ({"length_m": 5.0}, {"length_m": 12.0})


def test_calculate_length_can_report_kilometres(executor, ctx) -> None:
    cycleways = gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (300, 400)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(cycleways, name="cycleways")

    out = executor.execute(
        "calculate_length",
        {"layer": ref, "output_field": "length_km", "unit": "km"},
    )

    measured = ctx.read(out.layer)
    assert out.total_length_m == pytest.approx(500.0)
    assert measured["length_km"].iloc[0] == pytest.approx(0.5)
    assert out.table == ({"length_km": 0.5},)


def test_filter_by_attribute_contains(executor, ctx) -> None:
    streets = gpd.GeoDataFrame(
        {"name": ["Ataturk Caddesi", "Cumhuriyet Caddesi", None]},
        geometry=[
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
            LineString([(2, 2), (3, 3)]),
        ],
        crs="EPSG:4326",
    )
    ref = ctx.write(streets, name="streets")

    out = executor.execute(
        "filter_by_attribute",
        {"layer": ref, "field": "name", "contains": "ataturk"},
    )
    assert out.matched_count == 1

    with pytest.raises(ToolExecutionError, match="missing_field"):
        executor.execute(
            "filter_by_attribute",
            {"layer": ref, "field": "street_type", "equals": "primary"},
        )


def test_filter_folds_turkish_diacritics_like_real_osm_names(executor, ctx) -> None:
    """Real OSM carries 'Atatürk Bulvarı'; users type 'Ataturk Bulvari'.
    Case-insensitive matching must fold Turkish diacritics both ways."""
    streets = gpd.GeoDataFrame(
        {"name": ["Atatürk Bulvarı", "İnönü Caddesi", "Gazi Bulvarı"]},
        geometry=[
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
            LineString([(2, 2), (3, 3)]),
        ],
        crs="EPSG:4326",
    )
    ref = ctx.write(streets, name="real_names")

    out = executor.execute(
        "filter_by_attribute",
        {"layer": ref, "field": "name", "contains": "ataturk bulvari"},
    )
    assert out.matched_count == 1

    out = executor.execute(
        "filter_by_attribute",
        {"layer": ref, "field": "name", "equals": "inonu caddesi"},
    )
    assert out.matched_count == 1


def test_validate_and_repair_geometry(executor, ctx) -> None:
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    layer = gpd.GeoDataFrame(
        geometry=[bowtie, square, square, Polygon()], crs="EPSG:5254"
    )
    ref = ctx.write(layer, name="dirty")

    report = executor.execute("validate_geometry", {"layer": ref})
    assert report.invalid_count == 1
    assert report.duplicate_count == 1
    assert report.empty_count == 1
    assert report.is_clean is False

    repaired = executor.execute("repair_geometry", {"layer": ref})
    clean_report = executor.execute("validate_geometry", {"layer": repaired.layer})
    assert clean_report.is_clean is True
    # bowtie repaired (kept), one duplicate square and one empty dropped
    assert repaired.feature_count == 2


def test_load_save_roundtrip_geopackage(executor, ctx, tmp_path) -> None:
    original = gpd.GeoDataFrame(
        {"name": ["parcel_1"]},
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(original, name="parcels")

    target = tmp_path / "out" / "parcels.gpkg"
    saved = executor.execute(
        "save_vector", {"layer": ref, "path": str(target), "format": "GPKG"}
    )
    assert saved.feature_count == 1

    loaded = executor.execute("load_vector", {"path": str(target)})
    assert loaded.feature_count == 1
    assert loaded.srid == "EPSG:5254"
    assert loaded.geometry_types == ("Polygon",)


def test_load_vector_missing_file(executor) -> None:
    with pytest.raises(ToolExecutionError, match="file_not_found"):
        executor.execute("load_vector", {"path": "/nonexistent/file.shp"})
