"""Deterministic demo OSM gateway and demo composer: synthetic Kutahya,
no network, no LLM.

Used by the test suite and by the dev server's --demo mode so the full
workbench - including LLM-composed multi-criteria plans - can be
demonstrated offline and reproducibly. Data shape mirrors what
Nominatim/Overpass return: EPSG:4326, OSM tag columns, line geometries
for roads, points for amenities.
"""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, box

from ageo.application.tools.errors import GatewayError

KUTAHYA_BOUNDARY = box(29.8, 39.3, 30.2, 39.6)
NEIGHBORHOOD_BOUNDARY = box(29.93, 39.39, 30.02, 39.45)  # synthetic "mahalle"

# (name, highway class, geometry)
KUTAHYA_STREETS: list[tuple[str | None, str, LineString]] = [
    ("Ataturk Caddesi", "primary",
     LineString([(29.95, 39.42), (29.97, 39.425), (29.99, 39.43)])),
    ("Cumhuriyet Caddesi", "secondary",
     LineString([(29.96, 39.40), (29.98, 39.41)])),
    ("Bisiklet Yolu", "cycleway",
     LineString([(29.975, 39.418), (29.982, 39.424)])),
    (None, "residential",
     LineString([(29.90, 39.35), (29.92, 39.36)])),
]

# (name, geometry) - the school sits ~150 m from Ataturk Caddesi, so a
# 500 m school buffer and a 250 m main-road buffer genuinely intersect.
KUTAHYA_SCHOOLS: list[tuple[str, Point]] = [
    ("Evliya Celebi Ilkokulu", Point(29.9705, 39.4265)),
]

KUTAHYA_PARKS: list[tuple[str, Polygon]] = [
    ("Zafer Parki", box(29.965, 39.415, 29.972, 39.421)),
    ("Kent Park", box(29.985, 39.432, 29.994, 39.438)),
]


class DemoOsmGateway:
    def fetch_boundary(self, place_name: str) -> gpd.GeoDataFrame:
        folded = place_name.lower()
        geometry = (
            NEIGHBORHOOD_BOUNDARY
            if "mahalle" in folded or "neighborhood" in folded
            else KUTAHYA_BOUNDARY
        )
        return gpd.GeoDataFrame(
            {"name": [place_name]}, geometry=[geometry], crs="EPSG:4326"
        )

    def fetch_features(
        self, boundary, key: str, value: str | None, require_tags: tuple[str, ...] = ()
    ) -> gpd.GeoDataFrame:
        if key == "highway":
            rows = [
                (name, highway) for name, highway, _ in KUTAHYA_STREETS
                if value is None or highway == value
            ]
            geoms = [
                geom for _, highway, geom in KUTAHYA_STREETS
                if value is None or highway == value
            ]
            return gpd.GeoDataFrame(
                {"name": [n for n, _ in rows], "highway": [h for _, h in rows]},
                geometry=geoms,
                crs="EPSG:4326",
            )
        if key == "amenity" and value in (None, "school"):
            return gpd.GeoDataFrame(
                {"name": [n for n, _ in KUTAHYA_SCHOOLS],
                 "amenity": ["school"] * len(KUTAHYA_SCHOOLS)},
                geometry=[g for _, g in KUTAHYA_SCHOOLS],
                crs="EPSG:4326",
            )
        if key == "leisure" and value in (None, "park"):
            return gpd.GeoDataFrame(
                {"name": [n for n, _ in KUTAHYA_PARKS],
                 "leisure": ["park"] * len(KUTAHYA_PARKS)},
                geometry=[g for _, g in KUTAHYA_PARKS],
                crs="EPSG:4326",
            )
        return gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")


# The plan the demo composer emits for the multi-criteria rental scenario.
# It is exactly what a well-prompted model produces from the recipe; keeping
# it here makes the composed-plan pipeline demoable offline and gives tests
# a known-good reference plan.
RENTAL_SITE_SEARCH_PLAN: dict = {
    "name": "rental_site_search_kutahya",
    "summary": "Areas in the neighborhood within 500 m of a school and "
               "250 m of a main road, for a rental home search.",
    "steps": [
        {"id": "neighborhood", "tool": "fetch_osm_boundary",
         "params": {"place_name": "Evliya Celebi Mahallesi, Kutahya"}},
        {"id": "schools", "tool": "fetch_osm_features",
         "params": {"boundary": "$steps.neighborhood.layer",
                    "key": "amenity", "value": "school"}},
        {"id": "roads", "tool": "fetch_osm_features",
         "params": {"boundary": "$steps.neighborhood.layer", "key": "highway"}},
        {"id": "main_roads", "tool": "filter_by_attribute",
         "params": {"layer": "$steps.roads.layer", "field": "highway",
                    "in_values": ["primary", "secondary", "trunk"]}},
        {"id": "schools_metric", "tool": "reproject",
         "params": {"layer": "$steps.schools.layer", "target_srid": "EPSG:5254"}},
        {"id": "roads_metric", "tool": "reproject",
         "params": {"layer": "$steps.main_roads.layer", "target_srid": "EPSG:5254"}},
        {"id": "school_zone", "tool": "buffer_metric",
         "params": {"layer": "$steps.schools_metric.layer", "distance_m": 500.0}},
        {"id": "road_zone", "tool": "buffer_metric",
         "params": {"layer": "$steps.roads_metric.layer", "distance_m": 250.0}},
        {"id": "suitable", "tool": "intersect",
         "params": {"layer": "$steps.school_zone.layer",
                    "other": "$steps.road_zone.layer"}},
        {"id": "display", "tool": "reproject",
         "params": {"layer": "$steps.suitable.layer", "target_srid": "EPSG:4326"}},
    ],
    "outputs": {
        "suitable_area": "$steps.display.layer",
        "schools": "$steps.schools.layer",
        "main_roads": "$steps.main_roads.layer",
    },
}

