# AI Python Debugger

> A VS Code extension that captures Python runtime errors, analyses them with static analysis and AST inspection, and delivers AI-powered explanations with corrected code — all inside your editor.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│         VS Code Extension (TypeScript)        │
│  Thin client — UI, error capture, display     │
│                                               │
│  extension.ts          ← command + pipeline   │
│  stackTraceParser.ts   ← instant local parse  │
│  codeContextExtractor.ts ← VS Code FS read    │
│  backendClient.ts      ← HTTP POST /analyze   │
│  webviewPanel.ts       ← styled result UI     │
└──────────────────┬───────────────────────────┘
                   │  HTTP POST /analyze
                   │  localhost:7823
┌──────────────────▼───────────────────────────┐
│      Python FastAPI Backend                   │
│  All heavy analysis runs here                 │
│                                               │
│  services/stack_trace_parser.py               │
│  services/ast_analyzer.py  ← diskcache        │
│  services/root_cause_detector.py              │
│  services/error_context_builder.py            │
│  services/ai_engine.py  ← Gemini 1.5 Flash   │
└──────────────────────────────────────────────┘
```

---

## Features

| Feature | Details |
|---|---|
| **Instant squiggle** | Red diagnostic appears before the backend responds |
| **Stack trace parsing** | Extracts deepest frame: file, line, function, error type |
| **AST analysis** | Finds the exact failing expression (`a / b`, `lst[i]`) |
| **AST caching** | Second run on unchanged file is served from cache (<1 ms) |
| **Root cause rules** | Zero-AI detection for 8 error types |
| **AI explanation** | Gemini 1.5 Flash delivers plain-English explanation + fix |
| **Graceful fallback** | Rule-based output shown when AI is unavailable |
| **Output channel** | All backend `print()` / log lines visible in VS Code Output panel |
| **Webview panel** | Dark-themed panel with copy-to-clipboard button |

---

## Supported Python Errors

| Error | Rule detects |
|---|---|
| `ZeroDivisionError` | Identifies the denominator variable |
| `IndexError` | Identifies the list and index |
| `AttributeError` | Identifies the object and attribute name |
| `NameError` | Identifies the undefined variable |
| `TypeError` | Reports type mismatch from message |
| `KeyError` | Identifies the missing key |
| `ValueError` | Reports invalid value from message |
| `RecursionError` | Identifies the recursive function |

---

## Setup

### 1 — Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2 — Add your Gemini API key *(optional)*

Open `backend/.env` and paste your key:

```env
GEMINI_API_KEY=your_key_here
```

Get a free key at → **[aistudio.google.com](https://aistudio.google.com/)**

> `.env` is gitignored — it will never be committed.  
> Without a key, the extension still works using rule-based analysis.

### 3 — Launch the extension

Press **F5** inside the `debugger-ext` project folder.  
A new **Extension Development Host** window opens.  
The backend starts automatically.

---

## Usage

1. Open any `.py` file in the Extension Development Host window
2. Press `Ctrl+Shift+P` → **Run Diagnostics**  
   *(or click the 🐛 icon in the editor title bar)*
3. The extension runs your file and analyses any error

**What you'll see:**

- **Output panel** (`View → Output → AI Debugger`) — live backend logs streaming in real time
- **Red squiggle** — inline diagnostic on the error line
- **Webview panel** — slides open beside your editor with:
  - Error type + location
  - Failing expression (`a / b`, `lst[5]`, …)
  - Code snippet with the error line marked
  - AI explanation
  - Root cause
  - Suggested fix
  - Corrected code with a **Copy** button

---

## Backend Logs

Every step of the pipeline prints a structured log line you can follow in the **Output Channel**:

```
[AI Debugger]     Running: python "test.py"
[AI Debugger]     Captured output: ...
[StackTraceParser] Deepest frame: test.py:6 in calculate_ratio
[StackTraceParser] Detected exception: ZeroDivisionError: division by zero
[AstAnalyzer]      Cache MISS — parsing AST for line 6
[AstAnalyzer]      Found node 'BinOp' expr='a / b' vars=['a', 'b']
[AstAnalyzer]      Result cached
[RootCause]        ZeroDivisionError — denominator is 'b'
[ContextBuilder]   Built ErrorContext: ZeroDivisionError @ test.py:6
[AiEngine]         Calling Gemini for ZeroDivisionError at test.py:6
[AiEngine]         Received response (512 chars)
[AiEngine]         JSON parsed successfully
[Backend]          Analysis complete: ai_used=True cached=False
[AI Debugger]      Result displayed in webview
```

---

## Settings

| Setting | Default | Description |
|---|---|---|
| `debugger-ext.geminiApiKey` | `""` | Gemini API key |
| `debugger-ext.backendUrl` | `http://localhost:7823` | Backend URL (local or remote) |
| `debugger-ext.autoStartBackend` | `true` | Spawn backend on activation |
| `debugger-ext.pythonPath` | `"python"` | Python executable path |
| `debugger-ext.contextLines` | `7` | Lines shown around the error |

