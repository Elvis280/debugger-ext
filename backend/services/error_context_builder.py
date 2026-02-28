"""
services/error_context_builder.py

Merges parsed stack trace + AST result + root cause into the single
ErrorContext dict that gets sent to the AI engine and returned in the
API response.
"""

from dataclasses import dataclass, field
from typing import Optional

from services.stack_trace_parser import ParsedError
from services.ast_analyzer import AstResult
from services.root_cause_detector import RootCauseResult


@dataclass
class ErrorContext:
    # From stack trace
    error_type: str
    file: str
    line: int
    function: str
    message: str

    # From AST
    node_type: Optional[str]
    expression: Optional[str]
    variables: list[str]

    # Code
    code_snippet: str

    # Root cause
    possible_cause: str
    hint: str

    # Whether AST result came from cache
    cached: bool = False


def build(
    parsed: ParsedError,
    ast_result: AstResult,
    root_cause: RootCauseResult,
    code_snippet: str,
) -> ErrorContext:
    return ErrorContext(
        error_type=parsed.error_type,
        file=parsed.file,
        line=parsed.line,
        function=parsed.function,
        message=parsed.message,
        node_type=ast_result.node_type,
        expression=ast_result.expression,
        variables=ast_result.variables,
        code_snippet=code_snippet,
        possible_cause=root_cause.possible_cause,
        hint=root_cause.hint,
        cached=ast_result.cached,
    )
