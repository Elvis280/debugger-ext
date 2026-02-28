"""
services/ai_engine.py
──────────────────────
Sends the structured ErrorContext to Google Gemini and returns a
plain-English explanation, root-cause analysis, and corrected code.

Prompt strategy:
- We send STRUCTURED context rather than raw error text.  This gives
  Gemini precise information (node type, variables, rule-based cause)
  so it can produce targeted, accurate explanations.
- The model is asked to respond in strict JSON — no markdown fences.
- If anything goes wrong (no key, rate limit, network error, bad JSON)
  this module returns a graceful fallback built from the rule-based
  possible_cause / hint fields so the UI always has something to show.
"""

import os
import json
import re
import logging
from dataclasses import dataclass

import google.generativeai as genai

from services.error_context_builder import ErrorContext

log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class AiResult:
    explanation:   str           # 2-4 sentence human explanation
    root_cause:    str           # single-sentence root cause
    suggested_fix: str           # 1-3 step fix
    improved_code: str           # corrected code block
    ai_used:       bool = True   # False when AI was unavailable / fallback used


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(ctx: ErrorContext) -> str:
    """
    Build a structured prompt from the ErrorContext.
    Providing structured input (not just raw traceback) lets the model
    reason about the specific expression and variables involved.
    """
    vars_str = ", ".join(ctx.variables) if ctx.variables else "unknown"

    return f"""You are an expert Python debugger. Analyse the runtime error below and \
respond ONLY with a JSON object — no markdown fences, no extra text.

## Error Information
- Error type : {ctx.error_type}
- Message    : {ctx.message}
- File       : {ctx.file}  |  Line: {ctx.line}  |  Function: {ctx.function}

## AST Analysis (static analysis result)
- Node type  : {ctx.node_type or 'unknown'}
- Expression : {ctx.expression or 'unknown'}
- Variables  : {vars_str}

## Rule-based pre-diagnosis
{ctx.possible_cause}
Hint: {ctx.hint}

## Code snippet (error occurs at line {ctx.line})
```python
{ctx.code_snippet}
```

Respond with exactly this JSON structure:
{{
  "explanation": "<2-4 sentence plain-English explanation of why the error happened>",
  "root_cause": "<single sentence identifying the precise root cause>",
  "suggested_fix": "<concrete 1-3 step fix the developer should apply>",
  "improved_code": "<corrected Python code block, complete function if possible>"
}}"""


# ── Public API ────────────────────────────────────────────────────────────────

def explain(ctx: ErrorContext, api_key: str) -> AiResult:
    """
    Call Gemini 1.5 Flash with the structured ErrorContext.
    Returns a graceful fallback AiResult on any failure so the extension
    always has something useful to display.
    """
    if not api_key or api_key.strip() == "":
        print("[AiEngine] No API key configured — using rule-based fallback")
        log.warning("Gemini API key not set; falling back to rule-based explanation.")
        return _fallback(ctx)

    print(f"[AiEngine] Calling Gemini for {ctx.error_type} at {ctx.file}:{ctx.line}")

    try:
        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content(
            _build_prompt(ctx),
            generation_config=genai.GenerationConfig(
                temperature=0.2,       # low temperature for factual, stable output
                max_output_tokens=1024,
            ),
        )

        raw = response.text.strip()
        print(f"[AiEngine] Received response ({len(raw)} chars)")
        log.info("Gemini response received (%d chars)", len(raw))

        return _parse_response(raw, ctx)

    except Exception as exc:
        print(f"[AiEngine] Gemini call failed: {exc}")
        log.error("Gemini API error: %s", exc)
        return _fallback(ctx)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_response(raw: str, ctx: ErrorContext) -> AiResult:
    """
    Strip any accidental markdown fences and parse the JSON response.
    Falls back if the JSON is malformed.
    """
    # Remove leading/trailing ```json ... ``` fences the model sometimes adds
    clean = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    clean = re.sub(r"\n?```$",       "", clean, flags=re.MULTILINE).strip()

    try:
        data = json.loads(clean)
        print("[AiEngine] JSON parsed successfully")
        return AiResult(
            explanation   = data.get("explanation",   ctx.possible_cause),
            root_cause    = data.get("root_cause",    ctx.possible_cause),
            suggested_fix = data.get("suggested_fix", ctx.hint),
            improved_code = data.get("improved_code", ""),
            ai_used       = True,
        )
    except json.JSONDecodeError as exc:
        print(f"[AiEngine] JSON decode error: {exc} — using fallback")
        log.warning("Could not decode Gemini JSON response: %s", exc)
        return _fallback(ctx)


def _fallback(ctx: ErrorContext) -> AiResult:
    """
    Rule-based fallback used when AI is unavailable.
    Uses the possible_cause / hint produced by root_cause_detector.
    """
    print("[AiEngine] Returning rule-based fallback explanation")
    return AiResult(
        explanation   = ctx.possible_cause,
        root_cause    = ctx.possible_cause,
        suggested_fix = ctx.hint,
        improved_code = "",
        ai_used       = False,
    )
