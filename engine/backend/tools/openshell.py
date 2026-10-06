import shutil
from collections.abc import Callable
from dataclasses import dataclass

from backend.tools.executor import ExecResult

OPENSHELL_COMMAND = "openshell"
NOT_INSTALLED = f"OpenShell is not installed (the `{OPENSHELL_COMMAND}` command was not found)."
NOT_WIRED = "OpenShell was found, but sandboxed execution is not wired up yet in this version."


@dataclass(frozen=True)
class OpenShellStatus:
    available: bool
    reason: str


class SandboxUnavailableError(Exception):
    """The sandbox was asked for but cannot run; the command was not executed anywhere."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"Sandbox is enabled but unavailable: {reason.rstrip('.')}. "
            "Disable it in Settings or fix the setup."
        )


def detect_openshell(which: Callable[[str], str | None] = shutil.which) -> OpenShellStatus:
    """Looks for the OpenShell CLI on PATH only: no process is started and nothing is contacted.

    Never available yet: running commands through it is the roadmap item `openshell-sandbox`.
    """
    if which(OPENSHELL_COMMAND) is None:
        return OpenShellStatus(available=False, reason=NOT_INSTALLED)
    return OpenShellStatus(available=False, reason=NOT_WIRED)


class OpenShellExecutor:
    """Placeholder for running commands in an OpenShell sandbox (roadmap: `openshell-sandbox`).

    Refuses every command rather than running it outside the sandbox.
    """

    def __init__(self, reason: str = NOT_WIRED) -> None:
        self._reason = reason

    async def run(self, command: str, cwd: str, timeout_s: float) -> ExecResult:
        raise SandboxUnavailableError(self._reason)
