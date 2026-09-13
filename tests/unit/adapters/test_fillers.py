from pathlib import Path
from unittest.mock import AsyncMock
import pytest

from applypilot.adapters.applications import (
    BeisenApplicationAdapter,
    BeisenModalSchoolPicker,
    FileUploadFiller,
    GenericApplicationAdapter,
    MokaApplicationAdapter,
    MokaSearchSelectFiller,
    NativeSelectFiller,
    RadioCheckboxFiller,
    StandardInputFiller,
)
from applypilot.domain.base import TriState
from applypilot.domain.profile import AssetRecord, CandidateProfile
from applypilot.modules.apply.mapper import FieldMapper
from applypilot.modules.profile.resolver import ValueResolver


# =============================================================================
# 1. FileUploadFiller Tests
# =============================================================================

@pytest.mark.asyncio
async def test_file_upload_filler_can_handle():
    filler = FileUploadFiller()
    assert await filler.can_handle(None, {"field_type": "file"}) is True
    assert await filler.can_handle(None, {"field_type": "upload"}) is True
    assert await filler.can_handle(None, {"type": "file"}) is True
    assert await filler.can_handle(None, {"widget": "upload"}) is True
    assert await filler.can_handle(None, {"field_type": "text"}) is False


@pytest.mark.asyncio
async def test_file_upload_filler_success(tmp_path: Path):
    test_file = tmp_path / "resume.pdf"
    test_file.write_text("dummy resume content", encoding="utf-8")

    filler = FileUploadFiller()
    mock_el = AsyncMock()
    mock_el.set_files = AsyncMock()
    mock_page = AsyncMock()

    # Pass Path
    res = await filler.fill(mock_page, mock_el, test_file)
    assert res.success is True
    assert res.action_type == "set_files"
    assert res.observed_value == str(test_file)
    assert res.verification_status == "verified_match"
    mock_el.set_files.assert_awaited_with([str(test_file)])

    # Pass AssetRecord
    mock_el.set_files.reset_mock()
    asset = AssetRecord(
        asset_id="asset_01",
        asset_type="resume_pdf",
        file_path=str(test_file),
        title="Resume",
    )
    res = await filler.fill(mock_page, mock_el, asset)
    assert res.success is True
    mock_el.set_files.assert_awaited_with([str(test_file)])

    # Pass list of paths
    mock_el.set_files.reset_mock()
    res = await filler.fill(mock_page, mock_el, [str(test_file)])
    assert res.success is True
    mock_el.set_files.assert_awaited_with([str(test_file)])


@pytest.mark.asyncio
async def test_file_upload_filler_missing_file(tmp_path: Path):
    missing_file = tmp_path / "not_found.pdf"
    filler = FileUploadFiller()
    mock_el = AsyncMock()
    mock_el.set_files = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, missing_file)
    assert res.success is False
    assert res.error_code == "FILE_NOT_FOUND"
    assert res.recoverable is False
    mock_el.set_files.assert_not_called()


@pytest.mark.asyncio
async def test_file_upload_filler_not_interactable(tmp_path: Path):
    test_file = tmp_path / "resume.pdf"
    test_file.write_text("dummy resume content", encoding="utf-8")

    filler = FileUploadFiller()
    mock_el = object()  # Lacks set_files
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, test_file)
    assert res.success is False
    assert res.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res.recoverable is False


@pytest.mark.asyncio
async def test_file_upload_filler_exception_handling(tmp_path: Path):
    test_file = tmp_path / "resume.pdf"
    test_file.write_text("dummy resume content", encoding="utf-8")

    filler = FileUploadFiller()
    mock_el = AsyncMock()
    mock_el.set_files = AsyncMock(side_effect=RuntimeError("Browser upload rejected"))
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, test_file)
    assert res.success is False
    assert res.error_code == "FILE_UPLOAD_ERROR"
    assert res.recoverable is True


@pytest.mark.asyncio
async def test_file_upload_filler_expanduser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    test_file = tmp_path / "resume_tilde.pdf"
    test_file.write_text("tilde resume", encoding="utf-8")

    filler = FileUploadFiller()
    mock_el = AsyncMock()
    mock_el.set_files = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "~/resume_tilde.pdf")
    assert res.success is True
    assert res.action_type == "set_files"
    assert res.observed_value == str(test_file)
    assert res.verification_status == "verified_match"
    mock_el.set_files.assert_awaited_with([str(test_file)])


