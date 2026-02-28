"""
services/error_context_builder.py
───────────────────────────────────
Assembles a single ErrorContext object from the outputs of all upstream
analysis steps.  This is the data contract between the analysis pipeline
and the AI engine / API response.

Having a single merge point makes it straightforward to:
- Add new analysis fields without touching the endpoint or AI engine.
- Log exactly what information is forwarded to Gemini.
- Unit-test the merge logic in isolation.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from services.stack_trace_parser import ParsedError
from services.ast_analyzer import AstResult
from services.root_cause_detector import RootCauseResult

log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ErrorContext:
    """
    Unified error context forwarded to the AI engine and returned
    (partially) in the API response.
    """
    # ── From stack trace parser ──
    error_type: str           # e.g. 'ZeroDivisionError'
    file:       str           # absolute path to the file
    line:       int           # 1-indexed error line
    function:   str           # enclosing function or '<module>'
    message:    str           # raw exception message

    # ── From AST analyser ───────
    node_type:  Optional[str]     # e.g. 'BinOp'
    expression: Optional[str]     # e.g. 'a / b'
    variables:  list[str]         # e.g. ['a', 'b']

    # ── From code context extractor (VS Code side) ──
    code_snippet: str             # annotated lines around the error

    # ── From root cause detector ──
    possible_cause: str           # human-readable probable cause
    hint:           str           # short actionable hint for AI prompt

    # ── Meta ──────────────────────
    cached: bool = False          # True when AST result came from cache


# ── Public API ────────────────────────────────────────────────────────────────

def build(
    parsed:     ParsedError,
    ast_result: AstResult,
    root_cause: RootCauseResult,
    code_snippet: str,
) -> ErrorContext:
    """
    Merge all upstream results into a single ErrorContext.

    Args:
        parsed:       Output of stack_trace_parser.parse()
        ast_result:   Output of ast_analyzer.analyse()
        root_cause:   Output of root_cause_detector.detect()
        code_snippet: Code lines extracted by the VS Code extension

    Returns:
        A fully populated ErrorContext ready for the AI engine.
    """
    ctx = ErrorContext(
        # Stack trace fields
        error_type = parsed.error_type,
        file       = parsed.file,
        line       = parsed.line,
        function   = parsed.function,
        message    = parsed.message,
        # AST fields
        node_type  = ast_result.node_type,
        expression = ast_result.expression,
        variables  = ast_result.variables,
        # Code
        code_snippet   = code_snippet,
        # Root cause
        possible_cause = root_cause.possible_cause,
        hint           = root_cause.hint,
        # Meta
        cached = ast_result.cached,
    )

    print(
        f"[ContextBuilder] Built ErrorContext: "
        f"{ctx.error_type} @ {ctx.file}:{ctx.line} "
        f"node={ctx.node_type} cached={ctx.cached}"
    )
    log.info(
        "ErrorContext built: %s at %s:%d (AST cached=%s)",
        ctx.error_type, ctx.file, ctx.line, ctx.cached,
    )

    return ctx
