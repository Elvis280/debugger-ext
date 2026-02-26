# debugger-ext

**AI-assisted debugging diagnostics for Python files in VS Code.**

`debugger-ext` automatically runs your active Python file, parses any runtime errors, and surfaces them directly in the editor as VS Code diagnostics — no manual output reading required.

---

## Features

- **One-command diagnostics** — Run the `Diagnostics: Run Diagnostics` command to execute the active Python file and catch runtime errors instantly.
- **Inline error highlighting** — Errors are pinpointed to the exact line number and shown in the Problems panel with the source label `AI Debugger`.
- **Python exception parsing** — Automatically detects all standard Python exception types (e.g. `TypeError`, `ValueError`, `IndexError`, etc.) from the interpreter's stack trace.
- **Zero configuration** — Works out of the box as long as `python` is available on your system PATH.

---

## Requirements

- **Python** must be installed and accessible via the `python` command in your terminal.
- The extension targets **VS Code `^1.109.0`**.

---

## Usage

1. Open any `.py` file in the editor.
2. Open the Command Palette (`Ctrl+Shift+P` on Windows/Linux, `Cmd+Shift+P` on macOS).
3. Run **`Diagnostics: Run Diagnostics`**.
4. If your script has a runtime error, the offending line will be highlighted in the editor and the error will appear in the **Problems** panel.
5. If no errors are found, a notification confirms: _"No runtime errors found."_

---

## Extension Settings

This extension does not contribute any VS Code settings at this time.

---

## Known Issues

- Only **Python runtime errors** are detected. Static/type errors caught at parse time may not always be reported.
- The extension uses the system `python` command. If your environment uses `python3` or a virtual environment, ensure the correct interpreter is on your PATH or activate the environment before launching VS Code.
- Only the **active editor file** is executed — multi-file projects with imports may produce errors if dependencies are not resolvable from the file's directory.

---

## Release Notes

### 0.0.1

- Initial release.
- Executes the active Python file and parses runtime errors.
- Surfaces errors as VS Code diagnostics with line-level precision.