@pytest.mark.asyncio
async def test_file_upload_filler_directory_rejected(tmp_path: Path):
    sub_dir = tmp_path / "somedir"
    sub_dir.mkdir()

    filler = FileUploadFiller()
    mock_el = AsyncMock()
    mock_el.set_files = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, str(sub_dir))
    assert res.success is False
    assert res.error_code == "FILE_NOT_FOUND"
    mock_el.set_files.assert_not_called()


# =============================================================================
# 2. NativeSelectFiller Tests
# =============================================================================

@pytest.mark.asyncio
async def test_native_select_filler_can_handle():
    filler = NativeSelectFiller()
    assert await filler.can_handle(None, {"field_type": "select"}) is True
    assert await filler.can_handle(None, {"tag": "select"}) is True
    assert await filler.can_handle(None, {"field_type": "text"}) is False


@pytest.mark.asyncio
async def test_native_select_filler_success():
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "硕士研究生")
    assert res.success is True
    assert res.action_type == "select_option"
    assert res.observed_value == "硕士研究生"
    assert res.verification_status == "verified_match"
    mock_el.select_option.assert_awaited_with("硕士研究生")


@pytest.mark.asyncio
async def test_native_select_filler_enum_value():
    filler = NativeSelectFiller()
    mock_el = AsyncMock()
    mock_el.select_option = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, TriState.YES)
    assert res.success is True
    mock_el.select_option.assert_awaited_with("yes")


@pytest.mark.asyncio
async def test_native_select_filler_not_interactable():
    filler = NativeSelectFiller()
    mock_el = object()  # Lacks select_option
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "北京")
    assert res.success is False
    assert res.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res.recoverable is False


# =============================================================================
# 3. RadioCheckboxFiller Tests
# =============================================================================

@pytest.mark.asyncio
async def test_radio_checkbox_filler_can_handle():
    filler = RadioCheckboxFiller()
    assert await filler.can_handle(None, {"field_type": "radio"}) is True
    assert await filler.can_handle(None, {"field_type": "checkbox"}) is True
    assert await filler.can_handle(None, {"type": "radio"}) is True
    assert await filler.can_handle(None, {"type": "checkbox"}) is True
    assert await filler.can_handle(None, {"field_type": "text"}) is False


@pytest.mark.asyncio
async def test_radio_checkbox_filler_success():
    filler = RadioCheckboxFiller()
    mock_el = AsyncMock()
    mock_el.click = AsyncMock()
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "同意")
    assert res.success is True
    assert res.action_type == "click"
    assert res.observed_value == "同意"
    assert res.verification_status == "verified_match"
    mock_el.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_radio_checkbox_filler_not_interactable():
    filler = RadioCheckboxFiller()
    mock_el = object()  # Lacks click
    mock_page = AsyncMock()

    res = await filler.fill(mock_page, mock_el, "同意")
    assert res.success is False
    assert res.error_code == "ELEMENT_NOT_INTERACTABLE"
    assert res.recoverable is False


