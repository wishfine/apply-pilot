"""Candidate profile models representing verifiable candidate facts."""

from enum import StrEnum
from typing import Optional
from pydantic import BaseModel, Field
from applypilot.domain.base import FactMetadata, PartialDate, SensitivityLevel, TriState


class EducationLevel(StrEnum):
    """Education level hierarchy."""

    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTOR = "doctor"


class ExperienceType(StrEnum):
    """Experience categories for campus and career profiles."""

    INTERNSHIP = "internship"  # 实习 (校招一等公民)
    FULL_TIME = "full_time"  # 全职工作
    RESEARCH = "research"  # 课题/科研
    STUDENT_ORG = "student_org"  # 学生骨干/社团
    VOLUNTEER = "volunteer"  # 志愿活动


class IdentityInfo(BaseModel):
    """Candidate personal identity fields."""

    name: Optional[str] = None
    pinyin_first_name: Optional[str] = None
    pinyin_last_name: Optional[str] = None
    english_name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[PartialDate] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    ethnicity: Optional[str] = None  # 严禁默认汉族
    health_status: Optional[str] = None  # 严禁默认健康


class ContactInfo(BaseModel):
    """Candidate contact and emergency information."""

    mobile: Optional[str] = None
    email: Optional[str] = None
    current_city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class EducationRecord(BaseModel):
    """Academic degree and institution attendance record."""

    id: str  # 稳定 ID: edu_bachelor, edu_master
    school_name: str
    education_level: EducationLevel  # 学历层次: 本科 / 硕士
    academic_degree: Optional[str] = None  # 学位名称: 工学学士 / 工学硕士
    major: str
    department: Optional[str] = None
    start_date: PartialDate
    end_date: PartialDate
    gpa: Optional[float] = None
    gpa_scale: Optional[float] = None
    ranking_pct: Optional[str] = None
    is_first_degree: TriState = TriState.UNKNOWN
    is_highest_degree: TriState = TriState.UNKNOWN
    thesis_title: Optional[str] = None


class ExperienceRecord(BaseModel):
    """Work and internship experience record."""

    id: str  # 稳定 ID: exp_bytedance_intern
    experience_type: ExperienceType
    org_name: str
    department: Optional[str] = None
    title: str
    city: Optional[str] = None
    start_date: PartialDate
    end_date: Optional[PartialDate] = None
    description_bullets: list[str] = Field(default_factory=list)
    skills_used_ids: list[str] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    """Project record."""

    id: str  # 稳定 ID: proj_apply_pilot
    project_name: str
    role: str
    start_date: PartialDate
    end_date: Optional[PartialDate] = None
    summary: str
    description_bullets: list[str] = Field(default_factory=list)
    technologies_used_ids: list[str] = Field(default_factory=list)
    repo_url: Optional[str] = None


class SkillRecord(BaseModel):
    """Candidate verified or claimed skill."""

    skill_id: str  # skill_python, skill_financial_modeling
    name: str
    category: str  # "programming", "finance", "engineering", "language"
    proficiency: Optional[str] = None
    years_experience: Optional[float] = None


class AssetRecord(BaseModel):
    """Local attachment or credential artifact."""

    asset_id: str  # asset_resume_pdf, asset_transcript
    asset_type: str  # "resume_pdf" | "transcript" | "cet_cert"
    file_path: str  # 本地路径
    title: str
    related_fact_ids: list[str] = Field(default_factory=list)
    sensitivity: SensitivityLevel = SensitivityLevel.PERSONAL


class ChinaCampusContext(BaseModel):
    """Contextual academic and graduation facts for Chinese campus hiring."""

    graduation_year: Optional[int] = None
    graduation_month: Optional[int] = None
    employment_status: Optional[str] = None
    cet4_score: Optional[int] = None
    cet6_score: Optional[int] = None
    ielts_score: Optional[float] = None
    toefl_score: Optional[int] = None
    has_dispatch_qualification: TriState = TriState.UNKNOWN


class FamilyMember(BaseModel):
    """Family member details for SOE or background clearance."""

    id: str  # family_father, family_mother
    relation: str  # "父亲" / "母亲" / "配偶"
    name: str
    political_status: Optional[str] = None
    workplace: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None


class SOEExtendedInfo(BaseModel):
    """State-owned enterprise specific questionnaire details."""

    political_status: Optional[str] = None  # 严禁默认党员或团员
    join_party_date: Optional[PartialDate] = None
    native_place: Optional[str] = None
    household_registration: Optional[str] = None
    household_type: Optional[str] = None
    family_members: list[FamilyMember] = Field(default_factory=list)
    conflict_of_interest: TriState = TriState.UNKNOWN
    conflict_details: Optional[str] = None


class StoryRecord(BaseModel):
    """STAR behavioral question story repository."""

    story_id: str
    topic: str
    title: str
    situation: str
    task: str
    action: str
    result: str
    related_fact_ids: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Complete, verified factual ground truth profile of a candidate."""

    schema_version: str = "1.1.0"
    profile_id: str
    identity: IdentityInfo = Field(default_factory=IdentityInfo)
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: list[EducationRecord] = Field(default_factory=list)
    experiences: list[ExperienceRecord] = Field(default_factory=list)
    projects: list[ProjectRecord] = Field(default_factory=list)
    skills: list[SkillRecord] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)
    campus_context: ChinaCampusContext = Field(default_factory=ChinaCampusContext)
    soe_extended: Optional[SOEExtendedInfo] = None
    stories: list[StoryRecord] = Field(default_factory=list)
    fact_metadata: dict[str, FactMetadata] = Field(default_factory=dict)
