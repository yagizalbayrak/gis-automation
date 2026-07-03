"""Domain-layer CRS rules: the geodetic gate as a pure function."""
from __future__ import annotations

from ageo.domain.value_objects.crs import CrsDescriptor, CrsKind
from ageo.domain.value_objects.requirements import CrsRequirement, check_crs

WGS84 = CrsDescriptor("EPSG", 4326, CrsKind.GEOGRAPHIC, "degree", "WGS 84")
TUREF_TM30 = CrsDescriptor("EPSG", 5254, CrsKind.PROJECTED_METRIC, "metre", "TUREF / TM30")
FEET_CRS = CrsDescriptor("EPSG", 2277, CrsKind.PROJECTED_OTHER, "US survey foot", "Texas Central ftUS")


def test_metric_requirement_rejects_geographic() -> None:
    message = check_crs(CrsRequirement.PROJECTED_METRIC, WGS84)
    assert message is not None
    assert "EPSG:4326" in message
    assert "reproject" in message.lower()


def test_metric_requirement_rejects_foot_based_projected_crs() -> None:
    # Projected is NOT sufficient: a foot-based CRS would silently produce
    # a "25 foot" buffer for a 25 metre request.
    assert check_crs(CrsRequirement.PROJECTED_METRIC, FEET_CRS) is not None


def test_metric_requirement_accepts_turef_tm30() -> None:
    assert check_crs(CrsRequirement.PROJECTED_METRIC, TUREF_TM30) is None


def test_missing_crs_always_fails_unless_requirement_is_none() -> None:
    assert check_crs(CrsRequirement.ANY_DEFINED, None) is not None
    assert check_crs(CrsRequirement.PROJECTED_METRIC, None) is not None
    assert check_crs(CrsRequirement.NONE, None) is None


def test_geographic_requirement() -> None:
    assert check_crs(CrsRequirement.GEOGRAPHIC, WGS84) is None
    assert check_crs(CrsRequirement.GEOGRAPHIC, TUREF_TM30) is not None
