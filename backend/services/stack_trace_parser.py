"""
services/stack_trace_parser.py

Parses Python stderr / stack trace output into structured data.
Extracts the DEEPEST frame (closest to the actual error site).
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedError:
    file: str
    line: int
    function: str
    error_type: str
    message: str


# Matches:   File "/path/to/file.py", line 42, in my_function
_FRAME_RE = re.compile(
    r'File "(?P<file>[^"]+)",\s+line\s+(?P<line>\d+),\s+in\s+(?P<func>\S+)'
)

# Matches the final exception line:   ZeroDivisionError: division by zero
_EXCEPTION_RE = re.compile(
    r'^(?P<type>[A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|KeyboardInterrupt|'
    r'SystemExit|GeneratorExit|StopIteration|StopAsyncIteration|BaseException))'
    r':\s*(?P<msg>.*)$',
    re.MULTILINE,
)


def parse(stack_trace: str) -> Optional[ParsedError]:
    """
    Returns the deepest ParsedError from a Python traceback, or None
    if the string cannot be parsed as a Python traceback.
    """
    frames = _FRAME_RE.findall(stack_trace)

    if not frames:
        return None

    # last frame is deepest — closest to the actual error
    file_path, line_str, func = frames[-1]

    exc_match = _EXCEPTION_RE.search(stack_trace)
    if exc_match:
        error_type = exc_match.group("type")
        message = exc_match.group("msg").strip()
    else:
        error_type = "RuntimeError"
        message = "Unknown runtime error"

    return ParsedError(
        file=file_path,
        line=int(line_str),
        function=func,
        error_type=error_type,
        message=message,
    )
