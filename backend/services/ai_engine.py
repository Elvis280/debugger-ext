"""
services/ai_engine.py

Sends the structured ErrorContext to Google Gemini and returns a
plain-English explanation, root cause analysis, and a corrected code snippet.

Falls back to the rule-based `possible_cause` + `hint` when the API key is
missing, the API is unreachable, or any other error occurs.
"""

import os
import logging
from dataclasses import dataclass

import google.generativeai as genai

from services.error_context_builder import ErrorContext

log = logging.getLogger(__name__)


@dataclass
class AiResult:
    explanation: str
    root_cause: str
    suggested_fix: str
    improved_code: str
    ai_used: bool = True            # False when AI was unavailable


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(ctx: ErrorContext) -> str:
    vars_str = ", ".join(ctx.variables) if ctx.variables else "unknown"
    return f"""You are an expert Python debugger. Analyse the following runtime error and respond ONLY with a JSON object — no markdown fences, no extra text.

## Error Information
- **Error type**: {ctx.error_type}
- **Message**: {ctx.message}
- **File**: {ctx.file}  |  **Line**: {ctx.line}  |  **Function**: {ctx.function}

## AST Analysis
- **Node type**: {ctx.node_type or "unknown"}
- **Expression**: {ctx.expression or "unknown"}
- **Variables involved**: {vars_str}

## Rule-based diagnosis
{ctx.possible_cause}
Hint: {ctx.hint}

## Code snippet (error at line {ctx.line})
```python
{ctx.code_snippet}
```

Respond with this exact JSON structure:
{{
  "explanation": "<2–4 sentence plain-English explanation of why the error happened>",
  "root_cause": "<single sentence identifying the precise root cause>",
  "suggested_fix": "<concrete 1–3 step fix the developer should apply>",
  "improved_code": "<corrected Python code block, complete function if possible>"
}}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain(ctx: ErrorContext, api_key: str) -> AiResult:
    """
    Call Gemini.  If anything goes wrong, return a graceful fallback so
    the extension always has something useful to display.
    """
    if not api_key or api_key.strip() == "":
        log.warning("Gemini API key not configured — using rule-based fallback.")
        return _fallback(ctx)

    try:
        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content(
            _build_prompt(ctx),
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )

        raw = response.text.strip()
        return _parse_response(raw, ctx)

    except Exception as exc:
        log.error("Gemini call failed: %s", exc)
        return _fallback(ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_response(raw: str, ctx: ErrorContext) -> AiResult:
    import json, re

    # Strip any accidental markdown fences
    clean = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    clean = re.sub(r"\n?```$", "", clean, flags=re.MULTILINE).strip()

    try:
        data = json.loads(clean)
        return AiResult(
            explanation=data.get("explanation", ctx.possible_cause),
            root_cause=data.get("root_cause", ctx.possible_cause),
            suggested_fix=data.get("suggested_fix", ctx.hint),
            improved_code=data.get("improved_code", ""),
            ai_used=True,
        )
    except json.JSONDecodeError:
        log.warning("Could not parse Gemini JSON response — using fallback.")
        return _fallback(ctx)


def _fallback(ctx: ErrorContext) -> AiResult:
    return AiResult(
        explanation=ctx.possible_cause,
        root_cause=ctx.possible_cause,
        suggested_fix=ctx.hint,
        improved_code="",
        ai_used=False,
    )
