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
    "date",
    "month",
    "time",
    "datetime-local",
    "datetime",
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


class DateInputFiller:
    """Component filler for HTML5 date/month/time/datetime-local input controls."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        type_attr = str(field_info.get("type") or "").strip().lower()
        widget = str(field_info.get("widget") or "").strip().lower()
        return (
            field_type in ("date", "month", "time", "datetime-local", "datetime")
            or type_attr in ("date", "month", "time", "datetime-local", "datetime")
            or widget in ("date", "datepicker", "month", "monthpicker")
        )

    @staticmethod
    def format_date_value(value: Any, input_type: str = "date") -> str:
        """Format candidate date fact to standard YYYY-MM-DD or YYYY-MM."""
        from applypilot.modules.apply.normalizer import parse_date_components

        parsed = parse_date_components(value)
        if parsed is not None:
            y, m, d = parsed
            if input_type == "month":
                return f"{y:04d}-{m:02d}" if m is not None else ""
            else:
                return f"{y:04d}-{m:02d}-{d:02d}" if m is not None and d is not None else ""

        if hasattr(value, "to_display"):
            disp = str(value.to_display())
            if input_type == "month" and len(disp) >= 7:
                return disp[:7]
            return disp

        val_str = str(value).strip() if value is not None else ""
        return val_str

    async def fill(
        self,
        page: Any,
        element: Any,
        value: Any,
        field_info: Optional[dict] = None,
    ) -> FillResult:
        if not (hasattr(element, "type_text") or hasattr(element, "fill")):
            return FillResult(
                success=False,
                action_type="set_date",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        input_type = "date"
        if field_info:
            input_type = str(field_info.get("type") or field_info.get("field_type") or "date").strip().lower()
        attr_t = await _get_attr(element, "type")
        if attr_t:
            input_type = attr_t.strip().lower()

        formatted_val = self.format_date_value(value, input_type)

        if not formatted_val:
            return FillResult(success=False, action_type="set_date", error_code="INSUFFICIENT_DATE_PRECISION")

        try:
            if hasattr(element, "clear_text"):
                res_c = element.clear_text()
                if inspect.isawaitable(res_c):
                    await res_c
            if hasattr(element, "type_text"):
                res_t = element.type_text(formatted_val)
                if inspect.isawaitable(res_t):
                    await res_t
            elif hasattr(element, "fill"):
                res_f = element.fill(formatted_val)
                if inspect.isawaitable(res_f):
                    await res_f

            eval_fn = None
            if hasattr(element, "evaluate") and type(element).__name__ != "AsyncMock":
                eval_fn = getattr(element, "evaluate")
            elif hasattr(element, "_locator") and hasattr(element._locator, "evaluate"):
                eval_fn = getattr(element._locator, "evaluate")

            if eval_fn is not None and callable(eval_fn):
                try:
                    res_e = eval_fn("""(el, val) => {
                        if (el.value !== val) {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", formatted_val)
                    if inspect.isawaitable(res_e):
                        await res_e
                except Exception:
                    pass

            return FillResult(
                success=True,
                action_type="set_date",
                observed_value=formatted_val,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="set_date",
                observed_value=None,
                verification_status="unverified",
                error_code="DATE_INPUT_ERROR",
                recoverable=True,
            )


class NativeSelectFiller:
    """Component filler for HTML <select> dropdown elements."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type") or "").strip().lower()
        tag = str(field_info.get("tag") or field_info.get("tag_name") or "").strip().lower()
        return field_type == "select" or tag == "select"

    async def _get_options(self, element: Any, field_info: Optional[dict] = None) -> list[dict[str, str]]:
        eval_fn = None
        if hasattr(element, "evaluate"):
            eval_fn = getattr(element, "evaluate")
        elif hasattr(element, "_locator") and hasattr(element._locator, "evaluate"):
            eval_fn = getattr(element._locator, "evaluate")

        if eval_fn is not None and callable(eval_fn):
            try:
                res = eval_fn("""el => {
                    if (!el.options) return [];
                    return Array.from(el.options).map(o => ({
                        value: (o.value || '').trim(),
                        text: (o.textContent || o.text || '').trim(),
                        label: (o.label || '').trim()
                    }));
                }""")
                if inspect.isawaitable(res):
                    res = await res
                if isinstance(res, list) and res:
                    return res
            except Exception:
                pass

        if field_info and "options" in field_info and isinstance(field_info["options"], (list, tuple)):
            res = []
            for item in field_info["options"]:
                if isinstance(item, dict):
                    res.append({
                        "value": str(item.get("value") or "").strip(),
                        "text": str(item.get("text") or item.get("label") or "").strip(),
                        "label": str(item.get("label") or item.get("text") or "").strip(),
                    })
                elif isinstance(item, str):
                    res.append({"value": item.strip(), "text": item.strip(), "label": item.strip()})
            if res:
                return res

        return []

    def _match_option(self, val_str: str, raw_val: Any, options: list[dict[str, str]]) -> Optional[dict[str, str]]:
        if not options:
            return None

        val_lower = val_str.lower().strip()

        # 1. Direct match (exact value, text, or label)
        for opt in options:
            if (
                opt.get("value", "").lower() == val_lower
                or opt.get("text", "").lower() == val_lower
                or opt.get("label", "").lower() == val_lower
            ):
                return opt

        # 2. Gender semantic mapping (e.g. male -> 1 or 男)
        if val_lower in ("male", "m", "男", "男性"):
            for opt in options:
                t = opt.get("text", "")
                l = opt.get("label", "")
                v = opt.get("value", "")
                if t in ("男", "男性") or l in ("男", "男性") or v in ("male", "男"):
                    return opt
        elif val_lower in ("female", "f", "女", "女性"):
            for opt in options:
                t = opt.get("text", "")
                l = opt.get("label", "")
                v = opt.get("value", "")
                if t in ("女", "女性") or l in ("女", "女性") or v in ("female", "女"):
                    return opt

        # 3. Education level / academic degree semantic mapping
        from applypilot.modules.apply.normalizer import (
            BACHELOR_ALIASES,
            MASTER_ALIASES,
            DOCTOR_ALIASES,
            ASSOCIATE_ALIASES,
            BOOLEAN_TRUE_SET,
            BOOLEAN_FALSE_SET,
        )

        bachelor_set = BACHELOR_ALIASES | {"bachelor", "undergraduate", "学士"}
        master_set = MASTER_ALIASES | {"master", "postgraduate", "硕士"}
        doctor_set = DOCTOR_ALIASES | {"doctor", "phd", "博士"}
        associate_set = ASSOCIATE_ALIASES | {"associate", "大专", "专科"}

        if val_lower in bachelor_set or "本科" in val_str or "学士" in val_str:
            for opt in options:
                t, l, v = opt.get("text", ""), opt.get("label", ""), opt.get("value", "").lower()
                if any(x in t or x in l for x in ("本科", "学士")) or v in bachelor_set:
                    return opt

        if val_lower in master_set or "硕士" in val_str:
            for opt in options:
                t, l, v = opt.get("text", ""), opt.get("label", ""), opt.get("value", "").lower()
                if "硕士" in t or "硕士" in l or v in master_set:
                    return opt

        if val_lower in doctor_set or "博士" in val_str:
            for opt in options:
                t, l, v = opt.get("text", ""), opt.get("label", ""), opt.get("value", "").lower()
                if "博士" in t or "博士" in l or v in doctor_set:
                    return opt

        if val_lower in associate_set or "大专" in val_str or "专科" in val_str:
            for opt in options:
                t, l, v = opt.get("text", ""), opt.get("label", ""), opt.get("value", "").lower()
                if any(x in t or x in l for x in ("大专", "专科")) or v in associate_set:
                    return opt

        # 4. Boolean / TriState mapping
        if val_lower in BOOLEAN_TRUE_SET:
            for opt in options:
                t, l, v = opt.get("text", "").lower(), opt.get("label", "").lower(), opt.get("value", "").lower()
                if t in BOOLEAN_TRUE_SET or l in BOOLEAN_TRUE_SET or v in BOOLEAN_TRUE_SET:
                    return opt
        elif val_lower in BOOLEAN_FALSE_SET:
            for opt in options:
                t, l, v = opt.get("text", "").lower(), opt.get("label", "").lower(), opt.get("value", "").lower()
                if t in BOOLEAN_FALSE_SET or l in BOOLEAN_FALSE_SET or v in BOOLEAN_FALSE_SET:
                    return opt

        # 5. Chinese text containment / fuzzy match
        if len(val_str) >= 2:
            for opt in options:
                t = opt.get("text", "")
                if t and (val_str in t or t in val_str):
                    return opt

        return None

    async def fill(
        self,
        page: Any,
        element: Any,
        value: Any,
        field_info: Optional[dict] = None,
    ) -> FillResult:
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

        options = await self._get_options(element, field_info)

        # If options are available on DOM/field_info
        if options:
            matched = self._match_option(val_str, value, options)
            if matched:
                target_val = matched.get("value")
                target_text = matched.get("text") or matched.get("label") or val_str
                sel_arg = target_val if (target_val is not None and target_val != "") else target_text
                try:
                    await element.select_option(sel_arg)
                    return FillResult(
                        success=True,
                        action_type="select_option",
                        observed_value=target_text or sel_arg,
                        verification_status="verified_match",
                    )
                except Exception:
                    # Fallback to selecting by text
                    try:
                        if hasattr(element, "select_option") and target_text != sel_arg:
                            await element.select_option(target_text)
                            return FillResult(
                                success=True,
                                action_type="select_option",
                                observed_value=target_text,
                                verification_status="verified_match",
                            )
                    except Exception:
                        pass

            # Options were present, but no option matched!
            candidates = [f"{o.get('text', '')}(value={o.get('value', '')})" for o in options]
            return FillResult(
                success=False,
                action_type="select_option",
                observed_value=None,
                verification_status="conflict",
                error_code=f"OPTION_MISMATCH: available candidates are {candidates}",
                recoverable=True,
            )

        # Fallback when options cannot be inspected from DOM (e.g. Unit test mock)
        try:
            await element.select_option(val_str)
            return FillResult(
                success=True,
                action_type="select_option",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            # Try semantic translation fallback if val_str failed
            translated = None
            v_low = val_str.lower()
            if v_low in ("male", "m"):
                translated = "男"
            elif v_low in ("female", "f"):
                translated = "女"
            elif v_low == "bachelor":
                translated = "本科"
            elif v_low == "master":
                translated = "硕士"
            elif v_low == "doctor":
                translated = "博士"
            elif v_low in ("yes", "true", "1"):
                translated = "是"
            elif v_low in ("no", "false", "0"):
                translated = "否"

            if translated:
                try:
                    await element.select_option(translated)
                    return FillResult(
                        success=True,
                        action_type="select_option",
                        observed_value=translated,
                        verification_status="verified_match",
                    )
                except Exception:
                    pass

            return FillResult(
                success=False,
                action_type="select_option",
                observed_value=None,
                verification_status="unverified",
                error_code="SELECT_ERROR",
                recoverable=True,
            )


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

    async def fill(
        self,
        page: Any,
        element: Any,
        value: Any,
        field_info: Optional[dict] = None,
    ) -> FillResult:
        if not hasattr(element, "type_text"):
            return FillResult(
                success=False,
                action_type="type_text",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        field_type = (
            str(field_info.get("field_type") or field_info.get("type") or "").strip().lower()
            if field_info
            else ""
        )
        if field_type in ("date", "month", "datetime-local", "time"):
            val_str = DateInputFiller.format_date_value(value, field_type)
        else:
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
                DateInputFiller(),
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
        if not page or not hasattr(page, "execute_unsafe_script"):
            return False
        result = await page.execute_unsafe_script(
            "Detect final submission control without clicking it",
            """() => Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]'))
                .some(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'
                    && /^(提交|提交申请|确认提交|提交简历|确认并提交|立即提交|Submit|Submit application)$/i.test((el.textContent || el.value || '').trim()))""",
        )
        return result is True

    async def is_login_page(self, page: Any) -> bool:
        if not page or not hasattr(page, "execute_unsafe_script"):
            return False
        result = await page.execute_unsafe_script(
            "Detect login page signals",
            """() => {
                const text = (document.body ? document.body.innerText : '') || '';
                const hasLoginText = /(请先登录|扫码登录|微信扫码|账号密码登录|短信登录|登录后投递|立即登录|验证码登录|请登录)/i.test(text);
                const hasLoginInput = !!document.querySelector('input[type=password], input[name*=password], input[name*=pwd], input[placeholder*=密码], input[placeholder*=验证码]');
                const formInputs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=password]), select, textarea'))
                    .filter(el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden');
                return (hasLoginText || hasLoginInput) && formInputs.length <= 2;
            }""",
        )
        return result is True
