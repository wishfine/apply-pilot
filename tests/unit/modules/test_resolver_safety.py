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
