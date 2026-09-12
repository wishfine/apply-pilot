from enum import StrEnum
from typing import Optional
from pydantic import BaseModel, Field
from applypilot.domain.base import PartialDate
from applypilot.domain.profile import EducationLevel
from applypilot.domain.variant import DisclosurePolicy


class ApplicationStatus(StrEnum):
    """Business lifecycle status for a job application."""

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    READY_REVIEW = "ready_review"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class Job(BaseModel):

    """Job posting specification crawled or imported from external channels."""

    job_id: str
    external_job_id: Optional[str] = None  # 平台原有岗位ID，去重关键
    title: str
    company_name: str
    company_id: Optional[str] = None
    locations: list[str] = Field(default_factory=list)
    job_type: str = "campus"
    department: Optional[str] = None
    description_raw: str
    degree_required: Optional[EducationLevel] = None
    graduation_years: list[int] = Field(default_factory=list)
    majors_preferred: list[str] = Field(default_factory=list)
    source_channel: str  # "moka" | "beisen" | "nowcoder" | "url"
    source_url: str
    apply_url: str
    deadline: Optional[PartialDate] = None
    posted_at: Optional[PartialDate] = None
    recruitment_cycle: Optional[str] = None  # 如 "2027-campus-autumn"


class ApplicationTarget(BaseModel):
    """A configured target application intent binding a job with variant and policy."""

    target_id: str
    job: Job
    platform_type: Optional[str] = None  # "ats" | "company"
    provider: Optional[str] = None  # "moka" | "beisen" | "generic"
    final_form_url: Optional[str] = None  # 逐步探测补全
    assigned_variant_id: Optional[str] = None
    disclosure_policy: DisclosurePolicy = Field(default_factory=DisclosurePolicy)
