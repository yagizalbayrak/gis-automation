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
from shapely.geometry import LineString, shape

from ageo.application.tools.errors import GatewayError

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "ageo-autonomous-gis-workbench/0.1 (contact: ops@ageo.local)"
_TIMEOUT_S = 60


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
            f"way[{tag}]{extra}({south},{west},{north},{east});"
            f"out geom tags;"
        )
        body = urllib.parse.urlencode({"data": overpass_query}).encode()
        payload = self._post_json(self._overpass_url, body)

        records: list[dict] = []
        geometries: list = []
        for element in payload.get("elements", []):
            coords = [(pt["lon"], pt["lat"]) for pt in element.get("geometry", [])]
            if len(coords) < 2:
                continue
            geometries.append(LineString(coords))
            tags = element.get("tags", {})
            records.append({
                "osm_id": element.get("id"),
                "name": tags.get("name"),
                key: tags.get(key),
            })
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
