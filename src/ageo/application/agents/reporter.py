"""Reporter: turns a task's trace into a human-readable process report.

Deterministic and template-based - no LLM call. The trace already
contains every fact worth reporting (guards, CRS decisions, tool results,
failures); the reporter only arranges them in user language. An LLM
"polish" pass can be layered on later, but the factual report must never
depend on model availability.

Supported languages: English ("en") and Turkish ("tr"), matching the
initial target users from the project brief.
"""
from __future__ import annotations

from typing import Any

from ageo.application.orchestration.trace import TraceEvent, TracePhase

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Process report",
        "request": "Request",
        "workflow": "Selected workflow",
        "params": "Parameters",
        "steps": "Executed steps",
        "crs": "CRS decisions",
        "warnings": "Warnings",
        "outputs": "Outputs",
        "error": "Error",
        "status": "Status",
        "no_steps": "No tools were executed.",
        "features": "features",
        "assumptions": "Assumptions",
    },
    "tr": {
        "title": "Islem raporu",
        "request": "Istek",
        "workflow": "Secilen is akisi",
        "params": "Parametreler",
        "steps": "Yurutulen adimlar",
        "crs": "CRS kararlari",
        "warnings": "Uyarilar",
        "outputs": "Ciktilar",
        "error": "Hata",
        "status": "Durum",
        "no_steps": "Hicbir arac calistirilmadi.",
        "features": "obje",
        "assumptions": "Varsayimlar",
    },
}

_STATUS_TR = {
    "succeeded": "basarili",
    "failed": "basarisiz",
    "running": "calisiyor",
    "needs_input": "girdi bekliyor",
    "unmatched": "eslesmedi",
}


class ProcessReporter:
    def report(
        self,
        *,
        text: str,
        workflow: str | None,
        params: dict[str, Any],
        status: str,
        events: list[TraceEvent],
        outputs: dict[str, str],
        error: str | None = None,
        lang: str = "en",
        depth: str = "steps",
        assumptions: list[dict[str, Any]] | None = None,
    ) -> str:
        labels = _LABELS.get(lang, _LABELS["en"])
        status_text = _STATUS_TR.get(status, status) if lang == "tr" else status
        show_detail = depth != "plain"  # params, executed steps, CRS, warnings

        lines: list[str] = [f"# {labels['title']}", ""]
        lines.append(f"{labels['request']}: {text}")
        lines.append(f"{labels['status']}: {status_text}")
        if workflow:
            lines.append(f"{labels['workflow']}: {workflow}")
        if params and show_detail:
            rendered = ", ".join(f"{k}={v}" for k, v in params.items() if v is not None)
            lines.append(f"{labels['params']}: {rendered}")

        # Assumptions render at EVERY depth, including "plain": a silent
        # default must never be invisible to the user.
        if assumptions:
            lines.append("")
            lines.append(f"## {labels['assumptions']}")
            for assumption in assumptions:
                text_map = assumption.get("text") or {}
                lines.append(
                    f"- {text_map.get(lang) or text_map.get('en') or assumption.get('param')}"
                )

        if show_detail:
            steps = [e for e in events if e.phase is TracePhase.TOOL_FINISHED]
            lines.append("")
            lines.append(f"## {labels['steps']}")
            if steps:
                for index, event in enumerate(steps, start=1):
                    summary = _result_summary(event, labels)
                    lines.append(f"{index}. {event.subject}{summary}")
            else:
                lines.append(labels["no_steps"])

            crs_decisions = [
                f"- {e.subject}.{e.detail.get('input')}: {e.detail.get('crs')}"
                for e in events
                if e.phase is TracePhase.GUARD_PASSED and e.detail.get("crs")
            ]
            if crs_decisions:
                lines.append("")
                lines.append(f"## {labels['crs']}")
                lines.extend(dict.fromkeys(crs_decisions))  # keep order, drop repeats

            warnings = [
                f"- {e.subject}: {e.detail.get('message') or e.detail.get('error')}"
                for e in events
                if e.phase in (TracePhase.GUARD_FAILED, TracePhase.TOOL_FAILED)
            ]
            if warnings:
                lines.append("")
                lines.append(f"## {labels['warnings']}")
                lines.extend(warnings)

        if outputs:
            lines.append("")
            lines.append(f"## {labels['outputs']}")
            lines.extend(f"- {name} ({layer_id})" for name, layer_id in outputs.items())

        if error:
            lines.append("")
            lines.append(f"## {labels['error']}")
            lines.append(error)

        return "\n".join(lines)


def _result_summary(event: TraceEvent, labels: dict[str, str]) -> str:
    result = event.detail.get("result") or {}
    count = result.get("feature_count")
    if isinstance(count, int):
        return f" - {count} {labels['features']}"
    return ""
