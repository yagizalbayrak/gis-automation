"""pyproj-backed implementation of CrsInfoPort.

This is the ONLY module in the system that talks to pyproj's CRS/EPSG
machinery for CRS *facts*. Everything above receives immutable
CrsDescriptor value objects.
"""
from __future__ import annotations

from functools import lru_cache

from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info

from ageo.domain.value_objects.crs import CrsDescriptor, CrsKind

_METRE_UNITS = {"metre", "meter", "m"}

# TUREF (Turkish National Reference Frame) 3-degree Gauss-Kruger zones.
# Central meridians 27E..45E every 3 degrees; EPSG codes are contiguous
# from 5253 (TM27). Verified against the EPSG database at first use.
_TUREF_BASE_CODE = 5253
_TUREF_FIRST_CM = 27
_TUREF_LAST_CM = 45
# Approximate bounding box of Turkey for advisor routing.
_TURKEY_BBOX = (25.5, 35.5, 45.0, 42.5)  # west, south, east, north


class PyprojCrsInfo:
    def describe(self, crs_like: object) -> CrsDescriptor:
        return _describe(_as_key(crs_like))

    def suggest_metric_crs(self, lon: float, lat: float) -> CrsDescriptor:
        """TUREF TM zone inside Turkey, UTM zone elsewhere. Always metric."""
        west, south, east, north = _TURKEY_BBOX
        if west <= lon <= east and south <= lat <= north:
            descriptor = self._turef_zone_for(lon)
            if descriptor is not None:
                return descriptor
        return self._utm_for(lon, lat)

    def _turef_zone_for(self, lon: float) -> CrsDescriptor | None:
        central_meridian = min(
            range(_TUREF_FIRST_CM, _TUREF_LAST_CM + 1, 3),
            key=lambda cm: abs(cm - lon),
        )
        code = _TUREF_BASE_CODE + (central_meridian - _TUREF_FIRST_CM) // 3
        try:
            descriptor = self.describe(f"EPSG:{code}")
        except Exception:
            return None
        # Defensive check against the EPSG database: the code arithmetic must
        # land on the expected TUREF TM zone, otherwise fall back to UTM.
        expected = f"TM{central_meridian}"
        if expected in descriptor.name and descriptor.is_metric():
            return descriptor
        return None

    def _utm_for(self, lon: float, lat: float) -> CrsDescriptor:
        candidates = query_utm_crs_info(
            datum_name="WGS 84",
            area_of_interest=AreaOfInterest(
                west_lon_degree=lon, south_lat_degree=lat,
                east_lon_degree=lon, north_lat_degree=lat,
            ),
        )
        if not candidates:
            raise ValueError(f"No UTM CRS found for lon={lon}, lat={lat}")
        info = candidates[0]
        return self.describe(f"{info.auth_name}:{info.code}")


def _as_key(crs_like: object) -> str:
    """Normalize to a hashable cache key without manual CRS string surgery."""
    if isinstance(crs_like, CRS):
        return crs_like.to_wkt()
    return str(crs_like)


@lru_cache(maxsize=256)
def _describe(key: str) -> CrsDescriptor:
    crs = CRS.from_user_input(key)
    authority = crs.to_authority()
    auth_name, code = authority if authority else ("CUSTOM", "0")

    if crs.is_geographic:
        kind = CrsKind.GEOGRAPHIC
        unit = crs.axis_info[0].unit_name if crs.axis_info else "degree"
    elif crs.is_projected:
        unit = crs.axis_info[0].unit_name if crs.axis_info else ""
        kind = (
            CrsKind.PROJECTED_METRIC
            if unit.lower() in _METRE_UNITS
            else CrsKind.PROJECTED_OTHER
        )
    else:
        kind = CrsKind.UNKNOWN
        unit = ""

    return CrsDescriptor(
        authority=auth_name, code=int(code), kind=kind, unit=unit, name=crs.name
    )
