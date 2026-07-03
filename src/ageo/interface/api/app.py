"""FastAPI application factory.

Endpoints (the operational workbench contract from the brief, section 16):

- POST /tasks            natural-language task -> plan -> execute
                         (status needs_input + missing_params drives the
                         human-in-the-loop question flow)
- GET  /tasks/{id}       status, chosen workflow, outputs, error
- GET  /tasks/{id}/trace full process log (JSON)
- GET  /tasks/{id}/events  live Server-Sent Events stream of trace events
- GET  /tasks/{id}/layers/{name}  display-ready GeoJSON (always EPSG:4326)
- POST /uploads          file upload; returns a path usable as a workflow param
- GET  /catalog          workflows + tools the planner can choose from
"""
from __future__ import annotations

import json
import re
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import ageo.application.tools.impl  # noqa: F401 - registers all tools
from ageo.application.agents.composer import LlmComposerPort, PlanComposer
from ageo.application.agents.planner import HybridPlanner, LlmPlannerPort
from ageo.application.agents.reporter import ProcessReporter
from ageo.application.rag.store import RecipeStore
from ageo.application.tools.contract import LayerRef, OsmGateway
from ageo.application.tools.registry import registry as tool_registry
from ageo.application.workflows.defs import register_bundled
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.infrastructure.gis.crs_info import PyprojCrsInfo
from ageo.infrastructure.llm.config import PROVIDER_PRESETS, LlmConfig, LlmConfigStore
from ageo.interface.api.schemas import (
    CreateTaskRequest,
    LayerResponse,
    LlmSettingsResponse,
    LlmSettingsUpdate,
    LlmTestResponse,
    TaskResponse,
    UploadResponse,
)
from ageo.interface.api.tasks import TERMINAL_STATUSES, TaskManager, TaskRecord

_SSE_POLL_INTERVAL_S = 0.05
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")
_WEB_STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


