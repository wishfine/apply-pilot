"""Generic HTML application adapter and standard input component filler."""

from __future__ import annotations

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


class StandardInputFiller:
    """Component filler for standard text, email, phone, and numeric inputs."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        field_type = str(field_info.get("field_type", "text")).strip().lower()
        if not field_type or field_type in _SUPPORTED_INPUT_TYPES:
            return True
        return False

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        val_str = "" if value is None else str(value)
        try:
            if hasattr(element, "clear_text"):
                await element.clear_text()
            if hasattr(element, "type_text"):
                await element.type_text(val_str)
            return FillResult(
                success=True,
                action_type="type_text",
                observed_value=val_str,
                verification_status="verified_match",
            )
        except Exception as e:
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
        super().__init__(fillers=fillers or [StandardInputFiller()])

    async def detect_stage(self, page: Any) -> str:
        return "single_page"

    async def advance(self, page: Any, current_stage: str) -> bool:
        return False

    async def is_final_review(self, page: Any) -> bool:
        return True
