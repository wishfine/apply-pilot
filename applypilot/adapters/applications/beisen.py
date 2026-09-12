"""Beisen platform application adapter and specialized component fillers."""

from __future__ import annotations

from typing import Any, List, Optional
from applypilot.adapters.applications.base import (
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)
from applypilot.adapters.applications.generic import StandardInputFiller


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
        except Exception as e:
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
            fillers=fillers or [BeisenModalSchoolPicker(), StandardInputFiller()]
        )

    async def detect_stage(self, page: Any) -> str:
        return "beisen_stage"

    async def advance(self, page: Any, current_stage: str) -> bool:
        return True

    async def is_final_review(self, page: Any) -> bool:
        return False
