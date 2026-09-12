import pytest
from unittest.mock import AsyncMock

from applypilot.adapters.applications.base import (
    ApplicationAdapter,
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)
from applypilot.adapters.applications.beisen import (
    BeisenApplicationAdapter,
    BeisenModalSchoolPicker,
)
from applypilot.adapters.applications.generic import (
    GenericApplicationAdapter,
    StandardInputFiller,
)
from applypilot.adapters.applications.moka import (
    MokaApplicationAdapter,
    MokaSearchSelectFiller,
)


def test_fill_result_defaults_and_structure():
    res = FillResult(
        success=True,
        action_type="type_text",
        observed_value="北京大学",
        verification_status="verified_match",
    )
    assert res.success is True
    assert res.action_type == "type_text"
    assert res.observed_value == "北京大学"
    assert res.verification_status == "verified_match"
    assert res.error_code is None
    assert res.recoverable is True
    assert res.needs_human is False

    err_res = FillResult(
        success=False,
        action_type="none",
        error_code="ELEMENT_NOT_FOUND",
        recoverable=False,
        needs_human=True,
    )
    assert err_res.success is False
    assert err_res.error_code == "ELEMENT_NOT_FOUND"
    assert err_res.recoverable is False
    assert err_res.needs_human is True
    assert err_res.verification_status == "unverified"


@pytest.mark.asyncio
async def test_standard_input_filler_can_handle():
    filler = StandardInputFiller()
    mock_el = AsyncMock()

    for f_type in ["text", "email", "phone", "tel", "number", "standard_input"]:
        assert await filler.can_handle(mock_el, {"field_type": f_type}) is True

    # Default without field_type defaults to True
    assert await filler.can_handle(mock_el, {}) is True

    # Non-text types should not be handled
    assert (
        await filler.can_handle(mock_el, {"field_type": "moka_search_select"}) is False
    )
    assert (
        await filler.can_handle(mock_el, {"field_type": "beisen_modal"}) is False
    )


@pytest.mark.asyncio
async def test_standard_input_filler_fill_success():
    filler = StandardInputFiller()
    mock_page = AsyncMock()
    mock_el = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "张三")

    mock_el.clear_text.assert_awaited_once()
    mock_el.type_text.assert_awaited_once_with("张三")
    assert res.success is True
    assert res.action_type == "type_text"
    assert res.observed_value == "张三"
    assert res.verification_status == "verified_match"


@pytest.mark.asyncio
async def test_standard_input_filler_fill_failure():
    filler = StandardInputFiller()
    mock_page = AsyncMock()
    mock_el = AsyncMock()
    mock_el.type_text.side_effect = RuntimeError("Element detached")

    res = await filler.fill(mock_page, mock_el, "张三")
    assert res.success is False
    assert res.action_type == "type_text"
    assert res.error_code == "INPUT_ERROR"
    assert res.recoverable is True


@pytest.mark.asyncio
async def test_moka_search_select_filler():
    filler = MokaSearchSelectFiller()
    mock_page = AsyncMock()
    mock_el = AsyncMock()

    assert await filler.can_handle(mock_el, {"field_type": "search_select"}) is True
    assert (
        await filler.can_handle(mock_el, {"field_type": "moka_search_select"}) is True
    )
    assert await filler.can_handle(mock_el, {"field_type": "text"}) is False

    res = await filler.fill(mock_page, mock_el, "计算机科学与技术")
    assert res.success is True
    assert res.action_type == "moka_search_select"
    assert res.observed_value == "计算机科学与技术"
    assert res.verification_status == "verified_match"


@pytest.mark.asyncio
async def test_beisen_modal_school_picker():
    filler = BeisenModalSchoolPicker()
    mock_page = AsyncMock()
    mock_el = AsyncMock()

    assert await filler.can_handle(mock_el, {"field_type": "beisen_modal"}) is True
    assert (
        await filler.can_handle(mock_el, {"field_type": "school_picker"}) is True
    )
    assert (
        await filler.can_handle(
            mock_el, {"field_type": "select", "widget": "school_picker"}
        )
        is True
    )
    assert await filler.can_handle(mock_el, {"field_type": "text"}) is False

    res = await filler.fill(mock_page, mock_el, "清华大学")
    assert res.success is True
    assert res.action_type == "beisen_modal_pick"
    assert res.observed_value == "清华大学"
    assert res.verification_status == "verified_match"


@pytest.mark.asyncio
async def test_generic_application_adapter():
    adapter = GenericApplicationAdapter()
    assert len(adapter.fillers) >= 1
    assert any(isinstance(f, StandardInputFiller) for f in adapter.fillers)

    mock_page = AsyncMock()
    mock_el = AsyncMock()

    # Fill field delegation
    res = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "text"}, "13800138000"
    )
    assert res.success is True
    assert res.observed_value == "13800138000"

    # Stage methods
    stage = await adapter.detect_stage(mock_page)
    assert stage == "single_page"

    adv = await adapter.advance(mock_page, stage)
    assert adv is False

    is_final = await adapter.is_final_review(mock_page)
    assert is_final is True


