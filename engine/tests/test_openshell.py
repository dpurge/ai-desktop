import pytest

from backend.config import SandboxConfig
from backend.tools.executor import LocalExecutor
from backend.tools.executor_factory import RefusingExecutor, select_executor
from backend.tools.openshell import (
    NOT_INSTALLED,
    NOT_WIRED,
    OpenShellExecutor,
    OpenShellStatus,
    SandboxUnavailableError,
    detect_openshell,
)


def test_missing_command_is_reported_as_not_installed():
    status = detect_openshell(which=lambda name: None)
    assert status == OpenShellStatus(available=False, reason=NOT_INSTALLED)


def test_found_command_is_reported_as_not_wired_and_still_unavailable():
    asked = []
    status = detect_openshell(which=lambda name: asked.append(name) or "/usr/bin/openshell")
    assert status == OpenShellStatus(available=False, reason=NOT_WIRED)
    assert asked == ["openshell"]


async def test_executor_refuses_instead_of_running():
    with pytest.raises(SandboxUnavailableError) as raised:
        await OpenShellExecutor().run("echo hi", ".", 5)
    assert "not wired up yet" in str(raised.value)


def test_error_message_names_the_reason_and_the_way_out():
    message = str(SandboxUnavailableError("OpenShell is not installed."))
    assert message == (
        "Sandbox is enabled but unavailable: OpenShell is not installed. "
        "Disable it in Settings or fix the setup."
    )


UNAVAILABLE = OpenShellStatus(False, NOT_INSTALLED)
AVAILABLE = OpenShellStatus(True, "ready")


@pytest.mark.parametrize("status", [UNAVAILABLE, AVAILABLE])
def test_disabled_sandbox_uses_the_local_executor(status):
    assert isinstance(select_executor(SandboxConfig(enabled=False), status), LocalExecutor)


def test_enabled_and_available_uses_openshell():
    assert isinstance(select_executor(SandboxConfig(enabled=True), AVAILABLE), OpenShellExecutor)


async def test_enabled_but_unavailable_never_falls_back_to_local(tmp_path):
    executor = select_executor(SandboxConfig(enabled=True), UNAVAILABLE)
    assert isinstance(executor, RefusingExecutor)
    marker = tmp_path / "ran"
    with pytest.raises(SandboxUnavailableError):
        await executor.run(f"touch {marker}", str(tmp_path), 5)
    assert not marker.exists()
