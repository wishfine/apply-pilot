"""Unit tests for multi-signal PlatformDetector and candidate ranking."""

import pytest
from unittest.mock import AsyncMock

from applypilot.adapters.detection import (
    DetectionEvidence,
    DetectionResult,
    DetectionReport,
    PlatformDetector,
)
from applypilot.core.exceptions import BrowserDriverError


class MockPage:
    """Mock BrowserPage for platform detection testing."""

    def __init__(
        self,
        current_url: str = "about:blank",
        scripts_present: list[str] | None = None,
        dom_classes: list[str] | None = None,
        script_eval_map: dict[str, bool] | None = None,
        script_exception: Exception | None = None,
        url_exception: Exception | None = None,
    ):
        self._url = current_url
        self._scripts = scripts_present or []
        self._dom_classes = dom_classes or []
        self._script_eval_map = script_eval_map or {}
        self._script_exception = script_exception
        self._url_exception = url_exception
        self.script_call_log: list[tuple[str, str]] = []

    async def url(self) -> str:
        if self._url_exception:
            raise self._url_exception
        return self._url

    async def title(self) -> str:
        return "招聘岗位"

    async def execute_unsafe_script(self, reason: str, script: str, arg=None):
        self.script_call_log.append((reason, script))
        if self._script_exception:
            raise self._script_exception

        # Check explicit script_eval_map first
        if reason in self._script_eval_map:
            return self._script_eval_map[reason]
        if script in self._script_eval_map:
            return self._script_eval_map[script]

        # General simulation
        if "detect beisen runtime" in reason:
            return any("italent" in s or "BS" in s for s in self._scripts)
        if "detect beisen dom" in reason:
            return any("italent" in c or "beisen" in c for c in self._dom_classes)
        if "detect moka dom" in reason:
            return any("moka" in c for c in self._dom_classes)
        if "detect moka runtime" in reason:
            return any("moka" in s for s in self._scripts)

        return False


def test_detection_evidence_model():
    evidence = DetectionEvidence(
        signal_type="host",
        detail="italent domain",
        weight=0.6,
    )
    assert evidence.signal_type == "host"
    assert evidence.detail == "italent domain"
    assert evidence.weight == 0.6


def test_detection_result_model():
    result = DetectionResult(
        platform="beisen",
        confidence=0.85,
        evidences=[
            DetectionEvidence(signal_type="host", detail="beisen.com", weight=0.6),
            DetectionEvidence(signal_type="script", detail="BS runtime", weight=0.4),
        ],
    )
    assert result.platform == "beisen"
    assert result.confidence == 0.85
    assert len(result.evidences) == 2


def test_detection_result_clamping():
    res_high = DetectionResult(platform="beisen", confidence=1.4)
    assert res_high.confidence == 1.0

    res_low = DetectionResult(platform="moka", confidence=-0.5)
    assert res_low.confidence == 0.0


def test_detection_report_best_candidate():
    r1 = DetectionResult(platform="beisen", confidence=0.9)
    r2 = DetectionResult(platform="generic", confidence=0.3)
    report = DetectionReport(candidates=[r1, r2])

    assert report.best_candidate is not None
    assert report.best_candidate.platform == "beisen"
    assert report.best_candidate.confidence == 0.9

    empty_report = DetectionReport(candidates=[])
    assert empty_report.best_candidate is None


@pytest.mark.asyncio
async def test_detect_beisen_platform_full_match():
    page = MockPage(
        current_url="https://cmpc.italent.cn/campus/job/1001",
        scripts_present=["italent-sdk.js"],
        dom_classes=["italent-header", "beisen-layout"],
    )
    report = await PlatformDetector.detect(page)

    assert isinstance(report, DetectionReport)
    assert len(report.candidates) >= 2  # Beisen + Generic fallback
    top = report.best_candidate
    assert top is not None
    assert top.platform == "beisen"
    assert top.confidence >= 0.85
    assert top.confidence == 1.0

    signal_types = [e.signal_type for e in top.evidences]
    assert "host" in signal_types
    assert "script" in signal_types
    assert "dom" in signal_types


@pytest.mark.asyncio
async def test_detect_beisen_host_only():
    page = MockPage(
        current_url="https://jobs.beisen.com/apply/123",
        scripts_present=[],
        dom_classes=[],
    )
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "beisen"
    assert top.confidence == 0.6
    assert len(top.evidences) == 1
    assert top.evidences[0].signal_type == "host"


