from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
GUEST_ROOT = SPIKE_ROOT / "guest"
sys.path.insert(0, str(SPIKE_ROOT))
sys.path.insert(0, str(GUEST_ROOT))

from checkpoint import create_checkpoint  # noqa: E402
import land as land_module  # noqa: E402
from land import LandError, land_fixture  # noqa: E402
from workspace import capture_baseline, create_fixture  # noqa: E402


def git(
    *arguments: str,
    cwd: Path | None = None,
    git_dir: Path | None = None,
) -> str:
    command = ["git"]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def git_admin_snapshot(workspace: Path) -> dict[str, bytes | str]:
    raw_index = git("rev-parse", "--git-path", "index", cwd=workspace).strip()
    index = Path(raw_index)
    if not index.is_absolute():
        index = workspace / index
    return {
        "head": git("rev-parse", "HEAD", cwd=workspace),
        "branch": git("symbolic-ref", "HEAD", cwd=workspace),
        "refs": git(
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            cwd=workspace,
        ),
        "index": index.read_bytes(),
    }


def filesystem_snapshot(root: Path) -> dict[str, tuple[str, int, str]]:
    result: dict[str, tuple[str, int, str]] = {}
    for directory, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        parent = Path(directory)
        for name in sorted([*directory_names, *file_names]):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                result[relative] = ("symlink", mode, os.readlink(path))
            elif stat.S_ISREG(metadata.st_mode):
                result[relative] = (
                    "file",
                    mode,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            elif stat.S_ISDIR(metadata.st_mode):
                result[relative] = ("directory", mode, "")
            else:
                raise AssertionError(f"unexpected fixture entry: {relative}")
    return result


class LandFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-land-test-")
        self.root = Path(self.temporary.name).resolve()
        self.run_id = "p0-test-run"
        self.workspace_id = "lift-ec2-spike"
        self.workspace = self.root / "local"
        self.marker = create_fixture(self.workspace)
        self.approved_ignored = (self.marker["approvedIgnoredPath"],)
        self.ledger = self.root / "ledger.git"
        self.baseline = capture_baseline(
            workspace=self.workspace,
            ledger=self.ledger,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            approved_ignored=self.approved_ignored,
        )

        self.cloud = self.root / "cloud"
        git("clone", "--no-checkout", str(self.ledger), str(self.cloud))
        git("checkout", "--detach", self.baseline.commit, cwd=self.cloud)
        self.cloud_state = self.root / "cloud-state.json"
        self.cloud_state.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": self.run_id,
                    "workspaceId": self.workspace_id,
                    "workspacePath": str(self.cloud),
                    "ledgerPath": str(self.ledger),
                    "baselineCommit": self.baseline.commit,
                    "baselineRef": self.baseline.ref,
                }
            ),
            encoding="utf-8",
        )
        self.checkpoints = self.root / "checkpoints"
        self.operation_root = self.root / "land-operation"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def checkpoint_cloud(self) -> dict[str, object]:
        return create_checkpoint(
            workspace=self.cloud,
            ledger=self.ledger,
            state_path=self.cloud_state,
            checkpoints_root=self.checkpoints,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            ordinal=1,
            label="land-final",
            expected_volume_id=None,
            required_path=None,
            required_sha256=None,
            required_size=None,
            require_durable_mount=False,
        )

    def land(
        self,
        cloud: dict[str, object],
        *,
        fail_after_apply: int | None = None,
    ) -> dict:
        return land_fixture(
            workspace=self.workspace,
            ledger=self.ledger,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            baseline_ref=self.baseline.ref,
            baseline_commit=self.baseline.commit,
            cloud_ref=str(cloud["ref"]),
            cloud_commit=str(cloud["commit"]),
            approved_ignored=self.approved_ignored,
            operation_root=self.operation_root,
            fail_after_apply=fail_after_apply,
        )

    def assert_applied_refs(
        self, result: dict, cloud: dict[str, object]
    ) -> dict[str, str]:
        self.assertEqual("APPLIED", result["outcome"])
        refs: dict[str, str] = {}
        for key in (
            "localReturnRef",
            "cloudFinalRef",
            "mergeResultRef",
            "receiptRef",
        ):
            ref = result.get(key)
            self.assertIsInstance(ref, str)
            self.assertTrue(ref.startswith(f"refs/lift/{self.workspace_id}/"))
            refs[key] = git("rev-parse", "--verify", ref, git_dir=self.ledger).strip()
        self.assertEqual(cloud["commit"], refs["cloudFinalRef"])
        return refs

    def test_unchanged_local_applies_cloud_delta_without_touching_git_admin(self) -> None:
        expected_remote = "Status: landed from the cloud.\n"
        (self.cloud / "REMOTE_TEST.md").write_text(expected_remote, encoding="utf-8")
        (self.cloud / "CLOUD_ONLY.md").write_text(
            "Created while lifted.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original_git = git_admin_snapshot(self.workspace)

        result = self.land(cloud)

        refs = self.assert_applied_refs(result, cloud)
        self.assertEqual(expected_remote, (self.workspace / "REMOTE_TEST.md").read_text())
        self.assertEqual(
            "Created while lifted.\n",
            (self.workspace / "CLOUD_ONLY.md").read_text(),
        )
        self.assertEqual(original_git, git_admin_snapshot(self.workspace))
        merge_tree = git(
            "show", "-s", "--format=%T", refs["mergeResultRef"], git_dir=self.ledger
        ).strip()
        self.assertEqual(
            expected_remote,
            git("show", f"{merge_tree}:REMOTE_TEST.md", git_dir=self.ledger),
        )

    def test_disjoint_local_and_cloud_edits_are_combined(self) -> None:
        local_value = "State: changed locally while lifted.\n"
        cloud_value = "Status: changed independently in the cloud.\n"
        (self.workspace / "DIRTY_LOCAL.md").write_text(local_value, encoding="utf-8")
        (self.cloud / "REMOTE_TEST.md").write_text(cloud_value, encoding="utf-8")
        cloud = self.checkpoint_cloud()
        original_git = git_admin_snapshot(self.workspace)

        result = self.land(cloud)

        self.assert_applied_refs(result, cloud)
        self.assertEqual(local_value, (self.workspace / "DIRTY_LOCAL.md").read_text())
        self.assertEqual(cloud_value, (self.workspace / "REMOTE_TEST.md").read_text())
        self.assertEqual(original_git, git_admin_snapshot(self.workspace))

    def test_same_file_divergence_preserves_original_workspace_and_refs(self) -> None:
        (self.workspace / "REMOTE_TEST.md").write_text(
            "Status: edited on the Mac.\n", encoding="utf-8"
        )
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: edited in the cloud.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original_workspace = filesystem_snapshot(self.workspace)
        original_baseline = git(
            "rev-parse", self.baseline.ref, git_dir=self.ledger
        ).strip()
        original_cloud = git("rev-parse", str(cloud["ref"]), git_dir=self.ledger).strip()

        result = self.land(cloud)

        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertTrue(result.get("conflicts"))
        self.assertIn("REMOTE_TEST.md", json.dumps(result["conflicts"], sort_keys=True))
        conflict_worktree = Path(result["conflictWorktree"])
        self.assertTrue(conflict_worktree.is_dir())
        self.assertNotEqual(self.workspace, conflict_worktree)
        self.assertEqual(original_workspace, filesystem_snapshot(self.workspace))
        self.assertEqual(
            original_baseline,
            git("rev-parse", self.baseline.ref, git_dir=self.ledger).strip(),
        )
        self.assertEqual(
            original_cloud,
            git("rev-parse", str(cloud["ref"]), git_dir=self.ledger).strip(),
        )

    def test_excluded_sentinel_never_enters_the_landed_result(self) -> None:
        original_excluded = (self.workspace / "excluded.env").read_bytes()
        (self.cloud / "excluded.env").write_text(
            "SECRET=CHANGED_IN_CLOUD\n", encoding="utf-8"
        )
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: safe cloud delta.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        cloud_manifest = json.loads(
            Path(str(cloud["manifestPath"])).read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "excluded.env", {entry["path"] for entry in cloud_manifest["entries"]}
        )

        result = self.land(cloud)

        refs = self.assert_applied_refs(result, cloud)
        self.assertEqual(original_excluded, (self.workspace / "excluded.env").read_bytes())
        result_paths = set(
            git(
                "ls-tree",
                "-r",
                "--name-only",
                refs["mergeResultRef"],
                git_dir=self.ledger,
            ).splitlines()
        )
        self.assertNotIn("excluded.env", result_paths)

    def test_retry_after_success_reuses_the_same_refs_and_result(self) -> None:
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: idempotently landed.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()

        first = self.land(cloud)
        first_refs = self.assert_applied_refs(first, cloud)
        applied_workspace = filesystem_snapshot(self.workspace)
        second = self.land(cloud)
        second_refs = self.assert_applied_refs(second, cloud)

        self.assertEqual(first_refs, second_refs)
        self.assertEqual(applied_workspace, filesystem_snapshot(self.workspace))

    def test_retry_completes_after_injected_crash_during_apply(self) -> None:
        (self.cloud / "FIRST_CLOUD_FILE.md").write_text(
            "First cloud operation.\n", encoding="utf-8"
        )
        (self.cloud / "SECOND_CLOUD_FILE.md").write_text(
            "Second cloud operation.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original_git = git_admin_snapshot(self.workspace)

        with self.assertRaises(RuntimeError):
            self.land(cloud, fail_after_apply=1)

        result = self.land(cloud)

        self.assert_applied_refs(result, cloud)
        self.assertEqual(
            "First cloud operation.\n",
            (self.workspace / "FIRST_CLOUD_FILE.md").read_text(),
        )
        self.assertEqual(
            "Second cloud operation.\n",
            (self.workspace / "SECOND_CLOUD_FILE.md").read_text(),
        )
        self.assertEqual(original_git, git_admin_snapshot(self.workspace))

    def test_replacement_crash_keeps_original_and_resumes(self) -> None:
        original = (self.workspace / "REMOTE_TEST.md").read_bytes()
        replacement = b"Status: replaced durably in the cloud.\n"
        (self.cloud / "REMOTE_TEST.md").write_bytes(replacement)
        cloud = self.checkpoint_cloud()

        with self.assertRaisesRegex(LandError, "injected failure"):
            self.land(cloud, fail_after_apply=1)

        journal = json.loads(
            (self.operation_root / "apply-journal.json").read_text(encoding="utf-8")
        )
        operation = next(
            item for item in journal["operations"] if item["path"] == "REMOTE_TEST.md"
        )
        moved = Path(operation["movedPath"])
        self.assertEqual(original, moved.read_bytes())
        self.assertEqual(replacement, (self.workspace / "REMOTE_TEST.md").read_bytes())

        result = self.land(cloud)

        self.assertEqual("APPLIED", result["outcome"])
        self.assertEqual(original, moved.read_bytes())
        self.assertEqual(replacement, (self.workspace / "REMOTE_TEST.md").read_bytes())

    def test_tampered_journal_path_is_rejected_and_partial_apply_rolls_back(self) -> None:
        (self.cloud / "AAA_CLOUD.md").write_text("cloud\n", encoding="utf-8")
        (self.cloud / "ZZZ_CLOUD.md").write_text("cloud\n", encoding="utf-8")
        cloud = self.checkpoint_cloud()
        victim = self.root / "must-not-touch.txt"
        victim.write_text("private\n", encoding="utf-8")

        with self.assertRaisesRegex(LandError, "injected failure"):
            self.land(cloud, fail_after_apply=1)
        journal_path = self.operation_root / "apply-journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["operations"][0]["path"] = "../must-not-touch.txt"
        journal_path.write_text(
            json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(journal_path, 0o600)

        with self.assertRaisesRegex(LandError, "canonical B/L/C"):
            self.land(cloud)

        self.assertEqual("private\n", victim.read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / "AAA_CLOUD.md").exists())
        self.assertFalse((self.workspace / "ZZZ_CLOUD.md").exists())

    def test_receipt_payload_is_the_only_blob_in_its_private_git_tree(self) -> None:
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: receipt-backed.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()

        result = self.land(cloud)

        receipt = json.loads(
            (self.operation_root / "land-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            result["mergeResultCommit"],
            git(
                "show",
                "-s",
                "--format=%P",
                result["receiptCommit"],
                git_dir=self.ledger,
            ).strip(),
        )
        self.assertEqual(
            ["land-receipt.json"],
            git(
                "ls-tree",
                "--name-only",
                result["receiptCommit"],
                git_dir=self.ledger,
            ).splitlines(),
        )
        document = {
            key: value
            for key, value in receipt.items()
            if key
            not in {"receiptBlob", "receiptCommit", "receiptSha256", "receiptTree"}
        }
        canonical = (
            json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"
        )
        self.assertEqual(
            canonical,
            git(
                "show",
                f"{result['receiptCommit']}:land-receipt.json",
                git_dir=self.ledger,
            ),
        )
        self.assertEqual(
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            receipt["receiptSha256"],
        )

    def test_completed_land_stays_idempotent_after_new_local_edits(self) -> None:
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: landed before later edits.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        first = self.land(cloud)
        (self.workspace / "AFTER_LAND.md").write_text(
            "New local work must not invalidate the receipt.\n", encoding="utf-8"
        )

        second = self.land(cloud)

        self.assertEqual(first, second)
        self.assertEqual(
            "New local work must not invalidate the receipt.\n",
            (self.workspace / "AFTER_LAND.md").read_text(encoding="utf-8"),
        )

    def test_clean_land_retains_returning_local_refs_and_reflog_history(self) -> None:
        original_head = git("rev-parse", "HEAD", cwd=self.workspace).strip()
        original_tree = git("rev-parse", "HEAD^{tree}", cwd=self.workspace).strip()
        local_head = git(
            "commit-tree",
            original_tree,
            "-p",
            original_head,
            cwd=self.workspace,
        ).strip()
        git(
            "update-ref",
            "refs/heads/main",
            local_head,
            original_head,
            cwd=self.workspace,
        )
        git("branch", "saved-local-state", local_head, cwd=self.workspace)
        reflog_only = git(
            "commit-tree",
            original_tree,
            "-p",
            local_head,
            cwd=self.workspace,
        ).strip()
        git(
            "update-ref",
            "refs/heads/main",
            reflog_only,
            local_head,
            cwd=self.workspace,
        )
        git(
            "update-ref",
            "refs/heads/main",
            local_head,
            reflog_only,
            cwd=self.workspace,
        )
        before = git_admin_snapshot(self.workspace)
        cloud = self.checkpoint_cloud()

        result = self.land(cloud)

        self.assertEqual("APPLIED", result["outcome"])
        self.assertEqual(before, git_admin_snapshot(self.workspace))
        history_prefix = (
            f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/"
            "git-history/local-return"
        )
        self.assertEqual(
            local_head,
            git("rev-parse", f"{history_prefix}/head", git_dir=self.ledger).strip(),
        )
        self.assertEqual(
            local_head,
            git(
                "rev-parse",
                f"{history_prefix}/refs/heads/saved-local-state",
                git_dir=self.ledger,
            ).strip(),
        )
        self.assertEqual(
            reflog_only,
            git(
                "rev-parse",
                f"{history_prefix}/reflog/{reflog_only}",
                git_dir=self.ledger,
            ).strip(),
        )
        self.assertEqual(
            [self.baseline.commit, local_head],
            git(
                "show",
                "-s",
                "--format=%P",
                result["localReturnCommit"],
                git_dir=self.ledger,
            ).split(),
        )
        git("cat-file", "-e", f"{reflog_only}^{{commit}}", git_dir=self.ledger)
        self.assertEqual(local_head, result["localGitHistory"]["head"])
        self.assertIn(
            {
                "source": "reflog",
                "ref": f"{history_prefix}/reflog/{reflog_only}",
                "objectId": reflog_only,
            },
            result["localGitHistory"]["historyRefs"],
        )
        receipt = json.loads(
            (self.operation_root / "land-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result["localGitHistory"], receipt["localGitHistory"])

        git(
            "update-ref",
            "-d",
            f"{history_prefix}/reflog/{reflog_only}",
            reflog_only,
            git_dir=self.ledger,
        )
        with self.assertRaisesRegex(LandError, "Git history record differs"):
            self.land(cloud)

    def test_missing_local_receipt_record_recovers_from_deterministic_git_ref(
        self,
    ) -> None:
        (self.cloud / "REMOTE_TEST.md").write_text(
            "Status: recover the receipt record.\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        first = self.land(cloud)
        (self.operation_root / "result.json").unlink()
        (self.operation_root / "land-receipt.json").unlink()

        recovered = self.land(cloud)

        self.assertEqual(first, recovered)
        self.assertTrue((self.operation_root / "land-receipt.json").is_file())
        self.assertEqual(
            first["receiptCommit"],
            git(
                "rev-parse",
                first["receiptRef"],
                git_dir=self.ledger,
            ).strip(),
        )

    def test_operation_root_symlink_is_rejected_without_touching_referent(self) -> None:
        (self.cloud / "CLOUD_ONLY.md").write_text("cloud\n", encoding="utf-8")
        cloud = self.checkpoint_cloud()
        referent = self.root / "operation-referent"
        referent.mkdir(mode=0o700)
        self.operation_root.symlink_to(referent, target_is_directory=True)

        with self.assertRaisesRegex(LandError, "physical directory"):
            self.land(cloud)

        self.assertEqual([], list(referent.iterdir()))
        self.assertFalse((self.workspace / "CLOUD_ONLY.md").exists())

    def test_file_to_symlink_change_needs_review_without_touching_local(self) -> None:
        original = filesystem_snapshot(self.workspace)
        (self.cloud / "REMOTE_TEST.md").unlink()
        (self.cloud / "REMOTE_TEST.md").symlink_to("README.md")
        cloud = self.checkpoint_cloud()

        result = self.land(cloud)

        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertIn("type-change", {item["reason"] for item in result["conflicts"]})
        self.assertEqual(original, filesystem_snapshot(self.workspace))

    def test_file_directory_topology_change_needs_review(self) -> None:
        original = filesystem_snapshot(self.workspace)
        git("rm", "REMOTE_TEST.md", cwd=self.cloud)
        (self.cloud / "REMOTE_TEST.md").mkdir()
        (self.cloud / "REMOTE_TEST.md" / "nested.md").write_text(
            "nested\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()

        result = self.land(cloud)

        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertIn(
            "file-directory-topology",
            {item["reason"] for item in result["conflicts"]},
        )
        self.assertEqual(original, filesystem_snapshot(self.workspace))

    def test_case_colliding_directory_prefixes_need_review(self) -> None:
        (self.workspace / "lower").mkdir()
        (self.workspace / "lower" / "local.md").write_text(
            "local\n", encoding="utf-8"
        )
        (self.cloud / "LOWER").mkdir()
        (self.cloud / "LOWER" / "cloud.md").write_text(
            "cloud\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original = filesystem_snapshot(self.workspace)

        result = self.land(cloud)

        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertIn(
            "case-unicode-collision",
            {item["reason"] for item in result["conflicts"]},
        )
        self.assertEqual(original, filesystem_snapshot(self.workspace))

    def test_git_targeting_symlink_is_rejected_before_local_capture(self) -> None:
        (self.cloud / "ADMIN_LINK").symlink_to(".git/config")
        cloud = self.checkpoint_cloud()
        original = filesystem_snapshot(self.workspace)

        with self.assertRaisesRegex(LandError, "Git administration"):
            self.land(cloud)

        self.assertEqual(original, filesystem_snapshot(self.workspace))

    def test_land_rejects_a_forged_final_commit_containing_the_exclusion(self) -> None:
        (self.cloud / ".gitignore").write_text("approved-state/\n", encoding="utf-8")
        (self.cloud / "excluded.env").write_text(
            "SECRET=FORGED_FINAL_CHECKPOINT\n", encoding="utf-8"
        )
        git("add", ".gitignore", cwd=self.cloud)
        git("add", "-f", "excluded.env", cwd=self.cloud)
        git(
            "-c",
            "user.name=Cloud User",
            "-c",
            "user.email=cloud@example.invalid",
            "commit",
            "-m",
            "Forge an invalid final checkpoint",
            cwd=self.cloud,
        )
        forged_commit = git("rev-parse", "HEAD", cwd=self.cloud).strip()
        git("fetch", str(self.cloud), "HEAD", git_dir=self.ledger)
        forged_ref = (
            f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/"
            "checkpoints/0001-land-final"
        )
        git("update-ref", forged_ref, forged_commit, git_dir=self.ledger)
        original = filesystem_snapshot(self.workspace)

        with self.assertRaisesRegex(LandError, "hard-excluded"):
            self.land({"ref": forged_ref, "commit": forged_commit})

        self.assertEqual(original, filesystem_snapshot(self.workspace))

    def test_no_clobber_add_preserves_a_racing_user_file(self) -> None:
        (self.cloud / "RACE.md").write_text("cloud\n", encoding="utf-8")
        cloud = self.checkpoint_cloud()
        original_install = land_module._install_after
        injected = False

        def race_install(**kwargs: object) -> None:
            nonlocal injected
            if not injected and kwargs["name"] == "RACE.md":
                injected = True
                descriptor = os.open(
                    str(kwargs["name"]),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=int(kwargs["parent_descriptor"]),
                )
                try:
                    os.write(descriptor, b"user work\n")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            original_install(**kwargs)  # type: ignore[arg-type]

        with mock.patch.object(land_module, "_install_after", race_install):
            with self.assertRaises(LandError):
                self.land(cloud)

        self.assertEqual(
            "user work\n", (self.workspace / "RACE.md").read_text(encoding="utf-8")
        )

    def test_replacement_race_during_preservation_restores_user_bytes(self) -> None:
        (self.cloud / "AAA_CLOUD.md").write_text("cloud addition\n", encoding="utf-8")
        (self.cloud / "REMOTE_TEST.md").write_text(
            "cloud replacement\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original_preserve = land_module._preserve_original
        raced = False

        def race_preserve(**kwargs: object) -> None:
            nonlocal raced
            if not raced and kwargs["name"] == "REMOTE_TEST.md":
                raced = True
                descriptor = os.open(
                    str(kwargs["name"]),
                    os.O_WRONLY | os.O_TRUNC,
                    dir_fd=int(kwargs["parent_descriptor"]),
                )
                try:
                    os.write(descriptor, b"concurrent local work\n")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            original_preserve(**kwargs)  # type: ignore[arg-type]

        with mock.patch.object(land_module, "_preserve_original", race_preserve):
            with self.assertRaisesRegex(LandError, "local path changed during Land"):
                self.land(cloud)

        self.assertTrue(raced)
        self.assertEqual(
            b"concurrent local work\n",
            (self.workspace / "REMOTE_TEST.md").read_bytes(),
        )
        self.assertFalse((self.workspace / "AAA_CLOUD.md").exists())
        self.assertFalse((self.operation_root / "land-receipt.json").exists())
        journal = json.loads(
            (self.operation_root / "apply-journal.json").read_text(encoding="utf-8")
        )
        self.assertEqual("ROLLED_BACK", journal["phase"])

    def test_final_cutover_revalidation_restores_late_user_bytes(self) -> None:
        (self.cloud / "AAA_CLOUD.md").write_text("cloud addition\n", encoding="utf-8")
        (self.cloud / "REMOTE_TEST.md").write_text(
            "cloud replacement\n", encoding="utf-8"
        )
        cloud = self.checkpoint_cloud()
        original_validate = land_module._validate_preserved_originals
        raced = False

        def race_validation(journal: dict) -> None:
            nonlocal raced
            operation = next(
                item
                for item in journal["operations"]
                if item["path"] == "REMOTE_TEST.md"
            )
            Path(operation["movedPath"]).write_bytes(b"late local descriptor write\n")
            raced = True
            original_validate(journal)

        with mock.patch.object(
            land_module, "_validate_preserved_originals", race_validation
        ):
            with self.assertRaisesRegex(LandError, "local path changed during Land"):
                self.land(cloud)

        self.assertTrue(raced)
        self.assertEqual(
            b"late local descriptor write\n",
            (self.workspace / "REMOTE_TEST.md").read_bytes(),
        )
        self.assertFalse((self.workspace / "AAA_CLOUD.md").exists())
        self.assertFalse((self.operation_root / "land-receipt.json").exists())
        journal = json.loads(
            (self.operation_root / "apply-journal.json").read_text(encoding="utf-8")
        )
        self.assertEqual("ROLLED_BACK", journal["phase"])


if __name__ == "__main__":
    unittest.main()
