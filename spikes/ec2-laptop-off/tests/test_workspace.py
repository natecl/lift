from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

from workspace import (  # noqa: E402
    WorkspaceError,
    build_lift_off_archive,
    capture_baseline,
    create_fixture,
)


def git(*arguments: str, cwd: Path | None = None, git_dir: Path | None = None) -> str:
    command = ["git"]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout


class WorkspaceCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-workspace-test-")
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "fixture"
        self.marker = create_fixture(self.workspace)
        self.ledger = self.root / "ledger.git"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def capture(self):
        return capture_baseline(
            workspace=self.workspace,
            ledger=self.ledger,
            run_id="p0-test-run",
            workspace_id="lift-ec2-spike",
            approved_ignored=[self.marker["approvedIgnoredPath"]],
        )

    def test_capture_preserves_real_git_state_and_includes_expected_content(self) -> None:
        before_head = git("rev-parse", "HEAD", cwd=self.workspace)
        before_refs = git("for-each-ref", "--format=%(refname) %(objectname)", cwd=self.workspace)
        before_status = git("status", "--porcelain=v2", "--untracked-files=all", cwd=self.workspace)
        index_path = Path(git("rev-parse", "--git-path", "index", cwd=self.workspace).strip())
        if not index_path.is_absolute():
            index_path = self.workspace / index_path
        before_index = index_path.read_bytes()

        capture = self.capture()

        self.assertEqual(before_head, git("rev-parse", "HEAD", cwd=self.workspace))
        self.assertEqual(before_refs, git("for-each-ref", "--format=%(refname) %(objectname)", cwd=self.workspace))
        self.assertEqual(before_status, git("status", "--porcelain=v2", "--untracked-files=all", cwd=self.workspace))
        self.assertEqual(before_index, index_path.read_bytes())

        tree_paths = set(
            git("ls-tree", "-r", "--name-only", capture.commit, git_dir=self.ledger).splitlines()
        )
        self.assertIn("DIRTY_LOCAL.md", tree_paths)
        self.assertIn("STAGED_AND_DIRTY.md", tree_paths)
        self.assertIn("UNTRACKED.md", tree_paths)
        self.assertIn("approved-state/approved.txt", tree_paths)
        self.assertNotIn("excluded.env", tree_paths)

        dirty = git("show", f"{capture.commit}:DIRTY_LOCAL.md", git_dir=self.ledger)
        staged_and_dirty = git("show", f"{capture.commit}:STAGED_AND_DIRTY.md", git_dir=self.ledger)
        self.assertEqual("State: dirty local tracked change.\n", dirty)
        self.assertEqual(
            "State: staged change.\nState: additional unstaged change.\n",
            staged_and_dirty,
        )

        manifest_paths = {entry["path"] for entry in capture.manifest["entries"]}
        self.assertEqual(tree_paths, manifest_paths)
        self.assertNotIn("excluded.env", json.dumps(capture.manifest))

    def test_retry_reuses_immutable_baseline(self) -> None:
        first = self.capture()
        second = self.capture()
        self.assertEqual(first.commit, second.commit)
        self.assertEqual(first.ref, second.ref)

    def test_retry_rejects_different_content(self) -> None:
        self.capture()
        (self.workspace / "DIRTY_LOCAL.md").write_text("State: changed after capture.\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "immutable baseline"):
            self.capture()

    def test_capture_refuses_an_unmarked_real_workspace(self) -> None:
        (self.workspace / ".lift-spike-fixture.json").unlink()
        with self.assertRaisesRegex(WorkspaceError, "fixture marker"):
            self.capture()
        self.assertFalse(self.ledger.exists())

    def test_archive_contains_only_the_private_bundle_and_nonsecret_metadata(self) -> None:
        capture = self.capture()
        destination = self.root / "lift-off.tar.gz"
        digest = build_lift_off_archive(
            destination=destination,
            ledger=self.ledger,
            capture=capture,
            run_id="p0-test-run",
            workspace_id="lift-ec2-spike",
        )
        self.assertEqual(64, len(digest))
        with tarfile.open(destination, "r:gz") as archive:
            self.assertEqual(
                {"ledger.bundle", "manifest.json", "session.json"},
                {member.name for member in archive.getmembers()},
            )
            manifest_text = archive.extractfile("manifest.json").read().decode("utf-8")
            self.assertNotIn("THIS_FILE_MUST_NEVER_TRANSFER", manifest_text)


if __name__ == "__main__":
    unittest.main()
