# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Desktop chat app (Tauri shell, Python engine, plain-JS interface) that streams replies from Ollama (local or remote) or OpenRouter.
- Persistent chat sessions: create, rename, delete, and history that survives restarts.
- Settings screen: provider, Ollama URL, write-only OpenRouter API key, model picker populated from the provider, and a light/dark/system theme.
- Tools with approval cards: `shell` (approval on every call), `ask` and `propose`; `gmail`, `gcal` and `github` are registered as "not connected yet" stubs.
- Folder-based skills (`SKILL.md`) with a built-in `concise-summary` example.
- Optional NVIDIA OpenShell sandbox switch, off by default; unavailable in this version, and shell calls fail closed instead of running on the host.
- Taskfile-driven `build`, `test`, `run` and `release`, producing a macOS `.app` or a Windows NSIS installer (`task build` bundles `app` on macOS and `nsis` on Windows; the GUI copy no longer needs `rsync`).

### Fixed

- OpenRouter replies stream again: aisuite's own OpenRouter provider has no streaming support, so OpenRouter now runs through aisuite's OpenAI-compatible provider with OpenRouter's base URL.
- Shell calls now work on Windows: commands run through the host's native shell (`cmd.exe` via `COMSPEC`), and executor output is normalized to LF on every platform.
- A timed-out or cancelled shell command now stops its whole process tree on Windows (`taskkill /F /T`); POSIX keeps the process-group kill.
- State-folder resolution uses POSIX path semantics for the Linux branch, so `XDG_CONFIG_HOME` is honored even when the engine runs on Windows.
- The shell approval card shows a configured POSIX-style working directory as entered instead of mangling it into a Windows path.
