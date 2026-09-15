# ApplyPilot 简历与网页字段匹配 API 设计

## 目标

当前插件把 PDF 解析、`profile.yaml` 读取、网页字段识别和字段映射分散在两个运行时里。网页使用自定义组件、重复经历和动态分区时，单靠浏览器端固定别名容易出现“扫描到了字段但没有可填写项”。本方案引入一个版本化的 API 协议，将简历事实、候选人档案和当前页面字段统一转换为带证据的填写计划。

API 只负责理解和规划，不直接操作网页，也不点击保存、下一步或提交。插件继续掌握页面权限、敏感字段授权和最终写入。默认部署为本机 `127.0.0.1` 服务；远程模型服务只是可选的解析后端，不把个人资料默认发送到第三方。

## 总体架构

```text
PDF/DOCX ──本地提取──▶ Resume text
                         │
profile.yaml ──本地解析─▶ CandidateProfile ──┐
                                             │
当前页面 ──插件扫描──▶ PageSnapshot ──────────┼──▶ Mapping API
                                             │       │
                                             │       ├── deterministic rules
                                             │       ├── section/record resolver
                                             │       └── optional LLM fallback
                                             │              │
                                             └──────◀────── FillPlan
                                                      │
                                         插件复核、授权、写入、回读
```

现有仓库继续作为单一仓库：Python 的 `CandidateProfile` 和 API 合约放在核心包，FastAPI 服务放在 `apps/api`，浏览器插件放在 `apps/extension`。这样不会出现 CLI、API、插件各自维护一套字段名和档案版本的问题。

## API 边界

### `POST /v1/profiles/parse`

用于从简历文件或已提取文本生成结构化档案草稿。解析结果必须包含来源证据，缺失字段保持 `null`，不能用姓名、身份证号或上下文推测英文名、政治面貌、奖项等级等事实。

请求使用 `multipart/form-data`，二选一提供 `file` 或 `text`，并可附带已有 `profile` 作为合并基线：

```json
{
  "schema_version": "1.1.0",
  "mode": "merge",
  "base_profile": { "profile_id": "cand_zhang_yonglin_2026", "identity": {}, "experiences": [] },
  "source_name": "resume-photo.pdf",
  "source_sha256": "sha256:..."
}
```

响应返回 `profile_draft`、`facts` 和 `warnings`。每个事实至少包括 JSON Pointer、原文证据、页码或文本偏移、置信度和是否需要人工核验：

```json
{
  "request_id": "req_01J...",
  "profile_draft": {
    "profile_id": "cand_zhang_yonglin_2026",
    "education": [],
    "experiences": [],
    "projects": [],
    "awards": [],
    "publications": []
  },
  "facts": [
    {
      "path": "/experiences/0/org_name",
      "value": "新东方教育科技集团",
      "source": { "document": "resume-photo.pdf", "page": 1, "quote": "新东方教育科技集团" },
      "confidence": 0.99,
      "needs_review": false
    }
  ],
  "warnings": ["论文标题未在简历中出现，保留为空"]
}
```

`base_profile` 的已核实值优先于简历新抽取值；两者冲突时不能静默覆盖，返回 `conflicts[]`，交给用户选择。解析接口不保存原始文件，服务端默认只在请求生命周期内处理。

### `POST /v1/profiles/reconcile`

用于把用户现有 YAML 和一次新的简历解析结果合并。合并规则固定为：用户已核实档案 > 用户本次明确输入 > 有来源证据的简历事实 > 无证据推断（禁止）。数组记录按稳定 `id`、组织名 + 起止时间和项目名建立候选关联；无法唯一关联时新增 `conflicts[]`，不覆盖原记录。

### `POST /v1/forms/plan`

这是插件在扫描当前页后调用的主要接口。请求中的页面快照只包含控件结构和当前值，不上传 HTML、Cookie、账号密码或验证码：

```json
{
  "protocol_version": "1.0",
  "request_id": "req_01J...",
  "profile": { "profile_id": "cand_zhang_yonglin_2026", "identity": {}, "education": [], "experiences": [], "projects": [], "awards": [], "publications": [] },
  "page": {
    "url_origin": "https://iflytek.zhiye.com",
    "title": "填写简历",
    "platform_hint": "generic",
    "active_section": "个人信息",
    "sections": [{ "id": "s_personal", "label": "个人信息", "active": true }, { "id": "s_intern", "label": "实习经历", "active": false }],
    "fields": [
      {
        "field_ref": "ap-17",
        "label": "单位名称",
        "name": "workCompany",
        "section": "实习经历",
        "record_group": "experience-row-2",
        "kind": "text",
        "type": "text",
        "required": true,
        "value": "",
        "options": []
      }
    ]
  },
  "policy": {
    "fill_required_only": true,
    "allow_sensitive_paths": ["identity.id_number", "soe_extended.native_place"],
    "allow_remote_processing": false
  }
}
```

响应是可重放、可审计的计划。API 必须返回每个字段，即使决策是 `skip` 或 `review`：

```json
{
  "request_id": "req_01J...",
  "mapping_version": "rules-2026-09-15.1",
  "profile_hash": "sha256:...",
  "plan": [
    {
      "field_ref": "ap-17",
      "decision": "fill",
      "required": true,
      "value": "高德地图（大云图业务部）",
      "profile_path": "/experiences/1/org_name",
      "record_id": "exp_amap_traffic_algorithm_intern",
      "confidence": 0.99,
      "method": "section_rule",
      "evidence": [{ "path": "/experiences/1/org_name", "reason": "实习经历第 2 个空白记录槽" }]
    }
  ],
  "summary": { "fields": 38, "fill": 5, "review": 20, "optional_skipped": 13, "existing_skipped": 0 },
  "warnings": [],
  "expires_at": "2026-09-15T12:30:00Z"
}
```

