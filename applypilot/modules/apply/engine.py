"""Multi-stage automated job application state machine engine (ApplyEngine).

Coordinates platform detection, stage detection, element scanning, field mapping,
typed value resolution, disclosure gate, element filling, and human checkpoint handoff.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union
import uuid

logger = logging.getLogger(__name__)

from applypilot.adapters.applications.base import ApplicationAdapter
from applypilot.adapters.applications.beisen import BeisenApplicationAdapter
from applypilot.adapters.applications.generic import GenericApplicationAdapter
from applypilot.adapters.applications.moka import MokaApplicationAdapter
from applypilot.adapters.detection import PlatformDetector
from applypilot.core.privacy import AuditSanitizer, get_local_audit_secret
from applypilot.domain.base import FieldPolicy, LogStrategy, SensitivityLevel
from applypilot.domain.job import ApplicationStatus, ApplicationTarget
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.variant import DisclosurePolicy, ResumeVariant
from applypilot.modules.apply.mapper import FieldMapper
from applypilot.modules.apply.normalizer import ValueKind, ValueNormalizerRegistry
from applypilot.modules.apply.readiness import FormRequirementDetector, ReadinessAuditor
from applypilot.modules.profile.resolver import ValueResolver
from applypilot.storage.repositories import (
    ApplicationRepository,
    CheckpointRepository,
    CorrectionRepository,
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
        interactive_readiness: bool = True,
        readiness_resolver: Optional[Callable] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.browser = browser_backend
        self.browser_backend = browser_backend
        self.interactive_readiness = interactive_readiness
        self.readiness_resolver = readiness_resolver

        # Repositories
        self.app_repo = ApplicationRepository(self.db_path)
        self.chk_repo = CheckpointRepository(self.db_path)
        self.event_repo = EventRepository(self.db_path)
        self.snap_repo = SnapshotRepository(self.db_path)
        self.rev_repo = RevisionRepository(self.db_path)
        self.corr_repo = CorrectionRepository(self.db_path)

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

    @staticmethod
    def _infer_value_kind(path: str) -> ValueKind:
        """Infer semantic ValueKind from canonical profile path for normalized readback comparison."""
        p = path.lower()
        if "city" in p:
            return ValueKind.CITY
        if "phone" in p or "mobile" in p:
            return ValueKind.PHONE
        if "date" in p or "birth" in p:
            return ValueKind.DATE
        if "education_level" in p:
            return ValueKind.EDUCATION_LEVEL
        if "academic_degree" in p or "degree" in p:
            return ValueKind.ACADEMIC_DEGREE
        if "political" in p:
            return ValueKind.POLITICAL_STATUS
        if "name" in p:
            return ValueKind.PERSON_NAME
        if "email" in p:
            return ValueKind.EMAIL
        return ValueKind.PLAIN_TEXT

    def _check_disclosure(self, policy: Optional[DisclosurePolicy], path: str) -> bool:
        """Evaluate path against disclosure gate policy. Defaults to strict policy when None."""
        effective_policy = policy if policy is not None else DisclosurePolicy()
        if path in effective_policy.blocked_field_paths:
            return False
        if "family" in path and not effective_policy.disclose_family:
            return False
        if "political" in path and not effective_policy.disclose_political:
            return False
        if not effective_policy.allow_sensitive and ("id_number" in path or "secret" in path):
            return False
        return True

    @staticmethod
    async def _live_field(element: Any) -> Optional[dict[str, Any]]:
        # The optional state API must be explicitly implemented by the backend.
        if callable(getattr(type(element), "inspect_field", None)):
            return await element.inspect_field()
        return None

    async def _refresh_readiness(self, fields: list[dict], elements: list[Any]) -> None:
        for field, element in zip(fields, elements):
            try:
                state = await self._live_field(element)
                if state is not None:
                    field["observed_value"] = state["observed_value"]
                    field["is_valid"] = state["is_valid"]
                    if state.get("is_active") is False:
                        field["is_required"] = False
            except Exception:
                field["observed_value"] = None
                field["is_valid"] = False

    async def _pause_application(self, app_id: str, run_id: str, url: str,
                                 stage: str, snapshot_id: str) -> ApplicationStatus:
        await self.app_repo.update_status(app_id, ApplicationStatus.PAUSED, current_stage=stage)
        await self.app_repo.update_run_status(run_id, "paused")
        await self.chk_repo.save_checkpoint(
            checkpoint_id=f"chk_{uuid.uuid4().hex[:12]}", application_id=app_id,
            run_id=run_id, page_url=url, stage_key=stage, snapshot_id=snapshot_id,
            status="paused",
        )
        return ApplicationStatus.PAUSED

    async def run_application_target(
        self,
        target: ApplicationTarget,
        profile: CandidateProfile,
        variant: Optional[ResumeVariant] = None,
    ) -> ApplicationStatus:
        """Execute the multi-stage form application state machine for a target job."""
        run_id: Optional[str] = None
        try:
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

            current_platform = "generic"
            if target.provider and target.provider in self.adapters:
                current_platform = target.provider
                adapter = self.adapters[target.provider]
            elif page and hasattr(page, "execute_unsafe_script"):
                report = await self.detector.detect(page)
                best_plat = (
                    report.candidates[0].platform
                    if report and report.candidates
                    else "generic"
                )
                current_platform = best_plat
                adapter = self.adapters.get(best_plat, self.adapters.get("generic"))
            else:
                adapter = self.adapters.get(
                    "generic", next(iter(self.adapters.values()))
                )

            corrections = await self.corr_repo.lookup_corrections(platform=current_platform)

            # -----------------------------------------------------------------
            # d. Multi-Stage Filling Loop (max 10 iterations)
            # -----------------------------------------------------------------
            completed_normally = False
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

                stage_scanned_fields: list[dict[str, Any]] = []
                scanned_elements: list[Any] = []

                if hasattr(page, "find_all"):
                    elements = await page.find_all(
                        "input:not([type='hidden']), select, textarea"
                    )
                    for element in elements:
                        try:
                            live_state = await self._live_field(element)
                            if live_state is not None:
                                if live_state.get("is_active") is False:
                                    continue
                                label = live_state["label"]
                                field_sig = live_state["field_sig"]
                                tag_str = live_state["tag"]
                                type_str = live_state["type"]
                                field_type = ("select" if tag_str == "select" else
                                              "text" if tag_str == "textarea" else type_str or "text")
                                element_attrs = live_state["element_attrs"]
                                outer_html = live_state["outer_html"]
                            else:
                                aria_label = (
                                    await element.get_attribute("aria-label")
                                    if hasattr(element, "get_attribute")
                                    else None
                                )
                                title_attr = (
                                    await element.get_attribute("title")
                                    if hasattr(element, "get_attribute")
                                    else None
                                )
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

                                tag_name = None
                                if hasattr(element, "get_attribute"):
                                    try:
                                        t_val = await element.get_attribute("tagName")
                                        if not t_val:
                                            t_val = await element.get_attribute("tag")
                                        if isinstance(t_val, str):
                                            tag_name = t_val
                                    except Exception:
                                        pass
                                if tag_name is None and hasattr(element, "evaluate"):
                                    try:
                                        t_val = await element.evaluate("el => el.tagName")
                                        if isinstance(t_val, str):
                                            tag_name = t_val
                                    except Exception:
                                        pass
                                if tag_name is None and hasattr(element, "tag_name"):
                                    try:
                                        if isinstance(element.tag_name, str):
                                            tag_name = element.tag_name
                                        elif inspect.iscoroutinefunction(element.tag_name):
                                            t_val = await element.tag_name()
                                            if isinstance(t_val, str):
                                                tag_name = t_val
                                        elif callable(element.tag_name):
                                            t_val = element.tag_name()
                                            if inspect.iscoroutine(t_val) or inspect.isawaitable(t_val):
                                                t_val = await t_val
                                            if isinstance(t_val, str):
                                                tag_name = t_val
                                    except Exception:
                                        pass

                                label = aria_label or title_attr or name_attr or placeholder or id_attr or ""
                                tag_str = str(tag_name).strip().lower() if tag_name else ""
                                type_str = str(type_attr).strip().lower() if type_attr else ""

                                if tag_str == "select" or type_str in ("select", "select-one", "select-multiple"):
                                    field_type = "select"
                                elif type_str == "file":
                                    field_type = "file"
                                elif type_str in ("radio", "checkbox"):
                                    field_type = type_str
                                else:
                                    field_type = type_str or "text"

                                field_sig = id_attr or name_attr or aria_label or label

                                # Collect element attributes for requirement detection
                                element_attrs: dict[str, Any] = {}
                                if hasattr(element, "get_attribute"):
                                    for attr_name in (
                                        "required",
                                        "aria-required",
                                        "type",
                                        "name",
                                        "id",
                                        "placeholder",
                                        "class",
                                    ):
                                        try:
                                            attr_val = await element.get_attribute(attr_name)
                                            if attr_val is not None:
                                                element_attrs[attr_name] = attr_val
                                        except Exception:
                                            pass

                                outer_html = None
                                if hasattr(element, "get_attribute"):
                                    try:
                                        o_val = await element.get_attribute("outerHTML")
                                        if isinstance(o_val, str):
                                            outer_html = o_val
                                    except Exception:
                                        pass
                                if outer_html is None and hasattr(element, "evaluate"):
                                    try:
                                        o_val = await element.evaluate("el => el.outerHTML")
                                        if isinstance(o_val, str):
                                            outer_html = o_val
                                    except Exception:
                                        pass

                            is_required = FormRequirementDetector.is_field_required(
                                element_attrs=element_attrs,
                                label=label,
                                outer_html=outer_html,
                            )

                            map_res = self.mapper.map_field(
                                field_sig=field_sig,
                                normalized_label=label,
                                section_title=current_stage,
                                field_type=field_type,
                                correction_memories=corrections,
                            )
                            path, method, conf = map_res

                            mapping_id = f"map_{uuid.uuid4().hex[:12]}"
                            disclosure_allowed = (
                                self._check_disclosure(target.disclosure_policy, path)
                                if path
                                else False
                            )
                            await self.snap_repo.save_field_mapping(
                                mapping_id=mapping_id,
                                snapshot_id=snap_id,
                                field_signature=field_sig,
                                profile_path=path,
                                method=method,
                                confidence=conf,
                                disclosure_allowed=disclosure_allowed,
                            )

                            observed = live_state["observed_value"] if live_state is not None else None
                            if live_state is None:
                                if hasattr(element, "get_text"):
                                    observed = await element.get_text()
                                if not observed and hasattr(element, "get_attribute"):
                                    observed = await element.get_attribute("value")

                            if path and disclosure_allowed:
                                expected = self.resolver.resolve(profile, variant, path)
                                if expected is not None:
                                    kind = self._infer_value_kind(path)
                                    if not ValueNormalizerRegistry.are_equivalent(
                                        kind, observed, expected
                                    ):
                                        res = await adapter.fill_field(
                                            page,
                                            element,
                                            {
                                                "field_type": field_type,
                                                "field_sig": field_sig,
                                                "label": label,
                                                "type": type_str,
                                                "tag": tag_str,
                                            },
                                            expected,
                                        )
                                        action_type = str(getattr(res, "action_type", "type_text"))
                                        status_str = "success" if getattr(res, "success", True) else "failed"
                                        after_fill = await self._live_field(element)
                                        obs_raw = (after_fill["observed_value"] if after_fill is not None
                                                   else getattr(res, "observed_value", None))
                                        sensitive = any(key in path for key in ("id_number", "political", "family", "secret"))
                                        field_policy = FieldPolicy(
                                            path_pattern=path,
                                            sensitivity=SensitivityLevel.SENSITIVE if sensitive else SensitivityLevel.PERSONAL,
                                            llm_allowed=False, log_strategy=LogStrategy.MASK,
                                        )
                                        obs_val = AuditSanitizer.mask_value(field_policy, obs_raw)
                                        secret = get_local_audit_secret()
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
                                            mapping_id=mapping_id,
                                            action_type=action_type,
                                            status=status_str,
                                            duration_ms=50,
                                            value_preview=obs_val,
                                            expected_hash=AuditSanitizer.compute_fingerprint(secret, raw_value=expected),
                                            observed_hash=AuditSanitizer.compute_fingerprint(secret, raw_value=obs_raw),
                                            error_code=err_code,
                                        )
                                        if after_fill is not None:
                                            observed = after_fill["observed_value"]
                                        elif getattr(res, "observed_value", None) is not None:
                                            observed = res.observed_value
                                        elif getattr(res, "success", True):
                                            observed = expected

                            scanned_elements.append(element)
                            stage_scanned_fields.append({
                                "field_sig": field_sig,
                                "label": label,
                                "section_title": current_stage,
                                "is_required": is_required,
                                "mapped_path": path,
                                "observed_value": observed,
                                "element_attrs": element_attrs,
                                "outer_html": outer_html,
                            })
                        except Exception as e:
                            logger.warning(
                                "Failed to inspect or process form element on stage '%s': %s",
                                current_stage,
                                e,
                            )
                            continue

                # Re-read all controls after filling, including radio groups.
                await self._refresh_readiness(stage_scanned_fields, scanned_elements)

                # Stage readiness diagnostics and interactive resolution
                report = ReadinessAuditor.audit_fields(
                    stage_scanned_fields, profile, variant
                )
                if not report.is_ready:
                    await self.event_repo.append_event(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        run_id=run_id,
                        event_type="READINESS_AUDIT_HALTED",
                        payload_json={
                            "stage": current_stage,
                            "missing_required": [
                                item.model_dump(mode="json", exclude={"observed_value"})
                                for item in report.missing_required
                            ],
                        },
                    )
                    if self.interactive_readiness:
                        if self.readiness_resolver is not None:
                            res = self.readiness_resolver(
                                page, report, profile, variant
                            )
                            if inspect.iscoroutine(res) or inspect.isawaitable(res):
                                res = await res
                            if res == ApplicationStatus.PAUSED or res is False:
                                return await self._pause_application(
                                    app_id, run_id, target_url, current_stage, snap_id
                                )
                        else:
                            missing_labels = ", ".join(
                                item.label or item.field_sig
                                for item in report.missing_required
                            )
                            await self.browser.wait_for_user(
                                f"阶段【{current_stage}】存在 {len(report.missing_required)} 个必填缺失项：{missing_labels}，请在浏览器中核对补填"
                            )
                    else:
                        return await self._pause_application(
                            app_id, run_id, target_url, current_stage, snap_id
                        )

                if not report.is_ready:
                    await self._refresh_readiness(stage_scanned_fields, scanned_elements)
                    report = ReadinessAuditor.audit_fields(stage_scanned_fields, profile, variant)
                    if not report.is_ready:
                        return await self._pause_application(
                            app_id, run_id, target_url, current_stage, snap_id
                        )

                chk_id = f"chk_{uuid.uuid4().hex[:12]}"
                await self.chk_repo.save_checkpoint(
                    checkpoint_id=chk_id,
                    application_id=app_id,
                    run_id=run_id,
                    page_url=target_url,
                    stage_key=current_stage,
                    snapshot_id=snap_id,
                    completed_fields_json=[],
                    status="in_progress",
                )

                is_review = (
                    await adapter.is_final_review(page)
                    if hasattr(adapter, "is_final_review")
                    else False
                )
                if is_review:
                    completed_normally = True
                    break

                advanced = False
                if hasattr(adapter, "advance"):
                    advanced = await adapter.advance(page, current_stage)
                if not advanced:
                    return await self._pause_application(
                        app_id, run_id, target_url, current_stage, snap_id
                    )

            if not completed_normally:
                await self.app_repo.update_run_status(
                    run_id, status="failed", end_reason="MAX_STAGES_EXCEEDED"
                )
                await self.event_repo.append_event(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    run_id=run_id,
                    event_type="RUN_FAILED",
                    payload_json={
                        "error": "Exceeded maximum stage transitions without reaching final review"
                    },
                )
                raise RuntimeError(
                    "Exceeded maximum stage transitions without reaching final review"
                )

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

            await self.app_repo.update_status(
                app_id, ApplicationStatus.READY_REVIEW, current_stage="final_review"
            )
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

        except Exception as e:
            if run_id is not None:
                run_rec = await self.app_repo.get_run(run_id)
                if not run_rec or run_rec.get("status") != "failed":
                    await self.app_repo.update_run_status(
                        run_id, status="failed", end_reason=str(e)
                    )
                    await self.event_repo.append_event(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        run_id=run_id,
                        event_type="RUN_FAILED",
                        payload_json={"error": str(e)},
                    )
            raise


    # Alias for run_application_target
    run_session = run_application_target
