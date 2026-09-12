"""Form requirement detection and readiness assessment for job application forms."""

from __future__ import annotations

import re
from typing import Any, Optional


class FormRequirementDetector:
    """Sniffs whether a DOM form element represents a required field across recruitment ATS platforms."""

    _OPTIONAL_PATTERN = re.compile(
        r"选填|非必填|(\(|（|\[|【)\s*optional\s*(\)|）|\]|】)",
        re.IGNORECASE,
    )

    _CONTAINER_REQUIRED_CLASS_PATTERN = re.compile(
        r'class\s*=\s*["\'][^"\']*\b(is-required|required|form-required|item-required|ant-form-item-required)\b[^"\']*["\']',
        re.IGNORECASE,
    )

    _REQUIRED_INDICATOR_TAG_PATTERN = re.compile(
        r'<(?:span|em|i|b)[^>]*class\s*=\s*["\'][^"\']*\b(star|required|must)\b[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )

    @classmethod
    def is_field_required(
        cls,
        element_attrs: Optional[dict[str, Any]] = None,
        label: Optional[str] = None,
        outer_html: Optional[str] = None,
    ) -> bool:
        """Evaluate whether a form element is strictly required.

        Precedence order:
        1. Explicit optional downgrade (e.g. '(选填)', '(非必填)', '(optional)') -> returns False.
        2. HTML native attributes ('required', 'aria-required="true"') -> returns True.
        3. Label content ('*', '必填') -> returns True.
        4. Outer HTML container and ATS markers ('is-required', 'ant-form-item-required', '<span class="star">*</span>') -> returns True.
        5. Default fallback -> returns False.

        Args:
            element_attrs: Dictionary of DOM element attributes.
            label: Textual label associated with the field.
            outer_html: Surrounding outer HTML snippet of the form item.

        Returns:
            True if the field is determined to be required, False otherwise.
        """
        label_text = (str(label) if label is not None else "").strip()
        attrs = element_attrs or {}
        html_text = (str(outer_html) if outer_html is not None else "").strip()

        # 1. Explicit Optional Downgrade (Highest Precedence)
        if cls._OPTIONAL_PATTERN.search(label_text):
            return False

        # 2. HTML Native Attributes
        if "required" in attrs:
            val = attrs["required"]
            # Attributes can be True, "", "required", or non-empty string not equal to "false"
            if val is not False and str(val).strip().lower() != "false":
                return True

        aria_required = attrs.get("aria-required")
        if aria_required is True or (
            isinstance(aria_required, str) and aria_required.strip().lower() == "true"
        ):
            return True

        # 3. Label Content Indicators
        if "*" in label_text or "必填" in label_text:
            return True

        # 4. Outer HTML Container & ATS Class Markers
        if html_text:
            if cls._CONTAINER_REQUIRED_CLASS_PATTERN.search(html_text):
                return True
            if cls._REQUIRED_INDICATOR_TAG_PATTERN.search(html_text):
                return True

        # 5. Default Fallback
        return False
