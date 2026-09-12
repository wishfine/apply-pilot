import pytest
from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import (
    CandidateProfile,
    IdentityInfo,
    ContactInfo,
    EducationRecord,
    EducationLevel,
    ExperienceRecord,
    ExperienceType,
    ProjectRecord,
    SkillRecord,
    AssetRecord,
    ChinaCampusContext,
    FamilyMember,
    SOEExtendedInfo,
    StoryRecord,
)
from applypilot.domain.variant import (
    ResumeVariant,
    VariantProjectConfig,
    VariantBullet,
    DisclosurePolicy,
)
from applypilot.domain.job import Job, ApplicationTarget


def test_candidate_profile_creation():
    prof = CandidateProfile(
        profile_id="cand_test_01",
        identity=IdentityInfo(name="张三", gender="男", birth_date=PartialDate(year=2001, month=5)),
        contact=ContactInfo(mobile="13800000000", email="zhangsan@example.com"),
        education=[
            EducationRecord(
                id="edu_master",
                school_name="清华大学",
                education_level=EducationLevel.MASTER,
                academic_degree="工学硕士",
                major="计算机科学与技术",
                start_date=PartialDate(year=2023, month=9),
                end_date=PartialDate(year=2026, month=6),
                is_highest_degree=TriState.YES,
            )
        ],
        soe_extended=SOEExtendedInfo(
            political_status="中共党员",
            native_place="湖北省武汉市",
            conflict_of_interest=TriState.NO,
            family_members=[
                FamilyMember(id="fam_father", relation="父亲", name="张父", workplace="某单位")
            ]
        )
    )
    assert prof.identity.name == "张三"
    assert prof.education[0].education_level == EducationLevel.MASTER
    assert prof.soe_extended.conflict_of_interest == TriState.NO


def test_resume_variant_bullet_traceability():
    bullet = VariantBullet(
        text="负责核心架构重构，吞吐提升 30%",
        source_fact_ids=["exp_bytedance_intern"],
        generated_by="user",
        verified=True
    )
    assert bullet.source_fact_ids == ["exp_bytedance_intern"]


def test_job_and_application_target():
    job = Job(
        job_id="job_123",
        external_job_id="bytedance_campus_999",
        title="算法工程师",
        company_name="字节跳动",
        description_raw="负责大模型算法研发",
        source_channel="bytedance",
        source_url="https://jobs.bytedance.com/campus/job/999",
        apply_url="https://jobs.bytedance.com/campus/job/999",
        recruitment_cycle="2027-campus-autumn"
    )
    target = ApplicationTarget(
        target_id="target_001",
        job=job,
        platform_type="company",
        provider="bytedance",
        assigned_variant_id="algo_specialist"
    )
    assert target.job.external_job_id == "bytedance_campus_999"
    assert target.disclosure_policy.allow_sensitive is False


def test_education_level_and_experience_type_enums():
    assert EducationLevel.HIGH_SCHOOL == "high_school"
    assert EducationLevel.ASSOCIATE == "associate"
    assert EducationLevel.BACHELOR == "bachelor"
    assert EducationLevel.MASTER == "master"
    assert EducationLevel.DOCTOR == "doctor"

    assert ExperienceType.INTERNSHIP == "internship"
    assert ExperienceType.FULL_TIME == "full_time"
    assert ExperienceType.RESEARCH == "research"
    assert ExperienceType.STUDENT_ORG == "student_org"
    assert ExperienceType.VOLUNTEER == "volunteer"


def test_candidate_profile_defaults():
    profile = CandidateProfile(profile_id="cand_default")
    assert profile.schema_version == "1.1.0"
    assert profile.identity.name is None
    assert profile.contact.mobile is None
    assert profile.education == []
    assert profile.experiences == []
    assert profile.projects == []
    assert profile.skills == []
    assert profile.assets == []
    assert profile.campus_context.has_dispatch_qualification == TriState.UNKNOWN
    assert profile.soe_extended is None
    assert profile.stories == []
    assert profile.fact_metadata == {}


