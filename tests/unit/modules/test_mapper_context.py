import pytest
from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import (
    CandidateProfile,
    EducationLevel,
    EducationRecord,
    FamilyMember,
    IdentityInfo,
    ContactInfo,
    SOEExtendedInfo,
)
from applypilot.modules.apply import FieldMapper
from applypilot.modules.profile.resolver import ValueResolver


def test_mapper_family_member_context():
    # Direct label with family entity prefix
    r_father_name = FieldMapper.map_field("sig_f_name", "父亲姓名")
    assert r_father_name.profile_path == "soe_extended.family_members[father].name"

    r_father_phone = FieldMapper.map_field("sig_f_phone", "父亲联系电话")
    assert r_father_phone.profile_path == "soe_extended.family_members[father].phone"

    r_mother_phone = FieldMapper.map_field("sig_m_phone", "母亲联系电话")
    assert r_mother_phone.profile_path == "soe_extended.family_members[mother].phone"

    r_mother_workplace = FieldMapper.map_field("sig_m_wp", "母亲工作单位")
    assert r_mother_workplace.profile_path == "soe_extended.family_members[mother].workplace"

    # Family section without specific entity should NOT map to candidate identity
    r_section_ambiguous = FieldMapper.map_field(
        "sig_sec_name", "姓名", section_title="家庭成员信息"
    )
    assert r_section_ambiguous.profile_path != "identity.name"


def test_mapper_emergency_contact_context():
    # Emergency contact in section or label
    r_em_name = FieldMapper.map_field("sig_em_name", "姓名", section_title="紧急联系人")
    assert r_em_name.profile_path == "contact.emergency_contact_name"

    r_em_phone = FieldMapper.map_field("sig_em_phone", "联系电话", section_title="紧急联系人")
    assert r_em_phone.profile_path == "contact.emergency_contact_phone"


@pytest.mark.parametrize("label", ["导师姓名", "推荐人电话", "证明人邮箱", "实习城市"])
def test_mapper_does_not_map_third_party_context_to_candidate(label: str):
    result = FieldMapper.map_field("third_party", label)
    assert result.profile_path is None


def test_generic_attachment_label_requires_manual_mapping():
    assert FieldMapper.map_field("attachment", "上传附件", field_type="file").profile_path is None


def test_mapper_education_level_context():
    # Bachelor context
    r_bachelor_school = FieldMapper.map_field("sig_b_school", "本科毕业院校")
    assert r_bachelor_school.profile_path == "education[bachelor].school_name"

    r_bachelor_major = FieldMapper.map_field("sig_b_major", "本科就读专业")
    assert r_bachelor_major.profile_path == "education[bachelor].major"

    # Master context
    r_master_school = FieldMapper.map_field("sig_m_school", "硕士毕业院校")
    assert r_master_school.profile_path == "education[master].school_name"

    # Doctor context
    r_doctor_school = FieldMapper.map_field("sig_d_school", "博士院校")
    assert r_doctor_school.profile_path == "education[doctor].school_name"

    # Education section with explicit level
    r_sec_bachelor = FieldMapper.map_field("sig_sec_school", "学校名称", section_title="本科教育经历")
    assert r_sec_bachelor.profile_path == "education[bachelor].school_name"


def test_resolver_with_disambiguated_entities():
    profile = CandidateProfile(
        profile_id="cand_test_context",
        identity=IdentityInfo(name="张无忌", gender="male"),
        contact=ContactInfo(
            mobile="13800000001",
            email="zhangwuji@example.com",
            emergency_contact_name="谢逊",
            emergency_contact_phone="13900000002",
        ),
        education=[
            EducationRecord(
                id="edu_bachelor",
                school_name="北京理工大学",
                education_level=EducationLevel.BACHELOR,
                major="计算机科学与技术",
                start_date=PartialDate(year=2018, month=9),
                end_date=PartialDate(year=2022, month=6),
            ),
            EducationRecord(
                id="edu_master",
                school_name="清华大学",
                education_level=EducationLevel.MASTER,
                major="软件工程",
                start_date=PartialDate(year=2022, month=9),
                end_date=PartialDate(year=2025, month=6),
                is_highest_degree=TriState.YES,
            ),
        ],
        soe_extended=SOEExtendedInfo(
            family_members=[
                FamilyMember(
                    id="family_father",
                    relation="父亲",
                    name="张翠山",
                    phone="13700000003",
                    workplace="武当派",
                ),
                FamilyMember(
                    id="family_mother",
                    relation="母亲",
                    name="殷素素",
                    phone="13700000004",
                    workplace="天鹰教",
                ),
            ]
        ),
    )

    # 1. Candidate vs Family resolution
    assert ValueResolver.resolve(profile, None, "identity.name") == "张无忌"
    assert ValueResolver.resolve(profile, None, "soe_extended.family_members[father].name") == "张翠山"
    assert ValueResolver.resolve(profile, None, "soe_extended.family_members[mother].name") == "殷素素"
    assert ValueResolver.resolve(profile, None, "soe_extended.family_members[father].phone") == "13700000003"
    assert ValueResolver.resolve(profile, None, "soe_extended.family_members[mother].phone") == "13700000004"

    # 2. Highest vs Bachelor vs Master resolution
    assert ValueResolver.resolve(profile, None, "education[__HIGHEST__].school_name") == "清华大学"
    assert ValueResolver.resolve(profile, None, "education[master].school_name") == "清华大学"
    assert ValueResolver.resolve(profile, None, "education[bachelor].school_name") == "北京理工大学"
    assert ValueResolver.resolve(profile, None, "education[bachelor].major") == "计算机科学与技术"
