"""devtools/beads-hook.sh: the agents' beads context (specs/010-beads-issue-tracking).

Claude Code and Codex run the script when a session starts, and Codex on its compaction events too
(contracts/agent-hooks.md). It hands over beads' own hook output when beads is available, and a
line saying why it isn't otherwise. It always exits 0. Here it runs against a stand-in `bd`, on a
`PATH` that holds only that stand-in and the few tools the script uses, so no beads is needed.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "devtools" / "beads-hook.sh"

# What the script and the stand-in use. Linked one by one, so that a real `bd` on the machine,
# wherever it is installed, stays off the PATH.
TOOLS = ("bash", "env", "sed", "sort", "head", "cat")

STAND_IN = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_BD_LOG"
echo "cwd=$PWD" >> "$FAKE_BD_LOG"
case "$1" in
  version) echo "bd version ${FAKE_BD_VERSION} (stand-in)" ;;
  where) exit "${FAKE_BD_WHERE_EXIT:-0}" ;;
  prime) echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"PRIME"}}'
         exit "${FAKE_BD_PRIME_EXIT:-0}" ;;
  codex-hook) cat >> "$FAKE_BD_LOG"; echo "{\\"codex\\":\\"$2\\"}" ;;
esac
"""


@pytest.fixture
def tools(tmp_path: Path) -> Path:
    directory = tmp_path / "tools"
    directory.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, f"{tool} is needed to run the hook script"
        (directory / tool).symlink_to(found)
    return directory


def run(tmp_path: Path, tools: Path, *args: str, bd_version: str | None, payload: str = "", **env: str):
    """Run the script as an agent would, with the stand-in `bd` reporting `bd_version` (None: no bd)."""
    path = [str(tools)]
    if bd_version is not None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        stand_in = bin_dir / "bd"
        stand_in.write_text(STAND_IN)
        stand_in.chmod(0o755)
        path.insert(0, str(bin_dir))
    log = tmp_path / "bd.log"
    result = subprocess.run(
        [str(SCRIPT), *args],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PATH": os.pathsep.join(path),
            "HOME": str(tmp_path),
            "FAKE_BD_LOG": str(log),
            "FAKE_BD_VERSION": bd_version or "",
            **env,
        },
        check=False,
    )
    return result, (log.read_text() if log.exists() else "")


def context_of(stdout: str) -> str:
    """The context of a hook's SessionStart JSON envelope, which both agents read."""
    output = json.loads(stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    return output["additionalContext"]


def test_the_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)


@pytest.mark.parametrize("args", [("claude",), ("codex", "SessionStart")])
def test_without_bd_the_session_is_told_beads_isnt_installed(tmp_path, tools, args):
    result, _ = run(tmp_path, tools, *args, bd_version=None)

    assert result.returncode == 0
    context = context_of(result.stdout)
    assert "isn't installed" in context
    assert "AGENTS.md" in context


@pytest.mark.parametrize("event", ["PreCompact", "PostCompact", "UserPromptSubmit"])
def test_without_bd_codex_s_other_events_get_nothing(tmp_path, tools, event):
    result, _ = run(tmp_path, tools, "codex", event, bd_version=None)

    assert result.returncode == 0
    assert result.stdout == ""


def test_a_bd_older_than_1_3_4_is_named(tmp_path, tools):
    result, _ = run(tmp_path, tools, "claude", bd_version="1.3.3")

    assert result.returncode == 0
    assert "1.3.3 is older than 1.3.4" in context_of(result.stdout)


def test_a_clone_not_connected_to_the_tracker_is_told_to_run_make_beads(tmp_path, tools):
    result, log = run(tmp_path, tools, "claude", bd_version="1.3.4", FAKE_BD_WHERE_EXIT="1")

    assert result.returncode == 0
    assert "make beads" in context_of(result.stdout)
    assert "prime" not in log


@pytest.mark.parametrize("version", ["1.3.4", "1.10.0", "2.0.1"])
def test_with_beads_claude_code_gets_bd_prime_s_own_output(tmp_path, tools, version):
    result, log = run(tmp_path, tools, "claude", bd_version=version)

    assert result.returncode == 0
    assert context_of(result.stdout) == "PRIME"
    assert "prime --hook-json" in log.splitlines()


@pytest.mark.parametrize("event", ["SessionStart", "PreCompact", "PostCompact", "UserPromptSubmit"])
def test_with_beads_codex_gets_bd_codex_hook_with_its_payload(tmp_path, tools, event):
    payload = json.dumps({"session_id": "s1", "hook_event_name": event})
    result, log = run(tmp_path, tools, "codex", event, bd_version="1.3.4", payload=payload)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"codex": event}
    assert f"codex-hook {event}" in log.splitlines()
    assert payload in log


@pytest.mark.parametrize("args", [("claude",), ("codex", "SessionStart")])
def test_bd_runs_from_the_repository_s_root_wherever_the_session_started(tmp_path, tools, args):
    # bd prime reads .beads/PRIME.md from the directory it runs in, and gives beads' default text
    # from any other: a session started in app/ would get it (research.md R6).
    result, log = run(tmp_path, tools, *args, bd_version="1.3.4")

    assert result.returncode == 0
    assert {line for line in log.splitlines() if line.startswith("cwd=")} == {f"cwd={PROJECT}"}


def test_a_failing_bd_still_lets_the_session_start(tmp_path, tools):
    result, _ = run(tmp_path, tools, "claude", bd_version="1.3.4", FAKE_BD_PRIME_EXIT="3")

    assert result.returncode == 0
