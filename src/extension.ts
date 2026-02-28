/**
 * extension.ts
 * ─────────────
 * Main entry point for the AI Python Debugger VS Code extension.
 *
 * What this file does:
 *  1. Creates a VS Code Output Channel called "AI Debugger" so that all
 *     backend print() / logging output streams directly into the VS Code
 *     terminal panel — visible at View → Output → "AI Debugger".
 *  2. On activation, spawns the Python FastAPI backend as a child process
 *     (unless a remote URL is configured or the backend is already running).
 *  3. Registers the "Run Diagnostics" command which:
 *       a. Runs the active Python file and captures stderr
 *       b. Instantly highlights the error line (local parse → no wait)
 *       c. Extracts code context using VS Code workspace FS APIs
 *       d. POSTs to the backend /analyze endpoint
 *       e. Renders the full AI result in a styled webview panel
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';

import { parseLocally } from './stackTraceParser';
import { extractContext } from './codeContextExtractor';
import {
    analyze, isBackendAlive,
    AnalyzeRequest
} from './backendClient';
import * as webview from './webviewPanel';

// ── Module-level state ────────────────────────────────────────────────────────

/** Inline red-squiggle diagnostics collection. */
let diagnosticCollection: vscode.DiagnosticCollection;

/** Handle to the spawned backend process (null when using a remote backend). */
let backendProcess: cp.ChildProcess | undefined;

/**
 * Shared Output Channel — backend print() / logging lines are piped here
 * so the developer can see the full analysis pipeline in VS Code's
 * terminal panel without opening a separate terminal.
 *
 * View it: View menu → Output → select "AI Debugger" in the dropdown.
 */
let outputChannel: vscode.OutputChannel;


// ── Activation ────────────────────────────────────────────────────────────────

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // Create the Output Channel first — it must exist before the backend spawns
    outputChannel = vscode.window.createOutputChannel('AI Debugger');
    context.subscriptions.push(outputChannel);

    outputChannel.appendLine('[AI Debugger] Extension activated');
    outputChannel.appendLine(`[AI Debugger] Extension path: ${context.extensionPath}`);
    outputChannel.show(true);   // bring Output panel into focus (non-stealing)

    // Inline diagnostic collection shown as red squiggles in the editor
    diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-debugger');
    context.subscriptions.push(diagnosticCollection);

    // Register the primary command
    const cmd = vscode.commands.registerCommand(
        'debugger-ext.runDiagnostics',
        () => runDiagnostics()
    );
    context.subscriptions.push(cmd);

    // Optionally auto-start the Python backend
    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    if (cfg.get<boolean>('autoStartBackend', true)) {
        await ensureBackendRunning(context);
    }
}


// ── Deactivation ──────────────────────────────────────────────────────────────

export function deactivate(): void {
    outputChannel?.appendLine('[AI Debugger] Deactivating — killing backend process');
    backendProcess?.kill();
    backendProcess = undefined;
    webview.dispose();
}


// ── Backend lifecycle management ──────────────────────────────────────────────

/**
 * Check whether the backend is already running (e.g. from a previous session
 * or a manually started process).  If not, spawn it as a child process and
 * pipe its stdout/stderr into the VS Code Output Channel.
 */
