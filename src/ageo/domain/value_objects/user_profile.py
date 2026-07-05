"""User profile value objects.

Pure Python: no Pydantic. The profile captures how a user wants the
system to behave - autonomy level, jargon tolerance, report depth - and
is injected as a compact string into LLM prompts and read by the
reporter to pick a rendering depth. It carries no secrets, unlike
LlmConfig, so there is no masking concern.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UserRole(StrEnum):
    GIS_SPECIALIST = "gis_specialist"
    CIVIL_ENGINEER = "civil_engineer"
    URBAN_PLANNER = "urban_planner"
    MUNICIPALITY_STAFF = "municipality_staff"
    NON_TECHNICAL_USER = "non_technical_user"


class GisLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CrsAwareness(StrEnum):
    HIGH = "high"
    LOW = "low"


class AutonomyPreference(StrEnum):
    GUIDED = "guided"
    AUTONOMOUS = "autonomous"
    STRICT_CONFIRM = "strict_confirm"


class ExplanationDepth(StrEnum):
    PLAIN_LANGUAGE = "plain_language"
    STEP_BY_STEP = "step_by_step"
    TECHNICAL_AUDIT = "technical_audit"


class ProfileLanguage(StrEnum):
    TR = "tr"
    EN = "en"


# Short codes for the compact prompt-injection line - keep in lockstep
# with the enums above. The LLM only reads the encoded line; it is never
# decoded back into a profile.
_ROLE_CODES: dict[UserRole, str] = {
    UserRole.GIS_SPECIALIST: "gis_spec",
    UserRole.CIVIL_ENGINEER: "civil_eng",
    UserRole.URBAN_PLANNER: "urban_plan",
    UserRole.MUNICIPALITY_STAFF: "muni_staff",
    UserRole.NON_TECHNICAL_USER: "non_tech",
}
_LEVEL_CODES: dict[GisLevel, str] = {
    GisLevel.BEGINNER: "beg",
    GisLevel.INTERMEDIATE: "mid",
    GisLevel.ADVANCED: "adv",
}
_CRS_CODES: dict[CrsAwareness, str] = {
    CrsAwareness.HIGH: "hi",
    CrsAwareness.LOW: "lo",
}
_AUTONOMY_CODES: dict[AutonomyPreference, str] = {
    AutonomyPreference.GUIDED: "guided",
    AutonomyPreference.AUTONOMOUS: "auto",
    AutonomyPreference.STRICT_CONFIRM: "confirm",
}
_EXPLANATION_CODES: dict[ExplanationDepth, str] = {
    ExplanationDepth.PLAIN_LANGUAGE: "plain",
    ExplanationDepth.STEP_BY_STEP: "steps",
    ExplanationDepth.TECHNICAL_AUDIT: "audit",
}


@dataclass(frozen=True, slots=True)
class UserProfile:
    role: UserRole = UserRole.NON_TECHNICAL_USER
    gis_level: GisLevel = GisLevel.BEGINNER
    crs_awareness: CrsAwareness = CrsAwareness.LOW
    autonomy_preference: AutonomyPreference = AutonomyPreference.GUIDED
    explanation_depth: ExplanationDepth = ExplanationDepth.PLAIN_LANGUAGE
    language: ProfileLanguage = ProfileLanguage.EN

    def to_prompt_line(self) -> str:
        """Compact single-line serialization for LLM prompt injection.

        Short codes, not full enum names, to stay well under the token
        budget: e.g. 'USER role=urban_plan lvl=mid crs=lo auto=guided
        expl=steps lang=en'.
        """
        return (
            "USER "
            f"role={_ROLE_CODES[self.role]} "
            f"lvl={_LEVEL_CODES[self.gis_level]} "
            f"crs={_CRS_CODES[self.crs_awareness]} "
            f"auto={_AUTONOMY_CODES[self.autonomy_preference]} "
            f"expl={_EXPLANATION_CODES[self.explanation_depth]} "
            f"lang={self.language.value}"
        )

    def report_depth(self) -> str:
        """Maps explanation_depth onto the Reporter's depth vocabulary."""
        return _EXPLANATION_CODES[self.explanation_depth]