`decision` 只允许：

- `fill`：必填、为空、来源路径唯一、值通过类型和选项校验。
- `skip`：已有值，或选填字段按策略保持为空。
- `review`：缺资料、多个候选、敏感字段未授权、自定义控件、日期精度不足或记录无法唯一绑定。

API 不能返回一个没有 `profile_path` 和证据的 `fill`。插件收到计划后仍需在本地检查 `field_ref`、DOM 是否变化、敏感路径授权和页面值回读；计划过期或页面签名变化时必须重新扫描。

### `POST /v1/forms/feedback`

只接收脱敏的人工修正，用于更新本地纠错记忆：字段签名、分区签名、控件类型、选项集合哈希、用户选择的 JSON Pointer 和规则版本。默认不上传身份证、手机号、简历原文或完整页面 HTML。纠错记忆必须按站点 origin 和分区作用域隔离，避免把“父亲姓名”规则带到候选人姓名字段。

## 解析与匹配策略

1. **本地确定性层**：解析 YAML、标准化标签、识别必填、识别分区和记录组，优先使用现有 `FieldMapper`/别名规则。该层不调用模型，API 不可用时插件可以直接回退。
2. **档案证据层**：PDF 文本先提取为事实候选，再按稳定记录 ID 写入教育、经历、项目、奖项、论文、证书和校园实践数组。NAS 录用和 TNSM 在投属于论文状态，不应放入奖项数组。
3. **上下文层**：使用字段自身的 `section` 和 `record_group` 解决“名称”“描述”“结束时间”等通用标签。页面只有重复字段而没有分组线索时，返回 `review`，不按数组顺序盲填。
4. **可选模型层**：只处理确定性层未命中的字段，输入限定为标签、分区、控件类型、选项和候选 profile 路径；模型只能从候选路径中选择，不能生成新事实。模型输出必须经过 JSON Schema、候选值集合和敏感策略二次校验。
5. **执行层**：插件按计划逐项写入并回读。任何网站脚本清空值、选项不存在、页面跳转或上传失败都产生 `review`，不会自动重试到另一个字段。

## 多段经历与项目记录

扫描器为每个可见控件附带 `record_group`。优先使用网站已有的重复项容器、`data-*` 标识、`fieldset` 或组件 key；没有稳定标识时用同一容器内的标签序列生成临时签名。API 先收集已有公司名/项目名对应的 `record_id`，再把剩余空白槽按时间倒序分配给档案记录。若空白槽数超过档案记录数，剩余字段为 `review`，不重复填写最近一段经历。

项目、奖项和论文也采用相同策略。通用标签必须依赖 `section`，例如“名称”只有在“论文/专著”分区才可映射到 `publications[*].title`；“证书名称”只能映射到证书数组。

## 必填识别

必填结论由页面扫描和 API 双重校验，顺序如下：

1. `required`、`aria-required=true`、表单组件的必填属性；
2. 标签或同一字段容器中的 `*`、`＊`、`必填` 和 `is-required` 类名；
3. 网站适配器提供的已验证规则；
4. 无法确定时视为选填，除非页面提交前的校验明确报告该字段为必填。

选填空字段在计划中返回 `skip`，不能因为 profile 有值就自动填写。选择控件、承诺题、验证码、账号密码和最终提交按钮始终进入 `review` 或被扫描器排除。

## 隐私与部署

- 默认服务监听 `127.0.0.1`，扩展通过随机启动令牌或一次性本地密钥认证；不监听 `0.0.0.0`。
- 默认不保留 PDF、YAML、页面快照或模型请求；日志只记录请求 ID、规则版本、计数和错误码。
- 身份证、手机号、邮箱、籍贯和家庭信息按路径授权。未授权时可以返回缺失原因，但不能把值放入远程请求。
- 如果用户开启远程解析，先显示发送范围和服务地址，使用 HTTPS；远程服务不得把简历内容用于训练或长期保存，具体由部署方策略保证。
- 每个请求使用 `Idempotency-Key`；相同 `profile_hash + page_signature + mapping_version` 可短期缓存计划，但缓存必须加密且自动过期。

## 兼容和迁移

现有插件继续保留本地 `mapFields` 作为 API 不可用时的回退。迁移顺序是：

1. 提取共享的 Pydantic/JSON Schema 合约和 TypeScript 类型；
2. 在 `apps/api` 实现本地 `/healthz`、`/v1/profiles/parse`、`/v1/profiles/reconcile` 和 `/v1/forms/plan`；
3. 将 Python 现有 `ResumeIngestionService` 与 `FieldMapper` 接入 API 的确定性层；
4. 插件增加 API 地址、启用远程处理开关和请求超时设置，默认关闭远程处理；
5. 通过本地合成页面验证个人、教育、实习、项目、奖项、论文和重复记录；
6. 真实招聘站点只做用户本地验收，不把带登录态的 HTML、Cookie 或截图提交到 CI。

完成标准是：同一份 profile 和页面快照在 API 与本地回退下产生相同的确定性结果；每个自动填写字段都有来源路径、记录 ID、必填结论和回读验证；API 不可用、模型超时、资料冲突或字段分组不明确时均可安全回退到人工处理。
