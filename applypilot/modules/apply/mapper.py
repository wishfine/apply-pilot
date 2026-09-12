"""Field mapping and decision hierarchy engine for application forms.

Implements tri-level decision engine:
1. Scoped CorrectionMemory (highest priority)
2. Canonical Exact Rules (confidence=1.0)
3. Semantic / Keyword Heuristics (confidence=0.85)
4. Unmapped Fallback (confidence=0.0)
"""

from __future__ import annotations

from typing import Any, NamedTuple, Optional, Sequence


class FieldMappingResult(NamedTuple):
    """Result of field mapping decision.

    NamedTuple subclass that supports both attribute access and tuple unpacking:
        path, method, conf = FieldMapper.map_field(...)
    """

    profile_path: Optional[str]
    method: str
    confidence: float


_TAGS_TO_REMOVE = (
    "(必填)",
    "（必填）",
    "(选填)",
    "（选填）",
    "(必填项)",
    "（必填项）",
    "(选填项)",
    "（选填项）",
    "(必)",
    "（必）",
    "(选)",
    "（选）",
)

_CHARS_TO_REMOVE = ("*", ":", "：", "•", "·")

CANONICAL_EXACT_RULES: dict[str, str] = {
    # 身份 (identity)
    "姓名": "identity.name",
    "英文名": "identity.english_name",
    "英文姓名": "identity.english_name",
    "性别": "identity.gender",
    "出生日期": "identity.birth_date",
    "生日": "identity.birth_date",
    "身份证号": "identity.id_number",
    "证件号": "identity.id_number",
    "身份证": "identity.id_number",
    "证件号码": "identity.id_number",
    # 联系方式 (contact)
    "手机号": "contact.mobile",
    "手机号码": "contact.mobile",
    "手机": "contact.mobile",
    "移动电话": "contact.mobile",
    "邮箱": "contact.email",
    "电子邮箱": "contact.email",
    "email": "contact.email",
    "现居城市": "contact.current_city",
    "居住城市": "contact.current_city",
    "当前城市": "contact.current_city",
    "现居住地": "contact.current_city",
    "所在地": "contact.current_city",
    "紧急联系人": "contact.emergency_contact_name",
    "紧急联系人姓名": "contact.emergency_contact_name",
    "紧急联系人电话": "contact.emergency_contact_phone",
    "紧急联系人手机": "contact.emergency_contact_phone",
    # 教育 (education)
    "毕业院校": "education[__HIGHEST__].school_name",
    "学校名称": "education[__HIGHEST__].school_name",
    "就读学校": "education[__HIGHEST__].school_name",
    "学校": "education[__HIGHEST__].school_name",
    "专业": "education[__HIGHEST__].major",
    "专业名称": "education[__HIGHEST__].major",
    "就读专业": "education[__HIGHEST__].major",
    "最高学历": "education[__HIGHEST__].education_level",
    "学历": "education[__HIGHEST__].education_level",
    "学历层次": "education[__HIGHEST__].education_level",
    "最高学位": "education[__HIGHEST__].academic_degree",
    "学位": "education[__HIGHEST__].academic_degree",
    "入学时间": "education[__HIGHEST__].start_date",
    "入学日期": "education[__HIGHEST__].start_date",
    "毕业时间": "education[__HIGHEST__].end_date",
    "毕业日期": "education[__HIGHEST__].end_date",
    "绩点": "education[__HIGHEST__].gpa",
    "gpa": "education[__HIGHEST__].gpa",
    "成绩绩点": "education[__HIGHEST__].gpa",
    # 国企扩展 (soe_extended)
    "政治面貌": "soe_extended.political_status",
    "籍贯": "soe_extended.native_place",
    "籍贯所在地": "soe_extended.native_place",
    "民族": "soe_extended.ethnicity",
}


def _clean_label(label: str) -> str:
    """Clean markers, punctuation, tags and whitespace from label."""
    if not label:
        return ""
    cleaned = label
    for tag in _TAGS_TO_REMOVE:
        cleaned = cleaned.replace(tag, "")
    for ch in _CHARS_TO_REMOVE:
        cleaned = cleaned.replace(ch, "")
    return "".join(cleaned.split()).lower()


def _extract_item_value(item: Any, *keys: str, default: Any = None) -> Any:
    """Retrieve attribute or dict key from item."""
    for key in keys:
        if isinstance(item, dict):
            if key in item and item[key] is not None:
                return item[key]
        elif hasattr(item, key):
            val = getattr(item, key)
            if val is not None:
                return val
    return default


