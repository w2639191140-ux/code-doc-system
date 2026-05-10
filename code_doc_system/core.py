"""
智能代码文档生成与审查系统
V2.0 - 完整版本（含AI智能生成、质量审查、依赖图）
"""

import os
import ast
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
import urllib.request

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  数据类
# ──────────────────────────────────────────────

@dataclass
class CodeElement:
    """代码元素数据类"""
    name: str
    type: str          # 'function', 'class'
    docstring: str
    params: List[str]
    returns: str
    complexity: int    # 圈复杂度
    line_count: int
    file_path: str
    start_line: int
    end_line: int


@dataclass
class QualityIssue:
    """单条质量问题"""
    severity: str      # 'error', 'warning', 'info'
    rule: str
    message: str
    line: int


@dataclass
class QualityReport:
    """代码质量报告"""
    file_path: str
    issues: List[QualityIssue]
    score: float       # 0–100
    suggestions: List[str]
    metrics: Dict[str, Any]


# ──────────────────────────────────────────────
#  Claude AI 客户端（直接调用 Anthropic API）
# ──────────────────────────────────────────────

class ClaudeClient:
    """轻量级 Anthropic API 客户端（无需第三方 SDK）"""

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL   = "claude-sonnet-4-20250514"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            logger.warning("未设置 ANTHROPIC_API_KEY，AI 增强功能将被跳过。")

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """发送单轮对话请求，返回文本内容"""
        if not self.api_key:
            return ""

        payload = json.dumps({
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            return ""


# ──────────────────────────────────────────────
#  代码分析器
# ──────────────────────────────────────────────

class AdvancedCodeAnalyzer:
    """高级代码分析器"""

    def __init__(self):
        self.elements: List[CodeElement] = []
        self.dependencies: Dict[str, List[str]] = {}

    # ── 项目级分析 ──────────────────────────────

    def analyze_project(self, project_path: Path) -> Tuple[List[CodeElement], Dict[str, List[str]]]:
        """分析整个项目，返回所有代码元素及依赖关系"""
        all_elements: List[CodeElement] = []

        for py_file in sorted(project_path.rglob("*.py")):
            logger.info(f"分析文件: {py_file}")
            all_elements.extend(self.analyze_file(py_file))

        dependencies = self._build_dependencies(all_elements)
        return all_elements, dependencies

    # ── 文件级分析 ──────────────────────────────

    def analyze_file(self, file_path: Path) -> List[CodeElement]:
        """分析单个 Python 文件"""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except Exception as e:
            logger.error(f"分析文件 {file_path} 时出错: {e}")
            return []

        elements: List[CodeElement] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                el = self._analyze_function(node, content, str(file_path))
            elif isinstance(node, ast.AsyncFunctionDef):
                el = self._analyze_function(node, content, str(file_path), is_async=True)
            elif isinstance(node, ast.ClassDef):
                el = self._analyze_class(node, content, str(file_path))
            else:
                continue
            if el:
                elements.append(el)

        return elements

    # ── 节点分析 ────────────────────────────────

    def _analyze_function(
        self,
        node: ast.AST,
        content: str,
        file_path: str,
        is_async: bool = False,
    ) -> Optional[CodeElement]:
        start_line = node.lineno - 1
        end_line   = getattr(node, "end_lineno", start_line)

        docstring  = ast.get_docstring(node) or ""
        args       = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
        returns    = self._extract_return_info(node, docstring)
        complexity = self._calculate_cyclomatic_complexity(node)

        return CodeElement(
            name       = f"async {node.name}" if is_async else node.name,
            type       = "function",
            docstring  = docstring,
            params     = args,
            returns    = returns,
            complexity = complexity,
            line_count = end_line - start_line + 1,
            file_path  = file_path,
            start_line = start_line,
            end_line   = end_line,
        )

    def _analyze_class(self, node: ast.ClassDef, content: str, file_path: str) -> Optional[CodeElement]:
        docstring = ast.get_docstring(node) or ""
        methods   = [
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        return CodeElement(
            name       = node.name,
            type       = "class",
            docstring  = docstring,
            params     = methods,
            returns    = "",
            complexity = len(methods),
            line_count = getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
            file_path  = file_path,
            start_line = node.lineno - 1,
            end_line   = getattr(node, "end_lineno", node.lineno) - 1,
        )

    # ── 辅助计算 ────────────────────────────────

    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Assert, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _extract_return_info(self, node: ast.AST, docstring: str) -> str:
        # 优先从类型注解获取
        if hasattr(node, "returns") and node.returns:
            try:
                return ast.unparse(node.returns)
            except Exception:
                pass

        # 从 docstring 中匹配
        for pattern in [
            r"@return\s+(.+)",
            r":returns?:\s+(.+)",
            r"Returns:\s+(.+?)(?=\n\S|\Z)",
        ]:
            m = re.search(pattern, docstring, re.MULTILINE | re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return ""

    def _build_dependencies(self, elements: List[CodeElement]) -> Dict[str, List[str]]:
        """基于 import 语句构建文件依赖关系"""
        deps: Dict[str, List[str]] = {e.file_path: [] for e in elements}
        file_paths = list(deps.keys())

        for fp in file_paths:
            try:
                content = Path(fp).read_text(encoding="utf-8")
                tree = ast.parse(content)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        module_hint = node.module.replace(".", "/")
                        for other_fp in file_paths:
                            if other_fp != fp and module_hint in other_fp.replace("\\", "/"):
                                if other_fp not in deps[fp]:
                                    deps[fp].append(other_fp)

        return deps


# ──────────────────────────────────────────────
#  代码质量审查器
# ──────────────────────────────────────────────

class CodeQualityReviewer:
    """基于规则 + AI 的代码质量审查器"""

    # 规则阈值
    MAX_COMPLEXITY   = 10
    MAX_LINES        = 50
    MAX_PARAMS       = 5

    def __init__(self, claude: Optional[ClaudeClient] = None):
        self.claude = claude

    def review_elements(self, elements: List[CodeElement]) -> List[QualityReport]:
        """对所有代码元素按文件汇总生成质量报告"""
        files: Dict[str, List[CodeElement]] = {}
        for el in elements:
            files.setdefault(el.file_path, []).append(el)

        return [self._review_file(fp, els) for fp, els in files.items()]

    def _review_file(self, file_path: str, elements: List[CodeElement]) -> QualityReport:
        issues: List[QualityIssue] = []
        suggestions: List[str] = []

        for el in elements:
            issues.extend(self._lint_element(el))

        # AI 增强建议
        if self.claude:
            ai_suggestions = self._ai_review(elements)
            suggestions.extend(ai_suggestions)

        score = self._compute_score(issues, elements)

        metrics = {
            "total_elements"   : len(elements),
            "functions"        : sum(1 for e in elements if e.type == "function"),
            "classes"          : sum(1 for e in elements if e.type == "class"),
            "avg_complexity"   : (
                sum(e.complexity for e in elements if e.type == "function") /
                max(1, sum(1 for e in elements if e.type == "function"))
            ),
            "missing_docstrings": sum(1 for e in elements if not e.docstring),
        }

        return QualityReport(
            file_path   = file_path,
            issues      = issues,
            score       = score,
            suggestions = suggestions,
            metrics     = metrics,
        )

    def _lint_element(self, el: CodeElement) -> List[QualityIssue]:
        issues: List[QualityIssue] = []
        line = el.start_line + 1

        if not el.docstring:
            issues.append(QualityIssue(
                severity="warning",
                rule="missing-docstring",
                message=f"{el.type} `{el.name}` 缺少文档注释",
                line=line,
            ))

        if el.type == "function":
            if el.complexity > self.MAX_COMPLEXITY:
                issues.append(QualityIssue(
                    severity="error",
                    rule="high-complexity",
                    message=f"`{el.name}` 圈复杂度为 {el.complexity}，超过阈值 {self.MAX_COMPLEXITY}，建议拆分",
                    line=line,
                ))
            if el.line_count > self.MAX_LINES:
                issues.append(QualityIssue(
                    severity="warning",
                    rule="long-function",
                    message=f"`{el.name}` 共 {el.line_count} 行，建议保持在 {self.MAX_LINES} 行以内",
                    line=line,
                ))
            if len(el.params) > self.MAX_PARAMS:
                issues.append(QualityIssue(
                    severity="warning",
                    rule="too-many-params",
                    message=f"`{el.name}` 有 {len(el.params)} 个参数，建议使用数据类或配置对象聚合",
                    line=line,
                ))

        return issues

    def _ai_review(self, elements: List[CodeElement]) -> List[str]:
        """用 Claude 对当前文件整体给出改进建议"""
        summary = "\n".join(
            f"- [{el.type}] {el.name}  复杂度={el.complexity}  行数={el.line_count}  "
            f"参数={el.params}  有文档={'是' if el.docstring else '否'}"
            for el in elements
        )
        prompt = (
            "以下是一个 Python 文件的代码元素摘要，请给出 3–5 条具体的改进建议，"
            "用中文简洁回答，每条建议单独一行，以'- '开头：\n\n" + summary
        )
        raw = self.claude.complete(prompt, max_tokens=600)
        return [line.strip() for line in raw.splitlines() if line.strip().startswith("-")]

    def _compute_score(self, issues: List[QualityIssue], elements: List[CodeElement]) -> float:
        """根据问题数量和严重程度计算综合评分"""
        score = 100.0
        score -= sum(10 for i in issues if i.severity == "error")
        score -= sum(5  for i in issues if i.severity == "warning")
        score -= sum(1  for i in issues if i.severity == "info")
        return max(0.0, min(100.0, score))


# ──────────────────────────────────────────────
#  文档生成器（含 AI 智能增强）
# ──────────────────────────────────────────────

class AdvancedDocumentationGenerator:
    """高级文档生成器"""

    def __init__(self, claude: Optional[ClaudeClient] = None):
        self.claude = claude

    # ── 对外主接口 ──────────────────────────────

    def generate_comprehensive_docs(
        self,
        elements: List[CodeElement],
        dependencies: Dict[str, List[str]],
        reports: List[QualityReport],
        output_path: Path,
    ):
        docs_dir = output_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        (docs_dir / "index.md").write_text(
            self._create_main_index(elements, dependencies, reports), encoding="utf-8"
        )
        self._generate_file_specific_docs(elements, docs_dir)
        self._generate_dependency_diagram(dependencies, docs_dir / "dependencies.md")
        self._generate_quality_report_doc(reports, docs_dir / "quality_report.md")

        logger.info(f"✅ 文档已生成到: {docs_dir}")

    # ── 主索引 ──────────────────────────────────

    def _create_main_index(
        self,
        elements: List[CodeElement],
        dependencies: Dict[str, List[str]],
        reports: List[QualityReport],
    ) -> str:
        unique_files = sorted(set(e.file_path for e in elements))
        avg_score = (sum(r.score for r in reports) / len(reports)) if reports else 0

        lines = [
            "# 项目代码文档\n",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**分析文件数**: {len(unique_files)}  ",
            f"**代码元素总数**: {len(elements)}  ",
            f"**综合质量评分**: {avg_score:.1f} / 100  \n",
            "## 快速导航\n",
            "- [依赖关系图](dependencies.md)",
            "- [质量报告](quality_report.md)\n",
            "## 文件列表\n",
        ]

        for fp in unique_files:
            file_els = [e for e in elements if e.file_path == fp]
            fn_count  = sum(1 for e in file_els if e.type == "function")
            cls_count = sum(1 for e in file_els if e.type == "class")
            link = self._filename_for_link(fp)
            lines.append(f"- [{Path(fp).name}]({link}) — {fn_count} 函数 / {cls_count} 类")

        lines.append("\n## 代码元素详情\n")

        for fp in unique_files:
            file_els = [e for e in elements if e.file_path == fp]
            lines.append(f"### `{Path(fp).name}`\n")

            funcs = [e for e in file_els if e.type == "function"]
            if funcs:
                lines.append("#### 函数\n")
                lines.extend(self._format_function_doc(f) for f in funcs)

            classes = [e for e in file_els if e.type == "class"]
            if classes:
                lines.append("#### 类\n")
                lines.extend(self._format_class_doc(c) for c in classes)

            lines.append("---\n")

        return "\n".join(lines)

    # ── 单文件文档 ──────────────────────────────

    def _generate_file_specific_docs(self, elements: List[CodeElement], docs_dir: Path):
        for fp in set(e.file_path for e in elements):
            file_els = [e for e in elements if e.file_path == fp]
            lines = [f"# {Path(fp).name}\n"]

            # AI 摘要
            if self.claude:
                summary = self._ai_summarize_file(file_els)
                if summary:
                    lines += ["## 模块简介\n", summary, ""]

            funcs = [e for e in file_els if e.type == "function"]
            if funcs:
                lines.append("## 函数\n")
                lines.extend(self._format_function_doc(f) for f in funcs)

            classes = [e for e in file_els if e.type == "class"]
            if classes:
                lines.append("## 类\n")
                lines.extend(self._format_class_doc(c) for c in classes)

            out_file = docs_dir / self._filename_for_link(fp)
            out_file.write_text("\n".join(lines), encoding="utf-8")

    # ── 依赖关系图（Mermaid）──────────────────────

    def _generate_dependency_diagram(self, dependencies: Dict[str, List[str]], output_path: Path):
        lines = [
            "# 文件依赖关系图\n",
            "```mermaid",
            "graph TD",
        ]

        # 为每个文件路径建立短标签
        label: Dict[str, str] = {}
        for fp in dependencies:
            safe = Path(fp).stem.replace("-", "_").replace(" ", "_")
            label[fp] = safe

        has_edge = False
        for fp, deps in dependencies.items():
            for dep in deps:
                src = label.get(fp,  Path(fp).stem)
                dst = label.get(dep, Path(dep).stem)
                lines.append(f'    {src}["{Path(fp).name}"] --> {dst}["{Path(dep).name}"]')
                has_edge = True

        if not has_edge:
            lines.append('    A["（未检测到跨文件依赖）"]')

        lines += ["```\n"]
        output_path.write_text("\n".join(lines), encoding="utf-8")

    # ── 质量报告文档 ─────────────────────────────

    def _generate_quality_report_doc(self, reports: List[QualityReport], output_path: Path):
        lines = [
            "# 代码质量报告\n",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "| 文件 | 评分 | 错误 | 警告 | 均复杂度 | 缺注释 |",
            "|---|---|---|---|---|---|",
        ]

        for r in sorted(reports, key=lambda x: x.score):
            errors   = sum(1 for i in r.issues if i.severity == "error")
            warnings = sum(1 for i in r.issues if i.severity == "warning")
            lines.append(
                f"| `{Path(r.file_path).name}` "
                f"| {r.score:.0f} "
                f"| {errors} "
                f"| {warnings} "
                f"| {r.metrics.get('avg_complexity', 0):.1f} "
                f"| {r.metrics.get('missing_docstrings', 0)} |"
            )

        lines.append("")

        for r in reports:
            if not r.issues and not r.suggestions:
                continue
            lines.append(f"## `{Path(r.file_path).name}`\n")

            if r.issues:
                lines.append("### 发现的问题\n")
                for issue in r.issues:
                    icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                    lines.append(f"- {icon} **第 {issue.line} 行** [{issue.rule}] {issue.message}")
                lines.append("")

            if r.suggestions:
                lines.append("### AI 改进建议\n")
                lines.extend(r.suggestions)
                lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")

    # ── 格式化工具 ──────────────────────────────

    def _format_function_doc(self, func: CodeElement) -> str:
        params_str = ", ".join(func.params) if func.params else "无"
        complexity_tag = (
            "🔴 高" if func.complexity > 10
            else "🟡 中" if func.complexity > 5
            else "🟢 低"
        )
        return (
            f"##### `{func.name}({params_str})`\n\n"
            f"{func.docstring or '*暂无文档注释*'}\n\n"
            f"| 返回值 | 复杂度 | 行数 | 位置 |\n"
            f"|---|---|---|---|\n"
            f"| `{func.returns or 'None'}` | {complexity_tag} ({func.complexity}) "
            f"| {func.line_count} | 第 {func.start_line+1}–{func.end_line+1} 行 |\n\n"
        )

    def _format_class_doc(self, cls: CodeElement) -> str:
        methods_str = ", ".join(f"`{m}`" for m in cls.params) if cls.params else "无"
        return (
            f"##### `{cls.name}`\n\n"
            f"{cls.docstring or '*暂无文档注释*'}\n\n"
            f"**方法**: {methods_str}  \n"
            f"**行数**: {cls.line_count} | **位置**: 第 {cls.start_line+1}–{cls.end_line+1} 行\n\n"
        )

    # ── AI 辅助 ─────────────────────────────────

    def _ai_summarize_file(self, elements: List[CodeElement]) -> str:
        """用 Claude 生成一段模块功能摘要"""
        names = [f"{e.type} {e.name}" for e in elements[:15]]
        prompt = (
            "以下是一个 Python 模块包含的代码元素，请用 2–3 句中文简要说明这个模块的主要功能和用途：\n\n"
            + "\n".join(names)
        )
        return self.claude.complete(prompt, max_tokens=300)

    # ── 路径工具 ────────────────────────────────

    @staticmethod
    def _filename_for_link(file_path: str) -> str:
        """将任意文件路径转换为安全的 Markdown 文件名"""
        name = Path(file_path).stem
        safe = re.sub(r"[^\w\-]", "_", name)
        return f"{safe}.md"


# ──────────────────────────────────────────────
#  主程序入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="智能代码文档生成与审查系统 V2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析当前目录，输出到 ./output
  python code_doc_system.py .

  # 指定输出路径并启用 AI 增强（需要设置 ANTHROPIC_API_KEY）
  python code_doc_system.py ./my_project --output ./my_docs

  # 仅生成质量报告，不写文档
  python code_doc_system.py . --report-only
        """,
    )
    parser.add_argument("project_path", help="要分析的项目根目录")
    parser.add_argument("--output", default="./output", help="文档输出目录（默认 ./output）")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 增强功能")
    parser.add_argument("--report-only", action="store_true", help="仅输出质量报告到控制台")
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()
    output_path  = Path(args.output).resolve()

    if not project_path.exists():
        logger.error(f"路径不存在: {project_path}")
        return

    # 初始化 AI 客户端
    claude = None if args.no_ai else ClaudeClient()

    # 1. 代码分析
    logger.info("🔍 开始分析代码...")
    analyzer = AdvancedCodeAnalyzer()
    elements, dependencies = analyzer.analyze_project(project_path)
    logger.info(f"共发现 {len(elements)} 个代码元素")

    # 2. 质量审查
    logger.info("📋 开始质量审查...")
    reviewer = CodeQualityReviewer(claude=claude)
    reports  = reviewer.review_elements(elements)

    # 仅报告模式：打印到控制台
    if args.report_only:
        for r in reports:
            print(f"\n{'='*60}")
            print(f"文件: {r.file_path}")
            print(f"评分: {r.score:.1f}/100")
            for issue in r.issues:
                print(f"  [{issue.severity.upper()}] 第{issue.line}行: {issue.message}")
            for s in r.suggestions:
                print(f"  💡 {s}")
        return

    # 3. 文档生成
    logger.info("📝 开始生成文档...")
    generator = AdvancedDocumentationGenerator(claude=claude)
    generator.generate_comprehensive_docs(elements, dependencies, reports, output_path)

    # 4. 打印汇总
    print("\n" + "="*60)
    print("📊 质量汇总")
    print("="*60)
    for r in sorted(reports, key=lambda x: x.score):
        bar_len = int(r.score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"{Path(r.file_path).name:<30} {bar} {r.score:.0f}/100")
    print("="*60)
    print(f"📁 文档路径: {output_path / 'docs'}")


if __name__ == "__main__":
    main()
