"""Unit tests for ValueNormalizerRegistry and semantic ValueKind normalizers."""

from enum import Enum
import pytest

from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import EducationLevel
from applypilot.modules.apply.normalizer import (
    ValueKind,
    ValueNormalizerRegistry,
    normalize_academic_degree,
    normalize_boolean,
    normalize_city,
    normalize_date,
    normalize_education_level,
    normalize_email,
    normalize_person_name,
    normalize_phone,
    normalize_political_status,
)


class SampleEnum(Enum):
    ALPHA = "alpha_val"
    BETA = "beta_val"


class TestValueKindEnum:
    """Validate ValueKind enum members."""

    def test_value_kind_enum_values(self):
        assert ValueKind.PLAIN_TEXT == "plain_text"
        assert ValueKind.PERSON_NAME == "person_name"
        assert ValueKind.PHONE == "phone"
        assert ValueKind.EMAIL == "email"
        assert ValueKind.CITY == "city"
        assert ValueKind.DATE == "date"
        assert ValueKind.EDUCATION_LEVEL == "education_level"
        assert ValueKind.ACADEMIC_DEGREE == "academic_degree"
        assert ValueKind.POLITICAL_STATUS == "political_status"
        assert ValueKind.BOOLEAN == "boolean"
        assert ValueKind.ENUM == "enum"


class TestEmptyAndNoneHandling:
    """Verify empty, None, and edge case behaviors."""

    def test_both_none_or_empty(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, None, None) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "", "") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "   ", None) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, None, "") is True

    def test_one_side_none_or_empty(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, None, "张三") is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "", "张三") is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "   ", "张三") is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "张三", None) is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "张三", "") is False

    def test_falsy_expected_is_not_treated_as_empty(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "", False) is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, None, False) is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.PLAIN_TEXT, "", 0) is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "", TriState.NO) is False


class TestCityNormalizer:
    """Verify city name normalization and equivalence."""

    def test_normalize_city_helpers(self):
        assert normalize_city("北京市") == "北京"
        assert normalize_city("北京") == "北京"
        assert normalize_city("上海市") == "上海"
        assert normalize_city("广州市") == "广州"
        assert normalize_city("香港特别行政区") == "香港"
        assert normalize_city("新疆维吾尔自治区") == "新疆"
        assert normalize_city("广西壮族自治区") == "广西"
        assert normalize_city("内蒙古自治区") == "内蒙古"
        assert normalize_city("宁夏回族自治区") == "宁夏"
        assert normalize_city("阿里地区") == "阿里"
        assert normalize_city("广东省广州市") == "广州"

    def test_city_equivalence_success(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "北京市", "北京") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "北京", "北京市") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "上海市", "上海") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "广州市", "广州") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "香港特别行政区", "香港") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "新疆维吾尔自治区", "新疆") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "广东省广州市", "广州市") is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "Beijing", "beijing") is True

    def test_different_cities_not_equivalent(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "南京", "北京") is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "南京市", "北京市") is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.CITY, "上海", "深圳") is False


class TestEducationLevelNormalizer:
    """Verify education level hierarchy normalization and strict matching."""

    def test_normalize_education_level_helpers(self):
        assert normalize_education_level("博士研究生") == "doctor"
        assert normalize_education_level("博士") == "doctor"
        assert normalize_education_level("doctor") == "doctor"
        assert normalize_education_level("硕士研究生") == "master"
        assert normalize_education_level("硕士") == "master"
        assert normalize_education_level("master") == "master"
        assert normalize_education_level("本科") == "bachelor"
        assert normalize_education_level("大学本科") == "bachelor"
        assert normalize_education_level("学士") == "bachelor"
        assert normalize_education_level("bachelor") == "bachelor"
        assert normalize_education_level("大专") == "associate"
        assert normalize_education_level("专科") == "associate"
        assert normalize_education_level("associate") == "associate"
        assert normalize_education_level("高中") == "high_school"
        assert normalize_education_level("中专") == "high_school"
        assert normalize_education_level("high_school") == "high_school"

    def test_education_level_cross_matching(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "硕士研究生", "master"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "本科", EducationLevel.BACHELOR
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "大学本科", "bachelor"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "博士", EducationLevel.DOCTOR
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "大专", EducationLevel.ASSOCIATE
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "中专", EducationLevel.HIGH_SCHOOL
            )
            is True
        )

    def test_education_level_mismatch_and_anti_substring(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(ValueKind.EDUCATION_LEVEL, "本科", "硕士")
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(ValueKind.EDUCATION_LEVEL, "大专", "本科")
            is False
        )
        # CRITICAL: anti-substring guard
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "本科", "本科及以上"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EDUCATION_LEVEL, "本科及以上", "本科"
            )
            is False
        )


