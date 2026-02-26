# Change Log

All notable changes to the **debugger-ext** extension will be documented in this file.

## [0.0.1] - 2026-02-27

### Added
- Initial release of `debugger-ext`.
- `Diagnostics: Run Diagnostics` command that executes the active Python file.
- Python runtime error parsing — detects standard exception types (e.g. `TypeError`, `ValueError`, `IndexError`) from the interpreter's stack trace.
- Inline diagnostics surfaced at the exact error line in the VS Code editor via the Problems panel, sourced as `AI Debugger`.
- Notification message when no runtime errors are detected.