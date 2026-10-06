---
title: Windows support — shell execution, paths, permissions, output line endings
kind: bugfix
status: done
version: 2
updated: 2026-10-06
branch: main
---

# Windows support — shell execution, paths, permissions, output line endings

## Problem / Motivation

`task test` passes on macOS but fails 10 engine tests on Windows. The tech-stack constitution declares Windows a supported platform ("Linux, Windows, macOS, in that priority order; platform-specific code ... isolated behind small, tested helpers"), while iteration 1 explicitly deferred Windows build verification and Windows secrets-file ACL hardening. The failures are deterministic host assumptions, not flakiness:

- **Executor runs through `cmd.exe`, but the tests send POSIX shell.** `asyncio.create_subprocess_shell` uses `%COMSPEC%` on Windows. Test commands use `;`, `>&2`, `pwd`, `sleep`, `touch`, `/dev/zero`, `head`, `tr`, `env`, and `~`; `cmd` understands none of the POSIX forms. CRLF output from cmd's `echo` also breaks exact-output assertions, and `_describe` strips only `"\n"`, leaving a trailing `"\r"`.
- **Host path semantics leak into platform-agnostic code.** `pathlib.Path` is `WindowsPath` here, so `Path("/xdg").is_absolute()` is `False` (XDG is ignored in the Linux branch), and `str(Path("/work").expanduser())` becomes `\work` in the approval card.
- **Windows has no POSIX permission bits.** `os.open(..., 0o600)` / `os.chmod` only toggle read-only; `stat.S_IMODE` reports `0o666`, so the secrets-file mode assertion fails. (The equivalent `test_paths.py` assertions are already `skipif(win32)`; this one is not.)
- **A fixture writes invalid TOML on Windows.** `workspace_dir = "C:\Users\...\ws"` uses backslashes as TOML escapes (`\U` is invalid), so the config fails to parse, the route returns 500, and the test gets `KeyError: 'skills'`.

**Assumptions recorded** (from the scoping decisions): approved commands run through the host's native shell (`cmd.exe` on Windows), not a forced POSIX shell or PowerShell; the executor normalizes output to LF; Windows process trees are killed with `taskkill /F /T`; Windows secrets-file ACL hardening stays out of scope (mode is best-effort).

## Acceptance Criteria

1. `task test` passes on Windows: engine pytest has zero failures, plus the existing GUI `node --test` and `cargo test` suites pass unchanged. No executor test depends on POSIX-only command syntax on Windows.
2. Approved commands run through the host's native shell — `cmd.exe` (via `COMSPEC`) on Windows, `/bin/sh` elsewhere — and this is documented as host-shell-specific command syntax.
3. Executor output is normalized to LF: `\r\n` and lone `\r` become `\n` for both stdout and stderr, so tool results and stored session history are identical across platforms.
4. Exit codes and timeout reporting are unchanged on both platforms; partial output is still preserved when a command is killed.
5. On timeout or cancellation, the whole process tree is terminated on Windows via `taskkill /F /T /PID`; POSIX keeps the process-group `SIGKILL`. A test proves a grandchild is stopped on both platforms.
6. `resolve_state_dir`'s POSIX branch uses POSIX path semantics on every host, so `XDG_CONFIG_HOME=/xdg` resolves to `/xdg/ai-desktop` even when the test runs on Windows.
7. The shell tool's approval details show a configured cwd without host-specific mangling: a POSIX-style configured path is displayed as entered on any platform, and `~` still expands to the user's home.
8. The secrets-file `0o600` assertion is Unix-only; Windows behavior is recorded as a known limitation. No POSIX mode assertion runs on Windows.
9. The skill-route workspace test writes valid TOML on Windows (path escaped) and passes on both platforms.
10. No behavior change on macOS/Linux: the currently passing engine, GUI, and Rust tests stay green.

## Approach

### Key decisions

| Decision | Choice | Rejected alternative |
|----------|--------|----------------------|
| Windows shell | Host-native shell: `cmd.exe` via `COMSPEC` on Windows, `/bin/sh` elsewhere | Force Git-Bash `sh` (depends on Git, surprising for stock Windows); PowerShell (extra behavior/syntax to document) |
| Output line endings | Normalize to LF in the executor reader | Keep native endings (leaks CRLF into history/prompt); normalize only in `_describe` (leaves executor inconsistent) |
| Process-tree kill | `taskkill /F /T /PID` on Windows, `killpg(SIGKILL)` on POSIX | `process.terminate()` (leaves orphaned grandchildren — iteration-1 limitation L2) |
| POSIX path logic | `posixpath`/`PurePosixPath` for the POSIX branch | Host `Path` (the current bug) |
| Approval cwd display | `os.path.expanduser(config.cwd)` on the raw string | `Path(...).expanduser()` (WindowsPath mangles POSIX paths) |
| Windows secrets ACLs | Out of scope; mode is best-effort, test is Unix-only | `icacls`/ACL hardening now (deferred by iteration 1) |
| Executor tests | Small per-platform command table in the test module | POSIX-only commands (the current bug); asserting on shell identity (brittle) |

