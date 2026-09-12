from types import SimpleNamespace
import pytest

from applypilot.modules.apply import FieldMapper, FieldMappingResult


class DummyMemoryObject:
    def __init__(
        self,
        normalized_label: str,
        corrected_semantic_path: str,
        section_title: str | None = None,
        confidence: float = 1.0,
    ):
        self.normalized_label = normalized_label
        self.corrected_semantic_path = corrected_semantic_path
        self.section_title = section_title
        self.confidence = confidence


def test_field_mapping_result_namedtuple_and_unpacking():
    res = FieldMappingResult("identity.name", "exact_rule", 1.0)
    assert res.profile_path == "identity.name"
    assert res.method == "exact_rule"
    assert res.confidence == 1.0

    # Tuple unpacking
    path, method, conf = res
    assert path == "identity.name"
    assert method == "exact_rule"
    assert conf == 1.0

    # Index access
    assert res[0] == "identity.name"
    assert res[1] == "exact_rule"
    assert res[2] == 1.0


def test_exact_canonical_rules_all_standard_labels():
    test_cases = [
        ("姓名", "identity.name"),
        ("英文名", "identity.english_name"),
        ("英文姓名", "identity.english_name"),
        ("性别", "identity.gender"),
        ("出生日期", "identity.birth_date"),
        ("生日", "identity.birth_date"),
        ("身份证号", "identity.id_number"),
        ("证件号", "identity.id_number"),
        ("身份证", "identity.id_number"),
        ("证件号码", "identity.id_number"),
        ("手机号", "contact.mobile"),
        ("手机号码", "contact.mobile"),
        ("手机", "contact.mobile"),
        ("移动电话", "contact.mobile"),
        ("邮箱", "contact.email"),
        ("电子邮箱", "contact.email"),
        ("Email", "contact.email"),
        ("email", "contact.email"),
        ("现居城市", "contact.current_city"),
        ("居住城市", "contact.current_city"),
        ("当前城市", "contact.current_city"),
        ("现居住地", "contact.current_city"),
        ("所在地", "contact.current_city"),
        ("毕业院校", "education[__HIGHEST__].school_name"),
        ("学校名称", "education[__HIGHEST__].school_name"),
        ("就读学校", "education[__HIGHEST__].school_name"),
        ("学校", "education[__HIGHEST__].school_name"),
        ("专业", "education[__HIGHEST__].major"),
        ("专业名称", "education[__HIGHEST__].major"),
        ("就读专业", "education[__HIGHEST__].major"),
        ("最高学历", "education[__HIGHEST__].education_level"),
        ("学历", "education[__HIGHEST__].education_level"),
        ("学历层次", "education[__HIGHEST__].education_level"),
        ("最高学位", "education[__HIGHEST__].academic_degree"),
        ("学位", "education[__HIGHEST__].academic_degree"),
        ("入学时间", "education[__HIGHEST__].start_date"),
        ("入学日期", "education[__HIGHEST__].start_date"),
        ("毕业时间", "education[__HIGHEST__].end_date"),
        ("毕业日期", "education[__HIGHEST__].end_date"),
        ("绩点", "education[__HIGHEST__].gpa"),
        ("GPA", "education[__HIGHEST__].gpa"),
        ("成绩绩点", "education[__HIGHEST__].gpa"),
        ("政治面貌", "soe_extended.political_status"),
        ("籍贯", "soe_extended.native_place"),
        ("籍贯所在地", "soe_extended.native_place"),
        ("民族", "identity.ethnicity"),
        ("紧急联系人", "contact.emergency_contact_name"),
        ("紧急联系人姓名", "contact.emergency_contact_name"),
        ("紧急联系人电话", "contact.emergency_contact_phone"),
        ("紧急联系人手机", "contact.emergency_contact_phone"),
    ]

    for label, expected_path in test_cases:
        res = FieldMapper.map_field(
            field_sig=f"sig_{label}",
            normalized_label=label,
        )
        assert res.profile_path == expected_path, f"Failed for label: {label}"
        assert res.method == "exact_rule"
        assert res.confidence == 1.0


def test_label_cleaning_punctuation_and_tags():
    dirty_labels = [
        ("* 姓名 (必填) :", "identity.name"),
        ("（必填） 手机号 ： ", "contact.mobile"),
        ("电子邮箱 (选填)", "contact.email"),
        ("*最高学历（选填项）:", "education[__HIGHEST__].education_level"),
        ("  姓  名  ", "identity.name"),
        ("* 紧急联系人手机 : ", "contact.emergency_contact_phone"),
    ]

    for label, expected_path in dirty_labels:
        path, method, conf = FieldMapper.map_field(
            field_sig="sig_dirty",
            normalized_label=label,
        )
        assert path == expected_path, f"Failed for dirty label: {label}"
        assert method == "exact_rule"
        assert conf == 1.0


def test_scoped_correction_memory_priority_dict():
    fake_memories = [
        {
            "normalized_label": "姓名",
            "section_title": "基本信息",
            "corrected_semantic_path": "custom.special_name",
            "confidence": 0.98,
        }
    ]

    res = FieldMapper.map_field(
        field_sig="sig_name",
        normalized_label="姓名",
        section_title="基本信息",
        correction_memories=fake_memories,
    )
    assert res.profile_path == "custom.special_name"
    assert res.method == "memory"
    assert res.confidence == 0.98


def test_scoped_correction_memory_priority_object():
    obj_mem = DummyMemoryObject(
        normalized_label="最高学历",
        corrected_semantic_path="education[0].education_level",
        section_title="教育背景",
        confidence=0.95,
    )

    path, method, conf = FieldMapper.map_field(
        field_sig="sig_edu",
        normalized_label="最高学历",
        section_title="教育背景",
        correction_memories=[obj_mem],
    )
    assert path == "education[0].education_level"
    assert method == "memory"
    assert conf == 0.95


