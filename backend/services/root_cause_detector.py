"""
services/root_cause_detector.py
────────────────────────────────
Rule-based heuristics that identify the probable cause of common Python
runtime errors WITHOUT needing an AI call.

Architecture:
- Each error type is handled by a dedicated `@_rule`-decorated function.
- The public `detect()` dispatcher looks up the handler by error type.
- If no rule matches, a generic fallback is returned.

This module runs in < 1 ms and acts as a reliable fallback when the AI
engine is unavailable, rate-limited, or not configured.
"""

import re
import logging
from dataclasses import dataclass

from services.ast_analyzer import AstResult
from services.stack_trace_parser import ParsedError

log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RootCauseResult:
    possible_cause: str   # concise human-readable cause statement
    hint: str = ""        # short actionable hint forwarded to the AI prompt


# ── Rule registry ─────────────────────────────────────────────────────────────

_RULES: dict = {}  # error_type (str) → handler (callable)


def _rule(error_type: str):
    """Decorator that registers a handler for a specific exception type."""
    def decorator(fn):
        _RULES[error_type] = fn
        return fn
    return decorator


# ── Per-error-type rules ──────────────────────────────────────────────────────

@_rule("ZeroDivisionError")
def _zero_div(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    """Division by zero — identify which variable is the denominator."""
    if ast.node_type == "BinOp" and ast.variables:
        # In a / b the right operand (denominator) is typically the last variable
        denom = ast.variables[-1]
        print(f"[RootCause] ZeroDivisionError — denominator is '{denom}'")
        return RootCauseResult(
            possible_cause=f"Denominator '{denom}' is zero during division in '{parsed.function}'.",
            hint=f"Add a guard: `if {denom} == 0: raise ValueError(...)` before the division.",
        )
    print("[RootCause] ZeroDivisionError — could not identify denominator from AST")
    return RootCauseResult(
        possible_cause="A division by zero occurred.",
        hint="Ensure the divisor is never zero before performing division.",
    )


@_rule("IndexError")
def _index(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    """List / sequence index out of range."""
    if ast.node_type == "Subscript" and ast.variables:
        collection, *rest = ast.variables
        idx = rest[0] if rest else "index"
        print(f"[RootCause] IndexError — '{idx}' out of range for '{collection}'")
        return RootCauseResult(
            possible_cause=f"Index '{idx}' is out of range for '{collection}' in '{parsed.function}'.",
            hint=f"Check `len({collection})` before accessing index `{idx}`.",
        )
    return RootCauseResult(
        possible_cause="List or sequence index is out of range.",
        hint="Validate the index against the collection length before access.",
    )


@_rule("AttributeError")
def _attr(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    """Attribute access on None or an unexpected type."""
    if ast.node_type == "Attribute" and ast.variables:
        obj  = ast.variables[0]
        attr = (ast.expression or "").split(".")[-1] or "attribute"
        print(f"[RootCause] AttributeError — '{obj}' may be None, missing '.{attr}'")
        return RootCauseResult(
            possible_cause=f"Object '{obj}' is None or does not have attribute '{attr}'.",
            hint=f"Check `if {obj} is not None` before accessing `.{attr}`.",
        )
    return RootCauseResult(
        possible_cause="An attribute was accessed on a None or unexpected object.",
        hint="Ensure the object is properly initialised before attribute access.",
    )


@_rule("NameError")
def _name(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    """Use of an undefined variable."""
    m   = re.search(r"name '([^']+)' is not defined", parsed.message)
    var = m.group(1) if m else (ast.variables[0] if ast.variables else "variable")
    print(f"[RootCause] NameError — variable '{var}' is undefined")
    return RootCauseResult(
        possible_cause=f"Variable '{var}' is used before it is defined.",
        hint=f"Define '{var}' before use or check for typos in the name.",
    )


@_rule("TypeError")
def _type(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    print(f"[RootCause] TypeError — {parsed.message}")
    return RootCauseResult(
        possible_cause=f"A type mismatch occurred: {parsed.message}",
        hint="Check the types of all operands and function arguments.",
    )


@_rule("KeyError")
def _key(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    m   = re.search(r"KeyError:\s*(.+)", parsed.message)
    key = m.group(1).strip() if m else "the key"
    print(f"[RootCause] KeyError — key {key} missing from dict")
    return RootCauseResult(
        possible_cause=f"Key {key} does not exist in the dictionary.",
        hint=f"Use `.get({key})` or check `if {key} in dict` before access.",
    )


@_rule("ValueError")
def _value(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    print(f"[RootCause] ValueError — {parsed.message}")
    return RootCauseResult(
        possible_cause=f"Invalid value passed to a function: {parsed.message}",
        hint="Validate the input value before passing it to the function.",
    )


@_rule("RecursionError")
def _recursion(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    print(f"[RootCause] RecursionError in '{parsed.function}'")
    return RootCauseResult(
        possible_cause=f"The recursion depth exceeded Python's limit in '{parsed.function}'.",
        hint="Add a base case or convert the recursion to an iterative approach.",
    )


# ── Public dispatcher ─────────────────────────────────────────────────────────

def detect(parsed: ParsedError, ast_result: AstResult) -> RootCauseResult:
    """
    Look up and call the rule for the given error type.
    Falls back to a generic message when no specific rule exists.
    """
    handler = _RULES.get(parsed.error_type)

    if handler:
        log.info("Root cause rule matched for %s", parsed.error_type)
        return handler(parsed, ast_result)

    # Generic fallback — still better than nothing
    print(f"[RootCause] No specific rule for {parsed.error_type} — using generic fallback")
    log.warning("No specific rule for %s", parsed.error_type)
    return RootCauseResult(
        possible_cause=f"{parsed.error_type}: {parsed.message}",
        hint="Review the error message and stack trace for more context.",
    )