class TestDateNormalizer:
    """Verify date normalization, partial dates, and separator tolerance."""

    def test_normalize_date_helpers(self):
        assert normalize_date("2025-06-01") == "2025-06-01"
        assert normalize_date("2025年6月1日") == "2025-06-01"
        assert normalize_date("2025/06/01") == "2025-06-01"
        assert normalize_date("2025.6.1") == "2025-06-01"
        assert normalize_date("2025-06") == "2025-06"
        assert normalize_date("2025年6月") == "2025-06"
        assert normalize_date("2025") == "2025"
        assert normalize_date(PartialDate(year=2025, month=6, day=1)) == "2025-06-01"
        assert normalize_date(PartialDate(year=2025, month=6)) == "2025-06"
        assert normalize_date(PartialDate(year=2025)) == "2025"

    def test_date_partial_prefix_matching(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(ValueKind.DATE, "2025-06-01", "2025-06")
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2025-06-01", PartialDate(year=2025, month=6)
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2025-06", PartialDate(year=2025, month=6, day=1)
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2025-06-01", PartialDate(year=2025)
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(ValueKind.DATE, "2025-06-01", 2025) is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2025年06月01日", "2025/6/1"
            )
            is True
        )

    def test_date_mismatch(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(ValueKind.DATE, "2025-07-01", "2025-06")
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2025-06-01", "2025-06-02"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "2024-06-01", "2025-06-01"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "invalid-date", "2025-06-01"
            )
            is False
        )


class TestPhoneNormalizer:
    """Verify phone normalization with country code and delimiters."""

    def test_normalize_phone_helpers(self):
        assert normalize_phone("+86 138-0000-0000") == "13800000000"
        assert normalize_phone("0086 138-0000-0000") == "13800000000"
        assert normalize_phone("8613800000000") == "13800000000"
        assert normalize_phone("(+86) 138 0000 0000") == "13800000000"
        assert normalize_phone(13800000000) == "13800000000"

    def test_phone_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PHONE, "+86 138-0000-0000", "13800000000"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PHONE, "0086-13800000000", 13800000000
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PHONE, "+86 138-0000-0000", "13900000000"
            )
            is False
        )


class TestEmailNormalizer:
    """Verify email case insensitivity and whitespace stripping."""

    def test_normalize_email_helpers(self):
        assert normalize_email(" Test@Example.com ") == "test@example.com"
        assert normalize_email("USER@DOMAIN.ORG") == "user@domain.org"

    def test_email_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EMAIL, " Test@Example.COM ", "test@example.com"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.EMAIL, "a@b.com", "c@b.com"
            )
            is False
        )


class TestPoliticalStatusNormalizer:
    """Verify political status normalization across official variations."""

    def test_normalize_political_status_helpers(self):
        assert normalize_political_status("中共党员") == "党员"
        assert normalize_political_status("党员") == "党员"
        assert normalize_political_status("共青团员") == "团员"
        assert normalize_political_status("团员") == "团员"
        assert normalize_political_status("群众") == "群众"
        assert normalize_political_status("中共预备党员") == "预备党员"
        assert normalize_political_status("预备党员") == "预备党员"

    def test_political_status_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "中共党员", "党员"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "共青团员", "团员"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "群众", "群众"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "预备党员", "中共预备党员"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "预备党员", "党员"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "共青团员", "党员"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.POLITICAL_STATUS, "群众", "中共党员"
            )
            is False
        )


