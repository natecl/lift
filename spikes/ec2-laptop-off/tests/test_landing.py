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


GUEST_ROOT = Path(__file__).resolve().parents[1] / "guest"
sys.path.insert(0, str(GUEST_ROOT))

import landing  # noqa: E402


class LandingLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-landing-test-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace_root = self.root / "workspaces"
        self.workspace_root.mkdir(mode=0o700)
        self.workspace_id = "lift-ec2-spike"
        self.workspace = self.workspace_root / self.workspace_id
        self.workspace.mkdir(mode=0o700)
        self.ledger_root = self.root / "ledger"
        self.ledger_root.mkdir(mode=0o700)
        self.run_id = "p0-test-run"
        self.ledger = self.ledger_root / f"{self.run_id}.git"
        self.ledger.mkdir(mode=0o700)
        self.reconstruction_root = self.root / "reconstruction"
        self.reconstruction_root.mkdir(mode=0o700)
        self.baseline_commit = "a" * 40
        self.baseline_ref = (
            f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/baseline"
        )
        reconstruction = {
            "schemaVersion": 1,
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
            "workspacePath": str(self.workspace),
            "ledgerPath": str(self.ledger),
            "baselineRef": self.baseline_ref,
            "baselineCommit": self.baseline_commit,
        }
        reconstruction_path = self.reconstruction_root / f"{self.workspace_id}.json"
        reconstruction_path.write_text(json.dumps(reconstruction), encoding="utf-8")
        os.chmod(reconstruction_path, 0o600)
        self.volume_id = "vol-0123456789abcdef0"
        self.patches = (
            mock.patch.object(landing, "WORKSPACE_ROOT", self.workspace_root),
            mock.patch.object(landing, "LEDGER_ROOT", self.ledger_root),
            mock.patch.object(
                landing,
                "RECONSTRUCTION_STATE_ROOT",
                self.reconstruction_root,
            ),
            mock.patch.object(
                landing,
                "_storage_identity",
                return_value=("8:1", self.volume_id),
            ),
            mock.patch.object(
                landing,
                "_workspace_writer_uid",
                return_value=1001,
            ),
        )
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temporary.cleanup()

    def state_path(self) -> Path:
        return self.ledger_root / "landing" / f"{self.workspace_id}.json"

    def user_manager_fence(self, uid: int = 1001) -> dict:
        return {
            "uid": uid,
            "user": "lift",
            "unit": f"user@{uid}.service",
            "unitMasked": True,
            "lingerDisabled": True,
        }

    def freeze(self, **overrides: object) -> dict:
        options = {
            "workspace": self.workspace,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "expected_volume_id": self.volume_id,
            "stop_runner": lambda: {"state": "inactive", "changed": True},
            "stopped_probe": lambda: None,
            "writer_probe": lambda _: 1001,
            "user_manager_probe": lambda uid: self.user_manager_fence(uid),
        }
        options.update(overrides)
        return landing.freeze_landing(**options)

    def checkpoint(self) -> dict:
        commit = "1" * 40
        tree = "2" * 40
        bundle_sha = "3" * 64
        manifest_sha = "4" * 64
        return {
            "schemaVersion": 1,
            "ordinal": 4,
            "label": "land-final",
            "ref": (
                f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/"
                "checkpoints/0004-land-final"
            ),
            "commit": commit,
            "tree": tree,
            "parents": [self.baseline_commit],
            "bundleSha256": bundle_sha,
            "manifestSha256": "6" * 64,
            "manifestFileSha256": manifest_sha,
            "s3Bucket": "lift-test-bucket",
            "s3ObjectKey": (
                f"sessions/{self.run_id}/checkpoints/{bundle_sha}.bundle"
            ),
            "s3VersionId": "bundle-version-1",
            "s3ManifestObjectKey": (
                f"sessions/{self.run_id}/checkpoints/"
                f"{manifest_sha}.manifest.json"
            ),
            "s3ManifestVersionId": "manifest-version-1",
            "restoreTest": {
                "bundleLocalSha256": bundle_sha,
                "manifestLocalSha256": manifest_sha,
                "restoredCommit": commit,
                "restoredTree": tree,
                "restoredFileCount": 7,
                "verifiedAt": "2026-09-02T12:00:00+00:00",
            },
        }

    def acknowledgement(self, checkpoint: dict) -> dict:
        merge_commit = "7" * 40
        local_manifest = {
            "schemaVersion": 1,
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
            "mergeResultRef": (
                f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/merge-result"
            ),
            "mergeResultCommit": merge_commit,
            "mergeResultTree": "8" * 40,
            "entries": [],
        }
        local_manifest["manifestSha256"] = hashlib.sha256(
            json.dumps(
                local_manifest, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        payload = {
            "schemaVersion": 1,
            "kind": "lift-land-acknowledgement",
            "operationId": f"{self.run_id}-land",
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
            "baseline": {
                "ref": (
                    f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/baseline"
                ),
                "commit": self.baseline_commit,
            },
            "cloudFinal": {
                "checkpointRef": checkpoint["ref"],
                "landRef": (
                    f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/cloud-final"
                ),
                "commit": checkpoint["commit"],
                "tree": checkpoint["tree"],
                "parents": checkpoint["parents"],
            },
            "recoveryObjects": {
                "bundle": {
                    "sha256": checkpoint["bundleSha256"],
                    "s3ObjectKey": checkpoint["s3ObjectKey"],
                    "s3VersionId": checkpoint["s3VersionId"],
                },
                "manifest": {
                    "sha256": checkpoint["manifestSha256"],
                    "fileSha256": checkpoint["manifestFileSha256"],
                    "s3ObjectKey": checkpoint["s3ManifestObjectKey"],
                    "s3VersionId": checkpoint["s3ManifestVersionId"],
                },
            },
            "localLand": {
                "resultSha256": "9" * 64,
                "outcome": "APPLIED",
                "localReturnRef": (
                    f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/local-return"
                ),
                "localReturnCommit": "a" * 40,
                "mergeResultRef": local_manifest["mergeResultRef"],
                "mergeResultCommit": merge_commit,
                "verifiedAt": "2026-09-02T12:05:00+00:00",
                "receiptRef": (
                    f"refs/lift/{self.workspace_id}/sessions/{self.run_id}/land-receipt"
                ),
                "receiptCommit": "5" * 40,
                "receiptSha256": "b" * 64,
            },
            "finalLocalManifest": local_manifest,
            "finalLocalManifestSha256": local_manifest["manifestSha256"],
        }
        payload["acknowledgementSha256"] = hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()
        return payload

    def record_checkpoint(self, checkpoint: dict | None = None) -> dict:
        return landing.record_final_checkpoint(
            workspace=self.workspace,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            expected_volume_id=self.volume_id,
            checkpoint=checkpoint or self.checkpoint(),
            stopped_probe=lambda: None,
            writer_probe=lambda _: 1001,
            user_manager_probe=lambda uid: self.user_manager_fence(uid),
        )

    def acknowledge(self, acknowledgement: dict) -> dict:
        return landing.acknowledge_landing(
            workspace=self.workspace,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            expected_volume_id=self.volume_id,
            acknowledgement=acknowledgement,
            stopped_probe=lambda: None,
            writer_probe=lambda _: 1001,
            user_manager_probe=lambda uid: self.user_manager_fence(uid),
        )

    def test_legacy_cloud_primary_state_is_migrated_to_ebs(self) -> None:
        self.assertFalse(self.state_path().exists())

        with landing.lifecycle_lock(self.workspace):
            state = landing.require_cloud_primary(self.workspace)

        self.assertEqual(landing.PHASE_CLOUD_PRIMARY, state["phase"])
        self.assertEqual("CLOUD_PRIMARY", state["lease"])
        self.assertEqual(self.volume_id, state["workspaceVolumeId"])
        self.assertTrue(self.state_path().is_file())
        self.assertEqual(0o600, self.state_path().stat().st_mode & 0o777)
        self.assertEqual(
            0o700,
            (self.ledger_root / "landing").stat().st_mode & 0o777,
        )

    def test_missing_state_fails_when_legacy_migration_is_disabled(self) -> None:
        with landing.lifecycle_lock(self.workspace):
            with self.assertRaisesRegex(
                landing.LandingError, "no durable ownership record"
            ):
                landing.require_cloud_primary(
                    self.workspace, allow_legacy_missing=False
                )

    def test_pid_scan_uses_status_uids_even_when_proc_directory_owner_differs(
        self,
    ) -> None:
        proc_root = self.root / "proc"
        proc_root.mkdir()
        target = proc_root / "4242"
        target.mkdir()
        target_uid = 65432
        (target / "status").write_bytes(
            b"Name:\tnondumpable-writer\n"
            b"State:\tS (sleeping)\n"
            + f"Uid:\t{target_uid}\t{target_uid}\t{target_uid}\t{target_uid}\n".encode(
                "ascii"
            )
        )
        other = proc_root / "4243"
        other.mkdir()
        (other / "status").write_bytes(
            b"Name:\tother\nState:\tS (sleeping)\nUid:\t0\t0\t0\t0\n"
        )

        self.assertNotEqual(target_uid, target.stat().st_uid)
        self.assertEqual([4242], landing._pids_for_uid(target_uid, proc_root))

    def test_user_manager_fence_disables_linger_masks_and_verifies_unit(self) -> None:
        commands: list[tuple[list[str], bool]] = []

        def run(command: list[str], *, check: bool = True):
            commands.append((command, check))
            if command[:2] == ["systemctl", "is-active"]:
                return subprocess.CompletedProcess(command, 3, "inactive\n", "")
            if command[:2] == ["systemctl", "is-enabled"]:
                return subprocess.CompletedProcess(command, 1, "masked\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        linger_root = self.root / "linger"
        linger_root.mkdir()
        identity = mock.Mock(pw_name="lift")
        with (
            mock.patch.object(landing, "LINGER_ROOT", linger_root),
            mock.patch.object(landing.pwd, "getpwuid", return_value=identity),
            mock.patch.object(landing, "_run", side_effect=run),
        ):
            evidence = landing._fence_user_manager(1001)

        self.assertEqual(self.user_manager_fence(), evidence)
        self.assertEqual(
            [
                (["loginctl", "disable-linger", "lift"], True),
                (["systemctl", "mask", "--now", "user@1001.service"], True),
                (["systemctl", "is-active", "user@1001.service"], False),
                (["systemctl", "is-enabled", "user@1001.service"], False),
            ],
            commands,
        )

    def test_freeze_fences_user_manager_before_and_after_writer_quiesce(self) -> None:
        events: list[str] = []

        def stopped() -> None:
            events.append("runner-stopped")

        def identify(_: Path) -> int:
            events.append("writer-identified")
            return 1001

        def fence(uid: int) -> dict:
            self.assertEqual(1001, uid)
            events.append("user-manager-fenced")
            return self.user_manager_fence(uid)

        def quiesce(_: Path) -> int:
            events.append("writer-quiesced")
            return 1001

        with mock.patch.object(
            landing,
            "_workspace_writer_uid",
            side_effect=identify,
        ):
            result = landing._assert_frozen(
                self.workspace,
                stopped_probe=stopped,
                writer_probe=quiesce,
                user_manager_probe=fence,
            )

        self.assertEqual((1001, self.user_manager_fence()), result)
        self.assertEqual(
            [
                "runner-stopped",
                "writer-identified",
                "user-manager-fenced",
                "writer-quiesced",
                "user-manager-fenced",
            ],
            events,
        )

    def test_freeze_writes_intent_before_stopping_runner(self) -> None:
        observed_phase: list[str] = []

        def fail_after_observing_intent() -> dict:
            raw = json.loads(self.state_path().read_text(encoding="utf-8"))
            observed_phase.append(raw["phase"])
            raise landing.LandingError("injected stop failure")

        with self.assertRaisesRegex(landing.LandingError, "injected stop failure"):
            self.freeze(stop_runner=fail_after_observing_intent)

        self.assertEqual([landing.PHASE_FREEZE_REQUESTED], observed_phase)
        state = landing.status_landing(workspace=self.workspace)
        self.assertEqual(landing.PHASE_FREEZE_REQUESTED, state["phase"])
        self.assertEqual("LANDING", state["lease"])
        with landing.lifecycle_lock(self.workspace):
            with self.assertRaisesRegex(
                landing.LandingError, "does not permit a cloud workload start"
            ):
                landing.require_cloud_primary(self.workspace)

    def test_retry_after_stop_failure_finishes_the_same_freeze(self) -> None:
        with self.assertRaises(landing.LandingError):
            self.freeze(
                stop_runner=lambda: (_ for _ in ()).throw(
                    landing.LandingError("stop failed")
                )
            )

        result = self.freeze()

        self.assertTrue(result["changed"])
        self.assertEqual(landing.PHASE_CLOUD_FROZEN, result["phase"])
        self.assertEqual("inactive", result["freeze"]["runnerState"])
        self.assertEqual(1001, result["freeze"]["workspaceWriterUid"])
        self.assertEqual(
            self.user_manager_fence(), result["freeze"]["userManagerFence"]
        )

    def test_completed_freeze_retry_only_revalidates(self) -> None:
        first = self.freeze()
        stop = mock.Mock(side_effect=AssertionError("runner stop must not repeat"))
        stopped = mock.Mock()
        writers = mock.Mock(return_value=1001)
        user_manager = mock.Mock(return_value=self.user_manager_fence())

        second = self.freeze(
            stop_runner=stop,
            stopped_probe=stopped,
            writer_probe=writers,
            user_manager_probe=user_manager,
        )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        stop.assert_not_called()
        stopped.assert_called_once_with()
        writers.assert_called_once_with(self.workspace)
        self.assertEqual(
            [mock.call(1001), mock.call(1001)],
            user_manager.call_args_list,
        )

    def test_status_revalidates_a_recorded_checkpoint_with_read_only_probes(
        self,
    ) -> None:
        self.freeze()
        self.record_checkpoint()
        before = self.state_path().read_bytes()
        stopped = mock.Mock()
        writers = mock.Mock(return_value=1001)
        user_manager = mock.Mock(return_value=self.user_manager_fence())

        result = landing.status_landing(
            workspace=self.workspace,
            stopped_probe=stopped,
            writer_probe=writers,
            user_manager_probe=user_manager,
        )

        self.assertEqual(
            landing.PHASE_FINAL_CHECKPOINT_RECORDED, result["phase"]
        )
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.state_path().read_bytes())
        stopped.assert_called_once_with()
        writers.assert_called_once_with(self.workspace)
        self.assertEqual(
            [mock.call(1001), mock.call(1001)],
            user_manager.call_args_list,
        )

    def test_retry_rejects_fence_that_differs_from_durable_evidence(self) -> None:
        self.freeze()
        changed_fence = self.user_manager_fence()
        changed_fence["lingerDisabled"] = False

        with self.assertRaisesRegex(
            landing.LandingError,
            "live cloud freeze differs from its durable evidence",
        ):
            self.freeze(user_manager_probe=lambda _: changed_fence)

    def test_persisted_freeze_rejects_tampered_user_manager_fence(self) -> None:
        self.freeze()
        state = json.loads(self.state_path().read_text(encoding="utf-8"))
        state["freeze"]["userManagerFence"]["unit"] = "user@0.service"
        self.state_path().write_text(json.dumps(state), encoding="utf-8")
        os.chmod(self.state_path(), 0o600)

        with self.assertRaisesRegex(
            landing.LandingError,
            "landing user-manager fence is invalid",
        ):
            landing.status_landing(workspace=self.workspace)

    def test_freeze_rejects_a_different_expected_volume(self) -> None:
        with self.assertRaisesRegex(
            landing.LandingError, "does not match durable workspace identity"
        ):
            self.freeze(expected_volume_id="vol-fedcba98765432100")

    def test_checkpoint_requires_completed_freeze(self) -> None:
        with landing.lifecycle_lock(self.workspace):
            landing.require_cloud_primary(self.workspace)

        with self.assertRaisesRegex(landing.LandingError, "before cloud freeze"):
            self.record_checkpoint()

    def test_checkpoint_and_acknowledgement_are_monotonic_and_idempotent(self) -> None:
        self.freeze()
        checkpoint = self.checkpoint()

        recorded = self.record_checkpoint(checkpoint)
        recorded_again = self.record_checkpoint(checkpoint)
        acknowledged = self.acknowledge(self.acknowledgement(checkpoint))
        acknowledged_again = self.acknowledge(self.acknowledgement(checkpoint))

        self.assertTrue(recorded["changed"])
        self.assertFalse(recorded_again["changed"])
        self.assertEqual(
            landing.PHASE_FINAL_CHECKPOINT_RECORDED, recorded["phase"]
        )
        self.assertTrue(acknowledged["changed"])
        self.assertFalse(acknowledged_again["changed"])
        self.assertEqual(landing.PHASE_ACKNOWLEDGED, acknowledged["phase"])
        self.assertEqual("LOCAL_PRIMARY", acknowledged["lease"])
        self.assertRegex(
            acknowledged["acknowledgement"]["acknowledgementSha256"],
            r"^[0-9a-f]{64}$",
        )
        with landing.lifecycle_lock(self.workspace):
            with self.assertRaisesRegex(
                landing.LandingError, "does not permit a cloud workload start"
            ):
                landing.require_cloud_primary(self.workspace)

    def test_checkpoint_retry_rejects_different_immutable_record(self) -> None:
        self.freeze()
        checkpoint = self.checkpoint()
        self.record_checkpoint(checkpoint)
        changed = json.loads(json.dumps(checkpoint))
        changed["tree"] = "6" * 40
        changed["restoreTest"]["restoredTree"] = "6" * 40

        with self.assertRaisesRegex(
            landing.LandingError, "immutable final checkpoint already differs"
        ):
            self.record_checkpoint(changed)

    def test_checkpoint_must_be_restore_verified_and_canonical(self) -> None:
        self.freeze()
        checkpoint = self.checkpoint()
        checkpoint["restoreTest"]["bundleLocalSha256"] = "9" * 64
        with self.assertRaisesRegex(
            landing.LandingError, "restore evidence is invalid"
        ):
            self.record_checkpoint(checkpoint)

        checkpoint = self.checkpoint()
        checkpoint["s3ObjectKey"] = "other/object.bundle"
        with self.assertRaisesRegex(
            landing.LandingError, "object keys are not canonical"
        ):
            self.record_checkpoint(checkpoint)

    def test_acknowledgement_requires_exact_final_checkpoint_and_receipt(self) -> None:
        self.freeze()
        checkpoint = self.checkpoint()
        self.record_checkpoint(checkpoint)
        acknowledgement = self.acknowledgement(checkpoint)
        acknowledgement["cloudFinal"]["commit"] = "c" * 40
        unsigned = {
            key: value
            for key, value in acknowledgement.items()
            if key != "acknowledgementSha256"
        }
        acknowledgement["acknowledgementSha256"] = hashlib.sha256(
            json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()

        with self.assertRaisesRegex(
            landing.LandingError, "not bound to this Land operation"
        ):
            self.acknowledge(acknowledgement)

    def test_acknowledgement_cannot_precede_checkpoint(self) -> None:
        self.freeze()
        checkpoint = self.checkpoint()
        with self.assertRaisesRegex(
            landing.LandingError, "requires a final checkpoint"
        ):
            self.acknowledge(self.acknowledgement(checkpoint))

    def test_tampered_state_and_symlink_marker_fail_closed(self) -> None:
        self.freeze()
        state = json.loads(self.state_path().read_text(encoding="utf-8"))
        state["lease"] = "CLOUD_PRIMARY"
        self.state_path().write_text(json.dumps(state), encoding="utf-8")
        os.chmod(self.state_path(), 0o600)
        with self.assertRaisesRegex(
            landing.LandingError, "invalid lifecycle metadata"
        ):
            landing.status_landing(workspace=self.workspace)

        self.state_path().unlink()
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        os.chmod(outside, 0o600)
        self.state_path().symlink_to(outside)
        with self.assertRaisesRegex(landing.LandingError, "cannot read landing state"):
            landing.status_landing(workspace=self.workspace)

    def test_legacy_migration_tightens_compatible_private_directories(self) -> None:
        os.chmod(self.reconstruction_root, 0o755)
        os.chmod(self.ledger, 0o755)

        with landing.lifecycle_lock(self.workspace):
            landing.require_cloud_primary(self.workspace)

        self.assertEqual(0o700, self.reconstruction_root.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.ledger.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