async function ensureBackendRunning(context: vscode.ExtensionContext): Promise<void> {
    outputChannel.appendLine('[AI Debugger] Checking if backend is already running…');

    const alive = await isBackendAlive();
    if (alive) {
        outputChannel.appendLine('[AI Debugger] Backend already running — skipping spawn');
        return;
    }

    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    const pythonPath = cfg.get<string>('pythonPath', 'python');
    const backendDir = path.join(context.extensionPath, 'backend');
    const startScript = path.join(backendDir, 'start_backend.py');

    // Forward the Gemini API key from settings as a CLI argument
    const apiKey = cfg.get<string>('geminiApiKey', '');
    const args = [startScript];
    if (apiKey) {
        args.push('--api-key', apiKey);
    }

    outputChannel.appendLine(`[AI Debugger] Spawning backend: ${pythonPath} ${args.join(' ')}`);

    backendProcess = cp.spawn(pythonPath, args, {
        cwd: backendDir,
        stdio: ['ignore', 'pipe', 'pipe'],  // capture stdout and stderr
    });

    // ── Pipe backend output → VS Code Output Channel ──────────────────────
    // Every print() and logging line from the Python process appears here.
    backendProcess.stdout?.on('data', (data: Buffer) => {
        const lines = data.toString().trim().split('\n');
        lines.forEach(line => outputChannel.appendLine(line));
    });

    backendProcess.stderr?.on('data', (data: Buffer) => {
        const lines = data.toString().trim().split('\n');
        lines.forEach(line => outputChannel.appendLine(`[stderr] ${line}`));
    });

    backendProcess.on('exit', (code) => {
        outputChannel.appendLine(`[AI Debugger] Backend exited with code ${code}`);
        backendProcess = undefined;
    });

    // Poll for readiness — check /health up to 12 times (6 seconds)
    outputChannel.appendLine('[AI Debugger] Waiting for backend to become ready…');
    for (let i = 0; i < 12; i++) {
        await sleep(500);
        if (await isBackendAlive()) {
            outputChannel.appendLine('[AI Debugger] Backend is ready');
            vscode.window.setStatusBarMessage('$(check) AI Debugger backend ready', 4000);
            return;
        }
    }

    // Backend did not start in time — warn but do not abort
    outputChannel.appendLine('[AI Debugger] WARNING: Backend did not start in time');
    vscode.window.showWarningMessage(
        '[AI Debugger] Backend did not start. ' +
        'Run `python start_backend.py` in the backend/ folder, ' +
        'then try again.  Check the Output panel for details.'
    );
}


// ── Main command: Run Diagnostics ─────────────────────────────────────────────

/**
 * Full analysis pipeline triggered by the "Run Diagnostics" command:
 *
 *  save → exec Python → capture stderr → local parse (instant squiggle)
 *  → extract code context → POST /analyze → show webview result
 */
async function runDiagnostics(): Promise<void> {
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
        vscode.window.showErrorMessage('[AI Debugger] No active editor.');
        return;
    }

    const filePath = editor.document.fileName;

    if (!filePath.endsWith('.py')) {
        vscode.window.showWarningMessage('[AI Debugger] Only Python (.py) files are supported.');
        return;
    }

    // Save first so we always analyse the latest version on disk
    await editor.document.save();
    diagnosticCollection.clear();

    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    const pythonPath = cfg.get<string>('pythonPath', 'python');
    const contextLines = cfg.get<number>('contextLines', 7);

    outputChannel.appendLine(`\n${'─'.repeat(60)}`);
    outputChannel.appendLine(`[AI Debugger] Running: ${pythonPath} "${filePath}"`);
    vscode.window.setStatusBarMessage('$(sync~spin) AI Debugger: running…', 30_000);

    // ── Execute the Python file ───────────────────────────────────────────────
    cp.exec(`"${pythonPath}" "${filePath}"`, async (error, stdout, stderr) => {
        vscode.window.setStatusBarMessage('');
        const output = stderr || stdout || '';

        outputChannel.appendLine(`[AI Debugger] Process exited (error=${!!error})`);

        // No error — nothing to analyse
        if (!error && !stderr.trim()) {
            outputChannel.appendLine('[AI Debugger] No runtime errors detected');
            vscode.window.showInformationMessage('AI Debugger: No runtime errors detected.');
            return;
        }

        outputChannel.appendLine('[AI Debugger] Captured output:');
        output.split('\n').forEach(l => outputChannel.appendLine(`  ${l}`));

        // ── Step 1: Lightweight local parse → instant squiggle ────────────────
        const local = parseLocally(output);

        if (!local) {
            outputChannel.appendLine('[AI Debugger] Could not detect a Python error in output');
            vscode.window.showErrorMessage('[AI Debugger] Could not detect a Python error in output.');
            return;
        }

        outputChannel.appendLine(
            `[AI Debugger] Local parse: ${local.errorType} at line ${local.line}`
        );

        // Show an immediate inline diagnostic while the backend processes
        setInlineDiagnostic(editor.document.uri, local.line, `${local.errorType}: ${local.message}`);

        // Show loading state in the webview
        webview.showLoading(local.errorType, local.file);

        // ── Step 2: Extract code context via VS Code workspace FS ─────────────
        outputChannel.appendLine('[AI Debugger] Extracting code context…');
        const ctx = await extractContext(local.file, local.line, contextLines);

        // ── Step 3: POST to backend /analyze ──────────────────────────────────
        outputChannel.appendLine('[AI Debugger] Sending to backend /analyze…');

        const request: AnalyzeRequest = {
            stack_trace: output,
            code_snippet: ctx.snippet || ctx.functionBlock,
            file_path: local.file,
            language: 'python',
        };

        try {
            const result = await analyze(request);

            // Update squiggle with the richer backend message
            setInlineDiagnostic(
                editor.document.uri,
                result.line,
                `${result.error_type}: ${result.possible_cause}`
            );

            // Print teacher-style analysis to the Output Channel (terminal)
            printResultToChannel(result);

            // Render full result in the webview panel
            webview.showResult(result);

        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            outputChannel.appendLine(`[AI Debugger] Backend error: ${msg}`);
            vscode.window.showErrorMessage(`[AI Debugger] Backend error: ${msg}`);
            webview.showError(msg);
        }
    });
}


// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Prints a teacher-style formatted analysis to the VS Code Output Channel
 * so the user can read the full explanation directly in the terminal panel
 * WITHOUT opening the webview.
 *
 * Layout:
 *   === ERROR ===========
 *   [Concept]   what is this error type?
 *   [What happened] specific explanation
 *   [Root Cause] precise cause
 *   [Analogy]   memorable real-world analogy
 *   [How to Fix] numbered steps
 *   [Improved Code] corrected snippet
 */
function printResultToChannel(r: import('./backendClient').AnalyzeResponse): void {
    const SEP = '='.repeat(60);
    const sep2 = '-'.repeat(60);
    const file = r.file.split(/[\\/]/).pop() ?? r.file;

    outputChannel.appendLine('');
    outputChannel.appendLine(SEP);
    outputChannel.appendLine(`  ${r.error_type}  |  ${file}:${r.line}  |  ${r.function}`);
    outputChannel.appendLine(SEP);

    outputChannel.appendLine('');
    outputChannel.appendLine('  WHAT IS THIS ERROR?');
    outputChannel.appendLine(sep2);
    outputChannel.appendLine(`  ${r.concept}`);

    outputChannel.appendLine('');
    outputChannel.appendLine('  WHAT WENT WRONG IN YOUR CODE?');
    outputChannel.appendLine(sep2);
    outputChannel.appendLine(`  ${r.explanation}`);
    if (r.expression) {
        outputChannel.appendLine(`  Failing expression: ${r.expression}`);
        if (r.variables.length) {
            outputChannel.appendLine(`  Variables:          ${r.variables.join(', ')}`);
        }
    }

    outputChannel.appendLine('');
    outputChannel.appendLine('  ROOT CAUSE');
    outputChannel.appendLine(sep2);
    outputChannel.appendLine(`  ${r.root_cause}`);

    if (r.analogy) {
        outputChannel.appendLine('');
        outputChannel.appendLine('  THINK OF IT LIKE THIS...');
        outputChannel.appendLine(sep2);
        outputChannel.appendLine(`  ${r.analogy}`);
    }

    outputChannel.appendLine('');
    outputChannel.appendLine('  HOW TO FIX IT');
    outputChannel.appendLine(sep2);
    r.step_by_step_fix.split(/\n/).filter(l => l.trim()).forEach(l => {
        outputChannel.appendLine(`  ${l}`);
    });

    if (r.improved_code) {
        outputChannel.appendLine('');
        outputChannel.appendLine('  IMPROVED CODE');
        outputChannel.appendLine(sep2);
        r.improved_code.split(/\n/).forEach(l => {
            outputChannel.appendLine(`  ${l}`);
        });
    }

    outputChannel.appendLine('');
    outputChannel.appendLine(`  cached: ${r.cached}`);
    outputChannel.appendLine(SEP);
    outputChannel.appendLine('');

    // Bring the Output Channel into view
    outputChannel.show(true);
}

/**
 * Place a single red-squiggle Diagnostic at the given 1-indexed line.
 */
function setInlineDiagnostic(
    uri: vscode.Uri,
    line: number,    // 1-indexed
    message: string
): void {
    const zeroLine = Math.max(0, line - 1);
    const range = new vscode.Range(
        new vscode.Position(zeroLine, 0),
        new vscode.Position(zeroLine, 500)
    );
    const diagnostic = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Error);
    diagnostic.source = 'AI Debugger';
    diagnosticCollection.set(uri, [diagnostic]);
}

/** Simple promise-based sleep utility. */
function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}