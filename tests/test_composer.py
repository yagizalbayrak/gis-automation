"""PlanComposer tests: the generative Composer against the deterministic
Critic, plus the Kutahya rental scenario end-to-end.

No LLM is ever called: scripted stubs play the model. What we test is the
validation cage around it - the same one bundled workflows live in.
"""
from __future__ import annotations

import copy

import pytest

from ageo.application.agents.composer import PlanComposer
from ageo.application.rag.store import RecipeStore
from ageo.application.tools.errors import ComposerError
from ageo.application.tools.registry import registry
from ageo.infrastructure.gis.demo import RENTAL_SITE_SEARCH_PLAN

RENTAL_REQUEST = (
    "Kutahya Evliya Celebi Mahallesi'nde okula 500 m, ana yollara 250 m "
    "mesafede kiralik ev icin uygun alanlari bul"
)


class ScriptedComposerLlm:
    """Plays the model: returns queued plans in order, records feedback."""

    def __init__(self, *plans: dict) -> None:
        self._plans = list(plans)
        self.calls = 0
        self.feedback_seen: list[str | None] = []

    def compose(self, text, tool_catalog, recipes, feedback) -> dict:
        self.feedback_seen.append(feedback)
        plan = self._plans[min(self.calls, len(self._plans) - 1)]
        self.calls += 1
        return plan


def _naive_plan() -> dict:
    """The classic geodetic mistake: buffering OSM data without reprojecting."""
    plan = copy.deepcopy(RENTAL_SITE_SEARCH_PLAN)
    plan["steps"] = [
        step for step in plan["steps"]
        if step["id"] not in ("schools_metric", "roads_metric")
    ]
    for step in plan["steps"]:
        if step["id"] == "school_zone":
            step["params"]["layer"] = "$steps.schools.layer"
        if step["id"] == "road_zone":
            step["params"]["layer"] = "$steps.main_roads.layer"
    return plan


@pytest.fixture
def composer_factory(crs_info):
    def build(*plans: dict) -> tuple[PlanComposer, ScriptedComposerLlm]:
        llm = ScriptedComposerLlm(*plans)
        return PlanComposer(llm, registry, crs_info, RecipeStore()), llm

    return build


def test_valid_plan_composes_first_try(composer_factory) -> None:
    composer, llm = composer_factory(RENTAL_SITE_SEARCH_PLAN)
    composed = composer.compose(RENTAL_REQUEST)
    assert composed.spec.name == "rental_site_search_kutahya"
    assert composed.attempts == 1
    assert composed.recipes_used > 0  # RAG-lite recipes matched the request
    assert llm.feedback_seen == [None]


def test_geodetically_naive_plan_is_rejected_then_fixed_via_feedback(
    composer_factory,
) -> None:
    """First attempt buffers EPSG:4326 data directly; the Critic rejects it
    and its error message becomes the retry feedback; the corrected plan
    passes. This is the Composer/Critic loop working as designed."""
    composer, llm = composer_factory(_naive_plan(), RENTAL_SITE_SEARCH_PLAN)
    composed = composer.compose(RENTAL_REQUEST)
    assert composed.attempts == 2
    assert llm.calls == 2
    assert llm.feedback_seen[1] is not None
    assert "metric" in llm.feedback_seen[1]


def test_persistently_invalid_plans_raise_composer_error(composer_factory) -> None:
    composer, llm = composer_factory(_naive_plan())
    with pytest.raises(ComposerError, match="metric"):
        composer.compose(RENTAL_REQUEST)
    assert llm.calls == 2  # exactly one retry, then give up - cost control


def test_hallucinated_tool_is_rejected(composer_factory) -> None:
    plan = copy.deepcopy(RENTAL_SITE_SEARCH_PLAN)
    plan["steps"][0]["tool"] = "download_the_internet"
    composer, _ = composer_factory(plan)
    with pytest.raises(ComposerError, match="unknown tool"):
        composer.compose(RENTAL_REQUEST)


def test_oversized_plan_is_rejected_before_validation(composer_factory) -> None:
    plan = copy.deepcopy(RENTAL_SITE_SEARCH_PLAN)
    plan["steps"] = plan["steps"] * 4  # 40 steps
    composer, _ = composer_factory(plan)
    with pytest.raises(ComposerError, match="limit"):
        composer.compose(RENTAL_REQUEST)


