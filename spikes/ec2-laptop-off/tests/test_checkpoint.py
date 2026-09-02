from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
GUEST_ROOT = SPIKE_ROOT / "guest"
sys.path.insert(0, str(SPIKE_ROOT))
sys.path.insert(0, str(GUEST_ROOT))

import checkpoint as checkpoint_module  # noqa: E402
from checkpoint import CheckpointError, create_checkpoint  # noqa: E402
from workspace import capture_baseline, create_fixture  # noqa: E402


def git(*arguments: str, cwd: Path | None = None, git_dir: Path | None = None) -> str:
    command = ["git"]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout


class CloudCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-checkpoint-test-")
        self.root = Path(self.temporary.name).resolve()
        local = self.root / "local"
        marker = create_fixture(local)
        self.ledger = self.root / "ledger.git"
        self.capture = capture_baseline(
            workspace=local,
            ledger=self.ledger,
            run_id="p0-test-run",
            workspace_id="lift-ec2-spike",
            approved_ignored=[marker["approvedIgnoredPath"]],
        )
        self.workspace = self.root / "cloud"
        git("clone", "--no-checkout", str(self.ledger), str(self.workspace))
        git("checkout", "--detach", self.capture.commit, cwd=self.workspace)
        git("config", "user.name", "Cloud User", cwd=self.workspace)
        git("config", "user.email", "cloud@example.invalid", cwd=self.workspace)

        (self.workspace / "REMOTE_TEST.md").write_text(
            "Status: committed from the cloud.\n", encoding="utf-8"
        )
        git("add", "REMOTE_TEST.md", cwd=self.workspace)
        git("commit", "-m", "Cloud-authored commit", cwd=self.workspace)
        self.cloud_head = git("rev-parse", "HEAD", cwd=self.workspace).strip()
        (self.workspace / ".lift").mkdir()
        self.phone_proof = b'{"source":"codex-phone"}\n'
        (self.workspace / ".lift" / "phone-proof.json").write_bytes(self.phone_proof)
        (self.workspace / "excluded.env").write_text(
            "SECRET=MUST_NOT_ENTER_CHECKPOINT\n", encoding="utf-8"
        )

        self.state_path = self.root / "workspace-state.json"
        self.state_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": "p0-test-run",
                    "workspaceId": "lift-ec2-spike",
                    "workspacePath": str(self.workspace),
                    "ledgerPath": str(self.ledger),
                    "baselineCommit": self.capture.commit,
                    "baselineRef": self.capture.ref,
                }
            ),
            encoding="utf-8",
        )
        self.checkpoints_root = self.root / "checkpoints"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def checkpoint(
        self,
        *,
        ordinal: int = 1,
        label: str = "phone-proof",
        required_path: str = ".lift/phone-proof.json",
        required_content: bytes | None = None,
    ):
        evidence = self.phone_proof if required_content is None else required_content
        return create_checkpoint(
            workspace=self.workspace,
            ledger=self.ledger,
            state_path=self.state_path,
            checkpoints_root=self.checkpoints_root,
            run_id="p0-test-run",
            workspace_id="lift-ec2-spike",
            ordinal=ordinal,
            label=label,
            required_path=required_path,
            required_sha256=hashlib.sha256(evidence).hexdigest(),
            required_size=len(evidence),
            require_durable_mount=False,
        )

    def test_checkpoint_preserves_cloud_git_history_and_content_manifest(self) -> None:
        before_head = git("rev-parse", "HEAD", cwd=self.workspace)
        before_refs = git("for-each-ref", "--format=%(refname) %(objectname)", cwd=self.workspace)
        before_status = git("status", "--porcelain=v2", "--untracked-files=all", cwd=self.workspace)
        before_index = (self.workspace / ".git" / "index").read_bytes()

        result = self.checkpoint()

        self.assertEqual(before_head, git("rev-parse", "HEAD", cwd=self.workspace))
        self.assertEqual(before_refs, git("for-each-ref", "--format=%(refname) %(objectname)", cwd=self.workspace))
        self.assertEqual(before_status, git("status", "--porcelain=v2", "--untracked-files=all", cwd=self.workspace))
        self.assertEqual(before_index, (self.workspace / ".git" / "index").read_bytes())

        git("cat-file", "-e", f"{self.cloud_head}^{{commit}}", git_dir=self.ledger)
        parents = git("show", "-s", "--format=%P", result["commit"], git_dir=self.ledger).split()
        self.assertEqual([self.capture.commit, self.cloud_head], parents)

        manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in manifest["entries"]}
        self.assertIn(".lift/phone-proof.json", paths)
        self.assertIn("REMOTE_TEST.md", paths)
        self.assertIn("approved-state/approved.txt", paths)
        self.assertNotIn("excluded.env", paths)

        bundle_heads = git("bundle", "list-heads", result["bundlePath"])
        self.assertIn(result["ref"], bundle_heads)
        self.assertTrue(any(item["ref"] in bundle_heads for item in result["historyRefs"]))

    def test_retry_is_immutable_and_rejects_changed_content(self) -> None:
        first = self.checkpoint()
        second = self.checkpoint()
        self.assertFalse(second["changed"])
        self.assertEqual(first["commit"], second["commit"])
        self.assertEqual(first["bundleSha256"], second["bundleSha256"])

        (self.workspace / ".lift" / "phone-proof.json").write_text(
            '{"source":"changed"}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(
            CheckpointError, "immutable checkpoint|required phone evidence"
        ):
            self.checkpoint()

    def test_unignoring_sentinel_cannot_admit_it_to_a_checkpoint(self) -> None:
        (self.workspace / ".gitignore").write_text(
            "approved-state/\n",
            encoding="utf-8",
        )
        (self.workspace / "excluded.env").write_text(
            "SECRET=VISIBLE_TO_GIT_BUT_NEVER_TO_LIFT\n",
            encoding="utf-8",
        )
        git("add", "-f", "excluded.env", cwd=self.workspace)
        before_index = (self.workspace / ".git" / "index").read_bytes()

        result = self.checkpoint()

        self.assertEqual(before_index, (self.workspace / ".git" / "index").read_bytes())
        manifest = json.loads(
            Path(result["manifestPath"]).read_text(encoding="utf-8")
        )
        paths = {entry["path"] for entry in manifest["entries"]}
        tree_paths = set(
            git(
                "ls-tree",
                "-r",
                "--name-only",
                result["commit"],
                git_dir=self.ledger,
            ).splitlines()
        )
        self.assertNotIn("excluded.env", paths)
        self.assertNotIn("excluded.env", tree_paths)
        self.assertEqual(
            "approved-state/\n",
            git("show", f"{result['commit']}:.gitignore", git_dir=self.ledger),
        )
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(self.capture.fixture_policy, state["fixturePolicy"])
        self.assertEqual(self.capture.fixture_policy, result["fixturePolicy"])

    def test_force_added_ignored_tracked_files_remain_in_checkpoint(self) -> None:
        ignored_committed = "ignored-committed.bin"
        ignored_staged = "ignored-staged.bin"
        with (self.workspace / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write(f"{ignored_committed}\n{ignored_staged}\n")
        committed_content = b"committed ignored bytes\x00\xff\n"
        staged_content = b"staged ignored bytes\x00\xfe\n"
        (self.workspace / ignored_committed).write_bytes(committed_content)
        git("add", ".gitignore", cwd=self.workspace)
        git("add", "-f", ignored_committed, cwd=self.workspace)
        git("commit", "-m", "Track an intentionally ignored cloud file", cwd=self.workspace)
        (self.workspace / ignored_staged).write_bytes(staged_content)
        git("add", "-f", ignored_staged, cwd=self.workspace)
        before_index = (self.workspace / ".git" / "index").read_bytes()

        result = self.checkpoint()

        self.assertEqual(before_index, (self.workspace / ".git" / "index").read_bytes())
        manifest = json.loads(
            Path(result["manifestPath"]).read_text(encoding="utf-8")
        )
        entries = {entry["path"]: entry for entry in manifest["entries"]}
        self.assertEqual(
            hashlib.sha256(committed_content).hexdigest(),
            entries[ignored_committed]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(staged_content).hexdigest(),
            entries[ignored_staged]["sha256"],
        )
        for path, content in (
            (ignored_committed, committed_content),
            (ignored_staged, staged_content),
        ):
            blob = subprocess.run(
                ["git", f"--git-dir={self.ledger}", "show", f"{result['commit']}:{path}"],
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(content, blob)
        self.assertNotIn("excluded.env", entries)

    def test_second_checkpoint_chains_from_first_and_binds_new_evidence(self) -> None:
        first = self.checkpoint()
        first_ref_commit = git("rev-parse", first["ref"], git_dir=self.ledger).strip()
        laptop_off_proof = (
            b'{"cwd":"/home/lift/workspaces/lift-ec2-spike",'
            b'"nonce":"offline-test-nonce","schemaVersion":1,'
            b'"source":"codex-phone-laptop-off"}\n'
        )
        laptop_off_path = ".lift/laptop-off-proof.json"
        (self.workspace / laptop_off_path).write_bytes(laptop_off_proof)

        second = self.checkpoint(
            ordinal=2,
            label="laptop-off-proof",
            required_path=laptop_off_path,
            required_content=laptop_off_proof,
        )

        self.assertTrue(second["changed"])
        self.assertEqual(2, second["ordinal"])
        self.assertEqual(first["ref"], second["parentRef"])
        self.assertEqual(first["commit"], second["parentCommit"])
        self.assertEqual([first["commit"]], second["parents"])
        self.assertEqual(
            [first["commit"]],
            git(
                "show", "-s", "--format=%P", second["commit"], git_dir=self.ledger
            ).split(),
        )
        self.assertEqual(
            first_ref_commit,
            git("rev-parse", first["ref"], git_dir=self.ledger).strip(),
        )

        manifest = json.loads(Path(second["manifestPath"]).read_text(encoding="utf-8"))
        entries = {entry["path"]: entry for entry in manifest["entries"]}
        self.assertIn(".lift/phone-proof.json", entries)
        self.assertEqual(
            {
                "sha256": hashlib.sha256(laptop_off_proof).hexdigest(),
                "size": len(laptop_off_proof),
                "type": "file",
                "executable": False,
            },
            {
                key: entries[laptop_off_path][key]
                for key in ("sha256", "size", "type", "executable")
            },
        )

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual([1, 2], [item["ordinal"] for item in state["checkpoints"]])
        self.assertEqual(first["commit"], state["checkpoints"][0]["commit"])
        self.assertEqual(second["ref"], state["latestCheckpointRef"])
        self.assertEqual(second["commit"], state["latestCheckpointCommit"])

        bundle_heads = git("bundle", "list-heads", second["bundlePath"])
        self.assertIn(first["ref"], bundle_heads)
        self.assertIn(second["ref"], bundle_heads)
        self.assertEqual(
            [
                {"ref": self.capture.ref, "objectId": self.capture.commit},
                {"ref": first["ref"], "objectId": first["commit"]},
                {"ref": second["ref"], "objectId": second["commit"]},
            ],
            second["recoveryCheckpointRefs"],
        )
        self.assertEqual(
            first["recoveryHistoryRefs"],
            second["recoveryHistoryRefs"][: len(first["recoveryHistoryRefs"])],
        )
        for item in [
            *second["recoveryCheckpointRefs"],
            *second["recoveryHistoryRefs"],
        ]:
            self.assertIn(f"{item['objectId']} {item['ref']}", bundle_heads)

    def test_private_git_wrapper_disables_hostile_hooks_and_fsmonitor(self) -> None:
        hostile = self.root / "hostile-git"
        hostile.mkdir()
        hook_marker = hostile / "reference-transaction-ran"
        monitor_marker = hostile / "fsmonitor-ran"
        hooks = hostile / "hooks"
        hooks.mkdir()
        reference_hook = hooks / "reference-transaction"
        reference_hook.write_text(
            "#!/bin/sh\n"
            f"printf ran > {hook_marker}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        reference_hook.chmod(0o755)
        fsmonitor = hostile / "fsmonitor"
        fsmonitor.write_text(
            "#!/bin/sh\n"
            f"printf ran > {monitor_marker}\n"
            "printf 'fake-token\\n'\n",
            encoding="utf-8",
        )
        fsmonitor.chmod(0o755)
        git("config", "core.hooksPath", str(hooks), git_dir=self.ledger)
        git("config", "core.fsmonitor", str(fsmonitor), git_dir=self.ledger)
        private_index = self.root / "hostile-wrapper.index"
        ref = "refs/lift/test-hostile-wrapper"
        hostile_environment = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": str(hooks),
            "GIT_CONFIG_KEY_1": "core.fsmonitor",
            "GIT_CONFIG_VALUE_1": str(fsmonitor),
        }

        with mock.patch.dict(os.environ, hostile_environment, clear=False):
            checkpoint_module.git(
                self.ledger,
                ["read-tree", self.capture.commit],
                workspace=self.workspace,
                index=private_index,
            )
            status = checkpoint_module.git(
                self.ledger,
                ["status", "--porcelain=v2", "--untracked-files=all"],
                workspace=self.workspace,
                index=private_index,
            )
            checkpoint_module.git(
                self.ledger,
                ["update-ref", "--no-deref", ref, self.capture.commit, "0" * 40],
            )

        self.assertIn("REMOTE_TEST.md", status.stdout)
        self.assertEqual(
            self.capture.commit,
            git("rev-parse", ref, git_dir=self.ledger).strip(),
        )
        self.assertFalse(hook_marker.exists())
        self.assertFalse(monitor_marker.exists())


if __name__ == "__main__":
    unittest.main()
