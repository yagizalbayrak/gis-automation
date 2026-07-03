"""CRS value objects.

Pure Python: no pyproj, no Pydantic. Facts about a CRS (kind, unit) are
produced exclusively by an infrastructure adapter wrapping pyproj and
injected here as immutable data. The domain layer only reasons about
those facts; it never parses CRS strings itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CrsKind(StrEnum):
    GEOGRAPHIC = "geographic"              # e.g. EPSG:4326 - degrees
    PROJECTED_METRIC = "projected_metric"  # e.g. EPSG:5254 (TUREF / TM30)
    PROJECTED_OTHER = "projected_other"    # projected but non-metre units
    UNKNOWN = "unknown"                    # missing or undetectable CRS


@dataclass(frozen=True, slots=True)
class CrsDescriptor:
    authority: str  # "EPSG"
    code: int       # 5254
    kind: CrsKind
    unit: str       # "metre", "degree", ...
    name: str = ""  # human-readable, e.g. "TUREF / TM30"

    @property
    def srid(self) -> str:
        return f"{self.authority}:{self.code}"

    def is_metric(self) -> bool:
        return self.kind is CrsKind.PROJECTED_METRIC

    def is_geographic(self) -> bool:
        return self.kind is CrsKind.GEOGRAPHIC
