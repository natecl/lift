from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

import spike  # noqa: E402


class ApprovalObserverControllerTests(unittest.TestCase):
    INSTANCE_ID = "i-0123456789abcdef0"

    def challenge(self) -> dict:
        return {
            "schemaVersion": 3,
            "nonce": "a" * 32,
            "approvalNonce": "b" * 32,
            "issuedAt": "2026-09-01T20:00:00+00:00",
            "environmentId": "env_test",
            "nativeProjectId": "01a-project",
            "projectRoot": spike.REMOTE_WORKSPACE,
            "expectedCwd": spike.REMOTE_WORKSPACE,
            "proofRelativePath": ".lift/post-restart-proof.json",
            "proofSource": "codex-phone-post-restart",
            "checkpointLabel": "post-restart-phone-proof",
            "threadBaseline": {
                "approvalGuardSha256": "e" * 64,
                "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
                "controllerThreadProjectId": None,
                "createdAtEpochSeconds": 1_788_000_000,
                "cwd": spike.REMOTE_WORKSPACE,
                "environmentId": "env_test",
                "nativeProjectId": "01a-project",
                "projectRoot": spike.REMOTE_WORKSPACE,
                "threadIds": ["thread-a", "thread-z"],
            },
        }

    def command_hashes(self, challenge: dict) -> tuple[str, str]:
        approval_sha256 = hashlib.sha256(
            spike.approval_canary_command(challenge["approvalNonce"]).encode()
        ).hexdigest()
        proof_sha256 = hashlib.sha256(
            spike.phone_proof_command(challenge).encode()
        ).hexdigest()
        return approval_sha256, proof_sha256

    def ready_evidence(self, challenge: dict) -> dict:
        approval_sha256, proof_sha256 = self.command_hashes(challenge)
        baseline = challenge["threadBaseline"]
        return {
            "approvalCommandSha256": approval_sha256,
            "approvalGuardSha256": baseline["approvalGuardSha256"],
            "baselineThreadIdsSha256": (
                spike.approval_observer_thread_ids_sha256(
                    baseline["threadIds"]
                )
            ),
            "challengeSha256": spike.phone_challenge_sha256(challenge),
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "createdAfterEpochSeconds": baseline["createdAtEpochSeconds"],
            "cwd": spike.REMOTE_WORKSPACE,
            "environmentId": challenge["environmentId"],
            "nativeProjectId": challenge["nativeProjectId"],
            "proofCommandSha256": proof_sha256,
            "schemaVersion": 8,
            "verificationMethod": spike.APPROVAL_OBSERVER_READY_METHOD,
        }

    def thread_evidence(self, challenge: dict) -> dict:
        approval_sha256, proof_sha256 = self.command_hashes(challenge)
        return {
            "approvalGuardSha256": challenge["threadBaseline"][
                "approvalGuardSha256"
            ],
            "approvalItemId": "approval-item",
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "commandSha256": {
                "approval": approval_sha256,
                "proof": proof_sha256,
            },
            "proofItemId": "proof-item",
            "threadId": "thread-new",
            "turnId": "turn-new",
        }

    def observation(self, challenge: dict, thread: dict) -> dict:
        baseline = challenge["threadBaseline"]
        return {
            "approvalCommandStartedAtEpochMilliseconds": 1_788_000_010_010,
            "approvalCommandCompletedAtEpochMilliseconds": 1_788_000_010_100,
            "approvalCommandSha256": thread["commandSha256"]["approval"],
            "approvalGuardSha256": thread["approvalGuardSha256"],
            "approvalItemId": thread["approvalItemId"],
            "baselineThreadIdsSha256": (
                spike.approval_observer_thread_ids_sha256(
                    baseline["threadIds"]
                )
            ),
            "challengeSha256": spike.phone_challenge_sha256(challenge),
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "createdAfterEpochSeconds": baseline["createdAtEpochSeconds"],
            "cwd": spike.REMOTE_WORKSPACE,
            "environmentId": challenge["environmentId"],
            "nativeProjectId": challenge["nativeProjectId"],
            "observedAtEpochSeconds": 1_788_000_012,
            "proofCommandCompletedAtEpochMilliseconds": 1_788_000_010_200,
            "proofCommandStartedAtEpochMilliseconds": 1_788_000_010_150,
            "proofCommandSha256": thread["commandSha256"]["proof"],
            "proofItemId": thread["proofItemId"],
            "requestId": "request-approval",
            "requestEnvironmentId": (
                spike.APPROVAL_REQUEST_EXECUTION_ENVIRONMENT_ID
            ),
            "requestStartedAtEpochMilliseconds": 1_788_000_010_000,
            "schemaVersion": 8,
            "threadId": thread["threadId"],
            "threadGoalClearedCount": 1,
            "threadNameUpdatedCount": 1,
            "turnCompletedAtEpochSeconds": 1_788_000_011,
            "turnId": thread["turnId"],
            "verificationMethod": (
                spike.APPROVAL_OBSERVER_VERIFICATION_METHOD
            ),
        }

    def assert_ready_bound(self, evidence: dict, challenge: dict) -> bool:
        approval_sha256, proof_sha256 = self.command_hashes(challenge)
        return spike.approval_observer_ready_is_bound(
            evidence,
            workspace=spike.REMOTE_WORKSPACE,
            challenge=challenge,
            challenge_sha256=spike.phone_challenge_sha256(challenge),
            approval_command_sha256=approval_sha256,
            proof_command_sha256=proof_sha256,
        )

    def assert_observation_bound(
        self, evidence: dict, challenge: dict, thread: dict
    ) -> bool:
        approval_sha256, proof_sha256 = self.command_hashes(challenge)
        return spike.approval_observation_is_bound(
            evidence,
            workspace=spike.REMOTE_WORKSPACE,
            challenge=challenge,
            challenge_sha256=spike.phone_challenge_sha256(challenge),
            approval_command_sha256=approval_sha256,
            proof_command_sha256=proof_sha256,
            thread_evidence=thread,
        )

    def test_start_command_is_hardened_bound_and_hash_only(self) -> None:
        challenge = self.challenge()
        commands = spike.approval_observer_start_commands(
            workspace=spike.REMOTE_WORKSPACE,
            challenge=challenge,
            previous_challenge_sha256="f" * 64,
        )
        script = "#!/usr/bin/env bash\n" + "\n".join(commands) + "\n"
        syntax = subprocess.run(
            ["bash", "-n"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual("", syntax.stderr)
        self.assertEqual(0, syntax.returncode)
        launch = next(command for command in commands if "systemd-run" in command)
        approval_sha256, proof_sha256 = self.command_hashes(challenge)
        challenge_sha256 = spike.phone_challenge_sha256(challenge)
        self.assertIn("--property=NoNewPrivileges=yes", launch)
        self.assertIn("--property=PrivateNetwork=yes", launch)
        self.assertIn("--property=ProtectSystem=strict", launch)
        self.assertIn("--property=ProtectHome=read-only", launch)
        self.assertIn("--property=RestrictAddressFamilies=AF_UNIX", launch)
        self.assertIn("--property=IPAddressDeny=any", launch)
        self.assertIn(
            "--property=ReadWritePaths="
            + spike.REMOTE_APPROVAL_OBSERVATION_ROOT,
            launch,
        )
        self.assertIn("--setenv=PYTHONNOUSERSITE=1", launch)
        self.assertIn("--expected-approval-command-sha256", launch)
        self.assertIn(approval_sha256, launch)
        self.assertIn("--expected-proof-command-sha256", launch)
        self.assertIn(proof_sha256, launch)
        self.assertIn("--challenge-sha256", launch)
        self.assertIn(challenge_sha256, launch)
        self.assertIn("--approval-guard-sha256", launch)
        self.assertNotIn("--approval-nonce", launch)
        self.assertNotIn("--proof-nonce", launch)
        self.assertNotIn(
            spike.approval_canary_command(challenge["approvalNonce"]), launch
        )
        self.assertNotIn(spike.phone_proof_command(challenge), launch)
        self.assertNotIn("LIFT_APPROVAL_CANARY", launch)
        self.assertNotIn("https://example.com/", launch)
        self.assertNotIn(challenge["approvalNonce"], launch)
        self.assertNotIn(challenge["nonce"], launch)
        self.assertIn(
            "systemctl stop "
            + spike.approval_observer_unit_name("f" * 64),
            script,
        )
        self.assertIn('systemctl is-active --quiet "$OBSERVER_UNIT"', script)
        self.assertIn('test ! -L "$RUNTIME_RELEASE/approval_observer.py"', script)
        self.assertIn(
            'test ! -L "$RUNTIME_RELEASE/codex_project.py"', script
        )

    def test_ready_evidence_requires_exact_challenge_binding(self) -> None:
        challenge = self.challenge()
        ready = self.ready_evidence(challenge)
        self.assertTrue(self.assert_ready_bound(ready, challenge))

        mutations = {
            "extra key": lambda value: value.update(extra=True),
            "challenge": lambda value: value.update(challengeSha256="0" * 64),
            "guard": lambda value: value.update(approvalGuardSha256="0" * 64),
            "baseline": lambda value: value.update(
                baselineThreadIdsSha256="0" * 64
            ),
            "approval command": lambda value: value.update(
                approvalCommandSha256="0" * 64
            ),
            "proof command": lambda value: value.update(
                proofCommandSha256="0" * 64
            ),
            "created after": lambda value: value.update(
                createdAfterEpochSeconds=1_788_000_001
            ),
            "workspace": lambda value: value.update(cwd="/tmp"),
            "environment": lambda value: value.update(environmentId="other"),
            "project": lambda value: value.update(nativeProjectId="other"),
            "method": lambda value: value.update(verificationMethod="other"),
            "schema": lambda value: value.update(schemaVersion=1),
        }
        for description, mutate in mutations.items():
            with self.subTest(description=description):
                invalid = copy.deepcopy(ready)
                mutate(invalid)
                self.assertFalse(self.assert_ready_bound(invalid, challenge))

    def test_observation_requires_exact_historical_and_temporal_binding(
        self,
    ) -> None:
        challenge = self.challenge()
        thread = self.thread_evidence(challenge)
        evidence = self.observation(challenge, thread)
        self.assertTrue(
            self.assert_observation_bound(evidence, challenge, thread)
        )

        mutations = {
            "extra key": lambda value: value.update(extra=True),
            "request bool": lambda value: value.update(requestId=True),
            "challenge": lambda value: value.update(challengeSha256="0" * 64),
            "approval hash": lambda value: value.update(
                approvalCommandSha256="0" * 64
            ),
            "proof hash": lambda value: value.update(
                proofCommandSha256="0" * 64
            ),
            "thread": lambda value: value.update(threadId="other"),
            "turn": lambda value: value.update(turnId="other"),
            "approval item": lambda value: value.update(
                approvalItemId="other"
            ),
            "proof item": lambda value: value.update(proofItemId="other"),
            "request environment": lambda value: value.update(
                requestEnvironmentId="other"
            ),
            "request before baseline": lambda value: value.update(
                requestStartedAtEpochMilliseconds=1_787_999_999_999
            ),
            "approval before request": lambda value: value.update(
                approvalCommandCompletedAtEpochMilliseconds=1_788_000_009_999
            ),
            "approval start before request": lambda value: value.update(
                approvalCommandStartedAtEpochMilliseconds=1_788_000_009_999
            ),
            "approval start lag": lambda value: value.update(
                approvalCommandStartedAtEpochMilliseconds=1_788_000_020_001
            ),
            "proof before approval": lambda value: value.update(
                proofCommandCompletedAtEpochMilliseconds=1_788_000_010_099
            ),
            "proof start before approval": lambda value: value.update(
                proofCommandStartedAtEpochMilliseconds=1_788_000_010_099
            ),
            "turn before proof": lambda value: value.update(
                turnCompletedAtEpochSeconds=1_788_000_009
            ),
            "observed before turn": lambda value: value.update(
                observedAtEpochSeconds=1_788_000_010
            ),
            "method": lambda value: value.update(verificationMethod="other"),
        }
        for description, mutate in mutations.items():
            with self.subTest(description=description):
                invalid = copy.deepcopy(evidence)
                mutate(invalid)
                self.assertFalse(
                    self.assert_observation_bound(invalid, challenge, thread)
                )

        changed_thread = copy.deepcopy(thread)
        changed_thread["commandSha256"]["approval"] = "0" * 64
        self.assertFalse(
            self.assert_observation_bound(evidence, challenge, changed_thread)
        )

    def test_managed_arm_parses_and_validates_last_json(self) -> None:
        challenge = self.challenge()
        ready = self.ready_evidence(challenge)
        response = "observer startup log\n" + json.dumps(ready)
        with mock.patch.object(
            spike, "send_command", return_value=response
        ) as send:
            observed = spike.managed_approval_observer_arm(
                self.INSTANCE_ID,
                spike.REMOTE_WORKSPACE,
                challenge,
                previous_challenge_sha256="f" * 64,
            )

        self.assertEqual(ready, observed)
        self.assertEqual(self.INSTANCE_ID, send.call_args.args[0])
        self.assertEqual(
            "Arm root-owned native approval observer", send.call_args.args[2]
        )
        self.assertEqual(60, send.call_args.kwargs["timeout_seconds"])
        self.assertIn(
            spike.approval_observer_unit_name("f" * 64),
            "\n".join(send.call_args.args[1]),
        )

        invalid = copy.deepcopy(ready)
        invalid["challengeSha256"] = "0" * 64
        with (
            mock.patch.object(
                spike, "send_command", return_value=json.dumps(invalid)
            ),
            mock.patch.object(
                spike, "stop_managed_approval_observer"
            ) as stop,
        ):
            with self.assertRaisesRegex(spike.SpikeError, "not bound"):
                spike.managed_approval_observer_arm(
                    self.INSTANCE_ID, spike.REMOTE_WORKSPACE, challenge
                )
        stop.assert_called_once_with(
            self.INSTANCE_ID, spike.phone_challenge_sha256(challenge)
        )

        with (
            mock.patch.object(spike, "send_command", return_value=""),
            mock.patch.object(
                spike, "stop_managed_approval_observer"
            ) as stop,
        ):
            with self.assertRaisesRegex(spike.SpikeError, "valid JSON"):
                spike.managed_approval_observer_arm(
                    self.INSTANCE_ID, spike.REMOTE_WORKSPACE, challenge
                )
        stop.assert_called_once_with(
            self.INSTANCE_ID, spike.phone_challenge_sha256(challenge)
        )

        with (
            mock.patch.object(
                spike,
                "send_command",
                side_effect=spike.SpikeError("observer startup failed"),
            ),
            mock.patch.object(
                spike, "stop_managed_approval_observer"
            ) as stop,
        ):
            with self.assertRaisesRegex(spike.SpikeError, "startup failed"):
                spike.managed_approval_observer_arm(
                    self.INSTANCE_ID, spike.REMOTE_WORKSPACE, challenge
                )
        stop.assert_called_once_with(
            self.INSTANCE_ID, spike.phone_challenge_sha256(challenge)
        )

    def test_managed_evidence_requires_successful_unit_and_exact_file(
        self,
    ) -> None:
        challenge = self.challenge()
        thread = self.thread_evidence(challenge)
        evidence = self.observation(challenge, thread)
        response = "observer journal summary\n" + json.dumps(evidence)
        with mock.patch.object(
            spike, "send_command", return_value=response
        ) as send:
            observed = spike.managed_approval_observer_evidence(
                self.INSTANCE_ID,
                spike.REMOTE_WORKSPACE,
                challenge,
                thread,
            )

        self.assertEqual(evidence, observed)
        self.assertEqual(
            "Read root-owned native approval observation",
            send.call_args.args[2],
        )
        self.assertEqual(60, send.call_args.kwargs["timeout_seconds"])
        commands = send.call_args.args[1]
        script = "\n".join(commands)
        unit = spike.approval_observer_unit_name(
            spike.phone_challenge_sha256(challenge)
        )
        self.assertIn(f"OBSERVER_UNIT={unit}", commands)
        self.assertIn(
            'test "$(systemctl show "$OBSERVER_UNIT" --property=ActiveState --value)" = active',
            commands,
        )
        self.assertIn(
            'test "$(systemctl show "$OBSERVER_UNIT" --property=SubState --value)" = exited',
            commands,
        )
        self.assertIn(
            'test "$(systemctl show "$OBSERVER_UNIT" --property=Result --value)" = success',
            commands,
        )
        self.assertIn(
            'test "$(systemctl show "$OBSERVER_UNIT" --property=ExecMainStatus --value)" = 0',
            commands,
        )
        self.assertIn('test ! -L "$EVIDENCE_PATH"', commands)
        self.assertIn(
            'test "$(stat -c \'%a:%u:%g:%h:%F\' -- "$EVIDENCE_PATH")" = "600:0:0:1:regular file"',
            commands,
        )
        self.assertIn('cat -- "$EVIDENCE_PATH"', commands)
        self.assertNotIn("journalctl", script)

        with mock.patch.object(spike, "send_command", return_value=""):
            with self.assertRaisesRegex(spike.SpikeError, "valid JSON"):
                spike.managed_approval_observer_evidence(
                    self.INSTANCE_ID,
                    spike.REMOTE_WORKSPACE,
                    challenge,
                    thread,
                )

        with mock.patch.object(
            spike,
            "send_command",
            side_effect=spike.SpikeError("approval evidence file is missing"),
        ):
            with self.assertRaisesRegex(spike.SpikeError, "file is missing"):
                spike.managed_approval_observer_evidence(
                    self.INSTANCE_ID,
                    spike.REMOTE_WORKSPACE,
                    challenge,
                    thread,
                )

    def test_managed_evidence_rejects_one_field_mutation(self) -> None:
        challenge = self.challenge()
        thread = self.thread_evidence(challenge)
        evidence = self.observation(challenge, thread)
        evidence["proofItemId"] = "wrong-item"
        with mock.patch.object(
            spike, "send_command", return_value=json.dumps(evidence)
        ):
            with self.assertRaisesRegex(spike.SpikeError, "unbound evidence"):
                spike.managed_approval_observer_evidence(
                    self.INSTANCE_ID,
                    spike.REMOTE_WORKSPACE,
                    challenge,
                    thread,
                )


if __name__ == "__main__":
    unittest.main()
