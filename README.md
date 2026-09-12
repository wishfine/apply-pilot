<div align="center">

# 🚀 ApplyPilot

**面向中国校招与社招场景的本地优先（Local-first）智能求职网申 Agent**

*One profile. Every application. —— 一份资料，投遍所有岗位。*

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-186%20Passed-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/Design-Local--first-orange.svg)](docs/superpowers/specs/2026-09-12-apply-pilot-v0.1-design.md)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 📖 项目简介

每年春秋招与社招求职季，求职者往往需要向**央国企、互联网大厂、金融银行、科研院所**等数十家甚至上百家企业投递网申。每家单位采用不同的招聘系统（如**北森、Moka、自建系统**），求职者被迫陷入无休止的“复制粘贴基本信息、手动填写家庭成员、反复勾选学历背景”的机械内耗中。

**ApplyPilot** 专为解决这一困境而生：求职者仅需在本地维护一份详实严谨的**核心事实档案（CandidateProfile）**，ApplyPilot 即可在本地受控浏览器中，智能识别目标招聘系统、自动完成多阶段表单填报与回读校验，并在最终提交前主动挂起，由你亲自完成终审与点击提交。

---

## 🛡️ 核心设计原则

| 维度 | 传统自动化脚本 / 劣质 Agent | ApplyPilot 的设计准则 |
| :--- | :--- | :--- |
| **真实性保障** | 依赖大模型自由发挥，容易发生**事实幻觉、臆造经历** | **`CandidateProfile = Truth`**：事实库是唯一真理，杜绝一切无中生有与虚假默认值。 |
| **简历针对性** | 一份简历打天下，或改动事实原件 | **`ResumeVariant = Selection + Ordering + Presentation`**：变体仅剪裁与排序事实，每条亮点强制溯源至事实 ID。 |
| **隐私数据安全** | 将求职者身份证、家庭背景、手机号全量发给云端 LLM | **本地优先（Local-first）**：数据保存在本地 SQLite（WAL 模式），本地 `0o600` HMAC-SHA256 脱敏指纹，敏感数据默认不出网。 |
| **账号与反爬** | 强行逆向验证码接口，极易触发风控或封号 | **持久化浏览器（Persistent Context）**：求职者在真机浏览器中手动完成微信扫码或短信登录一次，会话长期复用。 |
| **投递控制权** | 盲目无人全自动提交，填错无法挽回 | **人机协同终审（Human-in-the-Loop）**：表单自动填好后严格停在 `READY_REVIEW` 卡点，由求职者在浏览器内亲自确认并点击提交。 |

---

## 🌐 支持平台生态 (v0.1)

- **北森 (Beisen / iTalent)**：支持多步骤向导流程、院校弹窗选择器（Modal School Picker）、级联选择。
- **Moka (MokaHR)**：支持单页长表单、搜索下拉选择器（Search-Select）、日期组件。
- **通用系统 (Generic HTML5)**：标准 HTML5 表单自动解析、文本/电话/邮箱/数字智能填充与平滑回退。

---

## ⚡ 快速上手 (Quick Start)

### 1. 安装环境与依赖

本项目基于现代 Python 工具链 **`uv`**（推荐）进行包管理：

```bash
# 1. 克隆代码仓库
git clone git@github.com:wishfine/apply-pilot.git
cd apply-pilot

# 2. 同步依赖环境 (要求 Python >= 3.11)
uv sync

# 3. 安装 Playwright Chromium 浏览器核心
uv run playwright install chromium
```

---

### 2. 第一步：配置你的核心事实档案 (`profile.yaml`)

从项目自带的标准模板复制并创建你的个人档案：

```bash
cp examples/profile.example.yaml profile.yaml
```

打开 `profile.yaml`，填入你的客观真实信息。该模板包含中国校招与社招的所有核心字段：
- **身份信息**：姓名、拼音、性别、出生日期、证件号码、民族、健康状况；
- **联系信息**：手机、邮箱、常住城市、紧急联系人；
- **教育背景**：多段学历层次（高中/专科/本科/硕士/博士）、学位、专业、毕业时间、GPA、是否第一学历、是否最高学历；
- **经历与项目**：实习经历、项目经历、技术栈、核心成就亮点（Bullets）；
- **专业技能**：技能类别、熟练度；
- **校招专有**：毕业年月、CET-4/6 成绩、英语标化考试、派遣证资格；
- **体制内/国央企扩展**：政治面貌、入党年月、籍贯、户口所在地、家庭成员、亲属回避与利益冲突申报。

> 💡 **提示**：模板中的字段均为结构化严格类型，非必填字段如果暂时留空，ApplyPilot 在网申遇到选填时会自动保持留白，不会胡乱编造。

---

### 3. 第二步：校验你的事实档案

使用内置校验命令验证你的档案格式是否合法：

```bash
# 验证 profile.yaml 结构正确性
uv run applypilot profile validate -p profile.yaml

# 输出示例：
# Profile validated successfully!
# Candidate: 张三 (cand_zhangsan_2026)
# Education records: 2
# Experience records: 2
# Project records: 1
```

