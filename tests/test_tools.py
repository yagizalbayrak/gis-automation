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


def test_centroid_of_square_is_its_center(executor, ctx) -> None:
    parcels = gpd.GeoDataFrame(
        {"parcel_id": ["a"]},
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(parcels, name="parcels")

    out = executor.execute("centroid", {"layer": ref})

    result = ctx.read(out.layer)
    assert out.feature_count == 1
    assert result["parcel_id"].iloc[0] == "a"
    point = result.geometry.iloc[0]
    assert (point.x, point.y) == pytest.approx((5.0, 5.0))


def test_simplify_geometry_reduces_vertex_count(executor, ctx) -> None:
    wiggly = LineString([(0, 0), (1, 0.01), (2, -0.01), (3, 0.01), (10, 0)])
    layer = gpd.GeoDataFrame(geometry=[wiggly], crs="EPSG:5254")
    ref = ctx.write(layer, name="wiggly")

    out = executor.execute(
        "simplify_geometry", {"layer": ref, "tolerance_m": 1.0}
    )

    simplified = ctx.read(out.layer).geometry.iloc[0]
    assert len(simplified.coords) < len(wiggly.coords)


def test_count_points_in_polygons_attaches_per_polygon_counts(executor, ctx) -> None:
    polygons = gpd.GeoDataFrame(
        {"zone": ["A", "B"]},
        geometry=[
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            Polygon([(20, 0), (30, 0), (30, 10), (20, 10)]),
        ],
        crs="EPSG:5254",
    )
    points = gpd.GeoDataFrame(
        geometry=[Point(5, 5), Point(6, 6), Point(25, 5), Point(100, 100)],
        crs="EPSG:5254",
    )
    poly_ref = ctx.write(polygons, name="zones")
    point_ref = ctx.write(points, name="sites")

    out = executor.execute(
        "count_points_in_polygons", {"points": point_ref, "polygons": poly_ref}
    )

    result = ctx.read(out.layer)
    assert out.feature_count == 2
    assert out.total_points_matched == 3
    counts = dict(zip(result["zone"], result["point_count"]))
    assert counts == {"A": 2, "B": 1}


def test_count_points_in_polygons_crs_mismatch(executor, ctx) -> None:
    polygons = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])], crs="EPSG:5254"
    )
    points = gpd.GeoDataFrame(geometry=[Point(29.9, 39.4)], crs="EPSG:4326")
    poly_ref = ctx.write(polygons, name="zones")
    point_ref = ctx.write(points, name="sites")

    with pytest.raises(ToolExecutionError, match="crs_mismatch"):
        executor.execute(
            "count_points_in_polygons", {"points": point_ref, "polygons": poly_ref}
        )


def test_nearest_neighbor_distance_matches_known_offsets(executor, ctx) -> None:
    layer = gpd.GeoDataFrame(
        geometry=[Point(0, 0), Point(100, 0)], crs="EPSG:5254"
    )
    other = gpd.GeoDataFrame(geometry=[Point(0, 30), Point(100, 40)], crs="EPSG:5254")
    layer_ref = ctx.write(layer, name="sites")
    other_ref = ctx.write(other, name="facilities")

    out = executor.execute(
        "nearest_neighbor_distance", {"layer": layer_ref, "other": other_ref}
    )

    result = ctx.read(out.layer)
    assert out.feature_count == 2
    assert sorted(result["nearest_distance_m"].tolist()) == pytest.approx([30.0, 40.0])
    assert out.min_distance_m == pytest.approx(30.0)
    assert out.max_distance_m == pytest.approx(40.0)


def test_merge_layers_concatenates_features(executor, ctx) -> None:
    first = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:5254"
    )
    second = gpd.GeoDataFrame(
        {"name": ["b"], "extra": ["x"]}, geometry=[Point(1, 1)], crs="EPSG:5254"
    )
    ref1 = ctx.write(first, name="first")
    ref2 = ctx.write(second, name="second")

    out = executor.execute("merge_layers", {"layers": (ref1, ref2)})

    merged = ctx.read(out.layer)
    assert out.feature_count == 2
    assert set(merged["name"]) == {"a", "b"}


def test_merge_layers_crs_mismatch(executor, ctx) -> None:
    first = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5254")
    second = gpd.GeoDataFrame(geometry=[Point(29.9, 39.4)], crs="EPSG:4326")
    ref1 = ctx.write(first, name="first")
    ref2 = ctx.write(second, name="second")

    with pytest.raises(ToolExecutionError, match="crs_mismatch"):
        executor.execute("merge_layers", {"layers": (ref1, ref2)})