SCORED_RENTAL_SITE_SEARCH_PLAN: dict = {
    "name": "scored_rental_site_analysis",
    "summary": "Rank candidate rental areas near schools and main roads by "
               "distance and area suitability.",
    "steps": [
        {"id": "neighborhood", "tool": "fetch_osm_boundary",
         "params": {"place_name": "Evliya Celebi Mahallesi, Kutahya"}},
        {"id": "schools", "tool": "fetch_osm_features",
         "params": {"boundary": "$steps.neighborhood.layer",
                    "key": "amenity", "value": "school"}},
        {"id": "roads", "tool": "fetch_osm_features",
         "params": {"boundary": "$steps.neighborhood.layer", "key": "highway"}},
        {"id": "main_roads", "tool": "filter_by_attribute",
         "params": {"layer": "$steps.roads.layer", "field": "highway",
                    "in_values": ["primary", "secondary", "trunk"]}},
        {"id": "schools_metric", "tool": "reproject",
         "params": {"layer": "$steps.schools.layer", "target_srid": "EPSG:5254"}},
        {"id": "roads_metric", "tool": "reproject",
         "params": {"layer": "$steps.main_roads.layer", "target_srid": "EPSG:5254"}},
        {"id": "school_zone", "tool": "buffer_metric",
         "params": {"layer": "$steps.schools_metric.layer", "distance_m": 500.0}},
        {"id": "road_zone", "tool": "buffer_metric",
         "params": {"layer": "$steps.roads_metric.layer", "distance_m": 250.0}},
        {"id": "candidates", "tool": "intersect",
         "params": {"layer": "$steps.school_zone.layer",
                    "other": "$steps.road_zone.layer"}},
        {"id": "areas", "tool": "calculate_area",
         "params": {"layer": "$steps.candidates.layer", "output_field": "area_m2"}},
        {"id": "school_distance", "tool": "nearest_neighbor_distance",
         "params": {"layer": "$steps.areas.layer",
                    "other": "$steps.schools_metric.layer",
                    "output_field": "school_distance_m"}},
        {"id": "road_distance", "tool": "nearest_neighbor_distance",
         "params": {"layer": "$steps.school_distance.layer",
                    "other": "$steps.roads_metric.layer",
                    "output_field": "road_distance_m"}},
        {"id": "scored", "tool": "score_candidates",
         "params": {"layer": "$steps.road_distance.layer",
                    "criteria": [
                        {"field": "school_distance_m", "direction": "minimize",
                         "weight": 0.4},
                        {"field": "road_distance_m", "direction": "minimize",
                         "weight": 0.4},
                        {"field": "area_m2", "direction": "maximize",
                         "weight": 0.2},
                    ]}},
        {"id": "display", "tool": "reproject",
         "params": {"layer": "$steps.scored.layer", "target_srid": "EPSG:4326"}},
    ],
    "outputs": {
        "ranked_sites": "$steps.display.layer",
        "schools": "$steps.schools.layer",
        "main_roads": "$steps.main_roads.layer",
    },
}

_SCENARIO_KEYWORDS = ("okul", "school", "kiralik", "rent", "ev ", "house")
_SCORING_KEYWORDS = (
    "rank", "score", "best", "prioritize", "puan", "sirala", "sırala",
    "skor", "en iyi",
)


class DemoComposerLlm:
    """Scripted LlmComposerPort for offline demos: answers the rental/school
    proximity scenario with the reference plan, refuses anything else the
    way a disabled composer would."""

    def compose(
        self, text, tool_catalog, recipes, feedback, *, profile=None,
        clarification_answer=None,
    ) -> dict:
        folded = text.lower()
        if any(keyword in folded for keyword in _SCENARIO_KEYWORDS):
            if any(keyword in folded for keyword in _SCORING_KEYWORDS):
                return SCORED_RENTAL_SITE_SEARCH_PLAN
            return RENTAL_SITE_SEARCH_PLAN
        raise GatewayError(
            "demo_composer: only the school/rental proximity scenario is "
            "scripted in demo mode."
        )
