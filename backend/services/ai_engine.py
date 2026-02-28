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
    concept:          str           # what this error type actually means (concept lesson)
    explanation:      str           # what went wrong in THIS specific code
    root_cause:       str           # single precise root cause sentence
    analogy:          str           # real-world analogy to make it memorable
    step_by_step_fix: str           # numbered steps to fix the problem
    improved_code:    str           # corrected Python code block
    ai_used:          bool = True   # False when AI was unavailable / fallback used


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(ctx: ErrorContext) -> str:
    """
    Build a teacher-style structured prompt from the ErrorContext.
    The model is asked to explain like a patient senior developer teaching
    a junior — concept first, then specific error, then how to fix it.
    """
    vars_str = ", ".join(ctx.variables) if ctx.variables else "unknown"

    return f"""You are a patient, expert Python teacher explaining a runtime error to a student.
Your job is to teach — not just fix. Explain the concept, why it happened, give an analogy, then show the fix.
Respond ONLY with a JSON object — no markdown fences, no extra text.

## Error Details
- Error type : {ctx.error_type}
- Message    : {ctx.message}
- File       : {ctx.file}  |  Line: {ctx.line}  |  Function: {ctx.function}
- Expression : {ctx.expression or 'unknown'}
- Variables  : {vars_str}

## Static Analysis Pre-diagnosis
{ctx.possible_cause}
Hint: {ctx.hint}

## Code (error at line {ctx.line}, marked with >>>)
```python
{ctx.code_snippet}
```

Respond with EXACTLY this JSON — all 6 fields are required:
{{
  "concept": "<2-3 sentences: what is {ctx.error_type}? Explain the concept in simple terms, as if to a beginner who has never seen this error before>",
  "explanation": "<2-3 sentences: what specifically went wrong in THIS code? Reference the variable names and line number>",
  "root_cause": "<1 precise sentence identifying the exact root cause in this code>",
  "analogy": "<1-2 sentences: a real-world analogy that makes this error memorable and intuitive>",
  "step_by_step_fix": "<numbered list of 2-4 concrete steps the student should take to fix their code>",
  "improved_code": "<the complete corrected Python code for the function or block that had the error>"
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
        print("[AiEngine] JSON parsed successfully — teacher-style response received")
        return AiResult(
            concept          = data.get("concept",          f"{ctx.error_type} occurs when Python cannot perform the requested operation."),
            explanation      = data.get("explanation",      ctx.possible_cause),
            root_cause       = data.get("root_cause",       ctx.possible_cause),
            analogy          = data.get("analogy",          ""),
            step_by_step_fix = data.get("step_by_step_fix", ctx.hint),
            improved_code    = data.get("improved_code",    ""),
            ai_used          = True,
        )
    except json.JSONDecodeError as exc:
        print(f"[AiEngine] JSON decode error: {exc} — using fallback")
        log.warning("Could not decode Gemini JSON response: %s", exc)
        return _fallback(ctx)


def _fallback(ctx: ErrorContext) -> AiResult:
    """
    Rule-based fallback when AI is unavailable.
    Uses possible_cause / hint from root_cause_detector.
    """
    print("[AiEngine] Returning rule-based fallback (no AI key or API failure)")
    return AiResult(
        concept          = f"{ctx.error_type} is a runtime error that occurs when Python cannot complete the requested operation.",
        explanation      = ctx.possible_cause,
        root_cause       = ctx.possible_cause,
        analogy          = "",
        step_by_step_fix = ctx.hint,
        improved_code    = "",
        ai_used          = False,
    )
