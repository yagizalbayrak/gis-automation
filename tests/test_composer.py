"""PlanComposer tests: the generative Composer against the deterministic
Critic, plus the Kutahya rental scenario end-to-end.

No LLM is ever called: scripted stubs play the model. What we test is the
validation cage around it - the same one bundled workflows live in.
"""
from __future__ import annotations

import copy
import json

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
        self.clarification_answers_seen: list[str | None] = []

    def compose(
        self, text, tool_catalog, recipes, feedback, *, profile=None,
        clarification_answer=None,
    ) -> dict:
        self.feedback_seen.append(feedback)
        self.clarification_answers_seen.append(clarification_answer)
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


def test_composed_park_centroid_plan_validates_and_executes(
    composer_factory, runner, ctx
) -> None:
    """Tier-1 gap S43: 'where is the center of each park'."""
    plan = {
        "name": "kutahya_park_centroids",
        "summary": "Find the centroid of each Kutahya park.",
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
                "id": "centroids",
                "tool": "centroid",
                "params": {"layer": "$steps.parks_metric.layer"},
            },
        ],
        "outputs": {"park_centroids": "$steps.centroids.layer"},
    }
    composer, _ = composer_factory(plan)

    composed = composer.compose("Kutahya'daki her parkin merkezini bul")
    outputs = runner.run_spec(composed.spec, {})

    centroids = ctx.read(outputs["park_centroids"])
    assert len(centroids) == 2
    assert (centroids.geometry.geom_type == "Point").all()


def test_composed_school_count_per_park_plan_validates_and_executes(
    composer_factory, runner, ctx
) -> None:
    """Tier-1 gap S35/S46: how many schools fall inside each park."""
    plan = {
        "name": "kutahya_schools_per_park",
        "summary": "Count schools inside each Kutahya park.",
        "steps": [
            {
                "id": "boundary",
                "tool": "fetch_osm_boundary",
                "params": {"place_name": "Kutahya, Turkey"},
            },
            {
                "id": "schools",
                "tool": "fetch_osm_features",
                "params": {
                    "boundary": "$steps.boundary.layer",
                    "key": "amenity",
                    "value": "school",
                },
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
                "id": "schools_metric",
                "tool": "reproject",
                "params": {"layer": "$steps.schools.layer", "target_srid": "EPSG:5254"},
            },
            {
                "id": "parks_metric",
                "tool": "reproject",
                "params": {"layer": "$steps.parks.layer", "target_srid": "EPSG:5254"},
            },
            {
                "id": "counts",
                "tool": "count_points_in_polygons",
                "params": {
                    "points": "$steps.schools_metric.layer",
                    "polygons": "$steps.parks_metric.layer",
                },
            },
        ],
        "outputs": {"parks_with_school_counts": "$steps.counts.layer"},
    }
    composer, _ = composer_factory(plan)

    composed = composer.compose("Kutahya'daki her parkin icinde kac okul var?")
    outputs = runner.run_spec(composed.spec, {})

    parks = ctx.read(outputs["parks_with_school_counts"])
    assert len(parks) == 2
    assert "point_count" in parks.columns
    # The demo school sits outside both park polygons - a real 0 count,
    # not a placeholder, is the correct answer here.
    assert int(parks["point_count"].sum()) == 0


