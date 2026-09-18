"""Deterministic, evidence-producing form mapping used by the local API."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from applypilot.api.contracts import (
    FormPlanRequest,
    FormPlanResponse,
    PageFieldSnapshot,
    PlanEvidence,
    PlanItem,
    PlanSummary,
    SourceLocation,
)
from applypilot.domain.profile import CandidateProfile
from applypilot.modules.profile.resolver import ValueResolver

MAPPING_VERSION = "rules-2026-09-15.2"

Rule = tuple[str, str]

BASE_RULES: dict[str, Rule] = {
    "姓名": ("identity.name", "个人资料"),
    "真实姓名": ("identity.name", "个人资料"),
    "英文名": ("identity.english_name", "个人资料"),
    "英文姓名": ("identity.english_name", "个人资料"),
    "性别": ("identity.gender", "个人资料"),
    "民族": ("identity.ethnicity", "个人资料"),
    "身份证": ("identity.id_number", "个人资料"),
    "身份证号": ("identity.id_number", "个人资料"),
    "证件号码": ("identity.id_number", "个人资料"),
    "证件类型": ("identity.id_type", "个人资料"),
    "出生日期": ("identity.birth_date", "个人资料"),
    "出生年月": ("identity.birth_date", "个人资料"),
    "出生时间": ("identity.birth_date", "个人资料"),
    "生日": ("identity.birth_date", "个人资料"),
    "出生年份": ("identity.birth_date", "个人资料"),
    "出生月份": ("identity.birth_date", "个人资料"),
    "出生日期年份": ("identity.birth_date", "个人资料"),
    "出生日期月份": ("identity.birth_date", "个人资料"),
    "出生年": ("identity.birth_date", "个人资料"),
    "出生月": ("identity.birth_date", "个人资料"),
    "出生日": ("identity.birth_date", "个人资料"),
    "手机号": ("contact.mobile", "联系方式"),
    "手机号码": ("contact.mobile", "联系方式"),
    "手机": ("contact.mobile", "联系方式"),
    "邮箱": ("contact.email", "联系方式"),
    "电子邮箱": ("contact.email", "联系方式"),
    "现居城市": ("contact.current_city", "联系方式"),
    "现居住地": ("contact.current_city", "联系方式"),
    "现居地址": ("contact.current_address", "联系方式"),
    "QQ": ("contact.qq", "联系方式"),
    "微信": ("contact.wechat", "联系方式"),
    "微信号": ("contact.wechat", "联系方式"),
    "紧急联系人": ("contact.emergency_contact_name", "联系方式"),
    "紧急联系人姓名": ("contact.emergency_contact_name", "联系方式"),
    "紧急联系人电话": ("contact.emergency_contact_phone", "联系方式"),
    "紧急联系人手机": ("contact.emergency_contact_phone", "联系方式"),
    "紧急联系方式": ("contact.emergency_contact_phone", "联系方式"),
    "紧急联系电话": ("contact.emergency_contact_phone", "联系方式"),
    "紧急联系人关系": ("contact.emergency_contact_relation", "联系方式"),
    "与紧急联系人关系": ("contact.emergency_contact_relation", "联系方式"),
    "与本人关系": ("contact.emergency_contact_relation", "联系方式"),
    "毕业院校": ("education[highest].school_name", "教育经历"),
    "学校名称": ("education[highest].school_name", "教育经历"),
    "学院名称": ("education[highest].department", "教育经历"),
    "学院": ("education[highest].department", "教育经历"),
    "院系名称": ("education[highest].department", "教育经历"),
    "专业": ("education[highest].major", "教育经历"),
    "专业名称": ("education[highest].major", "教育经历"),
    "学历": ("education[highest].education_level", "教育经历"),
    "最高学历": ("education[highest].education_level", "教育经历"),
    "学位": ("education[highest].academic_degree", "教育经历"),
    "入学时间": ("education[highest].start_date", "教育经历"),
    "入学日期": ("education[highest].start_date", "教育经历"),
    "入学年份": ("education[highest].start_date", "教育经历"),
    "入学月份": ("education[highest].start_date", "教育经历"),
    "入学年": ("education[highest].start_date", "教育经历"),
    "入学月": ("education[highest].start_date", "教育经历"),
    "开始时间": ("education[highest].start_date", "教育经历"),
    "开始日期": ("education[highest].start_date", "教育经历"),
    "毕业时间": ("education[highest].end_date", "教育经历"),
    "毕业日期": ("education[highest].end_date", "教育经历"),
    "毕业年份": ("campus_context.graduation_year", "校园信息"),
    "毕业月份": ("campus_context.graduation_month", "校园信息"),
    "毕业年": ("campus_context.graduation_year", "校园信息"),
    "毕业月": ("campus_context.graduation_month", "校园信息"),
    "结束时间": ("education[highest].end_date", "教育经历"),
    "结束日期": ("education[highest].end_date", "教育经历"),
    "籍贯": ("soe_extended.native_place", "个人资料"),
    "籍贯所在地": ("soe_extended.native_place", "个人资料"),
    "政治面貌": ("soe_extended.political_status", "个人资料"),
}

EXPERIENCE_RULES: dict[str, Rule] = {
    "公司": ("experiences[latest].org_name", "实习经历"),
    "公司名称": ("experiences[latest].org_name", "实习经历"),
    "单位名称": ("experiences[latest].org_name", "实习经历"),
    "实习单位": ("experiences[latest].org_name", "实习经历"),
    "实习公司": ("experiences[latest].org_name", "实习经历"),
    "职位": ("experiences[latest].title", "实习经历"),
    "职位名称": ("experiences[latest].title", "实习经历"),
    "岗位": ("experiences[latest].title", "实习经历"),
    "岗位名称": ("experiences[latest].title", "实习经历"),
    "实习岗位": ("experiences[latest].title", "实习经历"),
    "部门": ("experiences[latest].department", "实习经历"),
    "所在城市": ("experiences[latest].city", "实习经历"),
    "工作城市": ("experiences[latest].city", "实习经历"),
    "开始时间": ("experiences[latest].start_date", "实习经历"),
    "开始日期": ("experiences[latest].start_date", "实习经历"),
    "结束时间": ("experiences[latest].end_date", "实习经历"),
    "结束日期": ("experiences[latest].end_date", "实习经历"),
    "工作内容": ("experiences[latest].description_bullets", "实习经历"),
    "工作描述": ("experiences[latest].description_bullets", "实习经历"),
    "工作职责": ("experiences[latest].description_bullets", "实习经历"),
    "实习内容": ("experiences[latest].description_bullets", "实习经历"),
}

PROJECT_RULES: dict[str, Rule] = {
    "项目名称": ("projects[latest].project_name", "项目经历"),
    "项目标题": ("projects[latest].project_name", "项目经历"),
    "项目角色": ("projects[latest].role", "项目经历"),
    "项目职责": ("projects[latest].role", "项目经历"),
    "担任角色": ("projects[latest].role", "项目经历"),
    "项目简介": ("projects[latest].summary", "项目经历"),
    "项目介绍": ("projects[latest].summary", "项目经历"),
    "项目描述": ("projects[latest].description_bullets", "项目经历"),
    "项目内容": ("projects[latest].description_bullets", "项目经历"),
    "项目成果": ("projects[latest].description_bullets", "项目经历"),
    "项目链接": ("projects[latest].repo_url", "项目经历"),
    "项目地址": ("projects[latest].repo_url", "项目经历"),
    "项目开始时间": ("projects[latest].start_date", "项目经历"),
    "项目结束时间": ("projects[latest].end_date", "项目经历"),
}

AWARD_RULES: dict[str, Rule] = {
    "获奖项": ("awards[latest].name", "获奖情况"),
    "奖项": ("awards[latest].name", "获奖情况"),
    "奖项名称": ("awards[latest].name", "获奖情况"),
    "获奖名称": ("awards[latest].name", "获奖情况"),
    "获奖描述": ("awards[latest].description", "获奖情况"),
    "奖项描述": ("awards[latest].description", "获奖情况"),
}

PUBLICATION_RULES: dict[str, Rule] = {
    "名称": ("publications[latest].title", "论文/专著"),
    "论文": ("publications[latest].title", "论文/专著"),
    "论文题目": ("publications[latest].title", "论文/专著"),
    "论文名称": ("publications[latest].title", "论文/专著"),
    "专著名称": ("publications[latest].title", "论文/专著"),
    "成果描述": ("publications[latest].description", "论文/专著"),
    "论文描述": ("publications[latest].description", "论文/专著"),
    "发表刊物": ("publications[latest].venue", "论文/专著"),
    "期刊名称": ("publications[latest].venue", "论文/专著"),
    "论文作者": ("publications[latest].authors", "论文/专著"),
}

CERTIFICATE_RULES: dict[str, Rule] = {
    "证书名称": ("certificates[latest].name", "证书"),
    "证书描述": ("certificates[latest].description", "证书"),
    "证书编号": ("certificates[latest].number", "证书"),
}

PRACTICE_RULES: dict[str, Rule] = {
    "实践名称": ("campus_practices[latest].name", "在校实践"),
    "实践描述": ("campus_practices[latest].description", "在校实践"),
    "实践内容": ("campus_practices[latest].description", "在校实践"),
}


def normalize(value: str) -> str:
    return re.sub(r"[\s:*：/／,，.。·()（）【】\[\]_-]", "", value).replace("必选填项", "").replace("必填", "").replace("选填", "").lower()


def key_for(field: PageFieldSnapshot, rules: Mapping[str, Rule]) -> str | None:
    value = normalize(f"{field.label}{field.name}")
    for key in rules:
        cleaned = normalize(key)
        if value == cleaned or cleaned in value:
            return key
    return None


def selected_rule(field: PageFieldSnapshot, active_section: str | None) -> tuple[Rule, str] | None:
    scope = field.section or active_section
    scoped = {
        "实习经历": (EXPERIENCE_RULES, "experience"),
        "项目经历": (PROJECT_RULES, "project"),
        "获奖情况": (AWARD_RULES, "award"),
        "论文/专著": (PUBLICATION_RULES, "publication"),
        "证书": (CERTIFICATE_RULES, "certificate"),
        "在校实践": (PRACTICE_RULES, "practice"),
    }
    if scope in scoped:
        rules, source = scoped[scope]
        key = key_for(field, rules)
        if key:
            return rules[key], source
    key = key_for(field, BASE_RULES)
    if key:
        return BASE_RULES[key], "base"
    key = key_for(field, EXPERIENCE_RULES)
    if key and key not in {"开始时间", "开始日期", "结束时间", "结束日期"}:
        return EXPERIENCE_RULES[key], "experience"
    key = key_for(field, PROJECT_RULES)
    if key and not key.endswith(("开始时间", "结束时间")):
        return PROJECT_RULES[key], "project"
    for rules, source in ((AWARD_RULES, "award"), (PUBLICATION_RULES, "publication"), (CERTIFICATE_RULES, "certificate"), (PRACTICE_RULES, "practice")):
        key = key_for(field, rules)
        if key and not (source == "publication" and key in {"名称", "成果描述"}):
            return rules[key], source
    return None


def record_list(profile: CandidateProfile, source: str) -> list[Any]:
    records = list(getattr(profile, {"experience": "experiences", "project": "projects", "award": "awards", "publication": "publications", "certificate": "certificates", "practice": "campus_practices"}.get(source, ""), []) or [])
    if source == "experience":
        internships = [item for item in records if not str(getattr(item, "experience_type", "") or "").lower() or "intern" in str(getattr(item, "experience_type", "") or "").lower() or "实习" in str(getattr(item, "experience_type", "") or "")]
        records = internships or records
    return sorted(records, key=lambda item: date_key(getattr(item, "end_date", None) or getattr(item, "date", None) or getattr(item, "start_date", None) or getattr(item, "year", None)), reverse=True)


def date_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, Mapping):
        month = value.get("month") or 0
        day = value.get("day") or 0
        return f"{value.get('year', 0)}-{month:02}-{day:02}"
    return f"{getattr(value, 'year', 0)}-{getattr(value, 'month', 0) or 0:02}-{getattr(value, 'day', 0) or 0:02}"


def display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, Mapping):
        year = value.get("year")
        if not year:
            return str(value)
        month, day = value.get("month"), value.get("day")
        return f"{year}-{month:02}-{day:02}" if month and day else f"{year}-{month:02}" if month else str(year)
    if hasattr(value, "to_display"):
        return value.to_display()
    return str(value)


def record_value(profile: CandidateProfile, source: str, path: str, index: int) -> tuple[Any, str | None, str | None]:
    records = record_list(profile, source)
    record = records[index] if 0 <= index < len(records) else None
    match = re.search(r"\[latest\]\.(.+)$", path)
    key = match.group(1) if match else ""
    if record is None:
        return None, None, None
    value = getattr(record, key, None)
    if key == "description_bullets" and isinstance(value, list):
        value = "\n".join(str(item) for item in value if item is not None)
    if key == "summary" and not value:
        value = getattr(record, "description_bullets", None)
    record_id = str(getattr(record, "id", "")) or None
    return display(value), record_id, f"/{source_records_key(source)}/{index}/{key}"


def source_records_key(source: str) -> str:
    return {"experience": "experiences", "project": "projects", "award": "awards", "publication": "publications", "certificate": "certificates", "practice": "campus_practices"}[source]


SENSITIVE_PREFIXES = (
    "identity.id_number",
    "identity.birth_date",
    "contact.mobile",
    "contact.email",
    "contact.qq",
    "contact.wechat",
    "soe_extended.",
)


def logical_path(path: str) -> str:
    return re.sub(r"\[[^]]+\]", "", path)


def sensitive_allowed(path: str, allowed_paths: list[str]) -> bool:
    logical = logical_path(path).lstrip("/").replace("/", ".")
    normalized = [logical_path(item).lstrip("/").replace("/", ".") for item in allowed_paths]
    return any(logical == item or logical.startswith(f"{item}.") for item in normalized)


def is_sensitive(path: str) -> bool:
    logical = logical_path(path).lstrip("/").replace("/", ".")
    return any(logical == prefix or logical.startswith(prefix) for prefix in SENSITIVE_PREFIXES)


def resolve_base(profile: CandidateProfile, path: str) -> Any:
    resolver_path = path.replace("[highest]", "[__HIGHEST__]")
    return display(ValueResolver.resolve(profile, None, resolver_path))


def profile_hash(profile: CandidateProfile) -> str:
    payload = json.dumps(profile.model_dump(mode="json", exclude_none=True), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_pointer(path: str) -> str:
    return "/" + re.sub(r"\[([^]]+)\]", r"/\1", path.replace(".", "/")).strip("/")


def build_form_plan(request: FormPlanRequest) -> FormPlanResponse:
    fields = request.page.fields
    occurrences: dict[str, int] = {}
    group_slots: dict[tuple[str, str], int] = {}
    fixed_group_slots: dict[tuple[str, str], int] = {}
    used_experience: set[int] = set()
    ungrouped_experience_slots: list[int] = []
    ungrouped_experience_seen: set[str] = set()
    ungrouped_experience_current_row = 0
    experience_records = record_list(request.profile, "experience")
    for field in fields:
        if not field.value.strip():
            continue
        selected = selected_rule(field, request.page.active_section)
        if selected and selected[1] == "experience" and any(token in normalize(field.label) for token in ("公司", "单位", "职位", "岗位")):
            wanted = normalize(field.value)
            for index, record in enumerate(experience_records):
                if wanted in {normalize(str(getattr(record, "org_name", ""))), normalize(str(getattr(record, "title", "")))}:
                    used_experience.add(index)
                    if field.record_group:
                        fixed_group_slots[("experience", field.record_group)] = index

    def record_slot(source: str, field: PageFieldSnapshot, path: str) -> int:
        nonlocal ungrouped_experience_current_row
        if field.record_group:
            group_key = (source, field.record_group)
            if group_key in group_slots:
                return group_slots[group_key]
            if group_key in fixed_group_slots:
                group_slots[group_key] = fixed_group_slots[group_key]
                return group_slots[group_key]
            if source == "experience":
                records_used = set(group_slots.values())
                available = next((index for index in range(len(experience_records)) if index not in used_experience and index not in records_used), len(experience_records))
                group_slots[group_key] = available
                used_experience.add(available)
                return available
            family_key = f"{source}:{path.rsplit('.', 1)[-1]}"
            slot = occurrences.get(family_key, 0)
            occurrences[family_key] = slot + 1
            group_slots[group_key] = slot
            return slot
        if source == "experience":
            label = normalize(field.label)
            category = "org" if any(token in label for token in ("公司", "单位")) else "title" if any(token in label for token in ("职位", "岗位", "职务")) else "description" if any(token in label for token in ("内容", "描述", "职责")) else "other"
            if category == "org" and "org" in ungrouped_experience_seen:
                ungrouped_experience_seen.clear()
                ungrouped_experience_current_row += 1
            if not ungrouped_experience_slots or ungrouped_experience_current_row >= len(ungrouped_experience_slots):
                available = next((index for index in range(len(experience_records)) if index not in used_experience and index not in ungrouped_experience_slots), len(experience_records))
                ungrouped_experience_slots.append(available)
            ungrouped_experience_seen.add(category)
            return ungrouped_experience_slots[ungrouped_experience_current_row]
        family_key = f"{source}:{path.rsplit('.', 1)[-1]}"
        slot = occurrences.get(family_key, 0)
        occurrences[family_key] = slot + 1
        return slot

    plan: list[PlanItem] = []
    for field in fields:
        if field.value.strip():
            plan.append(PlanItem(field_ref=field.field_ref, decision="skip", required=field.required, confidence=1, method="existing", reason="已有内容，已保留"))
            continue
        if request.policy.fill_required_only and not field.required:
            plan.append(PlanItem(field_ref=field.field_ref, decision="skip", required=False, confidence=1, method="policy", reason="选填项，按要求留空"))
            continue
        selected = selected_rule(field, request.page.active_section)
        if selected is None:
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, confidence=0, method="unmapped", reason="没有唯一的字段规则，请人工选择", evidence=[PlanEvidence(reason="字段标签或分区未命中规则")]))
            continue
        (path, _scope), source = selected
        if is_sensitive(path) and not sensitive_allowed(path, request.policy.allow_sensitive_paths):
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, profile_path=json_pointer(path), confidence=1, method="sensitive_policy", reason="敏感字段未获得本次授权", evidence=[PlanEvidence(path=json_pointer(path), reason="策略未允许向网页计划返回该敏感值")]))
            continue
        index = None
        if source in {"experience", "project", "award", "publication", "certificate", "practice"}:
            index = record_slot(source, field, path)
            value, record_id, concrete = record_value(request.profile, source, path, index)
            profile_path = concrete
        else:
            value, record_id, profile_path = resolve_base(request.profile, path), None, json_pointer(path)
        if value is None or not str(value).strip():
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, profile_path=profile_path, record_id=record_id, confidence=0.9, method="profile_missing", reason=f"资料缺少：{profile_path or path}", evidence=[PlanEvidence(path=profile_path, reason="档案中没有非空值")]))
            continue
        if field.kind in {"choice", "file"}:
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, value=str(value), profile_path=profile_path, record_id=record_id, confidence=0.95, method="manual_control", reason="选择或附件控件需要人工确认", evidence=[PlanEvidence(path=profile_path, reason="控件不是安全的普通文本写入")]))
            continue
        if field.type == "date" and re.fullmatch(r"\d{4}-\d{2}", str(value)):
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, value=str(value), profile_path=profile_path, record_id=record_id, confidence=1, method="date_precision", reason="资料只有年月，日期控件需要完整日期", evidence=[PlanEvidence(path=profile_path, reason="不补造日期")]))
            continue
        if field.options and not any(str(value).strip().lower() == option.strip().lower() or str(value).strip().lower() in option.strip().lower() or option.strip().lower() in str(value).strip().lower() for option in field.options):
            plan.append(PlanItem(field_ref=field.field_ref, decision="review", required=field.required, value=str(value), profile_path=profile_path, record_id=record_id, confidence=0.95, method="option_check", reason=f"页面没有匹配选项：{value}", evidence=[PlanEvidence(path=profile_path, reason="候选值不在页面选项集合中")]))
            continue
        evidence_reason = "标签、分区和候选档案值唯一匹配"
        if field.record_group:
            evidence_reason += f"；记录组：{field.record_group}"
        plan.append(PlanItem(field_ref=field.field_ref, decision="fill", required=field.required, value=str(value), profile_path=profile_path, record_id=record_id, confidence=1, method="deterministic_rule", reason=f"来源：{profile_path}", evidence=[PlanEvidence(path=profile_path, reason=evidence_reason)]))

    optional = sum(item.decision == "skip" and not item.required for item in plan)
    existing = sum(item.decision == "skip" and item.required for item in plan)
    return FormPlanResponse(
        request_id=request.request_id or "req_" + hashlib.sha256(json.dumps(request.page.model_dump(), sort_keys=True).encode()).hexdigest()[:16],
        mapping_version=MAPPING_VERSION,
        profile_hash=profile_hash(request.profile),
        plan=plan,
        summary=PlanSummary(fields=len(plan), fill=sum(item.decision == "fill" for item in plan), review=sum(item.decision == "review" for item in plan), optional_skipped=optional, existing_skipped=existing),
        expires_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
