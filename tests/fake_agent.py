"""A zero-token fake of the tla-modeler agent + Claude Code harness.

The real system is: an LLM makes tool calls (Write/Bash), and the harness
fires this plugin's hooks around them (PostToolUse after writes, Stop /
SubagentStop when the agent tries to finish). For testing, the LLM is
replaced by a scripted transcript of tool calls, so runs are deterministic
and cost nothing; only the plugin's own machinery (scripts/tlc,
scripts/layout_hook.py) actually executes.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(PLUGIN_ROOT, "scripts", "tlc")
HOOK = os.path.join(PLUGIN_ROOT, "scripts", "layout_hook.py")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@dataclass
class HookResult:
    """Parsed outcome of one hook invocation (exit code + JSON decision)."""

    exit_code: int
    stderr: str
    decision: Optional[str] = None
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return self.decision == "block" or self.exit_code == 2


def fire_hook(event, cwd, **fields):
    """Simulate the harness dispatching a hook event to the plugin."""
    payload = {"hook_event_name": event, "cwd": cwd, **fields}
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,  # hook exit codes are the signal under test
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return HookResult(
        exit_code=proc.returncode,
        stderr=proc.stderr,
        decision=out.get("decision"),
        reason=out.get("reason", ""),
    )


class FakeAgent:
    """Replays tool calls the way the real subagent would make them."""

    def __init__(self, workdir):
        # realpath: the runner reports resolved paths (macOS /var -> /private/var)
        self.workdir = os.path.realpath(workdir)
        self.hook_results = []  # (tool, path-or-cmd, HookResult)

    def write(self, relpath, content):
        """Write tool call + the PostToolUse hook the harness would fire."""
        path = os.path.join(self.workdir, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        result = fire_hook(
            "PostToolUse",
            self.workdir,
            tool_name="Write",
            tool_input={"file_path": path},
        )
        self.hook_results.append(("Write", relpath, result))
        return result

    def write_fixture(self, relpath, fixture):
        with open(os.path.join(FIXTURES, fixture), encoding="utf-8") as f:
            return self.write(relpath, f.read())

    def run_tlc(self, spec_relpath, *args):
        """Bash tool call: invoke the plugin's runner (real, deterministic TLC)."""
        proc = subprocess.run(
            [RUNNER, spec_relpath, *args],
            capture_output=True,
            text=True,
            cwd=self.workdir,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT},
            check=False,  # runner exit codes are the signal under test
        )
        return proc

    def log_path_from(self, tlc_proc):
        """The log path the runner reported (the agent reads this off stdout)."""
        m = re.search(r"^log: (.+)$", tlc_proc.stdout, re.MULTILINE)
        return m.group(1) if m else None

    def try_stop(self, event="SubagentStop", stop_hook_active=False):
        """The agent ends its turn; the harness fires the stop gate."""
        return fire_hook(
            event, self.workdir, stop_hook_active=stop_hook_active
        )
