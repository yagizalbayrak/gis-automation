"""API request/response schemas.

Deliberately lenient on input (client JSON) - strictness lives at the
tool and runner boundaries, which re-validate everything anyway. The
response schema is the UI's contract: it must always say what the system
understood, which workflow it chose, and what it still needs to know.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    UNMATCHED = "unmatched"      # no workflow pattern matched the request
    NEEDS_INPUT = "needs_input"  # workflow selected, parameters missing (HIL)
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CreateTaskRequest(BaseModel):
    text: str = Field(min_length=1, description="Natural-language task")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit parameter values; override/complete what the "
                    "planner extracts (used to answer needs_input questions).",
    )


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    text: str
    workflow: str | None = None
    mode: str = "registered"  # "registered" | "composed"
    plan: list[dict[str, Any]] = Field(
        default_factory=list,
        description="For composed tasks: the validated step chain that will run",
    )
    params: dict[str, Any] = Field(default_factory=dict)
    missing_params: list[str] = Field(default_factory=list)
    explanation: str = ""
    outputs: dict[str, str] = Field(
        default_factory=dict, description="Output name -> workspace layer id"
    )
    results: dict[str, Any] = Field(
        default_factory=dict, description="Non-layer scalar/table workflow outputs"
    )
    error: str | None = None


class UploadResponse(BaseModel):
    path: str
    filename: str
    size_bytes: int


class LlmSettingsUpdate(BaseModel):
    provider: str = Field(pattern=r"^(gemini|anthropic|openai|custom)$")
    model: str = Field(min_length=1, description="LiteLLM model id")
    api_key: str | None = Field(
        default=None,
        description="Omit or send null to keep the previously saved key",
    )
    api_base: str | None = None


class LlmSettingsResponse(BaseModel):
    configured: bool
    provider: str | None = None
    model: str | None = None
    api_key_masked: str | None = None
    api_base: str | None = None
    providers: dict[str, Any] = Field(
        default_factory=dict, description="Provider presets for the UI"
    )


class LlmTestResponse(BaseModel):
    ok: bool
    model: str | None = None
    latency_ms: int | None = None
    message: str


class LayerResponse(BaseModel):
    name: str
    source_srid: str | None
    display_srid: str  # preview payloads are always served in EPSG:4326
    feature_count: int
    feature_collection: dict[str, Any]
