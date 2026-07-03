"""Location-aware metric CRS selection (TUREF zones in Turkey, UTM elsewhere)."""
from __future__ import annotations

from ageo.domain.value_objects.crs import CrsKind


def test_kutahya_gets_turef_tm30(crs_info) -> None:
    descriptor = crs_info.suggest_metric_crs(lon=29.98, lat=39.42)
    assert descriptor.srid == "EPSG:5254"
    assert "TM30" in descriptor.name
    assert descriptor.is_metric()


def test_eastern_turkey_gets_a_higher_turef_zone(crs_info) -> None:
    descriptor = crs_info.suggest_metric_crs(lon=41.3, lat=39.9)  # Erzurum area
    assert descriptor.is_metric()
    assert "TM42" in descriptor.name
    assert descriptor.srid == "EPSG:5258"


def test_outside_turkey_falls_back_to_utm(crs_info) -> None:
    descriptor = crs_info.suggest_metric_crs(lon=13.4, lat=52.5)  # Berlin
    assert descriptor.srid == "EPSG:32633"  # WGS 84 / UTM 33N
    assert descriptor.is_metric()


def test_describe_classifies_common_crs(crs_info) -> None:
    assert crs_info.describe("EPSG:4326").kind is CrsKind.GEOGRAPHIC
    assert crs_info.describe("EPSG:5254").kind is CrsKind.PROJECTED_METRIC
    assert crs_info.describe(5254).is_metric()
    # US survey foot CRS must NOT classify as metric
    assert crs_info.describe("EPSG:2277").kind is CrsKind.PROJECTED_OTHER