@pytest.mark.asyncio
async def test_radio_button_option_matching():
    filler = RadioCheckboxFiller()
    mock_page = AsyncMock()

    # 1. Matching option value -> clicked when unchecked
    mock_el_match = AsyncMock()
    mock_el_match.click = AsyncMock()
    mock_el_match.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "male"}.get(attr)
    )
    mock_el_match.is_checked = AsyncMock(return_value=False)
    res_match = await filler.fill(mock_page, mock_el_match, "male")
    assert res_match.success is True
    assert res_match.action_type == "click"
    assert res_match.observed_value == "male"
    assert res_match.verification_status == "verified_match"
    mock_el_match.click.assert_awaited_once()

    # 2. Mismatched option value -> skipped, NOT clicked
    mock_el_mismatch = AsyncMock()
    mock_el_mismatch.click = AsyncMock()
    mock_el_mismatch.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "female"}.get(attr)
    )
    mock_el_mismatch.is_checked = AsyncMock(return_value=False)
    res_mismatch = await filler.fill(mock_page, mock_el_mismatch, "male")
    assert res_mismatch.success is True
    assert res_mismatch.action_type == "skip_mismatched_option"
    assert res_mismatch.observed_value == "female"
    assert res_mismatch.verification_status == "unverified"
    mock_el_mismatch.click.assert_not_called()

    # 3. Matching by label text (e.g. value="M", text="男 (Male)")
    mock_el_text = AsyncMock()
    mock_el_text.click = AsyncMock()
    mock_el_text.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "M"}.get(attr)
    )
    mock_el_text.get_text = AsyncMock(return_value="男 (Male)")
    mock_el_text.is_checked = AsyncMock(return_value=False)
    res_text = await filler.fill(mock_page, mock_el_text, "男")
    assert res_text.success is True
    assert res_text.action_type == "click"
    mock_el_text.click.assert_awaited_once()

    # 4. Matching option that is already checked -> noop, NOT clicked
    mock_el_already_checked = AsyncMock()
    mock_el_already_checked.click = AsyncMock()
    mock_el_already_checked.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "male"}.get(attr)
    )
    mock_el_already_checked.is_checked = AsyncMock(return_value=True)
    res_noop = await filler.fill(mock_page, mock_el_already_checked, "male")
    assert res_noop.success is True
    assert res_noop.action_type == "noop"
    assert res_noop.verification_status == "verified_match"
    mock_el_already_checked.click.assert_not_called()


@pytest.mark.asyncio
async def test_radio_filler_uses_field_info_label():
    filler = RadioCheckboxFiller()
    mock_page = AsyncMock()

    # <input type="radio" value="opt_1"> without inner text, but field_info has label="硕士研究生"
    mock_el = AsyncMock()
    mock_el.click = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "opt_1"}.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")  # No inner text on input
    mock_el.is_checked = AsyncMock(return_value=False)

    field_info = {
        "field_type": "radio",
        "type": "radio",
        "label": "硕士研究生",
    }
    res = await filler.fill(mock_page, mock_el, "硕士", field_info=field_info)
    assert res.success is True
    assert res.action_type == "click"
    mock_el.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_adapter_forwards_field_info_to_filler():
    adapter = GenericApplicationAdapter()
    mock_page = AsyncMock()
    mock_el = AsyncMock()
    mock_el.click = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "radio", "value": "opt_A"}.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_el.is_checked = AsyncMock(return_value=False)

    field_info = {
        "field_type": "radio",
        "type": "radio",
        "label": "北京大学",
    }
    res = await adapter.fill_field(mock_page, mock_el, field_info, "北京大学")
    assert res.success is True
    assert res.action_type == "click"
    mock_el.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkbox_boolean_state_handling():
    filler = RadioCheckboxFiller()
    mock_page = AsyncMock()

    # 1. Expected True & unchecked -> click
    mock_el1 = AsyncMock()
    mock_el1.click = AsyncMock()
    mock_el1.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el1.is_checked = AsyncMock(return_value=False)
    res1 = await filler.fill(mock_page, mock_el1, True)
    assert res1.success is True
    assert res1.action_type == "click"
    mock_el1.click.assert_awaited_once()

    # 2. Expected True & already checked -> noop (not clicked)
    mock_el2 = AsyncMock()
    mock_el2.click = AsyncMock()
    mock_el2.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el2.is_checked = AsyncMock(return_value=True)
    res2 = await filler.fill(mock_page, mock_el2, True)
    assert res2.success is True
    assert res2.action_type == "noop"
    mock_el2.click.assert_not_called()

    # 3. Expected False & checked -> click (to uncheck)
    mock_el3 = AsyncMock()
    mock_el3.click = AsyncMock()
    mock_el3.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el3.is_checked = AsyncMock(return_value=True)
    res3 = await filler.fill(mock_page, mock_el3, False)
    assert res3.success is True
    assert res3.action_type == "click"
    mock_el3.click.assert_awaited_once()

    # 4. Expected False & unchecked -> noop (not clicked)
    mock_el4 = AsyncMock()
    mock_el4.click = AsyncMock()
    mock_el4.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el4.is_checked = AsyncMock(return_value=False)
    res4 = await filler.fill(mock_page, mock_el4, False)
    assert res4.success is True
    assert res4.action_type == "noop"
    mock_el4.click.assert_not_called()

    # 5. TriState support (TriState.YES unchecked -> click, TriState.NO unchecked -> noop)
    mock_el5 = AsyncMock()
    mock_el5.click = AsyncMock()
    mock_el5.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el5.is_checked = AsyncMock(return_value=False)
    res5 = await filler.fill(mock_page, mock_el5, TriState.YES)
    assert res5.success is True
    assert res5.action_type == "click"
    mock_el5.click.assert_awaited_once()

    mock_el6 = AsyncMock()
    mock_el6.click = AsyncMock()
    mock_el6.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox"}.get(attr)
    )
    mock_el6.is_checked = AsyncMock(return_value=False)
    res6 = await filler.fill(mock_page, mock_el6, TriState.NO)
    assert res6.success is True
    assert res6.action_type == "noop"
    mock_el6.click.assert_not_called()

    # 6. Fallback to get_attribute("checked") when is_checked is not present
    mock_el7 = AsyncMock(spec=["click", "get_attribute"])
    mock_el7.click = AsyncMock()
    mock_el7.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox", "checked": "checked"}.get(attr)
    )
    res7 = await filler.fill(mock_page, mock_el7, True)
    assert res7.success is True
    assert res7.action_type == "noop"
    mock_el7.click.assert_not_called()


