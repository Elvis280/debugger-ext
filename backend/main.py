"""
main.py
FastAPI backend — single /analyze endpoint that orchestrates all
analysis services and returns a fully-structured AnalyzeResponse.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import AnalyzeRequest, AnalyzeResponse
import services.stack_trace_parser as stp
import services.ast_analyzer as asta
import services.root_cause_detector as rcd
import services.error_context_builder as ecb
import services.ai_engine as ai

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("debugger-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Debug Analysis Service starting on http://localhost:7823")
    yield
    log.info("🛑 Debug Analysis Service shutting down")


app = FastAPI(
    title="Python Debug Analysis Service",
    description="Backend for the VS Code AI Debugger extension",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the VS Code extension (localhost) to talk to this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "debugger-backend"}


# ---------------------------------------------------------------------------
# Main analysis endpoint
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Full pipeline:
        stack_trace → parse → AST analysis (cached) →
        root cause → error context → AI explanation → AnalyzeResponse
    """

    # 1. Parse the stack trace
    parsed = stp.parse(request.stack_trace)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Could not parse stack trace. "
                            "Make sure the stack_trace field contains valid Python traceback output.")

    log.info("Parsed error: %s at %s:%d", parsed.error_type, parsed.file, parsed.line)

    # 2. AST analysis (uses cache)
    ast_result = asta.analyse(parsed.file, parsed.line)

    # 3. Rule-based root cause
    root_cause = rcd.detect(parsed, ast_result)

    # 4. Build unified context
    ctx = ecb.build(parsed, ast_result, root_cause, request.code_snippet)

    # 5. AI explanation
    api_key = os.environ.get("GEMINI_API_KEY", "")
    ai_result = ai.explain(ctx, api_key)

    log.info(
        "Analysis complete: ai_used=%s cached=%s",
        ai_result.ai_used,
        ast_result.cached,
    )

    return AnalyzeResponse(
        # Stack trace fields
        error_type=ctx.error_type,
        file=ctx.file,
        line=ctx.line,
        function=ctx.function,
        # AST fields
        node_type=ctx.node_type,
        expression=ctx.expression,
        variables=ctx.variables,
        # Root cause
        possible_cause=ctx.possible_cause,
        # Code
        code_snippet=ctx.code_snippet,
        # AI
        explanation=ai_result.explanation,
        root_cause=ai_result.root_cause,
        suggested_fix=ai_result.suggested_fix,
        improved_code=ai_result.improved_code,
        # Meta
        cached=ctx.cached,
        language=request.language,
    )
