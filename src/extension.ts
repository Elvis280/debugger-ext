import * as vscode from 'vscode';
import { exec } from 'child_process';

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {

    console.log("AI Debugger extension activated");

    diagnosticCollection = vscode.languages.createDiagnosticCollection("ai-debugger");

    const disposable = vscode.commands.registerCommand(
        'debugger-ext.runDiagnostics',
        runDiagnostics
    );

    context.subscriptions.push(disposable);
}

function runDiagnostics() {

    const editor = vscode.window.activeTextEditor;

    if (!editor) {
        vscode.window.showErrorMessage("No active editor.");
        return;
    }

    const filePath = editor.document.fileName;

    diagnosticCollection.clear();

    // safer python execution
    const command = `python "${filePath}"`;

    exec(command, (error, stdout, stderr) => {

        console.log("STDOUT:", stdout);
        console.log("STDERR:", stderr);

        // If no error happened
        if (!error && !stderr) {
            vscode.window.showInformationMessage("No runtime errors found.");
            return;
        }

        const parsed = parsePythonError(stderr || stdout);

        console.log("Parsed error:", parsed);

        if (!parsed) {
            vscode.window.showErrorMessage("Could not parse Python error.");
            return;
        }

        const { line, message } = parsed;

        const range = new vscode.Range(
            new vscode.Position(line - 1, 0),
            new vscode.Position(line - 1, 200)
        );

        const diagnostic = new vscode.Diagnostic(
            range,
            message,
            vscode.DiagnosticSeverity.Error
        );

        diagnostic.source = "AI Debugger";

        console.log("Created diagnostic:", diagnostic);

        diagnosticCollection.set(editor.document.uri, [diagnostic]);
    });
}

function parsePythonError(output: string) {

    const lines = output.split("\n");

    let lineNumber: number | null = null;
    let message = "";

    for (const line of lines) {

        // Match stack trace lines
        const match = line.match(/File "(.+)", line (\d+)/);

        if (match) {
            lineNumber = parseInt(match[2]);
        }

        // Detect any Python exception
        if (line.match(/[A-Za-z]+Error:/)) {
            message = line.trim();
        }
    }

    if (lineNumber === null) {
        return null;
    }

    return {
        line: lineNumber,
        message: message || "Python runtime error"
    };
}

export function deactivate() {}