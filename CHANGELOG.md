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
- Taskfile-driven `build`, `test`, `run` and `release`, producing a macOS `.app`.