def test_project_skill_asset_story_records():
    proj = ProjectRecord(
        id="proj_001",
        project_name="ApplyPilot",
        role="Core Developer",
        start_date=PartialDate(year=2026, month=1),
        summary="AI-assisted campus job application toolkit",
        description_bullets=["Built domain models"],
        technologies_used_ids=["skill_python"],
    )
    assert proj.project_name == "ApplyPilot"
    assert proj.technologies_used_ids == ["skill_python"]

    skill = SkillRecord(
        skill_id="skill_python",
        name="Python",
        category="programming",
        proficiency="expert",
        years_experience=3.5,
    )
    assert skill.skill_id == "skill_python"

    asset = AssetRecord(
        asset_id="asset_resume_pdf",
        asset_type="resume_pdf",
        file_path="/path/to/resume.pdf",
        title="Resume 2026",
    )
    assert asset.asset_id == "asset_resume_pdf"

    story = StoryRecord(
        story_id="story_001",
        topic="leadership",
        title="Led architecture revamp",
        situation="System bottleneck",
        task="Redesign domain layer",
        action="Introduced strict Pydantic schemas",
        result="Zero schema drift",
        related_fact_ids=["exp_001"],
    )
    assert story.topic == "leadership"
    assert story.related_fact_ids == ["exp_001"]


def test_resume_variant_creation_and_config():
    variant = ResumeVariant(
        variant_id="algo_specialist",
        profile_id="cand_test_01",
        target_job_type="algorithm",
        headline="AI Algorithm Engineer",
        selected_education_ids=["edu_master"],
        selected_experience_ids=["exp_bytedance_intern"],
        project_configs=[
            VariantProjectConfig(
                project_id="proj_001",
                selected=True,
                priority_order=1,
                bullets=[
                    VariantBullet(
                        text="Optimized transformer inference speed by 40%",
                        source_fact_ids=["proj_001_bullet_1"],
                    )
                ],
            )
        ],
        highlighted_skill_ids=["skill_python"],
    )
    assert variant.variant_id == "algo_specialist"
    assert len(variant.project_configs[0].bullets) == 1
    assert variant.project_configs[0].bullets[0].generated_by == "user"


def test_disclosure_policy_defaults_and_blocking():
    policy = DisclosurePolicy()
    assert policy.allow_sensitive is False
    assert policy.disclose_family is False
    assert policy.disclose_political is False
    assert policy.blocked_field_paths == set()

    custom_policy = DisclosurePolicy(
        allow_sensitive=True,
        disclose_family=False,
        disclose_political=True,
        blocked_field_paths={"identity.id_number", "contact.emergency_contact_phone"},
    )
    assert custom_policy.allow_sensitive is True
    assert "identity.id_number" in custom_policy.blocked_field_paths


def test_bullet_requires_source_fact_ids():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VariantBullet(text="invalid bullet without facts")

    with pytest.raises(ValidationError):
        VariantBullet(text="invalid bullet with empty facts", source_fact_ids=[])


def test_domain_package_exports():
    import applypilot.domain as domain

    expected_exports = [
        "CandidateProfile",
        "IdentityInfo",
        "ContactInfo",
        "EducationRecord",
        "EducationLevel",
        "ExperienceRecord",
        "ExperienceType",
        "ProjectRecord",
        "SkillRecord",
        "AssetRecord",
        "ChinaCampusContext",
        "FamilyMember",
        "SOEExtendedInfo",
        "StoryRecord",
        "ResumeVariant",
        "VariantProjectConfig",
        "VariantBullet",
        "DisclosurePolicy",
        "Job",
        "ApplicationTarget",
        "FactMetadata",
        "FieldPolicy",
        "LogStrategy",
        "PartialDate",
        "SensitivityLevel",
        "TriState",
    ]
    for export_name in expected_exports:
        assert hasattr(domain, export_name), f"Missing export: {export_name}"


def test_profile_and_variant_serialization_roundtrip():
    prof = CandidateProfile(
        profile_id="cand_ser_01",
        identity=IdentityInfo(name="李四"),
        education=[
            EducationRecord(
                id="edu_bach",
                school_name="北京大学",
                education_level=EducationLevel.BACHELOR,
                major="软件工程",
                start_date=PartialDate(year=2020, month=9),
                end_date=PartialDate(year=2024, month=6),
            )
        ],
    )
    raw_dict = prof.model_dump()
    recovered = CandidateProfile.model_validate(raw_dict)
    assert recovered.profile_id == prof.profile_id
    assert recovered.identity.name == "李四"
    assert recovered.education[0].school_name == "北京大学"
    assert recovered.education[0].education_level == EducationLevel.BACHELOR

