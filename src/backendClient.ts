/**
 * backendClient.ts
 *
 * HTTP client that sends an AnalyzeRequest to the FastAPI backend
 * and returns the AnalyzeResponse.  Uses the built-in Node.js `http`
 * module so no extra bundling dependencies are needed.
 */

import * as http from 'http';
import * as https from 'https';
import * as vscode from 'vscode';

// ── Types mirroring the Pydantic models ──────────────────────────────────────

export interface AnalyzeRequest {
    stack_trace: string;
    code_snippet: string;
    file_path: string;
    language: string;
}

export interface AnalyzeResponse {
    error_type: string;
    file: string;
    line: number;
    function: string;
    node_type: string | null;
    expression: string | null;
    variables: string[];
    possible_cause: string;
    code_snippet: string;
    explanation: string;
    root_cause: string;
    suggested_fix: string;
    improved_code: string;
    cached: boolean;
    language: string;
}

// ── Config helpers ───────────────────────────────────────────────────────────

function getBackendUrl(): string {
    const cfg = vscode.workspace.getConfiguration('debugger-ext');
    return cfg.get<string>('backendUrl', 'http://localhost:7823');
}

// ── Core request helper ───────────────────────────────────────────────────────

function postJson<T>(url: string, body: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify(body);
        const parsed = new URL(url);
        const isHttps = parsed.protocol === 'https:';
        const lib = isHttps ? https : http;

        const options: http.RequestOptions = {
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname + parsed.search,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(payload),
            },
        };

        const req = lib.request(options, (res) => {
            const chunks: Buffer[] = [];
            res.on('data', (chunk) => chunks.push(chunk));
            res.on('end', () => {
                const raw = Buffer.concat(chunks).toString('utf8');
                if (res.statusCode && res.statusCode >= 400) {
                    reject(new Error(`Backend returned HTTP ${res.statusCode}: ${raw}`));
                    return;
                }
                try {
                    resolve(JSON.parse(raw) as T);
                } catch (e) {
                    reject(new Error(`Invalid JSON from backend: ${raw}`));
                }
            });
        });

        req.on('error', reject);
        req.setTimeout(30_000, () => {
            req.destroy(new Error('Backend request timed out after 30 s'));
        });

        req.write(payload);
        req.end();
    });
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Sends the request to /analyze and returns the full AnalyzeResponse.
 * Throws on network / backend errors so the caller can handle UI feedback.
 */
export async function analyze(req: AnalyzeRequest): Promise<AnalyzeResponse> {
    const base = getBackendUrl().replace(/\/$/, '');
    return postJson<AnalyzeResponse>(`${base}/analyze`, req);
}

/**
 * Pings /health — resolves true if backend is up, false otherwise.
 */
export async function isBackendAlive(): Promise<boolean> {
    const base = getBackendUrl().replace(/\/$/, '');
    const url = `${base}/health`;
    const parsed = new URL(url);
    const isHttps = parsed.protocol === 'https:';
    const lib = isHttps ? https : http;

    return new Promise((resolve) => {
        const req = lib.get(url, (res) => {
            res.resume();
            resolve(res.statusCode === 200);
        });
        req.on('error', () => resolve(false));
        req.setTimeout(3_000, () => { req.destroy(); resolve(false); });
    });
}
