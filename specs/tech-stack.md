---
version: 2
status: approved
updated: 2026-10-06
---

# AI Desktop Tech Stack

## Languages & runtimes

- **Python 3.11+** — engine backend (FastAPI + Uvicorn)
- **JavaScript (ES modules)** — plain JS, HTML, and CSS for the GUI; no framework, no Tailwind, no bundler
- **Rust (stable)** — Tauri 2 shell for desktop app lifecycle

## Frameworks & libraries

- **FastAPI** — REST API for the engine (sessions, config, approvals)
- **Uvicorn** — ASGI server for FastAPI, runs as a sidecar on 127.0.0.1
- **aisuite** — unified LLM client (Ollama and OpenRouter providers)
- **SQLite3** — session index
- **Tauri 2** — desktop shell; spawns and supervises the engine sidecar
- **Custom web components** — light DOM, one folder per component, plain CSS with design tokens in a shared `theme.css` (light and dark)

## Infrastructure & tooling

- **Platforms**: Linux, Windows, macOS, in that priority order; platform-specific code (paths, sidecar packaging, sandbox availability) is isolated behind small, tested helpers
- **Build**: root `Taskfile.yml` with `build`, `test`, `run`, `release` tasks, delegating to per-part tasks (engine/, desktop/, installer/)
  - Engine sidecar: PyInstaller standalone binary per platform
  - GUI: plain files with no bundler; in development Tauri serves desktop/gui directly, and the release bundle task copies a filtered copy (without node_modules, tests or test support) into the app
  - Installer: scripts and config under installer/
- **Test**: pytest (engine), `node --test` (GUI components), `cargo test` (Rust logic only, if any)
- **Lint & format**: ruff (Python); no JS formatter mandated
- **Package management**: pyproject.toml + uv (preferred) for the engine
- **Persistence**:
  - Sessions: SQLite index under the state directory
  - Session logs: append-only JSONL per session
  - Config: layered TOML (defaults < global state-dir config.toml)
  - Secrets: 0600 file in the state directory initially; OS keychain later
- **Release**: `release` task builds the sidecar binary and the Tauri bundle for the host platform; no CI in iteration 1

## Key conventions

- Engine listens on 127.0.0.1 and requires a per-launch token header on every request
- GUI talks to the engine over REST (sessions, config), Server-Sent Events (streamed tokens and events), and POST (approval answers)
- Components follow `ad-<name>/component.js` + `component.css` + `component.test.js`
- Skills are folders with a `SKILL.md`; global skills live in the state directory, optional per-workspace skills override them
- Tools (shell, ask, propose, gmail, gcal, github) register with an approval flow; real OAuth connectors come after iteration 1
- NVIDIA OpenShell sandbox for the shell tool is optional and off by default
- No hardcoded credentials; API keys are read from the secrets file or environment and never logged
