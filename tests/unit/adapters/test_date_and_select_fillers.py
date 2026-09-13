from datetime import date, datetime
from unittest.mock import AsyncMock
import pytest

from applypilot.adapters.applications import (
    DateInputFiller,
    GenericApplicationAdapter,
    NativeSelectFiller,
)
from applypilot.domain.base import PartialDate, TriState
from applypilot.domain.profile import EducationLevel


# =============================================================================
# 1. DateInputFiller Tests
# =============================================================================

@pytest.mark.asyncio
async def test_date_input_filler_can_handle():
    filler = DateInputFiller()
    assert await filler.can_handle(None, {"field_type": "date"}) is True
    assert await filler.can_handle(None, {"field_type": "month"}) is True
    assert await filler.can_handle(None, {"type": "date"}) is True
    assert await filler.can_handle(None, {"type": "datetime-local"}) is True
    assert await filler.can_handle(None, {"widget": "datepicker"}) is True
    assert await filler.can_handle(None, {"field_type": "text"}) is False
    assert await filler.can_handle(None, {"field_type": "select"}) is False


def test_date_input_filler_format_date():
    # PartialDate full
    p_full = PartialDate(year=2000, month=5, day=20)
    assert DateInputFiller.format_date_value(p_full, "date") == "2000-05-20"
    assert DateInputFiller.format_date_value(p_full, "month") == "2000-05"

    # PartialDate year-month
    p_ym = PartialDate(year=2018, month=9)
    assert DateInputFiller.format_date_value(p_ym, "date") == "2018-09-01"
    assert DateInputFiller.format_date_value(p_ym, "month") == "2018-09"

    # String variations
    assert DateInputFiller.format_date_value("1998/12/31", "date") == "1998-12-31"
    assert DateInputFiller.format_date_value("1998年12月31日", "date") == "1998-12-31"
    assert DateInputFiller.format_date_value("2020.06", "month") == "2020-06"
    assert DateInputFiller.format_date_value(date(2021, 7, 1), "date") == "2021-07-01"


@pytest.mark.asyncio
async def test_date_input_filler_fill_success():
    filler = DateInputFiller()
    mock_el = AsyncMock()
    mock_el.type_text = AsyncMock()
    mock_el.clear_text = AsyncMock()
    mock_el.get_attribute = AsyncMock(return_value="date")
    mock_page = AsyncMock()

    bday = PartialDate(year=1999, month=10, day=15)
    res = await filler.fill(mock_page, mock_el, bday, field_info={"type": "date"})
    assert res.success is True
    assert res.action_type == "set_date"
    assert res.observed_value == "1999-10-15"
    assert res.verification_status == "verified_match"
    mock_el.clear_text.assert_awaited_once()
    mock_el.type_text.assert_awaited_with("1999-10-15")


@pytest.mark.asyncio
async def test_date_input_filler_month_fill_success():
    filler = DateInputFiller()
    mock_el = AsyncMock()
    del mock_el.type_text
    mock_el.fill = AsyncMock()
    mock_el.get_attribute = AsyncMock(return_value="month")
    mock_page = AsyncMock()

    entry_date = PartialDate(year=2018, month=9)
    res = await filler.fill(mock_page, mock_el, entry_date, field_info={"type": "month"})
    assert res.success is True
    assert res.observed_value == "2018-09"
    mock_el.fill.assert_awaited_with("2018-09")


# =============================================================================
# 2. NativeSelectFiller Tests (P2-2 Enum Mapping & Candidate Listing)
# =============================================================================

@pytest.mark.asyncio
async def test_native_select_filler_gender_enum_to_platform_code():
    """P2-2: Candidate has gender: 'male', target has <option value='1'>男</option>."""
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_el.evaluate = AsyncMock(return_value=[
        {"value": "", "text": "请选择性别", "label": "请选择性别"},
        {"value": "1", "text": "男", "label": "男"},
        {"value": "2", "text": "女", "label": "女"},
    ])
    mock_page = AsyncMock()

    # Test with string 'male'
    res = await filler.fill(mock_page, mock_el, "male")
    assert res.success is True
    assert res.action_type == "select_option"
    assert res.observed_value == "男"
    mock_el.select_option.assert_awaited_with("1")

    # Test with string 'female'
    mock_el.select_option.reset_mock()
    res = await filler.fill(mock_page, mock_el, "female")
    assert res.success is True
    assert res.observed_value == "女"
    mock_el.select_option.assert_awaited_with("2")

    # Test with StrEnum
    from enum import StrEnum
    class DummyGender(StrEnum):
        MALE = "male"

    mock_el.select_option.reset_mock()
    res = await filler.fill(mock_page, mock_el, DummyGender.MALE)
    assert res.success is True
    assert res.observed_value == "男"
    mock_el.select_option.assert_awaited_with("1")


