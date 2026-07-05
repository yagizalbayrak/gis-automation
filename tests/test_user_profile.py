"""UserProfile domain object and file-backed store: roundtrip, corrupt
file handling, prompt-line compactness, report-depth mapping."""
from __future__ import annotations

from ageo.domain.value_objects.user_profile import (
    AutonomyPreference,
    CrsAwareness,
    ExplanationDepth,
    GisLevel,
    ProfileLanguage,
    UserProfile,
    UserRole,
)
from ageo.infrastructure.user.profile_store import UserProfileStore


def test_profile_store_roundtrip(tmp_path) -> None:
    store = UserProfileStore(tmp_path / "profile.json")
    assert store.get() is None
    assert store.get_or_default() == UserProfile()

    profile = UserProfile(
        role=UserRole.URBAN_PLANNER,
        gis_level=GisLevel.INTERMEDIATE,
        crs_awareness=CrsAwareness.HIGH,
        autonomy_preference=AutonomyPreference.AUTONOMOUS,
        explanation_depth=ExplanationDepth.TECHNICAL_AUDIT,
        language=ProfileLanguage.TR,
    )
    store.save(profile)
    assert store.get() == profile
    assert store.get_or_default() == profile


def test_profile_store_corrupt_file_returns_none(tmp_path) -> None:
    path = tmp_path / "profile.json"
    path.write_text("not json", encoding="utf-8")
    store = UserProfileStore(path)
    assert store.get() is None
    assert store.get_or_default() == UserProfile()


def test_profile_store_missing_field_returns_none(tmp_path) -> None:
    path = tmp_path / "profile.json"
    path.write_text('{"role": "gis_specialist"}', encoding="utf-8")
    store = UserProfileStore(path)
    assert store.get() is None


def test_to_prompt_line_is_compact_and_contains_all_axes() -> None:
    profile = UserProfile(
        role=UserRole.URBAN_PLANNER,
        gis_level=GisLevel.INTERMEDIATE,
        crs_awareness=CrsAwareness.LOW,
        autonomy_preference=AutonomyPreference.GUIDED,
        explanation_depth=ExplanationDepth.STEP_BY_STEP,
        language=ProfileLanguage.EN,
    )
    line = profile.to_prompt_line()
    assert line == "USER role=urban_plan lvl=mid crs=lo auto=guided expl=steps lang=en"
    assert len(line) < 120  # comfortably under the ~100-token prompt budget
    for fragment in ("role=", "lvl=", "crs=", "auto=", "expl=", "lang="):
        assert fragment in line


def test_report_depth_mapping() -> None:
    assert UserProfile(
        explanation_depth=ExplanationDepth.PLAIN_LANGUAGE
    ).report_depth() == "plain"
    assert UserProfile(
        explanation_depth=ExplanationDepth.STEP_BY_STEP
    ).report_depth() == "steps"
    assert UserProfile(
        explanation_depth=ExplanationDepth.TECHNICAL_AUDIT
    ).report_depth() == "audit"
