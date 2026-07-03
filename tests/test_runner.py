"""scripts/tlc: layout enforcement, log persistence, violation reporting."""

import glob
import os
import shutil
import tempfile
import unittest

from fake_agent import FakeAgent

VIOLATING_TLA = """---- MODULE Bump ----
EXTENDS Naturals
VARIABLE x
Init == x = 0
Next == x' = x + 1
Inv == x < 3
====
"""
VIOLATING_CFG = "INIT Init\nNEXT Next\nINVARIANT Inv\n"

PASSING_TLA = """---- MODULE Cycle ----
EXTENDS Naturals
VARIABLE x
Init == x = 0
Next == x' = (x + 1) % 3
Inv == x < 3
====
"""
PASSING_CFG = "INIT Init\nNEXT Next\nINVARIANT Inv\n"


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="model-check-test-")
        self.addCleanup(shutil.rmtree, self.workdir)
        self.agent = FakeAgent(self.workdir)

    def model(self, name, tla, cfg, mapping="# stub mapping\n"):
        d = f"verification/{name}"
        self.agent.write(f"{d}/{name}.tla", tla)
        if cfg is not None:
            self.agent.write(f"{d}/{name}.cfg", cfg)
        if mapping is not None:
            self.agent.write(f"{d}/MAPPING.md", mapping)
        return f"{d}/{name}.tla"

    def test_refuses_without_cfg(self):
        spec = self.model("Bump", VIOLATING_TLA, cfg=None)
        proc = self.agent.run_tlc(spec)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("Bump.cfg is missing", proc.stderr)

    def test_refuses_without_mapping(self):
        spec = self.model("Bump", VIOLATING_TLA, VIOLATING_CFG, mapping=None)
        proc = self.agent.run_tlc(spec)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("MAPPING.md is missing", proc.stderr)

    def test_violation_flow(self):
        spec = self.model("Bump", VIOLATING_TLA, VIOLATING_CFG)
        proc = self.agent.run_tlc(spec)
        self.assertEqual(proc.returncode, 12)  # TLC safety-violation exit

        # every run is persisted to traces/
        log = self.agent.log_path_from(proc)
        self.assertIsNotNone(log)
        self.assertIn("/verification/Bump/traces/", log)
        with open(log, encoding="utf-8") as f:
            self.assertIn("Error: Invariant Inv is violated.", f.read())

        # the runner demands the back-mapping artifacts
        self.assertIn("COUNTEREXAMPLE FOUND", proc.stderr)
        scenario = log[: -len(".log")] + ".scenario.md"
        self.assertIn(os.path.basename(scenario), proc.stderr)
        self.assertIn("failing test", proc.stderr)

        # TTrace specs live with the trace; TLC metadata is cleaned up
        traces = os.path.join(self.workdir, "verification/Bump/traces")
        self.assertTrue(glob.glob(os.path.join(traces, "Bump_TTrace_*.tla")))
        model_dir = os.path.join(self.workdir, "verification/Bump")
        self.assertFalse(glob.glob(os.path.join(model_dir, "*_TTrace_*")))
        self.assertFalse(os.path.exists(os.path.join(traces, ".tlc-meta")))

    def test_pass_flow(self):
        spec = self.model("Cycle", PASSING_TLA, PASSING_CFG)
        proc = self.agent.run_tlc(spec)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("No violation found", proc.stdout)
        self.assertIn("constants are large enough", proc.stdout)
        self.assertIsNotNone(self.agent.log_path_from(proc))

    def test_all_mode_aggregates(self):
        self.model("Bump", VIOLATING_TLA, VIOLATING_CFG)
        self.model("Cycle", PASSING_TLA, PASSING_CFG)
        proc = self.agent.run_tlc("--all", "verification")
        self.assertEqual(proc.returncode, 12)  # the violation wins
        self.assertIn("=== verification/Bump/Bump.tla ===", proc.stdout)
        self.assertIn("=== verification/Cycle/Cycle.tla ===", proc.stdout)


if __name__ == "__main__":
    unittest.main()
