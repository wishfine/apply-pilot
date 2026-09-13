# 深度审查：填写与恢复交互边界

基线：`e6289a2`。日期：2026-09-13。

## 后续深审修复（2026-09-13）

在上一轮修复基础上，继续修复并加入回归测试：完整字段描述变化检测与动态重扫、无效选填项阻断、每次运行更新披露上下文、终态应用防重跑、异常可恢复检查点、第三方联系人和模糊附件保守映射、资产类型校验、终端回写验证、编码性别选项、JSON 导入输出、内容派生 profile ID、真实表单快照和本地敏感文件权限；本轮又补上披露策略预填绕过、运行创建异常、checkpoint URL、复杂组件候选项回读、禁用提交按钮、失败事件脱敏、模型 ID 冲突和动态表单渲染等待。Python 3.11 与 3.14 强制浏览器全量测试均为 **390 passed**。

## 修复状态（2026-09-13）

本报告列出的 9 项问题均已修复并转化为自动回归。修复后的引擎会重新发现填写中出现的活动控件、将填写失败或值冲突阻断在终审前、在每轮填写前检测登录页，并在恢复时重建保存的目标披露策略。纠错记忆现在要求租户、控件类型和选项集合兼容；嵌套分组、具体学位、祖辈标签与日期输入也采用更严格的判定。

验证：Python 3.11 与 3.14 下强制浏览器测试的全量套件通过（390 项）。本报告保留原始复现和根因，作为后续回归与设计依据。

审查开始时的完整测试在 Python 3.14 下为 **344 passed（22.38 秒）**，强制启用了浏览器回归。额外检查使用真实 Chrome 的本地合成页面、临时 SQLite、虚构档案及 CliRunner；未访问真实招聘表单、未提交申请、未调用外部模型。

上一轮修复验证了单层上下文、静态表单、空字段填写失败等场景。本轮检查的是嵌套上下文、动态表单、非空旧值冲突和配置跨执行轮次保留，并发现以下未解决问题。

## P1-1：动态新增必填项未纳入就绪检查

位置：`applypilot/modules/apply/engine.py:320`、`:569`；`_refresh_readiness()` 位于 `:129`。

引擎每阶段只取得一次控件列表，后续仅回读原列表。填写过程中新增或从隐藏状态变为可见的字段没有重新扫描，也不会加入 readiness report。

复现网页：

```html
<input aria-label="姓名" oninput="if(!document.querySelector('#new')){let e=document.createElement('input');e.id='new';e.required=true;e.setAttribute('aria-label','邮箱');document.body.appendChild(e)}">
<button>提交申请</button>
```

提供姓名“候选人甲”，不提供邮箱。最终 DOM 存在空必填邮箱且 `validity.valid=false`，引擎仍返回 `ready_review`。

建议：填写/人工处理后重新发现当前活动字段，处理新字段和变化后的必填约束；以有界稳定循环完成扫描，持续变化时暂停。

## P1-2：改写失败但旧值非空，冲突被当作已完成

位置：`applypilot/modules/apply/readiness.py:183`；引擎字段动作与就绪信息之间的传递。

```html
<input aria-label="姓名" value="其他人乙" readonly required>
<button>提交申请</button>
```

档案姓名“候选人甲”。实际填写返回 `INPUT_ERROR`，DOM 仍为“其他人乙”，审计中的 expected/observed 指纹不同，但 readiness 只检查非空与 HTML validity，最终仍为 `ready_review`。

这不是“档案有值就视为填写”的旧问题，而是**非空值是否匹配及动作失败没有成为完成条件**。建议将冲突/填写失败作为独立状态，要求人工明确处理；不能把非空直接当正确。

## P1-3：恢复时丢失原申请的禁止披露字段

位置：`applypilot/cli/main.py:527`，以及申请上下文持久化设计。

用 Python API 创建目标并设置 `DisclosurePolicy(blocked_field_paths={'contact.email'})`，暂停后使用 `apply resume <id> -p profile.json`。通过 CliRunner 截取传给执行层的恢复目标，`blocked_field_paths` 变为空集合。

恢复重新构造 `ApplicationTarget`，没有加载原披露策略。默认允许普通邮箱填写，因此已明确禁止的字段在下一轮可能被填写。默认更严格的敏感开关不能覆盖自定义禁止路径丢失的问题。

