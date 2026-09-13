"""Value resolver for evaluating semantic paths against candidate profiles and variants."""

import re
from typing import Any, Optional

from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import CandidateProfile, EducationLevel, EducationRecord
from applypilot.domain.variant import ResumeVariant

EDUCATION_LEVEL_WEIGHTS: dict[Any, int] = {
    EducationLevel.DOCTOR: 5,
    "doctor": 5,
    EducationLevel.MASTER: 4,
    "master": 4,
    EducationLevel.BACHELOR: 3,
    "bachelor": 3,
    EducationLevel.ASSOCIATE: 2,
    "associate": 2,
    EducationLevel.HIGH_SCHOOL: 1,
    "high_school": 1,
}

FIELD_ALIASES: dict[str, str] = {
    "role": "title",
    "title": "role",
    "name": "project_name",
    "project_name": "name",
}

ID_ATTRS: tuple[str, ...] = (
    "id",
    "project_id",
    "skill_id",
    "asset_id",
    "story_id",
    "variant_id",
)


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ValueResolver:
    """Evaluates dot-separated and indexed paths over a candidate profile and resume variant."""

    @classmethod
    def resolve(
        cls,
        profile: Optional[CandidateProfile],
        variant: Optional[ResumeVariant],
        path: str,
    ) -> Any:
        """Resolve a path to its concrete value from profile or variant.

        Args:
            profile: Verified ground truth candidate profile.
            variant: Optional active resume variant.
            path: Dot-separated and/or bracket-indexed path string.

        Returns:
            Resolved field value, or None if not found/unresolvable.
        """
        try:
            tokens = cls._parse_path(path)
            if tokens is None or not tokens:
                return None

            # Handle variant or profile root prefix
            if tokens[0] == ("attr", "variant"):
                if variant is None:
                    return None
                curr: Any = variant
                remaining_tokens = tokens[1:]
            elif tokens[0] == ("attr", "profile"):
                if profile is None:
                    return None
                curr = profile
                remaining_tokens = tokens[1:]
            else:
                if profile is None:
                    return None
                curr = profile
                first_type, first_val = tokens[0]
                if first_type == "attr" and not hasattr(profile, first_val):
                    # Check common shortcut submodels
                    submodels = (
                        getattr(profile, "soe_extended", None),
                        getattr(profile, "campus_context", None),
                        getattr(profile, "identity", None),
                        getattr(profile, "contact", None),
                    )
                    for sm in submodels:
                        if sm is not None and hasattr(sm, first_val):
                            curr = sm
                            break
                remaining_tokens = tokens

            for tok_type, val in remaining_tokens:
                if curr is None:
                    return None

                if tok_type == "attr":
                    if isinstance(curr, dict):
                        if val in curr:
                            curr = curr[val]
                        elif val in FIELD_ALIASES and FIELD_ALIASES[val] in curr:
                            curr = curr[FIELD_ALIASES[val]]
                        else:
                            return None
                    elif hasattr(curr, val):
                        curr = getattr(curr, val)
                    else:
                        alias = FIELD_ALIASES.get(val)
                        if alias and hasattr(curr, alias):
                            curr = getattr(curr, alias)
                        else:
                            return None

                elif tok_type == "index":
                    if val == "__HIGHEST__":
                        if not isinstance(curr, list) or not curr:
                            return None
                        curr = cls._resolve_highest_education(curr)
                        if curr is None:
                            return None
                    elif val in (
                        "bachelor",
                        "master",
                        "doctor",
                        "associate",
                        "high_school",
                        "undergraduate",
                        "本科",
                        "硕士",
                        "博士",
                        "专科",
                        "大专",
                        "高中",
                    ):
                        if not isinstance(curr, (list, tuple)) or not curr:
                            return None
                        matched = None
                        target_levels = {
                            "bachelor": (EducationLevel.BACHELOR, "bachelor"),
                            "undergraduate": (EducationLevel.BACHELOR, "bachelor"),
                            "本科": (EducationLevel.BACHELOR, "bachelor"),
                            "master": (EducationLevel.MASTER, "master"),
                            "硕士": (EducationLevel.MASTER, "master"),
                            "研究生": (EducationLevel.MASTER, "master"),
                            "doctor": (EducationLevel.DOCTOR, "doctor"),
                            "博士": (EducationLevel.DOCTOR, "doctor"),
                            "associate": (EducationLevel.ASSOCIATE, "associate"),
                            "大专": (EducationLevel.ASSOCIATE, "associate"),
                            "专科": (EducationLevel.ASSOCIATE, "associate"),
                            "high_school": (EducationLevel.HIGH_SCHOOL, "high_school"),
                            "高中": (EducationLevel.HIGH_SCHOOL, "high_school"),
                        }.get(val, ())
                        for item in curr:
                            item_lvl = _get_val(item, "education_level")
                            if item_lvl in target_levels or (hasattr(item_lvl, "value") and item_lvl.value in target_levels):
                                matched = item
                                break
                            if _get_val(item, "id") in (f"edu_{val}", val):
                                matched = item
                                break
                        if matched is not None:
                            curr = matched
                        else:
                            return None
                    elif val in ("father", "mother", "spouse", "child", "父亲", "母亲", "配偶", "子女"):
                        if not isinstance(curr, (list, tuple)) or not curr:
                            return None
                        rel_map = {
                            "father": ("父亲", "父", "爸爸", "family_father", "father"),
                            "父亲": ("父亲", "父", "爸爸", "family_father", "father"),
                            "mother": ("母亲", "母", "妈妈", "family_mother", "mother"),
                            "母亲": ("母亲", "母", "妈妈", "family_mother", "mother"),
                            "spouse": ("配偶", "丈夫", "妻子", "爱人", "family_spouse", "spouse"),
                            "配偶": ("配偶", "丈夫", "妻子", "爱人", "family_spouse", "spouse"),
                            "child": ("子女", "儿子", "女儿", "family_child", "child"),
                            "子女": ("子女", "儿子", "女儿", "family_child", "child"),
                        }
                        targets = rel_map.get(val, ())
                        matched = None
                        for item in curr:
                            rel = str(_get_val(item, "relation") or "")
                            item_id = str(_get_val(item, "id") or "")
                            if any(t == rel for t in targets) or item_id in targets:
                                matched = item
                                break
                        if matched is not None:
                            curr = matched
                        else:
                            return None
                    else:
                        if re.match(r"^-?\d+$", val):
                            idx = int(val)
                            if isinstance(curr, (list, tuple)):
                                if -len(curr) <= idx < len(curr):
                                    curr = curr[idx]
                                else:
                                    return None
                            elif isinstance(curr, dict):
                                if val in curr:
                                    curr = curr[val]
                                elif idx in curr:
                                    curr = curr[idx]
                                else:
                                    return None
                            else:
                                return None
                        else:
                            # Entity ID selector
                            if isinstance(curr, (list, tuple)):
                                matched = None
                                for item in curr:
                                    matched_id = None
                                    for id_attr in ID_ATTRS:
                                        id_val = _get_val(item, id_attr)
                                        if id_val is not None:
                                            matched_id = id_val
                                            break
                                    if matched_id == val:
                                        matched = item
                                        break
                                if matched is not None:
                                    curr = matched
                                else:
                                    # Fallback for assets: strictly enforce asset type
                                    if curr and any(
                                        hasattr(item, "asset_type")
                                        or (isinstance(item, dict) and "asset_type" in item)
                                        for item in curr
                                    ):
                                        val_lower = str(val).lower()
                                        is_resume_request = "resume" in val_lower or "cv" in val_lower or "简历" in val_lower

                                        fallback_asset = None
                                        if is_resume_request:
                                            candidates = [item for item in curr
                                                if str(_get_val(item, "asset_type") or "").lower() in ("resume_pdf", "resume")]
                                            fallback_asset = candidates[0] if len(candidates) == 1 else None
                                            # Strictly return matching resume or None. Never pick arbitrary PDF!
                                            curr = fallback_asset
                                            if curr is None:
                                                return None
                                        else:
                                            # Non-resume request: match by asset_type
                                            for item in curr:
                                                if str(_get_val(item, "asset_type") or "").lower() == val_lower:
                                                    fallback_asset = item
                                                    break
                                            curr = fallback_asset
                                            if curr is None:
                                                return None
                                    else:
                                        return None
                            elif isinstance(curr, dict):
                                if val in curr:
                                    curr = curr[val]
                                else:
                                    return None
                            else:
                                return None

            if isinstance(curr, PartialDate):
                return curr.to_display()
            return curr

        except Exception:
            return None

    @classmethod
    def _parse_path(cls, path: Any) -> Optional[list[tuple[str, str]]]:
        if not isinstance(path, str):
            return None
        path = path.strip()
        if not path:
            return None
        if path.startswith(".") or path.endswith("."):
            return None
        if ".." in path:
            return None

        tokens: list[tuple[str, str]] = []
        i = 0
        n = len(path)
        while i < n:
            if path[i] == ".":
                i += 1
                continue
            if path[i] == "[":
                close_bracket = path.find("]", i)
                if close_bracket == -1:
                    return None
                content = path[i + 1 : close_bracket].strip()
                if not content:
                    return None
                tokens.append(("index", content))
                i = close_bracket + 1
            else:
                start = i
                while i < n and path[i] not in (".", "["):
                    if path[i] == "]":
                        return None
                    i += 1
                attr = path[start:i].strip()
                if not attr:
                    return None
                tokens.append(("attr", attr))
        return tokens

    @classmethod
    def _resolve_highest_education(cls, records: list[Any]) -> Optional[Any]:
        if not records:
            return None

        def _edu_sort_key(item_with_idx: tuple[int, Any]) -> tuple[int, int, int, int, int, int]:
            idx, edu = item_with_idx
            level = _get_val(edu, "education_level")
            level_weight = EDUCATION_LEVEL_WEIGHTS.get(level, 0)
            end_date = _get_val(edu, "end_date")
            end_year = _get_val(end_date, "year", 0) if end_date else 0
            end_month = _get_val(end_date, "month", 0) or 0 if end_date else 0
            start_date = _get_val(edu, "start_date")
            start_year = _get_val(start_date, "year", 0) if start_date else 0
            start_month = _get_val(start_date, "month", 0) or 0 if start_date else 0
            return (level_weight, end_year, end_month, start_year, start_month, idx)

        yes_records = [
            (idx, r)
            for idx, r in enumerate(records)
            if _get_val(r, "is_highest_degree") in (TriState.YES, "yes")
        ]
        if yes_records:
            return max(yes_records, key=_edu_sort_key)[1]

        all_records = list(enumerate(records))
        return max(all_records, key=_edu_sort_key)[1]
