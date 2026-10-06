use std::fmt;
use std::path::PathBuf;

pub const ENGINE_CMD_ENV_VAR: &str = "AD_ENGINE_CMD";

#[derive(Debug, PartialEq)]
pub enum EngineCommandError {
    NotFound,
    Malformed(String),
}

impl fmt::Display for EngineCommandError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NotFound => write!(
                f,
                "Engine not found. For development set {ENGINE_CMD_ENV_VAR}, or run `task run`."
            ),
            Self::Malformed(reason) => {
                write!(
                    f,
                    "{ENGINE_CMD_ENV_VAR} is not a valid command line: {reason}"
                )
            }
        }
    }
}

impl std::error::Error for EngineCommandError {}

/// Program and leading arguments used to start the engine (without `--port`).
#[derive(Debug, PartialEq)]
pub struct EngineCommand {
    pub program: String,
    pub args: Vec<String>,
}

/// The AD_ENGINE_CMD value to honor. A release app never runs a command taken from its
/// environment, so whoever can set variables for the app cannot make it execute their program.
pub fn engine_command_override(env_value: Option<String>, is_debug_build: bool) -> Option<String> {
    env_value.filter(|_| is_debug_build)
}

/// `env_value` (AD_ENGINE_CMD) wins; otherwise the bundled executable, if one was found.
pub fn resolve_engine_command(
    env_value: Option<&str>,
    bundled_executable: Option<PathBuf>,
) -> Result<EngineCommand, EngineCommandError> {
    if let Some(command_line) = env_value.filter(|value| !value.trim().is_empty()) {
        let mut words = shell_words::split(command_line)
            .map_err(|error| EngineCommandError::Malformed(error.to_string()))?
            .into_iter();
        let program = words
            .next()
            .ok_or_else(|| EngineCommandError::Malformed("empty command".into()))?;
        return Ok(EngineCommand {
            program,
            args: words.collect(),
        });
    }
    bundled_executable
        .map(|path| EngineCommand {
            program: path.to_string_lossy().into_owned(),
            args: vec![],
        })
        .ok_or(EngineCommandError::NotFound)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_command_is_honored_in_debug_builds_only() {
        let value = Some("engine-dev".to_string());
        assert_eq!(
            engine_command_override(value.clone(), true),
            Some("engine-dev".to_string())
        );
        assert_eq!(engine_command_override(value, false), None);
        assert_eq!(engine_command_override(None, true), None);
    }

    #[test]
    fn env_command_is_split_like_a_shell_would() {
        let command = resolve_engine_command(
            Some("uv run --project '../my engine' python -m backend"),
            None,
        )
        .unwrap();
        assert_eq!(command.program, "uv");
        assert_eq!(
            command.args,
            [
                "run",
                "--project",
                "../my engine",
                "python",
                "-m",
                "backend"
            ]
        );
    }

    #[test]
    fn env_command_wins_over_bundled_executable() {
        let command =
            resolve_engine_command(Some("engine-dev"), Some(PathBuf::from("/app/engine"))).unwrap();
        assert_eq!(command.program, "engine-dev");
    }

    #[test]
    fn bundled_executable_is_used_without_env_command() {
        let command = resolve_engine_command(None, Some(PathBuf::from("/app/engine"))).unwrap();
        assert_eq!(
            command,
            EngineCommand {
                program: "/app/engine".into(),
                args: vec![]
            }
        );
    }

    #[test]
    fn blank_env_command_falls_back_to_bundled_executable() {
        let command =
            resolve_engine_command(Some("  "), Some(PathBuf::from("/app/engine"))).unwrap();
        assert_eq!(command.program, "/app/engine");
    }

    #[test]
    fn missing_engine_explains_how_to_fix_it() {
        let error = resolve_engine_command(None, None).unwrap_err();
        assert_eq!(error, EngineCommandError::NotFound);
        assert!(error.to_string().contains("AD_ENGINE_CMD"));
        assert!(error.to_string().contains("task run"));
    }

    #[test]
    fn unbalanced_quotes_are_reported() {
        let error = resolve_engine_command(Some("uv 'run"), None).unwrap_err();
        assert!(matches!(error, EngineCommandError::Malformed(_)));
    }
}
