"""End-to-end replay of the tla-modeler pipeline with a faked LLM.

The transcript below is the tool-call sequence a compliant agent makes on the
jobqueue fixture (a real TOCTOU race; the spec/mapping are golden artifacts
from a verified run). At each step we assert the plugin machinery — runner and
hooks — steers a non-compliant agent back and lets a compliant one finish.
"""

import os
import shutil
import tempfile
import unittest

from fake_agent import FakeAgent


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="model-check-test-")
        self.addCleanup(shutil.rmtree, self.workdir)
        self.agent = FakeAgent(self.workdir)
        self.agent.write_fixture("jobqueue.py", "jobqueue/jobqueue.py")

    def test_full_pipeline(self):
        agent = self.agent
        model = "verification/JobQueue"

        # Step 1: spec written first -> harness reminds about the rest
        result = agent.write_fixture(f"{model}/JobQueue.tla", "jobqueue/JobQueue.tla")
        self.assertTrue(result.blocked)
        self.assertIn("JobQueue.cfg", result.stderr)
        self.assertIn("MAPPING.md", result.stderr)

        # Step 2: runner still refuses while MAPPING.md is missing
        agent.write_fixture(f"{model}/JobQueue.cfg", "jobqueue/JobQueue.cfg")
        proc = agent.run_tlc(f"{model}/JobQueue.tla")
        self.assertEqual(proc.returncode, 3)

        # Step 3: layout completed -> TLC runs and finds the race
        agent.write_fixture(f"{model}/MAPPING.md", "jobqueue/MAPPING.md")
        proc = agent.run_tlc(f"{model}/JobQueue.tla")
        self.assertEqual(proc.returncode, 12)
        log = agent.log_path_from(proc)
        with open(log) as f:
            self.assertIn("Error: Invariant AtMostOnce is violated.", f.read())

        # Step 4: agent tries to finish without back-mapping -> gate blocks
        result = agent.try_stop("SubagentStop")
        self.assertTrue(result.blocked)
        self.assertIn(os.path.basename(log), result.reason)
        self.assertIn(".scenario.md", result.reason)

        # Step 5: agent writes the scenario the gate named -> may finish
        scenario = log[: -len(".log")] + ".scenario.md"
        with open(os.path.join(os.path.dirname(__file__), "fixtures/jobqueue/scenario.md")) as f:
            agent.write(os.path.relpath(scenario, agent.workdir), f.read())
        self.assertFalse(agent.try_stop("SubagentStop").blocked)

        # ... and the parent session may stop too
        self.assertFalse(agent.try_stop("Stop").blocked)


if __name__ == "__main__":
    unittest.main()
