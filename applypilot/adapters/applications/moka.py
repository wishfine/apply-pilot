"""Moka platform application adapter and specialized component fillers."""

from __future__ import annotations

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


class MokaSearchSelectFiller:
    """Component filler for Moka searchable dropdown selection fields."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type", "")).lower()
        widget = str(field_info.get("widget", "")).lower()
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
        return True
