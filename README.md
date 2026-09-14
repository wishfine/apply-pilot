<div align="center">

# 🚀 ApplyPilot

**面向中国校招与社招的本地网申辅助工具**

*One profile. Every application.*

[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/Tests-415%20Passed-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/Design-Local--first-orange.svg)](docs/superpowers/specs/2026-09-12-apply-pilot-v0.1-design.md)

</div>

ApplyPilot 从本地候选人档案读取资料，通过 Playwright 辅助填写招聘表单，在最终提交前交给用户核对。档案支持身份、联系方式、多段教育与经历、技能、附件，以及中国校招和国央企扩展信息。

**当前版本是 v0.1 原型。** 数据模型覆盖的字段多于自动填写已支持的字段；平台适配器已通过本地合成表单测试，尚未在真实招聘站点全面验证。已知缺陷和下一步开发建议见[项目审查记录](docs/reviews/2026-09-13-project-audit.md)。

## 当前能力与边界

| 能力 | 当前实现 |
| :--- | :--- |
| 档案管理 | 校验、查看 YAML/JSON；从可提取文本的 PDF 和单个 `.tex` 文件调用模型生成档案 |
| 字段映射 | 纠错记忆、固定规则、关键词启发式；表单填写本身不调用 LLM |
| 基础控件 | 文本框、文本域、原生 select、radio/checkbox、文件上传；读取实时值、选中状态和关联 label；支持同源 iframe 控件 |
| 就绪检查 | 等待动态表单完成渲染后检查当前可见阶段的必填项；字段检查失败、填写失败或人工补填后仍不满足要求时暂停 |
| 北森 | 识别部分阶段标记和“下一步”按钮，验证阶段变化；识别最终提交按钮并停下 |
| Moka / 通用 | 基础控件填充；登录后会重新识别页面和平台，弹窗/新标签会切换到最新页面 |
| 复杂组件 | 院校弹窗、搜索下拉会在找不到并回读候选项时暂停；级联、自定义日期弹窗、动态重复经历尚未完整支持；原生 date/month 已支持，缺失精度时暂停而不补造日期 |
| 跟踪 | SQLite 保存申请、执行轮次、阶段快照、审计事件；CLI 可查询记录 |
| 恢复与提交后状态 | 支持 `apply resume` 重新打开 checkpoint 的实际 URL 并扫描；候选人、岗位、周期隔离，并保留已保存的披露策略；提交结果确认尚未实现 |

`CandidateProfile` 是事实来源，`ResumeVariant` 是展示与选择的数据模型。当前 CLI 尚未提供变体选择、简历导出和纠错记忆编辑命令。自动提取的资料仍需人工核实，结构校验不能证明事实正确。

## 快速开始

以下命令适用于 macOS/Linux 的 shell；Windows 可设置同名环境变量，使用对应的路径与复制命令。

### 1. 安装

```bash
git clone git@github.com:wishfine/apply-pilot.git
cd apply-pilot
uv sync
uv run playwright install chromium
```

项目声明 Python >= 3.11；最近一次完整测试在 Python 3.11 和 3.14 上均为 414 项通过。

### 2. 统一资料目录

```bash
export APPLYPILOT_HOME="$HOME/.applypilot"
mkdir -p "$APPLYPILOT_HOME"
```

后续终端也需设置该变量。未设置时，程序使用 `platformdirs` 返回的操作系统应用数据目录，而非固定的 `~/.applypilot`。查看当前目录：

```bash
uv run python -c 'from applypilot.core.config import get_app_home_dir; print(get_app_home_dir())'
```

### 3. 准备候选人档案

方式 A：复制[示例模板](examples/profile.example.yaml)，替换全部示例资料。

```bash
cp examples/profile.example.yaml "$APPLYPILOT_HOME/profile.yaml"
```

方式 B：从简历生成档案。

```bash
# 先在本地环境中配置 APPLYPILOT_LLM_API_KEY
uv run applypilot profile import -f resume.pdf
# 或
uv run applypilot profile import -f resume.tex
```

`profile import` 会将提取的简历全文发送给配置的模型服务。默认地址为 `https://api.openai.com/v1`，默认模型为 `gpt-4o-mini`；可通过 `--base-url`、`--model` 或环境变量覆盖。当前实现要求 API key，包括连接本地兼容服务时；可按该服务要求提供占位值。

支持的环境变量：`APPLYPILOT_LLM_API_KEY`、`APPLYPILOT_LLM_BASE_URL`、`APPLYPILOT_LLM_MODEL`；API key 和地址也可读取 `OPENAI_API_KEY`、`OPENAI_BASE_URL`。导入没有全文脱敏或事实核验步骤，也没有 OCR。重复导入同一输出路径会覆盖文件；需要保留已有档案时使用 `-o` 指定新路径。

导入目前不会自动把源 PDF 登记为上传附件。需要上传简历时，在档案中添加：

```yaml
assets:
  - asset_id: asset_resume_pdf
    asset_type: resume_pdf
    file_path: /absolute/path/to/resume.pdf
    title: 求职简历
```

请核对文件路径和类型。默认简历 ID 不存在时，仅在有且只有一个明确标为 `resume_pdf` / `resume` 的附件时回退；多个简历必须通过明确的附件 ID 选择，不会根据目录或文件名猜测类型。

### 4. 校验资料并运行

```bash
uv run applypilot profile validate -p "$APPLYPILOT_HOME/profile.yaml"
uv run applypilot profile show
uv run applypilot apply run -u "https://目标招聘网站/实际表单地址"
```

为避免从聊天窗口复制 Markdown 链接时把 `[标题](URL)` 一起带入，推荐把目标地址保存到应用目录的 `config.yaml`：

```yaml
job_url: "https://目标招聘网站/实际表单地址"
```

