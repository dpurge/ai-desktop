---
title: Add wired shell — engine, Tauri GUI, chat, sessions, settings, tools, skills
kind: feature
status: done
version: 1
updated: 2026-10-06
---

# Iteration 1: Wired Shell

## Problem / Motivation

Deliver the first complete, runnable "wired shell" of AI Desktop: a working desktop chat app that connects to Ollama (local or remote) or OpenRouter, maintains persistent sessions, allows configuration without friction, and provides a framework for tools and skills. This iteration wires together all major components end-to-end:

- **Engine** (FastAPI backend): unified LLM client, session management, settings persistence, tool execution loop with approval gates, skills loader, SSE streaming
- **Tauri shell** (desktop container): spawns engine sidecar, injects connection token, kills sidecar on exit, no orphaned processes
- **Plain-JS GUI** (no framework/bundler): chat view with streaming replies, session sidebar, settings form, tool approval cards, message text shown as-is (Markdown is not rendered yet)
- **Tool framework**: `shell` (requires per-call approval), `ask` (question card), `propose` (decision card), and stubs for gmail/gcal/github
- **Skills system**: folder-based with SKILL.md frontmatter, loaded from state directory
- **Build/test root Taskfile**: `task test` (pytest + node --test + cargo test, no network/real LLM), `task run` (desktop app), `task release` (macOS .app bundle)

**Key assumptions recorded here:**
- macOS-only CI/build verification this iteration; code is cross-platform by design
- Messages are Markdown by contract (stored and sent as Markdown text); iteration 1 displays them as plain text via textContent, and a later iteration adds Markdown rendering with a sanitizer
- Shell approval is per-call only; no "allow always"
- Engine serves GUI locally in dev mode via `--gui-dir`; production uses Tauri resources
- aisuite 0.2.0 is verified to have Ollama and OpenRouter providers and to accept streaming calls with tool schemas
- `tomli-w` added to dependencies for writing config.toml

## Acceptance Criteria

1. `task test` runs pytest (engine) + node --test (GUI) + cargo test (Rust) in parallel and passes with no network, no real LLM, and no real provider API calls; fake provider returns canned replies.

2. `task run` starts the Tauri desktop app; window shows sessions sidebar, chat view, settings button, and status bar; engine sidecar is spawned on 127.0.0.1 with a per-launch random token, 0-length timeout for graceful shutdown, and killed on app exit (no orphaned process).

3. Settings route (GET,PUT /settings, PUT,DELETE /settings/api-key) persists provider choice, Ollama base URL, and OpenRouter API key to config.toml/secrets file (0600 mode on Unix); key is write-only and never returned by API or logs; model list is fetched from provider when changed.

4. Chat (POST /sessions/{id}/messages over text/event-stream): user message is streamed token-by-token; reply is a single assistant message in OpenAI format; cancel stops a turn; errors (invalid key, unreachable host) render as readable text in the chat transcript; SSE events include turn_started, text_delta, tool_call, interaction_required, interaction_resolved, tool_result, error, turn_done.

5. Sessions (GET,POST /sessions; GET,PATCH,DELETE /sessions/{id}): create, list, rename, delete, switch; history persists across app restarts via SQLite index (id, title, renamed, model, created_at, updated_at, message_count) and JSONL log (one OpenAI-format message per line); session IDs validated against path traversal (UUID format).

6. Tools (GET /tools, POST /interactions/{id}): `shell` (shows command+cwd, requires approval every call, 60s timeout, 32KB output cap, can be disabled in config), `ask` (question card, answer returned to model), `propose` (card with accept/reject + optional comment); gmail/gcal/github registered as stubs returning "not connected yet"; approval timeout 600s treated as denial; cancel resolves pending interactions.

7. Skills (GET /skills, GET /catalog): folder-based with SKILL.md (frontmatter name/description), loaded from state-dir skills/ folder and optional workspace-dir; catalog listed in system prompt; `load_skill` tool returns SKILL.md body; one example skill `concise-summary` shipped.