class TestBooleanAndTriStateNormalizer:
    """Verify boolean and TriState normalization."""

    def test_normalize_boolean_helpers(self):
        assert normalize_boolean("是") is True
        assert normalize_boolean("yes") is True
        assert normalize_boolean("true") is True
        assert normalize_boolean("1") is True
        assert normalize_boolean(True) is True
        assert normalize_boolean(1) is True
        assert normalize_boolean(TriState.YES) is True

        assert normalize_boolean("否") is False
        assert normalize_boolean("no") is False
        assert normalize_boolean("false") is False
        assert normalize_boolean("0") is False
        assert normalize_boolean(False) is False
        assert normalize_boolean(0) is False
        assert normalize_boolean(TriState.NO) is False

        assert normalize_boolean(TriState.UNKNOWN) is None

    def test_boolean_equivalence(self):
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "是", True) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "否", TriState.NO) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "是", False) is False
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "1", True) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "0", False) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "yes", TriState.YES) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "no", False) is True
        assert ValueNormalizerRegistry.are_equivalent(ValueKind.BOOLEAN, "否", "是") is False


class TestAcademicDegreeNormalizer:
    """Verify academic degree tier and discipline normalization."""

    def test_normalize_academic_degree_helpers(self):
        assert normalize_academic_degree("学士学位") == "学士"
        assert normalize_academic_degree("硕士学位") == "硕士"
        assert normalize_academic_degree("博士学位") == "博士"
        assert normalize_academic_degree("工学学士") == "工学学士"

    def test_academic_degree_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "工学学士", "学士"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "工学学士", "工学学士"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "学士学位", "学士"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "硕士", "master"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "工学学士", "理学学士"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ACADEMIC_DEGREE, "工学学士", "工学硕士"
            )
            is False
        )


class TestPlainTextAndAntiSubstringGuard:
    """Verify strict normalized equality and anti-false-positive substring guards."""

    def test_whitespace_collapsing(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PLAIN_TEXT, "  Python   Developer  ", "python developer"
            )
            is True
        )

    def test_anti_false_positive_substring_guard(self):
        # CRITICAL: "软件工程" vs "软件工程师" must be FALSE
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PLAIN_TEXT, "软件工程", "软件工程师"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PLAIN_TEXT, "软件工程师", "软件工程"
            )
            is False
        )
        # CRITICAL: "本科" vs "本科及以上" must be FALSE
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PLAIN_TEXT, "本科", "本科及以上"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PLAIN_TEXT, "Java", "JavaScript"
            )
            is False
        )


class TestPersonNameNormalizer:
    """Verify person name normalization."""

    def test_person_name_helpers(self):
        assert normalize_person_name("张 三") == "张三"
        assert normalize_person_name("张三") == "张三"
        assert normalize_person_name("John  Doe") == "john doe"

    def test_person_name_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PERSON_NAME, "张 三", "张三"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PERSON_NAME, "John  Doe", "john doe"
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PERSON_NAME, "张三", "张三丰"
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PERSON_NAME, "John", "John Doe"
            )
            is False
        )


class TestEnumNormalizer:
    """Verify ENUM kind matching with Enum values and names."""

    def test_enum_equivalence(self):
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ENUM, "alpha_val", SampleEnum.ALPHA
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ENUM, "ALPHA", SampleEnum.ALPHA
            )
            is True
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.ENUM, "beta_val", SampleEnum.ALPHA
            )
            is False
        )


class TestRegistryCustomExtensionAndRobustness:
    """Verify custom registry handlers and robustness under edge case inputs."""

    def test_custom_handler_registration(self):
        # Register a custom handler or override
        try:
            ValueNormalizerRegistry.register(
                ValueKind.PLAIN_TEXT,
                lambda obs, exp: obs.strip().upper() == str(exp).strip().upper(),
            )
            assert (
                ValueNormalizerRegistry.are_equivalent(
                    ValueKind.PLAIN_TEXT, "hello", "HELLO"
                )
                is True
            )
        finally:
            ValueNormalizerRegistry.unregister(ValueKind.PLAIN_TEXT)

    def test_robustness_on_unexpected_types(self):
        # Never raises unhandled exception
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.DATE, "not a date", [1, 2, 3]
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.PHONE, "bad", {"key": "val"}
            )
            is False
        )
        assert (
            ValueNormalizerRegistry.are_equivalent(
                ValueKind.BOOLEAN, "maybe", 999
            )
            is False
        )
