"""Storage repositories for SQLite persistence layer."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Union
import aiosqlite


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_str(val: Any) -> str:
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False, default=str)


class BaseRepository:
    """Base repository providing standardized async connection management."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    @asynccontextmanager
    async def get_connection(self, enforce_fk: bool = True) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if enforce_fk:
                await db.execute("PRAGMA foreign_keys = ON;")
            yield db


class ApplicationRepository:
    """Repository for managing applications and execution runs."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def create_application(
        self,
        app_id: str,
        application_key: str,
        candidate_id: str,
        canonical_job_id: str,
        company_name: str,
        job_title: str,
        recruitment_cycle: Optional[str] = None,
        status: str = "created",
        current_stage: Optional[str] = None,
        assigned_variant_id: Optional[str] = None,
        target_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO applications (
                    id, application_key, candidate_id, canonical_job_id,
                    company_name, job_title, recruitment_cycle, status,
                    current_stage, assigned_variant_id, target_context_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_id,
                    application_key,
                    candidate_id,
                    canonical_job_id,
                    company_name,
                    job_title,
                    recruitment_cycle,
                    status,
                    current_stage,
                    assigned_variant_id,
                    _to_json_str(target_context) if target_context is not None else None,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def update_target_context(self, app_id: str, target_context: Dict[str, Any]) -> None:
        now = _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE applications SET target_context_json = ?, updated_at = ? WHERE id = ?",
                (_to_json_str(target_context), now, app_id),
            )
            await db.commit()

    async def get_application(self, app_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM applications WHERE id = ? OR
                (canonical_job_id = ? AND (SELECT count(*) FROM applications WHERE canonical_job_id = ?) = 1)
                ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END LIMIT 1""",
                (app_id, app_id.removeprefix("app_"), app_id.removeprefix("app_"), app_id),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_application_by_key(
        self, application_key: str
    ) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM applications WHERE application_key = ?",
                (application_key,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_applications(
        self,
        status: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM applications WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if candidate_id:
                query += " AND candidate_id = ?"
                params.append(candidate_id)
            query += " ORDER BY created_at DESC"
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def update_status(
        self,
        app_id: str,
        status: str,
        current_stage: Optional[str] = None,
    ) -> None:
        now = _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            if current_stage is not None:
                await db.execute(
                    """
                    UPDATE applications
                    SET status = ?, current_stage = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, current_stage, now, app_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE applications
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, app_id),
                )
            await db.commit()

    async def create_run(
        self,
        run_id: str,
        application_id: str,
        run_index: int = 1,
        profile_revision_id: str = "",
        adapter_name: str = "generic",
        adapter_version: str = "1.0.0",
        mapper_version: str = "1.0.0",
        config_hash: str = "default",
        status: str = "running",
        variant_revision_id: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        end_reason: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        start = start_time or _utc_now_iso()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO application_runs (
                    id, application_id, run_index, status, profile_revision_id,
                    variant_revision_id, adapter_name, adapter_version, mapper_version,
                    config_hash, llm_provider, llm_model, start_time, end_time, end_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    application_id,
                    run_index,
                    status,
                    profile_revision_id,
                    variant_revision_id,
                    adapter_name,
                    adapter_version,
                    mapper_version,
                    config_hash,
                    llm_provider,
                    llm_model,
                    start,
                    end_time,
                    end_reason,
                ),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM application_runs WHERE id = ?",
                (run_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_runs_by_application(self, application_id: str) -> List[Dict[str, Any]]:
        application = await ApplicationRepository(self.db_path).get_application(application_id)
        if application is None:
            return []
        application_id = application["id"]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM application_runs 
                WHERE application_id = ?
                ORDER BY run_index ASC
                """,
                (application_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        end_reason: Optional[str] = None,
    ) -> None:
        now = _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                UPDATE application_runs
                SET status = ?, end_time = ?, end_reason = ?
                WHERE id = ?
                """,
                (status, now, end_reason, run_id),
            )
            await db.commit()


class CheckpointRepository:
    """Repository for managing materialization checkpoints."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        application_id: str,
        run_id: str,
        page_url: str = "",
        stage_key: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        last_completed_field_sig: Optional[str] = None,
        status: str = "paused",
        created_at: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        now = created_at or _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO application_checkpoints (
                    id, application_id, run_id, page_url, stage_key,
                    snapshot_id, last_completed_field_sig, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    application_id,
                    run_id,
                    page_url,
                    stage_key,
                    snapshot_id,
                    last_completed_field_sig,
                    status,
                    now,
                ),
            )
            await db.commit()

    async def get_latest_checkpoint(self, application_id: str) -> Optional[Dict[str, Any]]:
        application = await ApplicationRepository(self.db_path).get_application(application_id)
        if application is None:
            return None
        application_id = application["id"]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM application_checkpoints
                WHERE application_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (application_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM application_checkpoints WHERE id = ?",
                (checkpoint_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None


class EventRepository:
    """Repository for append-only audit event logging."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def append_event(
        self,
        event_id: Optional[str] = None,
        run_id: str = "",
        event_type: str = "",
        payload_json: Union[str, Dict[str, Any], List[Any]] = "",
        created_at: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        evt_id = event_id or f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        now = created_at or _utc_now_iso()
        payload = _to_json_str(payload_json)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO application_events (
                    id, run_id, event_type, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (evt_id, run_id, event_type, payload, now),
            )
            await db.commit()


    async def list_events_by_run(self, run_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM application_events
                WHERE run_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (run_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


class SnapshotRepository:
    """Repository for form snapshots, field mappings, and field actions."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def save_snapshot(
        self,
        snapshot_id: str,
        run_id: str,
        page_url: str,
        dom_fingerprint: str,
        fields_meta_json: Union[str, Dict[str, Any], List[Any]],
        stage_key: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        now = created_at or _utc_now_iso()
        fields_str = _to_json_str(fields_meta_json)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO form_snapshots (
                    id, run_id, page_url, stage_key, dom_fingerprint,
                    fields_meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, run_id, page_url, stage_key, dom_fingerprint, fields_str, now),
            )
            await db.commit()

    async def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM form_snapshots WHERE id = ?",
                (snapshot_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_snapshot(
        self,
        snapshot_id: str,
        *,
        dom_fingerprint: Optional[str] = None,
        fields_meta_json: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    ) -> None:
        """Materialize metadata collected after the initial snapshot row."""
        updates: list[str] = []
        params: list[Any] = []
        if dom_fingerprint is not None:
            updates.append("dom_fingerprint = ?")
            params.append(dom_fingerprint)
        if fields_meta_json is not None:
            updates.append("fields_meta_json = ?")
            params.append(_to_json_str(fields_meta_json))
        if not updates:
            return
        params.append(snapshot_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE form_snapshots SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()

    async def save_field_mapping(
        self,
        mapping_id: str,
        snapshot_id: str,
        field_signature: Optional[str] = None,
        method: str = "exact_rule",
        confidence: float = 1.0,
        disclosure_allowed: bool = True,
        profile_path: Optional[str] = None,
        created_at: Optional[str] = None,
        field_sig: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        sig = field_signature or field_sig or ""
        now = created_at or _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO field_mappings (
                    id, snapshot_id, field_signature, profile_path,
                    method, confidence, disclosure_allowed, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mapping_id,
                    snapshot_id,
                    sig,
                    profile_path,
                    method,
                    confidence,
                    1 if disclosure_allowed else 0,
                    now,
                ),
            )
            await db.commit()


    async def get_field_mappings(self, snapshot_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM field_mappings WHERE snapshot_id = ? ORDER BY created_at ASC",
                (snapshot_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def save_field_action(
        self,
        action_id: str,
        run_id: str,
        snapshot_id: str,
        field_signature: str,
        action_type: str,
        status: str,
        duration_ms: int,
        mapping_id: Optional[str] = None,
        expected_hash: Optional[str] = None,
        observed_hash: Optional[str] = None,
        value_preview: Optional[str] = None,
        error_code: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        now = created_at or _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO field_actions (
                    id, run_id, snapshot_id, field_signature, mapping_id,
                    action_type, status, expected_hash, observed_hash,
                    value_preview, error_code, duration_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    run_id,
                    snapshot_id,
                    field_signature,
                    mapping_id,
                    action_type,
                    status,
                    expected_hash,
                    observed_hash,
                    value_preview,
                    error_code,
                    duration_ms,
                    now,
                ),
            )
            await db.commit()

    async def list_field_actions(self, run_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM field_actions WHERE run_id = ? ORDER BY created_at ASC, rowid ASC",
                (run_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


class CorrectionRepository:
    """Repository for scoped correction memories."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def save_correction(
        self,
        correction_id: str,
        provider: str,
        normalized_label: str,
        field_type: str,
        corrected_semantic_path: str,
        confidence: float = 1.0,
        tenant_hint: Optional[str] = None,
        section_signature: Optional[str] = None,
        options_signature: Optional[str] = None,
        hit_count: int = 1,
        last_used_at: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        now = last_used_at or _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO correction_memories (
                    id, provider, tenant_hint, section_signature,
                    options_signature, normalized_label, field_type,
                    corrected_semantic_path, confidence, hit_count,
                    last_used_at, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correction_id,
                    provider,
                    tenant_hint,
                    section_signature,
                    options_signature,
                    normalized_label,
                    field_type,
                    corrected_semantic_path,
                    confidence,
                    hit_count,
                    now,
                    1 if enabled else 0,
                ),
            )
            await db.commit()

    async def lookup_corrections(
        self,
        provider: Optional[str] = None,
        normalized_label: Optional[str] = None,
        section_signature: Optional[str] = None,
        tenant_hint: Optional[str] = None,
        platform: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        prov = provider or platform or "generic"
        conditions = ["provider = ?", "enabled = 1"]
        params: List[Any] = [prov]

        if normalized_label is not None:
            conditions.append("normalized_label = ?")
            params.append(normalized_label)

        if section_signature is not None:
            conditions.append("(section_signature = ? OR section_signature IS NULL)")
            params.append(section_signature)

        if tenant_hint is not None:
            conditions.append("(tenant_hint = ? OR tenant_hint IS NULL)")
            params.append(tenant_hint)

        order_clauses = []
        if section_signature is not None:
            order_clauses.append("(CASE WHEN section_signature = ? THEN 0 ELSE 1 END) ASC")
            params.append(section_signature)
        if tenant_hint is not None:
            order_clauses.append("(CASE WHEN tenant_hint = ? THEN 0 ELSE 1 END) ASC")
            params.append(tenant_hint)
        order_clauses.extend(["confidence DESC", "hit_count DESC", "last_used_at DESC"])

        query = f"""
            SELECT * FROM correction_memories
            WHERE {' AND '.join(conditions)}
            ORDER BY {', '.join(order_clauses)}
        """

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


    async def increment_hit_count(self, memory_id: str) -> None:
        now = _utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                UPDATE correction_memories
                SET hit_count = hit_count + 1, last_used_at = ?
                WHERE id = ?
                """,
                (now, memory_id),
            )
            await db.commit()


class RevisionRepository:
    """Repository for candidate profile and resume variant revisions."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path)

    async def save_profile_revision(
        self,
        revision_id: str,
        profile_id: str,
        content_hash: str,
        content_json: Union[str, Dict[str, Any], List[Any]],
        created_at: Optional[str] = None,
    ) -> None:
        now = created_at or _utc_now_iso()
        content = _to_json_str(content_json)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO profile_revisions (
                    id, profile_id, content_hash, content_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (revision_id, profile_id, content_hash, content, now),
            )
            await db.commit()

    async def get_profile_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM profile_revisions WHERE id = ?",
                (revision_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_latest_profile_revision(self, profile_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM profile_revisions
                WHERE profile_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (profile_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def save_variant_revision(
        self,
        revision_id: str,
        variant_id: str,
        content_hash: str,
        content_json: Union[str, Dict[str, Any], List[Any]],
        created_at: Optional[str] = None,
    ) -> None:
        now = created_at or _utc_now_iso()
        content = _to_json_str(content_json)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                """
                INSERT INTO resume_variant_revisions (
                    id, variant_id, content_hash, content_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (revision_id, variant_id, content_hash, content, now),
            )
            await db.commit()

    async def get_variant_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM resume_variant_revisions WHERE id = ?",
                (revision_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_variant_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM resume_variant_revisions WHERE id = ?",
                (revision_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
