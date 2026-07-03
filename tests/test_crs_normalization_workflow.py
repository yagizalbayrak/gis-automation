"""crs_normalization workflow end-to-end, exercising layer collections
through workflow bindings."""
from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import Polygon


def test_crs_normalization_end_to_end(runner, ctx, tmp_path) -> None:
    source = tmp_path / "input.geojson"
    gpd.GeoDataFrame(
        {"name": ["parcel"]},
        geometry=[Polygon([(29.9, 39.4), (30.0, 39.4), (30.0, 39.5), (29.9, 39.5)])],
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")
    delivery = tmp_path / "delivery"

    outputs = runner.run(
        "crs_normalization",
        {
            "path": str(source),
            "target_srid": "EPSG:5254",
            "output_dir": str(delivery),
        },
    )

    assert ctx.read(outputs["layer"]).crs.to_epsg() == 5254
    assert (delivery / "normalized.gpkg").exists()
    manifest = json.loads((delivery / "manifest.json").read_text())
    assert manifest["layers"][0]["srid"] == "EPSG:5254"
