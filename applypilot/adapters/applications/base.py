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
                can_handle = await filler.can_handle(element, field_info)
            except Exception:
                continue

            if can_handle:
                try:
                    try:
                        return await filler.fill(page, element, value, field_info=field_info)
                    except TypeError:
                        return await filler.fill(page, element, value)
                except Exception:
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

    async def is_login_page(self, page: Any) -> bool:
        """Detect an authentication gate without mistaking a header login link for it."""
        if not page or not hasattr(page, "execute_unsafe_script"):
            return False
        result = await page.execute_unsafe_script(
            "Detect login page signals",
            """() => {
                const visible = el => !!el.getClientRects().length
                    && getComputedStyle(el).visibility !== 'hidden';
                const text = (document.body ? document.body.innerText : '') || '';
                const strongLoginText = /(请先登录|扫码登录|微信扫码|账号密码登录|短信登录|登录后投递|验证码登录)/i.test(text);
                const authInputs = Array.from(document.querySelectorAll(
                    'input[type=password], input[name*=password], input[name*=pwd], input[placeholder*=密码], input[placeholder*=验证码]'
                )).filter(visible);
                const loginFormButton = Array.from(document.querySelectorAll(
                    'form button, form input[type=submit], [role=dialog] button, [role=dialog] input[type=submit]'
                )).some(el => visible(el) && /登录|sign in|log in/i.test((el.textContent || el.value || '').trim()));
                return strongLoginText || authInputs.length > 0 || loginFormButton;
            }""",
        )
        return result is True
