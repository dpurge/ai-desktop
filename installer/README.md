# Installer

Builds the macOS `AI Desktop.app`. Only macOS `.app` output is supported: no dmg, signing,
notarization, or other operating systems.

## Tasks

Run from `installer/` as `task <name>`, or from the repository root as `task installer:<name>`.

| Task      | What it does |
|-----------|--------------|
| `sidecar` | Freezes the engine with PyInstaller into `engine/dist/backend/` (`task engine:sidecar`). |
| `bundle`  | Builds the app with `tauri build --bundles app`, with the frozen engine as a resource. Needs `sidecar` first. |
| `release` | `sidecar`, `bundle`, then copies `AI Desktop.app` to `installer/dist/` and prints its path and size. |
| `clean`   | Removes `installer/dist`, `engine/dist`, `engine/build`, and the Tauri bundle output. |

The root `task build` runs `installer:release`; the root `task release` runs the tests first.

## Bundle layout

```
AI Desktop.app/Contents/
  MacOS/ai-desktop              the Tauri shell
  Resources/engine/backend      the frozen engine (PyInstaller onedir)
  Resources/engine/_internal/   its libraries, backend/defaults (config.toml, skills), aisuite
```

The shell looks for `Resources/engine/backend` when `AD_ENGINE_CMD` is not set (see
`BUNDLED_ENGINE_RELATIVE_PATH` in `desktop/src-tauri/src/lib.rs`).

## How it is wired

- `engine/sidecar.spec` is the PyInstaller spec. It collects aisuite whole because aisuite loads
  its providers by name at run time, which PyInstaller cannot see.
- `desktop/src-tauri/tauri.bundle.conf.json` is merged into `tauri.conf.json` only by
  `task gui:bundle`. It maps the frozen engine into `engine/` and points the frontend at a copy of
  `desktop/gui` without `node_modules` and tests. Keeping it out of the main config means
  `task run` (`tauri dev`) works without a frozen engine.
- `task engine:sidecar-smoke` starts the frozen engine alone and checks `/health`.

## Unsigned app

The app is unsigned. On a Mac where it was downloaded or copied, the first launch is blocked by
Gatekeeper: right-click the app and choose Open, or run
`xattr -dr com.apple.quarantine "AI Desktop.app"`.

The first launch of a freshly built engine can take tens of seconds while macOS scans its
libraries; later launches take a couple of seconds.