def test_memory_without_section_matches_any_section():
    fake_memories = [
        {
            "normalized_label": "毕业学校",
            "corrected_semantic_path": "education[0].school_name",
            "section_title": None,
            "confidence": 1.0,
        }
    ]

    res = FieldMapper.map_field(
        field_sig="sig_school",
        normalized_label="毕业学校",
        section_title="任意教育模块",
        correction_memories=fake_memories,
    )
    assert res.profile_path == "education[0].school_name"
    assert res.method == "memory"
    assert res.confidence == 1.0


def test_section_mismatch_falls_through_to_exact_rule():
    fake_memories = [
        {
            "normalized_label": "最高学历",
            "section_title": "工作履历",  # Mismatched section
            "corrected_semantic_path": "work[0].level",
            "confidence": 0.9,
        }
    ]

    # Target field is in "教育背景"
    path, method, conf = FieldMapper.map_field(
        field_sig="sig_edu",
        normalized_label="最高学历",
        section_title="教育背景",
        correction_memories=fake_memories,
    )
    # Falls through to exact rule
    assert path == "education[__HIGHEST__].education_level"
    assert method == "exact_rule"
    assert conf == 1.0


def test_section_mismatch_when_field_has_no_section():
    fake_memories = [
        {
            "normalized_label": "手机号码",
            "section_title": "联系信息",
            "corrected_semantic_path": "contact.backup_phone",
            "confidence": 0.9,
        }
    ]

    # Target field has no section_title provided
    path, method, conf = FieldMapper.map_field(
        field_sig="sig_phone",
        normalized_label="手机号码",
        section_title=None,
        correction_memories=fake_memories,
    )
    assert path == "contact.mobile"
    assert method == "exact_rule"
    assert conf == 1.0


def test_semantic_keyword_matching():
    cases = [
        ("本人手机", "contact.mobile"),
        ("联系电话", "contact.mobile"),
        ("个人邮箱", "contact.email"),
        ("企业email地址", "contact.email"),
        ("本科院校", "education[__HIGHEST__].school_name"),
        ("录取学校", "education[__HIGHEST__].school_name"),
        ("主修专业", "education[__HIGHEST__].major"),
        ("已获学历", "education[__HIGHEST__].education_level"),
        ("已获学位", "education[__HIGHEST__].academic_degree"),
        ("个人籍贯", "soe_extended.native_place"),
        ("党派归属", "soe_extended.political_status"),
        ("中共党员/政治面貌说明", "soe_extended.political_status"),
    ]

    for label, expected_path in cases:
        path, method, conf = FieldMapper.map_field(
            field_sig="sig_sem",
            normalized_label=label,
        )
        assert path == expected_path, f"Failed for semantic label: {label}"
        assert method == "semantic"
        assert conf == 0.85


def test_emergency_contact_does_not_mismatch_mobile():
    # Contains "电话" but also "紧急" -> should not map to contact.mobile
    res = FieldMapper.map_field(
        field_sig="sig_em_phone",
        normalized_label="紧急联系电话",
    )
    assert res.profile_path != "contact.mobile"


def test_unmapped_fallback():
    unmapped_labels = [
        "期望薪资",
        "自我介绍",
        "个人主页GitHub",
        "特长爱好",
        "12345678",
    ]

    for label in unmapped_labels:
        path, method, conf = FieldMapper.map_field(
            field_sig="sig_unk",
            normalized_label=label,
        )
        assert path is None
        assert method == "unmapped"
        assert conf == 0.0


def test_target_city_not_mapped_to_current_city():
    # Target / Desired job location cities must NOT map to current residence city
    target_city_labels = [
        "期望工作城市",
        "意向城市",
        "目标城市",
        "应聘城市",
        "工作城市",
    ]
    for label in target_city_labels:
        res = FieldMapper.map_field(
            field_sig="sig_target_city",
            normalized_label=label,
        )
        assert res.profile_path != "contact.current_city"


def test_semantic_name_gender_and_dates():
    # Variations of name, gender, and education dates
    assert FieldMapper.map_field("s1", "真实姓名").profile_path == "identity.name"
    assert FieldMapper.map_field("s2", "您的性别").profile_path == "identity.gender"
    assert FieldMapper.map_field("s3", "入学年月").profile_path == "education[__HIGHEST__].start_date"
    assert FieldMapper.map_field("s4", "预计毕业时间").profile_path == "education[__HIGHEST__].end_date"


def test_semantic_resume_upload_heuristics():
    test_labels = [
        "请上传您的个人简历",
        "上传中英文简历",
        "附件简历 (PDF)",
        "Please upload your resume",
        "Attach CV",
    ]
    for label in test_labels:
        res = FieldMapper.map_field("sig_resume", label)
        assert res.profile_path == "assets[asset_resume_pdf].file_path"
        assert res.method == "semantic"
        assert res.confidence == 0.85


def test_disabled_correction_memory_ignored():
    disabled_memory = [
        {
            "normalized_label": "手机号",
            "corrected_semantic_path": "custom.mobile",
            "enabled": False,
            "confidence": 1.0,
        }
    ]
    res = FieldMapper.map_field(
        field_sig="sig_m",
        normalized_label="手机号",
        correction_memories=disabled_memory,
    )
    # Since memory is disabled, falls through to exact rule
    assert res.profile_path == "contact.mobile"
    assert res.method == "exact_rule"

