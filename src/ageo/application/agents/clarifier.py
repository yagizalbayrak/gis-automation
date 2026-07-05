"""Clarifier: deterministic structured HIL questions + assumption ledger.

Upgrades the missing_params: list[str] mechanism into PendingQuestion
objects gated by UserProfile.autonomy_preference, plus an Assumption
ledger recording parameters that silently fell back to spec defaults.
Pure and deterministic - zero LLM tokens, mirroring the Reporter.

Gating matrix (param state x autonomy):

- required, no default, not provided -> "parameter" question, severity
  critical, blocking, asked under EVERY autonomy level. The system never
  invents values: missing parameters are reported, not guessed.
- has a spec default, not user-supplied:
  - strict_confirm -> blocking "risk_confirmation" question carrying the
    default as the single recommended option (severity material for
    srid/srid_metric kinds - a geodetic choice - else cosmetic).
  - guided / autonomous -> not asked; recorded as an Assumption
    (source="spec_default") so the silent default is never invisible.

Net effect: strict_confirm asks strictly more; guided == autonomous for
registered workflows (the mirror asymmetry appears for composer-originated
clarifications - see composer.py's ComposerClarificationRequired, where
autonomous is instead the outlier that asks less). Params that are
optional with no default produce neither a question nor an assumption.
"""
from __future__ import annotations

from typing import Any, Literal

from ageo.application.tools.contract import StrictModel
from ageo.application.workflows.spec import WorkflowParam, WorkflowSpec
from ageo.domain.value_objects.user_profile import AutonomyPreference, UserProfile

QuestionType = Literal["parameter", "risk_confirmation", "clarification", "preference"]
Severity = Literal["critical", "material", "cosmetic"]

# Deterministic question/assumption text per param kind, EN + TR (Turkish
# ASCII-folded, matching the Reporter's label convention). EN embeds the
# param's English description; TR uses kind-based phrasing + param name
# because param descriptions are English-only.
_ASK_TEXT: dict[str, dict[str, str]] = {
    "string": {
        "en": "Please provide '{name}'{desc}.",
        "tr": "'{name}' icin bir deger girin.",
    },
    "float": {
        "en": "What value should '{name}' be{desc}?",
        "tr": "'{name}' icin sayisal bir deger girin.",
    },
    "int": {
        "en": "What whole-number value should '{name}' be{desc}?",
        "tr": "'{name}' icin tam sayi bir deger girin.",
    },
    "bool": {
        "en": "Should '{name}' be enabled{desc}?",
        "tr": "'{name}' acik olsun mu?",
    },
    "srid": {
        "en": "Which coordinate system (EPSG code) should '{name}' use{desc}?",
        "tr": "'{name}' icin hangi koordinat sistemi (EPSG kodu) kullanilsin?",
    },
    "srid_metric": {
        "en": "Which projected metric coordinate system should '{name}' use{desc}?",
        "tr": "'{name}' icin hangi metrik (projeksiyonlu) koordinat sistemi kullanilsin?",
    },
}
_CONFIRM_TEXT = {
    "en": "Use the default {value} for '{name}'{desc}?",
    "tr": "'{name}' icin varsayilan deger ({value}) kullanilsin mi?",
}
_OPTION_LABEL = {
    "en": "{value} (workflow default)",
    "tr": "{value} (varsayilan)",
}
_ASSUMED_TEXT = {
    "en": "Assumed {name} = {value} (workflow default).",
    "tr": "{name} = {value} varsayildi (is akisi varsayilani).",
}


class QuestionOption(StrictModel):
    value: Any
    label: dict[str, str]  # required "en" + "tr" keys
    recommended: bool = False


class PendingQuestion(StrictModel):
    question_id: str  # "q_param_<name>" / "q_confirm_<name>"
    question_type: QuestionType  # only parameter/risk_confirmation emitted now
    severity: Severity
    param: str  # binding target
    kind: str  # WorkflowParam kind -> UI input type
    reason: str  # machine-honest EN
    text: dict[str, str]  # "en" + "tr"
    options: tuple[QuestionOption, ...] = ()
    blocking: bool = True
    default_if_skipped: Any = None


class Assumption(StrictModel):
    param: str
    value: Any
    source: Literal["spec_default", "composer_recommended"]
    reason: str  # EN, from the param description
    text: dict[str, str]  # en/tr one-liner for report/UI


def build_questions(
    spec: WorkflowSpec, provided: dict[str, Any], profile: UserProfile
) -> tuple[list[PendingQuestion], list[Assumption]]:
    """Apply the gating matrix over the spec's params, in spec order."""
    questions: list[PendingQuestion] = []
    assumptions: list[Assumption] = []
    for param in spec.params:
        if param.name in provided:
            continue
        if param.required and param.default is None:
            questions.append(_parameter_question(param))
        elif param.default is not None:
            if profile.autonomy_preference is AutonomyPreference.STRICT_CONFIRM:
                questions.append(_confirmation_question(param))
            else:
                assumptions.append(_assumption(param))
    return questions, assumptions


def _desc_suffix(param: WorkflowParam) -> str:
    return f" - {param.description}" if param.description else ""


def _default_severity(param: WorkflowParam) -> Severity:
    return "material" if param.kind in ("srid", "srid_metric") else "cosmetic"


def _parameter_question(param: WorkflowParam) -> PendingQuestion:
    templates = _ASK_TEXT.get(param.kind, _ASK_TEXT["string"])
    return PendingQuestion(
        question_id=f"q_param_{param.name}",
        question_type="parameter",
        severity="critical",
        param=param.name,
        kind=param.kind,
        reason=f"required parameter '{param.name}' has no value and no default",
        text={
            "en": templates["en"].format(name=param.name, desc=_desc_suffix(param)),
            "tr": templates["tr"].format(name=param.name),
        },
        blocking=True,
    )


def _confirmation_question(param: WorkflowParam) -> PendingQuestion:
    return PendingQuestion(
        question_id=f"q_confirm_{param.name}",
        question_type="risk_confirmation",
        severity=_default_severity(param),
        param=param.name,
        kind=param.kind,
        reason=(
            f"parameter '{param.name}' would fall back to spec default "
            f"{param.default!r}; strict_confirm profiles confirm defaults "
            "before execution"
        ),
        text={
            "en": _CONFIRM_TEXT["en"].format(
                name=param.name, value=param.default, desc=_desc_suffix(param)
            ),
            "tr": _CONFIRM_TEXT["tr"].format(name=param.name, value=param.default),
        },
        options=(
            QuestionOption(
                value=param.default,
                label={
                    "en": _OPTION_LABEL["en"].format(value=param.default),
                    "tr": _OPTION_LABEL["tr"].format(value=param.default),
                },
                recommended=True,
            ),
        ),
        blocking=True,
        default_if_skipped=param.default,
    )


def _assumption(param: WorkflowParam) -> Assumption:
    return Assumption(
        param=param.name,
        value=param.default,
        source="spec_default",
        reason=param.description or f"spec default for '{param.name}'",
        text={
            "en": _ASSUMED_TEXT["en"].format(name=param.name, value=param.default),
            "tr": _ASSUMED_TEXT["tr"].format(name=param.name, value=param.default),
        },
    )
