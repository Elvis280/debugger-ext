"""
services/stack_trace_parser.py
──────────────────────────────
Parses Python stderr / traceback output into structured data.

Design decisions:
- We extract the DEEPEST frame because that is the actual crash site,
  not the entry point that triggered the chain.
- The exception regex covers both *Error and base classes so we never
  fall through to a generic "RuntimeError" for common exceptions.
- Returns None (not raises) so callers can gracefully handle bad input.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ParsedError:
    """Structured representation of the deepest frame in a Python traceback."""
    file: str       # absolute or relative path as reported by Python
    line: int       # 1-indexed line number
    function: str   # enclosing function / '<module>' for top-level code
    error_type: str # e.g. 'ZeroDivisionError'
    message: str    # e.g. 'division by zero'


# ── Regex patterns ────────────────────────────────────────────────────────────

# Matches every "  File ..., line N, in func" line in a traceback.
# DOTALL not needed; we scan line-by-line via findall.
_FRAME_RE = re.compile(
    r'File "(?P<file>[^"]+)",\s+line\s+(?P<line>\d+),\s+in\s+(?P<func>\S+)'
)

# Matches the final exception line.  Covers all standard exception families.
_EXCEPTION_RE = re.compile(
    r'^(?P<type>[A-Za-z][A-Za-z0-9_]*'
    r'(?:Error|Exception|Warning|KeyboardInterrupt|'
    r'SystemExit|GeneratorExit|StopIteration|'
    r'StopAsyncIteration|BaseException))'
    r':\s*(?P<msg>.*)$',
    re.MULTILINE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def parse(stack_trace: str) -> Optional[ParsedError]:
    """
    Parse a Python traceback string and return the deepest ParsedError.

    Returns None when the input does not contain a recognisable traceback
    so the caller can surface a user-friendly error instead of crashing.
    """
    print(f"[StackTraceParser] Parsing traceback ({len(stack_trace)} chars)")

    # Collect every frame; the last one is the crash site
    frames = _FRAME_RE.findall(stack_trace)

    if not frames:
        print("[StackTraceParser] No stack frames found — not a Python traceback")
        log.warning("No stack frames found in input.")
        return None

    # frames = list of (file, line, func) tuples
    file_path, line_str, func = frames[-1]
    print(f"[StackTraceParser] Deepest frame: {file_path}:{line_str} in {func}")

    # Extract the exception type and message
    exc_match = _EXCEPTION_RE.search(stack_trace)
    if exc_match:
        error_type = exc_match.group("type")
        message    = exc_match.group("msg").strip()
        print(f"[StackTraceParser] Detected exception: {error_type}: {message}")
    else:
        error_type = "RuntimeError"
        message    = "Unknown runtime error"
        print("[StackTraceParser] Could not detect exception type; using RuntimeError")
        log.warning("Exception type not detected; defaulting to RuntimeError.")

    result = ParsedError(
        file=file_path,
        line=int(line_str),
        function=func,
        error_type=error_type,
        message=message,
    )
    log.info("Parsed: %s at %s:%s in %s", error_type, file_path, line_str, func)
    return result
