"""
services/root_cause_detector.py

Rule-based heuristics for common Python runtime errors.
No AI required — runs instantly and acts as a reliable fallback.
"""

from dataclasses import dataclass
from typing import Optional

from services.ast_analyzer import AstResult
from services.stack_trace_parser import ParsedError


@dataclass
class RootCauseResult:
    possible_cause: str
    hint: str = ""                  # short human hint for the AI prompt


_RULES: dict[str, callable] = {}   # populated below by @_rule decorator


def _rule(error_type: str):
    def decorator(fn):
        _RULES[error_type] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Per-error rules
# ---------------------------------------------------------------------------

@_rule("ZeroDivisionError")
def _zero_div(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    if ast.node_type == "BinOp" and ast.variables:
        denom = ast.variables[-1]          # right-hand operand is usually last
        return RootCauseResult(
            possible_cause=f"Denominator '{denom}' is zero during division in '{parsed.function}'.",
            hint=f"Add a guard: `if {denom} == 0: raise ValueError(...)` before the division.",
        )
    return RootCauseResult(
        possible_cause="A division by zero occurred.",
        hint="Ensure the divisor is never zero before performing division.",
    )


@_rule("IndexError")
def _index(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    if ast.node_type == "Subscript" and ast.variables:
        collection, *rest = ast.variables
        idx = rest[0] if rest else "index"
        return RootCauseResult(
            possible_cause=(
                f"Index '{idx}' is out of range for '{collection}' "
                f"in '{parsed.function}'."
            ),
            hint=f"Check `len({collection})` before accessing index `{idx}`.",
        )
    return RootCauseResult(
        possible_cause="List or sequence index is out of range.",
        hint="Validate the index against the collection length before access.",
    )


@_rule("AttributeError")
def _attr(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    if ast.node_type == "Attribute" and ast.variables:
        obj = ast.variables[0]
        attr = ast.expression.split(".")[-1] if ast.expression and "." in ast.expression else "attribute"
        return RootCauseResult(
            possible_cause=(
                f"Object '{obj}' is None or does not have attribute '{attr}'."
            ),
            hint=f"Check `if {obj} is not None` before accessing `.{attr}`.",
        )
    return RootCauseResult(
        possible_cause="An attribute was accessed on a None or unexpected object.",
        hint="Ensure the object is properly initialised before attribute access.",
    )


@_rule("NameError")
def _name(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    # The undefined name appears in the error message: "name 'x' is not defined"
    import re
    m = re.search(r"name '([^']+)' is not defined", parsed.message)
    var = m.group(1) if m else (ast.variables[0] if ast.variables else "variable")
    return RootCauseResult(
        possible_cause=f"Variable '{var}' is used before it is defined.",
        hint=f"Define '{var}' before use or check for typos in the name.",
    )


@_rule("TypeError")
def _type(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    return RootCauseResult(
        possible_cause=f"A type mismatch occurred: {parsed.message}",
        hint="Check the types of all operands and function arguments.",
    )


@_rule("KeyError")
def _key(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    import re
    m = re.search(r"KeyError:\s*(.+)", parsed.message)
    key = m.group(1).strip() if m else "the key"
    return RootCauseResult(
        possible_cause=f"Key {key} does not exist in the dictionary.",
        hint=f"Use `.get({key})` or check `if {key} in dict` before access.",
    )


@_rule("ValueError")
def _value(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    return RootCauseResult(
        possible_cause=f"Invalid value passed to a function: {parsed.message}",
        hint="Validate the input value before passing it to the function.",
    )


@_rule("RecursionError")
def _recursion(parsed: ParsedError, ast: AstResult) -> RootCauseResult:
    return RootCauseResult(
        possible_cause=f"The recursion depth exceeded Python's limit in '{parsed.function}'.",
        hint="Add a base case or convert the recursion to an iterative approach.",
    )


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def detect(parsed: ParsedError, ast_result: AstResult) -> RootCauseResult:
    handler = _RULES.get(parsed.error_type)
    if handler:
        return handler(parsed, ast_result)
    return RootCauseResult(
        possible_cause=f"{parsed.error_type}: {parsed.message}",
        hint="Review the error message and stack trace for more context.",
    )
