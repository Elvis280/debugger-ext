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
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Start the Debug Analysis Service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7823)
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    parser.add_argument("--api-key", default="", help="Gemini API key (or set GEMINI_API_KEY env var)")
    args = parser.parse_args()

    if args.api_key:
        os.environ["GEMINI_API_KEY"] = args.api_key

    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "[WARN] GEMINI_API_KEY not set. "
            "AI explanations will fall back to rule-based output.",
            file=sys.stderr,
        )

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