@pytest.mark.asyncio
async def test_checkbox_choice_matching():
    filler = RadioCheckboxFiller()
    mock_page = AsyncMock()

    # Checkbox with choice option value matching target in list
    mock_el = AsyncMock()
    mock_el.click = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox", "value": "python"}.get(attr)
    )
    mock_el.is_checked = AsyncMock(return_value=False)

    res = await filler.fill(mock_page, mock_el, ["python", "golang"])
    assert res.success is True
    assert res.action_type == "click"
    mock_el.click.assert_awaited_once()

    # Checkbox with choice option value NOT matching target in list
    mock_el_mismatch = AsyncMock()
    mock_el_mismatch.click = AsyncMock()
    mock_el_mismatch.get_attribute = AsyncMock(
        side_effect=lambda attr: {"type": "checkbox", "value": "rust"}.get(attr)
    )
    mock_el_mismatch.is_checked = AsyncMock(return_value=False)

    res_mis = await filler.fill(mock_page, mock_el_mismatch, ["python", "golang"])
    assert res_mis.success is True
    assert res_mis.action_type == "skip_mismatched_option"
    mock_el_mismatch.click.assert_not_called()


# =============================================================================
# 4. Adapter Default Fillers Registration Tests
# =============================================================================

def test_adapters_default_fillers():
    generic_adapter = GenericApplicationAdapter()
    filler_types = [type(f) for f in generic_adapter.fillers]
    assert FileUploadFiller in filler_types
    assert NativeSelectFiller in filler_types
    assert RadioCheckboxFiller in filler_types
    assert StandardInputFiller in filler_types

    beisen_adapter = BeisenApplicationAdapter()
    b_types = [type(f) for f in beisen_adapter.fillers]
    assert BeisenModalSchoolPicker in b_types
    assert FileUploadFiller in b_types
    assert NativeSelectFiller in b_types
    assert RadioCheckboxFiller in b_types
    assert StandardInputFiller in b_types

    moka_adapter = MokaApplicationAdapter()
    m_types = [type(f) for f in moka_adapter.fillers]
    assert MokaSearchSelectFiller in m_types
    assert FileUploadFiller in m_types
    assert NativeSelectFiller in m_types
    assert RadioCheckboxFiller in m_types
    assert StandardInputFiller in m_types


# =============================================================================
# 5. FieldMapper Canonical Exact Rules for Resume Upload Tests
# =============================================================================

def test_field_mapper_resume_upload_rules():
    labels = [
        "上传简历",
        "简历附件",
        "简历上传",
        "个人简历",
        "附件简历",
        "上传附件",
        "简历",
        "resume",
        "cv",
    ]
    for label in labels:
        path, method, conf = FieldMapper.map_field(
            field_sig=label,
            normalized_label=label,
            field_type="file",
        )
        assert path == "assets[asset_resume_pdf].file_path", f"Failed for {label}"
        assert method == "exact_rule"
        assert conf == 1.0


# =============================================================================
# 6. ValueResolver Asset Path & Fallback Tests
# =============================================================================

