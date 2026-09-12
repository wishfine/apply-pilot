"""Multi-stage automated job application state machine engine (ApplyEngine).

Coordinates platform detection, stage detection, element scanning, field mapping,
typed value resolution, disclosure gate, element filling, and human checkpoint handoff.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
import uuid

from applypilot.adapters.applications.base import ApplicationAdapter
from applypilot.adapters.applications.beisen import BeisenApplicationAdapter
from applypilot.adapters.applications.generic import GenericApplicationAdapter
from applypilot.adapters.applications.moka import MokaApplicationAdapter
from applypilot.adapters.detection import PlatformDetector
from applypilot.domain.job import ApplicationStatus, ApplicationTarget
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.variant import DisclosurePolicy, ResumeVariant
from applypilot.modules.apply.mapper import FieldMapper
from applypilot.modules.apply.normalizer import ValueKind, ValueNormalizerRegistry
from applypilot.modules.profile.resolver import ValueResolver
from applypilot.storage.repositories import (
    ApplicationRepository,
    CheckpointRepository,
    EventRepository,
    RevisionRepository,
    SnapshotRepository,
)


class ApplyEngine:
    """State machine pipeline executing end-to-end multi-stage form application runs."""

    def __init__(
        self,
        db_path: Union[Path, str],
        browser_backend: Any,
        platform_detector: Optional[PlatformDetector] = None,
        adapters: Optional[Dict[str, ApplicationAdapter]] = None,
        mapper: Optional[Any] = None,
        resolver: Optional[Any] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.browser = browser_backend
        self.browser_backend = browser_backend

        # Repositories
        self.app_repo = ApplicationRepository(self.db_path)
        self.chk_repo = CheckpointRepository(self.db_path)
        self.event_repo = EventRepository(self.db_path)
        self.snap_repo = SnapshotRepository(self.db_path)
        self.rev_repo = RevisionRepository(self.db_path)

        # Adapters and components
        self.adapters = (
            adapters
            if adapters is not None
            else {
                "generic": GenericApplicationAdapter(),
                "moka": MokaApplicationAdapter(),
                "beisen": BeisenApplicationAdapter(),
            }
        )
        self.detector = platform_detector or PlatformDetector()
        self.platform_detector = self.detector
        self.mapper = mapper or FieldMapper
        self.resolver = resolver or ValueResolver

    def _check_disclosure(self, policy: Optional[DisclosurePolicy], path: str) -> bool:
        """Evaluate path against disclosure gate policy."""
        if not policy:
            return True
        if path in policy.blocked_field_paths:
            return False
        if "family" in path and not policy.disclose_family:
            return False
        if "political" in path and not policy.disclose_political:
            return False
        if not policy.allow_sensitive and ("id_number" in path or "secret" in path):
            return False
        return True

    async def run_application_target(
        self,
        target: ApplicationTarget,
        profile: CandidateProfile,
        variant: Optional[ResumeVariant] = None,
    ) -> ApplicationStatus:
        """Execute the multi-stage form application state machine for a target job."""
        # -----------------------------------------------------------------
        # a. Application Record Management
        # -----------------------------------------------------------------
        app_id = f"app_{target.job.job_id}"
        cycle = target.job.recruitment_cycle or "default"
        app_key = f"{profile.profile_id}:{target.job.job_id}:{cycle}"

        existing_app = await self.app_repo.get_application(app_id)
        if not existing_app:
            await self.app_repo.create_application(
                app_id=app_id,
                application_key=app_key,
                candidate_id=profile.profile_id,
                canonical_job_id=target.job.job_id,
                company_name=target.job.company_name,
                job_title=target.job.title,
                recruitment_cycle=target.job.recruitment_cycle,
                status=ApplicationStatus.CREATED,
                assigned_variant_id=target.assigned_variant_id,
            )

        await self.app_repo.update_status(app_id, ApplicationStatus.IN_PROGRESS)

        # Ensure profile revision exists (satisfies foreign key constraint)
        profile_json = (
            profile.model_dump_json()
            if hasattr(profile, "model_dump_json")
            else json.dumps(profile)
        )
        p_hash = hashlib.sha256(profile_json.encode()).hexdigest()[:16]
        profile_rev_id = f"rev_{profile.profile_id}_{p_hash}"
        existing_p_rev = await self.rev_repo.get_profile_revision(profile_rev_id)
        if not existing_p_rev:
            await self.rev_repo.save_profile_revision(
                revision_id=profile_rev_id,
                profile_id=profile.profile_id,
                content_hash=p_hash,
                content_json=profile_json,
            )

        variant_rev_id = None
        if variant:
            variant_json = (
                variant.model_dump_json()
                if hasattr(variant, "model_dump_json")
                else json.dumps(variant)
            )
            v_hash = hashlib.sha256(variant_json.encode()).hexdigest()[:16]
            variant_rev_id = f"vrev_{variant.variant_id}_{v_hash}"
            existing_v_rev = (
                await self.rev_repo.get_variant_revision(variant_rev_id)
                if hasattr(self.rev_repo, "get_variant_revision")
                else None
            )
            if not existing_v_rev:
                await self.rev_repo.save_variant_revision(
                    revision_id=variant_rev_id,
                    variant_id=variant.variant_id,
                    content_hash=v_hash,
                    content_json=variant_json,
                )

        existing_runs = await self.app_repo.list_runs_by_application(app_id)
        run_index = len(existing_runs) + 1
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        await self.app_repo.create_run(
            run_id=run_id,
            application_id=app_id,
            run_index=run_index,
            profile_revision_id=profile_rev_id,
            variant_revision_id=variant_rev_id,
            adapter_name=target.provider or "generic",
            adapter_version="1.0.0",
            mapper_version="1.0.0",
            config_hash="default",
            status="running",
            run_mode="semi_auto",
            browser_session_id="local",
        )

        await self.event_repo.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            event_type="RUN_STARTED",
            payload_json={"target_id": target.target_id, "job_id": target.job.job_id},
        )

        # -----------------------------------------------------------------
        # b. Resume / Checkpoint Detection
        # -----------------------------------------------------------------
        latest_chk = await self.chk_repo.get_latest_checkpoint(app_id)
        if latest_chk:
            resumed_stage = latest_chk.get("stage_key")
            await self.event_repo.append_event(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                event_type="CHECKPOINT_RESUMED",
                payload_json={"stage_key": resumed_stage},
            )

        # -----------------------------------------------------------------
        # c. Navigation & Platform Adapter Selection
        # -----------------------------------------------------------------
        target_url = target.final_form_url or target.job.apply_url
        page = await self.browser.open_page(target_url)

        if target.provider and target.provider in self.adapters:
            adapter = self.adapters[target.provider]
        elif page and hasattr(page, "execute_unsafe_script"):
            report = await self.detector.detect(page)
            best_plat = (
                report.candidates[0].platform
                if report and report.candidates
                else "generic"
            )
            adapter = self.adapters.get(best_plat, self.adapters.get("generic"))
        else:
            adapter = self.adapters.get(
                "generic", next(iter(self.adapters.values()))
            )

        # -----------------------------------------------------------------
        # d. Multi-Stage Filling Loop (max 10 iterations)
        # -----------------------------------------------------------------
        for step in range(10):
            current_stage = (
                await adapter.detect_stage(page)
                if hasattr(adapter, "detect_stage")
                else "single_page"
            )

            snap_id = f"snap_{uuid.uuid4().hex[:12]}"

            await self.snap_repo.save_snapshot(
                snapshot_id=snap_id,
                run_id=run_id,
                page_url=target_url,
                dom_fingerprint="fp",
                fields_meta_json=[],
                stage_key=current_stage,
            )

            if hasattr(page, "find_all"):
                elements = await page.find_all(
                    "input:not([type='hidden']), select, textarea"
                )
                for element in elements:
                    name_attr = (
                        await element.get_attribute("name")
                        if hasattr(element, "get_attribute")
                        else None
                    )
                    placeholder = (
                        await element.get_attribute("placeholder")
                        if hasattr(element, "get_attribute")
                        else None
                    )
                    id_attr = (
                        await element.get_attribute("id")
                        if hasattr(element, "get_attribute")
                        else None
                    )
                    type_attr = (
                        await element.get_attribute("type")
                        if hasattr(element, "get_attribute")
                        else None
                    )

                    label = name_attr or placeholder or id_attr or ""
                    field_type = type_attr or "text"
                    field_sig = id_attr or name_attr or label

                    map_res = self.mapper.map_field(
                        field_sig=field_sig,
                        normalized_label=label,
                        section_title=current_stage,
                        field_type=field_type,
                    )
                    path, method, conf = map_res

                    if path:
                        if not self._check_disclosure(target.disclosure_policy, path):
                            continue

                        expected = self.resolver.resolve(profile, variant, path)
                        if expected is not None:
                            observed = None
                            if hasattr(element, "get_text"):
                                observed = await element.get_text()
                            if not observed and hasattr(element, "get_attribute"):
                                observed = await element.get_attribute("value")

                            if not ValueNormalizerRegistry.are_equivalent(
                                ValueKind.PLAIN_TEXT, observed, expected
                            ):
                                res = await adapter.fill_field(
                                    page,
                                    element,
                                    {
                                        "field_type": field_type,
                                        "field_sig": field_sig,
                                        "label": label,
                                    },
                                    expected,
                                )
                                action_type = str(getattr(res, "action_type", "type_text"))
                                status_str = "success" if getattr(res, "success", True) else "failed"
                                obs_val = (
                                    str(res.observed_value)
                                    if getattr(res, "observed_value", None) is not None
                                    else None
                                )
                                err_code = (
                                    str(res.error_code)
                                    if getattr(res, "error_code", None) is not None
                                    else None
                                )
                                await self.snap_repo.save_field_action(
                                    action_id=f"act_{uuid.uuid4().hex[:12]}",
                                    run_id=run_id,
                                    snapshot_id=snap_id,
                                    field_signature=field_sig,
                                    action_type=action_type,
                                    status=status_str,
                                    duration_ms=50,
                                    value_preview=obs_val,
                                    error_code=err_code,
                                )


            chk_id = f"chk_{uuid.uuid4().hex[:12]}"
            await self.chk_repo.save_checkpoint(
                checkpoint_id=chk_id,
                application_id=app_id,
                run_id=run_id,
                page_url=target_url,
                stage_key=current_stage,
                completed_fields_json=[],
                status="in_progress",
            )

            is_review = (
                await adapter.is_final_review(page)
                if hasattr(adapter, "is_final_review")
                else False
            )
            if is_review:
                break

            advanced = False
            if hasattr(adapter, "advance"):
                advanced = await adapter.advance(page, current_stage)
            if not advanced:
                break


        # -----------------------------------------------------------------
        # e. Human Review Station & Handoff
        # -----------------------------------------------------------------
        final_chk_id = f"chk_{uuid.uuid4().hex[:12]}"
        await self.chk_repo.save_checkpoint(
            checkpoint_id=final_chk_id,
            application_id=app_id,
            run_id=run_id,
            page_url=target_url,
            stage_key="final_review",
            completed_fields_json=[],
            status="ready_review",
        )

        await self.app_repo.update_status(app_id, ApplicationStatus.READY_REVIEW)
        await self.app_repo.update_run_status(run_id, "paused")

        await self.event_repo.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            event_type="READY_REVIEW",
            payload_json={"reason": "Human review required before submission"},
        )

        await self.browser.wait_for_user(
            "表单字段已填写完毕，请在浏览器中核对后亲自点击提交"
        )

        return ApplicationStatus.READY_REVIEW

    # Alias for run_application_target
    run_session = run_application_target
