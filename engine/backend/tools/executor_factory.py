from backend.config import SandboxConfig
from backend.tools.executor import ExecResult, Executor, LocalExecutor
from backend.tools.openshell import OpenShellExecutor, OpenShellStatus, SandboxUnavailableError


class RefusingExecutor:
    """Stands in when the sandbox is switched on but cannot be used.

    The user asked for confinement, so running on the host instead would be a silent downgrade.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def run(self, command: str, cwd: str, timeout_s: float) -> ExecResult:
        raise SandboxUnavailableError(self._reason)


def select_executor(sandbox: SandboxConfig, status: OpenShellStatus) -> Executor:
    if not sandbox.enabled:
        return LocalExecutor()
    if status.available:
        return OpenShellExecutor()
    return RefusingExecutor(status.reason)