@pytest.mark.asyncio
async def test_detect_beisen_script_only():
    page = MockPage(
        current_url="https://careers.customcorp.com/openings",
        scripts_present=["window.BS"],
        dom_classes=[],
    )
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "beisen"
    assert top.confidence == 0.4
    assert len(top.evidences) == 1
    assert top.evidences[0].signal_type == "script"


@pytest.mark.asyncio
async def test_detect_beisen_dom_only():
    page = MockPage(
        current_url="https://careers.customcorp.com/openings",
        scripts_present=[],
        dom_classes=["beisen-job-detail"],
    )
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "beisen"
    assert top.confidence == 0.3
    assert len(top.evidences) == 1
    assert top.evidences[0].signal_type == "dom"


@pytest.mark.asyncio
async def test_detect_moka_host_and_dom():
    page = MockPage(
        current_url="https://app.mokahr.com/campus-recruitment/xyz",
        scripts_present=[],
        dom_classes=["moka-form", "moka-apply-container"],
    )
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "moka"
    # host (0.6) + dom (0.4) = 1.0
    assert top.confidence == 1.0
    signal_types = [e.signal_type for e in top.evidences]
    assert "host" in signal_types
    assert "dom" in signal_types


@pytest.mark.asyncio
async def test_detect_moka_script_only():
    page = MockPage(
        current_url="https://career.myenterprise.com/join",
        scripts_present=["moka-runtime"],
        dom_classes=[],
    )
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "moka"
    assert top.confidence == 0.3
    assert len(top.evidences) == 1
    assert top.evidences[0].signal_type == "script"


@pytest.mark.asyncio
async def test_detect_generic_fallback_when_no_signals():
    page = MockPage(
        current_url="https://careers.smallbiz.com/jobs/1",
        scripts_present=[],
        dom_classes=[],
    )
    report = await PlatformDetector.detect(page)

    assert len(report.candidates) == 1
    top = report.best_candidate
    assert top is not None
    assert top.platform == "generic"
    assert top.confidence == 0.3
    assert top.evidences[0].signal_type == "fallback"


@pytest.mark.asyncio
async def test_detect_ranking_multiple_candidates():
    # Page with Beisen host (0.6) and Moka runtime script (0.3)
    page = MockPage(
        current_url="https://talents.italent.cn/jobs/1",
        scripts_present=["moka-script"],
        dom_classes=[],
    )
    report = await PlatformDetector.detect(page)

    platforms = [c.platform for c in report.candidates]
    assert "beisen" in platforms
    assert "moka" in platforms
    assert "generic" in platforms

    # Verify descending confidence
    confidences = [c.confidence for c in report.candidates]
    assert confidences == sorted(confidences, reverse=True)
    assert report.best_candidate.platform == "beisen"
    assert report.best_candidate.confidence == 0.6


@pytest.mark.asyncio
async def test_resilience_when_script_evaluation_fails():
    page = MockPage(
        current_url="https://talents.italent.cn/jobs/1",
        script_exception=BrowserDriverError("Browser context detached"),
    )
    # Should not raise exception
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    assert top.platform == "beisen"
    assert top.confidence == 0.6  # Host signal still captured


@pytest.mark.asyncio
async def test_resilience_when_url_retrieval_fails():
    page = MockPage(
        current_url="https://talents.italent.cn/jobs/1",
        url_exception=RuntimeError("Connection lost"),
        scripts_present=["italent-sdk"],
    )
    # Should not raise exception
    report = await PlatformDetector.detect(page)

    top = report.best_candidate
    assert top is not None
    # Script detected Beisen even though URL failed
    assert top.platform == "beisen"
    assert top.confidence >= 0.4


@pytest.mark.asyncio
async def test_prevent_false_positives_in_query_params():
    # A search engine query or blog URL referring to italent.cn or mokahr.com must NOT match host
    page = MockPage(
        current_url="https://www.google.com/search?q=italent.cn+review",
    )
    report = await PlatformDetector.detect(page)
    top = report.best_candidate
    assert top is not None
    assert top.platform == "generic"

    moka_blog = MockPage(
        current_url="https://blog.techcareer.com/article/123?ref=mokahr.com",
    )
    report_blog = await PlatformDetector.detect(moka_blog)
    assert report_blog.best_candidate.platform == "generic"

