"""Generic HTML application adapter and standard input component filler."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional
from applypilot.adapters.applications.base import (
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)

_SUPPORTED_INPUT_TYPES = {
    "text",
    "email",
    "phone",
    "tel",
    "number",
    "standard_input",
    "input",
    "password",
    "url",
}


class FileUploadFiller:
    """Component filler for file upload input controls."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        type_attr = str(field_info.get("type") or "").strip().lower()
        widget = str(field_info.get("widget") or "").strip().lower()
        return (
            field_type in ("file", "upload")
            or type_attr == "file"
            or widget == "upload"
        )

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not hasattr(element, "set_files"):
            return FillResult(
                success=False,
                action_type="set_files",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        if isinstance(value, (list, tuple)):
            if not value:
                return FillResult(
                    success=False,
                    action_type="set_files",
                    observed_value=None,
                    verification_status="unverified",
                    error_code="FILE_NOT_FOUND",
                    recoverable=False,
                )
            raw_val = value[0]
        else:
            raw_val = value

        if hasattr(raw_val, "file_path"):
            path_str = str(raw_val.file_path)
        else:
            path_str = str(raw_val) if raw_val is not None else ""

        path_obj = Path(path_str)
        if not path_str or not path_obj.exists():
            return FillResult(
                success=False,
                action_type="set_files",
                observed_value=None,
                verification_status="unverified",
                error_code="FILE_NOT_FOUND",
                recoverable=False,
            )

        try:
            await element.set_files([str(path_obj)])
            return FillResult(
                success=True,
                action_type="set_files",
                observed_value=str(path_obj),
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="set_files",
                observed_value=None,
                verification_status="unverified",
                error_code="FILE_UPLOAD_ERROR",
                recoverable=True,
            )


class NativeSelectFiller:
    """Component filler for HTML <select> dropdown elements."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        tag = str(field_info.get("tag") or field_info.get("tag_name") or "").strip().lower()
        return field_type == "select" or tag == "select"

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not hasattr(element, "select_option"):
            return FillResult(
                success=False,
                action_type="select_option",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        if hasattr(value, "value"):
            val_str = str(value.value)
        else:
            val_str = "" if value is None else str(value)

        try:
            await element.select_option(val_str)
            return FillResult(
                success=True,
                action_type="select_option",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="select_option",
                observed_value=None,
                verification_status="unverified",
                error_code="SELECT_ERROR",
                recoverable=True,
            )


class RadioCheckboxFiller:
    """Component filler for HTML radio buttons and checkboxes."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        type_attr = str(field_info.get("type") or "").strip().lower()
        return field_type in ("radio", "checkbox") or type_attr in ("radio", "checkbox")

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not hasattr(element, "click"):
            return FillResult(
                success=False,
                action_type="click",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        if hasattr(value, "value"):
            val_str = str(value.value)
        else:
            val_str = "" if value is None else str(value)

        try:
            await element.click()
            return FillResult(
                success=True,
                action_type="click",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="click",
                observed_value=None,
                verification_status="unverified",
                error_code="CLICK_ERROR",
                recoverable=True,
            )


class StandardInputFiller:
    """Component filler for standard text, email, phone, and numeric inputs."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "text").strip().lower()
        if not field_type or field_type in _SUPPORTED_INPUT_TYPES:
            return True
        return False

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not hasattr(element, "type_text"):
            return FillResult(
                success=False,
                action_type="type_text",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        val_str = "" if value is None else str(value)
        try:
            if hasattr(element, "clear_text"):
                await element.clear_text()
            await element.type_text(val_str)
            return FillResult(
                success=True,
                action_type="type_text",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="type_text",
                observed_value=None,
                verification_status="unverified",
                error_code="INPUT_ERROR",
                recoverable=True,
            )


class GenericApplicationAdapter(BaseApplicationAdapter):
    """Fallback generic adapter for standard single-page or unspecialized forms."""

    def __init__(self, fillers: Optional[List[ComponentFiller]] = None) -> None:
        super().__init__(
            fillers=fillers
            if fillers is not None
            else [
                FileUploadFiller(),
                NativeSelectFiller(),
                RadioCheckboxFiller(),
                StandardInputFiller(),
            ]
        )


    async def detect_stage(self, page: Any) -> str:
        return "single_page"

    async def advance(self, page: Any, current_stage: str) -> bool:
        return False

    async def is_final_review(self, page: Any) -> bool:
        return True
