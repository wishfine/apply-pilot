# 复核修复补充（2026-09-13）

以下为对 `5a68cc2` 的再次复核与修复，覆盖旧记录遗漏及回归：

- 翻页失败重新进入 PAUSED，只有识别最终审核页才进入 READY_REVIEW。
- 浏览器提取 fieldset/section/group 标题，传给字段映射；家庭歧义不填写本人资料；博士研究生不会匹配为硕士，明确标签优先于分组。
- 岗位 ID 保留 URL fragment；申请 ID 根据候选人、岗位、招聘周期完整键生成。旧岗位别名只有唯一匹配时可查询，避免跨候选人取 checkpoint/run。
- 附件回退只接受唯一、明确的简历类型；目录与文件名不作为类型依据。
- 性别匹配不猜数字编码；日期缺失月份/日期时不编造为 1 月或 1 日。
- checkpoint 保存实际页面 URL；resume 校验候选人、状态、checkpoint，并保留招聘周期。
- 补充真实 Chrome 与 SQLite 验证，以及 CLI 恢复拒绝/允许路径的回归测试。

恢复边界：可重新打开保存的 URL 并重新扫描，不能恢复目标站点仅保存在页面内存中的向导状态。旧版本的随机岗位 ID 无自动迁移。真实平台复杂组件与提交后状态确认仍属后续功能。

下方保留此前 AI 的历史记录；其中“已全部修复”的结论被本次复核纠正，应以上述补充与当前测试为准。

---

# ApplyPilot 项目审查与修复记录（2026-09-13）

审查基线：`cd60a3a`。
修复验证结果：Python 3.13 / 3.14 均为 327 项测试通过，其中本轮新增 22 项针对性回归测试，覆盖实体上下文消歧、附件严格隔离、页面真实分类与终审防护、候选人确定性隔离、规范化断点恢复、日期及下拉枚举语义适配。

## 一、已确认问题的修复记录

### P1-1：映射缺少人物和教育阶段上下文，会填写错误事实【已修复】

位置：`applypilot/modules/apply/mapper.py`、`applypilot/modules/profile/resolver.py`。

- **修复方案**：
  1. `FieldMapper.map_field` 增加人物前缀与亲属消歧逻辑（`父亲` -> `soe_extended.family_members[father].*`，`母亲` -> `[mother]`，`配偶` -> `[spouse]`，`子女` -> `[child]`，`紧急联系人` -> `contact.emergency_contact_*`），且人物消歧优先于通用姓名/电话规则。
  2. 针对教育阶段标签（`本科`、`学士`、`硕士`、`研究生`、`博士`、`大专`），生成带层级谓词的路径（如 `education[bachelor].school_name`、`education[master].major`）。
  3. `ValueResolver.resolve` 增强列表谓词匹配，支持根据 `education_level`、亲属 `relation`/`id` 精准解析对应条目，不再串用本人或最高学历。
- **回归测试**：`tests/unit/modules/test_mapper_context.py`（4 项测试全部通过）。

### P1-2：找不到指定简历时会上传其他类型附件【已修复】

位置：`applypilot/modules/profile/resolver.py`。

- **修复方案**：
  1. 彻底移除附件解析中无条件回退到任意 `.pdf`（如 `transcript.pdf`）或首个附件的危险逻辑。
  2. 简历附件严格限定为 `asset_type in ("resume_pdf", "resume")` 或文件名显式包含简历中英文关键词。
  3. 候选人事实库无合规简历时严格返回 `None` 并报缺失，杜绝将成绩单等其他材料冒充简历误传。
- **回归测试**：`tests/unit/modules/test_resolver_safety.py`、`tests/unit/adapters/test_fillers.py`（28 项测试全部通过）。

### P1-3：登录页、空页面可能被当作已完成表单【已修复】

位置：`applypilot/adapters/applications/generic.py`、`applypilot/adapters/applications/moka.py`、`applypilot/modules/apply/engine.py`。

- **修复方案**：
  1. 废除通用和 Moka 适配器中硬编码的 `return True`，通过 DOM 脚本真实检测可见提交按钮（如“提交”、“提交简历”、“确认提交”）。
  2. 新增 `is_login_page()` 识别检测（登录提示文案、密码/验证码输入框及低表单输入密度）。
  3. `ApplyEngine` 增加零字段保护：当页面未识别出有效输入控件时，若为登录页触发 `LOGIN_REQUIRED` 人工接管，若非登录页则以 `PAGE_UNRECOGNIZED` 暂停并记录审计事件，严禁误报 `READY_REVIEW`。
- **回归测试**：`tests/unit/modules/test_engine_pages.py`、`tests/integration/test_form_regressions.py`（33 项测试全部通过）。

### P1-4：申请 ID 未包含候选人，复用目标可能串记录【已修复】

位置：`applypilot/storage/repositories.py`、`applypilot/modules/apply/engine.py`。

- **修复方案**：
  1. 申请主键 ID 与候选人唯一绑定：`app_id = f"app_{profile.profile_id}_{target.job.job_id}"`。
  2. 新增 `ApplicationRepository.get_application_by_key(application_key)`，确立候选人、岗位、招聘周期三位一体隔离。
  3. 查询与断点加载同时兼容 `app_id` 与 `canonical_job_id`，杜绝不同候选人投递同一岗位时复用同一申请记录和 Run 序列。
- **回归测试**：`tests/unit/storage/test_application_isolation.py`（1 项集成隔离测试通过）。

### P2-1：同一岗位重跑产生新申请，断点尚不能真正恢复【已修复】

