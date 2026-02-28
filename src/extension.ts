/**
 * extension.ts
 *
 * Main entry point for the AI Debugger VS Code extension.
 *
 * Responsibilities:
 *   1. Spawn the Python FastAPI backend on activation (if autoStart enabled)
 *   2. Register the "Run Diagnostics" command
 *   3. Coordinate: run file → capture stderr → local parse → show loading UI
 *      → send to backend → show full result + inline diagnostic
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';

import { parseLocally } from './stackTraceParser';
import { extractContext } from './codeContextExtractor';
import { analyze, isBackendAlive, AnalyzeRequest } from './backendClient';
import * as webview from './webviewPanel';

// ── State ─────────────────────────────────────────────────────────────────────

let diagnosticCollection: vscode.DiagnosticCollection;
let backendProcess: cp.ChildProcess | undefined;

// ── Activation ────────────────────────────────────────────────────────────────

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    console.log('[AI Debugger] Extension activated');

    diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-debugger');
    context.subscriptions.push(diagnosticCollection);

    // Register command
    const cmd = vscode.commands.registerCommand(
        'debugger-ext.runDiagnostics',
        () => runDiagnostics()
    );
    context.subscriptions.push(cmd);

    // Optionally auto-start the backend
    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    if (cfg.get<boolean>('autoStartBackend', true)) {
        await ensureBackendRunning(context);
    }
}

// ── Deactivation ──────────────────────────────────────────────────────────────

export function deactivate(): void {
    backendProcess?.kill();
    backendProcess = undefined;
    webview.dispose();
}

// ── Backend management ────────────────────────────────────────────────────────

async function ensureBackendRunning(context: vscode.ExtensionContext): Promise<void> {
    const alive = await isBackendAlive();
    if (alive) {
        console.log('[AI Debugger] Backend already running — skipping spawn');
        return;
    }

    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    const pythonPath = cfg.get<string>('pythonPath', 'python');

    // Backend directory is a sibling of the extension's root
    const backendDir = path.join(context.extensionPath, 'backend');
    const startScript = path.join(backendDir, 'start_backend.py');

    const apiKey = cfg.get<string>('geminiApiKey', '');
    const args = [startScript];
    if (apiKey) {
        args.push('--api-key', apiKey);
    }

    console.log('[AI Debugger] Spawning backend:', pythonPath, args.join(' '));

    backendProcess = cp.spawn(pythonPath, args, {
        cwd: backendDir,
        stdio: ['ignore', 'pipe', 'pipe'],
    });

    backendProcess.stdout?.on('data', (d) =>
        console.log('[backend]', d.toString().trim())
    );
    backendProcess.stderr?.on('data', (d) =>
        console.error('[backend]', d.toString().trim())
    );
    backendProcess.on('exit', (code) => {
        console.warn('[AI Debugger] Backend exited with code', code);
        backendProcess = undefined;
    });

    // Wait up to 6 s for the backend to become available
    for (let i = 0; i < 12; i++) {
        await sleep(500);
        if (await isBackendAlive()) {
            console.log('[AI Debugger] Backend is ready');
            return;
        }
    }

    vscode.window.showWarningMessage(
        '[AI Debugger] Backend did not start in time. ' +
        'Try running `python start_backend.py` manually in the backend/ folder.'
    );
}

// ── Main command ──────────────────────────────────────────────────────────────

async function runDiagnostics(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('[AI Debugger] No active editor.');
        return;
    }

    const filePath = editor.document.fileName;

    if (!filePath.endsWith('.py')) {
        vscode.window.showWarningMessage('[AI Debugger] Only Python files are supported.');
        return;
    }

    // Save the file first so we run the latest version
    await editor.document.save();
    diagnosticCollection.clear();

    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    const pythonPath = cfg.get<string>('pythonPath', 'python');
    const contextLines = cfg.get<number>('contextLines', 7);

    vscode.window.setStatusBarMessage('$(sync~spin) AI Debugger: running…', 30_000);

    cp.exec(`"${pythonPath}" "${filePath}"`, async (error, stdout, stderr) => {
        vscode.window.setStatusBarMessage('');

        const output = stderr || stdout || '';

        // No error at all
        if (!error && !stderr.trim()) {
            vscode.window.showInformationMessage('✅ No runtime errors detected.');
            return;
        }

        // ── Step 1: lightweight local parse for instant feedback ─────────────
        const local = parseLocally(output);

        if (!local) {
            vscode.window.showErrorMessage('[AI Debugger] Could not detect a Python error in the output.');
            return;
        }

        // Show inline diagnostic immediately
        setInlineDiagnostic(editor.document.uri, local.line, `${local.errorType}: ${local.message}`);

        // Show loading panel
        webview.showLoading(local.errorType, local.file);

        // ── Step 2: extract code context via VS Code APIs ─────────────────────
        const ctx = await extractContext(local.file, local.line, contextLines);

        // ── Step 3: send to backend ───────────────────────────────────────────
        const request: AnalyzeRequest = {
            stack_trace: output,
            code_snippet: ctx.snippet || ctx.functionBlock,
            file_path: local.file,
            language: 'python',
        };

        try {
            const result = await analyze(request);

            // Update inline diagnostic with richer message from backend
            setInlineDiagnostic(
                editor.document.uri,
                result.line,
                `${result.error_type}: ${result.possible_cause}`
            );

            webview.showResult(result);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`[AI Debugger] Backend error: ${msg}`);
            webview.showError(msg);
        }
    });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setInlineDiagnostic(
    uri: vscode.Uri,
    line: number,      // 1-indexed
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

function sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
}