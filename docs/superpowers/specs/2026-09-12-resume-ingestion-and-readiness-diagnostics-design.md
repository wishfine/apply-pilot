# ApplyPilot 简历解析提取与网申必填项完整度诊断设计规范 (System Design Specification)

**版本**: v0.2.0-draft  
**模块定位**:
1. **`ResumeIngestion` (简历多格式解析提取器)**：将 PDF / LaTeX (`.tex`) 简历智能转换为高完整度 `CandidateProfile` 事实档案。
2. **`ReadinessDiagnostics` (网申必填项缺漏诊断与交互补填)**：在网申全流程中主动探测表单必填项，针对事实档案缺失字段提供实时诊断、终端交互补全与事实库反哺回写闭环。

---

## 1. 背景与核心价值

在 ApplyPilot v0.1 中，系统已成功实现了基于 `profile.yaml` 的事实库驱动网申、三级映射与终审卡点。然而在实际使用中存在两大体验瓶颈：
1. **档案建档门槛高**：求职者手头通常已拥有精美的 PDF 简历或 Overleaf/LaTeX 简历源码，从零手动编写上百行的结构化 `profile.yaml` 耗时繁琐；
2. **目标平台必填字段缺漏**：不同企业或招聘系统（如国央企对“政治面貌”、“籍贯”、“家庭成员”，外企对“紧急联系人”等）常有独特的必填项。如果求职者的 `profile.yaml` 中恰好留白，传统自动化会直接跳过，导致最终在点击下一步或提交时被页面阻断或报校验错误。

本模块通过**简历解析提取器**将建档时间缩短至秒级，并通过**必填项前置诊断与闭环补填**彻底杜绝因信息漏填引发的提交失败。

---

## 2. 核心架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             ApplyPilot CLI                                  │
│  applypilot profile import -f resume.pdf / applypilot apply run -u <url>    │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │                             │
                        ▼ [建档阶段]                  ▼ [填报阶段]
      ┌─────────────────────────────────┐   ┌─────────────────────────────────┐
      │   Resume Ingestion Subsystem    │   │  Readiness Diagnostics Subsys   │
      ├─────────────────────────────────┤   ├─────────────────────────────────┤
      │ • PdfExtractor (pypdf)          │   │ • FormRequirementDetector       │
      │ • TexExtractor (LaTeX AST/Regex)│   │ • ReadinessAuditor              │
      │ • LLM Extraction Adapter        │   │ • InteractiveTerminalResolver   │
      │   (DeepSeek/Ollama/OpenAI)      │   │ • ProfileWritebackSynchronizer  │
      │ • CandidateProfile Validator    │   │                                 │
      └────────────────┬────────────────┘   └────────────────┬────────────────┘
                       │                                     │
                       ▼                                     ▼
      ┌─────────────────────────────────┐   ┌─────────────────────────────────┐
      │     profile.yaml (事实档案)      │──▶│    ApplyEngine (状态机填报)     │
      └─────────────────────────────────┘   └─────────────────────────────────┘
```

---

## 3. 子系统 1：简历解析提取器 (Resume Ingestion)

### 3.1 架构分层与无外部专有依赖

遵循本地优先（Local-first）原则，简历解析采用**本地纯文本抽取 + 标准 OpenAI 协议结构化提取**的双层架构：
1. **本地抽取层**：
   - PDF 文件通过纯本地 Python 库 `pypdf` 进行文本流提取，保留段落排版并自动去重页眉页脚；
   - LaTeX (`.tex`) 文件通过专有规则引擎剔除注释（`%` 开头）、展开通用环境（`itemize`, `tabular` 等）、剔除排版宏命令（如 `\vspace`, `\textbf`, `\geometry` 等），转化为干净语义文本。
2. **结构化适配层**：
   - 依赖本地或远程的兼容端点（如本地 `ollama run deepseek-r1` / `qwen2.5`，或配置 API Key 的 DeepSeek / OpenAI 端点）；
   - 使用 `CandidateProfile.model_json_schema()` 构建强约束 Prompt，要求模型仅提取可验证的客观事实，**严禁对未提及的事实做主观臆造**。
3. **校验与输出层**：
   - 模型输出通过 `CandidateProfile.model_validate(raw_dict)` 进行严苛的 Pydantic v2 校验；
   - 提取结果在终端通过 Rich Table 格式化展示候选人摘要；
   - 写入用户指定的输出文件（默认为 `profile.yaml`）。

### 3.2 详细组件接口定义

```python
# applypilot/modules/profile/ingestion/extractors.py
from pathlib import Path
from typing import Protocol

class TextExtractor(Protocol):
    def extract_text(self, file_path: Path) -> str:
        """从简历源文件中提取无排版噪点的纯净文本."""
        ...

class PdfExtractor:
    def extract_text(self, file_path: Path) -> str:
        # 使用 pypdf 读取所有页面文本并标准化空白符
        ...

class TexExtractor:
    def extract_text(self, file_path: Path) -> str:
        # 正则剥离 LaTeX 导言区、排版宏、注释，保留主体文本
        ...
```

```python
# applypilot/modules/profile/ingestion/service.py
from typing import Optional
from pathlib import Path
from applypilot.domain.profile import CandidateProfile

class ResumeIngestionService:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        ...

    def parse_file(self, file_path: Path) -> CandidateProfile:
        """输入 PDF 或 .tex 路径，解析并校验为 CandidateProfile 实体."""
        ...