之后可以直接运行 `uv run applypilot apply run`；也可以用 `-c/--config` 指定其他配置文件。命令行仍支持 `-u/--job-url`，并会自动解包标准 Markdown 链接、还原被转义的 `&`，对缺少 `http(s)` 或主机名的输入直接报错。

尽量使用已登录、已打开填写步骤的表单地址。浏览器使用独立的持久化目录，不会自动复用你日常 Chrome 的登录状态；遇到登录、短信验证或暂时未加载出控件的页面时，交互模式会保持浏览器打开并提示你完成操作，回到终端按回车后重新扫描。

运行时：

1. 打开 Chromium，检测平台并扫描控件。
2. 登录、验证或页面控件尚未出现时，按终端提示在浏览器中完成操作，再按回车重新扫描。
3. 按规则匹配本地档案，应用披露策略后尝试填写。
4. 回读页面，检查必填项。出现缺失时可选择浏览器补填、终端补填或暂停。
5. 人工补填后再次检查；仍未满足要求则进入 `PAUSED`。
6. 到达 `READY_REVIEW` 后，在浏览器中核对并亲自提交，完成后再回终端按回车。回车结束流程后浏览器会关闭。

终端补填目前仅适合普通文本控件；数组路径（如某段教育经历）不支持自动回写，下拉框和文件上传等请在浏览器处理。JSON 档案回写会保留 JSON 格式。

`READY_REVIEW` 目前不能证明已到达真实站点的最终提交页，也不能证明全部资料正确。未识别到终审页或无法翻页时会暂停，仍需用户核对真实站点的审核页面。`--headless` 不适合需要浏览器人工接管的流程。

### 5. 查看记录

```bash
uv run applypilot track list
uv run applypilot track list -s paused
uv run applypilot track status app_xxx
```

恢复已暂停申请：

```bash
uv run applypilot apply resume app_xxx -p "$APPLYPILOT_HOME/profile.yaml"
```

恢复前校验候选人归属、申请状态和 checkpoint，保留招聘周期、平台信息与披露策略，并重新打开保存的实际页面 URL、重新扫描。相同 URL 保持岗位 ID 稳定，`#/job/...` 路由参与身份计算。旧记录没有保存披露策略时，恢复会禁止自动填写，直到用户在浏览器中人工核对；旧版本生成的随机岗位 ID 不会自动迁移；尚无“标记已提交”命令。页面仅存在内存中的步骤状态无法通过 URL 重建时，需要人工重新进入对应步骤。

## CLI 参考

| 命令 | 主要参数 |
| :--- | :--- |
| `profile import` | `-f/--file`；`-o/--output`；`-m/--model`；`-b/--base-url`；`-k/--api-key` |
| `profile validate` | `-p/--path`，必填 |
| `profile show` | `-p/--path`，默认读取应用目录的 `profile.yaml` |
| `apply run` | `-u/--job-url`（或配置文件中的 `job_url`）；`-c/--config`；`-p/--profile`；`--headless`；`--interactive-readiness/--no-interactive-readiness` |
| `track list` | `-s/--status` |
| `track status` | 申请 ID |

`profile import` 默认输出到应用目录的 `profile.yaml`。使用 `uv run applypilot --help` 或子命令 `--help` 查看完整参数。

## 本地数据与隐私

设置上述 `APPLYPILOT_HOME` 后，目录结构为：

```text
~/.applypilot/
├── profile.yaml
├── config.yaml
├── applypilot.db
├── .audit_secret
└── browser_profile/
```

- 档案和历史 `profile_revisions` 在本地以完整内容保存，没有数据库加密。
- 字段操作审计使用 HMAC 指纹和遮罩预览；表单快照只保存结构元数据；已识别的身份证、政治面貌、家庭等敏感路径不保留明文预览。这不等于整个数据库均已脱敏。
- `DisclosurePolicy` 控制向招聘表单填写部分敏感字段；CLI 当前没有配置该策略的选项。
- 简历导入直接发送全文到所配置的模型服务，和本地表单填写的披露策略是两条独立流程。
- SQLite WAL 提供事务与并发支持；审计表没有防篡改签名链或禁止修改的数据库约束，不能视为不可篡改账本。

## 开发与测试

```bash
uv run pytest

# 强制真实浏览器回归测试实际执行，缺少浏览器时失败
APPLYPILOT_REQUIRE_BROWSER_TESTS=1 uv run pytest tests/integration/ -q

# 使用隔离环境验证 Python 3.13，不替换当前 .venv
APPLYPILOT_REQUIRE_BROWSER_TESTS=1 uv run --isolated --python 3.13 --locked pytest -q
```

当前共有 415 项测试，其中包含真实浏览器表单回归、同源 iframe、延迟短信登录页、申请隔离和恢复校验测试。浏览器测试使用本地合成表单和虚构资料，优先使用 Playwright Chromium，也可使用已安装的 Chrome。默认在两者均不可用时跳过相关测试；这部分 Chrome 回退只适用于测试，CLI 仍使用 Playwright Chromium。

测试通过说明已覆盖的行为符合断言，不代表真实招聘站点全功能兼容。后续重点包括上下文映射、附件类型约束、登录与页面识别、可恢复申请状态机，以及真实平台组件适配。

## 项目资料

- [初始设计](docs/superpowers/specs/2026-09-12-apply-pilot-v0.1-design.md)
- [导入与就绪诊断设计](docs/superpowers/specs/2026-09-12-resume-ingestion-and-readiness-diagnostics-design.md)
- [本轮审查：剩余 bug、功能缺口与优先级](docs/reviews/2026-09-13-project-audit.md)

仓库目前尚未提供 `LICENSE` 文件，正式发布前需要补齐许可文本。请在真实投递前核实资料和附件，最终提交由用户完成。
