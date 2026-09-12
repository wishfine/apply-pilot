"""Multi-signal platform detection and candidate ranking."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator

from applypilot.browser.base import BrowserPage


class DetectionEvidence(BaseModel):
    """Evidence signal gathered during platform detection."""

    signal_type: str  # "host", "dom", "script", "meta", "fallback"
    detail: str
    weight: float


class DetectionResult(BaseModel):
    """Platform candidate with aggregated confidence and supporting evidences."""

    platform: str  # "beisen", "moka", "generic"
    confidence: float = Field(ge=0.0, le=1.0)
    evidences: list[DetectionEvidence] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        try:
            val = float(v)
            return round(min(1.0, max(0.0, val)), 4)
        except (ValueError, TypeError):
            return 0.0


class DetectionReport(BaseModel):
    """Ranked report containing platform candidates sorted by confidence."""

    candidates: list[DetectionResult]

    @property
    def best_candidate(self) -> Optional[DetectionResult]:
        """Returns the highest-confidence platform candidate, or None if empty."""
        if not self.candidates:
            return None
        return self.candidates[0]


class PlatformDetector:
    """Multi-signal detector identifying recruitment platforms via host, DOM, and runtime."""

    @classmethod
    async def detect(cls, page: BrowserPage) -> DetectionReport:
        """Detect recruitment platform using multi-signal heuristics.

        Evaluates host patterns, DOM signatures, and runtime JavaScript globals
        for known platforms (Beisen, Moka), returning ranked candidates with a
        generic fallback.
        """
        try:
            raw_url = await page.url()
            current_url = (raw_url or "").strip().lower()
        except Exception:
            current_url = ""

        candidates: list[DetectionResult] = []

        async def _safe_eval(reason: str, script: str) -> bool:
            try:
                result = await page.execute_unsafe_script(reason, script)
                return bool(result)
            except Exception:
                return False

        # 1. Beisen Detection
        beisen_evidences: list[DetectionEvidence] = []
        # Host signal (0.6)
        if "italent.cn" in current_url or "beisen.com" in current_url:
            beisen_evidences.append(
                DetectionEvidence(
                    signal_type="host",
                    detail=f"Matched Beisen host pattern in URL ({current_url})",
                    weight=0.6,
                )
            )

        # Script signal (0.4)
        if await _safe_eval("detect beisen runtime", "Boolean(window.BS || window.italent)"):
            beisen_evidences.append(
                DetectionEvidence(
                    signal_type="script",
                    detail="Detected Beisen runtime objects (window.BS or window.italent)",
                    weight=0.4,
                )
            )

        # DOM signal (0.3)
        if await _safe_eval(
            "detect beisen dom",
            'Boolean(document.querySelector(\'[class*="italent"], [class*="beisen"], [id*="italent"], meta[content*="italent"]\'))',
        ):
            beisen_evidences.append(
                DetectionEvidence(
                    signal_type="dom",
                    detail="Detected Beisen DOM / meta signatures",
                    weight=0.3,
                )
            )

        beisen_score = round(min(1.0, sum(e.weight for e in beisen_evidences)), 4)
        if beisen_score > 0:
            candidates.append(
                DetectionResult(
                    platform="beisen",
                    confidence=beisen_score,
                    evidences=beisen_evidences,
                )
            )

        # 2. Moka Detection
        moka_evidences: list[DetectionEvidence] = []
        # Host signal (0.6)
        if "mokahr.com" in current_url or "moka.com" in current_url:
            moka_evidences.append(
                DetectionEvidence(
                    signal_type="host",
                    detail=f"Matched Moka host pattern in URL ({current_url})",
                    weight=0.6,
                )
            )

        # DOM signal (0.4)
        if await _safe_eval(
            "detect moka dom",
            'Boolean(document.querySelector(\'[class*="moka-"], [class*="moka_"], [id*="moka-"], .moka-form\'))',
        ):
            moka_evidences.append(
                DetectionEvidence(
                    signal_type="dom",
                    detail="Detected Moka DOM signatures",
                    weight=0.4,
                )
            )

        # Script signal (0.3)
        if await _safe_eval(
            "detect moka runtime",
            "Boolean(window.moka || window.__MOKA__ || window.__INITIAL_STATE__)",
        ):
            moka_evidences.append(
                DetectionEvidence(
                    signal_type="script",
                    detail="Detected Moka runtime objects (window.moka, __MOKA__, or __INITIAL_STATE__)",
                    weight=0.3,
                )
            )

        moka_score = round(min(1.0, sum(e.weight for e in moka_evidences)), 4)
        if moka_score > 0:
            candidates.append(
                DetectionResult(
                    platform="moka",
                    confidence=moka_score,
                    evidences=moka_evidences,
                )
            )

        # 3. Generic Fallback (0.3 baseline)
        candidates.append(
            DetectionResult(
                platform="generic",
                confidence=0.3,
                evidences=[
                    DetectionEvidence(
                        signal_type="fallback",
                        detail="Generic fallback baseline adapter",
                        weight=0.3,
                    )
                ],
            )
        )

        # 4. Rank candidates descending by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return DetectionReport(candidates=candidates)
