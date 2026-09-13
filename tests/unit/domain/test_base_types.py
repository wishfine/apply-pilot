import pytest
from applypilot.domain.base import TriState, PartialDate, SensitivityLevel, FieldPolicy, LogStrategy, FactMetadata

def test_tristate_values():
    assert TriState.YES == "yes"
    assert TriState.NO == "no"
    assert TriState.UNKNOWN == "unknown"

def test_partial_date_formatting():
    d1 = PartialDate(year=2025)
    assert d1.to_display() == "2025"

    d2 = PartialDate(year=2025, month=9)
    assert d2.to_display() == "2025-09"

    d3 = PartialDate(year=2025, month=9, day=12)
    assert d3.to_display() == "2025-09-12"

def test_field_policy_definition():
    policy = FieldPolicy(
        path_pattern="identity.id_number",
        sensitivity=SensitivityLevel.SENSITIVE,
        llm_allowed=False,
        log_strategy=LogStrategy.MASK,
        requires_confirmation=True,
    )
    assert policy.llm_allowed is False
    assert policy.requires_confirmation is True

def test_fact_metadata_creation():
    meta = FactMetadata(
        source="user_input",
        verified=True,
        confidence=1.0,
        updated_at="2026-09-12T00:00:00Z",
    )
    assert meta.verified is True
    assert meta.source == "user_input"


def test_partial_date_str():
    assert str(PartialDate(year=2025, month=9, day=12)) == "2025-09-12"
    assert str(PartialDate(year=2025, month=9)) == "2025-09"
    assert str(PartialDate(year=2025)) == "2025"


def test_partial_date_validation_rules():
    with pytest.raises(ValueError, match="Cannot specify day without specifying month"):
        PartialDate(year=2025, day=15)

    with pytest.raises(ValueError, match="Month must be between 1 and 12"):
        PartialDate(year=2025, month=13)

    with pytest.raises(ValueError, match="Day must be between 1 and 31"):
        PartialDate(year=2025, month=5, day=32)


@pytest.mark.parametrize("value", ["2023-02-31", "2024-foo-12", "2024-01-01-extra"])
def test_partial_date_rejects_invalid_calendar_and_malformed_strings(value):
    with pytest.raises(ValueError):
        PartialDate.model_validate(value)


def test_field_policy_defaults():
    policy = FieldPolicy(
        path_pattern="profile.name",
        sensitivity=SensitivityLevel.PERSONAL,
        llm_allowed=True,
    )
    assert policy.log_strategy == LogStrategy.MASK
    assert policy.requires_confirmation is False


def test_fact_metadata_defaults_and_bounds():
    meta = FactMetadata(source="user_input", updated_at="2026-09-12T00:00:00Z")
    assert meta.verified is False
    assert meta.confidence == 1.0

    with pytest.raises(ValueError):
        FactMetadata(source="user", updated_at="now", confidence=1.5)
