"""Process trace: the audit trail behind every workflow run.

Every guard decision, tool execution and failure is recorded as a typed
event. The interface layer streams these to the UI trace panel; the
Reporter agent summarizes them; JSON process logs serialize them.
"""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TracePhase(StrEnum):
    TOOL_STARTED = "tool_started"
    GUARD_PASSED = "guard_passed"
    GUARD_FAILED = "guard_failed"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_FINISHED = "workflow_finished"
    WORKFLOW_FAILED = "workflow_failed"


class TraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: TracePhase
    subject: str                      # tool or workflow name
    detail: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class ListTraceSink:
    """Simple in-memory sink; also the JSON process-log source."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)

    def phases(self) -> list[str]:
        return [e.phase.value for e in self.events]
