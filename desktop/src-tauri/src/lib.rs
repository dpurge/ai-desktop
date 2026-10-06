mod engine_command;
mod sidecar;

use std::path::PathBuf;
use std::sync::Mutex;

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

use engine_command::{engine_command_override, resolve_engine_command, ENGINE_CMD_ENV_VAR};
use sidecar::EngineProcess;

const BUNDLED_ENGINE_RELATIVE_PATH: &str = if cfg!(windows) {
    "engine/backend.exe"
} else {
    "engine/backend"
};

/// Held in app state so the engine lives exactly as long as the app.
struct EngineState(Mutex<Option<EngineProcess>>);

fn bundled_engine(app: &tauri::AppHandle) -> Option<PathBuf> {
    let path = app
        .path()
        .resource_dir()
        .ok()?
        .join(BUNDLED_ENGINE_RELATIVE_PATH);
    path.is_file().then_some(path)
}

// The window is created only after the engine process is spawned. It is not necessarily
// listening yet; the GUI polls /health, so no wait loop is needed here.
fn start_engine_and_window(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let env_command = engine_command_override(
        std::env::var(ENGINE_CMD_ENV_VAR).ok(),
        cfg!(debug_assertions),
    );
    let command = resolve_engine_command(env_command.as_deref(), bundled_engine(app.handle()))?;

    let port = sidecar::pick_free_port()?;
    let token = sidecar::generate_token();
    let engine = sidecar::spawn_engine(&command, port, &token)
        .map_err(|error| format!("Could not start the engine `{}`: {error}", command.program))?;
    app.manage(EngineState(Mutex::new(Some(engine))));

    WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
        .title("AI Desktop")
        .inner_size(1100.0, 720.0)
        .initialization_script(sidecar::injected_script(&sidecar::base_url(port), &token))
        .build()?;
    Ok(())
}

fn stop_engine(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<EngineState>() {
        if let Some(mut engine) = state.0.lock().unwrap().take() {
            engine.kill();
        }
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            start_engine_and_window(app).map_err(|error| {
                // Without a window nothing else would tell the user why the app closed.
                eprintln!("{error}");
                error
            })
        })
        .build(tauri::generate_context!())
        .expect("error while building the app");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            stop_engine(app);
        }
    });
}
