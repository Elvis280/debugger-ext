/**
 * stackTraceParser.ts
 *
 * Lightweight local parser — extracts just the file path and line number
 * from the Python stderr so the extension can highlight the error inline
 * BEFORE the backend responds.  Full parsing happens in the backend.
 */

export interface LocalParsedError {
    file: string;
    line: number;
    errorType: string;
    message: string;
}

const FRAME_RE = /File "([^"]+)", line (\d+)/g;
const EXCEPTION_RE = /^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|KeyboardInterrupt|SystemExit|GeneratorExit|StopIteration|StopAsyncIteration|BaseException)):\s*(.*)$/m;

/**
 * Returns the deepest file/line pair and exception info from Python stderr,
 * or null if none could be found.
 */
export function parseLocally(stderr: string): LocalParsedError | null {
    const frames: Array<{ file: string; line: number }> = [];
    let match: RegExpExecArray | null;

    FRAME_RE.lastIndex = 0;
    while ((match = FRAME_RE.exec(stderr)) !== null) {
        frames.push({ file: match[1], line: parseInt(match[2], 10) });
    }

    if (frames.length === 0) {
        return null;
    }

    const deepest = frames[frames.length - 1];
    const excMatch = EXCEPTION_RE.exec(stderr);

    return {
        file: deepest.file,
        line: deepest.line,
        errorType: excMatch ? excMatch[1] : 'RuntimeError',
        message: excMatch ? excMatch[2].trim() : 'Runtime error',
    };
}
