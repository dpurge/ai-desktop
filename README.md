# AI Desktop

A desktop chat app: a local Python engine (FastAPI, streams replies over SSE) and a plain-JS GUI
with no framework or bundler. This is iteration 1, step 10: the engine chats with a real provider
(Ollama or OpenRouter), the model can run shell commands with your approval (see Tools), chat
history persists across restarts, and the provider, model, and API key are changed from a Settings
screen. A fake provider is available for offline demos. The GUI runs in a Tauri desktop window that
starts the engine itself.

## Requirements

[Rust](https://rustup.rs), Node.js, `uv`, and [Task](https://taskfile.dev). `task doctor` checks
that all of them are installed. Building the app needs macOS.

## Commands

- `task test` runs the engine tests (pytest), GUI tests (`node --test`), and Rust tests
  (`cargo test`). No network needed.
- `task run` opens the desktop app with the configured provider. The first run compiles the Rust
  shell, which takes a few minutes.
- `task run-fake` does the same with the offline fake provider (no network, no model).
- `task run-web` runs only the engine and serves the GUI for a browser; open the
  `http://127.0.0.1:<port>/#token=...` URL it prints. `task run-web-fake` uses the fake provider.
- `task engine:smoke -- ollama` (or `openrouter`) sends one prompt through the real provider and
  prints the reply. It is not part of `task test`.
- `task engine:lint` lints the engine with ruff.
- `task doctor` prints the versions of the build tools and fails with a message if one is missing.
- `task build` builds `installer/dist/AI Desktop.app` without running the tests.
- `task release` runs `task test`, then does the same as `task build`.
- `task installer:clean` removes the build output.

## Building the app

`task build` freezes the engine with PyInstaller (`engine/dist/backend/`), then builds the Tauri
app with the frozen engine as a resource, and copies `AI Desktop.app` to `installer/dist/`. The
first build compiles the Rust shell in release mode and takes a few minutes. See
`installer/README.md` for the steps and the bundle layout.

The app contains the Tauri shell, the GUI, and a self-contained engine under
`Contents/Resources/engine/` (the `backend` executable and its `_internal/` folder, including the
default `config.toml`, the built-in skills, and the model providers). It needs no Python, `uv`, or
network access to start.

The app is **not signed or notarized**. The first time you open a copy that was downloaded or
copied from another Mac, right-click it and choose Open, or run
`xattr -dr com.apple.quarantine "AI Desktop.app"`.

Environment variables:

- `AD_ENGINE_CMD` is the command that starts the engine, for example
  `uv run --directory ../engine python -m backend`. `task run` sets a default; the packaged app
  does not set it and starts the engine in its own `Resources/engine/` folder. Only debug builds
  honor it; a release app ignores it.
- `AD_LLM=fake` selects the offline provider.
- `AD_LOG_LEVEL` sets the uvicorn log level (default `warning`); set to `info` to see request logs.
- `AD_STATE_DIR` chooses the state folder (see Configuration).
- `AD_TOKEN` chooses the token for `task run-web`; otherwise one is generated and printed. The
  desktop app always generates its own.

## How the desktop app starts the engine

1. The Tauri shell picks a free port on 127.0.0.1 and generates a random token.
2. It starts the engine from `AD_ENGINE_CMD` with `--port <port>` and the environment variables
   `AD_TOKEN` and `AD_PARENT_PID`.
3. It opens the window with `window.__AI_DESKTOP__ = {baseUrl, token}` injected before the GUI
   scripts run; the GUI polls `/health` until the engine is ready.
4. The engine rejects requests without the token and pages from other origins.
5. The shell kills the engine when the app exits; if the app dies abruptly, the engine notices
   that `AD_PARENT_PID` is gone within a few seconds and exits too.

## Configuration

State lives in one folder: `~/Library/Application Support/ai-desktop` on macOS,
`$XDG_CONFIG_HOME/ai-desktop` (default `~/.config/ai-desktop`) on Linux, `%APPDATA%\ai-desktop` on
Windows. Set `AD_STATE_DIR` to use another folder.

`config.toml` there overrides the built-in defaults:

```toml
provider = "ollama"            # or "openrouter"
model = "gemma4:12b"

[ollama]
base_url = "http://localhost:11434"

[openrouter]
base_url = "https://openrouter.ai/api/v1"

[ui]
theme = "system"               # or "light" / "dark"

[tools.shell]
enabled = true                 # false: the model is not offered the shell tool
cwd = "~"                      # folder commands start in
timeout_s = 60                 # a command running longer is killed

[approval]
timeout_s = 600                # an unanswered approval counts as a denial

[skills]
workspace_dir = ""             # optional extra folder of skills, e.g. a project's (see Skills)

[sandbox]
enabled = false                # true: shell commands must run in the OpenShell sandbox (see Sandbox)
```

## Settings screen

Open **Settings** in the sidebar (or click the status line at the bottom of the chat). There you can:

- switch the provider between Ollama and OpenRouter, and edit each base URL;
- pick the model from the list the provider offers (Refresh reloads it). Your current model stays
  in the list even if the server does not report it, and **Other...** lets you type any model id;
- choose the theme (System follows the OS light/dark setting);
- paste an OpenRouter API key. Once saved, the screen only says "Key saved" with Replace and
  Remove buttons.

Saving applies to the next message you send; no restart is needed. Settings are written to
`config.toml` in the state folder.

### Where the API key lives

The OpenRouter key is stored in `secrets.json` in the state folder (owner-only permissions, 0600
on macOS and Linux). The engine never returns it: the settings API only reports whether a key is
set, and it never appears in responses, errors, or logs. If `OPENROUTER_API_KEY` is set in the
environment it takes precedence over the stored key, and Remove only deletes the stored one.

## Chat history

Sessions live in the state folder: `sessions.db` (SQLite index of titles, model, dates, message
counts) and `sessions/<id>.jsonl` (one message per line: `id`, `ts`, `role`, `content`, where
`content` is Markdown text). Deleting a session removes both. The sidebar lists sessions, newest
activity first; a session is auto-titled from its first message until you rename it.

## Tools

The model can use tools during a reply: `shell` (needs your approval), `ask` and `propose` (ask
you something), and placeholders for services that are not connected. `GET /tools` lists them all
with `name`, `description`, `requires_approval`, `available`, and `enabled`.

### shell

- **Every call needs your approval.** The chat shows the exact command and the folder it will run
  in, with Approve and Deny buttons. There is no "allow always". Denying, or not answering within
  `[approval] timeout_s` (600 s), tells the model the command was not run, and it can react.
- **Limits.** A command is killed (with its child processes) after `[tools.shell] timeout_s`
  (60 s). Output is cut to 32 KB, ending with `[truncated]`. Commands run in `[tools.shell] cwd`
  (default `~`) through your shell, with your permissions.
- **Stop.** The Stop button next to the message box ends the turn: pending approvals are
  cancelled and a running command is killed. Closing the app mid-turn does the same.
- **Turn off.** Set `enabled = false` under `[tools.shell]` in `config.toml`; the model is then not
  told the tool exists.
- **Try it offline.** With `task run-fake` or `task run-web-fake`, send `run: ls` and the fake
  provider calls the shell tool with `ls`, waits for your approval, then summarizes the output.
  Any other message is echoed as before.

### ask and propose

- **`ask`** puts a question in the chat, with optional answer buttons (up to 6) and a box for your
  own text. Your answer (up to 4000 characters) goes back to the model. If you do not answer within
  `[approval] timeout_s`, the model is told "No answer from the user." and the turn goes on.
- **`propose`** shows a title and details (shown as plain text; Markdown is not rendered yet) with
  Accept and Reject buttons and an optional comment (up to 2000 characters). The model is told
  `accepted` or `rejected`, followed by `: <comment>` when you wrote one. No response counts as
  rejected.
- Neither tool asks for approval: the question or proposal is itself what you are asked.
- Stop cancels a pending question or proposal and ends the turn, as with approvals.
- Try them offline with `task run-fake` or `task run-web-fake`: send `ask: Which color?` or
  `propose: Rename project`; the fake provider calls the tool and then repeats your reply.

### Not connected yet

`gmail`, `gcal`, and `github` are listed by `GET /tools` with `available: false`. They are never
offered to the model and have no implementation; a call would only answer "<name> is not
connected yet."

A tool call is stored in the session log as an assistant message with `tool_calls` followed by a
`tool` message holding the result (OpenAI format), so reopening a session shows the calls.

## Sandbox

[NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) can confine shell commands in a sandbox.
The setting is off by default, and commands then run directly on your machine after you approve
them.

Status in this version: detect-only. Settings > Sandbox looks for the `openshell` command on your
PATH and shows one of two messages next to a checkbox that stays disabled:

- "OpenShell is not installed ...": the command was not found.
- "OpenShell was found, but sandboxed execution is not wired up yet ...": it is installed, but
  this version cannot run commands through it.

If `config.toml` sets `[sandbox] enabled = true` anyway, every shell call fails with "Sandbox is
enabled but unavailable: <reason>" and the command is not run. It never falls back to running on
your machine. Set it back to `false` in Settings or in the file to run commands again.

The roadmap item `openshell-sandbox` wires the real execution.

## Skills

A skill is reusable instructions for the model. It is a folder with a `SKILL.md` file: a
frontmatter block with `name` and `description`, then Markdown instructions.

```
skills/
  shout/
    SKILL.md
```

```markdown
---
name: shout
description: Reply in capital letters
---

Write the whole reply in capital letters.
```

- **Frontmatter.** One `key: value` per line; values may be quoted. `name` is required: lowercase
  letters, digits, and `-`, up to 64 characters. The body is limited to 32 KB.
- **Where skills live**, lowest to highest precedence (a later one replaces a skill with the same
  name):
  1. built in (shipped with the app; currently `concise-summary`);
  2. global: `skills/` in the state folder (`AD_STATE_DIR`, or the OS default);
  3. workspace: the folder set in `[skills] workspace_dir` in `config.toml` (it holds skill
     folders directly).
- **How the model uses them.** The system prompt lists each skill's name and description; the model
  calls the `load_skill` tool (no approval needed) to read the one that matches the task. The tool
  is offered only when at least one skill exists.
- **No restart needed.** Skills are re-scanned on every message, so a new folder works at once.
- **Broken skills** are skipped, never stop the app, and are reported. `GET /skills` returns
  `{"skills": [{name, description, source}], "problems": [{path, message}]}`, where `path` is the
  folder name.
- **Try it offline.** With `task run-fake` or `task run-web-fake`, send `skill: concise-summary`
  and the fake provider calls `load_skill` with that name, then repeats the first line of the
  result. An unknown name shows the list of available skills.
