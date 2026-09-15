"""Versioned request and response contracts for the local ApplyPilot API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from applypilot.domain.profile import CandidateProfile


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceLocation(ApiModel):
    document: str | None = None
    page: int | None = None
    quote: str | None = None
    start: int | None = None
    end: int | None = None


class FactEvidence(ApiModel):
    path: str
    value: Any = None
    source: SourceLocation
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False


class Conflict(ApiModel):
    path: str
    existing_value: Any = None
    incoming_value: Any = None
    reason: str


class ParseRequest(ApiModel):
    text: str | None = None
    base_profile: CandidateProfile | None = None
    source_name: str = "resume"
    source_sha256: str | None = None
    mode: Literal["new", "merge"] = "new"


class ParseResponse(ApiModel):
    request_id: str
    profile_draft: CandidateProfile
    facts: list[FactEvidence] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReconcileRequest(ApiModel):
    base_profile: CandidateProfile
    incoming_profile: CandidateProfile


class ReconcileResponse(ApiModel):
    request_id: str
    profile: CandidateProfile
    conflicts: list[Conflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PageFieldSnapshot(ApiModel):
    field_ref: str
    frame_id: int = 0
    label: str
    name: str = ""
    section: str | None = None
    record_group: str | None = None
    kind: str
    type: str = "text"
    required: bool = False
    value: str = ""
    options: list[str] = Field(default_factory=list)


class PageSectionSnapshot(ApiModel):
    id: str
    label: str
    active: bool = False


class PageSnapshot(ApiModel):
    url_origin: str
    title: str = ""
    platform_hint: str = "generic"
    active_section: str | None = None
    sections: list[PageSectionSnapshot] = Field(default_factory=list)
    fields: list[PageFieldSnapshot] = Field(default_factory=list)


class FormPolicy(ApiModel):
    fill_required_only: bool = True
    allow_sensitive_paths: list[str] = Field(default_factory=list)
    allow_remote_processing: bool = False


class FormPlanRequest(ApiModel):
    protocol_version: str = "1.0"
    request_id: str | None = None
    profile: CandidateProfile
    page: PageSnapshot
    policy: FormPolicy = Field(default_factory=FormPolicy)


class PlanEvidence(ApiModel):
    path: str | None = None
    reason: str
    source: SourceLocation | None = None


class PlanItem(ApiModel):
    field_ref: str
    decision: Literal["fill", "review", "skip"]
    required: bool
    value: str | None = None
    profile_path: str | None = None
    record_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    method: str
    reason: str
    evidence: list[PlanEvidence] = Field(default_factory=list)


class PlanSummary(ApiModel):
    fields: int
    fill: int
    review: int
    optional_skipped: int
    existing_skipped: int


class FormPlanResponse(ApiModel):
    request_id: str
    mapping_version: str
    profile_hash: str
    plan: list[PlanItem]
    summary: PlanSummary
    warnings: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class FeedbackRequest(ApiModel):
    field_signature: str = Field(min_length=1, max_length=256)
    section_signature: str | None = Field(default=None, max_length=256)
    control_kind: str = Field(min_length=1, max_length=64)
    options_signature: str | None = Field(default=None, max_length=256)
    corrected_profile_path: str = Field(min_length=1, max_length=512)
    mapping_version: str = Field(min_length=1, max_length=128)


class FeedbackResponse(ApiModel):
    accepted: bool
    message: str
