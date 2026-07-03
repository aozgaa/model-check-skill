"""A zero-token fake of the tla-modeler agent + Claude Code harness.

The real system is: an LLM makes tool calls (Write/Bash), and the harness
fires this plugin's hooks around them (PostToolUse after writes, Stop /
SubagentStop when the agent tries to finish). For testing, the LLM is
replaced by a scripted transcript of tool calls, so runs are deterministic
and cost nothing; only the plugin's own machinery (scripts/tlc,
scripts/layout-hook.py) actually executes.
"""

import json
import os
import re
import subprocess
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(PLUGIN_ROOT, "scripts", "tlc")
HOOK = os.path.join(PLUGIN_ROOT, "scripts", "layout-hook.py")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class HookResult:
    def __init__(self, proc):
        self.exit_code = proc.returncode
        self.stderr = proc.stderr
        self.decision = None
        self.reason = ""
        if proc.stdout.strip():
            out = json.loads(proc.stdout)
            self.decision = out.get("decision")
            self.reason = out.get("reason", "")

    @property
    def blocked(self):
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
    )
    return HookResult(proc)


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
        with open(path, "w") as f:
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
        with open(os.path.join(FIXTURES, fixture)) as f:
            return self.write(relpath, f.read())

    def run_tlc(self, spec_relpath, *args):
        """Bash tool call: invoke the plugin's runner (real, deterministic TLC)."""
        proc = subprocess.run(
            [RUNNER, spec_relpath, *args],
            capture_output=True,
            text=True,
            cwd=self.workdir,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT},
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
