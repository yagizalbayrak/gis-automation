"""Overpass gateway parsing tests.

No network calls: tests inject Overpass/Nominatim JSON payloads directly and
verify the adapter turns real OSM element shapes into useful geometries.
"""
from __future__ import annotations

import urllib.parse

import geopandas as gpd
from shapely.geometry import box

from ageo.infrastructure.gis.overpass import OverpassOsmGateway


class FakeOverpassGateway(OverpassOsmGateway):
    def __init__(self, payload: dict) -> None:
        super().__init__(timeout_s=5)
        self.payload = payload
        self.last_body: bytes | None = None

    def _post_json(self, url: str, body: bytes):
        self.last_body = body
        return self.payload


def _boundary() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[box(29.9, 39.4, 30.0, 39.5)], crs="EPSG:4326")


def test_overpass_fetches_nodes_ways_and_relations_in_one_query() -> None:
    gateway = FakeOverpassGateway({"elements": []})

    gateway.fetch_features(_boundary(), "amenity", "school", ("name",))

    assert gateway.last_body is not None
    query = urllib.parse.parse_qs(gateway.last_body.decode())["data"][0]
    assert 'node["amenity"="school"]["name"]' in query
    assert 'way["amenity"="school"]["name"]' in query
    assert 'relation["amenity"="school"]["name"]' in query


def test_overpass_parses_school_node_and_closed_way_polygon() -> None:
    gateway = FakeOverpassGateway({
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 39.426,
                "lon": 29.970,
                "tags": {"amenity": "school", "name": "Point School"},
            },
            {
                "type": "way",
                "id": 2,
                "tags": {"amenity": "school", "name": "Polygon School"},
                "geometry": [
                    {"lat": 39.420, "lon": 29.960},
                    {"lat": 39.420, "lon": 29.965},
                    {"lat": 39.425, "lon": 29.965},
                    {"lat": 39.425, "lon": 29.960},
                    {"lat": 39.420, "lon": 29.960},
                ],
            },
        ]
    })

    result = gateway.fetch_features(_boundary(), "amenity", "school")

    assert len(result) == 2
    assert set(result.geometry.geom_type) == {"Point", "Polygon"}
    assert set(result["name"]) == {"Point School", "Polygon School"}
    assert set(result["osm_type"]) == {"node", "way"}


def test_overpass_keeps_open_highway_way_as_line() -> None:
    gateway = FakeOverpassGateway({
        "elements": [
            {
                "type": "way",
                "id": 10,
                "tags": {"highway": "primary", "name": "Main Road"},
                "geometry": [
                    {"lat": 39.420, "lon": 29.950},
                    {"lat": 39.430, "lon": 29.980},
                ],
            },
        ]
    })

    result = gateway.fetch_features(_boundary(), "highway", None)

    assert len(result) == 1
    assert result.geometry.iloc[0].geom_type == "LineString"
    assert result["highway"].iloc[0] == "primary"


def test_overpass_parses_multipolygon_relation_with_hole() -> None:
    gateway = FakeOverpassGateway({
        "elements": [
            {
                "type": "relation",
                "id": 20,
                "tags": {"type": "multipolygon", "landuse": "residential"},
                "members": [
                    {
                        "role": "outer",
                        "geometry": [
                            {"lat": 39.410, "lon": 29.930},
                            {"lat": 39.410, "lon": 29.990},
                            {"lat": 39.470, "lon": 29.990},
                            {"lat": 39.470, "lon": 29.930},
                            {"lat": 39.410, "lon": 29.930},
                        ],
                    },
                    {
                        "role": "inner",
                        "geometry": [
                            {"lat": 39.430, "lon": 29.950},
                            {"lat": 39.430, "lon": 29.960},
                            {"lat": 39.440, "lon": 29.960},
                            {"lat": 39.440, "lon": 29.950},
                            {"lat": 39.430, "lon": 29.950},
                        ],
                    },
                ],
            },
        ]
    })

    result = gateway.fetch_features(_boundary(), "landuse", "residential")

    assert len(result) == 1
    geometry = result.geometry.iloc[0]
    assert geometry.geom_type == "Polygon"
    assert len(geometry.interiors) == 1
