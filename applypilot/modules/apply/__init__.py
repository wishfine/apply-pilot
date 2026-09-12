"""Apply module containing typed value normalization, element matching, and form automation."""

from applypilot.domain.job import ApplicationStatus
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.modules.apply.mapper import FieldMapper, FieldMappingResult
from applypilot.modules.apply.readiness import (
    FieldReadinessItem,
    FieldReadinessStatus,
    FormRequirementDetector,
    ProfileWritebackSynchronizer,
    ReadinessAuditor,
    ReadinessReport,
)
from applypilot.modules.apply.normalizer import (
    ValueKind,
    ValueNormalizerRegistry,
    normalize_academic_degree,
    normalize_boolean,
    normalize_city,
    normalize_date,
    normalize_education_level,
    normalize_email,
    normalize_person_name,
    normalize_phone,
    normalize_plain_text,
    normalize_political_status,
)

__all__ = [
    "ApplicationStatus",
    "ApplyEngine",
    "FieldMapper",
    "FieldMappingResult",
    "FormRequirementDetector",
    "FieldReadinessStatus",
    "FieldReadinessItem",
    "ReadinessReport",
    "ReadinessAuditor",
    "ProfileWritebackSynchronizer",

    "ValueKind",
    "ValueNormalizerRegistry",
    "normalize_academic_degree",
    "normalize_boolean",
    "normalize_city",
    "normalize_date",
    "normalize_education_level",
    "normalize_email",
    "normalize_person_name",
    "normalize_phone",
    "normalize_plain_text",
    "normalize_political_status",
]