def test_composed_plan_executes_end_to_end(composer_factory, runner, ctx) -> None:
    """The full vision: NL request -> composed plan -> guarded execution ->
    suitability area. Demo OSM data is built so school and main-road
    buffers genuinely intersect."""
    composer, _ = composer_factory(RENTAL_SITE_SEARCH_PLAN)
    composed = composer.compose(RENTAL_REQUEST)

    outputs = runner.run_spec(composed.spec, {})

    suitable = ctx.read(outputs["suitable_area"])
    assert len(suitable) >= 1
    assert suitable.crs.to_epsg() == 4326
    assert (suitable.geometry.geom_type.isin(["Polygon", "MultiPolygon"])).all()

    main_roads = ctx.read(outputs["main_roads"])
    assert set(main_roads["highway"]) <= {"primary", "secondary", "trunk"}
    assert len(main_roads) == 2  # Ataturk (primary) + Cumhuriyet (secondary)


def test_composed_area_statistics_plan_validates_and_executes(
    composer_factory, runner, ctx
) -> None:
    plan = {
        "name": "kutahya_park_area_statistics",
        "summary": "Calculate Kutahya park areas in hectares.",
        "steps": [
            {
                "id": "boundary",
                "tool": "fetch_osm_boundary",
                "params": {"place_name": "Kutahya, Turkey"},
            },
            {
                "id": "parks",
                "tool": "fetch_osm_features",
                "params": {
                    "boundary": "$steps.boundary.layer",
                    "key": "leisure",
                    "value": "park",
                },
            },
            {
                "id": "parks_metric",
                "tool": "reproject",
                "params": {"layer": "$steps.parks.layer", "target_srid": "EPSG:5254"},
            },
            {
                "id": "areas",
                "tool": "calculate_area",
                "params": {
                    "layer": "$steps.parks_metric.layer",
                    "output_field": "area_ha",
                    "unit": "ha",
                },
            },
        ],
        "outputs": {
            "parks_with_area": "$steps.areas.layer",
            "area_table": "$steps.areas.table",
        },
    }
    composer, _ = composer_factory(plan)

    composed = composer.compose(
        "Kütahya'daki her parkın alanını hektar cinsinden hesapla ve listele"
    )
    outputs = runner.run_spec(composed.spec, {})

    parks = ctx.read(outputs["parks_with_area"])
    assert "area_ha" in parks.columns
    assert len(outputs["area_table"]) == len(parks)
    assert all(row["area_ha"] > 0 for row in outputs["area_table"])


def test_composed_length_statistics_plan_validates_and_executes(
    composer_factory, runner, ctx
) -> None:
    plan = {
        "name": "kutahya_cycleway_length",
        "summary": "Calculate total Kutahya cycleway length in kilometres.",
        "steps": [
            {
                "id": "boundary",
                "tool": "fetch_osm_boundary",
                "params": {"place_name": "Kutahya, Turkey"},
            },
            {
                "id": "cycleways",
                "tool": "fetch_osm_features",
                "params": {
                    "boundary": "$steps.boundary.layer",
                    "key": "highway",
                    "value": "cycleway",
                },
            },
            {
                "id": "cycleways_metric",
                "tool": "reproject",
                "params": {
                    "layer": "$steps.cycleways.layer",
                    "target_srid": "EPSG:5254",
                },
            },
            {
                "id": "lengths",
                "tool": "calculate_length",
                "params": {
                    "layer": "$steps.cycleways_metric.layer",
                    "output_field": "length_km",
                    "unit": "km",
                },
            },
        ],
        "outputs": {
            "cycleways_with_length": "$steps.lengths.layer",
            "length_table": "$steps.lengths.table",
            "total_length_m": "$steps.lengths.total_length_m",
        },
    }
    composer, _ = composer_factory(plan)

    composed = composer.compose("How many kilometres of cycleway does Kutahya have?")
    outputs = runner.run_spec(composed.spec, {})

    cycleways = ctx.read(outputs["cycleways_with_length"])
    assert "length_km" in cycleways.columns
    assert outputs["total_length_m"] > 0
    assert len(outputs["length_table"]) == len(cycleways)


def test_recipe_store_matches_turkish_and_english(crs_info) -> None:
    store = RecipeStore()
    turkish = store.search("okula yakin kiralik ev icin uygun alan bul")
    assert any("PROXIMITY SITE SEARCH" in r for r in turkish)
    english = store.search("find sites near a school and main roads")
    assert any("PROXIMITY SITE SEARCH" in r for r in english)
    assert store.search("completely unrelated request about poetry") == []