建议：保存并恢复完整目标配置（披露策略、指定变体等）。旧记录缺少策略时不能默默视为默认允许；需要明确的保守恢复行为或用户重新设置。

## P1-4：纠错记忆跨租户、跨控件类型应用

位置：`applypilot/modules/apply/engine.py:288`；`applypilot/modules/apply/mapper.py:173`。

向真实 SQLite 写入一条记忆：provider=generic、tenant_hint=company_A、field_type=file、normalized_label=姓名、corrected_semantic_path=contact.email。按引擎当前方式仅用 platform 查询后，对文本姓名框调用映射器，返回 `contact.email / memory / 1.0`。

查询不带目标租户，映射器也不校验 field_type 或 options_signature。属于公司 A 的文件控件修正会污染其他公司的文本框。

建议：解析目标租户并执行显式作用域匹配；控件类型、选项集合变化时不得复用不兼容记忆。高优先级 memory 应有比关键词更严格的适用条件。

## P1-5：嵌套分组再次丢失家庭上下文

位置：`applypilot/browser/playwright_backend.py:117`。

```html
<section><h2>家庭成员</h2>
  <fieldset><label for="n">姓名</label><input id="n" required></fieldset>
</section>
<button>提交申请</button>
```

只取最近的 fieldset；该 fieldset 没有直接 legend，于是 section_title 为空，没有继续向外寻找 section 的“家庭成员”。结果填写候选人姓名并进入 `ready_review`。

建议：提取层级上下文，跳过没有标题的包装容器，并保留外层家庭/教育域与内层具体人物/阶段。不能只支持标题与字段位于同一层。

## P1-6：学位匹配把不同具体学位视为同一个硕士

位置：`applypilot/adapters/applications/generic.py:337`。

档案 `academic_degree=工学硕士`。网页选项为“理学硕士”“工程硕士”，没有完全匹配。填充器因目标包含“硕士”而选择第一个“理学硕士”，动作报 success，最终 `ready_review`。

建议：区分 education_level 与 academic_degree；“硕士层级”不能证明具体学位相同。没有等价候选时返回 mismatch，不应无条件取首个同层级选项。

## P1-7：有输入框的登录页绕过登录检查

位置：`applypilot/modules/apply/engine.py:571`。

```html
<h1>请先登录</h1>
<input aria-label="手机号">
<button>提交</button>
```

该页可被适配器的登录判别规则识别，但引擎只有在扫描结果为零字段时才调用登录判别。实际手机号被填写，随后“提交”按钮被认作最终提交按钮，返回 `ready_review`。

建议：在填写前完成页面分类，并在导航/结构变化后重新分类。登录页判断不能只放在零字段分支。

## P2-1：祖父/祖母标签仍被映射成父母

位置：`applypilot/modules/apply/mapper.py:225`。

`FieldMapper.map_field('x', '祖父姓名')` 返回 `soe_extended.family_members[father].name`，因为规则按包含“父”判断。上一轮只修正 resolver 中“祖父”关系不等于“父亲”，没有修正标签入口。

建议：采用明确关系词和优先级；不能解析的祖辈、监护人等关系应保持未映射，不能降级成父母。

## P2-2：日期校验接受无效日期并静默丢弃非法片段

位置：`applypilot/domain/base.py:29`、`:39`。

已直接调用 `PartialDate.model_validate` 验证：

| 输入 | 被接受为 |
| --- | --- |
| `2023-02-31` | `2023-02-31` |
| `2024-foo-12` | `2024-12` |
| `2024-01-01-extra` | `2024-01-01` |

解析器过滤非数字片段后继续解析，只限制月份 1–12、日 1–31，没有验证实际日历合法性。

建议：完整匹配输入格式；具备完整年月日时使用日历校验，局部日期保留合法精度；不静默修剪无效字符。

## 修复优先级与验收建议

1. 将就绪报告拆分为缺失、冲突、填写失败、需人工处理；在进入终审前重新发现全部活动字段。
2. 保留恢复上下文与披露策略，严格执行纠错记忆作用域。
3. 提取层级语义上下文，采用按字段类型区分的选项匹配。
4. 将登录分类移到填写前，再修正亲属标签和日期输入校验。

本记录的 9 项均有运行证据，不以“未实现完整平台支持”替代具体故障。审查时的 344 项测试没有覆盖上述输入；后续已将复现转化为回归断言。