@pytest.mark.asyncio
async def test_moka_application_adapter():
    adapter = MokaApplicationAdapter()
    assert len(adapter.fillers) >= 2
    assert any(isinstance(f, MokaSearchSelectFiller) for f in adapter.fillers)
    assert any(isinstance(f, StandardInputFiller) for f in adapter.fillers)

    mock_page = AsyncMock()
    mock_el = AsyncMock()

    # Handles search_select via first filler
    res_select = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "search_select"}, "硕士"
    )
    assert res_select.success is True
    assert res_select.action_type == "moka_search_select"

    # Falls back to standard input for text
    res_text = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "text"}, "李四"
    )
    assert res_text.success is True
    assert res_text.action_type == "type_text"

    # Lifecycle methods
    stage = await adapter.detect_stage(mock_page)
    assert stage == "moka_form"
    assert await adapter.advance(mock_page, stage) is False
    assert await adapter.is_final_review(mock_page) is True


@pytest.mark.asyncio
async def test_beisen_application_adapter():
    adapter = BeisenApplicationAdapter()
    assert len(adapter.fillers) >= 2
    assert any(isinstance(f, BeisenModalSchoolPicker) for f in adapter.fillers)
    assert any(isinstance(f, StandardInputFiller) for f in adapter.fillers)

    mock_page = AsyncMock()
    mock_el = AsyncMock()

    # Handles modal school picker
    res_school = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "beisen_modal"}, "北京大学"
    )
    assert res_school.success is True
    assert res_school.action_type == "beisen_modal_pick"

    # Falls back to standard input for text
    res_text = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "text"}, "张三"
    )
    assert res_text.success is True
    assert res_text.action_type == "type_text"

    # Lifecycle methods
    stage = await adapter.detect_stage(mock_page)
    assert stage == "beisen_stage"
    assert await adapter.advance(mock_page, stage) is True
    assert await adapter.is_final_review(mock_page) is False


@pytest.mark.asyncio
async def test_adapter_no_matching_filler():
    adapter = GenericApplicationAdapter()
    mock_page = AsyncMock()
    mock_el = AsyncMock()

    # Generic adapter only has StandardInputFiller; an unsupported type should fail cleanly
    res = await adapter.fill_field(
        mock_page, mock_el, {"field_type": "unsupported_complex_widget"}, "value"
    )
    assert res.success is False
    assert res.action_type == "none"
    assert res.error_code == "NO_MATCHING_FILLER"
    assert res.recoverable is False


def test_protocol_conformance():
    for adapter_cls in [
        GenericApplicationAdapter,
        MokaApplicationAdapter,
        BeisenApplicationAdapter,
    ]:
        adapter = adapter_cls()
        assert isinstance(adapter, ApplicationAdapter)

    for filler_cls in [
        StandardInputFiller,
        MokaSearchSelectFiller,
        BeisenModalSchoolPicker,
    ]:
        filler = filler_cls()
        assert isinstance(filler, ComponentFiller)


@pytest.mark.asyncio
async def test_field_type_none_handling():
    filler = StandardInputFiller()
    mock_el = AsyncMock()
    assert await filler.can_handle(mock_el, {"field_type": None}) is True


@pytest.mark.asyncio
async def test_non_interactive_elements_return_error():
    mock_page = AsyncMock()
    # Dummy object with no interactive methods
    class NonInteractiveElement:
        pass

    non_interactive = NonInteractiveElement()

    # StandardInputFiller
    input_filler = StandardInputFiller()
    res_input = await input_filler.fill(mock_page, non_interactive, "test")
    assert res_input.success is False
    assert res_input.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res_input.recoverable is False

    # MokaSearchSelectFiller
    moka_filler = MokaSearchSelectFiller()
    res_moka = await moka_filler.fill(mock_page, non_interactive, "test")
    assert res_moka.success is False
    assert res_moka.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res_moka.recoverable is False

    # BeisenModalSchoolPicker
    beisen_filler = BeisenModalSchoolPicker()
    res_beisen = await beisen_filler.fill(mock_page, non_interactive, "test")
    assert res_beisen.success is False
    assert res_beisen.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res_beisen.recoverable is False


@pytest.mark.asyncio
async def test_can_handle_exception_resilient_fallback():
    mock_page = AsyncMock()
    mock_el = AsyncMock()

    class FaultyFiller:
        async def can_handle(self, element, field_info):
            raise RuntimeError("DOM inspection failed")

        async def fill(self, page, element, value):
            raise AssertionError("Should not be called")

    class WorkingFiller:
        async def can_handle(self, element, field_info):
            return True

        async def fill(self, page, element, value):
            return FillResult(
                success=True,
                action_type="custom_fill",
                observed_value=str(value),
                verification_status="verified_match",
            )

    adapter = BaseApplicationAdapter(fillers=[FaultyFiller(), WorkingFiller()])
    res = await adapter.fill_field(mock_page, mock_el, {"field_type": "text"}, "hello")

    assert res.success is True
    assert res.action_type == "custom_fill"
    assert res.observed_value == "hello"


def test_explicit_empty_fillers_list():
    gen = GenericApplicationAdapter(fillers=[])
    assert gen.fillers == []

    moka = MokaApplicationAdapter(fillers=[])
    assert moka.fillers == []

    beisen = BeisenApplicationAdapter(fillers=[])
    assert beisen.fillers == []

