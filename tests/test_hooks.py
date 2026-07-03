"""scripts/layout-hook.py: PostToolUse reminders and the Stop gate."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from fake_agent import HOOK, FakeAgent, fire_hook

VIOLATION_LOG = "Error: Invariant AtMostOnce is violated.\nState 1: ...\n"
CLEAN_LOG = "Model checking completed. No error has been found.\n"


class PostToolUseTest(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="model-check-test-")
        self.addCleanup(shutil.rmtree, self.workdir)
        self.agent = FakeAgent(self.workdir)

    def test_non_tla_files_are_silent(self):
        result = self.agent.write("verification/M/MAPPING.md", "# map\n")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stderr, "")

    def test_tla_without_cfg_and_mapping_reminds(self):
        result = self.agent.write("verification/M/M.tla", "---- MODULE M ----\n====\n")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("M.cfg", result.stderr)
        self.assertIn("MAPPING.md", result.stderr)

    def test_complete_layout_is_silent(self):
        self.agent.write("verification/M/M.cfg", "INIT Init\n")
        self.agent.write("verification/M/MAPPING.md", "# map\n")
        result = self.agent.write("verification/M/M.tla", "---- MODULE M ----\n====\n")
        self.assertEqual(result.exit_code, 0)

    def test_ttrace_specs_in_traces_are_exempt(self):
        result = self.agent.write(
            "verification/M/traces/M_TTrace_1.tla", "---- MODULE M_TTrace_1 ----\n====\n"
        )
        self.assertEqual(result.exit_code, 0)

    def test_garbage_stdin_is_harmless(self):
        proc = subprocess.run(
            [sys.executable, HOOK], input="not json", capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0)


class StopGateTest(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="model-check-test-")
        self.addCleanup(shutil.rmtree, self.workdir)
        self.agent = FakeAgent(self.workdir)
        self.traces = "verification/M/traces"

    def test_clean_tree_allows_stop(self):
        self.assertFalse(self.agent.try_stop().blocked)

    def test_clean_run_log_allows_stop(self):
        self.agent.write(f"{self.traces}/M-1.log", CLEAN_LOG)
        self.assertFalse(self.agent.try_stop().blocked)

    def test_unmapped_violation_blocks_stop_and_subagent_stop(self):
        self.agent.write(f"{self.traces}/M-1.log", VIOLATION_LOG)
        for event in ("Stop", "SubagentStop"):
            result = self.agent.try_stop(event)
            self.assertTrue(result.blocked, event)
            self.assertIn("M-1.log", result.reason)
            self.assertIn("M-1.scenario.md", result.reason)

    def test_scenario_unblocks(self):
        self.agent.write(f"{self.traces}/M-1.log", VIOLATION_LOG)
        self.agent.write(f"{self.traces}/M-1.scenario.md", "# scenario\n")
        self.assertFalse(self.agent.try_stop().blocked)

    def test_stop_hook_active_never_loops(self):
        self.agent.write(f"{self.traces}/M-1.log", VIOLATION_LOG)
        self.assertFalse(self.agent.try_stop(stop_hook_active=True).blocked)

    def test_skips_vcs_and_dependency_dirs(self):
        for skipped in (".git", "node_modules"):
            path = os.path.join(self.workdir, skipped, "traces", "M-1.log")
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as f:
                f.write(VIOLATION_LOG)
        self.assertFalse(self.agent.try_stop().blocked)

    def test_only_scans_traces_dirs(self):
        # a violation-looking log outside a traces/ dir is not this plugin's
        self.agent.write("logs/M-1.log", VIOLATION_LOG)
        self.assertFalse(self.agent.try_stop().blocked)

    def test_missing_cwd_falls_back_gracefully(self):
        result = fire_hook("Stop", self.workdir)  # cwd only via payload
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