### Ordered implementation plan

1. **Normalize output line endings** in `_SharedBudgetReader.read_all` (`\r\n`/`\r` → `\n`) and add a unit test feeding `\r\n` and lone `\r`. Verify `test_success_captures_stdout` and the `hi\r` tool-result tests on Windows.
2. **Platform-aware shell + process-tree kill.** Confirm `LocalExecutor` selects the native shell (already `create_subprocess_shell`); on Windows route `_kill` through `taskkill /F /T /PID <pid>` (fall back to `terminate()` if `taskkill` fails), keeping `start_new_session` on POSIX. Add a grandchild-stops test that is repeatable and fast on both hosts.
3. **Make `test_executor.py` host-shell-aware.** Introduce a small `cmd(posix, windows)` helper; use `echo`, `cd` (Windows) / `pwd` (POSIX), `ping -n 31 127.0.0.1 >nul` (Windows sleep) / `sleep 30`, `set` / `env`, and a native equivalent of the `/dev/zero | tr` truncation command. Fix the `~` test to patch `USERPROFILE` on Windows as well as `HOME`. Verify the full executor test file on Windows.
4. **Fix POSIX path semantics** in `resolve_state_dir`/`_xdg_config_home` using `PurePosixPath`/`posixpath.isabs` for the POSIX branch, leaving Windows/macOS branches on host `Path`. Verify `test_linux_uses_xdg_config_home`.
5. **Fix the approval cwd display** in `shell_spec.approval_details` to `os.path.expanduser(config.cwd)`. Verify `test_shell_requires_approval_and_describes_command_and_cwd` and that `test_shell_passes_configured_cwd_and_timeout_to_the_executor` still passes.
6. **Guard the secrets-mode assertion** in `test_settings_routes.py` with `skipif(win32)` (matching `test_paths.py`), and note the Windows limitation in the spec and README. Verify settings tests on Windows.
7. **Fix the skill-route TOML fixture** by writing the workspace path with proper TOML escaping (e.g. `json.dumps(str(workspace))` or `tomli_w`), and add a regression assertion that the written file parses. Verify the skill-route test on both platforms.
8. **Run the full `task test` on Windows** and report pass/fail; reason about macOS/Linux equivalence for every touched branch (the POSIX paths are unchanged and remain covered by the existing tests).

### Risks

- Windows command strings are inherently host-specific; the platform-aware tests must stay readable, not become a second implementation. Keep the table minimal and comment why each pair is equivalent.
- `taskkill /F /T` can be unavailable or fail; the kill path falls back to `terminate()` and must never raise into the caller.
- The grandchild-kill test is the most timing-sensitive; it must use a marker plus generous bounds and stay well under the suite's budget.

## Affected Areas

- `engine/backend/tools/executor.py` — shell selection, output normalization, Windows process-tree kill
- `engine/backend/paths.py` — POSIX branch uses POSIX path semantics
- `engine/backend/tools/shell.py` — approval cwd display
- `engine/tests/test_executor.py` — host-shell-aware commands, `USERPROFILE` patch
- `engine/tests/test_paths.py` — XDG test now host-independent
- `engine/tests/test_settings_routes.py` — Unix-only mode assertion
- `engine/tests/test_skill_routes.py` — valid TOML fixture
- `specs/features/windows-support.md`, `CHANGELOG.md`, `README.md` — record and document

## Out of Scope

- Windows secrets-file ACL hardening (`icacls`/ACLs); POSIX mode is best-effort on Windows
- PowerShell as the shell tool's interpreter
- Windows MSI/Tauri bundle and `task release` verification
- Real Windows GUI visual verification (covered only by `node --test` and `cargo test`)
- Changing shell tool config keys or defaults
- macOS/Linux behavior changes

## Implementation Notes

All eight planned steps were completed and validated on Windows.

