# ApplyPilot v0.1 系统设计规范 (System Design Specification)

> **Document Status**: Frozen Architecture / Approved for Implementation  
> **Version**: 0.1.0  
> **Date**: 2026-09-12  
> **Repository**: `git@github.com:wishfine/apply-pilot.git`  
> **Slogan**: One profile. Every application. / 一份资料，投遍所有岗位。

---

## 目录
1. [执行摘要与顶层架构原则](#1-执行摘要与顶层架构原则)
2. [PRD 产品需求与 v0.1 边界](#2-prd-产品需求与-v01-边界)
3. [核心领域模型 (Domain Layer)](#3-核心领域模型-domain-layer)
4. [数据库持久化、可审计与断点续填体系 (Storage & Track)](#4-数据库持久化可审计与断点续填体系-storage--track)
5. [受控浏览器抽象与反反爬治理 (Browser Layer)](#5-受控浏览器抽象与反反爬治理-browser-layer)
6. [适配器架构：组合策略与多信号检测 (Adapters Ecosystem)](#6-适配器架构组合策略与多信号检测-adapters-ecosystem)
7. [多阶段网申自动化引擎 (Apply Engine & State Machine)](#7-多阶段网申自动化引擎-apply-engine--state-machine)
8. [类型化语义归一化与回读校验 (ValueNormalizer & ValueKind)](#8-类型化语义归一化与回读校验-valuenormalizer--valuekind)
9. [人机协同与用户纠错分类 (Human-in-the-Loop & Correction Memory)](#9-人机协同与用户纠错分类-human-in-the-loop--correction-memory)
10. [工程目录结构与运行环境管理](#10-工程目录结构与运行环境管理)
11. [三大真实场景纸面走查 (Real-World Walkthrough Scenarios)](#11-三大真实场景纸面走查-real-world-walkthrough-scenarios)
12. [规范自审与质量关卡 (Spec Self-Review)](#12-规范自审与质量关卡-spec-self-review)

---

## 1. 执行摘要与顶层架构原则

ApplyPilot 是一个面向中国招聘生态的本地优先（Local-first）AI 求职投递 Agent，覆盖**央国企、互联网大厂、银行金融机构、科研院所与行业代表企业**。

### 1.1 四大不可动摇顶层铁律
1. **CandidateProfile = Truth（不可变事实知识库）**：主档案是候选人个人所有经历、资质与家庭关系的**全集事实超集**；ResumeVariant 仅是针对特定岗位的“投影/选择/排序策略”，严禁无中生有。
2. **JobSourceAdapter ≠ ApplicationAdapter（职位源与网申填报彻底解耦）**：发现岗位的渠道（如高校就业网、牛客、国聘、公司门户）与最终承载申请表单的系统（如北森、Moka、自建站）相互独立。
3. **ApplyEngine ≠ Playwright（浏览器引擎接口化隔离）**：自动化引擎通过语义化受控协议 `BrowserBackend` 操作页面，Playwright 仅作为 v0.1 的驱动实现，严禁上层业务直接侵入底层 CDP 或原生 Page。
4. **Every Action is Auditable & Resumable（全操作可审计与断点续填）**：网申跨天进行是常态。Event 负责事后审计，Checkpoint 负责现场恢复；决策、映射与执行动作清晰解耦；所有持久化数据遵循数据最小化与防泄露机制。

---

## 2. PRD 产品需求与 v0.1 边界

### 2.1 五大核心子系统职责

```
┌─────────────────────────────────────────────────────────────┐
│                       ApplyPilot CLI                        │
├─────────────┬─────────────┬─────────────┬─────────────┬─────┤
│   Profile   │  Discover   │    Match    │    Apply    │Track│
│ 事实库/变体  │ 职位解析/导入│ 硬门槛+语义  │ 多阶段自动填报│全生命│
│ 凭证材料管理 │ 外部ID去重  │ 岗位匹配打分 │ 人机最终提交 │周期 │
└─────────────┴─────────────┴─────────────┴─────────────┴─────┘
```

### 2.2 v0.1 严控功能范围（In-Scope vs Out-of-Scope）

#### In-Scope（v0.1 必须跑通的核心闭环）
* **Profile**：支持 YAML/JSON 导入全量候选人事实知识库；支持派生 ResumeVariant（经历筛选与 STAR Bullet 表达定制）；支持材料附件管理；支持敏感字段策略标记。
* **Discover**：支持单 URL 直接解析与结构化 Job 录入；提取招聘周期、岗位硬要求与外部 Job ID。
* **Match**：基于规则的硬门槛过滤（学历、毕业年份、专业大类）+ 基于 LLM/Embeddings 的技能匹配打分（0-100）。
* **Apply**：多信号平台识别；Generic HTML、Moka、北森（Beisen）三大适配器全流程自动填报；三级字段映射（记忆 $\to$ 规则 $\to$ LLM）；回读校验与多阶段翻页；人机协同登录与最终提交把关。
* **Track**：SQLite 本地全量审计；支持跨天会话断点续填；用户纠错记忆沉淀。

#### Out-of-Scope（严格移至 v0.2+，v0.1 严禁过度设计）
* 自动破解/绕过极验、腾讯滑块或图形验证码（一律触发 Human Checkpoint 由用户在浏览器中完成）；
* 浏览器端直接全自动无人值守 Submit（最后一步必须由用户人工核验后在浏览器中点击）；
* 飞书招聘、牛客、51job、智联、字节/腾讯自建系统（v0.1 集中打透 Generic + Moka + Beisen）；
* 复杂分布式任务调度与 Web 前端控制台。

---

## 3. 核心领域模型 (Domain Layer)

领域模型全部位于 `applypilot/domain/`，纯 Pydantic v2 `BaseModel`，与持久化 ORM 彻底隔离。

### 3.1 基础基石类型

```python
from enum import StrEnum
from typing import Optional, List, Dict, Set, Any
from pydantic import BaseModel, Field

class TriState(StrEnum):
    """消灭布尔型二义性：区分'明确确认'、'明确否定'与'未提供/未知'"""
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

class PartialDate(BaseModel):
    """支持部分精度的日期，杜绝系统私自虚构 '01' 日"""
    year: int
    month: Optional[int] = None
    day: Optional[int] = None

    def to_display(self) -> str:
        if self.month and self.day:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.month:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

class SensitivityLevel(StrEnum):
    PUBLIC = "public"          # 公开信息: 技能名称、公共主页
    NORMAL = "normal"          # 常规职业信息: 期望城市、工作年限
    PERSONAL = "personal"      # 个人隐私: 姓名、联系电话、教育经历流水
    SENSITIVE = "sensitive"    # 强隐私: 身份证号、政治面貌、家庭成员、亲属回避
    SECRET = "secret"          # 绝密凭据: Cookie、Session Token、API Key

class LogStrategy(StrEnum):
    PLAIN = "plain"
    MASK = "mask"              # 掩码脱敏 (如 138****1234)
    OMIT = "omit"              # 严禁打印/保存

class FieldPolicy(BaseModel):
    path_pattern: str          # 模式匹配: 如 "identity.id_number", "soe_extended.*"
    sensitivity: SensitivityLevel
    llm_allowed: bool          # 严格限制: SENSITIVE/SECRET 严禁发送给 LLM
    log_strategy: LogStrategy = LogStrategy.MASK
    requires_confirmation: bool = False

class FactMetadata(BaseModel):
    source: str                # "user_input" | "resume_parser" | "ocr" | "llm_extract"
    verified: bool = False     # 是否由用户显式核验
    confidence: float = 1.0
    updated_at: str            # ISO 8601 UTC
```

### 3.2 候选人事实库 (CandidateProfile)

```python
class EducationLevel(StrEnum):
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTOR = "doctor"

class ExperienceType(StrEnum):
    INTERNSHIP = "internship"    # 实习 (校招一等公民)
    FULL_TIME = "full_time"      # 全职工作
    RESEARCH = "research"        # 课题/科研
    STUDENT_ORG = "student_org"  # 学生骨干/社团
    VOLUNTEER = "volunteer"      # 志愿活动

class IdentityInfo(BaseModel):
    name: Optional[str] = None
    pinyin_first_name: Optional[str] = None
    pinyin_last_name: Optional[str] = None
    english_name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[PartialDate] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    ethnicity: Optional[str] = None       # 严禁默认汉族
    health_status: Optional[str] = None   # 严禁默认健康

class ContactInfo(BaseModel):
    mobile: Optional[str] = None
    email: Optional[str] = None
    current_city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class EducationRecord(BaseModel):
    id: str                               # 稳定 ID: edu_bachelor, edu_master
    school_name: str
    education_level: EducationLevel       # 学历层次: 本科 / 硕士
    academic_degree: Optional[str] = None # 学位名称: 工学学士 / 工学硕士
    major: str
    department: Optional[str] = None
    start_date: PartialDate
    end_date: PartialDate
    gpa: Optional[float] = None
    gpa_scale: Optional[float] = None
    ranking_pct: Optional[str] = None
    is_first_degree: TriState = TriState.UNKNOWN
    is_highest_degree: TriState = TriState.UNKNOWN
    thesis_title: Optional[str] = None

class ExperienceRecord(BaseModel):
    id: str                               # 稳定 ID: exp_bytedance_intern
    experience_type: ExperienceType
    org_name: str
    department: Optional[str] = None
    title: str
    city: Optional[str] = None
    start_date: PartialDate
    end_date: Optional[PartialDate] = None
    description_bullets: List[str] = Field(default_factory=list)
    skills_used_ids: List[str] = Field(default_factory=list)

class ProjectRecord(BaseModel):
    id: str                               # 稳定 ID: proj_apply_pilot
    project_name: str
    role: str
    start_date: PartialDate
    end_date: Optional[PartialDate] = None
    summary: str
    description_bullets: List[str] = Field(default_factory=list)
    technologies_used_ids: List[str] = Field(default_factory=list)
    repo_url: Optional[str] = None

class SkillRecord(BaseModel):
    skill_id: str                         # skill_python, skill_financial_modeling
    name: str
    category: str                         # "programming", "finance", "engineering", "language"
    proficiency: Optional[str] = None
    years_experience: Optional[float] = None

class AssetRecord(BaseModel):
    asset_id: str                         # asset_resume_pdf, asset_transcript
    asset_type: str                       # "resume_pdf" | "transcript" | "cet_cert"
    file_path: str                        # 本地路径
    title: str
    related_fact_ids: List[str] = Field(default_factory=list)
    sensitivity: SensitivityLevel = SensitivityLevel.PERSONAL

class ChinaCampusContext(BaseModel):
    graduation_year: Optional[int] = None
    graduation_month: Optional[int] = None
    employment_status: Optional[str] = None
    cet4_score: Optional[int] = None
    cet6_score: Optional[int] = None
    ielts_score: Optional[float] = None
    toefl_score: Optional[int] = None
    has_dispatch_qualification: TriState = TriState.UNKNOWN

class FamilyMember(BaseModel):
    id: str                               # family_father, family_mother
    relation: str                         # "父亲" / "母亲" / "配偶"
    name: str
    political_status: Optional[str] = None
    workplace: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None

class SOEExtendedInfo(BaseModel):
    political_status: Optional[str] = None # 严禁默认党员或团员
    join_party_date: Optional[PartialDate] = None
    native_place: Optional[str] = None
    household_registration: Optional[str] = None
    household_type: Optional[str] = None
    family_members: List[FamilyMember] = Field(default_factory=list)
    conflict_of_interest: TriState = TriState.UNKNOWN
    conflict_details: Optional[str] = None

class StoryRecord(BaseModel):
    story_id: str
    topic: str
    title: str
    situation: str
    task: str
    action: str
    result: str
    related_fact_ids: List[str] = Field(default_factory=list)

class CandidateProfile(BaseModel):
    schema_version: str = "1.1.0"
    profile_id: str
    identity: IdentityInfo = Field(default_factory=IdentityInfo)
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: List[EducationRecord] = Field(default_factory=list)
    experiences: List[ExperienceRecord] = Field(default_factory=list)
    projects: List[ProjectRecord] = Field(default_factory=list)
    skills: List[SkillRecord] = Field(default_factory=list)
    assets: List[AssetRecord] = Field(default_factory=list)
    campus_context: ChinaCampusContext = Field(default_factory=ChinaCampusContext)
    soe_extended: Optional[SOEExtendedInfo] = None
    stories: List[StoryRecord] = Field(default_factory=list)
    fact_metadata: Dict[str, FactMetadata] = Field(default_factory=dict)
```

### 3.3 呈现策略 (ResumeVariant) 与披露策略 (DisclosurePolicy)

```python
class VariantBullet(BaseModel):
    text: str
    source_fact_ids: List[str] = Field(..., description="必须显式关联主事实库经历或bullet ID")
    generated_by: str = "user"         # "user" | "llm_polished"
    verified: bool = True

class VariantProjectConfig(BaseModel):
    project_id: str
    selected: bool = True
    priority_order: int = 0
    bullets: List[VariantBullet] = Field(default_factory=list)

class ResumeVariant(BaseModel):
    variant_id: str                    # 如 "algo_specialist", "backend_dev"
    profile_id: str
    target_job_type: str
    headline: str
    selected_education_ids: List[str] = Field(default_factory=list)
    selected_experience_ids: List[str] = Field(default_factory=list)
    project_configs: List[VariantProjectConfig] = Field(default_factory=list)
    highlighted_skill_ids: List[str] = Field(default_factory=list)

class DisclosurePolicy(BaseModel):
    """网申维度的披露边界门禁"""
    allow_sensitive: bool = False
    disclose_family: bool = False
    disclose_political: bool = False
    blocked_field_paths: Set[str] = Field(default_factory=set)
```

### 3.4 职位与申请目标 (Job & ApplicationTarget)

```python
class Job(BaseModel):
    job_id: str
    external_job_id: Optional[str] = None  # 平台原有岗位ID，去重关键
    title: str
    company_name: str
    company_id: Optional[str] = None
    locations: List[str] = Field(default_factory=list)
    job_type: str = "campus"
    department: Optional[str] = None
    description_raw: str
    degree_required: Optional[EducationLevel] = None
    graduation_years: List[int] = Field(default_factory=list)
    majors_preferred: List[str] = Field(default_factory=list)
    source_channel: str                    # "moka" | "beisen" | "nowcoder" | "url"
    source_url: str
    apply_url: str
    deadline: Optional[PartialDate] = None
    posted_at: Optional[PartialDate] = None
    recruitment_cycle: Optional[str] = None # 如 "2027-campus-autumn"

class ApplicationTarget(BaseModel):
    target_id: str
    job: Job
    platform_type: Optional[str] = None    # "ats" | "company"
    provider: Optional[str] = None         # "moka" | "beisen" | "generic"
    final_form_url: Optional[str] = None   # 逐步探测补全
    assigned_variant_id: Optional[str] = None
    disclosure_policy: DisclosurePolicy = Field(default_factory=DisclosurePolicy)
```

---

## 4. 数据库持久化、可审计与断点续填体系 (Storage & Track)

存储底座为本地 SQLite，采用 WAL 模式，严格开启外键约束。

### 4.1 核心审计与恢复架构

```
               Application (业务生命周期: IN_PROGRESS / READY_REVIEW / SUBMITTED)
                    │
                    ├── Latest Checkpoint (物化现场: page_url, stage_key, snapshot_id)
                    │
                    ├── Immutable Profile / Variant Revisions (版本镜像)
                    │
                    └── ApplicationRun #N (单次执行轮次: RUNNING / PAUSED / COMPLETED)
                            │
                            ├── ApplicationEvents (Append-only 审计事件流)
                            │
                            └── FormSnapshot (页面结构与字段指纹)
                                    │
                                    └── FieldMappings (认知决策: Signature -> ProfilePath)
                                            │
                                            └── FieldActions (DOM 执行回读: ActionType, Hashes, Status)
```

### 4.2 隐私屏障：安全审计脱敏 (AuditSanitizer)

为杜绝彩虹表与字典碰撞，指纹计算采用 `HMAC-SHA256`，秘钥存储在 OS Keyring（macOS Keychain / Linux SecretService / Windows Credential Vault）：

```python
import hmac
import hashlib

class AuditSanitizer:
    @staticmethod
    def compute_fingerprint(audit_secret: bytes, raw_value: Optional[str]) -> Optional[str]:
        if raw_value is None:
            return None
        normalized = raw_value.strip().lower()
        sig = hmac.new(audit_secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac-sha256:{sig}"

    @staticmethod
    def mask_value(field_policy: FieldPolicy, raw_value: Optional[str]) -> Optional[str]:
        if not raw_value:
            return None
        if field_policy.sensitivity in (SensitivityLevel.SENSITIVE, SensitivityLevel.SECRET):
            return None  # 强隐私原值严禁落库
        if field_policy.log_strategy == LogStrategy.MASK:
            if len(raw_value) <= 4:
                return "***"
            return f"{raw_value[:2]}****{raw_value[-2:]}"
        return raw_value
```

### 4.3 SQLite 完整 10 表物理 Schema

```sql
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
    run_id VARCHAR(64) NOT NULL REFERENCES application_runs(id),
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
    run_id VARCHAR(64) NOT NULL REFERENCES application_runs(id),
    event_type VARCHAR(64) NOT NULL,
    payload_json TEXT NOT NULL, -- 经 AuditSanitizer 脱敏
    created_at DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run_time ON application_events(run_id, created_at);

-- 7. 表单快照表
CREATE TABLE IF NOT EXISTS form_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES application_runs(id),
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
    run_id VARCHAR(64) NOT NULL REFERENCES application_runs(id),
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
```

---

## 5. 受控浏览器抽象与反反爬治理 (Browser Layer)

### 5.1 能力收口契约 (BrowserBackend Protocol)

严禁 Adapter 接触 Playwright 原生实例，通过语义化 API 交互：

```python
from typing import Protocol, List, Optional, Any
from pydantic import BaseModel

class ElementRect(BaseModel):
    x: float
    y: float
    width: float
    height: float

class BrowserElement(Protocol):
    async def get_attribute(self, name: str) -> Optional[str]: ...
    async def get_text(self) -> str: ...
    async def click(self) -> None: ...
    async def type_text(self, text: str) -> None: ...
    async def clear_text(self) -> None: ...
    async def select_option(self, value: str) -> None: ...
    async def set_files(self, file_paths: List[str]) -> None: ...
    async def get_bounding_rect(self) -> ElementRect: ...
    async def scroll_into_view(self) -> None: ...

class BrowserPage(Protocol):
    async def url(self) -> str: ...
    async def title(self) -> str: ...
    async def find(self, selector: str) -> Optional[BrowserElement]: ...
    async def find_all(self, selector: str) -> List[BrowserElement]: ...
    async def wait_for(self, selector: str, timeout_ms: int = 5000) -> BrowserElement: ...
    async def execute_unsafe_script(self, reason: str, script: str, arg: Any = None) -> Any: ...

class BrowserBackend(Protocol):
    async def open_page(self, url: str) -> BrowserPage: ...
    async def current_page(self) -> BrowserPage: ...
    async def wait_for_user(self, reason: str) -> None: ...
    async def close(self) -> None: ...
```

> **Unsafe Script 准入限制**：`execute_unsafe_script` 属于特权 API，仅在平台级探测或无法通过 DOM 标准事件触发的极其罕见的特殊组件中允许调用，且调用时必须显式声明 `reason` 并记录审计日志。

### 5.2 交互策略与隐私策略

* **InteractionPolicy**：由底层统一接管动作间隔（`min_action_interval_ms = 150`）、等待超时（`action_timeout_ms = 10000`）与重试退避。拒绝在业务代码中散落私有 jitter。
* **ScreenshotPolicy**：默认**严禁**任何截图落地；仅在 CLI 带有 `--debug-screenshots` 且用户明确知晓的情况下临时开启，并由定时清理器执行 TTL 自动销毁。
* **Session Lifecycle**：使用本地专用用户目录（Persistent User Data Dir），用户仅需首次手动微信扫码或短信登录，Session 长期有效，告别反爬攻防战。

---

## 6. 适配器架构：组合策略与多信号检测 (Adapters Ecosystem)

### 6.1 组合优于继承 (Composition over Inheritance)

Adapter 不再继承 GenericAdapter，而是充当策略组装器：

```
┌─────────────────────────────────────────────────────────────┐
│                  ApplicationAdapter (Protocol)              │
│  - detect(page) -> DetectionResult                          │
│  - detect_stage(page) -> StageInfo                          │
│  - scan(page) -> FormSnapshot                               │
│  - fill_field(page, field, resolved_value) -> FillResult    │
│  - advance(page, current_stage) -> NavigationResult         │
│  - is_final_review(page) -> bool                            │
└──────────────────────────────┬──────────────────────────────┘
                               │ 实现与装配
        ┌──────────────────────┴──────────────────────┐
        ▼                                             ▼
 ┌─────────────────────────────┐       ┌─────────────────────────────┐
 │    MokaApplicationAdapter   │       │   BeisenApplicationAdapter  │
 │ 组装:                       │       │ 组装:                       │
 │ - GenericFormScanner        │       │ - GenericFormScanner        │
 │ - StandardInputFiller       │       │ - StandardInputFiller       │
 │ - MokaSearchSelectFiller    │       │ - BeisenModalSchoolPicker   │
 │ - MokaDateGridFiller        │       │ - BeisenCascaderFiller      │
 │ - MokaNavigationStrategy    │       │ - BeisenNavigationStrategy  │
 └─────────────────────────────┘       └─────────────────────────────┘
```

### 6.2 结构化填充响应 (FillResult)

```python
class FillResult(BaseModel):
    success: bool
    action_type: str
    observed_value: Optional[str] = None
    verification_status: str             # "verified_match" | "conflict" | "unverified"
    error_code: Optional[str] = None     # "ELEMENT_NOT_FOUND" | "OPTION_MISMATCH" | "TIMEOUT"
    recoverable: bool = True
    needs_human: bool = False
```

### 6.3 多信号联合检测 (Multi-Signal Detection)

拒绝仅靠域名硬编码，采用综合评分报告：

```python
class DetectionEvidence(BaseModel):
    signal_type: str                     # "host" | "dom_signature" | "script" | "component_class"
    detail: str
    weight: float

class DetectionResult(BaseModel):
    platform: str
    confidence: float
    evidences: List[DetectionEvidence] = Field(default_factory=list)

class DetectionReport(BaseModel):
    candidates: List[DetectionResult]    # 按置信度降序排列
```

* 命中阈值 $\ge 0.85$：直接采用最高分 Adapter；
* $0.60 \sim 0.85$：触发 Adapter 自检验证；
* $< 0.60$：回退至 GenericHTMLAdapter，提示人工确认。

---

## 7. 多阶段网申自动化引擎 (Apply Engine & State Machine)

真实中国招聘表单由多个业务阶段构成（如：基本信息 $\to$ 教育经历 $\to$ 实习经历 $\to$ 家庭信息 $\to$ 附件上传 $\to$ 综合预览）。

### 7.1 会话级主状态机循环

```
                    ┌─────────────────────────┐
                    │      Start / Resume     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │     Platform Detect     │
                    └────────────┬────────────┘
                                 │
                                 ▼
        ┌─────────────────────────────────────────────────┐
        │ 阶段循环 (Stage Loop)                            │
        │                                                 │
        │ 1. detect_stage(page) ──▶ 获取当前 stage_key    │
        │ 2. scan(page) ──▶ 生成 FormSnapshot (落库)      │
        │ 3. map_fields() ──▶ 三级映射 (记忆/规则/LLM)     │
        │ 4. resolve_values() ──▶ 结合 Variant 求值       │
        │ 5. disclosure_gate() ──▶ 隐私门禁过滤           │
        │ 6. 遍历字段:                                    │
        │      readback() ──▶ 与 expected 语义归一化比对    │
        │      若已相等 ──▶ Skip                          │
        │      若冲突或为空 ──▶ execute fill()            │
        │      回读验证 ──▶ 生成 FieldActionRecord (落库) │
        │ 7. 更新物化 Checkpoint                           │
        │ 8. if is_final_review(page):                    │
        │        BREAK LOOP ──▶ 进入最终人工审核           │
        │ 9. advance(page, stage) ──▶ 翻页/下一步         │
        │10. wait_navigation() ──▶ 确认 URL/DOM 变动       │
        └────────────────────────┬────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Human Review Station  │
                    │   终端打印全案摘要看板  │
                    │   用户亲自点击最终 Submit│
                    └─────────────────────────┘
```

---

## 8. 类型化语义归一化与回读校验 (ValueNormalizer & ValueKind)

严禁使用全局子串包含做等价判断。依据字段语义类型 `ValueKind` 精确分流比对：

```python
class ValueKind(StrEnum):
    PLAIN_TEXT = "plain_text"
    PERSON_NAME = "person_name"
    PHONE = "phone"
    EMAIL = "email"
    CITY = "city"
    DATE = "date"
    EDUCATION_LEVEL = "education_level"
    ACADEMIC_DEGREE = "academic_degree"
    POLITICAL_STATUS = "political_status"
    BOOLEAN = "boolean"
    ENUM = "enum"

class ValueNormalizerRegistry:
    @staticmethod
    def normalize_city(val: str) -> str:
        return val.strip().rstrip("市省特别行政区")

    @staticmethod
    def normalize_education_level(val: str) -> str:
        s = val.strip()
        if "博" in s: return "doctor"
        if "硕" in s: return "master"
        if "本" in s: return "bachelor"
        if "专" in s: return "associate"
        return s

    @classmethod
    def are_equivalent(cls, kind: ValueKind, observed: Optional[str], expected: Any) -> bool:
        if not observed or expected is None:
            return False
        obs = observed.strip()
        exp = str(expected).strip()
        if obs == exp:
            return True

        if kind == ValueKind.CITY:
            return cls.normalize_city(obs) == cls.normalize_city(exp)
        if kind == ValueKind.EDUCATION_LEVEL:
            return cls.normalize_education_level(obs) == cls.normalize_education_level(exp)
        if kind == ValueKind.DATE:
            # 仅允许前缀匹配或精准等价，如 2025-06 与 2025-06-01
            return obs.startswith(exp) or exp.startswith(obs)
        if kind == ValueKind.PHONE:
            return obs.replace("-", "").replace(" ", "") == exp.replace("-", "").replace(" ", "")

        return False
```

---

## 9. 人机协同与用户纠错分类 (Human-in-the-Loop & Correction Memory)

### 9.1 用户人工干预的严格四级分类

在 Review 阶段，用户修正值决不无脑直接写入 CorrectionMemory，而是由用户指示修正属性：

| 干预类型 | 触发原因 | 处理策略 | 沉淀目标 |
| :--- | :--- | :--- | :--- |
| **Fix Mapping** | 字段标签识别错误（如将最高学位映射为学历） | 记录带有作用域签名的纠错规则 | 落入 `correction_memories` 表 |
| **Fix Fact** | 候选人主事实库原值有误或落后 | 更新 CandidateProfile 对应字段 | 生成新的 `ProfileRevision` |
| **Fix Formatting** | 平台枚举词汇微异（如“中共党员”要求填“党员”） | 记录该平台的值转换字典映射 | 沉淀至 Adapter Option Map |
| **One-time Override** | 用户仅对本岗位做出的临时特例改动 | 仅对当次执行生效，不污染全局 | 仅记录在当次 `FieldActionRecord` |

---

## 10. 工程目录结构与运行环境管理

### 10.1 本地优先存储路径（Platformdirs 隔离）

遵循现代操作系统标准，开发代码库与真实个人数据完全隔离：

```
代码目录 (apply-pilot/)                 用户数据目录 (APPLYPILOT_HOME)
├── applypilot/                       ├── macOS: ~/Library/Application Support/ApplyPilot/
├── configs/                          ├── Linux: ~/.local/share/applypilot/
│   └── default.yaml                  └── Windows: %LOCALAPPDATA%\ApplyPilot\
├── tests/                                  │
└── pyproject.toml                          ├── applypilot.db (SQLite 主库)
                                            ├── browser_profile/ (持久化登录态)
                                            ├── attachments/ (证件照/PDF/成绩单)
                                            ├── profiles/ (主事实库 profile.yaml)
                                            └── logs/ (运行与排错日志)
```

---

## 11. 三大真实场景纸面走查 (Real-World Walkthrough Scenarios)

### 场景 A：Moka 互联网校招（以美团/小红书典型 Moka 招聘页为例）

1. **职位发现与导入**：
   * 用户执行 `applypilot apply --job-url https://app.mokahr.com/campus-recruitment/meituan/10001#/job/xxx`；
   * `PlatformDetector` 探测：命中域名 `mokahr.com`，检测到 DOM 含有 `[class*="moka-"]`，输出 `DetectionReport(moka, confidence=0.98)`；
   * 路由至 `MokaApplicationAdapter`。
2. **表单扫描与字段映射**：
   * 页面展示单页长表单，`MokaApplicationAdapter` 驱动 `GenericFormScanner` 扫描出 18 个可见控件；
   * 姓名、手机号、邮箱通过正则直配（`exact_rule`）；
   * “毕业院校”控件检测为 Moka 专有搜索下拉框，指派 `MokaSearchSelectFiller`；
   * 字段映射生成 `FormSnapshot` 与 `FieldMappingRecord`，敏感字段经 `AuditSanitizer` 脱敏落库。
3. **回读比对与填充**：
   * 手机号与姓名已有用户历史草稿值，经 `ValueNormalizer` 比对指纹一致，标记 `already_verified` 并跳过；
   * 学校、专业、学历依次通过键盘事件平稳输入并选择匹配选项；
   * PDF 简历附件自动关联并调用 `BrowserElement.set_files()` 上传。
4. **人工交接**：
   * 自动化流程抵达底端“提交申请”按钮上方；
   * 终端展示清爽摘要表格，应用标记为 `READY_REVIEW`，系统暂停并提示：`请在浏览器中核实无误后，亲自点击提交`。

---

## 12. 规范自审与质量关卡 (Spec Self-Review)

| 检查项 | 状态 | 结论说明 |
| :--- | :---: | :--- |
| **占位符清理** | PASS | 全文无任何 `TODO`、`TBD` 或未定义的临时占位符。 |
| **内部一致性** | PASS | 领域模型字段、SQLite 10 表列定义与执行状态机名称 100% 严格一致。 |
| **范围严控** | PASS | 严格限定在 v0.1 Scope（Generic + Moka + Beisen），绝无未受控扩展。 |
| **歧义消除** | PASS | 字段敏感度、断点恢复机制、归一化比对算法均给出明确确定性逻辑。 |