def create_app(
    osm_gateway: OsmGateway | None = None,
    upload_dir: str | None = None,
    llm_planner: LlmPlannerPort | None = None,
    composer_llm: LlmComposerPort | None = None,
    settings_path: str | None = None,
) -> FastAPI:
    """Build the app. Pass a fake osm_gateway in tests; None uses the real
    Overpass gateway.

    The AI planner fallback and the plan composer are ALWAYS wired: they
    read the live LLM configuration (Settings panel / settings file / env)
    on every call. Unconfigured means they decline with a clear
    'open Settings' message - the app never fails at startup over a model,
    and a request outside the registered workflows is never a dead end
    once an LLM is configured."""
    if osm_gateway is None:
        from ageo.infrastructure.gis.overpass import OverpassOsmGateway

        osm_gateway = OverpassOsmGateway()

    crs_info = PyprojCrsInfo()
    workflows = WorkflowRegistry(tool_registry, crs_info)
    register_bundled(workflows)
    llm_config = LlmConfigStore(settings_path)

    if llm_planner is None:
        from ageo.infrastructure.llm.litellm_planner import LiteLlmPlanner

        llm_planner = LiteLlmPlanner(config=llm_config)
    planner = HybridPlanner(workflows, llm=llm_planner)

    if composer_llm is None:
        from ageo.infrastructure.llm.litellm_composer import LiteLlmComposer

        composer_llm = LiteLlmComposer(config=llm_config)
    composer = PlanComposer(composer_llm, tool_registry, crs_info, RecipeStore())

    manager = TaskManager(
        tool_registry, workflows, crs_info, osm_gateway,
        planner=planner, composer=composer,
    )
    reporter = ProcessReporter()
    uploads = Path(upload_dir or tempfile.mkdtemp(prefix="ageo_uploads_"))
    uploads.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Autonomous GIS Workbench", version="0.1.0")
    app.mount("/static", StaticFiles(directory=_WEB_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_WEB_STATIC_DIR / "index.html")

    @app.get("/catalog")
    def catalog() -> dict:
        return {
            "workflows": workflows.catalog(),
            "tools": tool_registry.catalog(),
        }

    @app.get("/settings/llm", response_model=LlmSettingsResponse)
    def get_llm_settings() -> LlmSettingsResponse:
        saved = llm_config.get()
        return LlmSettingsResponse(
            configured=llm_config.is_configured("AGEO_COMPOSER_MODEL"),
            provider=saved.provider if saved else None,
            model=saved.model if saved else None,
            api_key_masked=saved.masked_key() if saved else None,
            api_base=saved.api_base if saved else None,
            providers=PROVIDER_PRESETS,
        )

    @app.put("/settings/llm", response_model=LlmSettingsResponse)
    def update_llm_settings(update: LlmSettingsUpdate) -> LlmSettingsResponse:
        previous = llm_config.get()
        api_key = update.api_key
        if api_key is None and previous is not None:
            api_key = previous.api_key  # keep the saved secret on partial updates
        llm_config.save(LlmConfig(
            provider=update.provider,
            model=update.model.strip(),
            api_key=(api_key or "").strip() or None,
            api_base=(update.api_base or "").strip() or None,
        ))
        return get_llm_settings()

    @app.post("/settings/llm/test", response_model=LlmTestResponse)
    def test_llm_settings() -> LlmTestResponse:
        """One tiny completion against the saved configuration - proves the
        model id and API key actually work before any real task uses them."""
        saved = llm_config.get()
        if saved is None:
            return LlmTestResponse(
                ok=False, message="No LLM configured yet. Save settings first."
            )
        import litellm

        started = time.monotonic()
        try:
            response = litellm.completion(
                **saved.completion_kwargs(),
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=10,
                temperature=0.0,
                timeout=20.0,
            )
        except Exception as exc:
            return LlmTestResponse(
                ok=False,
                model=saved.model,
                message=f"Connection failed: {_brief_error(exc)}",
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        content = (response.choices[0].message.content or "").strip()
        return LlmTestResponse(
            ok=True,
            model=saved.model,
            latency_ms=latency_ms,
            message=f"Model responded ({content[:40] or 'empty reply'}).",
        )

    @app.post("/tasks", response_model=TaskResponse)
    def create_task(request: CreateTaskRequest, wait: bool = False) -> TaskResponse:
        record = manager.submit(request.text, request.params, wait=wait)
        return record.to_response()

    @app.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str) -> TaskResponse:
        return _record_or_404(manager, task_id).to_response()

    @app.get("/tasks/{task_id}/trace")
    def get_trace(task_id: str) -> list[dict]:
        record = _record_or_404(manager, task_id)
        return [event.model_dump(mode="json") for event in record.trace.events]

    @app.get("/tasks/{task_id}/report")
    def get_report(task_id: str, lang: str = "en") -> dict:
        record = _record_or_404(manager, task_id)
        report = reporter.report(
            text=record.text,
            workflow=record.workflow,
            params=record.params,
            status=record.status.value,
            events=record.trace.events,
            outputs={
                name: value.layer_id
                for name, value in record.outputs.items()
                if isinstance(value, LayerRef)
            },
            error=record.error,
            lang=lang,
        )
        return {"task_id": task_id, "lang": lang, "report": report}

    @app.get("/tasks/{task_id}/events")
    def stream_events(task_id: str) -> StreamingResponse:
        record = _record_or_404(manager, task_id)

        def generate():
            cursor = 0
            while True:
                events = record.trace.events
                while cursor < len(events):
                    yield f"data: {events[cursor].model_dump_json()}\n\n"
                    cursor += 1
                if record.status in TERMINAL_STATUSES:
                    yield (
                        'event: done\ndata: {"status": "%s"}\n\n' % record.status.value
                    )
                    return
                time.sleep(_SSE_POLL_INTERVAL_S)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/tasks/{task_id}/layers/{output_name}", response_model=LayerResponse)
    def get_layer(task_id: str, output_name: str) -> LayerResponse:
        record = _record_or_404(manager, task_id)
        value = record.outputs.get(output_name)
        if not isinstance(value, LayerRef) or record.workspace is None:
            raise HTTPException(404, f"No layer output named {output_name!r}")

        gdf = record.workspace.read(value)
        source_crs = record.workspace.crs_of(value)
        # Preview payloads are always served in the display CRS. This is a
        # serialization concern only - analysis results in the workspace and
        # exports keep their analytical CRS.
        if source_crs is not None and source_crs.srid != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        return LayerResponse(
            name=output_name,
            source_srid=source_crs.srid if source_crs else None,
            display_srid="EPSG:4326",
            feature_count=len(gdf),
            feature_collection=json.loads(gdf.to_json()),
        )

    @app.post("/uploads", response_model=UploadResponse)
    async def upload(file: UploadFile) -> UploadResponse:
        safe_name = _SAFE_FILENAME.sub("_", file.filename or "upload.bin")
        target = uploads / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        content = await file.read()
        target.write_bytes(content)
        return UploadResponse(
            path=str(target), filename=safe_name, size_bytes=len(content)
        )

    return app


def _record_or_404(manager: TaskManager, task_id: str) -> TaskRecord:
    record = manager.get(task_id)
    if record is None:
        raise HTTPException(404, f"Unknown task: {task_id!r}")
    return record


def _brief_error(exc: Exception) -> str:
    """Human part of a provider error.

    Provider SDK errors usually embed a JSON payload whose 'message' field
    holds the actionable reason ('API key not valid...', 'quota exceeded').
    Surface that; fall back to the first line without the JSON blob."""
    raw = str(exc).strip()
    if not raw:
        return type(exc).__name__

    match = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if match:
        message = match.group(1).encode().decode("unicode_escape")
        prefix = raw.splitlines()[0]
        brace = prefix.find("{")
        if brace > 0:
            prefix = prefix[:brace].rstrip(" -:")
        return f"{prefix}: {message}"[:300]

    text = raw.splitlines()[0]
    brace = text.find("{")
    if brace > 0:
        text = text[:brace].rstrip(" -:")
    return text[:200] or type(exc).__name__
