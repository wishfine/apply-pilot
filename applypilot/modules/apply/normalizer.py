"""Semantic Value Normalizer Registry for typed recruitment fact validation."""

from datetime import date, datetime
from enum import Enum, StrEnum
from pathlib import Path
import re
from typing import Any, Callable, Optional

from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import EducationLevel


class ValueKind(StrEnum):
    """Categorical value kinds for candidate fact normalization and matching."""

    PLAIN_TEXT = "plain_text"
    PERSON_NAME = "person_name"
    PHONE = "phone"
    EMAIL = "email"
    CITY = "city"
    GENDER = "gender"
    FILE = "file"
    DATE = "date"
    EDUCATION_LEVEL = "education_level"
    ACADEMIC_DEGREE = "academic_degree"
    POLITICAL_STATUS = "political_status"
    BOOLEAN = "boolean"
    ENUM = "enum"


# Precompiled regular expressions for performance and safety
RE_DATE_FULL = re.compile(r"^(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?$")
RE_DATE_YM = re.compile(r"^(\d{4})\s*[-/.年]\s*(\d{1,2})\s*月?$")
RE_DATE_Y = re.compile(r"^(\d{4})\s*年?$")
RE_DATE_C8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
RE_DATE_C6 = re.compile(r"^(\d{4})(\d{2})$")
RE_PHONE_CLEAN = re.compile(r"[\s\-_()+]")
RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_LATIN = re.compile(r"[a-zA-Z]")
RE_SPACES = re.compile(r"\s+")
RE_DOTS_AND_SPACES = re.compile(r"[·•・\s]+")


def _is_valid_calendar_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


# Suffixes stripped from Chinese administrative division names
CITY_SUFFIXES: list[str] = [
    "特别行政区",
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "自治区",
    "自治州",
    "地区",
    "盟",
    "市",
    "省",
]

DOCTOR_ALIASES = {
    "博士",
    "博士研究生",
    "doctor",
    "phd",
    "ph.d",
    "ph.d.",
    "博士生",
    "博士后",
    "全日制博士",
    "学术型博士",
}

MASTER_ALIASES = {
    "硕士",
    "硕士研究生",
    "硕士生",
    "master",
    "postgraduate",
    "全日制硕士",
    "统招硕士",
    "非全日制硕士",
    "学术型硕士",
    "专业型硕士",
    "专硕",
    "学硕",
}

BACHELOR_ALIASES = {
    "本科",
    "大学本科",
    "学士",
    "bachelor",
    "undergraduate",
    "全日制本科",
    "统招本科",
    "普通全日制本科",
    "非全日制本科",
}

ASSOCIATE_ALIASES = {
    "大专",
    "专科",
    "associate",
    "junior college",
    "专科生",
    "大专生",
}

HIGH_SCHOOL_ALIASES = {
    "高中",
    "中专",
    "中职",
    "high_school",
    "high school",
    "secondary",
    "高中生",
    "职业高中",
    "职高",
}

POLITICAL_STATUS_MAP: dict[str, set[str]] = {
    "党员": {"党员", "中共党员", "中国共产党党员", "正式党员"},
    "预备党员": {"预备党员", "中共预备党员", "中国共产党预备党员"},
    "团员": {"团员", "共青团员", "中国共产主义青年团团员", "共青团"},
    "群众": {"群众"},
    "民主党派": {"民主党派", "八大民主党派", "各民主党派"},
    "无党派人士": {"无党派人士", "无党派"},
}

DEGREE_LEVEL_MAP: dict[str, set[str]] = {
    "doctor": {"博士", "博士学位", "doctor", "doctorate", "phd", "ph.d", "ph.d."},
    "master": {
        "硕士",
        "硕士学位",
        "master",
        "master's",
        "masters",
        "master degree",
        "mba",
    },
    "bachelor": {
        "学士",
        "学士学位",
        "bachelor",
        "bachelor's",
        "bachelors",
        "bachelor degree",
    },
}

BOOLEAN_TRUE_SET = {"是", "有", "yes", "true", "1", "y", "t", "确定", "对"}
BOOLEAN_FALSE_SET = {"否", "无", "no", "false", "0", "n", "f", "取消", "错"}


