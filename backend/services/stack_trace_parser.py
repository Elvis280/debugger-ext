"""
services/stack_trace_parser.py
──────────────────────────────
Parses Python stderr / traceback output into structured data.

Design decisions:
- We extract the DEEPEST frame because that is the actual crash site,
  not the entry point that triggered the chain.
- The function name is OPTIONAL in the frame regex so that SyntaxErrors
  (which don't include ", in <func>") are handled correctly.
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
    file:       str   # absolute or relative path as reported by Python
    line:       int   # 1-indexed line number
    function:   str   # enclosing function, '<module>', or '<unknown>'
    error_type: str   # e.g. 'ZeroDivisionError', 'SyntaxError'
    message:    str   # e.g. 'division by zero'


# ── Regex patterns ────────────────────────────────────────────────────────────

# Matches every "  File ..., line N[, in func]" line in a traceback.
# The ", in <func>" part is OPTIONAL so SyntaxErrors are handled correctly:
#   Runtime error:  File "app.py", line 6, in calculate_ratio
#   SyntaxError:    File "app.py", line 6
_FRAME_RE = re.compile(
    r'File "(?P<file>[^"]+)",\s*line\s+(?P<line>\d+)'
    r'(?:,\s*in\s+(?P<func>\S+))?'       # optional ", in <funcname>"
)

# Matches the final exception line, e.g.:
#   ZeroDivisionError: division by zero
#   SyntaxError: invalid syntax
_EXCEPTION_RE = re.compile(
    r'^(?P<type>[A-Za-z][A-Za-z0-9_]*'
    r'(?:Error|Exception|Warning|KeyboardInterrupt|'
    r'SystemExit|GeneratorExit|StopIteration|'
    r'StopAsyncIteration|BaseException|SyntaxError))'
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
    # Normalise Windows CRLF → LF so anchors work consistently
    stack_trace = stack_trace.replace('\r\n', '\n').replace('\r', '\n')

    print(f"[StackTraceParser] Parsing traceback ({len(stack_trace)} chars)")
    print(f"[StackTraceParser] First 300 chars: {repr(stack_trace[:300])}")

    # Collect every frame; the last one is the crash site
    frames = _FRAME_RE.findall(stack_trace)

    if not frames:
        print("[StackTraceParser] No stack frames found — input may not be a Python traceback")
        log.warning("No stack frames found in input (first 200 chars): %r", stack_trace[:200])
        return None

    # frames = list of (file, line, func) tuples — func may be '' for SyntaxErrors
    file_path, line_str, func = frames[-1]
    func = func.strip() if func else "<unknown>"
    print(f"[StackTraceParser] Deepest frame: {file_path}:{line_str} in {func}")

    # Extract the exception type and message
    exc_match = _EXCEPTION_RE.search(stack_trace)
    if exc_match:
        error_type = exc_match.group("type")
        message    = exc_match.group("msg").strip()
        print(f"[StackTraceParser] Detected exception: {error_type}: {message}")
    else:
        # Last line of the traceback often contains the exception even if
        # the regex didn't match — grab whatever is after the last frame
        last_line = stack_trace.strip().splitlines()[-1].strip()
        if ':' in last_line:
            error_type, _, message = last_line.partition(':')
            error_type = error_type.strip()
            message    = message.strip()
        else:
            error_type = "RuntimeError"
            message    = last_line or "Unknown runtime error"
        print(f"[StackTraceParser] Fallback exception detection: {error_type}: {message}")
        log.warning("Exception type regex did not match — using fallback: %s", error_type)

    result = ParsedError(
        file=file_path,
        line=int(line_str),
        function=func,
        error_type=error_type,
        message=message,
    )
    log.info("Parsed: %s at %s:%s in '%s'", error_type, file_path, line_str, func)
    return result