查看已配置的核心摘要：

```bash
uv run applypilot profile show -p profile.yaml
```

---

### 4. 第三步：启动智能自动网申会话

只需一条命令即可开启目标职位的网申流程：

```bash
uv run applypilot apply run -u "https://app.mokahr.com/campus-recruitment/your-target-company/10001#/job/xxx" -p profile.yaml
```

#### 自动化全流程体验：
1. **浏览器唤起**：自动弹出本地 Chromium 浏览器（保留本地登录状态，若首次打开只需微信扫码或短信登录一次）；
2. **多信号平台检测**：结合 URL Host、DOM 结构与运行时脚本，毫秒级自动判别目标招聘平台（Moka / 北森 / 通用）；
3. **分阶段表单自动化**：
   - 逐页扫描输入框、下拉框与选择器；
   - 基于三级决策树（Scoped 纠错记忆 $\to$ 权威规则 $\to$ 语义匹配）将表单控件与事实库路径精确对齐；
   - 严格进行隐私门禁（Disclosure Policy）过滤；
   - 读取页面现有值，若已填写且语义等价（如“北京市”与“北京”）则自动跳过，避免重复键入；
   - 驱动对应平台的组件适配器执行清空与输入；
   - 每步操作在本地 SQLite 保存物化 Checkpoint 断点；
4. **终审卡点（READY_REVIEW）**：
   - 表单填写完毕后，自动化引擎**主动停止**，并在终端输出提示：
     ```text
     表单字段已填写完毕，请在浏览器中核对后亲自点击提交
     ```
   - 你可以在已打开的浏览器页面中逐项检查所有字段，上传个性化附件，最终亲自点击提交按钮！

---

### 5. 第四步：跟踪与查看申请看板

ApplyPilot 内置基于 SQLite WAL 模式的不可篡改审计追踪账本，随时查看申请进度：

```bash
# 查看所有申请记录及当前阶段状态
uv run applypilot track list

# 按状态筛选（如筛选处于终审阶段的岗位）
uv run applypilot track list -s ready_review

# 查看特定申请的详细上下文与审计统计
uv run applypilot track status app_xxx
```

---

## 🛠️ CLI 命令完整参考

```bash
applypilot [OPTIONS] COMMAND [ARGS]...

选项:
  --version, -v    显示版本信息 (ApplyPilot v0.1.0)
  --help           显示帮助信息

命令组:
  profile          管理候选人事实库档案
    validate       校验 YAML/JSON 档案数据格式 (-p, --path <FILE>)
    show           展示候选人核心事实摘要 (-p, --path <FILE>)

  apply            自动化表单填写与人机协同投递
    run            启动智能网申会话
                   -u, --job-url <URL>        (必填) 目标网申岗位链接
                   -p, --profile <FILE>       (可选) 指定档案路径，默认使用本地档案
                   --headless                 (可选) 是否以无头模式运行（默认可视弹出）

  track            查看申请记录与审计历史
    list           列表展示本地申请任务 (-s, --status <STATUS>)
    status         查看指定申请的详细状态与事件看板 (APP_ID)
```

---

## 📂 本地数据与隐私安全机制

ApplyPilot 遵循 **Local-First（本地优先）** 准则，数据存储在用户系统标准主目录下：

- **macOS**: `~/Library/Application Support/ApplyPilot/`
- **Linux**: `~/.local/share/applypilot/`
- **Windows**: `%LOCALAPPDATA%\ApplyPilot\`

目录结构：
```text
~/.applypilot/
├── applypilot.db         # 本地 SQLite 主库（10 张物理表，WAL 模式并发安全）
│                         # 存储：申请状态、断点 Checkpoint、字段动作记录、纠错记忆
├── .audit_secret         # 本地生成的 32 字节高强度随机盐值（文件权限严格限制为 0o600）
└── browser/              # Chromium 用户数据目录（保存登录凭据 Cookie 与 LocalStorage，免去重复登录）
```

> 🔒 **敏感数据保护承诺**：
> - 身份证号、政治面貌、家庭背景等敏感字段在写入日志前，全部经过本地专属密钥生成的 `hmac-sha256:{hex}` 单向脱敏指纹过滤，绝不记录明文。
> - 未经用户明确授权的敏感字段绝不进入大模型上下文。

---

## 🧪 开发与测试

本项目采用严格的测试驱动开发（TDD）规范，包含完整的单元测试与端到端 Smoke 测试：

```bash
# 运行完整测试套件 (186 项测试)
uv run pytest

# 运行特定模块测试
uv run pytest tests/unit/adapters/ -v
uv run pytest tests/unit/modules/test_engine.py -v
uv run pytest tests/e2e/test_cli_smoke.py -v
```

---

## 📄 开源协议与声明

- 本项目基于 **MIT License** 开放源代码。
- **免责声明**：ApplyPilot 旨在作为求职者的受控辅助工具，减轻繁重的重复表单输入负担。投递事实的真实性、最终提交动作及由此产生的一切求职结果均由求职者本人完全负责。请在点击最终提交前务必仔细核对所有表单信息。