8. OpenShell (Executor protocol, sandbox toggle in settings): detect-only OpenShellExecutor; sandbox toggle off by default, shows "not available" when detector doesn't find OpenShell; shell tool runs via LocalExecutor.

9. Security: every engine route requires X-AD-Token header; Origin gate (tauri://localhost, http(s)://tauri.localhost, localhost/127.0.0.1 on any port; others return 403); GUI renders model output via textContent only, never innerHTML.

10. `task release` produces a macOS .app bundle containing PyInstaller onedir engine sidecar; the .app launches, loads settings, and chats with a real provider.

11. Code readability: modules small and single-purpose; no hardcoded references to any external product or service name in code or docs; ruff passes without warnings.

12. GUI uses no framework, no bundler, no Tailwind; components follow ad-*/component.js/component.css/component.test.js layout; design tokens in theme.css (light/dark).

## Approach

### Key decisions

| Decision | Choice | Rejected alternative |
|----------|--------|----------------------|
| Turn transport | POST /sessions/{id}/messages, text/event-stream, fetch+ReadableStream | EventSource (can't send auth headers) |
| LLM client | aisuite streaming call per turn, manual tool execution loop (max_steps=8) | aisuite max_turns (incompatible with stream=True, loses control) |
| Tool schemas | Explicit hand-written JSON dicts | Auto-generated from Python signatures |
| Interactions | Single asyncio.Future per approval/ask/propose | Polling, callbacks, or queues |
| Session history | SQLite index + JSONL per session | JSONL only (slow list), relational (overkill) |
| Sidecar packaging | PyInstaller onedir via Tauri resources | onefile (cold-start too slow) |
| State directory | Custom `paths.py` (macOS/Linux/Windows rules) | platformdirs (extra dependency) |
| Config writing | tomli-w | hand-rolled TOML writer |

### Directory tree

```
Taskfile.yml
engine/
  Taskfile.yml
  pyproject.toml
  sidecar.spec
  backend/
    __main__.py
    app.py
    auth.py
    paths.py
    config.py
    secrets_store.py
    sessions.py
    sse.py
    interactions.py
  routes/
    health.py
    sessions.py
    chat.py
    settings.py
    interactions.py
    catalog.py
  agent/
    loop.py
    prompt.py
  llm/
    base.py
    aisuite_client.py
    fake.py
    models.py
  tools/
    registry.py
    shell.py
    ask.py
    propose.py
    stubs.py
    skill.py
    executor.py
    openshell.py
  skills/
    loader.py
  defaults/
    config.toml
    skills/
      concise-summary/
        SKILL.md
  tests/
    test_*.py
desktop/
  Taskfile.yml
  gui/
    index.html
    app.js
    api.js
    store.js
    router.js
    theme.css
    app.css
    components/
      ad-session-list/
        component.js
        component.css
        component.test.js
      ad-chat-view/
        component.js
        component.css
        component.test.js
      ad-message/
        component.js
        component.css
        component.test.js
      ad-composer/
        component.js
        component.css
        component.test.js
      ad-tool-call/
        component.js
        component.css
        component.test.js
      ad-interaction-card/
        component.js
        component.css
        component.test.js
      ad-settings-form/
        component.js
        component.css
        component.test.js
      ad-model-picker/
        component.js
        component.css
      ad-dialog/
        component.js
        component.css
      ad-status-bar/
        component.js
        component.css
  src-tauri/
    Cargo.toml
    tauri.conf.json
    capabilities/
      default.json
    src/
      main.rs
      sidecar.rs
installer/
  Taskfile.yml
  README.md
```

### API surface

GET /health — engine readiness

Sessions:
- GET /sessions — list all sessions
- POST /sessions — create new session
- GET /sessions/{id} — get session metadata
- PATCH /sessions/{id} — rename session
- DELETE /sessions/{id} — delete session

Chat:
- POST /sessions/{id}/messages (Content-Type: application/json, body: {role, content}; response: text/event-stream)

Cancel:
- POST /sessions/{id}/cancel

Interactions:
- POST /interactions/{id} (body: one of {decision: "approve"|"deny"}, {answer: "..."}, {decision: "accept"|"reject", comment: "..."})

Settings:
- GET /settings
- PUT /settings
- PUT /settings/api-key
- DELETE /settings/api-key

Models:
- GET /models?provider=ollama|openrouter

Tools:
- GET /tools

Skills:
- GET /skills

### SSE events

```
event: turn_started
data: {id}

event: text_delta
data: {delta}

event: tool_call
data: {tool, args}

event: interaction_required
data: {id, type: "approval"|"ask"|"proposal", prompt, ...}

event: interaction_resolved
data: {id, decision|answer}

event: tool_result
data: {result}

event: error
data: {message}

event: turn_done
data: {reason: "complete"|"cancelled"|"error"}
```

### Persistence

**Database schema (sessions table):**
```
id TEXT PRIMARY KEY
title TEXT
renamed BOOLEAN
model TEXT
created_at TIMESTAMP
updated_at TIMESTAMP
message_count INTEGER
```

**JSONL log:** One line per OpenAI-format message `{role, content}` (or `{role, content, tool_calls, tool_results}` for multi-turn).

**Config (config.toml):**
```toml
provider = "ollama" | "openrouter"
model = "..."

[ollama]
base_url = "http://localhost:11434"

[openrouter]
base_url = "https://openrouter.io/api/v1"

[tools.shell]
enabled = true
cwd = null
timeout_s = 60

[approval]
timeout_s = 600

[sandbox]
enabled = false

[skills]
workspace_dir = null

[ui]
theme = "auto" | "light" | "dark"
```

**Secrets file (state-dir secrets.toml or similar, 0600):**
```toml
[openrouter]
api_key = "..."
```

**State directory:**
- macOS: `~/Library/Application Support/ai-desktop`
- Linux: `$XDG_CONFIG_HOME/ai-desktop` (fallback `~/.config/ai-desktop`)
- Windows: `%APPDATA%\ai-desktop`
- Override: `AD_STATE_DIR` environment variable

### Ordered implementation plan

1. **Engine with fake provider, in-memory sessions, SSE, token/origin gate; GUI api.js, ad-message, ad-composer; root + engine Taskfiles.** Verify `task test` and `task run`; see fake reply stream in browser.

2. **config.py, secrets_store.py, aisuite_client.py; real provider smoke test.** Verify `task engine:smoke -- ollama`; real reply in page.

3. **SQLite + JSONL session store, CRUD routes, ad-session-list, router.** Verify history survives engine restart.

4. **Settings routes, models endpoint, settings screen (ad-settings-form, ad-model-picker).** Verify switch provider/model in UI; persisted on restart.

5. **Tauri sidecar (sidecar.rs), token/port injection, kill-on-exit.** Verify `task run`; desktop window opens and chats.

6. **Tool registry, interactions (asyncio.Future), multi-step loop (max_steps=8), shell tool, ad-tool-call, ad-interaction-card.** Verify approve/deny/timeout/cancel in UI.

7. **ask, propose, gmail/gcal/github stubs, GET /tools.** Verify question card answered, proposal accepted/rejected.

8. **Skills loader, load_skill route, SKILL.md format, one example skill (concise-summary), catalog in system prompt.** Verify skill used in agent loop.

9. **Executor protocol, OpenShellExecutor (detect-only), toggle in settings.** Verify toggle shows "not available" when not installed; shell runs via LocalExecutor.

10. **PyInstaller sidecar spec (collect_all for dynamic imports), Tauri resource bundling, `task release`.** Verify macOS .app runs and chats.

## Affected Areas

Everything new:
- `engine/` (FastAPI app, sidecar packaging)
- `desktop/` (Tauri shell, plain-JS GUI)
- `installer/` (macOS .app packaging)
- `Taskfile.yml` (root build/test/run/release)
- `specs/` (mission, tech-stack, roadmap updated and approved; this feature spec)

## Out of Scope

- Real gmail/gcal/github OAuth connectors (oauth-connectors iteration)
- Real NVIDIA OpenShell wiring (openshell-sandbox iteration)
- Tailored skills beyond the one example
- Platform-specific installers beyond macOS .app (Windows MSI, Linux AppImage)
- Keychain/credential manager storage (keychain-secrets iteration)
- Rendering Markdown in the chat (messages are already Markdown text; only the display is plain in this iteration)
- "Allow always" tool approvals
- Linux/Windows build verification in CI
- Auto-update mechanism
- Multi-user or server mode
- Windows secrets-file ACL hardening

## Implementation Notes

Completed all 10 implementation steps as planned:

1. **Engine + fake provider + SSE + token/origin gate + GUI api.js/ad-message/ad-composer + Taskfiles** — FastAPI app (app.py, auth.py for X-AD-Token + Origin gate), fake LLM provider for testing, SSE streaming via ReadableStream (POST /sessions/{id}/messages), GUI fetch+ReadableStream transport. All routed through root and engine Taskfiles.

2. **config.py + secrets_store.py + aisuite_client.py** — Settings persisted to config.toml and secrets.json (0600 on Unix). Real aisuite client verified with Ollama gemma4:12b smoke test.

3. **SQLite + JSONL sessions + session list + router** — Sessions persisted via SQLite index (id, title, renamed, model, created_at, updated_at, message_count) and JSONL message log (one OpenAI-format message per line). GUI router (ad-session-list, nav) and CRUD routes (POST, GET, PATCH, DELETE /sessions).

4. **Settings routes + models endpoint + settings screen** — GET,PUT /settings, PUT,DELETE /settings/api-key; GET /models?provider=. Settings screen (ad-settings-form, ad-model-picker, ad-dialog for theme picker) allows switching provider and model; persists across restarts.

5. **Tauri sidecar (sidecar.rs)** — Engine spawned on 127.0.0.1 with per-launch random token, 0-length timeout for graceful shutdown, killed on app exit (parent-PID watchdog in Rust). Verified no orphaned process on SIGTERM.

6. **Tool registry + interactions (asyncio.Future) + multi-step loop (max_steps=8) + shell tool + ad-tool-call + ad-interaction-card** — Tool schemas hand-written, approval via POST /interactions/{id} with decision field. One real gemma4:12b call emitted a shell tool call (29 s). Multi-step loop runs up to 8 iterations per turn. Approval timeout 600s treated as denial.

7. **ask + propose + gmail/gcal/github stubs + GET /tools** — Three tool types (approval, ask with answer, propose with accept/reject + comment). Gmail/gcal/github registered as stubs. Not offered to the model in this iteration.

8. **Skills loader + load_skill route + SKILL.md format + concise-summary example skill + catalog in system prompt** — Folder-based with SKILL.md frontmatter (name, description). Loaded from state-dir/skills/ and optional workspace-dir. GET /skills lists all. load_skill tool returns SKILL.md body. One example skill (concise-summary) shipped in defaults/skills/.

9. **Executor protocol + OpenShellExecutor (detect-only) + toggle in settings** — Executor interface with LocalExecutor and OpenShellExecutor. OpenShell detection via `openshell` command on PATH; detector returns available=false in this version (fail-closed). Toggle in settings screen. Shell tool always runs via LocalExecutor.

10. **PyInstaller onedir sidecar (36 MB) + Tauri .app bundle (46 MB) + task release + installer/** — Sidecar frozen via sidecar.spec (36 MB, includes bundled defaults + aisuite providers). Tauri .app bundle (46 MB) created by `task release`. Bundle task filters GUI folder to exclude node_modules. Installer/ has Taskfile for macOS packaging.

**Spec-vs-built deviations documented:**
- Session IDs are `^[A-Za-z0-9_-]{1,64}$` (UUID v4 hex), not "UUID format"
- SSE `turn_done` reason is "completed" (not "complete")
- SSE `text_delta` payload field is `text` (not `delta`)
- `turn_started` event includes turn_id
- POST /sessions/{id}/messages body is `{text}` (not `{role, content}`)
- Theme values "system|light|dark" (not "auto")
- No GET /catalog; only GET /tools and GET /skills
- Secrets file is secrets.json JSON (not .toml)
- [skills] workspace_dir defaults to "" (TOML has no null)
- Shell tool settings in config.toml only (not settings screen)
- Python package structure: engine/backend/ with subpackages (not top-level routes/agent/llm)
- GUI in desktop/gui/ (not a sibling of backend)
- Extra env vars: AD_LLM (fake provider), AD_LOG_LEVEL, AD_STATE_DIR, AD_ENGINE_CMD (debug only), AD_PARENT_PID, AD_TOKEN

**Known limitations (not fixed, recorded):**
- L1: Injected token script runs on any navigation (matters when Markdown links added — needs off-origin navigation block)
- L2: Long-running commands outlive engine SIGKILL (own process session; no process-group tracking on shutdown)
- L5: Deleting API key still reports has_api_key true when OPENROUTER_API_KEY env var is set
- L6: Approval card shows bidi/control characters as-is
- L8: Spec-vs-code wording differences (listed above)

**Bugs found and fixed:**
- (a) GUI fired requests before engine was listening → added waitForEngine retry
- (b) Frozen engine lacked packaged defaults → explicit data entry in sidecar.spec
- (c) Tauri rejected frontendDist containing node_modules → bundle task filters GUI folder
- (d) Flaky Rust port test (parallel race) → made deterministic
- (e) OpenShell detection corrected from package import to `openshell` command on PATH

**Security/correctness review fixes:**
- H1: History with unanswered tool_calls after kill → repair in memory + cancelled-branch results
- M1: Shell child inherited AD_TOKEN/API keys → token popped; child env filtered of AD_*, *_API_KEY, *_TOKEN, *_SECRET
- M3: Corrupt/truncated last JSONL line → skipped with warning on append
- L3: State dirs created with 0700 perms
- L4: AD_ENGINE_CMD honored only in debug builds
- L7: User message max 100000 chars
- L2: M2 (release bundle does not embed node_modules/test files) verified by reviewing overlay

## Validation

**Test results:**
- `task test` (root): engine pytest 360 passed, GUI node:test 135 pass/0 fail, cargo 13 passed, all in parallel, exit 0
- `task engine:lint`: ruff format and linting clean
- Engine and GUI both pass integration-style tests (no real LLM, no real provider APIs, fake provider used)

**Acceptance Criteria mapping:**

| AC | Title | Status | Notes |
|---|---|---|---|
| 1 | `task test` passes pytest+node+cargo, no network/real LLM | Pass | 360+135+13 tests passed; fake provider returns canned replies |
| 2 | `task run` desktop window, sidecar on 127.0.0.1, token/timeout/kill-on-exit | Pass (engine + window requests verified); window visuals not verified | GET /health, /sessions, /settings all 200 via Tauri dev and built .app; verified SIGTERM leaves no orphan via parent-PID watchdog |
| 3 | Settings routes persist config.toml/secrets 0600 mode | Pass | Frozen sidecar serves built-in config; coordinator verified reads settings correctly; secrets.json created with 0600 |
| 4 | Chat SSE streaming, single message, cancel, errors readable, SSE events | Pass | Real gemma4:12b call emitted shell tool call (29s); text_delta event, turn_done reason verified; all event types implemented |
| 5 | Sessions CRUD, SQLite+JSONL history persists | Pass | Verified SIGKILL engine mid-tool-call, restart, same session continues; history repaired in memory; JSONL unreadable fragments skipped with warning |
| 6 | Tools shell/ask/propose, approval per-call, stubs, GET /tools | Pass | Tool registry wired, interactions via asyncio.Future, multi-step loop (max_steps=8), shell tool 60s timeout 32KB cap, ask/propose stubs implemented |
| 7 | Skills folder-based SKILL.md, loaded from state-dir, example | Pass | Skills loader implemented; concise-summary example shipped; GET /skills works; catalog integrated in system prompt |
| 8 | OpenShell detect-only, sandbox toggle, shell via LocalExecutor | Pass | OpenShellExecutor detector returns available=false; fail-closed; shell always runs via LocalExecutor; toggle shows "not available" in settings |
| 9 | Security X-AD-Token, Origin gate, textContent rendering | Pass | X-AD-Token required on all routes; Origin gate (tauri://localhost, http(s)://tauri.localhost, localhost/127.0.0.1); M1 fix (child env filtered); textContent-only rendering in ad-message |
| 10 | `task release` produces macOS .app bundle with sidecar | Pass | PyInstaller onedir (36 MB) + Tauri .app (46 MB); verified launcher reads bundled config; ignores bogus AD_ENGINE_CMD in release build |
| 11 | Code readability: small modules, no hardcoded names, ruff clean | Pass | ruff format and linting clean; no reference-product or tool/model names in sources; modules single-purpose |
| 12 | GUI plain JS, no framework/bundler, ad-*/layout, theme tokens | Pass | No framework, no bundler, no Tailwind; 8 ad-* components; theme.css defines light/dark; jsdom tests pass |

**Not verified (reserved for user testing):**
- Visual rendering of GUI in window (no screenshots captured; only request logs and jsdom tests checked)
- Real-model behavior for ask/propose/load_skill interactions with a live provider
- Real OpenRouter chat with user's actual API key
- Corporate TLS inspection blocking OpenRouter in Python (deliberately ignored per user)
- Linux and Windows builds
- Gatekeeper/quarantine on a downloaded .app copy
- Client-disconnect cancellation under a real server
- Real NVIDIA OpenShell integration

## Documentation Review

**Scope:** README.md, installer/README.md, specs/mission.md, specs/tech-stack.md, specs/roadmap.md

**Findings:**

1. **specs/tech-stack.md GUI line was stale** — Stated "plain files served as-is by Tauri (no bundling step)" but code shows bundle task filters GUI folder and passes filtered copy via tauri.bundle.conf.json. Fixed in constitution update (version 2, updated 2026-10-06).

2. **README.md lacked AD_LOG_LEVEL** — Environment variables section listed AD_ENGINE_CMD, AD_LLM, AD_STATE_DIR, AD_TOKEN but omitted AD_LOG_LEVEL (uvicorn log level, default warning; info shows request logs). Fixed in README update.

3. **No CHANGELOG.md file existed** — Project-level docs did not record what was built; CHANGELOG.md is required per feature-spec-format and constitution-format skills. Created with 7 entries under ### Added.

4. **README.md** — Accurate in all other respects. All command names, config keys, and endpoints match the code.

5. **installer/README.md** — Accurate. Bundle layout, task descriptions, PyInstaller spec, Tauri config wiring match the code.

6. **specs/mission.md** — Accurate. Problem/Users/Value proposition/Non-goals reflect the actual implementation.

7. **specs/roadmap.md** — Accurate. The "Now" section correctly lists iteration-1-wired-shell as the current work in progress.

**Summary:** Stale GUI line in tech-stack.md (fixed), missing AD_LOG_LEVEL in README.md (fixed), and missing CHANGELOG.md (created). All other documentation is current and accurate.

## Documentation Updates

Completed:

- **README.md** — Added AD_LOG_LEVEL environment variable documentation (uvicorn log level, default warning; info shows request logs)
- **CHANGELOG.md** — Created with Keep a Changelog format; populated ### Added with 7 feature entries
- **specs/tech-stack.md** — Version incremented to 2 (updated 2026-10-06); GUI bundling line corrected to describe filtered copy passed via tauri.bundle.conf.json
- **specs/roadmap.md** — Removed iteration-1-wired-shell from ## Now section (now reads "Not started.")
- **specs/memory.md** — Created with 6 operational facts: [build] tags for PyInstaller frozen engine (backend/defaults explicit data) and Tauri bundle filtering; [gotcha] tags for firewall TLS interception, window/engine timing, Task dir: workaround, and tauri dev working directory

No git commit was created; the repository was not initialized per user directive.
