"""Form requirement detection and readiness assessment for job application forms."""

from __future__ import annotations

from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Optional
from pydantic import BaseModel, Field
import yaml

from applypilot.domain.base import TriState
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.variant import ResumeVariant
from applypilot.modules.apply.normalizer import ValueKind, ValueNormalizerRegistry


def _is_meaningful_value(val: Any) -> bool:
    """Evaluate whether a value represents non-empty factual content."""
    if val is None:
        return False
    if val == TriState.UNKNOWN:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    if isinstance(val, (list, dict, set)) and len(val) == 0:
        return False
    return True


class FormRequirementDetector:
    """Sniffs whether a DOM form element represents a required field across recruitment ATS platforms."""

    _OPTIONAL_PATTERN = re.compile(
        r"选填|非必填|(\(|（|\[|【)\s*optional\s*(\)|）|\]|】)",
        re.IGNORECASE,
    )

    _CONTAINER_REQUIRED_CLASS_PATTERN = re.compile(
        r'class\s*=\s*["\'][^"\']*\b(is-required|required|form-required|item-required|ant-form-item-required)\b[^"\']*["\']',
        re.IGNORECASE,
    )

    _REQUIRED_INDICATOR_TAG_PATTERN = re.compile(
        r'<(?:span|em|i|b)[^>]*class\s*=\s*["\'][^"\']*\b(star|required|must)\b[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )

    @classmethod
    def is_field_required(
        cls,
        element_attrs: Optional[dict[str, Any]] = None,
        label: Optional[str] = None,
        outer_html: Optional[str] = None,
    ) -> bool:
        """Evaluate whether a form element is strictly required.

        Precedence order:
        1. Explicit optional downgrade (e.g. '(选填)', '(非必填)', '(optional)') -> returns False.
        2. HTML native attributes ('required', 'aria-required="true"') -> returns True.
        3. Label content ('*', '必填') -> returns True.
        4. Outer HTML container and ATS markers ('is-required', 'ant-form-item-required', '<span class="star">*</span>') -> returns True.
        5. Default fallback -> returns False.

        Args:
            element_attrs: Dictionary of DOM element attributes.
            label: Textual label associated with the field.
            outer_html: Surrounding outer HTML snippet of the form item.

        Returns:
            True if the field is determined to be required, False otherwise.
        """
        label_text = (str(label) if label is not None else "").strip()
        attrs = element_attrs or {}
        html_text = (str(outer_html) if outer_html is not None else "").strip()

        # 1. Explicit Optional Downgrade (Highest Precedence)
        if cls._OPTIONAL_PATTERN.search(label_text):
            return False

        # 2. HTML Native Attributes
        if "required" in attrs:
            val = attrs["required"]
            # Attributes can be True, "", "required", or non-empty string not equal to "false"
            if val is not False and str(val).strip().lower() != "false":
                return True

        aria_required = attrs.get("aria-required")
        if aria_required is True or (
            isinstance(aria_required, str) and aria_required.strip().lower() == "true"
        ):
            return True

        # 3. Label Content Indicators
        if "*" in label_text or "必填" in label_text:
            return True

        # 4. Outer HTML Container & ATS Class Markers
        if html_text:
            if cls._CONTAINER_REQUIRED_CLASS_PATTERN.search(html_text):
                return True
            if cls._REQUIRED_INDICATOR_TAG_PATTERN.search(html_text):
                return True

        # 5. Default Fallback
        return False


class FieldReadinessStatus(StrEnum):
    """Evaluation status of a form field's completeness."""

    FILLED = "filled"
    OPTIONAL_EMPTY = "optional_empty"
    REQUIRED_MISSING = "required_missing"
    CONFLICT = "conflict"


class FieldReadinessItem(BaseModel):
    """Detailed readiness assessment item for an individual form field."""

    field_sig: str
    label: str
    section_title: Optional[str] = None
    is_required: bool = False
    status: FieldReadinessStatus
    profile_path: Optional[str] = None
    observed_value: Optional[str] = None
    suggested_fix: Optional[str] = None


class ReadinessReport(BaseModel):
    """Aggregated assessment report for all scanned form fields on a stage/page."""

    is_ready: bool
    missing_required: list[FieldReadinessItem] = Field(default_factory=list)
    conflicting_fields: list[FieldReadinessItem] = Field(default_factory=list)
    total_fields: int = 0
    filled_fields: int = 0
    optional_empty_fields: int = 0
    all_items: list[FieldReadinessItem] = Field(default_factory=list)

    @property
    def blocking_fields(self) -> list[FieldReadinessItem]:
        """Fields that must be resolved before a person can review submission."""
        return [*self.missing_required, *self.conflicting_fields]


class ReadinessAuditor:
    """Audits scanned form fields against candidate profile and computes readiness status."""

    @classmethod
    def audit_fields(
        cls,
        scanned_fields: list[dict[str, Any]],
        profile: CandidateProfile,
        variant: Optional[ResumeVariant] = None,
    ) -> ReadinessReport:
        """Evaluate readiness status for a batch of scanned form fields.

        Args:
            scanned_fields: List of element metadata dicts detected on the current page.
            profile: Verified factual ground truth candidate profile.
            variant: Optional targeted resume variant for tailoring.

        Returns:
            ReadinessReport aggregating status and missing required fields.
        """
        all_items: list[FieldReadinessItem] = []

        for field in scanned_fields:
            label = str(field.get("label") or "").strip()
            field_sig = str(field.get("field_sig") or field.get("id") or label or "field")
            section_title = field.get("section_title")

            # Determine is_required
            if "is_required" in field and field["is_required"] is not None:
                is_required = bool(field["is_required"])
            else:
                is_required = FormRequirementDetector.is_field_required(
                    element_attrs=field.get("element_attrs", {}),
                    label=label,
                    outer_html=field.get("outer_html"),
                )

            mapped_path = field.get("mapped_path") or field.get("profile_path")
            observed_value = field.get("observed_value")
            if observed_value is None:
                observed_value = field.get("current_value")

            is_filled = False
            # 1. Check if observed DOM value is meaningful (e.g. 0, False, non-empty string)
            if _is_meaningful_value(observed_value) and field.get("is_valid") is not False:
                is_filled = True

            expected_value = field.get("expected_value")
            value_kind = field.get("value_kind", ValueKind.PLAIN_TEXT)
            expected_mismatch = False
            if expected_value is not None and _is_meaningful_value(observed_value):
                expected_mismatch = not ValueNormalizerRegistry.are_equivalent(
                    value_kind, str(observed_value), expected_value
                )
            fill_failed = bool(field.get("fill_failed"))
            disclosure_blocked = bool(field.get("disclosure_blocked"))

            # Native/custom browser validity is a hard safety signal even for
            # optional controls.  An invalid value must never be presented as
            # ready for human review.
            invalid_value = field.get("is_valid") is False

            # Determine status
            if disclosure_blocked or invalid_value or fill_failed or expected_mismatch:
                status = FieldReadinessStatus.CONFLICT
                if disclosure_blocked:
                    suggested_fix = f"'{label}' 当前已有值，但该字段被披露策略禁止，请在浏览器中清除或确认后再继续"
                elif invalid_value:
                    suggested_fix = f"'{label}' 当前值未通过网页校验，请在浏览器中修正"
                elif fill_failed:
                    suggested_fix = f"自动填写 '{label}' 未成功，请在浏览器中核对并手动处理"
                else:
                    suggested_fix = f"'{label}' 当前值与档案值不一致，请在浏览器中核对"
            elif is_filled:
                status = FieldReadinessStatus.FILLED
                suggested_fix = None
            elif is_required:
                status = FieldReadinessStatus.REQUIRED_MISSING
                if mapped_path:
                    suggested_fix = f"请在 profile.yaml 中配置 {mapped_path}"
                else:
                    suggested_fix = f"未映射字段 '{label}'，请在浏览器中手动填写或配置映射规则"
            else:
                status = FieldReadinessStatus.OPTIONAL_EMPTY
                suggested_fix = None

            item = FieldReadinessItem(
                field_sig=field_sig,
                label=label,
                section_title=section_title,
                is_required=is_required,
                status=status,
                profile_path=mapped_path,
                observed_value=str(observed_value) if observed_value is not None else None,
                suggested_fix=suggested_fix,
            )
            all_items.append(item)

        missing_required = [
            item for item in all_items if item.status == FieldReadinessStatus.REQUIRED_MISSING
        ]
        conflicting_fields = [
            item for item in all_items if item.status == FieldReadinessStatus.CONFLICT
        ]
        filled_fields = sum(
            1 for item in all_items if item.status == FieldReadinessStatus.FILLED
        )
        optional_empty_fields = sum(
            1 for item in all_items if item.status == FieldReadinessStatus.OPTIONAL_EMPTY
        )
        is_ready = len(missing_required) == 0 and len(conflicting_fields) == 0

        return ReadinessReport(
            is_ready=is_ready,
            missing_required=missing_required,
            conflicting_fields=conflicting_fields,
            total_fields=len(all_items),
            filled_fields=filled_fields,
            optional_empty_fields=optional_empty_fields,
            all_items=all_items,
        )


class ProfileWritebackSynchronizer:
    """Synchronizes user-provided facts back to local profile.yaml."""

    @classmethod
    def sync_field(
        cls,
        profile_path: Path,
        profile_path_key: str,
        value: Any,
    ) -> None:
        """Write a new or updated field value back into the local profile YAML file.

        Args:
            profile_path: Path to profile.yaml.
            profile_path_key: Dot-separated path key, e.g. 'contact.current_city'.
            value: Value to set.

        Raises:
            FileNotFoundError: If the profile file does not exist.
            ValueError: If profile_path_key contains array indexing or has an invalid root key.
            ValidationError: If the resulting profile schema is invalid.
        """
        path = Path(profile_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Profile file not found at: {path}")

        if "[" in profile_path_key or "]" in profile_path_key:
            raise ValueError(f"Array-indexed writeback is not supported: {profile_path_key}")

        keys = profile_path_key.strip().split(".")
        root_key = keys[0]
        if root_key not in CandidateProfile.model_fields:
            raise ValueError(f"Invalid profile root key: '{root_key}'")

        raw_content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_content) or {}
        if not isinstance(data, dict):
            data = {}

        curr = data
        for key in keys[:-1]:
            if key not in curr or not isinstance(curr[key], dict):
                curr[key] = {}
            curr = curr[key]
        curr[keys[-1]] = value

        # Validate with CandidateProfile schema
        CandidateProfile.model_validate(data)

        serialized = (
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            if path.suffix.lower() == ".json"
            else yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        )
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(serialized, encoding="utf-8")
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
        tmp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
