"""
services/ast_analyzer.py

Uses Python's built-in `ast` module to analyse the source file at the
error line.  Results are placed into the shared diskcache so identical
(file, hash, line) triples are never re-analysed.
"""

import ast
import hashlib
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cache.ast_cache import get_cache


@dataclass
class AstResult:
    node_type: Optional[str] = None
    expression: Optional[str] = None
    function: Optional[str] = None
    klass: Optional[str] = None
    variables: list[str] = field(default_factory=list)
    cached: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(file_path: str, line: int) -> AstResult:
    """Return an AstResult for the given file and line number."""
    path = Path(file_path)
    if not path.exists():
        return AstResult()

    source = path.read_text(encoding="utf-8", errors="replace")
    file_hash = _sha256(source)

    cache = get_cache()
    cache_key = f"ast:{file_hash}:{line}"

    cached_val = cache.get(cache_key)
    if cached_val is not None:
        cached_val.cached = True
        return cached_val

    result = _do_analyse(source, line)
    cache.set(cache_key, result, expire=3600)   # 1-hour TTL
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class _NodeVisitor(ast.NodeVisitor):
    """Walk the AST and collect information about the node at target_line."""

    def __init__(self, target_line: int, source_lines: list[str]):
        self.target_line = target_line
        self.source_lines = source_lines
        self.result: AstResult = AstResult()
        self._func_stack: list[str] = []
        self._class_stack: list[str] = []

    # ---- scope tracking ------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef   # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef):
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    # ---- expression analysis -------------------------------------------

    def _check_line(self, node: ast.expr, node_type: str):
        if not hasattr(node, "lineno"):
            return
        if node.lineno != self.target_line:
            return

        self.result.node_type = node_type
        self.result.function = self._func_stack[-1] if self._func_stack else None
        self.result.klass = self._class_stack[-1] if self._class_stack else None

        # best-effort source extraction
        try:
            self.result.expression = ast.unparse(node)
        except Exception:
            idx = self.target_line - 1
            if 0 <= idx < len(self.source_lines):
                self.result.expression = self.source_lines[idx].strip()

        self.result.variables = _extract_names(node)

    def visit_BinOp(self, node: ast.BinOp):
        self._check_line(node, "BinOp")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        self._check_line(node, "Call")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        self._check_line(node, "Subscript")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        self._check_line(node, "Attribute")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        self._check_line(node, "Name")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        self._check_line(node, "Compare")
        self.generic_visit(node)


def _extract_names(node: ast.AST) -> list[str]:
    """Recursively collect all Name ids from an AST node."""
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.append(child.id)
    return list(dict.fromkeys(names))   # deduplicate while preserving order


def _do_analyse(source: str, target_line: int) -> AstResult:
    dedented = textwrap.dedent(source)
    try:
        tree = ast.parse(dedented, filename="<string>")
    except SyntaxError:
        return AstResult()

    source_lines = dedented.splitlines()
    visitor = _NodeVisitor(target_line, source_lines)
    visitor.visit(tree)
    return visitor.result
