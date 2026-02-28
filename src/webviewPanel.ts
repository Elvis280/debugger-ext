/**
 * webviewPanel.ts
 * ───────────────
 * Manages the VS Code Webview panel that displays analysis results
 * in a teacher-style layout: concept lesson → what went wrong →
 * root cause → analogy → step-by-step fix → corrected code.
 */

import * as vscode from 'vscode';
import type { AnalyzeResponse } from './backendClient';

let panel: vscode.WebviewPanel | undefined;

// ── Public API ────────────────────────────────────────────────────────────────

export function showLoading(errorType: string, filePath: string): void {
  ensurePanel();
  panel!.webview.html = buildLoadingHtml(errorType, filePath);
}

export function showResult(result: AnalyzeResponse): void {
  ensurePanel();
  panel!.webview.html = buildResultHtml(result);
}

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
      '🎓 AI Debugger',
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );
    panel.onDidDispose(() => { panel = undefined; });
  }
  panel.reveal(vscode.ViewColumn.Beside, true);
}

// ── HTML builders ─────────────────────────────────────────────────────────────

function buildLoadingHtml(errorType: string, filePath: string): string {
  const file = filePath.split(/[\\/]/).pop() ?? filePath;
  return `<!DOCTYPE html><html lang="en"><head>${head()}</head><body>
    <div class="loading-wrap">
        <div class="spinner"></div>
        <h2>Analysing <span class="err-pill">${esc(errorType)}</span></h2>
        <p class="muted">in <code>${esc(file)}</code></p>
        <p class="muted" style="margin-top:8px">Thinking like your teacher…</p>
    </div>
    </body></html>`;
}

function buildErrorHtml(message: string): string {
  return `<!DOCTYPE html><html lang="en"><head>${head()}</head><body>
    <div class="page">
        <div class="card border-red">
            <h2>⚠ Analysis Failed</h2>
            <p>${esc(message)}</p>
            <p class="muted" style="margin-top:10px">
                Make sure the backend is running:<br>
                <code>python start_backend.py</code>
            </p>
        </div>
    </div></body></html>`;
}

function buildResultHtml(r: AnalyzeResponse): string {
  const fileName = r.file.split(/[\\/]/).pop() ?? r.file;
  const vars = r.variables.length
    ? r.variables.map(v => `<span class="var-tag">${esc(v)}</span>`).join(' ')
    : '<span class="muted">none</span>';

  const cachedTag = r.cached
    ? '<span class="cache-tag">⚡ cached</span>' : '';

  // Build the numbered fix steps from a string like "1. do X\n2. do Y"
  const fixLines = r.step_by_step_fix
    .split(/\n/)
    .filter(l => l.trim())
    .map(l => `<li>${esc(l.replace(/^\d+\.\s*/, ''))}</li>`)
    .join('');

  const codeSection = r.improved_code ? `
    <div class="card border-green">
        <div class="card-label">✅ Corrected Code</div>
        <pre class="code-block">${esc(r.improved_code)}</pre>
        <button class="copy-btn" onclick="copyCode()">📋 Copy</button>
    </div>` : '';

  const analogySection = r.analogy ? `
    <div class="card border-purple">
        <div class="card-label">💡 Think of it like this…</div>
        <p class="analogy-text">${esc(r.analogy)}</p>
    </div>` : '';

  return `<!DOCTYPE html>
<html lang="en">
<head>
${head()}
<script>
function copyCode() {
    const code = document.querySelector('.code-block').innerText;
    navigator.clipboard.writeText(code).then(() => {
        const btn = document.querySelector('.copy-btn');
        btn.textContent = '✅ Copied!';
        setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000);
    });
}
</script>
</head>
<body>
<div class="page">

    <!-- ── Header ──────────────────────────────────────────── -->
    <div class="header">
        <div>
            <div class="header-top">
                <span class="err-pill">${esc(r.error_type)}</span>
                ${cachedTag}
            </div>
            <p class="location">
                📄 <code>${esc(fileName)}</code>
                &nbsp;·&nbsp; line <strong>${r.line}</strong>
                &nbsp;·&nbsp; <code>${esc(r.function)}</code>
            </p>
        </div>
    </div>

    <!-- ── Lesson 1: What is this error? ───────────────────── -->
    <div class="card border-blue">
        <div class="card-label">📖 What is ${esc(r.error_type)}?</div>
        <p>${esc(r.concept)}</p>
    </div>

    <!-- ── Lesson 2: What went wrong here? ─────────────────── -->
    <div class="card border-red">
        <div class="card-label">🔍 What went wrong in your code</div>
        <p>${esc(r.explanation)}</p>
        ${r.expression ? `
        <div class="expr-block">
            <span class="expr-label">Failing expression:</span>
            <code class="expr-code">${esc(r.expression)}</code>
        </div>
        <div style="margin-top:6px">Variables: ${vars}</div>` : ''}
    </div>

    <!-- ── Lesson 3: Root cause ─────────────────────────────── -->
    <div class="card border-orange">
        <div class="card-label">🎯 Root Cause</div>
        <p class="cause-text">${esc(r.root_cause)}</p>
    </div>

    <!-- ── Lesson 4: Analogy ────────────────────────────────── -->
    ${analogySection}

    <!-- ── Lesson 5: Code context ───────────────────────────── -->
    <div class="card">
        <div class="card-label">📋 Your Code (error marked with >>>)</div>
        <pre class="code-block snippet-block">${esc(r.code_snippet)}</pre>
    </div>

    <!-- ── Lesson 6: How to fix it ──────────────────────────── -->
    <div class="card border-green">
        <div class="card-label">🛠 How to Fix It — Step by Step</div>
        <ol class="fix-list">${fixLines}</ol>
    </div>

    <!-- ── Lesson 7: Corrected code ─────────────────────────── -->
    ${codeSection}

</div>
</body>
</html>`;
}

