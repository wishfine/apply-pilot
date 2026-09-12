from pathlib import Path
import pytest
import yaml

from applypilot.domain.base import TriState
from applypilot.domain.profile import CandidateProfile, ContactInfo, IdentityInfo
from applypilot.modules.apply.readiness import (
    FieldReadinessItem,
    FieldReadinessStatus,
    ProfileWritebackSynchronizer,
    ReadinessAuditor,
    ReadinessReport,
)


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        schema_version="1.1.0",
        profile_id="cand_audit_01",
        identity=IdentityInfo(name="张三", gender="male"),
        contact=ContactInfo(mobile="13800138000", email="zhangsan@example.com"),
        education=[],
        experiences=[],
        projects=[],
        skills=[],
    )


def test_field_readiness_enums_and_models():
    assert FieldReadinessStatus.FILLED == "filled"
    assert FieldReadinessStatus.OPTIONAL_EMPTY == "optional_empty"
    assert FieldReadinessStatus.REQUIRED_MISSING == "required_missing"

    item = FieldReadinessItem(
        field_sig="sig_name",
        label="姓名",
        is_required=True,
        status=FieldReadinessStatus.FILLED,
        profile_path="identity.name",
    )
    assert item.label == "姓名"
    assert item.status == FieldReadinessStatus.FILLED


def test_readiness_auditor_all_required_filled(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_name",
            "label": "姓名",
            "is_required": True,
            "mapped_path": "identity.name",
        },
        {
            "field_sig": "sig_mobile",
            "label": "手机号",
            "is_required": True,
            "mapped_path": "contact.mobile",
        },
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert isinstance(report, ReadinessReport)
    assert report.is_ready is True
    assert len(report.missing_required) == 0
    assert report.total_fields == 2
    assert report.filled_fields == 2
    assert report.optional_empty_fields == 0


def test_readiness_auditor_missing_required_field(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_name",
            "label": "姓名",
            "is_required": True,
            "mapped_path": "identity.name",
        },
        {
            "field_sig": "sig_political",
            "label": "政治面貌",
            "is_required": True,
            "mapped_path": "soe_extended.political_status",
        },
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is False
    assert len(report.missing_required) == 1
    missing = report.missing_required[0]
    assert missing.label == "政治面貌"
    assert missing.status == FieldReadinessStatus.REQUIRED_MISSING
    assert missing.suggested_fix is not None
    assert "profile.yaml" in missing.suggested_fix
    assert "soe_extended.political_status" in missing.suggested_fix


def test_readiness_auditor_unmapped_required_field_suggested_fix(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_custom",
            "label": "补充说明",
            "is_required": True,
            "mapped_path": None,
        }
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is False
    missing = report.missing_required[0]
    assert "未映射字段 '补充说明'" in missing.suggested_fix


def test_readiness_auditor_optional_empty_field(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_emergency",
            "label": "紧急联系人 (选填)",
            "mapped_path": "contact.emergency_contact_name",
        }
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is True
    assert report.total_fields == 1
    assert report.filled_fields == 0
    assert report.optional_empty_fields == 1
    assert report.all_items[0].status == FieldReadinessStatus.OPTIONAL_EMPTY


def test_readiness_auditor_observed_dom_value_fills_field(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_city",
            "label": "现居城市",
            "is_required": True,
            "observed_value": "上海",
            "mapped_path": None,
        }
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is True
    assert report.filled_fields == 1
    assert report.all_items[0].status == FieldReadinessStatus.FILLED


def test_readiness_auditor_falsy_dom_values_count_as_filled(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_years",
            "label": "工作经验年数",
            "is_required": True,
            "observed_value": 0,
        },
        {
            "field_sig": "sig_dispute",
            "label": "是否有违约记录",
            "is_required": True,
            "current_value": False,
        },
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is True
    assert report.filled_fields == 2
    assert report.all_items[0].status == FieldReadinessStatus.FILLED
    assert report.all_items[1].status == FieldReadinessStatus.FILLED


def test_readiness_auditor_tristate_unknown_not_counted_as_filled(sample_profile: CandidateProfile):
    # campus_context.has_dispatch_qualification defaults to TriState.UNKNOWN
    assert sample_profile.campus_context.has_dispatch_qualification == TriState.UNKNOWN

    scanned_fields = [
        {
            "field_sig": "sig_dispatch",
            "label": "派遣资格",
            "is_required": True,
            "mapped_path": "campus_context.has_dispatch_qualification",
        }
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.is_ready is False
    assert report.missing_required[0].status == FieldReadinessStatus.REQUIRED_MISSING


def test_readiness_auditor_detector_fallback_for_is_required(sample_profile: CandidateProfile):
    scanned_fields = [
        {
            "field_sig": "sig_exp_city",
            "label": "* 期望工作城市",
            "element_attrs": {"required": True},
            "mapped_path": "contact.current_city",
        }
    ]

    report = ReadinessAuditor.audit_fields(scanned_fields, sample_profile)
    assert report.all_items[0].is_required is True
    # current_city is None in sample_profile, so it should be required_missing
    assert report.is_ready is False
    assert report.all_items[0].status == FieldReadinessStatus.REQUIRED_MISSING


def test_profile_writeback_synchronizer_sync_field(tmp_path: Path, sample_profile: CandidateProfile):
    profile_file = tmp_path / "profile.yaml"
    profile_dict = sample_profile.model_dump(mode="json", exclude_none=True)
    profile_file.write_text(yaml.safe_dump(profile_dict, allow_unicode=True), encoding="utf-8")

    # Update existing nested field
    ProfileWritebackSynchronizer.sync_field(profile_file, "contact.current_city", "深圳")
    # Add new nested field
    ProfileWritebackSynchronizer.sync_field(profile_file, "soe_extended.political_status", "中共党员")

    updated_data = yaml.safe_load(profile_file.read_text(encoding="utf-8"))
    assert updated_data["contact"]["current_city"] == "深圳"
    assert updated_data["soe_extended"]["political_status"] == "中共党员"

    # Validate resulting CandidateProfile
    reloaded = CandidateProfile.model_validate(updated_data)
    assert reloaded.contact.current_city == "深圳"
    assert reloaded.soe_extended is not None
    assert reloaded.soe_extended.political_status == "中共党员"


def test_profile_writeback_synchronizer_missing_file_raises(tmp_path: Path):
    missing_file = tmp_path / "not_found.yaml"
    with pytest.raises(FileNotFoundError):
        ProfileWritebackSynchronizer.sync_field(missing_file, "identity.name", "李四")


def test_profile_writeback_synchronizer_invalid_keys_raises(tmp_path: Path, sample_profile: CandidateProfile):
    profile_file = tmp_path / "profile.yaml"
    profile_dict = sample_profile.model_dump(mode="json", exclude_none=True)
    profile_file.write_text(yaml.safe_dump(profile_dict, allow_unicode=True), encoding="utf-8")

    # Array indexing should be rejected
    with pytest.raises(ValueError, match="Array-indexed writeback is not supported"):
        ProfileWritebackSynchronizer.sync_field(profile_file, "education[0].school_name", "清华")

    # Invalid root key should be rejected
    with pytest.raises(ValueError, match="Invalid profile root key: 'unknown_root'"):
        ProfileWritebackSynchronizer.sync_field(profile_file, "unknown_root.field", "value")
