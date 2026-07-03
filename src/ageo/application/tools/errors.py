"""Typed failure taxonomy.

Every error a tool or guard can raise is a named class so the trace
panel, the Reporter agent, and workflow retry policies can react to
error *types* instead of parsing strings.
"""
from __future__ import annotations


class AgeoError(Exception):
    """Base for all ageo errors."""


class ToolExecutionError(AgeoError):
    """A tool failed during deterministic execution."""


class GuardViolation(AgeoError):
    """A precondition guard rejected the input before the tool ran."""


class CrsGuardViolation(GuardViolation):
    """CRS requirement not met (e.g. buffer attempted in a geographic CRS)."""


class GeometryGuardViolation(GuardViolation):
    """Geometry class or validity requirement not met."""


class UnknownLayerError(ToolExecutionError):
    """A LayerRef points to a layer that does not exist in the workspace."""


class EmptyLayerError(ToolExecutionError):
    """A tool that requires features received an empty layer."""


class ToolRegistrationError(AgeoError):
    """A tool definition is malformed. Raised at import time, never at runtime."""


class WorkflowRegistrationError(AgeoError):
    """A workflow definition is malformed or geodetically incoherent."""


class WorkflowParamError(AgeoError):
    """A workflow was instantiated with invalid parameters."""


class GatewayError(AgeoError):
    """An external data gateway (OSM/Overpass, etc.) failed or is unavailable."""


class ComposerError(AgeoError):
    """The plan composer could not produce a valid plan for the request."""