def test_value_resolver_assets_exact_id():
    profile = CandidateProfile(
        profile_id="cand_assets_01",
        assets=[
            AssetRecord(
                asset_id="asset_resume_pdf",
                asset_type="resume_pdf",
                file_path="/path/to/my_resume.pdf",
                title="简历",
            )
        ],
    )
    val = ValueResolver.resolve(profile, None, "assets[asset_resume_pdf].file_path")
    assert val == "/path/to/my_resume.pdf"


def test_value_resolver_assets_fallback_by_type():
    # asset_id does not match "asset_resume_pdf", but asset_type is "resume_pdf"
    profile = CandidateProfile(
        profile_id="cand_assets_02",
        assets=[
            AssetRecord(
                asset_id="custom_id_999",
                asset_type="resume_pdf",
                file_path="/path/to/fallback_resume.pdf",
                title="简历",
            )
        ],
    )
    val = ValueResolver.resolve(profile, None, "assets[asset_resume_pdf].file_path")
    assert val == "/path/to/fallback_resume.pdf"


def test_value_resolver_assets_fallback_by_pdf_extension():
    # asset_id and asset_type are non-standard, but extension is .pdf
    profile = CandidateProfile(
        profile_id="cand_assets_03",
        assets=[
            AssetRecord(
                asset_id="custom_cert",
                asset_type="certificate",
                file_path="/path/to/certificate.png",
                title="证书",
            ),
            AssetRecord(
                asset_id="my_resume",
                asset_type="custom",
                file_path="/path/to/my_resume.pdf",
                title="我的简历",
            ),
        ],
    )
    val = ValueResolver.resolve(profile, None, "assets[asset_resume_pdf].file_path")
    assert val is None


def test_value_resolver_assets_strictly_rejects_non_resume_fallback():
    profile = CandidateProfile(
        profile_id="cand_assets_04",
        assets=[
            AssetRecord(
                asset_id="custom_doc",
                asset_type="custom",
                file_path="/path/to/doc.docx",
                title="文档",
            )
        ],
    )
    val = ValueResolver.resolve(profile, None, "assets[asset_resume_pdf].file_path")
    assert val is None


@pytest.mark.asyncio
async def test_apply_engine_sniffs_select_and_file_elements(tmp_path: Path):
    db_file = tmp_path / "test.db"
    from applypilot.storage.database import init_db
    await init_db(db_file)

    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_browser.open_page.return_value = mock_page

    select_el = AsyncMock()
    select_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "学历",
            "tagName": "select",
            "value": "",
        }.get(attr)
    )
    select_el.get_text = AsyncMock(return_value="")
    select_el.select_option = AsyncMock()

    file_el = AsyncMock()
    file_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "上传简历",
            "type": "file",
        }.get(attr)
    )
    file_el.get_text = AsyncMock(return_value="")
    file_el.set_files = AsyncMock()

    mock_page.find_all = AsyncMock(return_value=[select_el, file_el])

    from applypilot.modules.apply.engine import ApplyEngine
    from applypilot.domain.job import ApplicationTarget, Job
    from applypilot.domain.profile import CandidateProfile, EducationRecord, EducationLevel

    resume_path = tmp_path / "resume.pdf"
    resume_path.write_text("content", encoding="utf-8")

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    from applypilot.domain.base import PartialDate
    profile = CandidateProfile(
        profile_id="cand_test",
        education=[
            EducationRecord(
                id="edu_01",
                school_name="清华大学",
                education_level=EducationLevel.BACHELOR,
                major="CS",
                start_date=PartialDate(year=2018, month=9),
                end_date=PartialDate(year=2022, month=6),
            )
        ],
        assets=[AssetRecord(asset_id="asset_resume_pdf", asset_type="resume_pdf", file_path=str(resume_path), title="简历")],
    )
    target = ApplicationTarget(
        target_id="tgt_test",
        job=Job(
            job_id="job_test",
            title="Dev",
            company_name="Company",
            description_raw="desc",
            source_channel="url",
            source_url="http://example.com",
            apply_url="http://example.com",
        ),
        provider="generic",
    )

    await engine.run_application_target(target, profile)
    file_el.set_files.assert_awaited_with([str(resume_path)])
    select_el.select_option.assert_awaited_with("bachelor")
