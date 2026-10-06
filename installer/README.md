# Installer

Builds the desktop bundle for the host platform: a macOS `AI Desktop.app` or a Windows NSIS setup
`.exe`. Signing, notarization, dmg, and Linux output are not supported.

## Tasks

Run from `installer/` as `task <name>`, or from the repository root as `task installer:<name>`.

| Task      | What it does |
|-----------|--------------|
| `sidecar` | Freezes the engine with PyInstaller into `engine/dist/backend/` (`task engine:sidecar`). |
| `bundle`  | Builds the app with `tauri build --bundles app` (macOS) or `--bundles nsis` (Windows), with the frozen engine as a resource. Needs `sidecar` first. |
| `release` | `sidecar`, `bundle`, then copies the platform bundle (`macos/` or `nsis/`) to `installer/dist/` and prints its path and contents. |
| `clean`   | Removes `installer/dist`, `engine/dist`, `engine/build`, and the Tauri bundle output. |

The root `task build` runs `installer:release`; the root `task release` runs the tests first.

## Bundle layout

macOS:

```
AI Desktop.app/Contents/
  MacOS/ai-desktop              the Tauri shell
  Resources/engine/backend      the frozen engine (PyInstaller onedir)
  Resources/engine/_internal/   its libraries, backend/defaults (config.toml, skills), aisuite
```

Windows (installed under the app directory):

```
ai-desktop.exe                  the Tauri shell
engine/backend.exe              the frozen engine
engine/_internal/               its libraries, backend/defaults, aisuite
```

The shell looks for the bundled engine when `AD_ENGINE_CMD` is not set: `engine/backend` on macOS
and `engine/backend.exe` on Windows (see `BUNDLED_ENGINE_RELATIVE_PATH` in
`desktop/src-tauri/src/lib.rs`).

## How it is wired

- `engine/sidecar.spec` is the PyInstaller spec. It collects aisuite whole because aisuite loads
  its providers by name at run time, which PyInstaller cannot see.
- `desktop/src-tauri/tauri.bundle.conf.json` is merged into `tauri.conf.json` only by
  `task gui:bundle`. It maps the frozen engine into `engine/` and points the frontend at a copy of
  `desktop/gui` without `node_modules` and tests. Keeping it out of the main config means
  `task run` (`tauri dev`) works without a frozen engine.
- `desktop/scripts/copy-gui.mjs` makes that GUI copy (and its exclusions) with Node, so the bundle
  step does not need `rsync` or other POSIX tools on Windows.
- `task engine:sidecar-smoke` starts the frozen engine alone and checks `/health`.

## Unsigned app

The app is unsigned. On a Mac where it was downloaded or copied, the first launch is blocked by
Gatekeeper: right-click the app and choose Open, or run
`xattr -dr com.apple.quarantine "AI Desktop.app"`. On Windows, SmartScreen may warn about the
unsigned installer; choose **More info** then **Run anyway**.

The first launch of a freshly built engine can take tens of seconds while the OS scans its
libraries; later launches take a couple of seconds.