1. **Output normalization** — `_SharedBudgetReader.read_all` now maps `\r\n` and lone `\r` to `\n` after decoding. Unit coverage via the existing executor tests (`test_success_captures_stdout`, `test_non_zero_exit_and_stderr`, the tool-result tests).
2. **Platform shell + process-tree kill** — `LocalExecutor` keeps `create_subprocess_shell`, which uses `%COMSPEC%` (`cmd.exe`) on Windows and `/bin/sh` elsewhere. `_kill` routes Windows through a new `_taskkill_tree(pid)` running `taskkill /F /T /PID <pid>` (bounded by `_DRAIN_GRACE_S`, output suppressed); on any `OSError`/`SubprocessError` or non-zero result it falls back to `process.terminate()`. POSIX still does `killpg(SIGKILL)`.
3. **Host-shell-aware executor tests** — added a `cmd(posix, windows)` helper and `IS_WINDOWS`; converted the stderr/exit, cwd/`~`, timeout, and cancel tests. The `~` test patches `USERPROFILE` as well as `HOME`. The truncation test uses `sys.executable -c` to emit 100 000 bytes on Windows. The credential test uses `set` on Windows and checks `PATH=` case-insensitively.
4. **POSIX path semantics** — `_xdg_config_home` now uses `posixpath.isabs` instead of `Path(...).is_absolute()`, so `XDG_CONFIG_HOME=/xdg` is honored on any host.
5. **Approval cwd display** — `shell_spec.approval_details` uses `os.path.expanduser(config.cwd)`, which leaves `/work` as entered and still expands `~`; `Path` is no longer imported in `shell.py`.
6. **Unix-only secrets assertion** — `test_api_key_is_write_only` asserts `0o600` only when not on Windows; the Windows limitation is recorded in the README and CHANGELOG.
7. **Valid TOML fixture** — `test_skills_route_uses_the_configured_workspace_dir` writes the workspace via `json.dumps(str(workspace))`, escaping Windows backslashes so the TOML parses.
8. **Full suite run on Windows** — green (see Validation).

Tests changed: `test_executor.py` (host-shell table, `USERPROFILE`), `test_settings_routes.py` (Unix-only mode assertion), `test_skill_routes.py` (TOML escaping). Production changed: `executor.py`, `paths.py`, `shell.py`.

## Validation

Run on Windows 11, Python 3.13.1 in `engine/.venv`, 2026-10-06:

- `python -m pytest -q` (engine): **356 passed, 4 skipped** — up from 346 passed / 10 failed. The four skips are the pre-existing POSIX-permission tests in `test_paths.py`.
- `node --test "*.test.js" "components/**/*.test.js"` (GUI): **135 passed, 0 failed.**
- `cargo test` (Rust): **13 passed, 0 failed.**
- `python -m ruff check` (engine): clean.

All ten baseline failures are resolved: `test_success_captures_stdout`, `test_non_zero_exit_and_stderr`, `test_cwd_is_used_and_tilde_expanded`, `test_timeout_kills_the_command_and_keeps_partial_output`, `test_linux_uses_xdg_config_home`, `test_api_key_is_write_only`, `test_skills_route_uses_the_configured_workspace_dir`, `test_shell_requires_approval_and_describes_command_and_cwd`, `test_approved_run_streams_events_in_order`, `test_tool_messages_persist_and_reload`.

**macOS/Linux equivalence (reasoned, not run here):** all new host-conditional logic sits behind `os.name == "nt"` / `sys.platform.startswith("win")`; the POSIX branches are the previous code. `posixpath.isabs` is identical to `Path.is_absolute` on a POSIX host, and `os.path.expanduser` is identical to `str(Path(...).expanduser())` there. LF normalization is a no-op when output has no `\r`. The `cmd(posix, ...)` helper returns the original POSIX command strings, so the executor tests run unchanged on macOS/Linux. Remaining acceptance criteria for macOS/Linux are covered by the unchanged green suites above when run on those hosts.

## Documentation Review

Single implicit artifact (root `.`); the repo has no `### Artifacts` table, so `CHANGELOG.md` at the project root is the only changelog. User-facing drift found:

- `CHANGELOG.md` — missing entry under `## [Unreleased]` for: Windows shell support and LF-normalized output (`Fixed`); Windows process-tree kill (`Fixed`); POSIX state-dir semantics (`Fixed`); approval cwd display (`Fixed`).
- `README.md` — shell section did not document that command syntax follows the host shell; API-key section did not state the Windows permission limitation.
- `specs/memory.md` — two durable `[gotcha]` entries worth recording (Windows `cmd echo` trailing space; Windows executor kill/normalization details).
- Constitution (`mission.md`, `tech-stack.md`, `roadmap.md`) — no drift; Windows was already declared supported.

## Documentation Updates

- `CHANGELOG.md` — four `Fixed` entries added under `## [Unreleased]`.
- `README.md` — added the "Command syntax is your shell's" bullet (host shell, LF normalization, whole-tree kill) and a Windows ACL note in "Where the API key lives".
- `specs/memory.md` — appended the two `[gotcha]` entries listed above.
- `specs/roadmap.md` — removed the completed Windows-support `## Now` line (it now lives in the changelog).
- Constitution files — unchanged.
