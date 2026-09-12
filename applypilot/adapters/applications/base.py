"""Base protocols, result models, and abstract adapters for form automation."""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel


class FillResult(BaseModel):
    """Structured result of a field-fill action."""

    success: bool
    action_type: str
    observed_value: Optional[str] = None
    verification_status: str = "unverified"  # "verified_match" | "conflict" | "unverified"
    error_code: Optional[str] = None  # "ELEMENT_NOT_FOUND" | "OPTION_MISMATCH" | "TIMEOUT" | etc.
    recoverable: bool = True
    needs_human: bool = False


@runtime_checkable
class ComponentFiller(Protocol):
    """Strategy protocol for handling specific DOM component interactions."""

    async def can_handle(self, element: Any, field_info: dict) -> bool:
        """Check if this filler can operate on the given element and field metadata."""
        ...

    async def fill(self, page: Any, element: Any, value: Any) -> FillResult:
        """Execute fill interaction on the element."""
        ...


@runtime_checkable
class ApplicationAdapter(Protocol):
    """Protocol for recruitment platform application flow adapters."""

    fillers: List[ComponentFiller]

    async def detect_stage(self, page: Any) -> str:
        """Detect current workflow stage of the application."""
        ...

    async def advance(self, page: Any, current_stage: str) -> bool:
        """Advance to the next stage/page in the application form."""
        ...

    async def is_final_review(self, page: Any) -> bool:
        """Check if the current page is the final review stage before submission."""
        ...

    async def fill_field(
        self, page: Any, element: Any, field_info: dict, value: Any
    ) -> FillResult:
        """Fill a field using the appropriate component filler."""
        ...


class BaseApplicationAdapter:
    """Base application adapter that implements strategy composition over component fillers."""

    def __init__(self, fillers: Optional[List[ComponentFiller]] = None) -> None:
        self.fillers: List[ComponentFiller] = list(fillers) if fillers is not None else []

    async def fill_field(
        self, page: Any, element: Any, field_info: dict, value: Any
    ) -> FillResult:
        """Delegate field filling to the first compatible component filler."""
        for filler in self.fillers:
            try:
                if await filler.can_handle(element, field_info):
                    return await filler.fill(page, element, value)
            except Exception as e:
                return FillResult(
                    success=False,
                    action_type="unknown",
                    error_code="FILLER_EXECUTION_ERROR",
                    observed_value=None,
                    verification_status="conflict",
                    recoverable=True,
                )

        return FillResult(
            success=False,
            action_type="none",
            error_code="NO_MATCHING_FILLER",
            recoverable=False,
        )

    async def detect_stage(self, page: Any) -> str:
        raise NotImplementedError("Subclasses must implement detect_stage")

    async def advance(self, page: Any, current_stage: str) -> bool:
        raise NotImplementedError("Subclasses must implement advance")

    async def is_final_review(self, page: Any) -> bool:
        raise NotImplementedError("Subclasses must implement is_final_review")
