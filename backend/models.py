"""
models.py
Pydantic schemas for the /analyze request and response.
"""

from typing import Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Payload sent by the VS Code extension to the backend."""

    stack_trace: str = Field(..., description="Full stderr / stack trace string")
    code_snippet: str = Field(..., description="Relevant code around the error line")
    file_path: str = Field(..., description="Absolute path to the file that raised the error")
    language: str = Field(default="python", description="Programming language")


class AnalyzeResponse(BaseModel):
    """Structured analysis result returned to the VS Code extension."""

    # Stack trace fields
    error_type: str
    file: str
    line: int
    function: str

    # AST fields
    node_type: Optional[str] = None
    expression: Optional[str] = None
    variables: list[str] = []

    # Root cause
    possible_cause: str

    # Code context
    code_snippet: str

    # AI fields (empty when AI is unavailable)
    explanation: str
    root_cause: str
    suggested_fix: str
    improved_code: str

    # Meta
    cached: bool = False
    language: str = "python"


class ErrorResponse(BaseModel):
    detail: str
