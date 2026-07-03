"""Shared fixtures.

Importing ageo.application.tools.impl registers (and therefore validates)
every tool contract before any test runs.
"""
from __future__ import annotations

import pytest

import ageo.application.tools.impl  # noqa: F401 - triggers tool registration
from ageo.infrastructure.llm import config as llm_config
from ageo.application.orchestration.executor import ToolExecutor
from ageo.application.orchestration.runner import WorkflowRunner
from ageo.application.orchestration.trace import ListTraceSink
from ageo.application.tools.registry import registry
from ageo.application.workflows.defs import register_bundled
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.infrastructure.gis.crs_info import PyprojCrsInfo
from ageo.infrastructure.gis.demo import DemoOsmGateway
from ageo.infrastructure.gis.workspace import InMemoryWorkspace

# The synthetic Kutahya dataset lives in infrastructure so the dev server's
# --demo mode and the tests exercise the exact same data.
FakeOsmGateway = DemoOsmGateway


@pytest.fixture(autouse=True)
def disable_project_dotenv(monkeypatch) -> None:
    """Tests stay offline even when the local checkout has a real .env."""
    monkeypatch.setenv("AGEO_DISABLE_DOTENV", "1")
    monkeypatch.delenv("AGEO_COMPOSER_MODEL", raising=False)
    monkeypatch.delenv("AGEO_PLANNER_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "_ENV_LOADED", False)


@pytest.fixture
def crs_info() -> PyprojCrsInfo:
    return PyprojCrsInfo()


@pytest.fixture
def trace() -> ListTraceSink:
    return ListTraceSink()


@pytest.fixture
def ctx(crs_info) -> InMemoryWorkspace:
    return InMemoryWorkspace(crs_info, osm=FakeOsmGateway())


@pytest.fixture
def executor(ctx, trace) -> ToolExecutor:
    return ToolExecutor(registry, ctx, trace)


@pytest.fixture
def workflows(crs_info) -> WorkflowRegistry:
    workflow_registry = WorkflowRegistry(registry, crs_info)
    register_bundled(workflow_registry)
    return workflow_registry


@pytest.fixture
def runner(workflows, ctx, trace, crs_info) -> WorkflowRunner:
    return WorkflowRunner(workflows, registry, ctx, trace, crs_info)
