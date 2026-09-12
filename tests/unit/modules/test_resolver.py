import pytest
from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import (
    CandidateProfile,
    ContactInfo,
    EducationLevel,
    EducationRecord,
    ExperienceRecord,
    ExperienceType,
    FamilyMember,
    IdentityInfo,
    ProjectRecord,
    SkillRecord,
    SOEExtendedInfo,
)
from applypilot.domain.variant import ResumeVariant, VariantBullet, VariantProjectConfig
from applypilot.modules.profile.resolver import ValueResolver


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        profile_id="prof_001",
        identity=IdentityInfo(
            name="张三",
            english_name=None,
            birth_date=PartialDate(year=2000, month=8, day=15),
        ),
        contact=ContactInfo(
            mobile="13800138000",
            email="zhangsan@example.com",
            current_city="北京",
        ),
        education=[
            EducationRecord(
                id="edu_hs",
                school_name="北京第一高中",
                education_level=EducationLevel.HIGH_SCHOOL,
                major="理科",
                start_date=PartialDate(year=2015, month=9),
                end_date=PartialDate(year=2018, month=6),
                is_highest_degree=TriState.NO,
            ),
            EducationRecord(
                id="edu_bach",
                school_name="武汉大学",
                education_level=EducationLevel.BACHELOR,
                academic_degree="工学学士",
                major="软件工程",
                start_date=PartialDate(year=2018, month=9),
                end_date=PartialDate(year=2022, month=6),
                gpa=3.85,
                is_highest_degree=TriState.NO,
            ),
            EducationRecord(
                id="edu_mast",
                school_name="北京大学",
                education_level=EducationLevel.MASTER,
                academic_degree="理学硕士",
                major="计算机应用技术",
                start_date=PartialDate(year=2022, month=9),
                end_date=PartialDate(year=2025, month=6),
                gpa=3.92,
                is_highest_degree=TriState.YES,
            ),
        ],
        experiences=[
            ExperienceRecord(
                id="exp_1",
                experience_type=ExperienceType.INTERNSHIP,
                org_name="字节跳动",
                department="基础架构部",
                title="后端研发实习生",
                start_date=PartialDate(year=2023, month=6),
                end_date=PartialDate(year=2023, month=12),
                description_bullets=["开发分布式缓存组件", "优化RPC调用延迟"],
            )
        ],
        projects=[
            ProjectRecord(
                id="proj_1",
                project_name="ApplyPilot智能求职引擎",
                role="架构师与核心开发者",
                start_date=PartialDate(year=2024, month=1),
                end_date=None,
                summary="基于LLM和本地沙箱的自动化求职助理",
                description_bullets=["实现事实库语义寻址", "支持多变体简历求值"],
            )
        ],
        skills=[
            SkillRecord(
                skill_id="skill_python",
                name="Python",
                category="programming",
                proficiency="expert",
            )
        ],
        soe_extended=SOEExtendedInfo(
            political_status="共青团员",
            native_place="湖北省武汉市",
            family_members=[
                FamilyMember(
                    id="fam_father",
                    relation="父亲",
                    name="张大山",
                    political_status="群众",
                    workplace="某制造企业",
                ),
                FamilyMember(
                    id="fam_mother",
                    relation="母亲",
                    name="李小红",
                    political_status="中共党员",
                    workplace="某医院",
                ),
            ],
        ),
    )


@pytest.fixture
def sample_variant() -> ResumeVariant:
    return ResumeVariant(
        variant_id="backend_algo",
        profile_id="prof_001",
        target_job_type="后端开发工程师",
        headline="专注高并发分布式系统与大模型工程落地",
        selected_education_ids=["edu_mast", "edu_bach"],
        project_configs=[
            VariantProjectConfig(
                project_id="proj_1",
                selected=True,
                priority_order=1,
                bullets=[
                    VariantBullet(
                        text="主导设计并落地高并发分发模块，吞吐量提升200%",
                        source_fact_ids=["proj_1_bullet_1"],
                    )
                ],
            )
        ],
    )


# --------------------------------------------------------------------------
# 1. Direct dot-separated paths
# --------------------------------------------------------------------------

def test_resolve_direct_fields(sample_profile: CandidateProfile):
    assert ValueResolver.resolve(sample_profile, None, "identity.name") == "张三"
    assert ValueResolver.resolve(sample_profile, None, "contact.mobile") == "13800138000"
    assert ValueResolver.resolve(sample_profile, None, "contact.email") == "zhangsan@example.com"
    assert ValueResolver.resolve(sample_profile, None, "soe_extended.political_status") == "共青团员"
    assert ValueResolver.resolve(sample_profile, None, "soe_extended.native_place") == "湖北省武汉市"


