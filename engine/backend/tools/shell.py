import os

from backend.config import ShellConfig
from backend.tools.openshell import SandboxUnavailableError
from backend.tools.registry import ToolContext, ToolOutcome, ToolSpec

_DESCRIPTION = (
    "Run a shell command on the user's computer and return its output and exit code. "
    "The user must approve every command before it runs. Prefer short, non-interactive "
    "commands; commands that run too long are stopped."
)
_PARAMETERS = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "The shell command line to run."}},
    "required": ["command"],
}


def shell_spec(config: ShellConfig) -> ToolSpec:
    async def run(arguments: dict, context: ToolContext) -> ToolOutcome:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolOutcome(False, "The 'command' argument must be a non-empty string.")
        try:
            result = await context.executor.run(command, config.cwd, config.timeout_s)
        except SandboxUnavailableError as exc:
            return ToolOutcome(False, str(exc))
        except OSError as exc:
            return ToolOutcome(False, f"Could not start the command in {config.cwd}: {exc}")
        return ToolOutcome.capped(
            ok=result.exit_code == 0 and not result.timed_out,
            output=_describe(result, config.timeout_s),
        )

    return ToolSpec(
        name="shell",
        description=_DESCRIPTION,
        parameters=_PARAMETERS,
        requires_approval=True,
        run=run,
        approval_details=lambda arguments: {
            "command": str(arguments.get("command", "")),
            "cwd": os.path.expanduser(config.cwd),
        },
    )


def _describe(result, timeout_s: int) -> str:
    parts = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append("[stderr]\n" + result.stderr.rstrip("\n"))
    if result.timed_out:
        parts.append(f"[timed out after {timeout_s} s and was killed]")
    elif result.exit_code != 0:
        parts.append(f"[exit code {result.exit_code}]")
    return "\n".join(parts) or "(no output)"
