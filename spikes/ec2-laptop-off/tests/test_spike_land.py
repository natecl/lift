from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

import spike  # noqa: E402


class LandControllerTests(unittest.TestCase):
    RUN_ID = "p0-20260902120000-abcd"
    BASELINE_COMMIT = "1" * 40
    PRIOR_COMMIT = "2" * 40
    CLOUD_COMMIT = "3" * 40
    CLOUD_TREE = "4" * 40
    MERGE_COMMIT = "5" * 40
    RECEIPT_COMMIT = "6" * 40
    CLOUD_HEAD = "7" * 40
    BUNDLE_SHA = "a" * 64
    MANIFEST_SHA = "b" * 64
    MANIFEST_FILE_SHA = "c" * 64
    ACK_SHA = "d" * 64

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-controller-land-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.ledger = self.root / "ledger.git"
        self.land_root = self.root / "land"
        self.workspace.mkdir()
        self.ledger.mkdir()
        self.land_root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def operation_id(self) -> str:
        return f"{self.RUN_ID}-land"

    @property
    def baseline_ref(self) -> str:
        return (
            f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/baseline"
        )

    @property
    def prior_ref(self) -> str:
        return (
            f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/"
            "checkpoints/0001-laptop-off-proof"
        )

    @property
    def final_ref(self) -> str:
        return (
            f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/"
            "checkpoints/0002-land-final"
        )

    def outputs(self) -> dict[str, str]:
        return {
            "InstanceId": "i-0123456789abcdef0",
            "WorkspaceVolumeId": "vol-0123456789abcdef0",
            "TransferBucketName": "lift-controller-test-bucket",
            "WorkspacePath": spike.REMOTE_WORKSPACE,
        }

    def prior_checkpoint(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "ordinal": 1,
            "label": "laptop-off-proof",
            "ref": self.prior_ref,
            "commit": self.PRIOR_COMMIT,
        }

    def final_checkpoint(self) -> dict[str, object]:
        history_ref = (
            f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/"
            "git-history/0002/head"
        )
        return {
            "schemaVersion": 1,
            "ordinal": 2,
            "label": "land-final",
            "ref": self.final_ref,
            "commit": self.CLOUD_COMMIT,
            "tree": self.CLOUD_TREE,
            "parents": [self.PRIOR_COMMIT],
            "parentRef": self.prior_ref,
            "parentCommit": self.PRIOR_COMMIT,
            "cloudHead": self.PRIOR_COMMIT,
            "gitSnapshotSha256": "8" * 64,
            "fixturePolicy": {
                "approvedIgnoredPath": ".lift-approved/session.json"
            },
            "historyRefs": [
                {"ref": history_ref, "objectId": self.PRIOR_COMMIT}
            ],
            "recoveryHistoryRefs": [
                {"ref": history_ref, "objectId": self.PRIOR_COMMIT}
            ],
            "recoveryCheckpointRefs": [
                {"ref": self.baseline_ref, "objectId": self.BASELINE_COMMIT},
                {"ref": self.prior_ref, "objectId": self.PRIOR_COMMIT},
                {"ref": self.final_ref, "objectId": self.CLOUD_COMMIT},
            ],
            "bundleSha256": self.BUNDLE_SHA,
            "bundleSize": 1024,
            "bundlePath": (
                f"/var/lib/lift/ledger/checkpoints/{self.RUN_ID}/"
                f"{self.BUNDLE_SHA}.bundle"
            ),
            "manifestSha256": self.MANIFEST_SHA,
            "manifestFileSha256": self.MANIFEST_FILE_SHA,
            "manifestSize": 512,
            "manifestPath": (
                f"/var/lib/lift/ledger/checkpoints/{self.RUN_ID}/"
                "0002-land-final-manifest.json"
            ),
            "fileCount": 4,
            "workspaceVolumeId": "vol-0123456789abcdef0",
            "s3Bucket": "lift-controller-test-bucket",
            "s3ObjectKey": f"sessions/{self.RUN_ID}/checkpoints/final.bundle",
            "s3VersionId": "bundle-version-1",
            "s3ManifestObjectKey": (
                f"sessions/{self.RUN_ID}/checkpoints/final.manifest.json"
            ),
            "s3ManifestVersionId": "manifest-version-1",
            "restoreTest": {"restoredCommit": self.CLOUD_COMMIT},
        }

    def initial_state(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "revision": 20,
            "runId": self.RUN_ID,
            "workspaceId": spike.WORKSPACE_ID,
            "runtime": {"state": "RUNNING"},
            "workspace": {
                "lease": "CLOUD_PRIMARY",
                "cloudPath": spike.REMOTE_WORKSPACE,
                "localPath": str(self.workspace),
                "ledgerPath": str(self.ledger),
                "baselineRef": self.baseline_ref,
                "baselineCommit": self.BASELINE_COMMIT,
                "checkpoints": [self.prior_checkpoint()],
            },
            "connection": {"state": "READY_SAFE_TO_CLOSE"},
            "readiness": {"safeToClose": True},
        }

    def freeze_record(self) -> dict[str, object]:
        outputs = self.outputs()
        return {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "runId": self.RUN_ID,
            "workspaceId": spike.WORKSPACE_ID,
            "workspaceVolumeId": outputs["WorkspaceVolumeId"],
            "baselineCommit": self.BASELINE_COMMIT,
            "phase": "CLOUD_FROZEN",
            "lease": "LANDING",
            "freeze": {"workspaceWriterUid": 1000},
        }

    def imported_record(self) -> dict[str, object]:
        return {
            "checkpointCommit": self.CLOUD_COMMIT,
            "importedRefsSha256": "e" * 64,
        }

    def applied_result(self) -> dict[str, object]:
        return {
            "outcome": "APPLIED",
            "mergeResultRef": (
                f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/"
                "land/merge-result"
            ),
            "mergeResultCommit": self.MERGE_COMMIT,
            "receiptCommit": self.RECEIPT_COMMIT,
        }

    def acknowledgement(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "checkpointRef": self.final_ref,
            "checkpointCommit": self.CLOUD_COMMIT,
            "mergeResultCommit": self.MERGE_COMMIT,
            "receiptCommit": self.RECEIPT_COMMIT,
            "acknowledgementSha256": self.ACK_SHA,
        }

    @contextlib.contextmanager
    def controller_boundaries(
        self,
        *,
        state: dict[str, object],
        land_result: dict[str, object],
        acknowledged_on_freeze: bool = False,
        saved_ack: dict[str, object] | None = None,
    ):
        outputs = self.outputs()
        checkpoint = self.final_checkpoint()
        acknowledgement = self.acknowledgement()
        freeze = self.freeze_record()

        def guest_action(**kwargs: object) -> dict[str, object]:
            action = kwargs["action"]
            if action == "freeze":
                if acknowledged_on_freeze:
                    return {
                        **freeze,
                        "phase": "ACKNOWLEDGED",
                        "lease": "LOCAL_PRIMARY",
                        "acknowledgement": acknowledgement,
                    }
                return freeze
            if action == "status":
                return {
                    **freeze,
                    "baselineRef": self.baseline_ref,
                    "phase": "FINAL_CHECKPOINT_RECORDED",
                    "finalCheckpoint": spike.guest_checkpoint_receipt(checkpoint),
                    "changed": False,
                }
            if action == "record-checkpoint":
                return {
                    **freeze,
                    "phase": "FINAL_CHECKPOINT_RECORDED",
                    "finalCheckpoint": spike.guest_checkpoint_receipt(checkpoint),
                }
            if action == "acknowledge":
                return {
                    **freeze,
                    "phase": "ACKNOWLEDGED",
                    "lease": "LOCAL_PRIMARY",
                    "acknowledgement": acknowledgement,
                }
            self.fail(f"unexpected guest Land action: {action}")

        captured_states: list[dict[str, object]] = []

        def capture_state(value: dict[str, object]) -> None:
            captured_states.append(copy.deepcopy(value))

        def read_private(path: Path, **_: object) -> bytes:
            if path.name == "acknowledgement.json" and saved_ack is not None:
                return (json.dumps(saved_ack, sort_keys=True) + "\n").encode("utf-8")
            return b'{"schemaVersion":1,"outcome":"APPLIED"}\n'

        with contextlib.ExitStack() as stack:
            boundaries = {
                "load_state": stack.enter_context(
                    mock.patch.object(spike, "load_state", return_value=state)
                ),
                "land_controller_lock": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "land_controller_lock",
                        return_value=contextlib.nullcontext(),
                    )
                ),
                "assert_identity": stack.enter_context(
                    mock.patch.object(spike, "assert_identity")
                ),
                "validated_stack_context": stack.enter_context(
                    mock.patch.object(
                        spike, "validated_stack_context", return_value=outputs
                    )
                ),
                "prepare_local_land_paths": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "prepare_local_land_paths",
                        return_value=(self.workspace, self.ledger, self.land_root),
                    )
                ),
                "validate_existing_local_land_paths": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "validate_existing_local_land_paths",
                        return_value=(self.workspace, self.ledger, self.land_root),
                    )
                ),
                "ensure_instance_online": stack.enter_context(
                    mock.patch.object(spike, "ensure_instance_online")
                ),
                "install_runtime_bundle": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "install_runtime_bundle",
                        return_value={"runtimeBundleSha256": "f" * 64},
                    )
                ),
                "guest_landing_action": stack.enter_context(
                    mock.patch.object(
                        spike, "guest_landing_action", side_effect=guest_action
                    )
                ),
                "guest_land_checkpoint": stack.enter_context(
                    mock.patch.object(
                        spike, "guest_land_checkpoint", return_value=checkpoint
                    )
                ),
                "make_land_checkpoint_durable": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "make_land_checkpoint_durable",
                        return_value=checkpoint,
                    )
                ),
                "import_final_checkpoint": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "import_final_checkpoint",
                        return_value=self.imported_record(),
                    )
                ),
                "fixture_policy_for_commit": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "fixture_policy_for_commit",
                        return_value={
                            "approvedIgnoredPath": ".lift-approved/session.json"
                        },
                    )
                ),
                "land_fixture": stack.enter_context(
                    mock.patch.object(spike, "land_fixture", return_value=land_result)
                ),
                "validate_conflicted_land_fixture": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "validate_conflicted_land_fixture",
                        return_value=land_result,
                    )
                ),
                "private_file_exists": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "private_file_exists",
                        side_effect=lambda path, **_: (
                            saved_ack is not None
                            and path.name == "acknowledgement.json"
                        ),
                    )
                ),
                "read_private_file": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "read_private_file",
                        side_effect=read_private,
                    )
                ),
                "final_local_land_manifest": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "final_local_land_manifest",
                        return_value=(
                            {"schemaVersion": 1, "entries": []},
                            "9" * 64,
                        ),
                    )
                ),
                "build_land_acknowledgement": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "build_land_acknowledgement",
                        return_value=acknowledgement,
                    )
                ),
                "atomic_private_json": stack.enter_context(
                    mock.patch.object(spike, "atomic_private_json")
                ),
                "stop_compute_after_land": stack.enter_context(
                    mock.patch.object(
                        spike,
                        "stop_compute_after_land",
                        return_value={
                            "instanceId": outputs["InstanceId"],
                            "state": "stopped",
                        },
                    )
                ),
                "atomic_state": stack.enter_context(
                    mock.patch.object(spike, "atomic_state", side_effect=capture_state)
                ),
                "record_event": stack.enter_context(
                    mock.patch.object(spike, "record_event")
                ),
                "now_iso": stack.enter_context(
                    mock.patch.object(
                        spike, "now_iso", return_value="2026-09-02T16:00:00+00:00"
                    )
                ),
            }
            boundaries["captured_states"] = captured_states
            yield boundaries

    def test_land_controller_lock_spans_the_entire_command(self) -> None:
        calls: list[str] = []

        @contextlib.contextmanager
        def lock():
            calls.append("lock-entered")
            yield
            calls.append("lock-exited")

        def command(_: object) -> None:
            calls.append("command")

        with mock.patch.object(spike, "land_controller_lock", side_effect=lock), mock.patch.object(
            spike, "_cmd_land_locked", side_effect=command
        ):
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        self.assertEqual(["lock-entered", "command", "lock-exited"], calls)

    def test_guest_record_uses_a_private_runtime_directory(self) -> None:
        with mock.patch.object(
            spike,
            "send_command",
            return_value='{"phase":"FINAL_CHECKPOINT_RECORDED"}',
        ) as send_command:
            result = spike.guest_landing_action(
                instance_id=self.outputs()["InstanceId"],
                run_id=self.RUN_ID,
                volume_id=self.outputs()["WorkspaceVolumeId"],
                action="record-checkpoint",
                record={"schemaVersion": 1},
            )

        commands = send_command.call_args.args[1]
        self.assertEqual("FINAL_CHECKPOINT_RECORDED", result["phase"])
        self.assertIn('RECORD_DIR="/run/lift-spike-land"', commands)
        self.assertIn(
            'install -d -o root -g root -m 0700 "$RECORD_DIR"', commands
        )
        self.assertIn('test ! -L "$RECORD_DIR"', commands)
        self.assertIn('RECORD=$(mktemp "$RECORD_DIR/record.XXXXXX")', commands)
        self.assertLess(
            commands.index('install -d -o root -g root -m 0700 "$RECORD_DIR"'),
            commands.index('RECORD=$(mktemp "$RECORD_DIR/record.XXXXXX")'),
        )

    def test_clean_land_completes_all_phases_appends_checkpoint_and_acks(self) -> None:
        state = self.initial_state()
        acknowledgement = self.acknowledgement()

        with self.controller_boundaries(
            state=state, land_result=self.applied_result()
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        result = json.loads(stdout.getvalue())
        workspace = state["workspace"]
        land = workspace["land"]
        self.assertEqual("APPLIED", result["outcome"])
        self.assertEqual("LOCAL_PRIMARY", result["lease"])
        self.assertEqual("LOCAL_PRIMARY", workspace["lease"])
        self.assertEqual("COMPLETE", land["phase"])
        self.assertEqual(acknowledgement, land["acknowledgement"])
        self.assertEqual(acknowledgement, land["guestAcknowledgement"]["acknowledgement"])
        self.assertEqual(
            [self.prior_checkpoint(), self.final_checkpoint()],
            workspace["checkpoints"],
        )
        self.assertEqual("LANDED", state["connection"]["state"])
        self.assertFalse(state["readiness"]["safeToClose"])
        self.assertEqual("STOPPED", state["runtime"]["state"])

        actions = [
            call.kwargs["action"]
            for call in boundaries["guest_landing_action"].call_args_list
        ]
        self.assertEqual(["freeze", "record-checkpoint", "acknowledge"], actions)
        self.assertEqual(
            acknowledgement,
            boundaries["guest_landing_action"].call_args_list[-1].kwargs["record"],
        )
        boundaries["atomic_private_json"].assert_called_once_with(
            self.land_root / "acknowledgement.json", acknowledgement
        )
        boundaries["stop_compute_after_land"].assert_called_once()
        self.assertEqual(
            [
                "land.runtime_install_started",
                "land.runtime_ready",
                "land.requested",
                "land.cloud_frozen",
                "land.final_checkpoint_sealed",
                "land.final_checkpoint_durable",
                "land.final_checkpoint_imported",
                "land.local_reconciled",
                "land.acknowledgement_durable",
                "land.complete",
                "land.compute_stopped",
            ],
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )

    def test_clean_land_persists_the_keep_compute_decision(self) -> None:
        state = self.initial_state()

        with self.controller_boundaries(
            state=state, land_result=self.applied_result()
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=True))

        result = json.loads(stdout.getvalue())
        expected = {"state": "running", "requested": False}
        self.assertEqual(expected, result["compute"])
        self.assertEqual(expected, state["workspace"]["land"]["computeCleanup"])
        self.assertEqual("RUNNING", state["runtime"]["state"])
        boundaries["stop_compute_after_land"].assert_not_called()
        self.assertEqual(
            "land.compute_retained",
            boundaries["record_event"].call_args_list[-1].args[0],
        )

    def test_runtime_install_failure_invalidates_readiness_before_mutation(
        self,
    ) -> None:
        state = self.initial_state()

        with self.controller_boundaries(
            state=state, land_result=self.applied_result()
        ) as boundaries:
            boundaries["install_runtime_bundle"].side_effect = spike.SpikeError(
                "injected runtime install failure"
            )
            with self.assertRaisesRegex(
                spike.SpikeError, "injected runtime install failure"
            ):
                spike.cmd_land(mock.Mock(keep_compute_running=False))

        self.assertFalse(state["readiness"]["safeToClose"])
        self.assertFalse(state["readiness"]["workloadHealthy"])
        self.assertEqual("CLOUD_PRIMARY", state["workspace"]["lease"])
        self.assertNotIn("land", state["workspace"])
        self.assertEqual("FAILED", state["runtime"]["runtimeDeploymentState"])
        self.assertEqual(
            "LAND_RUNTIME_INSTALL_FAILED", state["connection"]["state"]
        )
        self.assertEqual(
            ["land.runtime_install_started", "land.runtime_install_failed"],
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )
        boundaries["guest_landing_action"].assert_not_called()

    def test_needs_review_keeps_landing_lease_and_never_acks_or_stops(self) -> None:
        state = self.initial_state()
        conflicts = [{"path": "README.md", "kind": "content"}]
        land_result = {
            "outcome": "NEEDS_REVIEW",
            "conflicts": conflicts,
            "conflictWorktree": str(self.root / "conflict-worktree"),
        }

        with self.controller_boundaries(
            state=state, land_result=land_result
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        result = json.loads(stdout.getvalue())
        workspace = state["workspace"]
        land = workspace["land"]
        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertEqual("LANDING", result["lease"])
        self.assertEqual("LANDING", workspace["lease"])
        self.assertEqual("NEEDS_REVIEW", land["phase"])
        self.assertEqual(conflicts, land["result"]["conflicts"])
        self.assertEqual(
            [self.prior_checkpoint(), self.final_checkpoint()],
            workspace["checkpoints"],
        )
        self.assertEqual(
            ["freeze", "record-checkpoint"],
            [
                call.kwargs["action"]
                for call in boundaries["guest_landing_action"].call_args_list
            ],
        )
        boundaries["build_land_acknowledgement"].assert_not_called()
        boundaries["atomic_private_json"].assert_not_called()
        boundaries["stop_compute_after_land"].assert_not_called()
        self.assertNotIn("acknowledgement", land)
        self.assertIn(
            "land.needs_review",
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )
        self.assertNotIn(
            "land.complete",
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )

    def test_needs_review_retry_revalidates_live_and_local_evidence_without_mutation(
        self,
    ) -> None:
        state = self.initial_state()
        checkpoint = self.final_checkpoint()
        land_result = {
            "outcome": "NEEDS_REVIEW",
            "conflicts": [{"path": "README.md", "reason": "git-conflict"}],
            "conflictWorktree": str(self.land_root / "operation/merge-worktree"),
        }
        state["workspace"]["lease"] = "LANDING"
        state["workspace"]["checkpoints"].append(checkpoint)
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "NEEDS_REVIEW",
            "ordinal": 2,
            "finalCheckpoint": checkpoint,
            "result": land_result,
        }
        original = copy.deepcopy(state)

        with self.controller_boundaries(
            state=state, land_result=land_result
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        result = json.loads(stdout.getvalue())
        self.assertEqual("NEEDS_REVIEW", result["outcome"])
        self.assertFalse(result["changed"])
        self.assertEqual(original, state)
        boundaries["assert_identity"].assert_called_once_with(state)
        boundaries["validated_stack_context"].assert_called_once_with(state)
        boundaries["validate_existing_local_land_paths"].assert_called_once_with(
            state
        )
        boundaries["prepare_local_land_paths"].assert_not_called()
        boundaries["ensure_instance_online"].assert_not_called()
        self.assertEqual(
            ["status"],
            [
                call.kwargs["action"]
                for call in boundaries["guest_landing_action"].call_args_list
            ],
        )
        boundaries["validate_conflicted_land_fixture"].assert_called_once()
        boundaries["land_fixture"].assert_not_called()
        boundaries["atomic_state"].assert_not_called()
        boundaries["record_event"].assert_not_called()

    def test_needs_review_retry_rejects_corrupt_local_conflict_result(
        self,
    ) -> None:
        state = self.initial_state()
        checkpoint = self.final_checkpoint()
        verified_result = {
            "outcome": "NEEDS_REVIEW",
            "conflicts": [{"path": "README.md", "reason": "git-conflict"}],
            "conflictWorktree": str(self.land_root / "operation/merge-worktree"),
        }
        corrupted_result = copy.deepcopy(verified_result)
        corrupted_result["conflicts"] = []
        state["workspace"]["lease"] = "LANDING"
        state["workspace"]["checkpoints"].append(checkpoint)
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "NEEDS_REVIEW",
            "ordinal": 2,
            "finalCheckpoint": checkpoint,
            "result": corrupted_result,
        }
        original = copy.deepcopy(state)

        with self.controller_boundaries(
            state=state, land_result=verified_result
        ) as boundaries:
            with self.assertRaisesRegex(
                spike.SpikeError,
                "saved local Land conflict result changed on retry",
            ):
                spike.cmd_land(mock.Mock(keep_compute_running=False))

        self.assertEqual(original, state)
        boundaries["validate_conflicted_land_fixture"].assert_called_once()
        boundaries["land_fixture"].assert_not_called()
        boundaries["atomic_state"].assert_not_called()
        boundaries["record_event"].assert_not_called()

    def test_needs_review_retry_rejects_lost_live_guest_fence(self) -> None:
        state = self.initial_state()
        checkpoint = self.final_checkpoint()
        land_result = {
            "outcome": "NEEDS_REVIEW",
            "conflicts": [{"path": "README.md", "reason": "git-conflict"}],
            "conflictWorktree": str(self.land_root / "operation/merge-worktree"),
        }
        state["workspace"]["lease"] = "LANDING"
        state["workspace"]["checkpoints"].append(checkpoint)
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "NEEDS_REVIEW",
            "ordinal": 2,
            "finalCheckpoint": checkpoint,
            "result": land_result,
        }
        original = copy.deepcopy(state)

        with self.controller_boundaries(
            state=state, land_result=land_result
        ) as boundaries:
            boundaries["guest_landing_action"].side_effect = spike.SpikeError(
                "isolated user manager is not durably fenced"
            )
            with self.assertRaisesRegex(
                spike.SpikeError,
                "isolated user manager is not durably fenced",
            ):
                spike.cmd_land(mock.Mock(keep_compute_running=False))

        self.assertEqual(original, state)
        self.assertEqual(
            "status",
            boundaries["guest_landing_action"].call_args.kwargs["action"],
        )
        boundaries["validate_conflicted_land_fixture"].assert_not_called()
        boundaries["land_fixture"].assert_not_called()
        boundaries["atomic_state"].assert_not_called()
        boundaries["record_event"].assert_not_called()

    def test_acknowledged_guest_retry_completes_without_recapturing_final_c(self) -> None:
        state = self.initial_state()
        checkpoint = self.final_checkpoint()
        acknowledgement = self.acknowledgement()
        state["workspace"]["lease"] = "LANDING"
        state["workspace"]["checkpoints"].append(checkpoint)
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "ACK_DURABLE",
            "ordinal": 2,
            "finalCheckpoint": checkpoint,
            "result": self.applied_result(),
            "acknowledgement": acknowledgement,
        }

        with self.controller_boundaries(
            state=state,
            land_result=self.applied_result(),
            acknowledged_on_freeze=True,
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        result = json.loads(stdout.getvalue())
        self.assertEqual("APPLIED", result["outcome"])
        self.assertEqual("LOCAL_PRIMARY", state["workspace"]["lease"])
        self.assertEqual("COMPLETE", state["workspace"]["land"]["phase"])
        self.assertEqual(
            ["freeze"],
            [
                call.kwargs["action"]
                for call in boundaries["guest_landing_action"].call_args_list
            ],
        )
        boundaries["install_runtime_bundle"].assert_not_called()
        boundaries["guest_land_checkpoint"].assert_not_called()
        boundaries["make_land_checkpoint_durable"].assert_not_called()
        boundaries["import_final_checkpoint"].assert_not_called()
        boundaries["land_fixture"].assert_not_called()
        boundaries["build_land_acknowledgement"].assert_not_called()
        boundaries["atomic_private_json"].assert_not_called()
        boundaries["stop_compute_after_land"].assert_called_once()
        self.assertEqual(
            ["land.complete", "land.compute_stopped"],
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )

    def test_completed_land_retries_pending_compute_cleanup(self) -> None:
        state = self.initial_state()
        state["workspace"]["lease"] = "LOCAL_PRIMARY"
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "COMPLETE",
            "ordinal": 2,
            "computeCleanup": {
                "state": "pending",
                "error": "prior stop timed out",
            },
        }

        with self.controller_boundaries(
            state=state, land_result=self.applied_result()
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        result = json.loads(stdout.getvalue())
        self.assertEqual("stopped", result["compute"]["state"])
        self.assertEqual("stopped", state["workspace"]["land"]["computeCleanup"]["state"])
        self.assertEqual("STOPPED", state["runtime"]["state"])
        boundaries["assert_identity"].assert_called_once_with(state)
        boundaries["validated_stack_context"].assert_called_once_with(state)
        boundaries["stop_compute_after_land"].assert_called_once_with(
            state, self.outputs()
        )
        boundaries["prepare_local_land_paths"].assert_not_called()
        boundaries["ensure_instance_online"].assert_not_called()
        boundaries["guest_landing_action"].assert_not_called()
        self.assertEqual(
            ["land.compute_stopped"],
            [call.args[0] for call in boundaries["record_event"].call_args_list],
        )

    def test_completed_land_recovers_a_missing_keep_compute_decision(self) -> None:
        state = self.initial_state()
        state["workspace"]["lease"] = "LOCAL_PRIMARY"
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "COMPLETE",
            "ordinal": 2,
        }

        with self.controller_boundaries(
            state=state, land_result=self.applied_result()
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()) as stdout:
            spike.cmd_land(mock.Mock(keep_compute_running=True))

        result = json.loads(stdout.getvalue())
        expected = {"state": "running", "requested": False}
        self.assertEqual(expected, result["compute"])
        self.assertEqual(expected, state["workspace"]["land"]["computeCleanup"])
        boundaries["stop_compute_after_land"].assert_not_called()
        boundaries["atomic_state"].assert_called_once_with(state)
        boundaries["record_event"].assert_called_once_with(
            "land.compute_retained"
        )

    def test_final_checkpoint_accepts_committed_cloud_head_as_second_parent(self) -> None:
        state = self.initial_state()
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "CLOUD_FROZEN",
            "ordinal": 2,
        }
        state["workspace"]["lease"] = "LANDING"
        checkpoint = self.final_checkpoint()
        checkpoint["cloudHead"] = self.CLOUD_HEAD
        checkpoint["parents"] = [self.PRIOR_COMMIT, self.CLOUD_HEAD]
        checkpoint["historyRefs"][0]["objectId"] = self.CLOUD_HEAD
        checkpoint["recoveryHistoryRefs"][0]["objectId"] = self.CLOUD_HEAD

        with mock.patch.object(
            spike,
            "fixture_policy_for_commit",
            return_value=checkpoint["fixturePolicy"],
        ):
            validated = spike.validate_land_guest_checkpoint(
                state=state,
                outputs=self.outputs(),
                checkpoint=checkpoint,
            )

        self.assertEqual(
            [self.PRIOR_COMMIT, self.CLOUD_HEAD], validated["parents"]
        )

    def test_acknowledgement_manifest_rescans_the_actual_local_workspace(self) -> None:
        workspace = self.root / "actual-workspace"
        marker = spike.create_fixture(workspace)
        ledger = self.root / "actual-ledger.git"
        captured = spike.capture_baseline(
            workspace=workspace,
            ledger=ledger,
            run_id=self.RUN_ID,
            workspace_id=spike.WORKSPACE_ID,
            approved_ignored=[marker["approvedIgnoredPath"]],
        )
        state = {"runId": self.RUN_ID}
        land_result = {
            "mergeResultRef": (
                f"refs/lift/{spike.WORKSPACE_ID}/sessions/{self.RUN_ID}/"
                "land/merge-result"
            ),
            "mergeResultCommit": captured.commit,
        }
        arguments = {
            "state": state,
            "workspace": workspace,
            "ledger": ledger,
            "land_result": land_result,
            "approved_ignored": (marker["approvedIgnoredPath"],),
        }

        manifest, manifest_sha = spike.final_local_land_manifest(**arguments)

        self.assertEqual(captured.commit, manifest["mergeResultCommit"])
        self.assertEqual(manifest["manifestSha256"], manifest_sha)
        (workspace / "README.md").write_text(
            "changed after the verified apply\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            spike.SpikeError, "changed after the verified Land apply"
        ):
            spike.final_local_land_manifest(**arguments)

    def test_ack_durable_retry_reuses_cutover_manifest_after_new_local_work(
        self,
    ) -> None:
        state = self.initial_state()
        checkpoint = self.final_checkpoint()
        acknowledgement = self.acknowledgement()
        state["workspace"]["lease"] = "LANDING"
        state["workspace"]["checkpoints"].append(checkpoint)
        state["workspace"]["land"] = {
            "schemaVersion": 1,
            "operationId": self.operation_id,
            "phase": "ACK_DURABLE",
            "ordinal": 2,
            "guestCheckpoint": checkpoint,
            "finalCheckpoint": checkpoint,
            "import": self.imported_record(),
            "result": self.applied_result(),
            "acknowledgement": acknowledgement,
        }

        with self.controller_boundaries(
            state=state,
            land_result=self.applied_result(),
            saved_ack=acknowledgement,
        ) as boundaries, contextlib.redirect_stdout(io.StringIO()):
            spike.cmd_land(mock.Mock(keep_compute_running=False))

        boundaries["final_local_land_manifest"].assert_not_called()
        boundaries["atomic_private_json"].assert_not_called()
        self.assertEqual("COMPLETE", state["workspace"]["land"]["phase"])
        self.assertEqual("LOCAL_PRIMARY", state["workspace"]["lease"])
        self.assertEqual(
            ["freeze", "record-checkpoint", "acknowledge"],
            [
                call.kwargs["action"]
                for call in boundaries["guest_landing_action"].call_args_list
            ],
        )


if __name__ == "__main__":
    unittest.main()
