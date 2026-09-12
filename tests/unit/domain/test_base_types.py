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
        updated_at="2026-09-12T00:00:00Z"
    )
    assert meta.verified is True
    assert meta.source == "user_input"
