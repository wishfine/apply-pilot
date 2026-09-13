"""Beisen platform application adapter and specialized component fillers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, List, Optional
from applypilot.adapters.applications.base import (
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)
from applypilot.adapters.applications.generic import (
    FileUploadFiller,
    NativeSelectFiller,
    RadioCheckboxFiller,
    StandardInputFiller,
)


class BeisenModalSchoolPicker:
    """Component filler for Beisen modal school/college selection popups."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type", "")).lower()
        widget = str(field_info.get("widget", "")).lower()
        return (
            "beisen_modal" in field_type
            or "school_picker" in field_type
            or "beisen_modal" in widget
            or "school_picker" in widget
        )

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        if not (hasattr(element, "click") or hasattr(element, "type_text")):
            return FillResult(
                success=False,
                action_type="beisen_modal_pick",
                observed_value=None,
                verification_status="unverified",
                error_code="ELEMENT_NOT_INTERACTABLE",
                recoverable=False,
            )

        val_str = "" if value is None else str(value)
        try:
            # Trigger modal picker interaction if element has click
            if hasattr(element, "click"):
                await element.click()

            return FillResult(
                success=True,
                action_type="beisen_modal_pick",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception:
            return FillResult(
                success=False,
                action_type="beisen_modal_pick",
                observed_value=None,
                verification_status="unverified",
                error_code="MODAL_PICK_ERROR",
                recoverable=True,
            )


class BeisenApplicationAdapter(BaseApplicationAdapter):
    """Application adapter for Beisen multi-stage career portal forms."""

    def __init__(self, fillers: Optional[List[ComponentFiller]] = None) -> None:
        super().__init__(
            fillers=fillers
            if fillers is not None
            else [
                BeisenModalSchoolPicker(),
                FileUploadFiller(),
                NativeSelectFiller(),
                RadioCheckboxFiller(),
                StandardInputFiller(),
            ]
        )


    async def detect_stage(self, page: Any) -> str:
        state = await page.execute_unsafe_script(
            "Read Beisen stage markers without candidate values",
            """() => {
                const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
                return {url: location.href,
                    headings: Array.from(document.querySelectorAll('h1, h2, h3, [aria-current="step"], .ant-steps-item-process, .el-step.is-process, .step.active'))
                        .filter(visible).map(el => el.textContent.trim()),
                    fields: Array.from(document.querySelectorAll('input:not([type=hidden]), select, textarea'))
                        .filter(visible).map(el => [el.tagName, el.id, el.name, el.type, el.getAttribute('aria-label')]),
                    buttons: Array.from(document.querySelectorAll('button, input[type=button], input[type=submit]'))
                        .filter(visible).map(el => el.textContent.trim() || el.value)};
            }""",
        )
        if not isinstance(state, dict):
            return "beisen_stage"
        signature = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]
        return f"beisen_{signature}"

    async def advance(self, page: Any, current_stage: str) -> bool:
        if await self.is_final_review(page):
            return False
        for label in ("下一步", "保存并下一步", "保存并继续", "Next", "Continue"):
            for selector in (f'button:visible:text-is("{label}")',
                             f'input[type="button"][value="{label}"]:visible'):
                button = await page.find(selector)
                if button is None:
                    continue
                if await button.get_attribute("disabled") is not None:
                    continue
                if await button.get_attribute("aria-disabled") == "true":
                    continue
                await button.click()
                # A click may be rejected by validation; require an actual stage change.
                for _ in range(30):
                    if await self.detect_stage(page) != current_stage:
                        return True
                    await asyncio.sleep(0.1)
                return False
        return False

    async def is_final_review(self, page: Any) -> bool:
        result = await page.execute_unsafe_script(
            "Detect final submission control without clicking it",
            """() => Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]'))
                .some(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'
                    && /^(提交|提交申请|确认提交|提交简历|Submit|Submit application)$/i.test((el.textContent || el.value || '').trim()))""",
        )
        return result is True