def test_composed_scored_site_analysis_plan_validates_and_executes(
    composer_factory, runner, ctx
) -> None:
    """Site analysis increment: proximity constraints produce candidates;
    deterministic scoring then ranks them by area and nearest distances."""
    plan = {
        "name": "scored_rental_site_analysis",
        "summary": "Find and rank rental candidate areas near schools and main roads.",
        "steps": [
            {
                "id": "neighborhood",
                "tool": "fetch_osm_boundary",
                "params": {"place_name": "Evliya Celebi Mahallesi, Kutahya"},
            },
            {
                "id": "schools",
                "tool": "fetch_osm_features",
                "params": {
                    "boundary": "$steps.neighborhood.layer",
                    "key": "amenity",
                    "value": "school",
                },
            },
            {
                "id": "roads",
                "tool": "fetch_osm_features",
                "params": {"boundary": "$steps.neighborhood.layer", "key": "highway"},
            },
            {
                "id": "main_roads",
                "tool": "filter_by_attribute",
                "params": {
                    "layer": "$steps.roads.layer",
                    "field": "highway",
                    "in_values": ["primary", "secondary", "trunk"],
                },
            },
            {
                "id": "schools_metric",
                "tool": "reproject",
                "params": {"layer": "$steps.schools.layer", "target_srid": "EPSG:5254"},
            },
            {
                "id": "roads_metric",
                "tool": "reproject",
                "params": {
                    "layer": "$steps.main_roads.layer",
                    "target_srid": "EPSG:5254",
                },
            },
            {
                "id": "school_zone",
                "tool": "buffer_metric",
                "params": {"layer": "$steps.schools_metric.layer", "distance_m": 500.0},
            },
            {
                "id": "road_zone",
                "tool": "buffer_metric",
                "params": {"layer": "$steps.roads_metric.layer", "distance_m": 250.0},
            },
            {
                "id": "candidates",
                "tool": "intersect",
                "params": {
                    "layer": "$steps.school_zone.layer",
                    "other": "$steps.road_zone.layer",
                },
            },
            {
                "id": "areas",
                "tool": "calculate_area",
                "params": {"layer": "$steps.candidates.layer", "output_field": "area_m2"},
            },
            {
                "id": "school_distance",
                "tool": "nearest_neighbor_distance",
                "params": {
                    "layer": "$steps.areas.layer",
                    "other": "$steps.schools_metric.layer",
                    "output_field": "school_distance_m",
                },
            },
            {
                "id": "road_distance",
                "tool": "nearest_neighbor_distance",
                "params": {
                    "layer": "$steps.school_distance.layer",
                    "other": "$steps.roads_metric.layer",
                    "output_field": "road_distance_m",
                },
            },
            {
                "id": "scored",
                "tool": "score_candidates",
                "params": {
                    "layer": "$steps.road_distance.layer",
                    "criteria": [
                        {
                            "field": "school_distance_m",
                            "direction": "minimize",
                            "weight": 0.4,
                        },
                        {
                            "field": "road_distance_m",
                            "direction": "minimize",
                            "weight": 0.4,
                        },
                        {"field": "area_m2", "direction": "maximize", "weight": 0.2},
                    ],
                },
            },
            {
                "id": "display",
                "tool": "reproject",
                "params": {"layer": "$steps.scored.layer", "target_srid": "EPSG:4326"},
            },
        ],
        "outputs": {"ranked_sites": "$steps.display.layer"},
    }
    composer, _ = composer_factory(plan)

    composed = composer.compose("Rank rental sites near schools and main roads")
    outputs = runner.run_spec(composed.spec, {})

    ranked = ctx.read(outputs["ranked_sites"])
    assert len(ranked) >= 1
    assert "suitability_score" in ranked.columns
    assert "suitability_rank" in ranked.columns
    assert ranked["suitability_score"].between(0, 100).all()
    assert ranked.crs.to_epsg() == 4326


def test_recipe_store_matches_turkish_and_english(crs_info) -> None:
    store = RecipeStore()
    turkish = store.search("okula yakin kiralik ev icin uygun alan bul")
    assert any("PROXIMITY SITE SEARCH" in r for r in turkish)
    english = store.search("find sites near a school and main roads")
    assert any("PROXIMITY SITE SEARCH" in r for r in english)
    assert store.search("completely unrelated request about poetry") == []


