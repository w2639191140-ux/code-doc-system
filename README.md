# code-doc-system

Started this because I kept inheriting Python projects with zero documentation.
Built a tool that handles the tedious part — scans your codebase, pulls out
functions/classes/params, measures complexity, and outputs clean Markdown docs.

Optionally hooks into Claude API if you want AI-generated module summaries and
refactoring hints on top of the static analysis.

---

## What it does

- Walks your entire project and parses every `.py` file via AST
- Extracts functions, classes, parameters, return types, and cyclomatic complexity
- Flags issues: missing docstrings, overly complex functions, too many parameters
- Outputs a `docs/` folder with an index, per-file pages, and a Mermaid dependency graph
- Generates a quality score (0–100) per file with a breakdown of warnings/errors
- No third-party dependencies — just the Python standard library

## Quick start

```bash
# analyze current directory, write docs to ./output
python -m code_doc_system .

# specify paths
python -m code_doc_system ./my_project --output ./docs

# AI summaries (needs ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
python -m code_doc_system ./my_project

# just print the quality report, no files written
python -m code_doc_system . --report-only

# skip AI entirely
python -m code_doc_system . --no-ai
```

## Output structure

```
output/
└── docs/
    ├── index.md            # full project overview
    ├── dependencies.md     # mermaid dependency graph
    ├── quality_report.md   # per-file scores and issues
    └── <module_name>.md    # one page per source file
```

## Use it as a library

```python
from pathlib import Path
from code_doc_system.core import (
    AdvancedCodeAnalyzer,
    CodeQualityReviewer,
    AdvancedDocumentationGenerator,
    ClaudeClient,
)

analyzer = AdvancedCodeAnalyzer()
elements, deps = analyzer.analyze_project(Path("./my_project"))

claude   = ClaudeClient()  # reads ANTHROPIC_API_KEY from env
reviewer = CodeQualityReviewer(claude)
reports  = reviewer.review_elements(elements)

gen = AdvancedDocumentationGenerator(claude)
gen.generate_comprehensive_docs(elements, deps, reports, Path("./output"))
```

## AI features

When `ANTHROPIC_API_KEY` is set the tool will:

1. Write a 2–3 sentence plain-English summary for each module
2. Suggest concrete refactoring steps based on the code structure

Falls back to static-only mode silently if the key is missing.

## Install

```bash
pip install .
```

Or install the CLI globally:

```bash
pip install -e .
code-doc .
```

## License

MIT
