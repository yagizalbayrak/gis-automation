"""Port through which the domain and application layers obtain CRS facts.

The only implementation lives in infrastructure and wraps pyproj. Nothing
outside infrastructure may parse CRS strings or query EPSG data directly.
"""
from __future__ import annotations

from typing import Protocol

from ageo.domain.value_objects.crs import CrsDescriptor


class CrsInfoPort(Protocol):
    def describe(self, crs_like: object) -> CrsDescriptor:
        """Resolve any CRS-like input (EPSG code, 'EPSG:5254', WKT, pyproj CRS)
        into an immutable descriptor of facts."""
        ...

    def suggest_metric_crs(self, lon: float, lat: float) -> CrsDescriptor:
        """Recommend a projected metric CRS for a location (TUREF TM zones
        inside Turkey, UTM elsewhere)."""
        ...
