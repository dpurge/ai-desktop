import asyncio
import time

from backend.tools.executor import MAX_OUTPUT_BYTES, LocalExecutor, child_environment


async def run(command, timeout_s=10, cwd="."):
    return await LocalExecutor().run(command, cwd, timeout_s)


async def test_success_captures_stdout():
    result = await run("echo hello")
    assert (result.exit_code, result.stdout, result.stderr, result.timed_out) == (
        0,
        "hello\n",
        "",
        False,
    )


async def test_non_zero_exit_and_stderr():
    result = await run("echo oops >&2; exit 3")
    assert result.exit_code == 3
    assert result.stderr == "oops\n"
    assert result.timed_out is False


async def test_cwd_is_used_and_tilde_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = await run("pwd", cwd="~")
    assert result.stdout.strip() == str(tmp_path.resolve())


async def test_timeout_kills_the_command_and_keeps_partial_output():
    started = time.monotonic()
    result = await run("echo before; sleep 30", timeout_s=0.5)

    assert result.timed_out is True
    assert result.stdout == "before\n"
    assert time.monotonic() - started < 10


async def test_timeout_also_kills_child_processes():
    # The background child holds the pipe open; only a group kill lets the call return.
    result = await run("sleep 30 & wait", timeout_s=0.5)
    assert result.timed_out is True


async def test_output_is_truncated_with_a_marker():
    result = await run("head -c 100000 /dev/zero | tr '\\0' 'x'")

    assert result.exit_code == 0
    assert len(result.stdout) == MAX_OUTPUT_BYTES + len("\n[truncated]")
    assert result.stdout.endswith("\n[truncated]")


async def test_cancelling_kills_the_running_process(tmp_path):
    marker = tmp_path / "still-running"
    task = asyncio.create_task(run(f"sleep 1; touch {marker}", timeout_s=30))
    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(1.5)

    assert not marker.exists()


def test_child_environment_drops_engine_and_credential_variables():
    environ = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "AD_TOKEN": "t",
        "AD_LLM": "fake",
        "ad_state_dir": "/x",
        "OPENROUTER_API_KEY": "k",
        "GITHUB_TOKEN": "g",
        "my_db_secret": "s",
        "ADDRESS": "kept",
        "TOKEN_COUNT": "kept",
    }

    assert child_environment(environ) == {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "ADDRESS": "kept",
        "TOKEN_COUNT": "kept",
    }


async def test_command_does_not_see_the_engine_credentials(monkeypatch):
    for name in ("AD_TOKEN", "OPENROUTER_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "leaked-value")

    result = await run("env")

    assert result.exit_code == 0
    assert "leaked-value" not in result.stdout
    assert "PATH=" in result.stdout
