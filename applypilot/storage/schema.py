"""SQLite 10-table physical schema definition according to design specification section 4.3."""

CREATE_TABLES_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 1. 候选人主档案不可变历史版本镜像
CREATE TABLE IF NOT EXISTS profile_revisions (
    id VARCHAR(64) PRIMARY KEY,
    profile_id VARCHAR(64) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

-- 2. 简历变体不可变历史版本镜像
CREATE TABLE IF NOT EXISTS resume_variant_revisions (
    id VARCHAR(64) PRIMARY KEY,
    variant_id VARCHAR(64) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

-- 3. 求职申请主表 (业务生命周期)
CREATE TABLE IF NOT EXISTS applications (
    id VARCHAR(64) PRIMARY KEY,
    application_key VARCHAR(128) UNIQUE NOT NULL, -- candidate_id:canonical_job_id:cycle
    candidate_id VARCHAR(64) NOT NULL,
    canonical_job_id VARCHAR(64) NOT NULL,
    company_name VARCHAR(128) NOT NULL,
    job_title VARCHAR(128) NOT NULL,
    recruitment_cycle VARCHAR(64),
    status VARCHAR(32) NOT NULL, -- created, in_progress, ready_review, submitted, withdrawn, expired
    current_stage VARCHAR(64),
    assigned_variant_id VARCHAR(64),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- 4. 执行轮次表 (每次 CLI apply 生成一次 run)
CREATE TABLE IF NOT EXISTS application_runs (
    id VARCHAR(64) PRIMARY KEY,
    application_id VARCHAR(64) NOT NULL REFERENCES applications(id),
    run_index INT NOT NULL,
    status VARCHAR(32) NOT NULL, -- running, paused, completed, failed, cancelled
    profile_revision_id VARCHAR(64) NOT NULL REFERENCES profile_revisions(id),
    variant_revision_id VARCHAR(64) REFERENCES resume_variant_revisions(id),
    adapter_name VARCHAR(64) NOT NULL,
    adapter_version VARCHAR(32) NOT NULL,
    mapper_version VARCHAR(32) NOT NULL,
    config_hash VARCHAR(64) NOT NULL,
    llm_provider VARCHAR(32),
    llm_model VARCHAR(64),
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    end_reason VARCHAR(64),
    UNIQUE(application_id, run_index)
);

-- 5. 断点现场物化视图 (最新可恢复断点)
CREATE TABLE IF NOT EXISTS application_checkpoints (
    id VARCHAR(64) PRIMARY KEY,
    application_id VARCHAR(64) NOT NULL REFERENCES applications(id),
    run_id VARCHAR(64) NOT NULL,
    page_url TEXT NOT NULL,
    stage_key VARCHAR(64),
    snapshot_id VARCHAR(64),
    last_completed_field_sig VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL
);

-- 6. 审计事件流水 (Append-only)
CREATE TABLE IF NOT EXISTS application_events (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload_json TEXT NOT NULL, -- 经 AuditSanitizer 脱敏
    created_at DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run_time ON application_events(run_id, created_at);

-- 7. 表单快照表
CREATE TABLE IF NOT EXISTS form_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    page_url TEXT NOT NULL,
    stage_key VARCHAR(64),
    dom_fingerprint VARCHAR(64) NOT NULL,
    fields_meta_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

-- 8. 字段认知决策表 (Mapping 审计)
CREATE TABLE IF NOT EXISTS field_mappings (
    id VARCHAR(64) PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL REFERENCES form_snapshots(id),
    field_signature VARCHAR(64) NOT NULL,
    profile_path VARCHAR(128),
    method VARCHAR(32) NOT NULL, -- memory, exact_rule, semantic, llm, user_override
    confidence REAL NOT NULL,
    disclosure_allowed BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL
);

-- 9. 页面操作执行与回读审计 (Action 审计)
CREATE TABLE IF NOT EXISTS field_actions (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    snapshot_id VARCHAR(64) NOT NULL REFERENCES form_snapshots(id),
    field_signature VARCHAR(64) NOT NULL,
    mapping_id VARCHAR(64) REFERENCES field_mappings(id),
    action_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL, -- success, conflict, failed, skipped
    expected_hash VARCHAR(64),
    observed_hash VARCHAR(64),
    value_preview VARCHAR(64),
    error_code VARCHAR(32),
    duration_ms INT NOT NULL,
    created_at DATETIME NOT NULL
);

-- 10. 作用域约束的纠错记忆表 (越投越聪明)
CREATE TABLE IF NOT EXISTS correction_memories (
    id VARCHAR(64) PRIMARY KEY,
    provider VARCHAR(64) NOT NULL,
    tenant_hint VARCHAR(64),
    section_signature VARCHAR(64),
    options_signature VARCHAR(64),
    normalized_label VARCHAR(64) NOT NULL,
    field_type VARCHAR(32) NOT NULL,
    corrected_semantic_path VARCHAR(128) NOT NULL,
    confidence REAL NOT NULL,
    hit_count INT NOT NULL DEFAULT 1,
    last_used_at DATETIME NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_corr_lookup 
ON correction_memories(provider, normalized_label, section_signature);
"""
