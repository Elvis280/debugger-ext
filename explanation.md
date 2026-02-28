# AI Python Debugger — Project Explanation

## What This Project Does

A VS Code extension that watches you run Python code, catches runtime errors, and explains them **like a teacher** — not just the fix, but *why* it happened, what the concept is, and a real-world analogy to make it stick.

---

## Current Status ✅

The project is **fully functional** end-to-end with the following pipeline working:

```
You press "Run Diagnostics"
        ↓
Extension runs your .py file and captures the error
        ↓
Local parser → instant red squiggle on the error line (< 50 ms)
        ↓
Backend analyses the error (AST + root cause rules + AI)
        ↓
Result appears in TWO places simultaneously:
  1. VS Code Output Channel   ← plain-text teacher explanation in the terminal
  2. Webview panel            ← beautiful dark-themed visual breakdown
```

---

## Architecture

```
debugger-ext/
│
├── src/                         VS Code Extension (TypeScript — thin client)
│   ├── extension.ts             Entry point: spawns backend, runs command, pipes logs
│   ├── stackTraceParser.ts      Fast local parse for instant squiggle
│   ├── codeContextExtractor.ts  Reads file via VS Code FS APIs
│   ├── backendClient.ts         HTTP POST to backend /analyze
│   └── webviewPanel.ts          7-section teacher-style dark webview
│
└── backend/                     Python FastAPI Service (all heavy work)
    ├── main.py                  FastAPI app · /health · /analyze
    ├── models.py                Pydantic request/response schemas
    ├── start_backend.py         CLI launcher (loads .env, checks API key)
    ├── requirements.txt         pip dependencies
    ├── .env                     Your GEMINI_API_KEY (gitignored)
    ├── .env.example             Template for teammates
    └── services/
        ├── stack_trace_parser.py    Regex parser (handles RuntimeError + SyntaxError)
        ├── ast_analyzer.py          AST walker + diskcache (1-hour TTL)
        ├── root_cause_detector.py   Rule-based heuristics for 8 error types
        ├── error_context_builder.py Merges all pipeline results into one object
        └── ai_engine.py             Gemini 1.5 Flash · teacher-style prompt · fallback
```

---

## What the AI Explanation Looks Like

Every error is explained across **6 teacher-style sections**, shown both in the terminal and the webview:

| Section | What it answers |
|---|---|
| **What is this error?** | Concept explained for a beginner |
| **What went wrong in your code?** | Specific to your variables and line number |
| **Root Cause** | One precise sentence |
| **Think of it like this…** | Real-world analogy |
| **How to Fix It** | Numbered step-by-step fix |
| **Improved Code** | Corrected Python code with copy button |

---

## What Errors Are Supported

Rule-based detection (works without AI key) for:

| Error | What is detected |
|---|---|
| `ZeroDivisionError` | Which variable is the denominator |
| `IndexError` | Which list and which index |
| `AttributeError` | Which object and which attribute |
| `NameError` | Which variable is undefined |
| `TypeError` | Type mismatch from the error message |
| `KeyError` | Which key is missing |
| `ValueError` | Invalid value from the error message |
| `RecursionError` | Which function recurses infinitely |

---

## Where Output Appears

### 1 — VS Code Output Channel (`View → Output → AI Debugger`)
Shows **everything** — backend print logs, pipeline steps, and the full teacher explanation formatted as plain text.

### 2 — Webview Panel (slides open beside your editor)
The same content rendered as a styled, dark-themed page with colour-coded cards, expression highlights, and a copy button.

### 3 — Inline Squiggle (in the editor)
Red underline on the exact error line appears **instantly** (before even the backend responds).

---

## How to Run

### One-time setup
```bash
cd backend
pip install -r requirements.txt
```

Add your API key to `backend/.env`:
```env
GEMINI_API_KEY=your_key_here   # from aistudio.google.com (free)
```
> Works in rule-based mode without a key too.

### Every time
1. Open the `debugger-ext` folder in VS Code
2. Press **F5** → Extension Development Host opens
3. Open any `.py` file
4. `Ctrl+Shift+P` → **Run Diagnostics**

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| Backend is a separate FastAPI process | Heavy analysis (AST, AI) shouldn't block the extension host |
| Backend auto-spawns on extension activate | Zero setup for the user — it just works |
| Backend stdout piped to Output Channel | Developer can see every log line without opening a separate terminal |
| Two output surfaces (terminal + webview) | Power users read text; everyone else reads the visual breakdown |
| AI prompt is teacher-style, not just "fix this" | Helps the developer understand so they don't make the same mistake twice |
| AST cache (diskcache, 1h TTL) | Re-analysing an unchanged file costs ~0 ms |
| `.env` for API key | Never hardcode secrets; `.env` is gitignored |
| Graceful AI fallback | Works offline or without a key, using rule-based explanations |

---

## Known Limitations / Future Work

- **Only Python** is supported. The backend is designed to be extensible for other languages via a service registry.
- **AST analysis** only works when the referenced file is accessible from the backend (local files only — no remote SSH).
- **AI token limit**: very long code snippets may be truncated in the prompt.
- **No streaming**: the webview shows a spinner until the full response arrives (~2–5 s with AI).
