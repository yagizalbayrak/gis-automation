"""Bundled deterministic workflow definitions (Phase 1).

These are the JSON-equivalent records the planner selects from. They are
plain data; registering them proves them structurally and geodetically
valid at startup.
"""
from __future__ import annotations

from ageo.application.workflows.registry import WorkflowRegistry
from ageo.application.workflows.spec import WorkflowParam, WorkflowSpec, WorkflowStep

ROAD_FETCH_AND_BUFFER = WorkflowSpec(
    name="road_fetch_and_buffer",
    summary="Fetch OSM roads for a place, filter selected streets by name, "
            "buffer them by N metres in a metric CRS, return display-ready "
            "EPSG:4326 layers.",
    nl_patterns=(
        "yollari haritaya cek",
        "buffer uygula",
        "fetch roads",
        "buffer selected streets",
    ),
    params=(
        WorkflowParam(name="place", kind="string",
                      description="Place name, e.g. 'Kutahya, Turkey'"),
        WorkflowParam(name="street_name", kind="string",
                      description="Street name filter, e.g. 'Ataturk Caddesi'"),
        WorkflowParam(name="buffer_m", kind="float",
                      description="Buffer distance in metres"),
        WorkflowParam(
            name="target_srid", kind="srid_metric", required=False,
            default="EPSG:5254",
            description="Projected metric CRS for the buffer. Default TUREF/TM30 "
                        "suits western Turkey; pass a location-appropriate CRS "
                        "elsewhere (the planner should call suggest_metric_crs).",
        ),
    ),
    steps=(
        WorkflowStep(id="boundary", tool="fetch_osm_boundary",
                     params={"place_name": "$params.place"}),
        WorkflowStep(id="roads", tool="fetch_osm_features",
                     params={"boundary": "$steps.boundary.layer", "key": "highway",
                             # this workflow filters by street name next, so
                             # only named roads are worth transferring
                             "require_tags": ["name"]}),
        WorkflowStep(id="selected", tool="filter_by_attribute",
                     params={"layer": "$steps.roads.layer", "field": "name",
                             "contains": "$params.street_name"}),
        WorkflowStep(id="metric", tool="reproject",
                     params={"layer": "$steps.selected.layer",
                             "target_srid": "$params.target_srid"}),
        WorkflowStep(id="buffered", tool="buffer_metric",
                     params={"layer": "$steps.metric.layer",
                             "distance_m": "$params.buffer_m"}),
        WorkflowStep(id="display", tool="reproject",
                     params={"layer": "$steps.buffered.layer",
                             "target_srid": "EPSG:4326"}),
    ),
    outputs={
        "all_roads": "$steps.roads.layer",
        "selected_roads": "$steps.selected.layer",
        "buffered": "$steps.display.layer",
    },
)

PREFLIGHT_QUALITY_CHECK = WorkflowSpec(
    name="preflight_quality_check",
    summary="Load a vector file, report its CRS facts and geometry quality "
            "(invalid/empty/duplicate counts) without modifying anything.",
    nl_patterns=("quality check", "veri kontrolu", "check my file", "validate data"),
    params=(
        WorkflowParam(name="path", kind="string", description="Input file path"),
    ),
    steps=(
        WorkflowStep(id="load", tool="load_vector", params={"path": "$params.path"}),
        WorkflowStep(id="crs", tool="detect_crs", params={"layer": "$steps.load.layer"}),
        WorkflowStep(id="quality", tool="validate_geometry",
                     params={"layer": "$steps.load.layer"}),
    ),
    outputs={"layer": "$steps.load.layer"},
)

CRS_NORMALIZATION = WorkflowSpec(
    name="crs_normalization",
    summary="Load a vector file, transform it to a target CRS and export it "
            "as a delivery package with a manifest.",
    nl_patterns=(
        "koordinat sistemine donustur",
        "reproject my file",
        "convert crs",
        "transform to epsg",
    ),
    params=(
        WorkflowParam(name="path", kind="string", description="Input file path"),
        WorkflowParam(name="target_srid", kind="srid",
                      description="Target CRS, e.g. 'EPSG:5254'"),
        WorkflowParam(name="output_dir", kind="string",
                      description="Delivery directory for the package"),
        WorkflowParam(name="output_name", kind="string", required=False,
                      default="normalized", description="Output layer name"),
    ),
    steps=(
        WorkflowStep(id="load", tool="load_vector", params={"path": "$params.path"}),
        WorkflowStep(id="transformed", tool="reproject",
                     params={"layer": "$steps.load.layer",
                             "target_srid": "$params.target_srid"}),
        WorkflowStep(id="package", tool="package_outputs",
                     params={"layers": ["$steps.transformed.layer"],
                             "names": ["$params.output_name"],
                             "directory": "$params.output_dir"}),
    ),
    outputs={"layer": "$steps.transformed.layer"},
)

BUNDLED_WORKFLOWS = (ROAD_FETCH_AND_BUFFER, PREFLIGHT_QUALITY_CHECK, CRS_NORMALIZATION)


def register_bundled(registry: WorkflowRegistry) -> None:
    for spec in BUNDLED_WORKFLOWS:
        registry.register(spec)
