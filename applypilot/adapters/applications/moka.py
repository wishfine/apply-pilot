"""Moka platform application adapter and specialized component fillers."""

from __future__ import annotations

from typing import Any, List, Optional
from applypilot.adapters.applications.base import (
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)
from applypilot.adapters.applications.generic import (
    DateInputFiller,
    FileUploadFiller,
    NativeSelectFiller,
    RadioCheckboxFiller,
    StandardInputFiller,
)
async def _verify_selected_value(element: Any, expected: str) -> bool:
    from applypilot.modules.apply.normalizer import ValueKind, ValueNormalizerRegistry

    try:
        inspect_field = getattr(element, "inspect_field", None)
        if callable(inspect_field):
            state = await element.inspect_field()
            if isinstance(state, dict):
                observed = state.get("observed_value")
                if ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, observed, expected):
                    return True
    except Exception:
        pass
    try:
        if hasattr(element, "get_attribute"):
            observed = await element.get_attribute("value")
            return ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, observed, expected)
    except Exception:
        pass
    return False


class MokaSearchSelectFiller:
    """Component filler for Moka searchable dropdown selection fields."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type", "")).lower().replace("-", "_")
        widget = str(field_info.get("widget", "")).lower().replace("-", "_")
        return "search_select" in field_type or "search_select" in widget

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not (hasattr(element, "click") or hasattr(element, "type_text")):
            return FillResult(
                success=False,
                action_type="moka_search_select",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        val_str = "" if value is None else str(value)
        try:
            # If element provides interactive hooks (click, type_text), trigger them
            if hasattr(element, "click"):
                await element.click()
            if hasattr(element, "type_text"):
                await element.type_text(val_str)

            if not hasattr(page, "execute_unsafe_script"):
                return FillResult(
                    success=False,
                    action_type="moka_search_select",
                    observed_value=None,
                    verification_status="unverified",
                    error_code="SEARCH_OPTION_NOT_CONFIRMED",
                    recoverable=True,
                    needs_human=True,
                )
            selected = await page.execute_unsafe_script(
                "Select and verify Moka search result",
                """value => {
                    const visible = el => !!el.getClientRects().length
                        && getComputedStyle(el).visibility !== 'hidden';
                    const selectors = '[role=option], .moka-option, .moka-select-option, .ant-select-item-option';
                    const option = Array.from(document.querySelectorAll(selectors)).find(el =>
                        visible(el) && (el.textContent || '').trim() === value);
                    if (!option) return false;
                    option.click();
                    return true;
                }""",
                val_str,
            )
            if selected is not True or not await _verify_selected_value(element, val_str):
                return FillResult(
                    success=False,
                    action_type="moka_search_select",
                    observed_value=None,
                    verification_status="unverified",
                    error_code="SEARCH_OPTION_NOT_CONFIRMED",
                    recoverable=True,
                    needs_human=True,
                )
            return FillResult(
                success=True,
                action_type="moka_search_select",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="moka_search_select",
                observed_value=None,
                verification_status="unverified",
                error_code="SELECT_ERROR",
                recoverable=True,
            )


class MokaApplicationAdapter(BaseApplicationAdapter):
    """Application adapter for Moka ATS multi-field recruitment forms."""

    def __init__(self, fillers: Optional[List[ComponentFiller]] = None) -> None:
        super().__init__(
            fillers=fillers
            if fillers is not None
            else [
                MokaSearchSelectFiller(),
                FileUploadFiller(),
                DateInputFiller(),
                NativeSelectFiller(),
                RadioCheckboxFiller(),
                StandardInputFiller(),
            ]
        )


    async def detect_stage(self, page: Any) -> str:
        return "moka_form"

    async def advance(self, page: Any, current_stage: str) -> bool:
        return False

    async def is_final_review(self, page: Any) -> bool:
        if not page or not hasattr(page, "execute_unsafe_script"):
            return False
        result = await page.execute_unsafe_script(
            "Detect Moka final submission control",
            """() => Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]'))
                .some(el => el.getClientRects().length && !el.disabled && el.getAttribute('aria-disabled') !== 'true'
                    && getComputedStyle(el).visibility !== 'hidden'
                    && /^(提交|提交申请|确认提交|提交简历|Submit|Submit application)$/i.test((el.textContent || el.value || '').trim()))""",
        )
        return result is True
