"""Presentation strategies (ResumeVariant) and disclosure policies."""

from pydantic import BaseModel, Field


class VariantBullet(BaseModel):
    """Fact-traceable bullet point configured for a resume variant."""

    text: str
    source_fact_ids: list[str] = Field(..., description="必须显式关联主事实库经历或bullet ID")
    generated_by: str = "user"  # "user" | "llm_polished"
    verified: bool = True


class VariantProjectConfig(BaseModel):
    """Configuration and tailored bullets for a project in a resume variant."""

    project_id: str
    selected: bool = True
    priority_order: int = 0
    bullets: list[VariantBullet] = Field(default_factory=list)


class ResumeVariant(BaseModel):
    """A tailored resume variant configuration mapped to target job types."""

    variant_id: str  # 如 "algo_specialist", "backend_dev"
    profile_id: str
    target_job_type: str
    headline: str
    selected_education_ids: list[str] = Field(default_factory=list)
    selected_experience_ids: list[str] = Field(default_factory=list)
    project_configs: list[VariantProjectConfig] = Field(default_factory=list)
    highlighted_skill_ids: list[str] = Field(default_factory=list)


class DisclosurePolicy(BaseModel):
    """Per-application disclosure gate policy for sensitive or private data."""

    allow_sensitive: bool = False
    disclose_family: bool = False
    disclose_political: bool = False
    blocked_field_paths: set[str] = Field(default_factory=set)
