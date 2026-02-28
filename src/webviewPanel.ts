/**
 * webviewPanel.ts
 *
 * Creates and manages the VS Code Webview panel that displays
 * the AI analysis result: error summary, root cause, explanation,
 * suggested fix and improved code snippet.
 */

import * as vscode from 'vscode';
import type { AnalyzeResponse } from './backendClient';

let panel: vscode.WebviewPanel | undefined;

// ── Public API ────────────────────────────────────────────────────────────────

/** Show the loading state while waiting for the backend. */
export function showLoading(errorType: string, filePath: string): void {
    ensurePanel();
    panel!.webview.html = buildLoadingHtml(errorType, filePath);
}

/** Render the full analysis result. */
export function showResult(result: AnalyzeResponse): void {
    ensurePanel();
    panel!.webview.html = buildResultHtml(result);
}

/** Show an error message inside the panel. */
export function showError(message: string): void {
    ensurePanel();
    panel!.webview.html = buildErrorHtml(message);
}

export function dispose(): void {
    panel?.dispose();
    panel = undefined;
}

// ── Panel management ──────────────────────────────────────────────────────────

function ensurePanel(): void {
    if (!panel) {
        panel = vscode.window.createWebviewPanel(
            'aiDebugger',
            '🐛 AI Debugger',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );
        panel.onDidDispose(() => { panel = undefined; });
    }
    panel.reveal(vscode.ViewColumn.Beside, true);
}

// ── HTML builders ─────────────────────────────────────────────────────────────

function buildLoadingHtml(errorType: string, filePath: string): string {
    const file = filePath.split(/[\\/]/).pop() ?? filePath;
    return `<!DOCTYPE html>
<html lang="en">
<head>${commonHead()}</head>
<body>
  <div class="container loading-container">
    <div class="spinner"></div>
    <h2>Analysing <span class="error-badge">${esc(errorType)}</span></h2>
    <p class="muted">in <code>${esc(file)}</code></p>
    <p class="muted">Sending to analysis backend…</p>
  </div>
</body></html>`;
}

