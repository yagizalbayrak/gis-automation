"""Interface-layer tests: the full workbench loop over HTTP.

Natural language in -> workflow selection -> guarded execution -> trace,
GeoJSON preview and HIL question flow out. OSM is faked; everything runs
offline.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from ageo.infrastructure.gis.demo import DemoComposerLlm, RENTAL_SITE_SEARCH_PLAN
from ageo.interface.api.app import create_app
from conftest import FakeOsmGateway

TURKISH_COMMAND = 'Kutahya\'daki "Ataturk Caddesi" icin 25 m buffer uygula'
RENTAL_COMMAND = (
    "Kutahya Evliya Celebi Mahallesi'nde okula 500 m, ana yollara 250 m "
    "mesafede kiralik ev icin uygun alanlari bul"
)
SCORED_RENTAL_COMMAND = (
    "Kutahya Evliya Celebi Mahallesi'nde okula ve ana yollara yakin "
    "kiralik ev aday alanlarini puanla ve sirala"
)


def _cycleway_length_plan() -> dict:
    return {
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


class CyclewayLengthComposerLlm:
    def compose(
        self, text, tool_catalog, recipes, feedback, *, profile=None,
        clarification_answer=None,
    ) -> dict:
        return _cycleway_length_plan()


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(
        osm_gateway=FakeOsmGateway(),
        upload_dir=str(tmp_path / "uploads"),
        composer_llm=DemoComposerLlm(),
        settings_path=str(tmp_path / "llm_settings.json"),
        profile_path=str(tmp_path / "user_profile.json"),
    )
    return TestClient(app)


def _run_task(client: TestClient, text: str, params: dict | None = None) -> dict:
    response = client.post("/tasks?wait=true", json={"text": text, "params": params or {}})
    assert response.status_code == 200, response.text
    return response.json()


def test_turkish_command_end_to_end(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    assert task["status"] == "succeeded"
    assert task["workflow"] == "road_fetch_and_buffer"
    assert set(task["outputs"]) == {"all_roads", "selected_roads", "buffered"}
    assert task["error"] is None


def test_layer_endpoint_serves_display_crs_geojson(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    response = client.get(f"/tasks/{task['task_id']}/layers/buffered")
    assert response.status_code == 200
    layer = response.json()
    assert layer["display_srid"] == "EPSG:4326"
    assert layer["feature_count"] == 1
    features = layer["feature_collection"]["features"]
    assert features[0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    # display payload must be lon/lat magnitude, not projected metres
    lon = features[0]["geometry"]["coordinates"][0][0][0]
    assert -180 <= lon <= 180


def test_trace_is_a_complete_process_log(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    trace = client.get(f"/tasks/{task['task_id']}/trace").json()
    phases = [event["phase"] for event in trace]
    assert phases[0] == "workflow_started"
    assert phases[-1] == "workflow_finished"
    assert "guard_passed" in phases
    # the trace must show which CRS the buffer actually ran in
    buffer_guards = [
        e for e in trace
        if e["phase"] == "guard_passed" and e["subject"] == "buffer_metric"
    ]
    assert buffer_guards[0]["detail"]["crs"] == "EPSG:5254"


def test_trace_events_carry_the_workflow_step_id(client) -> None:
    """Progressive map rendering needs to label mid-run layers by step -
    every tool-scoped trace event from a workflow run must carry step_id."""
    task = _run_task(client, TURKISH_COMMAND)
    trace = client.get(f"/tasks/{task['task_id']}/trace").json()
    tool_events = [
        e for e in trace
        if e["phase"] in ("tool_started", "tool_finished", "guard_passed")
    ]
    assert tool_events  # sanity: the workflow actually ran tools
    assert all(e["detail"].get("step_id") for e in tool_events)


def test_workspace_layer_endpoint_serves_intermediate_layers(client) -> None:
    """The workspace endpoint must serve ANY layer that ever existed in the
    task's workspace, not just a named final output - this is what lets the
    UI preview a layer mid-run, before the workflow finishes."""
    task = _run_task(client, TURKISH_COMMAND)
    trace = client.get(f"/tasks/{task['task_id']}/trace").json()
    finished = [
        e for e in trace
        if e["phase"] == "tool_finished" and e["subject"] == "buffer_metric"
    ]
    layer_id = finished[0]["detail"]["result"]["layer"]["layer_id"]

    response = client.get(f"/tasks/{task['task_id']}/workspace/{layer_id}")
    assert response.status_code == 200
    layer = response.json()
    assert layer["display_srid"] == "EPSG:4326"
    assert layer["feature_count"] == 1

    # Same underlying layer as the named "buffered" output.
    named = client.get(f"/tasks/{task['task_id']}/layers/buffered").json()
    assert layer["feature_collection"] == named["feature_collection"]


def test_workspace_layer_endpoint_404_for_unknown_layer(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    response = client.get(f"/tasks/{task['task_id']}/workspace/no_such_layer_9999")
    assert response.status_code == 404


def test_workspace_layer_endpoint_404_for_unknown_task(client) -> None:
    response = client.get("/tasks/no-such-task/workspace/anything")
    assert response.status_code == 404


def test_needs_input_flow(client) -> None:
    first = _run_task(client, "Kutahya'daki tum yollari haritaya cek")
    assert first["status"] == "needs_input"
    assert set(first["missing_params"]) == {"street_name", "buffer_m"}

    answered = _run_task(
        client,
        "Kutahya'daki tum yollari haritaya cek",
        params={"street_name": "Cumhuriyet", "buffer_m": 10.0},
    )
    assert answered["status"] == "succeeded"


def test_needs_input_carries_structured_questions_and_ledger(client) -> None:
    task = _run_task(client, "Kutahya'daki tum yollari haritaya cek")
    assert task["status"] == "needs_input"
    assert {q["param"] for q in task["questions"]} == {"street_name", "buffer_m"}
    for question in task["questions"]:
        assert question["question_type"] == "parameter"
        assert question["severity"] == "critical"
        assert question["blocking"] is True
        assert question["text"]["en"]
        assert question["text"]["tr"]
        assert question["kind"]
    # The ledger is computed even on a needs_input response: the default
    # guided profile turns the target_srid spec default into an assumption.
    assert [a["param"] for a in task["assumptions"]] == ["target_srid"]
    assert task["missing_params"] == [q["param"] for q in task["questions"]]


def test_strict_confirm_turns_spec_default_into_confirmation(client) -> None:
    client.put("/settings/profile", json={
        "role": "gis_specialist",
        "gis_level": "advanced",
        "crs_awareness": "high",
        "autonomy_preference": "strict_confirm",
        "explanation_depth": "technical_audit",
        "language": "en",
    })
    first = _run_task(client, TURKISH_COMMAND)
    assert first["status"] == "needs_input"
    assert first["missing_params"] == ["target_srid"]
    assert len(first["questions"]) == 1
    question = first["questions"][0]
    assert question["question_type"] == "risk_confirmation"
    assert question["default_if_skipped"] == "EPSG:5254"
    assert question["options"][0]["recommended"] is True

    answered = _run_task(client, TURKISH_COMMAND, params={"target_srid": "EPSG:5254"})
    assert answered["status"] == "succeeded"
    assert answered["assumptions"] == []


def test_guided_run_records_assumption_visible_in_response_and_report(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    assert task["status"] == "succeeded"
    assert len(task["assumptions"]) == 1
    assumption = task["assumptions"][0]
    assert assumption["param"] == "target_srid"
    assert assumption["value"] == "EPSG:5254"
    assert assumption["source"] == "spec_default"

    english = client.get(f"/tasks/{task['task_id']}/report").json()
    assert "## Assumptions" in english["report"]
    assert "EPSG:5254" in english["report"]
    turkish = client.get(f"/tasks/{task['task_id']}/report?lang=tr").json()
    assert "## Varsayimlar" in turkish["report"]
    plain = client.get(f"/tasks/{task['task_id']}/report?depth=plain").json()
    assert "## Assumptions" in plain["report"]


def test_composed_task_bypasses_clarifier(client) -> None:
    # DemoComposerLlm never emits a clarification shape, so this composed
    # task has nothing to ask - unlike the tests below, which use a fake
    # that does clarify.
    task = _run_task(client, RENTAL_COMMAND)
    assert task["status"] == "succeeded"
    assert task["questions"] == []
    assert task["assumptions"] == []


class ClarifyingThenPlanComposerLlm:
    """First call returns a clarification (mirrors the S26 degree/metre
    trap); once a clarification_answer is supplied, returns the reference
    rental plan."""

    def compose(
        self, text, tool_catalog, recipes, feedback, *, profile=None,
        clarification_answer=None,
    ) -> dict:
        if clarification_answer is None:
            return {
                "clarification": {
                    "reason": "buffer distance given in degrees, not metres",
                    "question": {
                        "en": "Did you mean roughly 111 m?",
                        "tr": "Yaklasik 111 m mi demek istediniz?",
                    },
                    "options": [
                        {"value": 111, "label": {"en": "111 m", "tr": "111 m"}, "recommended": True}
                    ],
                }
            }
        return RENTAL_SITE_SEARCH_PLAN


def _client_with_composer(tmp_path, composer_llm) -> TestClient:
    app = create_app(
        osm_gateway=FakeOsmGateway(),
        upload_dir=str(tmp_path / "uploads"),
        composer_llm=composer_llm,
        settings_path=str(tmp_path / "llm_settings.json"),
        profile_path=str(tmp_path / "user_profile.json"),
    )
    return TestClient(app)


def test_composer_clarification_needs_input_under_guided(tmp_path) -> None:
    client = _client_with_composer(tmp_path, ClarifyingThenPlanComposerLlm())
    task = _run_task(client, RENTAL_COMMAND)
    assert task["status"] == "needs_input"
    assert task["mode"] == "composed"
    assert task["missing_params"] == ["clarification_answer"]
    assert len(task["questions"]) == 1
    question = task["questions"][0]
    assert question["question_type"] == "clarification"
    assert question["param"] == "clarification_answer"
    assert question["text"]["en"] and question["text"]["tr"]
    assert question["options"][0]["recommended"] is True

    answered = _run_task(client, RENTAL_COMMAND, params={"clarification_answer": "111"})
    assert answered["status"] == "succeeded"
    assert answered["mode"] == "composed"


def test_composer_clarification_needs_input_under_strict_confirm(tmp_path) -> None:
    client = _client_with_composer(tmp_path, ClarifyingThenPlanComposerLlm())
    client.put("/settings/profile", json={
        "role": "gis_specialist",
        "gis_level": "advanced",
        "crs_awareness": "high",
        "autonomy_preference": "strict_confirm",
        "explanation_depth": "technical_audit",
        "language": "en",
    })
    task = _run_task(client, RENTAL_COMMAND)
    assert task["status"] == "needs_input"
    assert task["questions"][0]["question_type"] == "clarification"


def test_composer_clarification_auto_resolves_under_autonomous(tmp_path) -> None:
    client = _client_with_composer(tmp_path, ClarifyingThenPlanComposerLlm())
    client.put("/settings/profile", json={
        "role": "gis_specialist",
        "gis_level": "advanced",
        "crs_awareness": "high",
        "autonomy_preference": "autonomous",
        "explanation_depth": "technical_audit",
        "language": "en",
    })
    task = _run_task(client, RENTAL_COMMAND)
    assert task["status"] == "succeeded"
    assert task["mode"] == "composed"
    assert len(task["assumptions"]) == 1
    assumption = task["assumptions"][0]
    assert assumption["param"] == "clarification_answer"
    assert assumption["value"] == 111
    assert assumption["source"] == "composer_recommended"


def test_unmatched_request(client) -> None:
    task = _run_task(client, "write me a poem about maps")
    assert task["status"] == "unmatched"
    assert task["workflow"] is None


def test_composed_rental_scenario_end_to_end(client) -> None:
    """No registered workflow matches, so the composer builds, validates and
    executes a multi-criteria site-search plan."""
    task = _run_task(client, RENTAL_COMMAND)
    assert task["status"] == "succeeded"
    assert task["mode"] == "composed"
    assert task["workflow"] == "rental_site_search_kutahya"
    assert len(task["plan"]) == 10  # the validated chain is visible to the UI
    assert {"suitable_area", "schools", "main_roads"} <= set(task["outputs"])

    layer = client.get(f"/tasks/{task['task_id']}/layers/suitable_area").json()
    assert layer["display_srid"] == "EPSG:4326"
    assert layer["feature_count"] >= 1

    trace = client.get(f"/tasks/{task['task_id']}/trace").json()
    buffer_guards = [
        e for e in trace
        if e["phase"] == "guard_passed" and e["subject"] == "buffer_metric"
    ]
    # both buffers provably ran in the metric CRS, composed plan or not
    assert {g["detail"]["crs"] for g in buffer_guards} == {"EPSG:5254"}


def test_composed_scored_rental_scenario_end_to_end(client) -> None:
    task = _run_task(client, SCORED_RENTAL_COMMAND)
    assert task["status"] == "succeeded"
    assert task["mode"] == "composed"
    assert task["workflow"] == "scored_rental_site_analysis"
    assert len(task["plan"]) == 14
    assert {"ranked_sites", "schools", "main_roads"} <= set(task["outputs"])

    layer = client.get(f"/tasks/{task['task_id']}/layers/ranked_sites").json()
    assert layer["display_srid"] == "EPSG:4326"
    assert layer["feature_count"] >= 1
    properties = layer["feature_collection"]["features"][0]["properties"]
    assert "suitability_score" in properties
    assert "suitability_rank" in properties


def test_composed_scalar_and_table_results_are_exposed(tmp_path) -> None:
    app = create_app(
        osm_gateway=FakeOsmGateway(),
        upload_dir=str(tmp_path / "uploads"),
        composer_llm=CyclewayLengthComposerLlm(),
        settings_path=str(tmp_path / "llm_settings.json"),
        profile_path=str(tmp_path / "user_profile.json"),
    )
    client = TestClient(app)

    task = _run_task(client, "How many kilometres of cycleway does Kutahya have?")

    assert task["status"] == "succeeded"
    assert set(task["outputs"]) == {"cycleways_with_length"}
    assert task["results"]["total_length_m"] > 0
    assert task["results"]["length_table"][0]["length_km"] > 0


def test_runtime_failure_is_reported_with_explanation(client) -> None:
    task = _run_task(client, "run a quality check on /nonexistent/data.shp")
    assert task["status"] == "failed"
    assert "file_not_found" in task["error"]


def test_upload_then_quality_check(client, tmp_path) -> None:
    import geopandas as gpd
    from shapely.geometry import Polygon

    source = tmp_path / "parcels.geojson"
    gpd.GeoDataFrame(
        {"name": ["p1"]},
        geometry=[Polygon([(29.9, 39.4), (30.0, 39.4), (30.0, 39.5), (29.9, 39.5)])],
        crs="EPSG:4326",
    ).to_file(source, driver="GeoJSON")

    with source.open("rb") as fh:
        uploaded = client.post(
            "/uploads", files={"file": ("parcels.geojson", fh, "application/geo+json")}
        ).json()
    assert uploaded["filename"] == "parcels.geojson"

    task = _run_task(client, f"run a quality check on {uploaded['path']}")
    assert task["status"] == "succeeded"
    assert task["workflow"] == "preflight_quality_check"


def test_sse_stream_replays_and_terminates(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    events: list[str] = []
    done = False
    with client.stream("GET", f"/tasks/{task['task_id']}/events") as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(line.removeprefix("data: "))
            if line.startswith("event: done"):
                done = True
    assert done
    first = json.loads(events[0])
    assert first["phase"] == "workflow_started"


def test_catalog_lists_workflows_and_tools(client) -> None:
    catalog = client.get("/catalog").json()
    workflow_names = {w["name"] for w in catalog["workflows"]}
    assert "road_fetch_and_buffer" in workflow_names
    assert len(catalog["tools"]) >= 16


def test_report_endpoint_english_and_turkish(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    english = client.get(f"/tasks/{task['task_id']}/report").json()
    assert "Selected workflow: road_fetch_and_buffer" in english["report"]
    assert "EPSG:5254" in english["report"]
    turkish = client.get(f"/tasks/{task['task_id']}/report?lang=tr").json()
    assert "Islem raporu" in turkish["report"]


def test_report_endpoint_accepts_explicit_depth(client) -> None:
    task = _run_task(client, TURKISH_COMMAND)
    plain = client.get(f"/tasks/{task['task_id']}/report?depth=plain").json()
    assert plain["depth"] == "plain"
    assert "## Executed steps" not in plain["report"]

    steps = client.get(f"/tasks/{task['task_id']}/report").json()
    assert steps["depth"] == "steps"
    assert "## Executed steps" in steps["report"]


def test_report_endpoint_defaults_depth_from_saved_profile(client) -> None:
    client.put("/settings/profile", json={
        "role": "gis_specialist",
        "gis_level": "advanced",
        "crs_awareness": "high",
        "autonomy_preference": "guided",
        "explanation_depth": "plain_language",
        "language": "tr",
    })
    task = _run_task(client, TURKISH_COMMAND)
    report = client.get(f"/tasks/{task['task_id']}/report").json()
    assert report["depth"] == "plain"
    assert report["lang"] == "tr"
    assert "## Executed steps" not in report["report"]


def test_web_ui_is_served(client) -> None:
    """Serve the React build when present, otherwise keep APIs testable with
    a clear fallback message for fresh clones that have not run npm build."""
    index = client.get("/")
    if index.status_code == 503:
        assert "Frontend not built yet" in index.text
        return
    assert index.status_code == 200
    assert "Autonomous GIS Workbench" in index.text
    assert "/assets/" in index.text
    asset_path = re.search(r'(/assets/index-[^"\']+\.js)', index.text)
    assert asset_path, "built index.html should reference a hashed JS bundle"
    assert client.get(asset_path.group(1)).status_code == 200


def test_unknown_task_and_layer_return_404(client) -> None:
    assert client.get("/tasks/nope").status_code == 404
    task = _run_task(client, TURKISH_COMMAND)
    assert client.get(f"/tasks/{task['task_id']}/layers/ghost").status_code == 404
