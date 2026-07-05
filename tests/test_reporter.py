"""Reporter tests: the process report must state workflow, steps, CRS
decisions and outputs - in English and Turkish - from the trace alone."""
from __future__ import annotations

from ageo.application.agents.reporter import ProcessReporter
from ageo.application.tools.contract import LayerRef


def _run_mvp(runner, trace):
    outputs = runner.run(
        "road_fetch_and_buffer",
        {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0},
    )
    return outputs, trace.events


def test_english_report_contains_the_facts(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    report = ProcessReporter().report(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={"place": "Kutahya", "buffer_m": 25.0},
        status="succeeded",
        events=events,
        outputs={k: v.layer_id for k, v in outputs.items() if isinstance(v, LayerRef)},
        lang="en",
    )
    assert "Selected workflow: road_fetch_and_buffer" in report
    assert "buffer_metric" in report
    assert "EPSG:5254" in report          # the CRS decision is in the report
    assert "## Outputs" in report
    assert "buffered" in report


def test_turkish_report_uses_turkish_labels(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    report = ProcessReporter().report(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={},
        status="succeeded",
        events=events,
        outputs={},
        lang="tr",
    )
    assert "Islem raporu" in report
    assert "Secilen is akisi" in report
    assert "Durum: basarili" in report


def test_default_depth_matches_explicit_steps_depth(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    kwargs = dict(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={"place": "Kutahya", "buffer_m": 25.0},
        status="succeeded",
        events=events,
        outputs={k: v.layer_id for k, v in outputs.items() if isinstance(v, LayerRef)},
        lang="en",
    )
    default_report = ProcessReporter().report(**kwargs)
    steps_report = ProcessReporter().report(**kwargs, depth="steps")
    assert default_report == steps_report


def test_plain_depth_omits_steps_params_and_crs(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    report = ProcessReporter().report(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={"place": "Kutahya", "buffer_m": 25.0},
        status="succeeded",
        events=events,
        outputs={k: v.layer_id for k, v in outputs.items() if isinstance(v, LayerRef)},
        lang="en",
        depth="plain",
    )
    assert "## Executed steps" not in report
    assert "Parameters:" not in report
    assert "## CRS decisions" not in report
    assert "Selected workflow: road_fetch_and_buffer" in report
    assert "## Outputs" in report


_SAMPLE_ASSUMPTION = {
    "param": "target_srid",
    "value": "EPSG:5254",
    "source": "spec_default",
    "reason": "workflow default",
    "text": {
        "en": "Assumed target_srid = EPSG:5254 (workflow default).",
        "tr": "target_srid = EPSG:5254 varsayildi (is akisi varsayilani).",
    },
}


def test_assumptions_section_renders_at_plain_depth(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    report = ProcessReporter().report(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={"place": "Kutahya", "buffer_m": 25.0},
        status="succeeded",
        events=events,
        outputs={k: v.layer_id for k, v in outputs.items() if isinstance(v, LayerRef)},
        lang="en",
        depth="plain",
        assumptions=[_SAMPLE_ASSUMPTION],
    )
    assert "## Assumptions" in report
    assert "Assumed target_srid = EPSG:5254 (workflow default)." in report
    assert "## Executed steps" not in report


def test_assumptions_section_uses_turkish_label_and_text(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    report = ProcessReporter().report(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={},
        status="succeeded",
        events=events,
        outputs={},
        lang="tr",
        assumptions=[_SAMPLE_ASSUMPTION],
    )
    assert "## Varsayimlar" in report
    assert "target_srid = EPSG:5254 varsayildi (is akisi varsayilani)." in report


def test_no_assumptions_section_when_empty(runner, trace) -> None:
    outputs, events = _run_mvp(runner, trace)
    kwargs = dict(
        text="buffer Ataturk",
        workflow="road_fetch_and_buffer",
        params={},
        status="succeeded",
        events=events,
        outputs={},
        lang="en",
    )
    assert "## Assumptions" not in ProcessReporter().report(**kwargs, assumptions=None)
    assert "## Assumptions" not in ProcessReporter().report(**kwargs, assumptions=[])
    assert "## Assumptions" not in ProcessReporter().report(**kwargs)


def test_failed_task_report_carries_error(runner, trace) -> None:
    report = ProcessReporter().report(
        text="check /missing.shp",
        workflow="preflight_quality_check",
        params={"path": "/missing.shp"},
        status="failed",
        events=trace.events,
        outputs={},
        error="file_not_found: /missing.shp",
        lang="en",
    )
    assert "## Error" in report
    assert "file_not_found" in report
