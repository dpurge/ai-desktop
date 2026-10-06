use std::io;
use std::net::TcpListener;
use std::process::{Child, Command};

use crate::engine_command::EngineCommand;

const HOST: &str = "127.0.0.1";

/// Owns the engine child process and kills it when dropped, so a panic or normal exit
/// cannot leave an orphan behind.
pub struct EngineProcess {
    child: Child,
}

impl EngineProcess {
    pub fn kill(&mut self) {
        // Errors mean the child already exited; nothing left to clean up.
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for EngineProcess {
    fn drop(&mut self) {
        self.kill();
    }
}

/// Asks the OS for a free port; the small race before the engine binds it is accepted.
pub fn pick_free_port() -> io::Result<u16> {
    let listener = TcpListener::bind((HOST, 0))?;
    Ok(listener.local_addr()?.port())
}

/// Two v4 UUIDs give 244 random bits as hex, without pulling in a separate RNG crate.
pub fn generate_token() -> String {
    format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    )
}

pub fn spawn_engine(command: &EngineCommand, port: u16, token: &str) -> io::Result<EngineProcess> {
    let child = Command::new(&command.program)
        .args(&command.args)
        .arg("--port")
        .arg(port.to_string())
        .env("AD_TOKEN", token)
        .env("AD_PARENT_PID", std::process::id().to_string())
        .spawn()?;
    Ok(EngineProcess { child })
}

pub fn base_url(port: u16) -> String {
    format!("http://{HOST}:{port}")
}

/// JavaScript run before the page's own scripts; JSON encoding keeps odd characters from
/// breaking out of the string literals.
pub fn injected_script(base_url: &str, token: &str) -> String {
    let connection = serde_json::json!({ "baseUrl": base_url, "token": token });
    format!("window.__AI_DESKTOP__ = {connection};")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn injected_script_sets_base_url_and_token() {
        let script = injected_script("http://127.0.0.1:5000", "abc");
        assert_eq!(
            script,
            r#"window.__AI_DESKTOP__ = {"baseUrl":"http://127.0.0.1:5000","token":"abc"};"#
        );
    }

    #[test]
    fn injected_script_escapes_quotes_and_script_breakers() {
        let script = injected_script("http://x", "a\"b\\c\n</script>");
        assert!(script.contains(r#""a\"b\\c\n</script>""#));
        assert!(!script.contains('\n'));
    }

    #[test]
    fn picked_port_is_not_zero() {
        // Rebinding the port here would race with other tests that also pick a port in
        // parallel, so only the part that is deterministic is asserted.
        assert!(pick_free_port().unwrap() > 0);
    }

    #[test]
    fn tokens_are_long_and_unique() {
        let (first, second) = (generate_token(), generate_token());
        assert_eq!(first.len(), 64);
        assert_ne!(first, second);
    }

    #[test]
    fn dropping_the_process_kills_the_child() {
        let command = EngineCommand {
            program: "sleep".into(),
            args: vec!["30".into()],
        };
        // `sleep 30 --port N` fails on some systems, so spawn directly for this test.
        let child = Command::new(&command.program)
            .args(&command.args)
            .spawn()
            .unwrap();
        let pid = child.id();
        drop(EngineProcess { child });
        let status = Command::new("kill")
            .args(["-0", &pid.to_string()])
            .status()
            .unwrap();
        assert!(!status.success());
    }

    #[test]
    fn spawn_failure_is_reported() {
        let command = EngineCommand {
            program: "definitely-not-a-real-program".into(),
            args: vec![],
        };
        assert!(spawn_engine(&command, 1, "t").is_err());
    }
}