// ── Shared CSS / head ─────────────────────────────────────────────────────────

function head(): string {
  return `
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Debugger</title>
<style>
  /* ── CSS Variables ── */
  :root {
    --bg:      #0d0f18;
    --surface: #13172a;
    --surface2:#1c2035;
    --border:  #272c45;
    --text:    #dde1f5;
    --muted:   #7a80a0;
    --blue:    #5b8dee;
    --red:     #f35b6b;
    --green:   #3ecf6f;
    --orange:  #f5a623;
    --purple:  #a78bfa;
    --mono:    'Cascadia Code','Fira Code','Consolas',monospace;
    --font:    'Segoe UI',system-ui,sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.7;
    padding-bottom: 48px;
  }

  /* ── Layout ── */
  .page { max-width: 860px; margin: 0 auto; padding: 24px 20px; }

  /* ── Header ── */
  .header {
    margin-bottom: 22px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .header-top {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
  }
  .location { color: var(--muted); font-size: 13px; }

  /* ── Cards ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 14px;
  }
  .card-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
    color: var(--muted);
  }
  .border-blue   { border-left: 3px solid var(--blue); }
  .border-red    { border-left: 3px solid var(--red); }
  .border-orange { border-left: 3px solid var(--orange); }
  .border-green  { border-left: 3px solid var(--green); }
  .border-purple { border-left: 3px solid var(--purple); }

  /* ── Pills & tags ── */
  .err-pill {
    display: inline-block;
    background: #f35b6b22;
    color: var(--red);
    border: 1px solid #f35b6b55;
    border-radius: 6px;
    padding: 3px 12px;
    font-size: 15px;
    font-weight: 700;
  }
  .cache-tag {
    display: inline-block;
    background: #3ecf6f22;
    color: var(--green);
    border: 1px solid #3ecf6f55;
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
  }
  .var-tag {
    display: inline-block;
    background: var(--surface2);
    color: var(--blue);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 7px;
    font-family: var(--mono);
    font-size: 12px;
  }

  /* ── Text styles ── */
  p { color: var(--text); }
  .muted { color: var(--muted); }
  code {
    font-family: var(--mono);
    background: var(--surface2);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--text);
  }

  /* ── Expression block ── */
  .expr-block {
    margin-top: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .expr-label { color: var(--muted); font-size: 12px; }
  .expr-code  {
    font-family: var(--mono);
    background: #0a0c14;
    color: var(--red);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 13px;
  }

  /* ── Root cause text ── */
  .cause-text {
    font-size: 14.5px;
    font-weight: 500;
    color: var(--orange);
  }

  /* ── Analogy text ── */
  .analogy-text {
    font-style: italic;
    color: #c4b5fd;
    font-size: 14px;
  }

  /* ── Fix list ── */
  .fix-list {
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .fix-list li { color: var(--text); }

  /* ── Code blocks ── */
  .code-block {
    background: #090b12;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 16px;
    font-family: var(--mono);
    font-size: 12.5px;
    line-height: 1.55;
    overflow-x: auto;
    white-space: pre;
    color: #c5cdf0;
    margin-top: 8px;
  }
  .snippet-block { max-height: 260px; overflow-y: auto; }

  /* ── Copy button ── */
  .copy-btn {
    margin-top: 10px;
    background: var(--surface2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    cursor: pointer;
    transition: background .2s, color .2s;
  }
  .copy-btn:hover { background: var(--green); color: #000; }

  /* ── Loading ── */
  .loading-wrap { text-align: center; padding-top: 90px; }
  .spinner {
    width: 48px; height: 48px;
    border: 4px solid var(--border);
    border-top-color: var(--blue);
    border-radius: 50%;
    animation: spin .8s linear infinite;
    margin: 0 auto 24px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>`;
}

/** HTML-escape a string for safe insertion. */
function esc(v: string | null | undefined): string {
  if (!v) { return ''; }
  return v
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
