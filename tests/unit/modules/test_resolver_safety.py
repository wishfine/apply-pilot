import pytest
from applypilot.domain.profile import CandidateProfile, AssetRecord
from applypilot.modules.profile.resolver import ValueResolver


def test_asset_resolver_rejects_non_resume_when_resolving_resume():
    # Candidate profile only has a transcript PDF, no resume
    profile = CandidateProfile(
        profile_id="cand_test_asset",
        assets=[
            AssetRecord(
                asset_id="asset_transcript_1",
                title="大学成绩单",
                asset_type="transcript",
                file_path="/Users/test/Documents/transcript.pdf",
            )
        ],
    )

    # Resolving resume should NOT fall back to transcript.pdf or first asset
    resolved = ValueResolver.resolve(
        profile, None, "assets[asset_resume_pdf].file_path"
    )
    assert resolved is None, f"Expected None for missing resume, but got: {resolved}"


def test_asset_resolver_matches_valid_resume():
    profile = CandidateProfile(
        profile_id="cand_test_asset",
        assets=[
            AssetRecord(
                asset_id="asset_transcript_1",
                title="大学成绩单",
                asset_type="transcript",
                file_path="/Users/test/Documents/transcript.pdf",
            ),
            AssetRecord(
                asset_id="asset_resume_pdf",
                title="个人中文简历",
                asset_type="resume_pdf",
                file_path="/Users/test/Documents/resume.pdf",
            ),
        ],
    )

    resolved = ValueResolver.resolve(
        profile, None, "assets[asset_resume_pdf].file_path"
    )
    assert resolved == "/Users/test/Documents/resume.pdf"


def test_explicit_resume_asset_id_cannot_resolve_transcript():
    profile = CandidateProfile(
        profile_id="cand_test_asset",
        assets=[AssetRecord(asset_id="asset_resume_pdf", title="成绩单",
                            asset_type="transcript", file_path="/tmp/transcript.pdf")],
    )
    assert ValueResolver.resolve(profile, None, "assets[asset_resume_pdf].file_path") is None


def test_named_education_level_resolves_latest_matching_record():
    from applypilot.domain.base import PartialDate
    from applypilot.domain.profile import EducationLevel, EducationRecord

    profile = CandidateProfile(
        profile_id="cand_edu",
        education=[
            EducationRecord(id="m1", school_name="旧校", education_level=EducationLevel.MASTER,
                            major="软件工程", start_date=PartialDate(year=2021, month=9),
                            end_date=PartialDate(year=2023, month=6)),
            EducationRecord(id="m2", school_name="新校", education_level=EducationLevel.MASTER,
                            major="软件工程", start_date=PartialDate(year=2023, month=9),
                            end_date=PartialDate(year=2025, month=6)),
        ],
    )
    assert ValueResolver.resolve(profile, None, "education[master].school_name") == "新校"
