"""
start_backend.py

Convenience launcher for the backend debug analysis service.
Usage:
    python start_backend.py
    python start_backend.py --port 7823 --reload
"""

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Start the Debug Analysis Service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7823)
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    parser.add_argument("--api-key", default="", help="Gemini API key (overrides .env)")
    args = parser.parse_args()

    # ── Load .env FIRST so the key check below is accurate ───────────────────
    # This must happen before we inspect os.environ["GEMINI_API_KEY"].
    # main.py also calls load_dotenv(), but that runs later when uvicorn
    # imports it — too late for this pre-flight check.
    env_file = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_file, override=False)  # shell env always wins

    # A --api-key CLI argument overrides everything
    if args.api_key:
        os.environ["GEMINI_API_KEY"] = args.api_key

    # Now the check is accurate — .env has already been read
    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "[WARN] GEMINI_API_KEY not set. "
            "Add it to backend/.env or pass --api-key. "
            "AI explanations will fall back to rule-based output.",
            file=sys.stderr,
        )
    else:
        print("[INFO] GEMINI_API_KEY loaded successfully.")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