```

---

## 4. 子系统 2：必填项缺漏诊断与交互补填 (Readiness Diagnostics)

### 4.1 必填项精准特征嗅探 (Requirement Detection)

在真实招聘系统中（如北森、Moka），必填标记不仅体现在原生 HTML 属性，更常以 CSS 类或伪元素形式存在。`FormRequirementDetector` 组合判定规则如下：

```python
# applypilot/modules/apply/readiness.py
from enum import StrEnum
from typing import Optional, Any
from pydantic import BaseModel

class FieldReadinessStatus(StrEnum):
    FILLED = "filled"                    # 映射成功，本地有值且已填报
    OPTIONAL_EMPTY = "optional_empty"    # 选填项且本地留白，安全跳过
    REQUIRED_MISSING = "required_missing"# ⚠️ 目标系统必填，但本地档案缺失或为空

class FieldReadinessItem(BaseModel):
    field_sig: str
    label: str
    section_title: str
    is_required: bool
    status: FieldReadinessStatus
    profile_path: Optional[str] = None
    observed_value: Optional[str] = None
    suggested_fix: Optional[str] = None
```

**必填标记判定逻辑**：
1. **原生属性**：`element.has_attribute("required")` 或 `element.get_attribute("aria-required") == "true"`；
2. **标签与父容器标记**：
   - 文本内容包含前导/后置星号 `*`；
   - 关联标签或父层容器类名匹配：`[class*="required"]`, `[class*="is-required"]`, `[class*="star"]`, `[class*="must"]`；
3. **排除项**：明确标有“（选填）”、“(optional)”的元素直接降级为选填。

### 4.2 诊断与即时交互卡点工作流

在 `ApplyEngine` 处理每一个业务阶段（Stage）时，执行以下卡点：

```
[ 执行完当前阶段初步填报 ]
            │
            ▼
[ ReadinessAuditor 扫描并审计当前阶段所有控件 ]
            │
      是否存在 REQUIRED_MISSING ?
      ├── 否 (100% 满足) ──▶ 继续自动进入下一步 (Advance)
      └── 是 ──▶ 触发【就绪诊断终端交互卡点】
                     │
                     ▼
  ┌────────────────────────────────────────────────────────┐
  │ 终端打印 Rich Table: 标明缺失的字段名、所属板块、建议路径 │
  │                                                        │
  │ 用户交互菜单:                                           │
  │ [1] 终端即时逐项补全                                    │
  │ [2] 切换至浏览器手动补填                                │
  │ [3] 终止本次网申                                        │
  └────────────────────────────────────────────────────────┘
```

#### 用户处理行为分支：
- **分支 1（终端补全并反哺）**：
  - 针对每一个缺失项，终端高亮提示用户输入；
  - 引擎实时调用对应适配器驱动浏览器填入表单；
  - 内存中的 `CandidateProfile` 同步更新；
  - 交互询问：`"是否将新补充的信息持久化回写至本地 profile.yaml？[Y/n]"`。若为 Y，调用 `ProfileWritebackSynchronizer` 安全更新源 YAML 文件（保留原有格式与注释结构）。
- **分支 2（浏览器手动补填）**：
  - 引擎主动等待：`"请在打开的浏览器中手动填好上述字段，完成后按回车继续..."`；
  - 用户敲击回车后，引擎重新执行 `ReadinessAuditor` 扫描回读，确认必填项已无缺失后继续流转。
- **分支 3（放弃/终止）**：
  - 更新运行状态为 `paused`，记录中断审计日志，安全退出。

---

## 5. CLI 终端命令接口扩充

### 5.1 档案导入命令 (`profile import`)
```bash
applypilot profile import [OPTIONS]

选项:
  -f, --file PATH        (必填) 输入的简历文件路径 (.pdf 或 .tex)
  -o, --output PATH      (可选) 输出的 profile.yaml 路径，默认为当前目录或标准配置目录下的 profile.yaml
  --model TEXT           (可选) 指定用于结构化解析的模型名称，默认使用 deepseek-chat 或配置中的默认模型
  --base-url TEXT        (可选) 指定 OpenAI 兼容端点 (例如 http://localhost:11434/v1 用于本地 Ollama)
  --api-key TEXT         (可选) 显式传入 API Key（优先读取 APPLYPILOT_LLM_API_KEY 环境变量）
```

### 5.2 网申执行命令升级 (`apply run`)
增强 `apply run` 的诊断交互开关：
```bash
applypilot apply run [OPTIONS]

选项:
  -u, --job-url TEXT     (必填) 目标岗位 URL
  -p, --profile PATH     (可选) 事实档案路径
  --headless             (可选) 无头模式运行
  --auto-interactive / --no-interactive
                         (可选) 是否在遇到必填缺失时启用终端交互补全，默认开启
```

---

## 6. 测试与验证计划

1. **简历解析单元测试 (`tests/unit/profile/test_ingestion.py`)**：
   - 验证 `PdfExtractor` 从样例 PDF 中提取干净分段文本；
   - 验证 `TexExtractor` 剥离复杂的 LaTeX 宏命令、环境和行内样式；
   - 验证 Mock LLM 返回结构化 JSON 后，`CandidateProfile.model_validate` 的准确组装。
2. **必填项探测与诊断测试 (`tests/unit/apply/test_readiness.py`)**：
   - 验证 `FormRequirementDetector` 对 HTML 原生属性、星号标签、类名的准确探测；
   - 验证在缺失必填字段时生成 `REQUIRED_MISSING` 状态报告；
   - 验证终端补全后表单填充与 `profile.yaml` 反哺回写。
3. **E2E 流程测试 (`tests/e2e/test_cli_import_and_readiness.py`)**：
   - 模拟完整的 `profile import` 流程生成合法 YAML 档案；
   - 模拟带有必填缺失的表单场景，验证交互式补填与全流程推进。
