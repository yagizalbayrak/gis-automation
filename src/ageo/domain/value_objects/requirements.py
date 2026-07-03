"""Declarative preconditions a tool imposes on its layer inputs.

These are DATA, not behaviour: the executor guard interprets them at
runtime and the workflow registry interprets them symbolically at
registration time. Keeping them declarative lets the planner catalog
and the trace panel display them without executing anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ageo.domain.value_objects.crs import CrsDescriptor, CrsKind


class GeometryClass(StrEnum):
    POINT = "point"
    LINE = "line"
    POLYGON = "polygon"
    ANY = "any"


class CrsRequirement(StrEnum):
    ANY_DEFINED = "any_defined"            # any CRS, but it must be known
    PROJECTED_METRIC = "projected_metric"  # buffer, area, length live here
    GEOGRAPHIC = "geographic"              # e.g. lat/lon bbox inputs
    NONE = "none"                          # tool is CRS-agnostic


@dataclass(frozen=True, slots=True)
class InputRequirement:
    crs: CrsRequirement = CrsRequirement.ANY_DEFINED
    geometry: frozenset[GeometryClass] = field(
        default_factory=lambda: frozenset({GeometryClass.ANY})
    )
    requires_valid_geometry: bool = False  # True => guard checks validity first

    def allows_geometry(self, geometry_class: GeometryClass) -> bool:
        return GeometryClass.ANY in self.geometry or geometry_class in self.geometry


def check_crs(requirement: CrsRequirement, crs: CrsDescriptor | None) -> str | None:
    """Return a violation message, or None if the requirement is satisfied.

    This is THE geodetic gate. "Do not buffer in EPSG:4326" is enforced
    here, once, for every tool that declares PROJECTED_METRIC.
    """
    if requirement is CrsRequirement.NONE:
        return None
    if crs is None or crs.kind is CrsKind.UNKNOWN:
        return (
            "Layer has no resolvable CRS. Run detect_crs or assign a CRS "
            "explicitly before this operation."
        )
    if requirement is CrsRequirement.PROJECTED_METRIC and not crs.is_metric():
        return (
            f"Operation requires a projected metric CRS but layer is {crs.srid} "
            f"({crs.kind.value}). Insert a 'reproject' step (e.g. to EPSG:5254 "
            f"TUREF/TM30 for western Turkey) before this tool."
        )
    if requirement is CrsRequirement.GEOGRAPHIC and not crs.is_geographic():
        return f"Operation requires a geographic CRS but layer is {crs.srid}."
    return None
