# 智能代码文档生成与审查系统 V2.0

自动分析 Python 项目，生成结构化 Markdown 文档、依赖关系图和代码质量报告，可选接入 Claude AI 实现智能摘要与审查建议。

## 特性

- **零依赖**：仅使用 Python 标准库（`ast`、`re`、`pathlib` 等）
- **静态分析**：自动提取函数、类、参数、返回值、圈复杂度
- **质量审查**：内置规则检测（缺文档、高复杂度、过长函数、参数过多）
- **AI 增强**（可选）：接入 Claude API，自动生成模块摘要和改进建议
- **Mermaid 依赖图**：可视化文件间依赖关系
- **灵活 CLI**：支持多种运行模式

## 安装

```bash
pip install code-doc-system
```

或从源码安装：

```bash
git clone https://github.com/your-org/code-doc-system.git
cd code-doc-system
pip install -e .
```

## 快速开始

```bash
# 分析当前目录，输出到 ./output
code-doc .

# 指定项目路径和输出目录
code-doc ./my_project --output ./docs

# 启用 AI 增强（需设置环境变量）
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
code-doc ./my_project --output ./docs

# 仅打印质量报告到控制台
code-doc . --report-only

# 禁用 AI，纯静态分析
code-doc . --no-ai
```

也可以作为 Python 模块运行：

```bash
python -m code_doc_system .
```

## 输出结构

```
output/
└── docs/
    ├── index.md            # 主索引（所有文件汇总）
    ├── dependencies.md     # Mermaid 依赖关系图
    ├── quality_report.md   # 代码质量报告
    └── <file_name>.md      # 每个文件的独立文档
```

## 在代码中使用

```python
from pathlib import Path
from code_doc_system.core import (
    AdvancedCodeAnalyzer,
    CodeQualityReviewer,
    AdvancedDocumentationGenerator,
    ClaudeClient,
)

project = Path("./my_project")

# 分析
analyzer = AdvancedCodeAnalyzer()
elements, deps = analyzer.analyze_project(project)

# 审查（可选 AI）
claude   = ClaudeClient()               # 读取 ANTHROPIC_API_KEY
reviewer = CodeQualityReviewer(claude)
reports  = reviewer.review_elements(elements)

# 生成文档
gen = AdvancedDocumentationGenerator(claude)
gen.generate_comprehensive_docs(elements, deps, reports, Path("./output"))
```

## AI 功能说明

设置 `ANTHROPIC_API_KEY` 环境变量后，系统会自动：

1. 为每个文件生成 2–3 句中文功能摘要
2. 读取代码结构，给出具体的重构改进建议

不设置时自动回退到纯静态分析模式，不影响其他功能。

## 许可证

MIT License