def test_resolve_partial_date_formatting(sample_profile: CandidateProfile):
    # Birth date has year, month, day -> YYYY-MM-DD
    assert ValueResolver.resolve(sample_profile, None, "identity.birth_date") == "2000-08-15"


def test_resolve_none_and_missing_properties(sample_profile: CandidateProfile):
    # Explicit None field
    assert ValueResolver.resolve(sample_profile, None, "identity.english_name") is None
    # Intermediate None (when soe_extended is None)
    empty_prof = CandidateProfile(profile_id="p_empty")
    assert ValueResolver.resolve(empty_prof, None, "soe_extended.political_status") is None
    # Non-existent attribute
    assert ValueResolver.resolve(sample_profile, None, "identity.unknown_field") is None
    assert ValueResolver.resolve(sample_profile, None, "non_existent.path") is None


# --------------------------------------------------------------------------
# 2. Semantic selector: education[__HIGHEST__].<field>
# --------------------------------------------------------------------------

def test_resolve_highest_education_priority_1_is_highest_degree(sample_profile: CandidateProfile):
    # Marked with is_highest_degree == TriState.YES
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].school_name") == "北京大学"
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].academic_degree") == "理学硕士"
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].major") == "计算机应用技术"
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].gpa") == 3.92
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].start_date") == "2022-09"
    assert ValueResolver.resolve(sample_profile, None, "education[__HIGHEST__].end_date") == "2025-06"


def test_resolve_highest_education_priority_2_hierarchy():
    # When no record has is_highest_degree == YES, pick highest by hierarchy
    prof = CandidateProfile(
        profile_id="p2",
        education=[
            EducationRecord(
                id="edu_1",
                school_name="专科学校",
                education_level=EducationLevel.ASSOCIATE,
                major="软件",
                start_date=PartialDate(year=2016),
                end_date=PartialDate(year=2019),
            ),
            EducationRecord(
                id="edu_2",
                school_name="本科大学",
                education_level=EducationLevel.BACHELOR,
                major="计算机",
                start_date=PartialDate(year=2019),
                end_date=PartialDate(year=2021),
            ),
        ],
    )
    assert ValueResolver.resolve(prof, None, "education[__HIGHEST__].school_name") == "本科大学"


def test_resolve_highest_education_priority_2_tie_breaking_by_dates():
    # Same level, break tie by end_date.year then start_date.year
    prof = CandidateProfile(
        profile_id="p3",
        education=[
            EducationRecord(
                id="edu_m1",
                school_name="第一硕士大学",
                education_level=EducationLevel.MASTER,
                major="AI",
                start_date=PartialDate(year=2020),
                end_date=PartialDate(year=2022),
            ),
            EducationRecord(
                id="edu_m2",
                school_name="第二硕士大学",
                education_level=EducationLevel.MASTER,
                major="DS",
                start_date=PartialDate(year=2022),
                end_date=PartialDate(year=2024),
            ),
        ],
    )
    assert ValueResolver.resolve(prof, None, "education[__HIGHEST__].school_name") == "第二硕士大学"


def test_resolve_highest_education_priority_3_last_item_fallback():
    # Same level, same dates, falls back to last item in list
    prof = CandidateProfile(
        profile_id="p4",
        education=[
            EducationRecord(
                id="edu_b1",
                school_name="第一本科学校",
                education_level=EducationLevel.BACHELOR,
                major="CS",
                start_date=PartialDate(year=2018),
                end_date=PartialDate(year=2022),
            ),
            EducationRecord(
                id="edu_b2",
                school_name="第二本科学校",
                education_level=EducationLevel.BACHELOR,
                major="EE",
                start_date=PartialDate(year=2018),
                end_date=PartialDate(year=2022),
            ),
        ],
    )
    assert ValueResolver.resolve(prof, None, "education[__HIGHEST__].school_name") == "第二本科学校"


def test_resolve_highest_education_empty():
    prof = CandidateProfile(profile_id="p_empty")
    assert ValueResolver.resolve(prof, None, "education[__HIGHEST__].school_name") is None


# --------------------------------------------------------------------------
# 3. ID-based selector: <collection>[<entity_id>].<field>
# --------------------------------------------------------------------------

