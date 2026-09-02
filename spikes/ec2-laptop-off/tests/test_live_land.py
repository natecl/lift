from __future__ import annotations

import hashlib
import json
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

from checkpoint import create_checkpoint  # noqa: E402
from land import land_fixture  # noqa: E402
import live_land  # noqa: E402
from live_land import (  # noqa: E402
    LiveLandError,
    _retain_exact_file,
    build_land_acknowledgement,
    import_final_checkpoint,
)
from workspace import capture_baseline, content_manifest, create_fixture  # noqa: E402


def git(
    *arguments: str,
    cwd: Path | None = None,
    git_dir: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = ["git"]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


class LiveLandImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-live-land-test-")
        self.root = Path(self.temporary.name).resolve()
        self.run_id = "p0-test-run"
        self.workspace_id = "lift-ec2-spike"
        self.local = self.root / "local"
        self.marker = create_fixture(self.local)
        self.approved = (self.marker["approvedIgnoredPath"],)
        self.ledger = self.root / "local-ledger.git"
        self.baseline = capture_baseline(
            workspace=self.local,
            ledger=self.ledger,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            approved_ignored=self.approved,
        )

        self.cloud_ledger = self.root / "cloud-ledger.git"
        git("clone", "--mirror", str(self.ledger), str(self.cloud_ledger))
        self.cloud = self.root / "cloud"
        git("clone", "--no-checkout", str(self.cloud_ledger), str(self.cloud))
        git("checkout", "--detach", self.baseline.commit, cwd=self.cloud)
        git("config", "user.name", "Cloud User", cwd=self.cloud)
        git("config", "user.email", "cloud@example.invalid", cwd=self.cloud)
        (self.cloud / "CLOUD_RETURN.md").write_text(
            "This came back from the final cloud checkpoint.\n", encoding="utf-8"
        )

        self.cloud_state = self.root / "cloud-state.json"
        self.cloud_state.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": self.run_id,
                    "workspaceId": self.workspace_id,
                    "workspacePath": str(self.cloud),
                    "ledgerPath": str(self.cloud_ledger),
                    "baselineCommit": self.baseline.commit,
                    "baselineRef": self.baseline.ref,
                }
            ),
            encoding="utf-8",
        )
        raw = create_checkpoint(
            workspace=self.cloud,
            ledger=self.cloud_ledger,
            state_path=self.cloud_state,
            checkpoints_root=self.root / "cloud-checkpoints",
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            ordinal=1,
            label="land-final",
            required_path=None,
            required_sha256=None,
            required_size=None,
            require_durable_mount=False,
        )
        self.checkpoint = {
            **raw,
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
            "baselineRef": self.baseline.ref,
            "baselineCommit": self.baseline.commit,
            "s3Bucket": "lift-test-bucket",
            "s3ObjectKey": f"sessions/{self.run_id}/{raw['bundleSha256']}.bundle",
            "s3VersionId": "exact-bundle-version",
            "s3ManifestObjectKey": (
                f"sessions/{self.run_id}/{raw['manifestFileSha256']}.manifest.json"
            ),
            "s3ManifestVersionId": "exact-manifest-version",
        }
        self.bundle = Path(str(raw["bundlePath"]))
        self.manifest = Path(str(raw["manifestPath"]))
        self.quarantine = self.root / "quarantine"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def import_checkpoint(
        self,
        *,
        checkpoint: dict[str, object] | None = None,
        bundle: Path | None = None,
        manifest: Path | None = None,
    ) -> dict[str, object]:
        return import_final_checkpoint(
            ledger=self.ledger,
            quarantine_root=self.quarantine,
            bundle_path=self.bundle if bundle is None else bundle,
            manifest_path=self.manifest if manifest is None else manifest,
            checkpoint=self.checkpoint if checkpoint is None else checkpoint,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            baseline_ref=self.baseline.ref,
            baseline_commit=self.baseline.commit,
        )

    def test_retain_recovers_crash_after_hard_link_publication(self) -> None:
        retained = self.quarantine / "artifact.bundle"
        retained.parent.mkdir()
        temporary = retained.with_name(f".retain-{retained.name}")
        value = b"exact recovery artifact\n"
        real_fsync_directory = live_land._fsync_directory
        fsync_calls = 0

        def crash_after_publication(directory: Path) -> None:
            nonlocal fsync_calls
            fsync_calls += 1
            real_fsync_directory(directory)
            if fsync_calls == 2:
                raise RuntimeError("simulated process crash")

        with mock.patch.object(
            live_land,
            "_fsync_directory",
            side_effect=crash_after_publication,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated process crash"):
                _retain_exact_file(retained, value)

        self.assertEqual(value, retained.read_bytes())
        self.assertTrue(temporary.exists())
        self.assertEqual(retained.stat().st_ino, temporary.stat().st_ino)
        self.assertEqual(2, retained.stat().st_nlink)

        _retain_exact_file(retained, value)

        self.assertEqual(value, retained.read_bytes())
        self.assertFalse(temporary.exists())
        self.assertEqual(1, retained.stat().st_nlink)

    def test_retain_fsyncs_each_directory_transition(self) -> None:
        retained = self.quarantine / "artifact.manifest.json"
        retained.parent.mkdir()
        real_fsync_directory = live_land._fsync_directory

        with mock.patch.object(
            live_land,
            "_fsync_directory",
            wraps=real_fsync_directory,
        ) as fsync_directory:
            _retain_exact_file(retained, b"exact manifest\n")

        self.assertEqual(3, fsync_directory.call_count)

    def test_retain_resumes_an_exact_temp_only_state(self) -> None:
        retained = self.quarantine / "artifact.bundle"
        retained.parent.mkdir()
        temporary = retained.with_name(f".retain-{retained.name}")
        value = b"durable staged artifact\n"
        temporary.write_bytes(value)
        temporary.chmod(0o600)
        real_fsync_directory = live_land._fsync_directory

        with mock.patch.object(
            live_land,
            "_fsync_directory",
            wraps=real_fsync_directory,
        ) as fsync_directory:
            _retain_exact_file(retained, value)

        self.assertEqual(value, retained.read_bytes())
        self.assertFalse(temporary.exists())
        self.assertEqual(1, retained.stat().st_nlink)
        self.assertEqual(2, fsync_directory.call_count)

    def test_retain_never_replaces_a_differing_destination(self) -> None:
        retained = self.quarantine / "artifact.bundle"
        retained.parent.mkdir()
        retained.write_bytes(b"existing winner\n")
        temporary = retained.with_name(f".retain-{retained.name}")
        temporary.write_bytes(b"new contender\n")

        with self.assertRaisesRegex(LiveLandError, "already differs"):
            _retain_exact_file(retained, b"new contender\n")

        self.assertEqual(b"existing winner\n", retained.read_bytes())
        self.assertEqual(b"new contender\n", temporary.read_bytes())

    def test_exact_bundle_import_is_idempotent_and_never_moves_user_git(self) -> None:
        before = {
            "head": git("rev-parse", "HEAD", cwd=self.local).stdout,
            "branch": git("symbolic-ref", "HEAD", cwd=self.local).stdout,
            "refs": git(
                "for-each-ref", "--format=%(refname) %(objectname)", cwd=self.local
            ).stdout,
            "index": (self.local / ".git" / "index").read_bytes(),
            "status": git(
                "status", "--porcelain=v2", "--untracked-files=all", cwd=self.local
            ).stdout,
        }

        first = self.import_checkpoint()
        second = self.import_checkpoint()

        self.assertEqual(first, second)
        self.assertEqual(str(self.quarantine), first["quarantinePath"])
        self.assertEqual(self.checkpoint["commit"], first["checkpointCommit"])
        self.assertEqual(self.checkpoint["tree"], first["checkpointTree"])
        self.assertEqual(self.checkpoint["manifestSha256"], first["manifestSha256"])
        self.assertEqual(
            hashlib.sha256(canonical(first["importedRefs"])).hexdigest(),
            first["importedRefsSha256"],
        )
        self.assertNotIn(
            self.baseline.ref,
            {item["ref"] for item in first["importedRefs"]},
        )
        self.assertEqual(
            self.baseline.commit,
            git("rev-parse", self.baseline.ref, git_dir=self.ledger).stdout.strip(),
        )
        for item in first["importedRefs"]:
            self.assertEqual(
                item["objectId"],
                git("rev-parse", item["ref"], git_dir=self.ledger).stdout.strip(),
            )
        after = {
            "head": git("rev-parse", "HEAD", cwd=self.local).stdout,
            "branch": git("symbolic-ref", "HEAD", cwd=self.local).stdout,
            "refs": git(
                "for-each-ref", "--format=%(refname) %(objectname)", cwd=self.local
            ).stdout,
            "index": (self.local / ".git" / "index").read_bytes(),
            "status": git(
                "status", "--porcelain=v2", "--untracked-files=all", cwd=self.local
            ).stdout,
        }
        self.assertEqual(before, after)

    def test_bundle_with_one_extra_head_is_rejected_before_ref_publication(self) -> None:
        evil_ref = "refs/heads/not-allowlisted"
        git("update-ref", evil_ref, self.baseline.commit, git_dir=self.cloud_ledger)
        expected = [
            item["ref"]
            for key in ("recoveryCheckpointRefs", "recoveryHistoryRefs")
            for item in self.checkpoint[key]
        ]
        malicious = self.root / "extra-head.bundle"
        git(
            "bundle",
            "create",
            str(malicious),
            *expected,
            evil_ref,
            git_dir=self.cloud_ledger,
        )
        checkpoint = dict(self.checkpoint)
        checkpoint["bundleSha256"] = hashlib.sha256(malicious.read_bytes()).hexdigest()
        checkpoint["bundleSize"] = malicious.stat().st_size

        with self.assertRaisesRegex(LiveLandError, "non-exact head map"):
            self.import_checkpoint(checkpoint=checkpoint, bundle=malicious)

        self.assertNotEqual(
            0,
            git(
                "show-ref", "--verify", checkpoint["ref"], git_dir=self.ledger, check=False
            ).returncode,
        )

    def test_manifest_self_hash_and_exact_tree_entries_are_both_enforced(self) -> None:
        malformed = json.loads(self.manifest.read_text(encoding="utf-8"))
        malformed["entries"][0]["size"] += 1
        malformed_path = self.root / "bad-self-hash.json"
        malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
        malformed_checkpoint = dict(self.checkpoint)
        malformed_checkpoint["manifestFileSha256"] = hashlib.sha256(
            malformed_path.read_bytes()
        ).hexdigest()
        malformed_checkpoint["manifestSize"] = malformed_path.stat().st_size
        with self.assertRaisesRegex(LiveLandError, "failed its self-hash"):
            self.import_checkpoint(
                checkpoint=malformed_checkpoint, manifest=malformed_path
            )

        forged = json.loads(self.manifest.read_text(encoding="utf-8"))
        forged["entries"][0]["size"] += 1
        unsigned = {key: value for key, value in forged.items() if key != "manifestSha256"}
        forged["manifestSha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        forged_path = self.root / "forged-tree.json"
        forged_path.write_text(json.dumps(forged), encoding="utf-8")
        forged_checkpoint = dict(self.checkpoint)
        forged_checkpoint["manifestSha256"] = forged["manifestSha256"]
        forged_checkpoint["manifestFileSha256"] = hashlib.sha256(
            forged_path.read_bytes()
        ).hexdigest()
        forged_checkpoint["manifestSize"] = forged_path.stat().st_size
        with self.assertRaisesRegex(LiveLandError, "tree entries differ"):
            self.import_checkpoint(checkpoint=forged_checkpoint, manifest=forged_path)

    def test_fixture_policy_mismatch_and_existing_ref_conflict_fail_closed(self) -> None:
        wrong_policy = dict(self.checkpoint["fixturePolicy"])
        wrong_policy["excludedSentinelPath"] = "different-secret.env"
        wrong = {**self.checkpoint, "fixturePolicy": wrong_policy}
        with self.assertRaisesRegex(LiveLandError, "fixture policy differs"):
            self.import_checkpoint(checkpoint=wrong)

        git(
            "update-ref",
            self.checkpoint["ref"],
            self.baseline.commit,
            git_dir=self.ledger,
        )
        with self.assertRaisesRegex(LiveLandError, "already differs"):
            self.import_checkpoint()

    def test_hostile_ambient_git_config_and_hooks_are_ignored(self) -> None:
        hostile = self.root / "hostile"
        hostile.mkdir()
        hooks = hostile / "hooks"
        hooks.mkdir()
        hook_marker = hostile / "reference-transaction-ran"
        hook = hooks / "reference-transaction"
        hook.write_text(
            f"#!/bin/sh\nprintf ran > {hook_marker}\nexit 1\n", encoding="utf-8"
        )
        hook.chmod(0o755)
        global_config = hostile / "global-config"
        global_config.write_text(
            f"[core]\n\thooksPath = {hooks}\n", encoding="utf-8"
        )
        git("config", "core.hooksPath", str(hooks), git_dir=self.ledger)
        old_environment = {
            key: os.environ.get(key)
            for key in ("GIT_CONFIG_GLOBAL", "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE")
        }
        os.environ["GIT_CONFIG_GLOBAL"] = str(global_config)
        os.environ["GIT_OBJECT_DIRECTORY"] = str(hostile / "objects")
        os.environ["GIT_INDEX_FILE"] = str(hostile / "index")
        try:
            result = self.import_checkpoint()
        finally:
            for key, value in old_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(self.checkpoint["commit"], result["checkpointCommit"])
        self.assertFalse(hook_marker.exists())

    def test_acknowledgement_binds_exact_recovery_local_result_and_receipt(self) -> None:
        self.import_checkpoint()
        operation_root = self.root / "land-operation"
        result = land_fixture(
            workspace=self.local,
            ledger=self.ledger,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            baseline_ref=self.baseline.ref,
            baseline_commit=self.baseline.commit,
            cloud_ref=str(self.checkpoint["ref"]),
            cloud_commit=str(self.checkpoint["commit"]),
            approved_ignored=self.approved,
            operation_root=operation_root,
        )
        receipt = json.loads(
            (operation_root / "land-receipt.json").read_text(encoding="utf-8")
        )
        raw_local_manifest = content_manifest(self.local, self.approved)
        local_manifest = {
            key: value
            for key, value in raw_local_manifest.items()
            if key != "manifestSha256"
        }
        local_manifest.update(
            {
                "runId": self.run_id,
                "workspaceId": self.workspace_id,
                "mergeResultCommit": result["mergeResultCommit"],
            }
        )
        local_manifest["manifestSha256"] = hashlib.sha256(
            canonical(local_manifest)
        ).hexdigest()
        acknowledgement = build_land_acknowledgement(
            operation_id="land-op-001",
            checkpoint=self.checkpoint,
            land_result=result,
            receipt=receipt,
            final_local_manifest=local_manifest,
            final_local_manifest_sha256=str(local_manifest["manifestSha256"]),
        )
        repeated = build_land_acknowledgement(
            operation_id="land-op-001",
            checkpoint=self.checkpoint,
            land_result=result,
            receipt=receipt,
            final_local_manifest=local_manifest,
            final_local_manifest_sha256=str(local_manifest["manifestSha256"]),
        )

        self.assertEqual(acknowledgement, repeated)
        self.assertEqual(
            hashlib.sha256(
                canonical(
                    {
                        key: value
                        for key, value in acknowledgement.items()
                        if key != "acknowledgementSha256"
                    }
                )
            ).hexdigest(),
            acknowledgement["acknowledgementSha256"],
        )
        self.assertEqual(
            "exact-bundle-version",
            acknowledgement["recoveryObjects"]["bundle"]["s3VersionId"],
        )
        self.assertEqual(
            receipt["receiptSha256"],
            acknowledgement["localLand"]["receiptSha256"],
        )
        self.assertEqual(local_manifest, acknowledgement["finalLocalManifest"])

        bad_checkpoint = {**self.checkpoint, "s3VersionId": "null"}
        with self.assertRaisesRegex(LiveLandError, "S3 version"):
            build_land_acknowledgement(
                operation_id="land-op-001",
                checkpoint=bad_checkpoint,
                land_result=result,
                receipt=receipt,
                final_local_manifest=local_manifest,
                final_local_manifest_sha256=str(local_manifest["manifestSha256"]),
            )


if __name__ == "__main__":
    unittest.main()