def _is_empty(val: Any) -> bool:
    """Check if value represents an empty or unprovided input."""
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def normalize_city(val: Any) -> Optional[str]:
    """Normalize city name by stripping administrative suffixes and provincial prefixes."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    # If "省" exists inside string and is not at the end (e.g. "广东省广州市"), extract city portion
    if "省" in s and not s.endswith("省"):
        s = s.split("省")[-1].strip()

    # Split by explicit hierarchy delimiters if present (e.g. "中国 / 北京", "中国-北京")
    for sep in ["/", ",", "-", ">"]:
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if parts:
                s = parts[-1]

    # For space-separated Chinese hierarchy (e.g. "中国 北京"), split only if all parts contain CJK
    if " " in s and RE_CJK.search(s):
        parts = [p.strip() for p in s.split(" ") if p.strip()]
        if len(parts) > 1 and all(RE_CJK.search(p) for p in parts):
            s = parts[-1]

    # Strip recognized administrative division suffixes
    for suffix in CITY_SUFFIXES:
        if s.endswith(suffix) and len(s) - len(suffix) >= 2:
            s = s[: -len(suffix)]
            break

    return s.lower()


def normalize_education_level(val: Any) -> Optional[str]:
    """Normalize education level to standard EducationLevel values."""
    if val is None:
        return None
    if isinstance(val, EducationLevel):
        return str(val.value).lower()

    s = str(val).strip().lower()
    if not s:
        return None

    if s in DOCTOR_ALIASES:
        return "doctor"
    if s in MASTER_ALIASES:
        return "master"
    if s in BACHELOR_ALIASES:
        return "bachelor"
    if s in ASSOCIATE_ALIASES:
        return "associate"
    if s in HIGH_SCHOOL_ALIASES:
        return "high_school"

    return s


def parse_date_components(
    val: Any,
) -> Optional[tuple[int, Optional[int], Optional[int]]]:
    """Parse a date representation into (year, month, day) components."""
    if val is None:
        return None
    if isinstance(val, PartialDate):
        if 1900 <= val.year <= 2100:
            return (val.year, val.month, val.day)
        return None
    if isinstance(val, (date, datetime)):
        if 1900 <= val.year <= 2100:
            return (val.year, val.month, val.day)
        return None
    if isinstance(val, int) and not isinstance(val, bool):
        if 1900 <= val <= 2100:
            return (val, None, None)
        return None

    s = str(val).strip()
    if not s:
        return None

    # Full date pattern: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, YYYY年MM月DD日
    m_full = RE_DATE_FULL.match(s)
    if m_full:
        try:
            y, m, d = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
            if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31 and _is_valid_calendar_date(y, m, d):
                return (y, m, d)
        except (ValueError, TypeError):
            return None
        return None

    # Year-Month pattern: YYYY-MM, YYYY/MM, YYYY.MM, YYYY年MM月
    m_ym = RE_DATE_YM.match(s)
    if m_ym:
        try:
            y, m = int(m_ym.group(1)), int(m_ym.group(2))
            if 1900 <= y <= 2100 and 1 <= m <= 12:
                return (y, m, None)
        except (ValueError, TypeError):
            return None
        return None

    # Year only pattern: YYYY, YYYY年
    m_y = RE_DATE_Y.match(s)
    if m_y:
        try:
            y = int(m_y.group(1))
            if 1900 <= y <= 2100:
                return (y, None, None)
        except (ValueError, TypeError):
            return None

    # Compact 8 digits: YYYYMMDD
    m_c8 = RE_DATE_C8.match(s)
    if m_c8:
        try:
            y, m, d = int(m_c8.group(1)), int(m_c8.group(2)), int(m_c8.group(3))
            if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31 and _is_valid_calendar_date(y, m, d):
                return (y, m, d)
        except (ValueError, TypeError):
            return None
        return None

    # Compact 6 digits: YYYYMM
    m_c6 = RE_DATE_C6.match(s)
    if m_c6:
        try:
            y, m = int(m_c6.group(1)), int(m_c6.group(2))
            if 1900 <= y <= 2100 and 1 <= m <= 12:
                return (y, m, None)
        except (ValueError, TypeError):
            return None
        return None

    return None


def normalize_date(val: Any) -> Optional[str]:
    """Normalize date to standardized ISO-formatted string YYYY, YYYY-MM, or YYYY-MM-DD."""
    comps = parse_date_components(val)
    if not comps:
        return None
    y, m, d = comps
    if m is not None and d is not None:
        return f"{y:04d}-{m:02d}-{d:02d}"
    if m is not None:
        return f"{y:04d}-{m:02d}"
    return f"{y:04d}"


def normalize_phone(val: Any) -> Optional[str]:
    """Normalize phone number by stripping country code (+86/0086), dashes, spaces, and punctuation."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    # Remove whitespace, dashes, parentheses, dots, underscores
    cleaned = re.sub(r"[\s\-\(\)\.\_]+", "", s)

    # Strip country codes +86 or 0086
    if cleaned.startswith("+86"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("0086"):
        cleaned = cleaned[4:]

    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Remove 86 prefix if 13 digits total
    if cleaned.startswith("86") and len(cleaned) == 13 and cleaned.isdigit():
        cleaned = cleaned[2:]

    # Leading zero before mobile number (0138... -> 138...)
    if len(cleaned) == 12 and cleaned.startswith("01") and cleaned.isdigit():
        cleaned = cleaned[1:]

    return cleaned if cleaned else None


def normalize_email(val: Any) -> Optional[str]:
    """Normalize email with whitespace stripping and lowercase."""
    if val is None:
        return None
    s = str(val).strip().lower()
    return s if s else None


def normalize_political_status(val: Any) -> Optional[str]:
    """Normalize political status to canonical category."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    for canonical, aliases in POLITICAL_STATUS_MAP.items():
        if s in aliases:
            return canonical
    return s


def normalize_boolean(val: Any) -> Optional[bool]:
    """Normalize boolean and TriState representations into a bool value."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, TriState):
        if val == TriState.YES:
            return True
        elif val == TriState.NO:
            return False
        return None
    if isinstance(val, int):
        if val == 1:
            return True
        elif val == 0:
            return False
        return None
    s = str(val).strip().lower()
    if s in BOOLEAN_TRUE_SET:
        return True
    if s in BOOLEAN_FALSE_SET:
        return False
    return None


def normalize_academic_degree(val: Any) -> Optional[str]:
    """Normalize academic degree by removing trailing '学位'."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.endswith("学位") and len(s) > 2:
        s = s[:-2]
    return s


def normalize_gender(val: Any) -> Optional[str]:
    if val is None:
        return None
    value = str(getattr(val, "value", val)).strip().lower()
    if value in {"male", "m", "男", "男性"}:
        return "male"
    if value in {"female", "f", "女", "女性"}:
        return "female"
    return None


def normalize_person_name(val: Any) -> Optional[str]:
    """Normalize person names (collapse internal space/dots for CJK, normalize whitespace for Latin)."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # If contains Chinese characters and no Latin letters, strip all whitespace and middle dots
    if RE_CJK.search(s) and not RE_LATIN.search(s):
        return RE_DOTS_AND_SPACES.sub("", s)
    # Latin / mixed: collapse multiple whitespace characters into single space
    return RE_SPACES.sub(" ", s).lower()


def normalize_plain_text(val: Any) -> Optional[str]:
    """Normalize plain text with trimmed whitespace, collapsed internal spaces, and lowercasing."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return RE_SPACES.sub(" ", s).lower()


def _get_degree_tier(s: str) -> Optional[str]:
    """Identify degree tier (doctor, master, bachelor) from degree name."""
    low = s.strip().lower()
    for tier, aliases in DEGREE_LEVEL_MAP.items():
        if low in aliases:
            return tier
        if tier == "bachelor" and low.endswith("学士"):
            return "bachelor"
        if tier == "master" and low.endswith("硕士"):
            return "master"
        if tier == "doctor" and low.endswith("博士"):
            return "doctor"
    return None


def _are_plain_text_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_plain_text(observed)
    exp = normalize_plain_text(expected)
    if obs is None or exp is None:
        return False
    # Strict equality - NO substring matching!
    return obs == exp


def _are_person_name_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_person_name(observed)
    exp = normalize_person_name(expected)
    if obs is None or exp is None:
        return False
    # Strict equality - NO substring matching!
    return obs == exp


def _are_phone_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_phone(observed)
    exp = normalize_phone(expected)
    if not obs or not exp:
        return False
    return obs == exp


def _are_email_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_email(observed)
    exp = normalize_email(expected)
    if not obs or not exp:
        return False
    return obs == exp


def _are_city_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_city(observed)
    exp = normalize_city(expected)
    if not obs or not exp:
        return False
    return obs == exp


def _are_date_equivalent(observed: str, expected: Any) -> bool:
    obs_comps = parse_date_components(observed)
    exp_comps = parse_date_components(expected)
    if obs_comps is None or exp_comps is None:
        return False

    oy, om, od = obs_comps
    ey, em, ed = exp_comps

    if oy != ey:
        return False

    # Month comparison: if both specify month, they must match
    if om is not None and em is not None:
        if om != em:
            return False

    # Day comparison: if both specify day, they must match
    if od is not None and ed is not None:
        if od != ed:
            return False

    return True


def _are_education_level_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_education_level(observed)
    exp = normalize_education_level(expected)
    if not obs or not exp:
        return False
    # Strict equality - NO substring matching!
    return obs == exp


def _are_academic_degree_equivalent(observed: str, expected: Any) -> bool:
    obs_s = normalize_academic_degree(observed)
    exp_s = normalize_academic_degree(expected)
    if not obs_s or not exp_s:
        return False

    obs_clean = obs_s.lower()
    exp_clean = exp_s.lower()

    if obs_clean == exp_clean:
        return True

    obs_tier = _get_degree_tier(obs_clean)
    exp_tier = _get_degree_tier(exp_clean)

    if obs_tier is None or exp_tier is None or obs_tier != exp_tier:
        return False

    # If tier matches and either is generic (e.g. "学士" or "bachelor")
    generic_aliases = DEGREE_LEVEL_MAP[obs_tier]
    if obs_clean in generic_aliases or exp_clean in generic_aliases:
        return True

    # Both specific but different (e.g. "工学学士" vs "理学学士") -> False
    return False


def _are_gender_equivalent(observed: str, expected: Any) -> bool:
    return normalize_gender(observed) is not None and normalize_gender(observed) == normalize_gender(expected)


def _are_file_equivalent(observed: str, expected: Any) -> bool:
    if not _is_empty(observed) and not _is_empty(expected):
        return Path(str(observed)).name == Path(str(expected)).name
    return False


def _are_political_status_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_political_status(observed)
    exp = normalize_political_status(expected)
    if not obs or not exp:
        return False
    return obs == exp


def _are_boolean_equivalent(observed: str, expected: Any) -> bool:
    obs = normalize_boolean(observed)
    exp = normalize_boolean(expected)
    if obs is None or exp is None:
        return False
    return obs == exp


def _are_enum_equivalent(observed: str, expected: Any) -> bool:
    obs_s = str(observed).strip().lower()
    if isinstance(expected, Enum):
        exp_val = str(expected.value).strip().lower()
        exp_name = str(expected.name).strip().lower()
        return obs_s == exp_val or obs_s == exp_name
    exp_s = str(expected).strip().lower()
    return obs_s == exp_s


class ValueNormalizerRegistry:
    """Registry and dispatcher for semantic value equivalence checks."""

    _handlers: dict[ValueKind, Callable[[str, Any], bool]] = {}

    @classmethod
    def register(cls, kind: ValueKind, handler: Callable[[str, Any], bool]) -> None:
        """Register a custom equivalence handler for a ValueKind."""
        cls._handlers[kind] = handler

    @classmethod
    def unregister(cls, kind: ValueKind) -> None:
        """Unregister custom equivalence handler for a ValueKind."""
        cls._handlers.pop(kind, None)

    @classmethod
    def are_equivalent(
        cls,
        kind: ValueKind,
        observed: Optional[str],
        expected: Any,
    ) -> bool:
        """Verify whether an observed DOM/field value is semantically equivalent to expected fact."""
        # Handle empty / None edge cases
        obs_empty = _is_empty(observed)
        exp_empty = _is_empty(expected)

        if obs_empty and exp_empty:
            return True
        if obs_empty or exp_empty:
            return False

        # If custom handler registered
        if kind in cls._handlers:
            try:
                return cls._handlers[kind](observed, expected)
            except Exception:
                return False

        # Ensure kind is ValueKind
        if isinstance(kind, str):
            try:
                kind = ValueKind(kind)
            except ValueError:
                return _are_plain_text_equivalent(observed, expected)

        try:
            if kind == ValueKind.PLAIN_TEXT:
                return _are_plain_text_equivalent(observed, expected)
            elif kind == ValueKind.PERSON_NAME:
                return _are_person_name_equivalent(observed, expected)
            elif kind == ValueKind.PHONE:
                return _are_phone_equivalent(observed, expected)
            elif kind == ValueKind.EMAIL:
                return _are_email_equivalent(observed, expected)
            elif kind == ValueKind.CITY:
                return _are_city_equivalent(observed, expected)
            elif kind == ValueKind.GENDER:
                return _are_gender_equivalent(observed, expected)
            elif kind == ValueKind.FILE:
                return _are_file_equivalent(observed, expected)
            elif kind == ValueKind.DATE:
                return _are_date_equivalent(observed, expected)
            elif kind == ValueKind.EDUCATION_LEVEL:
                return _are_education_level_equivalent(observed, expected)
            elif kind == ValueKind.ACADEMIC_DEGREE:
                return _are_academic_degree_equivalent(observed, expected)
            elif kind == ValueKind.POLITICAL_STATUS:
                return _are_political_status_equivalent(observed, expected)
            elif kind == ValueKind.BOOLEAN:
                return _are_boolean_equivalent(observed, expected)
            elif kind == ValueKind.ENUM:
                return _are_enum_equivalent(observed, expected)
            else:
                return _are_plain_text_equivalent(observed, expected)
        except Exception:
            return False