function buildErrorHtml(message: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>${commonHead()}</head>
<body>
  <div class="container">
    <div class="card error-card">
      <h2>⚠️ Analysis Failed</h2>
      <p>${esc(message)}</p>
      <p class="muted">Make sure the backend is running: <code>python start_backend.py</code></p>
    </div>
  </div>
</body></html>`;
}

function buildResultHtml(r: AnalyzeResponse): string {
    const fileName = r.file.split(/[\\/]/).pop() ?? r.file;
    const varsHtml = r.variables.length
        ? r.variables.map(v => `<span class="var-badge">${esc(v)}</span>`).join(' ')
        : '<span class="muted">none detected</span>';

    const cacheTag = r.cached
        ? '<span class="cache-badge">⚡ cached</span>'
        : '';

    const improvedCodeSection = r.improved_code
        ? `<div class="card">
        <h3>✅ Improved Code</h3>
        <pre class="code-block">${esc(r.improved_code)}</pre>
        <button class="copy-btn" onclick="copyCode()">📋 Copy</button>
       </div>`
        : '';

    return `<!DOCTYPE html>
<html lang="en">
<head>
  ${commonHead()}
  <script>
    function copyCode() {
      const code = document.querySelector('.code-block').innerText;
      navigator.clipboard.writeText(code).then(() => {
        const btn = document.querySelector('.copy-btn');
        btn.textContent = '✅ Copied!';
        setTimeout(() => btn.textContent = '📋 Copy', 2000);
      });
    }
  </script>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <h1><span class="error-badge">${esc(r.error_type)}</span> ${cacheTag}</h1>
      <p class="location">📄 <code>${esc(fileName)}</code> · line <strong>${r.line}</strong> · <code>${esc(r.function)}</code></p>
    </div>
  </div>

  <!-- Error Message -->
  <div class="card error-card">
    <h3>🚨 Error Message</h3>
    <p>${esc(r.possible_cause)}</p>
  </div>

  <!-- AST Info -->
  ${r.expression ? `
  <div class="card ast-card">
    <h3>🔬 Expression at Error Site</h3>
    <pre class="inline-code">${esc(r.expression)}</pre>
    <p><strong>Node type:</strong> ${esc(r.node_type ?? 'unknown')}</p>
    <p><strong>Variables:</strong> ${varsHtml}</p>
  </div>` : ''}

  <!-- Code Snippet -->
  <div class="card">
    <h3>📋 Code Context</h3>
    <pre class="code-block snippet-block">${esc(r.code_snippet)}</pre>
  </div>

  <!-- Explanation -->
  <div class="card explain-card">
    <h3>💡 Explanation</h3>
    <p>${esc(r.explanation)}</p>
  </div>

  <!-- Root Cause -->
  <div class="card cause-card">
    <h3>🔍 Root Cause</h3>
    <p>${esc(r.root_cause)}</p>
  </div>

  <!-- Suggested Fix -->
  <div class="card fix-card">
    <h3>🛠 Suggested Fix</h3>
    <p>${esc(r.suggested_fix)}</p>
  </div>

  <!-- Improved Code -->
  ${improvedCodeSection}

</div>
</body>
</html>`;
}

// ── Shared CSS / head ─────────────────────────────────────────────────────────

function commonHead(): string {
    return `
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Debugger</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3250;
    --accent: #6c7bff;
    --red: #ff5f6d;
    --green: #43e97b;
    --yellow: #f9c74f;
    --text: #e2e4f0;
    --muted: #8b90a8;
    --font: 'Segoe UI', system-ui, sans-serif;
    --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.6;
    padding: 0 0 40px;
  }
  .container { max-width: 860px; margin: 0 auto; padding: 24px 20px; }
  .header {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  h1 { font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
  h2 { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
  h3 { font-size: 13px; font-weight: 700; text-transform: uppercase;
       letter-spacing: .06em; margin-bottom: 10px; color: var(--muted); }
  p  { color: var(--text); line-height: 1.7; }
  .location { color: var(--muted); font-size: 13px; margin-top: 4px; }
  .muted { color: var(--muted); }
  code { font-family: var(--mono); background: var(--surface2);
         padding: 2px 6px; border-radius: 4px; font-size: 12px; }

  /* Cards */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 14px;
  }
  .error-card   { border-left: 3px solid var(--red); }
  .ast-card     { border-left: 3px solid #a78bfa; }
  .explain-card { border-left: 3px solid var(--accent); }
  .cause-card   { border-left: 3px solid var(--yellow); }
  .fix-card     { border-left: 3px solid var(--green); }

  /* Badges */
  .error-badge {
    background: #ff5f6d22; color: var(--red);
    border: 1px solid #ff5f6d55;
    border-radius: 6px; padding: 3px 10px; font-size: 14px; font-weight: 700;
  }
  .cache-badge {
    background: #43e97b22; color: var(--green);
    border: 1px solid #43e97b55;
    border-radius: 6px; padding: 3px 8px; font-size: 11px;
  }
  .var-badge {
    display: inline-block;
    background: var(--surface2); color: var(--accent);
    border: 1px solid var(--border);
    border-radius: 4px; padding: 1px 7px; font-family: var(--mono); font-size: 12px;
  }

  /* Code */
  .code-block {
    background: #0d0f1a;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 16px;
    font-family: var(--mono);
    font-size: 12.5px;
    line-height: 1.6;
    overflow-x: auto;
    white-space: pre;
    color: #c9d1f0;
  }
  .snippet-block { max-height: 260px; overflow-y: auto; }
  .inline-code {
    background: #0d0f1a; color: var(--red);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 12px; font-family: var(--mono); font-size: 13px;
    margin-bottom: 10px; display: inline-block;
  }
  .copy-btn {
    margin-top: 10px;
    background: var(--surface2); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 14px; font-size: 13px; cursor: pointer;
    transition: background .2s;
  }
  .copy-btn:hover { background: var(--accent); color: #fff; }

  /* Loading */
  .loading-container { text-align: center; padding-top: 80px; }
  .spinner {
    width: 48px; height: 48px; margin: 0 auto 24px;
    border: 4px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>`;
}

/** HTML-escape a value for safe insertion into HTML. */
function esc(v: string | null | undefined): string {
    if (!v) { return ''; }
    return v
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
