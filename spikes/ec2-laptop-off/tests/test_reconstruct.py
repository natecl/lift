from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


GUEST_ROOT = Path(__file__).resolve().parents[1] / "guest"
sys.path.insert(0, str(GUEST_ROOT))

import reconstruct as reconstruct_module  # noqa: E402


class ReconstructGitEnvironmentTests(unittest.TestCase):
    def test_git_ignores_ambient_git_configuration_and_disables_hooks(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )
        hostile = {
            "GIT_CONFIG_GLOBAL": "/tmp/hostile-gitconfig",
            "GIT_DIR": "/tmp/hostile-git-dir",
            "GIT_WORK_TREE": "/tmp/hostile-work-tree",
        }
        with (
            mock.patch.dict(os.environ, hostile, clear=False),
            mock.patch.object(
                reconstruct_module.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            self.assertEqual("ok\n", reconstruct_module.git(["status"]))

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual("git", command[0])
        self.assertIn("core.hooksPath=/dev/null", command)
        self.assertIn("core.fsmonitor=false", command)
        self.assertEqual("1", environment["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(os.devnull, environment["GIT_CONFIG_GLOBAL"])
        self.assertEqual("0", environment["GIT_TERMINAL_PROMPT"])
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_WORK_TREE", environment)


if __name__ == "__main__":
    unittest.main()
