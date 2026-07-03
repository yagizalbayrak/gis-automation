"""Delivery packaging: package_outputs.

Writes a set of workspace layers to a directory in a common format and
produces a machine-readable manifest (CRS, feature counts, geometry
types, timestamps) - the reproducibility artifact the brief requires in
every delivery.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ageo.application.tools.contract import (
    CrsEffect,
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import ToolExecutionError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement

_EXTENSIONS: dict[str, str] = {
    "GPKG": ".gpkg",
    "GeoJSON": ".geojson",
    "ESRI Shapefile": ".shp",
}


class PackageOutputsInput(StrictModel):
    layers: tuple[LayerRef, ...] = Field(min_length=1)
    names: tuple[str, ...] = Field(min_length=1, description="One name per layer")
    directory: str = Field(min_length=1)
    format: Literal["GPKG", "GeoJSON", "ESRI Shapefile"] = "GPKG"

    @model_validator(mode="after")
    def _names_match_layers(self) -> "PackageOutputsInput":
        if len(self.names) != len(self.layers):
            raise ValueError(
                f"names ({len(self.names)}) and layers ({len(self.layers)}) "
                f"must have the same length"
            )
        if len(set(self.names)) != len(self.names):
            raise ValueError("layer names in a package must be unique")
        return self


class PackageOutputsOutput(StrictModel):
    directory: str
    files: tuple[str, ...]
    manifest_path: str


@registry.register
class PackageOutputs(Tool[PackageOutputsInput, PackageOutputsOutput]):
    Input = PackageOutputsInput
    Output = PackageOutputsOutput
    spec = ToolSpec(
        name="package_outputs",
        summary="Export layers to a delivery directory with a JSON manifest "
                "(CRS, counts, geometry types). Every layer must have a "
                "defined CRS.",
        input_requirements={
            "layers": InputRequirement(crs=CrsRequirement.ANY_DEFINED)
        },
        crs_effect=CrsEffect.NONE,
        failure_modes=("write_failed",),
    )

    def run(self, params: PackageOutputsInput, ctx: ToolContext) -> PackageOutputsOutput:
        target_dir = Path(params.directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        extension = _EXTENSIONS[params.format]

        files: list[str] = []
        manifest_layers: list[dict] = []
        for ref, name in zip(params.layers, params.names):
            gdf = ctx.read(ref)
            crs = ctx.crs_of(ref)
            target = target_dir / f"{name}{extension}"
            try:
                gdf.to_file(target, driver=params.format)
            except Exception as exc:
                raise ToolExecutionError(f"write_failed: {target}: {exc}") from exc
            files.append(str(target))
            manifest_layers.append({
                "name": name,
                "file": target.name,
                "srid": crs.srid if crs else None,
                "crs_name": crs.name if crs else None,
                "feature_count": len(gdf),
                "geometry_types": sorted(gdf.geometry.geom_type.dropna().unique()),
            })

        manifest = {
            "generator": "ageo",
            "created_at": datetime.now(UTC).isoformat(),
            "format": params.format,
            "layers": manifest_layers,
        }
        manifest_path = target_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        return PackageOutputsOutput(
            directory=str(target_dir),
            files=tuple(files),
            manifest_path=str(manifest_path),
        )
