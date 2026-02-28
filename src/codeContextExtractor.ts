/**
 * codeContextExtractor.ts
 *
 * Reads a source file via VS Code workspace APIs and extracts:
 *   - the exact error line
 *   - N surrounding lines (configurable)
 *   - the full function block containing the line
 */

import * as vscode from 'vscode';
import * as path from 'path';

export interface CodeContext {
    snippet: string;      // surrounding lines
    errorLine: string;    // the exact line that caused the error
    functionBlock: string; // best-effort full function body
}

/**
 * Extracts code context around `line` from `filePath`.
 * Falls back to empty strings if the file is unreadable.
 */
export async function extractContext(
    filePath: string,
    line: number,          // 1-indexed, as reported by Python
    contextLines: number = 7
): Promise<CodeContext> {
    try {
        const uri = vscode.Uri.file(filePath);
        const bytes = await vscode.workspace.fs.readFile(uri);
        const text = Buffer.from(bytes).toString('utf8');
        const lines = text.split('\n');

        const zeroLine = line - 1;                          // 0-indexed
        const start = Math.max(0, zeroLine - contextLines);
        const end = Math.min(lines.length - 1, zeroLine + contextLines);

        // Annotate the error line with a marker
        const snippetLines = lines.slice(start, end + 1).map((l, i) => {
            const lineNo = start + i + 1;
            const marker = lineNo === line ? '>>> ' : '    ';
            return `${marker}${lineNo}: ${l}`;
        });

        const functionBlock = extractFunctionBlock(lines, zeroLine);

        return {
            snippet: snippetLines.join('\n'),
            errorLine: lines[zeroLine] ?? '',
            functionBlock,
        };
    } catch {
        return { snippet: '', errorLine: '', functionBlock: '' };
    }
}

/**
 * Walk upward from the error line to find the enclosing `def` or `class`,
 * then walk downward to find the end of that block.
 */
function extractFunctionBlock(lines: string[], zeroLine: number): string {
    // Walk up to find the nearest def/class
    let defLine = -1;
    for (let i = zeroLine; i >= 0; i--) {
        if (/^\s*(def |class |async def )/.test(lines[i])) {
            defLine = i;
            break;
        }
    }

    if (defLine === -1) {
        // No enclosing function — return a wider window
        const s = Math.max(0, zeroLine - 10);
        const e = Math.min(lines.length - 1, zeroLine + 10);
        return lines.slice(s, e + 1).join('\n');
    }

    // Determine indentation level of the def
    const baseIndent = (lines[defLine].match(/^(\s*)/) ?? ['', ''])[1].length;

    // Walk down until we hit a line with equal or lesser indentation (non-blank)
    let endLine = defLine + 1;
    while (endLine < lines.length) {
        const l = lines[endLine];
        if (l.trim() !== '') {
            const indent = (l.match(/^(\s*)/) ?? ['', ''])[1].length;
            if (indent <= baseIndent && endLine > defLine + 1) {
                break;
            }
        }
        endLine++;
    }

    return lines.slice(defLine, endLine).join('\n');
}