def test_resolve_by_entity_id(sample_profile: CandidateProfile):
    # education by id
    assert ValueResolver.resolve(sample_profile, None, "education[edu_mast].school_name") == "北京大学"
    assert ValueResolver.resolve(sample_profile, None, "education[edu_bach].school_name") == "武汉大学"

    # experiences by id, checking role alias to title
    assert ValueResolver.resolve(sample_profile, None, "experiences[exp_1].role") == "后端研发实习生"
    assert ValueResolver.resolve(sample_profile, None, "experiences[exp_1].title") == "后端研发实习生"
    assert ValueResolver.resolve(sample_profile, None, "experiences[exp_1].org_name") == "字节跳动"

    # projects by id, checking name alias to project_name
    assert ValueResolver.resolve(sample_profile, None, "projects[proj_1].name") == "ApplyPilot智能求职引擎"
    assert ValueResolver.resolve(sample_profile, None, "projects[proj_1].project_name") == "ApplyPilot智能求职引擎"

    # skills by skill_id
    assert ValueResolver.resolve(sample_profile, None, "skills[skill_python].name") == "Python"
    assert ValueResolver.resolve(sample_profile, None, "skills[skill_python].proficiency") == "expert"

    # family members with explicit path and shortcut path
    assert ValueResolver.resolve(sample_profile, None, "soe_extended.family_members[fam_father].relation") == "父亲"
    assert ValueResolver.resolve(sample_profile, None, "soe_extended.family_members[fam_father].name") == "张大山"
    assert ValueResolver.resolve(sample_profile, None, "family_members[fam_father].relation") == "父亲"
    assert ValueResolver.resolve(sample_profile, None, "family_members[fam_mother].political_status") == "中共党员"

    # Non-existent ID
    assert ValueResolver.resolve(sample_profile, None, "education[non_existent_id].school_name") is None


# --------------------------------------------------------------------------
# 4. Numeric index selector: <collection>[<int>].<field>
# --------------------------------------------------------------------------

def test_resolve_numeric_index(sample_profile: CandidateProfile):
    assert ValueResolver.resolve(sample_profile, None, "education[0].school_name") == "北京第一高中"
    assert ValueResolver.resolve(sample_profile, None, "education[-1].school_name") == "北京大学"
    assert ValueResolver.resolve(sample_profile, None, "experiences[0].description_bullets[0]") == "开发分布式缓存组件"

    # Out-of-bounds safe retrieval
    assert ValueResolver.resolve(sample_profile, None, "education[999].school_name") is None
    assert ValueResolver.resolve(sample_profile, None, "education[-999].school_name") is None


# --------------------------------------------------------------------------
# 5. Variant-based resolution
# --------------------------------------------------------------------------

def test_resolve_variant_fields(sample_profile: CandidateProfile, sample_variant: ResumeVariant):
    # None variant
    assert ValueResolver.resolve(sample_profile, None, "variant.headline") is None
    assert ValueResolver.resolve(sample_profile, None, "variant.target_job_type") is None

    # Direct variant fields
    assert ValueResolver.resolve(sample_profile, sample_variant, "variant.headline") == "专注高并发分布式系统与大模型工程落地"
    assert ValueResolver.resolve(sample_profile, sample_variant, "variant.target_job_type") == "后端开发工程师"
    assert ValueResolver.resolve(sample_profile, sample_variant, "variant.variant_id") == "backend_algo"

    # Project config lookup in variant
    bullets = ValueResolver.resolve(sample_profile, sample_variant, "variant.project_configs[proj_1].bullets")
    assert isinstance(bullets, list)
    assert len(bullets) == 1
    assert bullets[0].text == "主导设计并落地高并发分发模块，吞吐量提升200%"

    # Chained index into bullet text
    bullet_text = ValueResolver.resolve(
        sample_profile, sample_variant, "variant.project_configs[proj_1].bullets[0].text"
    )
    assert bullet_text == "主导设计并落地高并发分发模块，吞吐量提升200%"


# --------------------------------------------------------------------------
# 6. Safety & edge cases
# --------------------------------------------------------------------------

def test_safety_and_edge_cases(sample_profile: CandidateProfile):
    # Whitespace stripping
    assert ValueResolver.resolve(sample_profile, None, "  identity.name  ") == "张三"
    assert ValueResolver.resolve(sample_profile, None, "education[ edu_mast ].school_name") == "北京大学"

    # Empty and whitespace paths
    assert ValueResolver.resolve(sample_profile, None, "") is None
    assert ValueResolver.resolve(sample_profile, None, "   ") is None

    # Malformed paths
    assert ValueResolver.resolve(sample_profile, None, "education[") is None
    assert ValueResolver.resolve(sample_profile, None, "education[]") is None
    assert ValueResolver.resolve(sample_profile, None, "identity..name") is None
    assert ValueResolver.resolve(sample_profile, None, ".identity.name") is None
    assert ValueResolver.resolve(sample_profile, None, "identity.name.") is None
    assert ValueResolver.resolve(sample_profile, None, "[__HIGHEST__]") is None

    # Invalid input types
    assert ValueResolver.resolve(sample_profile, None, None) is None  # type: ignore
    assert ValueResolver.resolve(None, None, "identity.name") is None  # type: ignore
