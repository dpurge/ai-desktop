# Project Memory

<!-- Append-only, one entry per line: `YYYY-MM-DDTHH:MM:SSZ [tag] text`. See the `memory-format` skill. Do not read this file in full — grep it. -->

2026-10-06T00:00:00Z [build] engine/sidecar.spec must list backend/defaults explicitly; collect_data_files misses non-installed packages; aisuite needs collect_all for dynamic providers.
2026-10-06T00:01:00Z [build] Tauri 2 rejects frontendDist with node_modules; filter GUI to desktop/src-tauri/target/gui-bundle in bundle task; pass via tauri.bundle.conf.json.
2026-10-06T00:02:00Z [gotcha] Firewall re-signs HTTPS (certifi fails openrouter.ai); macOS curl works via trust store; truststore + inject_into_ssl is candidate fix, not yet applied.
2026-10-06T00:03:00Z [gotcha] Window loads before engine listens; GUI retries /health (desktop/gui/engine-ready.js); check AD_LOG_LEVEL=info to confirm GUI reaches engine.
2026-10-06T00:04:00Z [gotcha] Task 3.53 ignores per-command dir: in included Taskfiles; workaround is cd <dir> && ... in command string.
2026-10-06T00:05:00Z [gotcha] Under tauri dev, cwd is desktop/src-tauri; AD_ENGINE_CMD default uses uv run --directory <abs path> to reach engine from that directory.
2026-10-06T00:06:00Z [gotcha] Windows cmd echo adds a trailing space when a redirection or `&` follows (`echo x 1>&2` emits "x \n"); use `(echo x) 1>&2` and `echo x& next`.
2026-10-06T00:07:00Z [gotcha] Windows executor: normalize \r\n and lone \r to \n in _SharedBudgetReader; kill the process tree with `taskkill /F /T /PID` (fall back to terminate()); use posixpath.isabs for XDG checks and os.path.expanduser for the approval cwd.