def test_csv_to_point_layer_builds_points(executor, tmp_path) -> None:
    csv_path = tmp_path / "sites.csv"
    csv_path.write_text("name,lon,lat\nsite_a,29.98,39.42\nsite_b,29.99,39.43\n")

    out = executor.execute(
        "csv_to_point_layer",
        {"path": str(csv_path), "x_field": "lon", "y_field": "lat"},
    )

    assert out.feature_count == 2
    assert out.srid == "EPSG:4326"


def test_csv_to_point_layer_missing_field(executor, tmp_path) -> None:
    csv_path = tmp_path / "sites.csv"
    csv_path.write_text("name,x,y\nsite_a,29.98,39.42\n")

    with pytest.raises(ToolExecutionError, match="missing_field"):
        executor.execute(
            "csv_to_point_layer",
            {"path": str(csv_path), "x_field": "lon", "y_field": "lat"},
        )


def test_csv_to_point_layer_missing_file(executor) -> None:
    with pytest.raises(ToolExecutionError, match="file_not_found"):
        executor.execute(
            "csv_to_point_layer",
            {"path": "/nonexistent/sites.csv", "x_field": "lon", "y_field": "lat"},
        )


def test_voronoi_polygons_covers_each_input_point(executor, ctx) -> None:
    points = gpd.GeoDataFrame(
        geometry=[Point(0, 0), Point(100, 0), Point(0, 100), Point(100, 100)],
        crs="EPSG:5254",
    )
    ref = ctx.write(points, name="sites")

    out = executor.execute("voronoi_polygons", {"layer": ref})

    cells = ctx.read(out.layer)
    assert out.feature_count == 4
    assert (cells.geometry.geom_type == "Polygon").all()


def test_voronoi_polygons_requires_at_least_two_points(executor, ctx) -> None:
    points = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5254")
    ref = ctx.write(points, name="lonely")

    with pytest.raises(ToolExecutionError, match="insufficient_points"):
        executor.execute("voronoi_polygons", {"layer": ref})


def test_grid_generation_covers_boundary_extent(executor, ctx) -> None:
    boundary = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(boundary, name="boundary")

    out = executor.execute(
        "grid_generation",
        {"layer": ref, "cell_size_m": 50.0, "clip_to_boundary": False},
    )

    grid = ctx.read(out.layer)
    assert out.feature_count == 4
    total_area = grid.geometry.area.sum()
    assert total_area == pytest.approx(100.0 * 100.0)


def test_grid_generation_too_many_cells_is_rejected(executor, ctx) -> None:
    boundary = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(boundary, name="huge_boundary")

    with pytest.raises(ToolExecutionError, match="too_many_cells"):
        executor.execute(
            "grid_generation", {"layer": ref, "cell_size_m": 1.0}
        )


def test_save_vector_dxf_and_kml(executor, ctx, tmp_path) -> None:
    lines = gpd.GeoDataFrame(
        geometry=[LineString([(480000.0, 4363000.0), (480100.0, 4363000.0)])],
        crs="EPSG:5254",
    )
    ref = ctx.write(lines, name="lines")
    dxf_path = tmp_path / "lines.dxf"
    saved = executor.execute(
        "save_vector", {"layer": ref, "path": str(dxf_path), "format": "DXF"}
    )
    assert saved.feature_count == 1

    points = gpd.GeoDataFrame(geometry=[Point(29.98, 39.42)], crs="EPSG:4326")
    point_ref = ctx.write(points, name="points_wgs84")
    kml_path = tmp_path / "points.kml"
    saved_kml = executor.execute(
        "save_vector", {"layer": point_ref, "path": str(kml_path), "format": "KML"}
    )
    assert saved_kml.feature_count == 1


def test_save_vector_kml_requires_wgs84(executor, ctx, tmp_path) -> None:
    points = gpd.GeoDataFrame(geometry=[Point(480000.0, 4363000.0)], crs="EPSG:5254")
    ref = ctx.write(points, name="points_metric")

    with pytest.raises(ToolExecutionError, match="kml_requires_wgs84"):
        executor.execute(
            "save_vector",
            {"layer": ref, "path": str(tmp_path / "points.kml"), "format": "KML"},
        )