class FieldMapper:
    """Three-tier field mapping engine with scoped memory priority."""

    @classmethod
    def map_field(
        cls,
        field_sig: str,
        normalized_label: str,
        section_title: Optional[str] = None,
        field_type: str = "text",
        options: Optional[Sequence[str]] = None,
        correction_memories: Optional[Sequence[Any]] = None,
    ) -> FieldMappingResult:
        """Map a form field to its canonical profile path.

        Decision Hierarchy:
        1. Scoped CorrectionMemory (method="memory")
        2. Canonical Exact Rules (method="exact_rule", conf=1.0)
        3. Semantic / Keyword Heuristics (method="semantic", conf=0.85)
        4. Unmapped Fallback (method="unmapped", conf=0.0)
        """
        clean_key = _clean_label(normalized_label)

        # -----------------------------------------------------------------
        # Tier 1: Scoped CorrectionMemory
        # -----------------------------------------------------------------
        if correction_memories:
            for mem in correction_memories:
                mem_label = _extract_item_value(
                    mem, "normalized_label", "label", "field_label"
                )
                if not mem_label:
                    continue

                if _clean_label(str(mem_label)) != clean_key:
                    continue

                # Check section scope constraint
                mem_section = _extract_item_value(
                    mem, "section_title", "section_signature", "section"
                )
                if mem_section:
                    mem_sec_str = str(mem_section).strip()
                    if mem_sec_str:
                        if (
                            not section_title
                            or str(section_title).strip() != mem_sec_str
                        ):
                            continue

                corrected_path = _extract_item_value(
                    mem,
                    "corrected_semantic_path",
                    "profile_path",
                    "corrected_path",
                )
                if not corrected_path:
                    continue

                raw_conf = _extract_item_value(mem, "confidence", default=1.0)
                try:
                    conf = float(raw_conf)
                except (TypeError, ValueError):
                    conf = 1.0

                return FieldMappingResult(
                    profile_path=str(corrected_path),
                    method="memory",
                    confidence=conf,
                )

        # -----------------------------------------------------------------
        # Tier 2: Canonical Exact Rules
        # -----------------------------------------------------------------
        if clean_key in CANONICAL_EXACT_RULES:
            return FieldMappingResult(
                profile_path=CANONICAL_EXACT_RULES[clean_key],
                method="exact_rule",
                confidence=1.0,
            )

        # -----------------------------------------------------------------
        # Tier 3: Semantic / Keyword Heuristics
        # -----------------------------------------------------------------
        if "紧急" in clean_key:
            if "手机" in clean_key or "电话" in clean_key:
                return FieldMappingResult(
                    profile_path="contact.emergency_contact_phone",
                    method="semantic",
                    confidence=0.85,
                )
            if "联系人" in clean_key or "姓名" in clean_key:
                return FieldMappingResult(
                    profile_path="contact.emergency_contact_name",
                    method="semantic",
                    confidence=0.85,
                )
        elif "手机" in clean_key or "电话" in clean_key:
            return FieldMappingResult(
                profile_path="contact.mobile",
                method="semantic",
                confidence=0.85,
            )

        if "邮箱" in clean_key or "email" in clean_key:
            return FieldMappingResult(
                profile_path="contact.email",
                method="semantic",
                confidence=0.85,
            )

        if "院校" in clean_key or "学校" in clean_key:
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].school_name",
                method="semantic",
                confidence=0.85,
            )

        if "专业" in clean_key:
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].major",
                method="semantic",
                confidence=0.85,
            )

        if "学历" in clean_key:
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].education_level",
                method="semantic",
                confidence=0.85,
            )

        if "学位" in clean_key:
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].academic_degree",
                method="semantic",
                confidence=0.85,
            )

        if "籍贯" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.native_place",
                method="semantic",
                confidence=0.85,
            )

        if "政治面貌" in clean_key or "党派" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.political_status",
                method="semantic",
                confidence=0.85,
            )

        if "身份证" in clean_key or "证件号" in clean_key:
            return FieldMappingResult(
                profile_path="identity.id_number",
                method="semantic",
                confidence=0.85,
            )

        if "出生日期" in clean_key or "生日" in clean_key or "出生年月" in clean_key:
            return FieldMappingResult(
                profile_path="identity.birth_date",
                method="semantic",
                confidence=0.85,
            )

        if "绩点" in clean_key or "gpa" in clean_key:
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].gpa",
                method="semantic",
                confidence=0.85,
            )

        if "民族" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.ethnicity",
                method="semantic",
                confidence=0.85,
            )

        if "城市" in clean_key or "居住地" in clean_key:
            return FieldMappingResult(
                profile_path="contact.current_city",
                method="semantic",
                confidence=0.85,
            )

        # -----------------------------------------------------------------
        # Tier 4: Unmapped Fallback
        # -----------------------------------------------------------------
        return FieldMappingResult(
            profile_path=None,
            method="unmapped",
            confidence=0.0,
        )
