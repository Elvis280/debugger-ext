"""
main.py
────────
FastAPI backend — the single /analyze endpoint that orchestrates every
analysis service and returns a fully-structured AnalyzeResponse to the
VS Code extension.

Pipeline (every request):
    stack_trace  →  parse  →  AST analysis (with disk cache)
                 →  root cause detection  →  error context assembly
                 →  AI explanation (Gemini / fallback)  →  response

Start manually:
    cd backend
    python start_backend.py --api-key YOUR_KEY
"""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import AnalyzeRequest, AnalyzeResponse
import services.stack_trace_parser    as stp
import services.ast_analyzer          as asta
import services.root_cause_detector   as rcd
import services.error_context_builder as ecb
import services.ai_engine             as ai

# ── Load environment variables ────────────────────────────────────────────────
# Reads GEMINI_API_KEY (and any other vars) from backend/.env
# An existing shell environment variable always takes priority over .env
_ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)   # override=False: shell wins
print(f"[Backend] Loaded .env from {_ENV_FILE} (exists={_ENV_FILE.exists()})")


# ── Logging setup ─────────────────────────────────────────────────────────────
# All print() statements in service modules go to stdout.
# logging.basicConfig routes logger output to the same stream.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("debugger-backend")


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log startup and shutdown so the extension output channel shows status."""
    print("[Backend] Debug Analysis Service starting on http://localhost:7823")
    log.info("Debug Analysis Service ready")
    yield
    print("[Backend] Debug Analysis Service shutting down")
    log.info("Shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Python Debug Analysis Service",
    description = "Backend for the VS Code AI Debugger extension",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# Allow the VS Code extension (running on localhost) to POST to this service
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["POST", "GET"],
    allow_headers = ["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    Simple liveness probe used by the extension to check if the backend
    is up before sending an analysis request.
    """
    print("[Backend] /health — OK")
    return {"status": "ok", "service": "debugger-backend"}


# ── Main analysis endpoint ────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Full analysis pipeline:

    1. Parse the stack trace to extract the deepest frame.
    2. Run AST analysis on the referenced file (result is cached).
    3. Apply rule-based root cause detection.
    4. Build a unified ErrorContext from all upstream results.
    5. Call the AI engine (Gemini) to generate an explanation.
    6. Return a fully structured AnalyzeResponse.
    """
    print(f"\n[Backend] === New /analyze request ===")
    print(f"[Backend] Language: {request.language}  |  File: {request.file_path}")
    print(f"[Backend] Stack trace length: {len(request.stack_trace)} chars")
    log.info("Analyze request: %s (%s)", request.file_path, request.language)

    # ── Step 1: Parse stack trace ─────────────────────────────────────────────
    parsed = stp.parse(request.stack_trace)

    if parsed is None:
        print("[Backend] ERROR — could not parse stack trace")
        raise HTTPException(
            status_code=400,
            detail="Could not parse the stack trace. "
                   "Ensure the stack_trace field contains valid Python traceback output.",
        )

    # ── Step 2: AST analysis (disk-cached) ───────────────────────────────────
    ast_result = asta.analyse(parsed.file, parsed.line)

    # ── Step 3: Rule-based root cause detection ───────────────────────────────
    root_cause = rcd.detect(parsed, ast_result)

    # ── Step 4: Assemble unified error context ────────────────────────────────
    ctx = ecb.build(parsed, ast_result, root_cause, request.code_snippet)

    # ── Step 5: AI explanation ────────────────────────────────────────────────
    # API key comes from the GEMINI_API_KEY environment variable,
    # set either via `start_backend.py --api-key` or the user's shell.
    api_key    = os.environ.get("GEMINI_API_KEY", "")
    ai_result  = ai.explain(ctx, api_key)

    print(
        f"[Backend] Analysis complete: "
        f"ai_used={ai_result.ai_used}  cached={ast_result.cached}"
    )
    log.info(
        "Analysis done: ai_used=%s cached=%s",
        ai_result.ai_used, ast_result.cached,
    )

    # ── Step 6: Build and return response ────────────────────────────────────
    return AnalyzeResponse(
        error_type     = ctx.error_type,
        file           = ctx.file,
        line           = ctx.line,
        function       = ctx.function,
        node_type      = ctx.node_type,
        expression     = ctx.expression,
        variables      = ctx.variables,
        possible_cause = ctx.possible_cause,
        code_snippet   = ctx.code_snippet,
        explanation    = ai_result.explanation,
        root_cause     = ai_result.root_cause,
        suggested_fix  = ai_result.suggested_fix,
        improved_code  = ai_result.improved_code,
        cached         = ctx.cached,
        language       = request.language,
    )
