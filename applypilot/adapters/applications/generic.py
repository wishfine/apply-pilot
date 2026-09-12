"""Generic HTML application adapter and standard input component filler."""

from __future__ import annotations

import inspect
from pathlib import Path
import re
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

        path_obj = Path(path_str).expanduser() if path_str else Path("")
        if not path_str or not path_obj.is_file():
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


async def _get_attr(element: Any, name: str) -> Optional[str]:
    if not hasattr(element, "get_attribute"):
        return None
    try:
        val = element.get_attribute(name)
        if inspect.isawaitable(val):
            val = await val
        if isinstance(val, str):
            return val
        if isinstance(val, (int, float)):
            return str(val)
        return None
    except Exception:
        return None


async def _is_element_checked(element: Any) -> bool:
    if hasattr(element, "is_checked"):
        attr = getattr(element, "is_checked")
        if callable(attr):
            try:
                res = attr()
                if inspect.isawaitable(res):
                    res = await res
                if isinstance(res, bool):
                    return res
            except Exception:
                pass
        elif isinstance(attr, bool):
            return attr

    if hasattr(element, "get_attribute"):
        try:
            val = element.get_attribute("checked")
            if inspect.isawaitable(val):
                val = await val
            if isinstance(val, str):
                return val.lower() in ("true", "checked", "")
            if isinstance(val, bool):
                return val
        except Exception:
            pass
    return False


async def _get_element_text(element: Any) -> str:
    for method_name in ("get_text", "text_content", "inner_text"):
        if hasattr(element, method_name):
            try:
                fn = getattr(element, method_name)
                if callable(fn):
                    res = fn()
                    if inspect.isawaitable(res):
                        res = await res
                    if isinstance(res, str):
                        return res.strip()
            except Exception:
                pass
    return ""


def _option_matches(candidate: Optional[str], target: Any) -> bool:
    if candidate is None:
        return False
    cand_str = str(candidate).strip()
    if not cand_str:
        return False

    if hasattr(target, "value"):
        target_val = target.value
    else:
        target_val = target

    target_str = str(target_val).strip()

    from applypilot.modules.apply.normalizer import (
        ValueKind,
        ValueNormalizerRegistry,
    )

    # 1. Semantic equivalence across option-relevant ValueKinds
    for kind in (
        ValueKind.PLAIN_TEXT,
        ValueKind.EDUCATION_LEVEL,
        ValueKind.BOOLEAN,
        ValueKind.ENUM,
        ValueKind.POLITICAL_STATUS,
        ValueKind.ACADEMIC_DEGREE,
        ValueKind.CITY,
    ):
        try:
            if ValueNormalizerRegistry.are_equivalent(kind, cand_str, target_val):
                return True
        except Exception:
            pass

    # 2. Direct case-insensitive equality or discrete token match
    c_lower = cand_str.lower()
    t_lower = target_str.lower()
    if c_lower == t_lower:
        return True
    parts = [p.strip() for p in re.split(r"[\s/()（）\-_]+", c_lower) if p.strip()]
    if t_lower in parts:
        return True

    # 3. Chinese text containment (e.g. "硕士研究生" contains "硕士")
    if re.search(r"[\u4e00-\u9fff]", cand_str) and re.search(r"[\u4e00-\u9fff]", target_str):
        if len(target_str) >= 2 and (target_str in cand_str or cand_str in target_str):
            return True

    return False


class RadioCheckboxFiller:
    """Component filler for HTML radio buttons and checkboxes."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        type_attr = str(field_info.get("type") or "").strip().lower()
        return field_type in ("radio", "checkbox") or type_attr in ("radio", "checkbox")

    async def fill(
        self,
        page: Any,
        element: Any,
        value: Any,
        field_info: Optional[dict] = None,
    ) -> FillResult:
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

        elem_type = (await _get_attr(element, "type") or "").strip().lower()
        if not elem_type and field_info:
            elem_type = str(field_info.get("type") or field_info.get("field_type") or "").strip().lower()

        elem_val = await _get_attr(element, "value")
        elem_text = await _get_element_text(element)
        if not elem_text and field_info:
            elem_text = str(field_info.get("label") or "").strip()
        is_checked = await _is_element_checked(element)

        from applypilot.modules.apply.normalizer import normalize_boolean

        # Radio button handling
        if elem_type == "radio" or (
            elem_type != "checkbox"
            and normalize_boolean(value) is None
            and (elem_val is not None or elem_text)
        ):
            matches = False
            if elem_val is not None and _option_matches(elem_val, value):
                matches = True
            elif elem_text and _option_matches(elem_text, value):
                matches = True
            elif elem_val is None and not elem_text:
                matches = True

            if not matches:
                return FillResult(
                    success=True,
                    action_type="skip_mismatched_option",
                    observed_value=elem_val,
                    verification_status="unverified",
                )

            if is_checked:
                return FillResult(
                    success=True,
                    action_type="noop",
                    observed_value=val_str,
                    verification_status="verified_match",
                )

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

        # Checkbox handling: Boolean value
        expected_bool = normalize_boolean(value)
        if expected_bool is not None:
            if expected_bool is True:
                if not is_checked:
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
                else:
                    return FillResult(
                        success=True,
                        action_type="noop",
                        observed_value=val_str,
                        verification_status="verified_match",
                    )
            else:  # expected_bool is False
                if is_checked:
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
                else:
                    return FillResult(
                        success=True,
                        action_type="noop",
                        observed_value=val_str,
                        verification_status="verified_match",
                    )

        # Checkbox handling: Non-boolean string/choice
        if isinstance(value, (list, tuple, set)):
            should_be_checked = any(
                (elem_val is not None and _option_matches(elem_val, v))
                or (elem_text and _option_matches(elem_text, v))
                for v in value
            )
        else:
            should_be_checked = (
                (elem_val is not None and _option_matches(elem_val, value))
                or (elem_text and _option_matches(elem_text, value))
            )

        if elem_val is None and not elem_text:
            should_be_checked = True

        if should_be_checked:
            if not is_checked:
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
            else:
                return FillResult(
                    success=True,
                    action_type="noop",
                    observed_value=val_str,
                    verification_status="verified_match",
                )
        else:
            if is_checked:
                try:
                    await element.click()
                    return FillResult(
                        success=True,
                        action_type="click",
                        observed_value=str(elem_val or ""),
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
            else:
                return FillResult(
                    success=True,
                    action_type="skip_mismatched_option",
                    observed_value=elem_val,
                    verification_status="unverified",
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
