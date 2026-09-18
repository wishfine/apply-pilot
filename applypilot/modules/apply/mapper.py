"""Field mapping and decision hierarchy engine for application forms.

Implements tri-level decision engine:
1. Scoped CorrectionMemory (highest priority)
2. Canonical Exact Rules (confidence=1.0)
3. Semantic / Keyword Heuristics (confidence=0.85)
4. Unmapped Fallback (confidence=0.0)
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
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
    "【必填】",
    "[必填]",
    "(选填)",
    "（选填）",
    "【选填】",
    "[选填]",
    "(必填项)",
    "（必填项）",
    "【必填项】",
    "(选填项)",
    "（选填项）",
    "【选填项】",
    "(必)",
    "（必）",
    "(选)",
    "（选）",
)

_CHARS_TO_REMOVE = ("*", ":", "：", "•", "·", "【", "】", "[", "]")

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
    "民族": "identity.ethnicity",
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
    "户口类型": "soe_extended.household_type",
    "户口性质": "soe_extended.household_type",
    "户籍所在地": "soe_extended.household_registration",
    "户籍地址": "soe_extended.household_registration",
    "户口所在地": "soe_extended.household_registration",
    "入党时间": "soe_extended.join_party_date",
    "入团时间": "soe_extended.join_party_date",
    "身高": "soe_extended.height_cm",
    "体重": "soe_extended.weight_kg",
    "血型": "soe_extended.blood_type",
    "左眼视力": "soe_extended.eyesight_left",
    "右眼视力": "soe_extended.eyesight_right",
    "犯罪记录": "soe_extended.has_criminal_record",
    "有无犯罪记录": "soe_extended.has_criminal_record",
    "处分记录": "soe_extended.has_disciplinary_record",
    "有无处分": "soe_extended.has_disciplinary_record",
    "是否服从分配": "soe_extended.can_relocate",
    "是否服从调剂": "soe_extended.can_relocate",
    "服从调剂": "soe_extended.can_relocate",
    "服从分配": "soe_extended.can_relocate",
    "期望薪资": "soe_extended.expected_salary",
    "期望月薪": "soe_extended.expected_salary",
    "期望年薪": "soe_extended.expected_salary",
    "最早到岗": "soe_extended.available_date",
    "到岗时间": "soe_extended.available_date",
    "最早到岗时间": "soe_extended.available_date",
    "推荐人": "soe_extended.referrer_name",
    "推荐人姓名": "soe_extended.referrer_name",
    "推荐人工号": "soe_extended.referrer_employee_id",
    "内推人": "soe_extended.referrer_name",
    "内推工号": "soe_extended.referrer_employee_id",
    "自我评价": "soe_extended.personal_statement",
    "个人陈述": "soe_extended.personal_statement",
    "个人简介": "soe_extended.personal_statement",
    "个人总结": "soe_extended.personal_statement",
    "兴趣爱好": "soe_extended.hobbies",
    "爱好特长": "soe_extended.hobbies",
    "特长": "soe_extended.strengths",
    "个人特长": "soe_extended.strengths",
    "个人优势": "soe_extended.strengths",
    "海外经历": "soe_extended.has_overseas_background",
    "有无海外经历": "soe_extended.has_overseas_background",
    "海外亲属": "soe_extended.overseas_relatives",
    "有无海外亲属": "soe_extended.overseas_relatives",
    "驾照": "soe_extended.driving_license",
    "驾驶证": "soe_extended.driving_license",
    "驾照类型": "soe_extended.driving_license",
    "计算机水平": "soe_extended.computer_proficiency",
    "计算机等级": "soe_extended.computer_proficiency",
    "普通话等级": "soe_extended.mandarin_level",
    "普通话水平": "soe_extended.mandarin_level",
    "出生地": "identity.birth_place",
    "出生地点": "identity.birth_place",
    "证件有效期": "identity.id_expiry_date",
    "身份证有效期": "identity.id_expiry_date",
    "邮编": "contact.postal_code",
    "邮政编码": "contact.postal_code",
    "家庭电话": "contact.home_phone",
    "固定电话": "contact.home_phone",
    "座机": "contact.home_phone",
    "紧急联系人关系": "contact.emergency_contact_relation",
    "与紧急联系人关系": "contact.emergency_contact_relation",
    "院校类型": "education[__HIGHEST__].school_type",
    "院校性质": "education[__HIGHEST__].school_type",
    "学校类型": "education[__HIGHEST__].school_type",
    "学习方式": "education[__HIGHEST__].study_mode",
    "学习形式": "education[__HIGHEST__].study_mode",
    "培养方式": "education[__HIGHEST__].study_mode",
    "班级": "education[__HIGHEST__].class_name",
    "所在班级": "education[__HIGHEST__].class_name",
    "学号": "education[__HIGHEST__].student_id",
    "健康状况": "identity.health_status",
    "婚姻状况": "identity.marital_status",
    "婚姻状态": "identity.marital_status",
    "证件类型": "identity.id_type",
    "国籍": "identity.nationality",
    "毕业年份": "campus_context.graduation_year",
    "四级成绩": "campus_context.cet4_score",
    "六级成绩": "campus_context.cet6_score",
    "四级分数": "campus_context.cet4_score",
    "六级分数": "campus_context.cet6_score",
    "cet4": "campus_context.cet4_score",
    "cet6": "campus_context.cet6_score",
    "雅思": "campus_context.ielts_score",
    "雅思成绩": "campus_context.ielts_score",
    "托福": "campus_context.toefl_score",
    "托福成绩": "campus_context.toefl_score",
    # 附件与简历 (assets)
    "上传简历": "assets[asset_resume_pdf].file_path",
    "简历附件": "assets[asset_resume_pdf].file_path",
    "简历上传": "assets[asset_resume_pdf].file_path",
    "个人简历": "assets[asset_resume_pdf].file_path",
    "附件简历": "assets[asset_resume_pdf].file_path",
    "简历": "assets[asset_resume_pdf].file_path",
    "resume": "assets[asset_resume_pdf].file_path",
    "cv": "assets[asset_resume_pdf].file_path",
}

TARGET_CITY_EXCLUDES = ("期望", "意向", "目标", "应聘", "首选", "备选", "工作")


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
    """Retrieve attribute or dict/Mapping key from item."""
    for key in keys:
        if isinstance(item, Mapping):
            if key in item and item[key] is not None:
                return item[key]
        elif hasattr(item, key):
            val = getattr(item, key)
            if val is not None:
                return val
    return default


def _options_signature(options: Optional[Sequence[Any]]) -> Optional[str]:
    """Return a stable signature for an option set when the set is observable."""
    if options is None:
        return None
    normalized: list[dict[str, str]] = []
    for option in options:
        if isinstance(option, Mapping):
            normalized.append({
                "value": _clean_label(str(option.get("value") or "")),
                "text": _clean_label(str(option.get("text") or "")),
                "label": _clean_label(str(option.get("label") or "")),
            })
        else:
            value = _clean_label(str(option))
            normalized.append({"value": value, "text": value, "label": value})
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
        current_options_signature = _options_signature(options)

        # -----------------------------------------------------------------
        # Tier 1: Scoped CorrectionMemory
        # -----------------------------------------------------------------
        if correction_memories:
            for mem in correction_memories:
                enabled = _extract_item_value(mem, "enabled", default=True)
                if enabled is False or enabled == 0:
                    continue

                mem_label = _extract_item_value(
                    mem, "normalized_label", "label", "field_label"
                )
                if not mem_label:
                    continue

                if _clean_label(str(mem_label)) != clean_key:
                    continue

                mem_field_type = _extract_item_value(mem, "field_type")
                if mem_field_type and str(mem_field_type).strip().lower() != field_type.strip().lower():
                    continue

                mem_options_signature = _extract_item_value(mem, "options_signature")
                if mem_options_signature:
                    if current_options_signature is None or str(mem_options_signature) != current_options_signature:
                        continue

                # Check section scope constraint with normalized comparison
                mem_section = _extract_item_value(
                    mem, "section_title", "section_signature", "section"
                )
                if mem_section:
                    mem_sec_clean = _clean_label(str(mem_section))
                    if mem_sec_clean:
                        if not section_title or _clean_label(str(section_title)) != mem_sec_clean:
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

        clean_sec = _clean_label(section_title) if section_title else ""

        # -----------------------------------------------------------------
        # Entity & Section Context Disambiguation
        # -----------------------------------------------------------------
        # 1. Family member context (father, mother, spouse, child)
        fam_entity = None
        unsupported_relations = ("祖父", "祖母", "外祖父", "外祖母", "爷爷", "奶奶", "外公", "外婆")
        if any(relation in clean_key or relation in clean_sec for relation in unsupported_relations):
            if any(key in clean_key for key in ("姓名", "名字", "电话", "手机", "工作", "单位", "职务", "职位", "岗位")):
                return FieldMappingResult(None, "unmapped", 0.0)
        elif "父亲" in clean_key or ("父" in clean_key and any(k in clean_key for k in ("姓名", "电话", "手机", "工作", "单位", "职务"))):
            fam_entity = "father"
        elif "母亲" in clean_key or ("母" in clean_key and any(k in clean_key for k in ("姓名", "电话", "手机", "工作", "单位", "职务"))):
            fam_entity = "mother"
        elif "配偶" in clean_key:
            fam_entity = "spouse"
        elif any(k in clean_key for k in ("子女", "儿子", "女儿")):
            fam_entity = "child"

        if fam_entity is None:
            for relation, entity in (("父亲", "father"), ("母亲", "mother"), ("配偶", "spouse"), ("子女", "child")):
                if relation in clean_sec:
                    fam_entity = entity
                    break

        if fam_entity:
            if "姓名" in clean_key or "名字" in clean_key:
                return FieldMappingResult(f"soe_extended.family_members[{fam_entity}].name", "exact_rule", 1.0)
            if any(k in clean_key for k in ("手机", "电话", "联系方式")):
                return FieldMappingResult(f"soe_extended.family_members[{fam_entity}].phone", "exact_rule", 1.0)
            if any(k in clean_key for k in ("单位", "工作单位", "公司")):
                return FieldMappingResult(f"soe_extended.family_members[{fam_entity}].workplace", "exact_rule", 1.0)
            if any(k in clean_key for k in ("职务", "职位", "岗位")):
                return FieldMappingResult(f"soe_extended.family_members[{fam_entity}].title", "exact_rule", 1.0)
            if "政治面貌" in clean_key:
                return FieldMappingResult(f"soe_extended.family_members[{fam_entity}].political_status", "exact_rule", 1.0)

        # Family section without specific entity in label: ambiguous, do NOT map to candidate
        if any(k in clean_sec for k in ("家庭", "亲属", "家属", "父母", "配偶")):
            if "关系" in clean_key or "称谓" in clean_key:
                return FieldMappingResult(None, "unmapped", 0.0)
            if any(k in clean_key for k in ("姓名", "手机", "电话", "单位", "职务", "工作")):
                return FieldMappingResult(None, "unmapped", 0.0)

        # 2. Emergency contact context
        is_emergency = "紧急" in clean_key or any(k in clean_sec for k in ("紧急联系人", "紧急联系"))
        if is_emergency:
            if any(k in clean_key for k in ("手机", "电话")):
                return FieldMappingResult("contact.emergency_contact_phone", "exact_rule", 1.0)
            if ("联系人" in clean_key or "姓名" in clean_key) and "关系" not in clean_key:
                return FieldMappingResult("contact.emergency_contact_name", "exact_rule", 1.0)
            if "关系" in clean_key:
                return FieldMappingResult(None, "unmapped", 0.0)

        # 3. Education stage context
        edu_level = None
        for context in (clean_key, clean_sec):
            for level, labels in (
                ("doctor", ("博士",)), ("bachelor", ("本科", "学士")),
                ("master", ("硕士", "研究生")), ("associate", ("大专", "专科")),
                ("high_school", ("高中",)),
            ):
                if any(label in context for label in labels):
                    edu_level = level
                    break
            if edu_level:
                break

        if edu_level:
            if ("院校" in clean_key or "学校" in clean_key) and not any(k in clean_key for k in ("性质", "类型", "类别", "排名")):
                return FieldMappingResult(f"education[{edu_level}].school_name", "exact_rule" if any(clean_key == f"{k}毕业院校" for k in ("本科", "硕士", "博士")) else "semantic", 0.95)
            if "专业" in clean_key and not any(k in clean_key for k in ("排名", "性质", "类别")):
                return FieldMappingResult(f"education[{edu_level}].major", "exact_rule" if any(clean_key == f"{k}专业" for k in ("本科", "硕士", "博士")) else "semantic", 0.95)
            if "学历" in clean_key:
                return FieldMappingResult(f"education[{edu_level}].education_level", "exact_rule", 0.95)
            if "学位" in clean_key:
                return FieldMappingResult(f"education[{edu_level}].academic_degree", "exact_rule", 0.95)
            if "入学" in clean_key and any(k in clean_key for k in ("时间", "日期", "年月")):
                return FieldMappingResult(f"education[{edu_level}].start_date", "exact_rule", 0.95)
            if "毕业" in clean_key and any(k in clean_key for k in ("时间", "日期", "年月")):
                return FieldMappingResult(f"education[{edu_level}].end_date", "exact_rule", 0.95)
            if "绩点" in clean_key or "gpa" in clean_key:
                return FieldMappingResult(f"education[{edu_level}].gpa", "exact_rule", 0.95)

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
        # These labels refer to another person or to a job/placement context.
        # Mapping them to the candidate's identity/contact would silently put
        # the wrong facts into a form, so leave them for manual mapping.
        third_party_context = (
            "导师", "推荐人", "证明人", "证明人", "上级", "领导", "同事",
            "指导老师", "联系人", "实习", "工作经历", "任职", "供职",
        )
        if any(token in clean_key for token in third_party_context):
            return FieldMappingResult(profile_path=None, method="unmapped", confidence=0.0)

        # Resume attachment heuristics
        if "简历" in clean_key or "resume" in clean_key or "cv" in clean_key:
            return FieldMappingResult(
                profile_path="assets[asset_resume_pdf].file_path",
                method="semantic",
                confidence=0.85,
            )

        # Name heuristics
        if ("姓名" in clean_key or "名字" in clean_key) and "紧急" not in clean_key:
            if "英文" in clean_key or "english" in clean_key:
                return FieldMappingResult(
                    profile_path="identity.english_name",
                    method="semantic",
                    confidence=0.85,
                )
            return FieldMappingResult(
                profile_path="identity.name",
                method="semantic",
                confidence=0.85,
            )

        # Gender heuristic
        if "性别" in clean_key:
            return FieldMappingResult(
                profile_path="identity.gender",
                method="semantic",
                confidence=0.85,
            )

        # Dates heuristics
        if "入学" in clean_key and any(k in clean_key for k in ("时间", "日期", "年月")):
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].start_date",
                method="semantic",
                confidence=0.85,
            )

        if "毕业" in clean_key and any(k in clean_key for k in ("时间", "日期", "年月")):
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].end_date",
                method="semantic",
                confidence=0.85,
            )

        # Emergency contacts (with '关系' exclusion)
        if "紧急" in clean_key:
            if "手机" in clean_key or "电话" in clean_key:
                return FieldMappingResult(
                    profile_path="contact.emergency_contact_phone",
                    method="semantic",
                    confidence=0.85,
                )
            if ("联系人" in clean_key or "姓名" in clean_key) and "关系" not in clean_key:
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

        if ("院校" in clean_key or "学校" in clean_key) and not any(
            k in clean_key for k in ("性质", "类型", "类别", "排名")
        ):
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].school_name",
                method="semantic",
                confidence=0.85,
            )

        if "专业" in clean_key and not any(k in clean_key for k in ("排名", "性质", "类别")):
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

        if ("绩点" in clean_key or "gpa" in clean_key) and not any(
            k in clean_key for k in ("满分", "比例", "制度", "scale")
        ):
            return FieldMappingResult(
                profile_path="education[__HIGHEST__].gpa",
                method="semantic",
                confidence=0.85,
            )

        if "民族" in clean_key:
            return FieldMappingResult(
                profile_path="identity.ethnicity",
                method="semantic",
                confidence=0.85,
            )

        # Current residence city (strictly excluding target/intent job locations)
        if any(ex in clean_key for ex in TARGET_CITY_EXCLUDES):
            pass
        elif "现居" in clean_key or "居住" in clean_key or "当前城市" in clean_key or "所在地" in clean_key:
            return FieldMappingResult(
                profile_path="contact.current_city",
                method="semantic",
                confidence=0.85,
            )
        elif "城市" in clean_key and not any(w in clean_key for w in ("学校", "院校", "出生", "籍贯")):
            return FieldMappingResult(
                profile_path="contact.current_city",
                method="semantic",
                confidence=0.85,
            )

        # SOE extended semantic heuristics
        if "身高" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.height_cm",
                method="semantic",
                confidence=0.85,
            )

        if "体重" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.weight_kg",
                method="semantic",
                confidence=0.85,
            )

        if "血型" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.blood_type",
                method="semantic",
                confidence=0.85,
            )

        if "户口" in clean_key or "户籍" in clean_key:
            if "类型" in clean_key or "性质" in clean_key:
                return FieldMappingResult(
                    profile_path="soe_extended.household_type",
                    method="semantic",
                    confidence=0.85,
                )
            return FieldMappingResult(
                profile_path="soe_extended.household_registration",
                method="semantic",
                confidence=0.85,
            )

        if "驾照" in clean_key or "驾驶证" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.driving_license",
                method="semantic",
                confidence=0.85,
            )

        if "服从" in clean_key and ("分配" in clean_key or "调剂" in clean_key):
            return FieldMappingResult(
                profile_path="soe_extended.can_relocate",
                method="semantic",
                confidence=0.85,
            )

        if "自我评价" in clean_key or "个人陈述" in clean_key or "个人简介" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.personal_statement",
                method="semantic",
                confidence=0.85,
            )

        if "爱好" in clean_key or "兴趣" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.hobbies",
                method="semantic",
                confidence=0.85,
            )

        if "特长" in clean_key or "个人优势" in clean_key:
            return FieldMappingResult(
                profile_path="soe_extended.strengths",
                method="semantic",
                confidence=0.85,
            )

        if "健康" in clean_key and "状况" in clean_key:
            return FieldMappingResult(
                profile_path="identity.health_status",
                method="semantic",
                confidence=0.85,
            )

        if "婚姻" in clean_key:
            return FieldMappingResult(
                profile_path="identity.marital_status",
                method="semantic",
                confidence=0.85,
            )

        if "邮编" in clean_key or "邮政编码" in clean_key:
            return FieldMappingResult(
                profile_path="contact.postal_code",
                method="semantic",
                confidence=0.85,
            )

        # Custom fields fallback for SOE: check label against custom_fields
        # This is handled at a higher level by the engine, not here.

        # -----------------------------------------------------------------
        # Tier 4: Unmapped Fallback
        # -----------------------------------------------------------------
        return FieldMappingResult(
            profile_path=None,
            method="unmapped",
            confidence=0.0,
        )
