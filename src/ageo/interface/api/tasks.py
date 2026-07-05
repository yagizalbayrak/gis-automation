"""Task lifecycle: plan -> (needs_input | run in background) -> outputs.

Each task gets its OWN workspace and trace sink: tasks are isolated by
construction, and a task's trace is its complete, self-contained process
log. Shared, immutable services (registries, planner, CRS info) are
built once at app startup.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from ageo.application.agents.clarifier import Assumption, PendingQuestion, build_questions
from ageo.application.agents.composer import (
    ComposerClarificationRequired,
    PlanComposer,
    plan_preview,
)
from ageo.application.agents.planner import DeterministicPlanner, HybridPlanner
from ageo.application.orchestration.runner import WorkflowRunner
from ageo.application.orchestration.trace import ListTraceSink
from ageo.application.tools.contract import LayerRef, OsmGateway
from ageo.application.tools.errors import AgeoError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.application.workflows.spec import WorkflowSpec
from ageo.domain.ports.crs_info import CrsInfoPort
from ageo.domain.value_objects.user_profile import AutonomyPreference, UserProfile
from ageo.infrastructure.gis.workspace import InMemoryWorkspace
from ageo.infrastructure.user.profile_store import UserProfileStore
from ageo.interface.api.schemas import TaskResponse, TaskStatus

TERMINAL_STATUSES = frozenset(
    {TaskStatus.UNMATCHED, TaskStatus.NEEDS_INPUT, TaskStatus.SUCCEEDED, TaskStatus.FAILED}
)


@dataclass
class TaskRecord:
    task_id: str
    text: str
    status: TaskStatus
    workflow: str | None = None
    mode: str = "registered"
    spec: WorkflowSpec | None = None  # set for composed plans
    params: dict[str, Any] = field(default_factory=dict)
    missing_params: list[str] = field(default_factory=list)
    questions: list[PendingQuestion] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    explanation: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    trace: ListTraceSink = field(default_factory=ListTraceSink)
    workspace: InMemoryWorkspace | None = None
    thread: threading.Thread | None = None

    def to_response(self) -> TaskResponse:
        return TaskResponse(
            task_id=self.task_id,
            status=self.status,
            text=self.text,
            workflow=self.workflow,
            mode=self.mode,
            plan=plan_preview(self.spec) if self.spec else [],
            params={k: v for k, v in self.params.items() if v is not None},
            missing_params=self.missing_params,
            questions=[q.model_dump(mode="json") for q in self.questions],
            assumptions=[a.model_dump(mode="json") for a in self.assumptions],
            explanation=self.explanation,
            outputs={
                name: value.layer_id
                for name, value in self.outputs.items()
                if isinstance(value, LayerRef)
            },
            results={
                name: value
                for name, value in self.outputs.items()
                if not isinstance(value, LayerRef)
            },
            error=self.error,
        )


class TaskManager:
    def __init__(
        self,
        tools: ToolRegistry,
        workflows: WorkflowRegistry,
        crs_info: CrsInfoPort,
        osm_gateway: OsmGateway | None,
        planner: DeterministicPlanner | HybridPlanner | None = None,
        composer: PlanComposer | None = None,
        user_profile: UserProfileStore | None = None,
    ) -> None:
        self._tools = tools
        self._workflows = workflows
        self._crs_info = crs_info
        self._osm_gateway = osm_gateway
        self._planner = planner or DeterministicPlanner(workflows)
        self._composer = composer
        self._user_profile = user_profile or UserProfileStore()
        self._records: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def submit(
        self, text: str, user_params: dict[str, Any], wait: bool = False
    ) -> TaskRecord:
        record = TaskRecord(
            task_id=uuid.uuid4().hex[:12], text=text, status=TaskStatus.RUNNING
        )
        with self._lock:
            self._records[record.task_id] = record

        profile: UserProfile = self._user_profile.get_or_default()
        decision = self._planner.plan(text, profile=profile)
        record.workflow = decision.workflow
        record.explanation = decision.explanation
        # Explicit user parameters always win over heuristic extraction:
        # this is how needs_input answers flow back in.
        record.params = {**decision.params, **user_params}

        if decision.workflow is None:
            # No registered workflow fits: escalate to the plan composer,
            # which builds a new tool chain and must pass the same validator
            # bundled workflows pass.
            if self._composer is not None:
                return self._submit_composed(record, wait, profile)
            record.status = TaskStatus.UNMATCHED
            return record

        spec = self._workflows.get(decision.workflow)
        questions, assumptions = build_questions(spec, record.params, profile)
        record.questions = questions
        record.assumptions = assumptions
        # Backward-compat view: the params a human must still supply.
        record.missing_params = [q.param for q in questions if q.blocking]
        if record.missing_params:
            record.status = TaskStatus.NEEDS_INPUT
            return record

        record.thread = threading.Thread(
            target=self._execute, args=(record,), daemon=True
        )
        record.thread.start()
        if wait:
            record.thread.join()
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def _submit_composed(
        self, record: TaskRecord, wait: bool, profile: UserProfile
    ) -> TaskRecord:
        clarification_answer = record.params.get("clarification_answer")
        record.params = {}  # composed plans still carry no formal params otherwise

        try:
            composed = self._composer.compose(
                record.text, profile=profile, clarification_answer=clarification_answer
            )
        except ComposerClarificationRequired as exc:
            question = exc.question
            recommended = next((o for o in question.options if o.recommended), None)
            if (
                profile.autonomy_preference is AutonomyPreference.AUTONOMOUS
                and recommended is not None
            ):
                # Autonomy still never invents an answer without a
                # recommended option to fall back on - only auto-resolve
                # when the composer itself supplied one.
                try:
                    composed = self._composer.compose(
                        record.text,
                        profile=profile,
                        clarification_answer=str(recommended.value),
                    )
                except (ComposerClarificationRequired, AgeoError) as exc2:
                    record.status = TaskStatus.UNMATCHED
                    record.explanation = (
                        "No registered workflow matched and the plan composer "
                        "could not build a valid plan."
                    )
                    record.error = str(exc2)
                    return record
                record.assumptions = [
                    Assumption(
                        param="clarification_answer",
                        value=recommended.value,
                        source="composer_recommended",
                        reason=question.reason,
                        text=question.text,
                    )
                ]
            else:
                record.mode = "composed"
                record.questions = [question]
                record.missing_params = ["clarification_answer"]
                record.status = TaskStatus.NEEDS_INPUT
                return record
        except AgeoError as exc:
            record.status = TaskStatus.UNMATCHED
            record.explanation = (
                "No registered workflow matched and the plan composer could "
                "not build a valid plan."
            )
            record.error = str(exc)
            return record

        record.mode = "composed"
        record.spec = composed.spec
        record.workflow = composed.spec.name
        record.params = {}
        record.explanation = (
            f"Composed and validated a {len(composed.spec.steps)}-step plan "
            f"({composed.attempts} attempt(s), {composed.recipes_used} recipe(s)): "
            f"{composed.spec.summary}"
        )
        record.thread = threading.Thread(
            target=self._execute, args=(record,), daemon=True
        )
        record.thread.start()
        if wait:
            record.thread.join()
        return record

    def _execute(self, record: TaskRecord) -> None:
        record.workspace = InMemoryWorkspace(self._crs_info, osm=self._osm_gateway)
        runner = WorkflowRunner(
            self._workflows, self._tools, record.workspace, record.trace, self._crs_info
        )
        try:
            if record.spec is not None:
                record.outputs = runner.run_spec(record.spec, record.params)
            else:
                record.outputs = runner.run(record.workflow, record.params)
            record.status = TaskStatus.SUCCEEDED
        except AgeoError as exc:
            record.error = str(exc)
            record.status = TaskStatus.FAILED
        except Exception as exc:  # defensive: never leave a task in RUNNING
            record.error = f"internal_error: {exc}"
            record.status = TaskStatus.FAILED