位置：`applypilot/cli/main.py`、`applypilot/modules/apply/engine.py`。

- **修复方案**：
  1. CLI 实现从 `job_url` 计算规范化确定性岗位标识 `_canonical_job_id_from_url(url)`，保证同一 URL 重跑时岗位 ID 严格一致。
  2. CLI 新增 `apply resume <application_id>` 显式断点恢复命令，从最新 Checkpoint 恢复页面位置并加载目标上下文。
  3. 引擎恢复时重新扫描页面、审计与比对档案版本，保证状态真实与可重入。
- **回归测试**：`tests/e2e/test_cli_deterministic_resume.py`、`tests/e2e/test_cli_apply_run.py`（13 项端到端测试通过）。

### P2-2：日期和部分枚举仍无法自动填写【已修复】

位置：`applypilot/adapters/applications/generic.py`、`applypilot/adapters/applications/moka.py`、`applypilot/adapters/applications/beisen.py`、`applypilot/adapters/applications/__init__.py`。

- **修复方案**：
  1. `_SUPPORTED_INPUT_TYPES` 扩充支持 `"date"`、`"month"`、`"time"`、`"datetime-local"`。
  2. 新增 `DateInputFiller` 组件填充器，内置 `PartialDate` / `datetime` / 字符串规范化格式化（自动转换 `YYYY-MM-DD` 与 `YYYY-MM`），并集成至通用、Moka、北森三大适配器。
  3. 重构 `NativeSelectFiller`：支持从 DOM/元数据提取有效选项；内置双向语义映射（`gender: male` -> `<option value="1">男</option>`，`bachelor` -> `本科`，`master` -> `硕士研究生`，`TriState.YES` -> `是` 等）；选项存在但无法匹配时返回 `OPTION_MISMATCH` 并详细列出网页候选项。
- **回归测试**：`tests/unit/adapters/test_date_and_select_fillers.py`（10 项测试全部通过）。

## 二、尚未完成的功能

| 功能缺口 | 当前证据 | 建议验收标准 |
| --- | --- | --- |
| 登录与人工接管 | 有持久化浏览器目录，但没有登录状态判断和完整接管流程 | 首次登录、验证码、会话过期时暂停；完成后能继续识别表单 |
| 真正的平台复杂控件 | 北森学校选择器只点击触发；Moka 搜索选择只输入文本；引擎没有完整的 widget 识别 | 选中实际候选项并回读；覆盖搜索下拉、院校弹窗、级联选择和日期 |
| 多段教育/工作/项目 | 有列表数据模型，缺少重复分组定位、新增/删除记录和实体绑定 | 两段教育、两段实习分别填写到正确组，重复执行不新增重复记录 |
| 提交后的生命周期 | CLI 只有查询；最终 run 暂停在审核，未判断提交成功 | 用户提交后记录成功证据，或提供人工确认的 `mark-submitted`；失败与重复提交可辨别 |
| 简历导入后的审核与附件登记 | 解析后直接输出；`parse_file()` 未把源 PDF 注册到 assets | 展示待确认事实、缺失项和来源；用户确认后保存；明确登记源附件 |
| 导入隐私策略 | 简历全文直接进入模型请求；表单 DisclosurePolicy 不作用于导入 | 请求前可查看将发送的文本，支持本地服务与字段脱敏配置；文档明确数据边界 |
| 变体与纠错的用户入口 | 数据模型和 repository 存在，CLI 无变体/纠错管理命令 | 可选择目标变体、查看和撤销纠错；纠错严格按平台/租户/分组/控件范围生效 |
| 终端补填的完整闭环 | 补填直接 clear/type；不支持数组路径；磁盘校验失败后仍可能改内存 | 复用控件填充器，先校验 typed value，再一致更新磁盘与内存并回读网页 |
| 发布与持续集成 | 未发现 `.github` CI 配置或 `LICENSE` 文件 | Python 版本矩阵、强制浏览器回归、失败诊断工件、明确许可文本 |

## 三、建议开发顺序

1. **先保证填的是正确资料。** 修复人物/教育上下文、附件类型约束、跨候选人身份隔离，增加审核时的“页面标签 → 事实来源 → 实际值”对照。
2. **打通一次可恢复的申请。** 完成页面分类、登录接管、稳定岗位身份、跨进程恢复、最终提交后的状态确认。
3. **选一个真实平台做完整验证。** 建立可复现的脱敏页面 fixture，完成院校/日期/选项/多段经历；用端到端验收衡量支持程度。
4. **补齐用户操作入口。** 档案导入审核、附件与变体选择、纠错管理、记录导出；同步完善 CI 与许可文件。

当前最需要的是可靠的资料映射和申请流程。新增更多模型调用或批量投递之前，应先让上述错误条件有明确的暂停行为和自动化回归。

## 四、README 更新说明

本轮文档已调整为当前真实行为：

- 明确 v0.1 原型和本地表单验证范围，不再声称复杂平台控件全面支持。
- 统一 quick start 的 `APPLYPILOT_HOME`，修正默认目录与 `browser_profile/` 名称。
- 说明模型导入发送全文、档案历史保存完整内容，区分字段审计脱敏与数据库加密。
- 明确 checkpoint 不等于可恢复申请，`track` 不提供状态修改。
- 说明终端补填、源 PDF 附件登记、人工终审和浏览器关闭时机。
- 移除不存在的 LICENSE 链接及“不可篡改账本”等未实现承诺。

本轮新增发现暂未修改业务代码；后续可按以上优先级逐项修复并验收。