@pytest.mark.asyncio
async def test_native_select_filler_education_degree_semantic_match():
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_el.evaluate = AsyncMock(return_value=[
        {"value": "hs", "text": "高中及以下", "label": "高中及以下"},
        {"value": "col", "text": "专科/大专", "label": "专科/大专"},
        {"value": "bac", "text": "本科", "label": "本科"},
        {"value": "mas", "text": "硕士研究生", "label": "硕士研究生"},
        {"value": "doc", "text": "博士研究生", "label": "博士研究生"},
    ])
    mock_page = AsyncMock()

    # Match 'master' to 'mas' (硕士研究生)
    res = await filler.fill(mock_page, mock_el, "master")
    assert res.success is True
    assert res.observed_value == "硕士研究生"
    mock_el.select_option.assert_awaited_with("mas")

    # Match 'bachelor' to 'bac'
    mock_el.select_option.reset_mock()
    res = await filler.fill(mock_page, mock_el, EducationLevel.BACHELOR)
    assert res.success is True
    assert res.observed_value == "本科"
    mock_el.select_option.assert_awaited_with("bac")


@pytest.mark.asyncio
async def test_native_select_filler_boolean_match():
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_el.evaluate = AsyncMock(return_value=[
        {"value": "0", "text": "否", "label": "否"},
        {"value": "1", "text": "是", "label": "是"},
    ])
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, TriState.YES)
    assert res.success is True
    assert res.observed_value == "是"
    mock_el.select_option.assert_awaited_with("1")


@pytest.mark.asyncio
async def test_native_select_filler_option_mismatch_lists_candidates():
    """P2-2: If options exist but none match, return OPTION_MISMATCH with candidates."""
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_el.evaluate = AsyncMock(return_value=[
        {"value": "beijing", "text": "北京", "label": "北京"},
        {"value": "shanghai", "text": "上海", "label": "上海"},
    ])
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "广州")
    assert res.success is False
    assert res.action_type == "select_option"
    assert "OPTION_MISMATCH" in res.error_code
    assert "北京" in res.error_code
    assert "上海" in res.error_code
    assert res.verification_status == "conflict"
    mock_el.select_option.assert_not_called()


@pytest.mark.asyncio
async def test_native_select_filler_fallback_translation_without_dom_options():
    """When element.evaluate is not supported, fallback to translated Chinese if val_str fails."""
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    # First call with "male" raises exception, second call with "男" succeeds
    mock_el.select_option = AsyncMock(side_effect=[Exception("Value male not found"), None])
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "male")
    assert res.success is True
    assert res.observed_value == "男"
    assert mock_el.select_option.await_count == 2
    mock_el.select_option.assert_awaited_with("男")


# =============================================================================
# 3. Adapter Strategy Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_generic_adapter_dispatches_date_and_select():
    adapter = GenericApplicationAdapter()

    # 1. Date field dispatch
    mock_date_el = AsyncMock()
    mock_date_el.type_text = AsyncMock()
    mock_page = AsyncMock()

    res = await adapter.fill_field(
        mock_page,
        mock_date_el,
        {"field_type": "date", "type": "date", "label": "出生日期"},
        PartialDate(year=1995, month=6, day=1),
    )
    assert res.success is True
    assert res.action_type == "set_date"
    assert res.observed_value == "1995-06-01"

    # 2. Select field dispatch
    mock_select_el = AsyncMock()
    mock_select_el.select_option = AsyncMock()
    mock_select_el.evaluate = AsyncMock(return_value=[
        {"value": "1", "text": "男", "label": "男"},
        {"value": "2", "text": "女", "label": "女"},
    ])

    res = await adapter.fill_field(
        mock_page,
        mock_select_el,
        {"field_type": "select", "tag": "select", "label": "性别"},
        "male",
    )
    assert res.success is True
    assert res.action_type == "select_option"
    assert res.observed_value == "男"
    mock_select_el.select_option.assert_awaited_with("1")
