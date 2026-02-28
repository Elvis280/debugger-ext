"""
services/ast_analyzer.py
─────────────────────────
Uses Python's built-in `ast` module to inspect the source file at the
error line and extract structured information about the failing expression.

Key design points:
- Results are cached by (file_path, sha256_hash, line) using diskcache.
  Re-analysing an unchanged file is essentially free (~0 ms).
- The NodeVisitor walks the full AST but only records information for
  nodes whose lineno matches the target line.
- `ast.unparse()` reconstructs the source expression from the AST node,
  giving us the exact expression string (e.g. "a / b") without regex hacks.
- Graceful degradation: if the file cannot be read or parsed, we return
  an empty AstResult rather than raising an exception.
"""

import ast
import hashlib
import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cache.ast_cache import get_cache

log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class AstResult:
    """Structured AST information about the expression at the error line."""
    node_type:  Optional[str]  = None   # e.g. 'BinOp', 'Subscript', 'Call'
    expression: Optional[str]  = None   # e.g. 'a / b'
    function:   Optional[str]  = None   # enclosing function name
    klass:      Optional[str]  = None   # enclosing class name (if any)
    variables:  list[str]      = field(default_factory=list)  # Name ids found
    cached:     bool           = False  # True when result came from cache


# ── Public API ────────────────────────────────────────────────────────────────

def analyse(file_path: str, line: int) -> AstResult:
    """
    Return an AstResult for the given file and line number.

    Flow:
      1. Read the file and compute a SHA-256 hash of its content.
      2. Check the disk cache — return cached result if hit.
      3. Parse the AST and walk to find the node at `line`.
      4. Store result in cache and return.
    """
    path = Path(file_path)

    if not path.exists():
        print(f"[AstAnalyzer] File not found: {file_path} — skipping AST analysis")
        log.warning("File not found: %s", file_path)
        return AstResult()

    print(f"[AstAnalyzer] Reading file: {file_path}")
    source    = path.read_text(encoding="utf-8", errors="replace")
    file_hash = _sha256(source)
    cache_key = f"ast:{file_hash}:{line}"

    # ── Cache lookup ──────────────────────────────────────────────────────────
    cache      = get_cache()
    cached_val = cache.get(cache_key)

    if cached_val is not None:
        cached_val.cached = True
        print(f"[AstAnalyzer] Cache HIT for line {line} (hash={file_hash[:8]}...)")
        log.info("AST cache hit for %s line %d", file_path, line)
        return cached_val

    print(f"[AstAnalyzer] Cache MISS — parsing AST for line {line}")
    log.info("AST cache miss for %s line %d — running analyser", file_path, line)

    # ── Full AST analysis ─────────────────────────────────────────────────────
    result = _do_analyse(source, line)

    # Store in cache with 1-hour TTL
    cache.set(cache_key, result, expire=3600)
    print(f"[AstAnalyzer] Result cached: node_type={result.node_type} expr='{result.expression}'")
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    """Compute a stable cache key from file content."""
    return hashlib.sha256(text.encode()).hexdigest()


class _NodeVisitor(ast.NodeVisitor):
    """
    AST visitor that records the first interesting expression node found
    at `target_line`, along with scope context (function / class).
    """

    def __init__(self, target_line: int, source_lines: list[str]):
        self.target_line  = target_line
        self.source_lines = source_lines
        self.result       = AstResult()
        # Stacks track the current enclosing scope as we walk the tree
        self._func_stack:  list[str] = []
        self._class_stack: list[str] = []

    # ── Scope tracking ────────────────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    # AsyncFunctionDef has same structure as FunctionDef
    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef):
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    # ── Expression analysis ───────────────────────────────────────────────────

    def _check_line(self, node: ast.expr, node_type: str):
        """
        If this node is on the target line, record its type, expression
        string, enclosing scope, and all variable names it references.
        """
        if not hasattr(node, "lineno") or node.lineno != self.target_line:
            return

        self.result.node_type = node_type
        self.result.function  = self._func_stack[-1]  if self._func_stack  else None
        self.result.klass     = self._class_stack[-1] if self._class_stack else None

        # Reconstruct the expression text from the AST node
        try:
            self.result.expression = ast.unparse(node)
        except Exception:
            # Fallback: use raw source line
            idx = self.target_line - 1
            if 0 <= idx < len(self.source_lines):
                self.result.expression = self.source_lines[idx].strip()

        self.result.variables = _extract_names(node)

    # Visit the expression types we care about most
    def visit_BinOp(self,    node): self._check_line(node, "BinOp");    self.generic_visit(node)
    def visit_Call(self,     node): self._check_line(node, "Call");     self.generic_visit(node)
    def visit_Subscript(self,node): self._check_line(node, "Subscript");self.generic_visit(node)
    def visit_Attribute(self,node): self._check_line(node, "Attribute");self.generic_visit(node)
    def visit_Name(self,     node): self._check_line(node, "Name");     self.generic_visit(node)
    def visit_Compare(self,  node): self._check_line(node, "Compare");  self.generic_visit(node)


def _extract_names(node: ast.AST) -> list[str]:
    """Recursively collect all Name.id values from an AST subtree (deduplicated)."""
    names = [child.id for child in ast.walk(node) if isinstance(child, ast.Name)]
    return list(dict.fromkeys(names))  # deduplicate while preserving order


def _do_analyse(source: str, target_line: int) -> AstResult:
    """
    Dedent the source (handles indented code blocks), parse it, and
    run the NodeVisitor to find the expression at target_line.
    """
    dedented     = textwrap.dedent(source)
    source_lines = dedented.splitlines()

    try:
        tree = ast.parse(dedented, filename="<string>")
    except SyntaxError as exc:
        print(f"[AstAnalyzer] SyntaxError while parsing file: {exc}")
        log.error("SyntaxError during AST parse: %s", exc)
        return AstResult()

    visitor = _NodeVisitor(target_line, source_lines)
    visitor.visit(tree)

    if visitor.result.node_type:
        print(f"[AstAnalyzer] Found node '{visitor.result.node_type}' "
              f"expr='{visitor.result.expression}' "
              f"vars={visitor.result.variables}")
    else:
        print(f"[AstAnalyzer] No expression node found at line {target_line}")

    return visitor.result