def test_profile_line_is_injected_into_composer_user_message(monkeypatch) -> None:
    from types import SimpleNamespace

    from ageo.domain.value_objects.user_profile import UserProfile, UserRole
    from ageo.infrastructure.llm import litellm_composer
    from ageo.infrastructure.llm.litellm_composer import LiteLlmComposer

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        content = json.dumps({"steps": [], "summary": "no capability"})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    monkeypatch.setattr(litellm_composer.litellm, "completion", fake_completion)
    profile = UserProfile(role=UserRole.CIVIL_ENGINEER)
    LiteLlmComposer(model="test/model").compose(
        "x", [], [], None, profile=profile
    )
    user_content = captured["messages"][1]["content"]
    assert "role=civil_eng" in user_content


def test_profile_line_is_omitted_from_composer_when_none(monkeypatch) -> None:
    from types import SimpleNamespace

    from ageo.infrastructure.llm import litellm_composer
    from ageo.infrastructure.llm.litellm_composer import LiteLlmComposer

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        content = json.dumps({"steps": [], "summary": "no capability"})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    monkeypatch.setattr(litellm_composer.litellm, "completion", fake_completion)
    LiteLlmComposer(model="test/model").compose("x", [], [], None)
    user_content = captured["messages"][1]["content"]
    assert "USER role=" not in user_content


def _clarification_payload(recommended_value=111) -> dict:
    return {
        "clarification": {
            "reason": "0.001 degrees is not a fixed distance",
            "question": {"en": "Did you mean ~111 m?", "tr": "111 m mi demek istediniz?"},
            "options": [
                {
                    "value": recommended_value,
                    "label": {"en": "111 m", "tr": "111 m"},
                    "recommended": True,
                }
            ],
        }
    }


def test_clarification_payload_raises_composer_clarification_required(
    composer_factory,
) -> None:
    from ageo.application.agents.composer import ComposerClarificationRequired

    composer, llm = composer_factory(_clarification_payload())
    with pytest.raises(ComposerClarificationRequired) as excinfo:
        composer.compose("0.001 derece tampon olustur")
    question = excinfo.value.question
    assert question.question_type == "clarification"
    assert question.param == "clarification_answer"
    assert question.severity == "material"
    assert question.blocking is True
    assert question.text["en"] and question.text["tr"]
    assert len(question.options) == 1
    assert question.options[0].recommended is True
    assert question.options[0].value == 111
    assert llm.clarification_answers_seen == [None]


def test_clarification_answer_is_threaded_to_the_scripted_llm(composer_factory) -> None:
    composer, llm = composer_factory(RENTAL_SITE_SEARCH_PLAN)
    composer.compose(RENTAL_REQUEST, clarification_answer="111")
    assert llm.clarification_answers_seen == ["111"]


def test_second_clarification_after_answer_supplied_is_capped_to_refusal(
    composer_factory,
) -> None:
    """The model asking again despite an answer must not loop forever: the
    second clarification becomes an honest ComposerError, not another
    ComposerClarificationRequired."""
    composer, llm = composer_factory(_clarification_payload())
    with pytest.raises(ComposerError, match="plan_refused: 0.001 degrees is not a fixed distance"):
        composer.compose(RENTAL_REQUEST, clarification_answer="111")
    assert llm.clarification_answers_seen == ["111"]


def test_malformed_clarification_payload_is_sanitized_defensively(composer_factory) -> None:
    """Missing en/tr, non-bool recommended, non-list options must never
    raise a raw KeyError/TypeError - mirrors _to_decision() sanitization."""
    from ageo.application.agents.composer import ComposerClarificationRequired

    malformed = {
        "clarification": {
            "reason": "",
            "question": {"en": ""},  # missing tr
            "options": "not-a-list",
        }
    }
    composer, _ = composer_factory(malformed)
    with pytest.raises(ComposerClarificationRequired) as excinfo:
        composer.compose("belirsiz istek")
    question = excinfo.value.question
    assert question.text["en"]  # defaulted, never empty
    assert question.text["tr"]  # defaulted, never empty
    assert question.options == ()
