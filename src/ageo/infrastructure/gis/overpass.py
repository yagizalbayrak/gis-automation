"""OSM gateway backed by Nominatim (boundary geocoding) and Overpass
(feature queries).

Network adapter: no business logic here beyond translating between the
OsmGateway port and the public APIs. Covered by integration tests only;
unit tests use a fake gateway.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import unary_union

from ageo.application.tools.errors import GatewayError

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "ageo-autonomous-gis-workbench/0.1 (contact: ops@ageo.local)"
_TIMEOUT_S = 60
_AREA_TAG_KEYS = frozenset({
    "amenity", "building", "healthcare", "landuse", "leisure", "office",
    "shop", "tourism",
})


class OverpassOsmGateway:
    def __init__(
        self,
        nominatim_url: str = _NOMINATIM_URL,
        overpass_url: str = _OVERPASS_URL,
        timeout_s: int = _TIMEOUT_S,
    ) -> None:
        self._nominatim_url = nominatim_url
        self._overpass_url = overpass_url
        self._timeout_s = timeout_s

    # Nominatim ranks large admin areas ("Kutahya" -> the whole province)
    # above the city users usually mean. Prefer settlement-scale polygons.
    _PREFERRED_ADDRESSTYPES = (
        "city", "town", "municipality", "suburb", "neighbourhood",
        "quarter", "village", "district",
    )

    def fetch_boundary(self, place_name: str) -> gpd.GeoDataFrame:
        query = urllib.parse.urlencode({
            "q": place_name,
            "format": "jsonv2",
            "polygon_geojson": 1,
            "limit": 5,
        })
        payload = self._get_json(f"{self._nominatim_url}?{query}")
        candidates = [
            result for result in payload or []
            if result.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")
        ]
        if not candidates:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

        def rank(result: dict) -> int:
            addresstype = result.get("addresstype", "")
            if addresstype in self._PREFERRED_ADDRESSTYPES:
                return self._PREFERRED_ADDRESSTYPES.index(addresstype)
            return len(self._PREFERRED_ADDRESSTYPES)

        result = min(candidates, key=rank)
        return gpd.GeoDataFrame(
            {"name": [result.get("display_name", place_name)]},
            geometry=[shape(result["geojson"])],
            crs="EPSG:4326",
        )

    def fetch_features(
        self,
        boundary: gpd.GeoDataFrame,
        key: str,
        value: str | None,
        require_tags: tuple[str, ...] = (),
    ) -> gpd.GeoDataFrame:
        west, south, east, north = boundary.total_bounds
        tag = f'"{key}"="{value}"' if value else f'"{key}"'
        extra = "".join(f'["{t}"]' for t in require_tags)
        overpass_query = (
            f"[out:json][timeout:{self._timeout_s}][maxsize:33554432];"
            f"("
            f"node[{tag}]{extra}({south},{west},{north},{east});"
            f"way[{tag}]{extra}({south},{west},{north},{east});"
            f"relation[{tag}]{extra}({south},{west},{north},{east});"
            f");"
            f"out geom tags;"
        )
        body = urllib.parse.urlencode({"data": overpass_query}).encode()
        payload = self._post_json(self._overpass_url, body)

        records: list[dict] = []
        geometries: list = []
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            geometry = _geometry_from_element(element, key, tags)
            if geometry is None or geometry.is_empty:
                continue
            geometries.append(geometry)
            records.append({
                "osm_id": element.get("id"),
                "osm_type": element.get("type"),
                "name": tags.get("name"),
                key: tags.get(key),
                **tags,
            })
        if not records:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
        if gdf.empty:
            return gdf
        # bbox query over-fetches; clip precisely to the boundary polygon
        return gdf.clip(boundary)

    def _get_json(self, url: str):
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        return self._send(request)

    def _post_json(self, url: str, body: bytes):
        request = urllib.request.Request(
            url, data=body, headers={"User-Agent": _USER_AGENT}
        )
        return self._send(request)

    def _send(self, request: urllib.request.Request):
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                return json.loads(response.read().decode())
        except Exception as exc:
            raise GatewayError(f"OSM gateway request failed: {exc}") from exc


def _geometry_from_element(element: dict, key: str, tags: dict) -> object | None:
    element_type = element.get("type")
    if element_type == "node":
        lon = element.get("lon")
        lat = element.get("lat")
        if lon is None or lat is None:
            return None
        return Point(float(lon), float(lat))

    if element_type == "way":
        coords = _coords(element.get("geometry", []))
        if len(coords) < 2:
            return None
        if _is_area_feature(key, tags) and _is_closed(coords):
            return Polygon(coords)
        return LineString(coords)

    if element_type == "relation":
        return _relation_geometry(element, key, tags)
    return None


def _relation_geometry(element: dict, key: str, tags: dict) -> object | None:
    if not _is_area_feature(key, tags):
        return None
    outers: list[Polygon] = []
    inners: list[Polygon] = []
    for member in element.get("members", []):
        coords = _coords(member.get("geometry", []))
        if len(coords) < 3:
            continue
        ring = _closed(coords)
        polygon = Polygon(ring)
        if not polygon.is_valid or polygon.is_empty:
            continue
        if member.get("role") == "inner":
            inners.append(polygon)
        else:
            outers.append(polygon)
    if not outers:
        return None
    geometry = unary_union(outers)
    if inners:
        geometry = geometry.difference(unary_union(inners))
    if isinstance(geometry, (Polygon, MultiPolygon)) and not geometry.is_empty:
        return geometry
    return None


def _coords(raw_geometry: list[dict]) -> list[tuple[float, float]]:
    return [
        (float(point["lon"]), float(point["lat"]))
        for point in raw_geometry
        if "lon" in point and "lat" in point
    ]


def _closed(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not coords:
        return coords
    if coords[0] == coords[-1]:
        return coords
    return [*coords, coords[0]]


def _is_closed(coords: list[tuple[float, float]]) -> bool:
    return len(coords) >= 4 and coords[0] == coords[-1]


def _is_area_feature(key: str, tags: dict) -> bool:
    if tags.get("area") == "yes":
        return True
    if tags.get("type") == "multipolygon":
        return True
    return key in _AREA_TAG_KEYS or any(tag in tags for tag in _AREA_TAG_KEYS)