---

## File Structure

```
debugger-ext/
├── backend/                        ← Python FastAPI analysis service
│   ├── main.py                     ← FastAPI app + /analyze endpoint
│   ├── models.py                   ← Pydantic request/response schemas
│   ├── requirements.txt            ← pip dependencies
│   ├── start_backend.py            ← CLI launcher
│   ├── cache/
│   │   └── ast_cache.py            ← diskcache singleton
│   └── services/
│       ├── stack_trace_parser.py   ← Regex stack trace parser
│       ├── ast_analyzer.py         ← AST walker + cache
│       ├── root_cause_detector.py  ← Rule-based heuristics
│       ├── error_context_builder.py← Context assembler
│       └── ai_engine.py            ← Gemini 1.5 Flash client
│
└── src/                            ← VS Code Extension (TypeScript)
    ├── extension.ts                ← Entry point, Output Channel, pipeline
    ├── stackTraceParser.ts         ← Lightweight local parse
    ├── codeContextExtractor.ts     ← VS Code workspace FS reader
    ├── backendClient.ts            ← HTTP client (Node http module)
    └── webviewPanel.ts             ← Dark-themed webview panel
```

---

## API Reference

### `POST /analyze`

**Request**
```json
{
  "stack_trace": "Traceback (most recent call last):\n  ...",
  "code_snippet": "def calculate_ratio(a, b):\n    return a / b\n",
  "file_path": "/workspace/app.py",
  "language": "python"
}
```

**Response**
```json
{
  "error_type": "ZeroDivisionError",
  "file": "app.py",
  "line": 6,
  "function": "calculate_ratio",
  "node_type": "BinOp",
  "expression": "a / b",
  "variables": ["a", "b"],
  "possible_cause": "Denominator 'b' is zero during division in 'calculate_ratio'.",
  "code_snippet": "...",
  "explanation": "The function divides a by b. When b is 0...",
  "root_cause": "No guard against b == 0 before the division.",
  "suggested_fix": "Add `if b == 0: raise ValueError(...)` before the return.",
  "improved_code": "def calculate_ratio(a, b):\n    if b == 0:\n        raise ValueError('b cannot be zero')\n    return a / b\n",
  "cached": false,
  "language": "python"
}
```

### `GET /health`
```json
{ "status": "ok", "service": "debugger-backend" }
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Backend did not start | Run `python start_backend.py` in `backend/`, check Output panel |
| No AI explanation shown | Add `geminiApiKey` in settings — rule-based fallback still works |
| `python` not found | Set `debugger-ext.pythonPath` to the full path e.g. `C:\Python312\python.exe` |
| Output panel not visible | `View → Output` → select **AI Debugger** in the dropdown |
| Want to connect a remote backend | Set `debugger-ext.backendUrl` to your remote URL and `autoStartBackend` to `false` |
