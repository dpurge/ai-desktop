from backend.config import Config, ProviderEndpoints, ShellConfig
from backend.tools.executor import ExecResult
from backend.tools.registry import ToolContext, ToolOutcome, registry_for
from backend.tools.shell import shell_spec

ENDPOINTS = ProviderEndpoints("http://o", "http://r")


def config(**shell):
    return Config("ollama", "m", ENDPOINTS, shell=ShellConfig(**shell))


class RecordingExecutor:
    def __init__(self, result):
        self.calls = []
        self._result = result

    async def run(self, command, cwd, timeout_s):
        self.calls.append((command, cwd, timeout_s))
        return self._result


def offered_names(registry):
    return [schema["function"]["name"] for schema in registry.openai_schemas()]


def test_enabled_shell_is_offered_as_an_openai_function_schema():
    schema = next(
        s for s in registry_for(config()).openai_schemas() if s["function"]["name"] == "shell"
    )

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "shell"
    assert schema["function"]["description"]
    assert schema["function"]["parameters"]["required"] == ["command"]


def test_disabled_shell_is_not_offered_or_found():
    registry = registry_for(config(enabled=False))

    assert "shell" not in offered_names(registry)
    assert registry.get("shell") is None


def test_only_enabled_and_available_tools_are_offered():
    assert offered_names(registry_for(config())) == ["shell", "ask", "propose"]


def test_describe_lists_every_tool_with_its_state():
    described = {tool["name"]: tool for tool in registry_for(config(enabled=False)).describe()}

    assert list(described) == ["shell", "ask", "propose", "gmail", "gcal", "github"]
    assert described["shell"]["enabled"] is False
    assert described["shell"]["requires_approval"] is True
    assert described["ask"] == {
        "name": "ask",
        "description": described["ask"]["description"],
        "requires_approval": False,
        "available": True,
        "enabled": True,
    }
    assert [described[name]["available"] for name in ("gmail", "gcal", "github")] == [False] * 3


async def test_stub_reports_it_is_not_connected():
    outcome = await registry_for(config()).get("gmail").run({}, ToolContext(None))

    assert outcome == ToolOutcome(False, "gmail is not connected yet.")


def test_shell_requires_approval_and_describes_command_and_cwd():
    spec = registry_for(config(cwd="/work")).get("shell")

    assert spec.requires_approval is True
    assert spec.approval_details({"command": "ls"}) == {"command": "ls", "cwd": "/work"}


async def run_shell(result, **shell):
    executor = RecordingExecutor(result)
    spec = shell_spec(ShellConfig(**shell))
    outcome = await spec.run({"command": "ls"}, ToolContext(executor))
    return outcome, executor


async def test_shell_passes_configured_cwd_and_timeout_to_the_executor():
    _, executor = await run_shell(ExecResult(0, "", "", False), cwd="/work", timeout_s=7)
    assert executor.calls == [("ls", "/work", 7)]


async def test_successful_output():
    outcome, _ = await run_shell(ExecResult(0, "a\nb\n", "", False))
    assert outcome == ToolOutcome(True, "a\nb")


async def test_failure_includes_stderr_and_exit_code():
    outcome, _ = await run_shell(ExecResult(2, "", "nope\n", False))
    assert outcome.ok is False
    assert outcome.output == "[stderr]\nnope\n[exit code 2]"


async def test_timeout_is_reported_as_failure():
    outcome, _ = await run_shell(ExecResult(-9, "partial", "", True), timeout_s=3)
    assert outcome.ok is False
    assert outcome.output == "partial\n[timed out after 3 s and was killed]"


async def test_no_output_is_said_so():
    outcome, _ = await run_shell(ExecResult(0, "", "", False))
    assert outcome.output == "(no output)"


async def test_blank_command_is_an_error_without_running():
    executor = RecordingExecutor(ExecResult(0, "", "", False))
    outcome = await shell_spec(ShellConfig()).run({"command": "  "}, ToolContext(executor))
    assert outcome.ok is False
    assert executor.calls == []


async def test_unstartable_command_is_an_error_not_an_exception():
    class Broken:
        async def run(self, command, cwd, timeout_s):
            raise FileNotFoundError("no such directory")

    outcome = await shell_spec(ShellConfig(cwd="/nope")).run(
        {"command": "ls"}, ToolContext(Broken())
    )
    assert outcome.ok is False
    assert "/nope" in outcome.output


def test_outcome_text_is_capped():
    outcome = ToolOutcome.capped(True, "x" * 100_000)
    assert len(outcome.output) < 33_000
    assert outcome.output.endswith("[truncated]")
