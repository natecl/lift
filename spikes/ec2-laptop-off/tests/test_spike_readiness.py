from __future__ import annotations

import json
import contextlib
import copy
import hashlib
import io
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

import spike  # noqa: E402


class RuntimeDeploymentTests(unittest.TestCase):
    RUNTIME_SHA = "a" * 64

    def runtime_state(self) -> dict:
        run_id = "p0-20260901120000-abcd"
        account_id = "123456789012"
        stack_name = f"lift-{run_id}"
        return {
            "schemaVersion": 1,
            "revision": 1,
            "runId": run_id,
            "workspaceId": spike.WORKSPACE_ID,
            "identity": {
                "accountId": account_id,
                "principalArn": f"arn:aws:iam::{account_id}:user/lift-admin",
                "profile": spike.PROFILE,
                "region": spike.REGION,
                "userId": "AIDATEST",
            },
            "runtime": {
                "state": "RUNNING",
                "stackName": stack_name,
                "amiId": "ami-0123456789abcdef0",
                "stackId": (
                    f"arn:aws:cloudformation:{spike.REGION}:{account_id}:stack/"
                    f"{stack_name}/00000000-0000-0000-0000-000000000001"
                ),
                "outputs": {
                    "InstanceId": "i-0123456789abcdef0",
                    "WorkspaceVolumeId": "vol-0123456789abcdef0",
                    "TransferBucketName": "lift-runtime-test-bucket",
                    "WorkspacePath": spike.REMOTE_WORKSPACE,
                }
            },
            "workspace": {"lease": "CLOUD_PRIMARY"},
            "readiness": {
                key: True for key in spike.SAFE_TO_CLOSE_REQUIRED_GATES
            },
        }

    def expected_files(self) -> dict[str, tuple[str, str]]:
        return {
            "runner.py": ("1" * 64, "0755"),
            "codex_project.py": ("2" * 64, "0755"),
            "approval_observer.py": ("3" * 64, "0755"),
            "reconstruct.py": ("4" * 64, "0755"),
            "checkpoint.py": ("5" * 64, "0755"),
            "recipes/codex-headless.json": ("6" * 64, "0644"),
        }

    def install_script(self) -> str:
        commands = spike.runtime_install_commands(
            bucket="lift-runtime-test-bucket",
            runtime_key=(
                "sessions/p0-20260901120000-abcd/runtime/"
                f"{self.RUNTIME_SHA}.tar.gz"
            ),
            runtime_sha=self.RUNTIME_SHA,
            expected_files=self.expected_files(),
        )
        return "#!/usr/bin/env bash\n" + "\n".join(commands) + "\n"

    def test_runtime_install_is_staged_validated_and_atomically_activated(self) -> None:
        script = self.install_script()
        syntax = subprocess.run(
            ["bash", "-n"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual("", syntax.stderr)
        self.assertEqual(0, syntax.returncode)
        self.assertIn("/opt/lift-spike-releases/" + self.RUNTIME_SHA, script)
        self.assertIn('STAGE_DIR=$(mktemp -d "$RELEASE_ROOT/.stage.$RUNTIME_SHA.XXXXXX")', script)
        self.assertIn('validate_release "$STAGE_DIR"', script)
        self.assertIn('validate_release "$RELEASE_DIR"', script)
        self.assertIn('mv -Tf -- "$ACTIVATE_LINK" "$ACTIVE_PATH"', script)
        self.assertIn("trap finish_runtime_install EXIT", script)
        self.assertIn('case "$PREVIOUS_KIND" in', script)
        self.assertIn('mv -Tf -- "$ROLLBACK_LINK" "$ACTIVE_PATH"', script)
        self.assertIn(
            'load_state=$(systemctl show "$SERVICE_UNIT" '
            "--property=LoadState --value",
            script,
        )
        self.assertIn(
            'active_state=$(systemctl show "$SERVICE_UNIT" '
            "--property=ActiveState --value",
            script,
        )
        self.assertIn(
            "active|activating|reloading) SERVICE_WAS_ACTIVE=1",
            script,
        )
        self.assertIn(
            'enabled_state=$(systemctl is-enabled "$SERVICE_UNIT"',
            script,
        )
        self.assertIn('systemctl disable --now "$SERVICE_UNIT"', script)
        self.assertIn(
            '(set -o noclobber; : > "$LOCK_PATH") 2>/dev/null || true',
            script,
        )
        self.assertIn('exec 9<>"$LOCK_PATH"', script)
        self.assertIn("flock -n 9", script)
        self.assertIn(
            'python3 "$ACTIVE_PATH/runner.py" start '
            '--recipe "$ACTIVE_PATH/recipes/codex-headless.json"',
            script,
        )
        self.assertIn('python3 "$ACTIVE_PATH/runner.py" status >/dev/null', script)
        self.assertNotIn("systemctl restart lift-workload.service", script)
        self.assertIn(
            'python3 "$ACTIVE_PATH/approval_observer.py" --help >/dev/null',
            script,
        )
        self.assertIn(
            'test "$(find "$release" -xdev -mindepth 1 -printf . | wc -c)" -eq 7',
            script,
        )
        self.assertIn(
            "approval_observer.py checkpoint.py codex_project.py",
            script,
        )
        self.assertNotIn(
            'install -o root -g root -m 0755 "$TMP_DIR/unpack/runner.py" /opt/lift-spike/runner.py',
            script,
        )

    def test_runtime_upgrade_quiesces_before_swap_and_recreates_runner_unit(self) -> None:
        script = self.install_script()

        capture = script.index("\ncapture_service_intent\n")
        quiesce = script.index("\nquiesce_service\n")
        switch = script.index("\nSWITCH_STARTED=1\n")
        activate = script.index('mv -Tf -- "$ACTIVATE_LINK" "$ACTIVE_PATH"')
        restore = script.rindex("\nrestore_service_intent\n")

        self.assertLess(capture, quiesce)
        self.assertLess(quiesce, switch)
        self.assertLess(switch, activate)
        self.assertLess(activate, restore)
        self.assertIn(
            'if [ "$SERVICE_WAS_ACTIVE" -eq 0 ]; then\n'
            '    systemctl stop "$SERVICE_UNIT" || return 1',
            script,
        )
        self.assertIn(
            'if [ "$SERVICE_WAS_ENABLED" -eq 0 ]; then\n'
            '    systemctl disable "$SERVICE_UNIT" || return 1',
            script,
        )
        self.assertIn(
            'if [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then\n'
            '    systemctl is-active --quiet "$SERVICE_UNIT" || return 1',
            script,
        )
        self.assertIn(
            'if [ "$SERVICE_WAS_ENABLED" -eq 1 ]; then\n'
            '    systemctl is-enabled --quiet "$SERVICE_UNIT" || return 1',
            script,
        )

    def test_runtime_upgrade_failure_rolls_back_then_recovers_or_stays_stopped(
        self,
    ) -> None:
        script = self.install_script()
        finish = script.split("finish_runtime_install() {", 1)[1].split(
            "trap finish_runtime_install EXIT", 1
        )[0]

        first_fail_closed = finish.index("fail_closed_service")
        rollback = finish.index("rollback_active_runtime")
        recover = finish.index("restore_service_intent")
        final_fail_closed = finish.rindex("fail_closed_service")

        self.assertLess(first_fail_closed, rollback)
        self.assertLess(rollback, recover)
        self.assertLess(recover, final_fail_closed)
        self.assertIn(
            'if [ "$status" -ne 0 ] && '
            '[ "$SERVICE_MUTATION_STARTED" -eq 1 ]; then',
            finish,
        )
        self.assertIn(
            "if ! restore_service_intent >/dev/null 2>&1; then\n"
            "        recovery_failed=1\n"
            "        fail_closed_service || recovery_failed=1",
            finish,
        )
        self.assertIn(
            "if fail_closed_service; then\n"
            '      if [ "$SWITCH_STARTED" -eq 1 ]; then',
            finish,
        )
        self.assertIn(
            'systemctl reset-failed "$SERVICE_UNIT" >/dev/null 2>&1 || true\n'
            '  if systemctl is-active --quiet "$SERVICE_UNIT"; then return 1; fi',
            script,
        )
        self.assertIn(
            'test "$(stat -c \'%a:%u:%g:%h\' -- "$LOCK_PATH")" = '
            '"600:0:0:1"',
            script,
        )
        self.assertNotIn("%a:%u:%g:%h:%F", script)
        self.assertIn("verify_previous_active_runtime", finish)
        self.assertIn(
            "runtime install recovery could not restore the prior state",
            finish,
        )
        self.assertIn("runtime install failed at script line $LINENO", script)
        self.assertIn("trap - ERR\n  trap - EXIT", finish)
        self.assertIn('sync -f "$RELEASE_ROOT" || return 1', script)
        self.assertIn(
            'if [ "$SERVICE_WAS_PRESENT" -eq 1 ]; then '
            "remove_inactive_service_definition || return 1; fi",
            script,
        )

    def test_runtime_bundle_contains_exact_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle, digest = spike.build_runtime_bundle(Path(temp_dir))
            actual_digest = spike.sha256_file(bundle)
            with tarfile.open(bundle, "r:gz") as archive:
                members = {member.name for member in archive.getmembers()}

        self.assertEqual(actual_digest, digest)
        self.assertEqual(
            {
                "approval_observer.py",
                "checkpoint.py",
                "codex_project.py",
                "recipes/codex-headless.json",
                "reconstruct.py",
                "runner.py",
            },
            members,
        )

    def test_runtime_install_rejects_state_values_before_upload_or_commands(self) -> None:
        invalid_states = []
        invalid_run = self.runtime_state()
        invalid_run["runId"] = "../../shell-injection"
        invalid_states.append(invalid_run)
        invalid_instance = self.runtime_state()
        invalid_instance["runtime"]["outputs"]["InstanceId"] = "i-good; reboot"
        invalid_states.append(invalid_instance)
        invalid_bucket = self.runtime_state()
        invalid_bucket["runtime"]["outputs"]["TransferBucketName"] = "bucket; reboot"
        invalid_states.append(invalid_bucket)

        for state in invalid_states:
            with self.subTest(state=state), mock.patch.object(
                spike, "build_runtime_bundle"
            ) as build, mock.patch.object(spike, "upload_file") as upload, mock.patch.object(
                spike, "send_command"
            ) as send:
                with self.assertRaises(spike.SpikeError):
                    spike.install_runtime_bundle(state)
                build.assert_not_called()
                upload.assert_not_called()
                send.assert_not_called()

    def test_runtime_install_records_versioned_release_metadata(self) -> None:
        state = self.runtime_state()
        fake_bundle = Path("/tmp/guest-runtime.tar.gz")
        file_hashes = iter(value[0] for value in self.expected_files().values())
        with (
            mock.patch.object(
                spike,
                "build_runtime_bundle",
                return_value=(fake_bundle, self.RUNTIME_SHA),
            ),
            mock.patch.object(spike, "sha256_file", side_effect=file_hashes),
            mock.patch.object(spike, "upload_file") as upload,
            mock.patch.object(spike, "send_command", return_value="installed") as send,
        ):
            installed = spike.install_runtime_bundle(state)

        expected_key = (
            "sessions/p0-20260901120000-abcd/runtime/"
            f"{self.RUNTIME_SHA}.tar.gz"
        )
        upload.assert_called_once_with(
            fake_bundle, "lift-runtime-test-bucket", expected_key
        )
        self.assertEqual("i-0123456789abcdef0", send.call_args.args[0])
        self.assertEqual(
            f"/opt/lift-spike-releases/{self.RUNTIME_SHA}",
            installed["runtimeReleasePath"],
        )
        self.assertEqual("/opt/lift-spike", installed["runtimeActivePath"])
        self.assertEqual(
            self.expected_files()["approval_observer.py"][0],
            installed["approvalObserverSha256"],
        )

    def test_failed_runtime_install_clears_readiness_before_remote_mutation(self) -> None:
        state = self.runtime_state()
        state["readiness"]["approvalEvidence"] = {"threadId": "thread"}
        persisted_states: list[dict] = []

        with (
            mock.patch.object(spike, "load_state", return_value=state),
            mock.patch.object(spike, "assert_identity"),
            mock.patch.object(
                spike,
                "validated_stack_context",
                return_value=state["runtime"]["outputs"],
            ),
            mock.patch.object(spike, "wait_for_ssm"),
            mock.patch.object(
                spike,
                "install_runtime_bundle",
                side_effect=spike.SpikeError("activation verification failed"),
            ),
            mock.patch.object(
                spike,
                "atomic_state",
                side_effect=lambda value: persisted_states.append(copy.deepcopy(value)),
            ),
            mock.patch.object(spike, "record_event"),
        ):
            with self.assertRaisesRegex(spike.SpikeError, "activation verification"):
                spike.cmd_install_runtime(mock.Mock())

        self.assertGreaterEqual(len(persisted_states), 2)
        self.assertEqual("INSTALLING", persisted_states[0]["runtime"]["runtimeDeploymentState"])
        self.assertEqual("FAILED", persisted_states[-1]["runtime"]["runtimeDeploymentState"])
        self.assertFalse(state["readiness"]["safeToClose"])
        self.assertFalse(state["readiness"]["workloadHealthy"])
        self.assertFalse(state["readiness"]["approvalRoundTripVerified"])
        self.assertNotIn("approvalEvidence", state["readiness"])


class StateAndStackValidationTests(unittest.TestCase):
    def state(self) -> dict:
        run_id = "p0-20260901120000-abcd"
        account_id = "123456789012"
        stack_name = f"lift-{run_id}"
        outputs = {
            "InstanceId": "i-0123456789abcdef0",
            "WorkspaceVolumeId": "vol-0123456789abcdef0",
            "TransferBucketName": "lift-runtime-test-bucket",
            "WorkspacePath": spike.REMOTE_WORKSPACE,
            "LedgerPath": "/var/lib/lift/ledger",
            "VpcId": "vpc-0123456789abcdef0",
            "SecurityGroupId": "sg-0123456789abcdef0",
        }
        return {
            "schemaVersion": 1,
            "revision": 7,
            "runId": run_id,
            "workspaceId": spike.WORKSPACE_ID,
            "createdAt": "2026-09-01T12:00:00+00:00",
            "identity": {
                "accountId": account_id,
                "principalArn": f"arn:aws:iam::{account_id}:user/lift-admin",
                "profile": spike.PROFILE,
                "region": spike.REGION,
                "userId": "AIDATEST",
            },
            "runtime": {
                "state": "RUNNING",
                "stackName": stack_name,
                "amiId": "ami-0123456789abcdef0",
                "stackId": (
                    f"arn:aws:cloudformation:{spike.REGION}:{account_id}:stack/"
                    f"{stack_name}/00000000-0000-0000-0000-000000000001"
                ),
                "outputs": outputs,
            },
            "workspace": {
                "lease": "CLOUD_PRIMARY",
                "cloudPath": spike.REMOTE_WORKSPACE,
            },
            "connection": {"state": "CONNECTED"},
            "readiness": {},
        }

    def stack(self, state: dict) -> dict:
        runtime = state["runtime"]
        return {
            "StackName": runtime["stackName"],
            "StackId": runtime["stackId"],
            "StackStatus": "CREATE_COMPLETE",
            "Parameters": [
                {"ParameterKey": "AmiId", "ParameterValue": runtime["amiId"]},
                {
                    "ParameterKey": "InstanceType",
                    "ParameterValue": "c7i-flex.large",
                },
                {
                    "ParameterKey": "WorkspaceVolumeSize",
                    "ParameterValue": "30",
                },
                {"ParameterKey": "AutoStopMinutes", "ParameterValue": "240"},
                {"ParameterKey": "SpikeId", "ParameterValue": state["runId"]},
            ],
            "Outputs": [
                {"OutputKey": key, "OutputValue": value}
                for key, value in runtime["outputs"].items()
            ],
        }

    def resources(self, state: dict) -> list[dict]:
        outputs = state["runtime"]["outputs"]
        return [
            {
                "LogicalResourceId": "WorkspaceInstance",
                "PhysicalResourceId": outputs["InstanceId"],
                "ResourceType": "AWS::EC2::Instance",
                "ResourceStatus": "CREATE_COMPLETE",
            },
            {
                "LogicalResourceId": "WorkspaceVolume",
                "PhysicalResourceId": outputs["WorkspaceVolumeId"],
                "ResourceType": "AWS::EC2::Volume",
                "ResourceStatus": "CREATE_COMPLETE",
            },
            {
                "LogicalResourceId": "TransferBucket",
                "PhysicalResourceId": outputs["TransferBucketName"],
                "ResourceType": "AWS::S3::Bucket",
                "ResourceStatus": "CREATE_COMPLETE",
            },
        ]

    def test_load_state_rejects_tainted_immutable_values_before_aws(self) -> None:
        mutations = {
            "boolean-schema": lambda state: state.update(schemaVersion=True),
            "shell-run-id": lambda state: state.update(runId="p0-$(reboot)"),
            "traversal-run-id": lambda state: state.update(runId="../../outside"),
            "wrong-stack-name": lambda state: state["runtime"].update(
                stackName="unrelated-production-stack"
            ),
            "invalid-stack-id": lambda state: state["runtime"].update(
                stackId=(
                    f"arn:aws:cloudformation:{spike.REGION}:123456789012:stack/"
                    f"{state['runtime']['stackName']}/00000000-0000-0000-0000000000000"
                )
            ),
            "invalid-ami": lambda state: state["runtime"].update(amiId="ami-good;reboot"),
            "invalid-instance": lambda state: state["runtime"]["outputs"].update(
                InstanceId="i-good;reboot"
            ),
            "invalid-volume": lambda state: state["runtime"]["outputs"].update(
                WorkspaceVolumeId="../../volume"
            ),
            "invalid-bucket": lambda state: state["runtime"]["outputs"].update(
                TransferBucketName="bucket;reboot"
            ),
            "wrong-workspace": lambda state: state["runtime"]["outputs"].update(
                WorkspacePath="/tmp/not-lift"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                state = self.state()
                mutate(state)
                state_path = Path(directory) / "state.json"
                state_path.write_text(json.dumps(state), encoding="utf-8")
                with (
                    mock.patch.object(spike, "STATE_PATH", state_path),
                    mock.patch.object(spike, "aws_json") as aws,
                ):
                    with self.assertRaises(spike.SpikeError):
                        spike.load_state()
                aws.assert_not_called()

    def test_lift_off_rejects_command_substitution_before_aws_or_filesystem(self) -> None:
        state = self.state()
        state["runId"] = "p0-$(reboot)"
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                mock.patch.object(spike, "STATE_PATH", state_path),
                mock.patch.object(spike, "caller_identity") as identity,
                mock.patch.object(spike, "validated_stack_context") as stack_context,
                mock.patch.object(spike, "create_fixture") as create_fixture,
            ):
                with self.assertRaisesRegex(spike.SpikeError, "invalid run ID"):
                    spike.cmd_lift_off(mock.Mock())
            identity.assert_not_called()
            stack_context.assert_not_called()
            create_fixture.assert_not_called()

    def test_lift_off_root_commands_are_argv_quoted(self) -> None:
        state = self.state()
        run_id = state["runId"]
        bucket = state["runtime"]["outputs"]["TransferBucketName"]
        package_sha = "a" * 64

        commands = spike.lift_off_reconstruct_commands(
            run_id=run_id,
            bucket=bucket,
            package_sha=package_sha,
        )

        remote_package = f"/var/lib/lift-spike/packages/{package_sha}.tar.gz"
        self.assertEqual(
            [
                "aws",
                "s3",
                "cp",
                f"s3://{bucket}/sessions/{run_id}/lift-off/{package_sha}.tar.gz",
                remote_package,
                "--only-show-errors",
            ],
            shlex.split(commands[2]),
        )
        self.assertEqual(
            [
                "python3",
                "/opt/lift-spike/reconstruct.py",
                "--package",
                remote_package,
                "--sha256",
                package_sha,
                "--run-id",
                run_id,
                "--workspace-id",
                spike.WORKSPACE_ID,
            ],
            shlex.split(commands[3]),
        )
        with self.assertRaisesRegex(spike.SpikeError, "invalid run ID"):
            spike.lift_off_reconstruct_commands(
                run_id="p0-$(reboot)", bucket=bucket, package_sha=package_sha
            )
        with self.assertRaisesRegex(spike.SpikeError, "invalid transfer bucket"):
            spike.lift_off_reconstruct_commands(
                run_id=run_id, bucket="bucket;reboot", package_sha=package_sha
            )
        with self.assertRaisesRegex(spike.SpikeError, "invalid package SHA-256"):
            spike.lift_off_reconstruct_commands(
                run_id=run_id, bucket=bucket, package_sha="$(reboot)"
            )

    def test_cached_ami_is_revalidated_before_up_writes_or_deploys(self) -> None:
        state = self.state()
        with tempfile.TemporaryDirectory() as directory:
            local_root = Path(directory) / "control"
            with (
                mock.patch.object(spike, "LOCAL_ROOT", local_root),
                mock.patch.object(spike, "load_state", return_value=state),
                mock.patch.object(spike, "assert_identity"),
                mock.patch.object(
                    spike,
                    "validated_stack_context",
                    return_value=state["runtime"]["outputs"],
                ),
                mock.patch.object(
                    spike,
                    "validate_ami",
                    side_effect=spike.SpikeError("not Canonical"),
                ) as validate_ami,
                mock.patch.object(spike, "run") as run,
                mock.patch.object(spike, "atomic_state") as atomic_state,
            ):
                with self.assertRaisesRegex(spike.SpikeError, "not Canonical"):
                    spike.cmd_up(mock.Mock())

            validate_ami.assert_called_once_with(state["runtime"]["amiId"])
            run.assert_not_called()
            atomic_state.assert_not_called()
            self.assertFalse(local_root.exists())

    def test_existing_up_validates_stack_before_deploy_and_preserves_binding(self) -> None:
        state = self.state()
        original_stack_id = state["runtime"]["stackId"]
        original_outputs = copy.deepcopy(state["runtime"]["outputs"])
        calls: list[str] = []

        def validate_context(_: dict) -> dict[str, str]:
            calls.append("validate-stack")
            return copy.deepcopy(original_outputs)

        def deploy(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            self.assertIn("deploy", command)
            calls.append("deploy")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(spike, "LOCAL_ROOT", Path(directory) / "control"),
                mock.patch.object(spike, "load_state", return_value=state),
                mock.patch.object(spike, "assert_identity"),
                mock.patch.object(
                    spike, "validated_stack_context", side_effect=validate_context
                ) as stack_context,
                mock.patch.object(
                    spike, "validate_ami", return_value=state["runtime"]["amiId"]
                ),
                mock.patch.object(spike, "run", side_effect=deploy),
                mock.patch.object(spike, "describe_stack") as describe_stack,
                mock.patch.object(spike, "atomic_state"),
                mock.patch.object(spike, "record_event"),
                mock.patch.object(
                    spike, "aws_raw", side_effect=spike.SpikeError("stop after deploy")
                ),
            ):
                with self.assertRaisesRegex(spike.SpikeError, "stop after deploy"):
                    spike.cmd_up(mock.Mock())

        self.assertEqual(["validate-stack", "deploy", "validate-stack"], calls)
        self.assertEqual(2, stack_context.call_count)
        describe_stack.assert_not_called()
        self.assertEqual(original_stack_id, state["runtime"]["stackId"])
        self.assertEqual(original_outputs, state["runtime"]["outputs"])

    def test_existing_up_rejects_unvalidated_stack_before_any_mutation(self) -> None:
        state = self.state()
        with tempfile.TemporaryDirectory() as directory:
            local_root = Path(directory) / "control"
            with (
                mock.patch.object(spike, "LOCAL_ROOT", local_root),
                mock.patch.object(spike, "load_state", return_value=state),
                mock.patch.object(spike, "assert_identity"),
                mock.patch.object(
                    spike,
                    "validated_stack_context",
                    side_effect=spike.SpikeError("stack binding changed"),
                ),
                mock.patch.object(spike, "validate_ami") as validate_ami,
                mock.patch.object(spike, "run") as run,
                mock.patch.object(spike, "atomic_state") as atomic_state,
                mock.patch.object(spike, "record_event") as record_event,
            ):
                with self.assertRaisesRegex(spike.SpikeError, "stack binding changed"):
                    spike.cmd_up(mock.Mock())

            validate_ami.assert_not_called()
            run.assert_not_called()
            atomic_state.assert_not_called()
            record_event.assert_not_called()
            self.assertFalse(local_root.exists())

    def test_first_create_requires_exact_stack_absence_before_deploy(self) -> None:
        state = self.state()
        state["runtime"] = {
            "state": "NOT_CREATED",
            "stackName": state["runtime"]["stackName"],
        }
        with tempfile.TemporaryDirectory() as directory:
            local_root = Path(directory) / "control"
            with (
                mock.patch.object(spike, "LOCAL_ROOT", local_root),
                mock.patch.object(spike, "load_state", return_value=state),
                mock.patch.object(spike, "assert_identity"),
                mock.patch.object(
                    spike, "resolve_ami", return_value="ami-0123456789abcdef0"
                ),
                mock.patch.object(
                    spike,
                    "assert_stack_absent_for_create",
                    side_effect=spike.SpikeError("stack absence not proven"),
                ) as absent,
                mock.patch.object(spike, "run") as run,
                mock.patch.object(spike, "atomic_state") as atomic_state,
                mock.patch.object(spike, "record_event") as record_event,
            ):
                with self.assertRaisesRegex(spike.SpikeError, "absence not proven"):
                    spike.cmd_up(mock.Mock())

            absent.assert_called_once_with(state["runtime"]["stackName"])
            run.assert_not_called()
            atomic_state.assert_not_called()
            record_event.assert_not_called()
            self.assertFalse(local_root.exists())

    def test_stack_absence_probe_fails_closed_on_any_other_describe_result(self) -> None:
        stack_name = "lift-p0-20260901120000-abcd"
        exact_absence = (
            "An error occurred (ValidationError) when calling the DescribeStacks "
            f"operation: Stack with id {stack_name} does not exist"
        )
        absent = subprocess.CompletedProcess([], 255, "", exact_absence)
        with mock.patch.object(spike, "run", return_value=absent) as run:
            spike.assert_stack_absent_for_create(stack_name)
        command = run.call_args.args[0]
        self.assertEqual(
            [
                *spike.aws_arguments(
                    "cloudformation", "describe-stacks", "--stack-name", stack_name
                ),
                "--output",
                "json",
            ],
            command,
        )
        self.assertFalse(run.call_args.kwargs["check"])

        rejected = (
            subprocess.CompletedProcess([], 0, '{"Stacks": [{}]}', ""),
            subprocess.CompletedProcess([], 255, "", "AccessDenied"),
            subprocess.CompletedProcess(
                [],
                255,
                "",
                exact_absence.replace(stack_name, f"{stack_name}-other"),
            ),
            subprocess.CompletedProcess([], 255, "unexpected output", exact_absence),
        )
        for result in rejected:
            with self.subTest(result=result), mock.patch.object(
                spike, "run", return_value=result
            ):
                with self.assertRaises(spike.SpikeError):
                    spike.assert_stack_absent_for_create(stack_name)

    def test_validate_ami_binds_exact_canonical_available_image(self) -> None:
        ami_id = "ami-0123456789abcdef0"
        valid = {
            "Images": [
                {
                    "ImageId": ami_id,
                    "OwnerId": spike.CANONICAL_OWNER,
                    "Architecture": "x86_64",
                    "State": "available",
                }
            ]
        }
        with mock.patch.object(spike, "aws_json", return_value=valid) as aws:
            self.assertEqual(ami_id, spike.validate_ami(ami_id))
        aws.assert_called_once_with("ec2", "describe-images", "--image-ids", ami_id)

        for field, value in (
            ("ImageId", "ami-11111111111111111"),
            ("OwnerId", "999999999999"),
            ("Architecture", "arm64"),
            ("State", "deregistered"),
        ):
            response = copy.deepcopy(valid)
            response["Images"][0][field] = value
            with self.subTest(field=field), mock.patch.object(
                spike, "aws_json", return_value=response
            ):
                with self.assertRaises(spike.SpikeError):
                    spike.validate_ami(ami_id)

        for images in (None, {}, ["not-an-image"]):
            with self.subTest(images=images), mock.patch.object(
                spike, "aws_json", return_value={"Images": images}
            ):
                with self.assertRaises(spike.SpikeError):
                    spike.validate_ami(ami_id)

    def test_describe_stack_rejects_malformed_aws_collections(self) -> None:
        for stacks in (None, {}, ["not-a-stack"]):
            with self.subTest(stacks=stacks), mock.patch.object(
                spike, "aws_json", return_value={"Stacks": stacks}
            ):
                with self.assertRaises(spike.SpikeError):
                    spike.describe_stack("lift-p0-20260901120000-abcd")

    def test_live_stack_context_binds_outputs_parameters_and_resources(self) -> None:
        state = self.state()
        stack = self.stack(state)
        resources = self.resources(state)

        def aws_response(service: str, operation: str, *args: str) -> dict:
            self.assertEqual("cloudformation", service)
            if operation == "describe-stacks":
                return {"Stacks": [copy.deepcopy(stack)]}
            if operation == "describe-stack-resources":
                return {"StackResources": copy.deepcopy(resources)}
            raise AssertionError((service, operation, args))

        with mock.patch.object(spike, "aws_json", side_effect=aws_response):
            self.assertEqual(
                state["runtime"]["outputs"], spike.validated_stack_context(state)
            )

        for field, value in (
            ("StackName", "unrelated-production-stack"),
            (
                "StackId",
                (
                    f"arn:aws:cloudformation:{spike.REGION}:123456789012:stack/"
                    "lift-p0-20260901120000-abcd/"
                    "11111111-1111-1111-1111-111111111111"
                ),
            ),
        ):
            wrong_identity = copy.deepcopy(stack)
            wrong_identity[field] = value
            with self.subTest(field=field), mock.patch.object(
                spike,
                "aws_json",
                return_value={"Stacks": [wrong_identity]},
            ):
                with self.assertRaisesRegex(spike.SpikeError, "identity"):
                    spike.validated_stack_context(state)

        wrong_live_output = copy.deepcopy(stack)
        next(
            item
            for item in wrong_live_output["Outputs"]
            if item["OutputKey"] == "InstanceId"
        )["OutputValue"] = "i-11111111111111111"
        with mock.patch.object(
            spike,
            "aws_json",
            return_value={"Stacks": [wrong_live_output]},
        ):
            with self.assertRaisesRegex(spike.SpikeError, "outputs differ"):
                spike.validated_stack_context(state)

        wrong_resource = copy.deepcopy(resources)
        wrong_resource[0]["PhysicalResourceId"] = "i-11111111111111111"

        def wrong_resource_response(service: str, operation: str, *args: str) -> dict:
            if operation == "describe-stacks":
                return {"Stacks": [copy.deepcopy(stack)]}
            return {"StackResources": copy.deepcopy(wrong_resource)}

        with mock.patch.object(spike, "aws_json", side_effect=wrong_resource_response):
            with self.assertRaisesRegex(spike.SpikeError, "WorkspaceInstance"):
                spike.validated_stack_context(state)


class SpikeReadinessTests(unittest.TestCase):
    def thread_baseline(self) -> dict:
        return {
            "approvalGuardSha256": "e" * 64,
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "createdAtEpochSeconds": 1_788_000_000,
            "cwd": spike.REMOTE_WORKSPACE,
            "environmentId": "env_test",
            "nativeProjectId": "01a-project",
            "projectRoot": spike.REMOTE_WORKSPACE,
            "threadIds": ["thread-a", "thread-z"],
        }

    def phone_challenge(self) -> dict:
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
            "threadBaseline": self.thread_baseline(),
        }

    def normal_phone_challenge(self) -> dict:
        challenge = self.phone_challenge()
        challenge.update(
            {
                "nonce": "c" * 32,
                "approvalNonce": "d" * 32,
                "proofRelativePath": ".lift/phone-proof.json",
                "proofSource": "codex-phone",
                "checkpointLabel": "phone-proof",
            }
        )
        return challenge

    def thread_evidence(
        self, challenge: dict | None = None, *, combined: bool = True
    ) -> dict:
        challenge = challenge or self.phone_challenge()
        approval_hash = hashlib.sha256(
            spike.approval_canary_command(challenge["approvalNonce"]).encode()
        ).hexdigest()
        proof_hash = hashlib.sha256(
            spike.phone_proof_command(challenge).encode()
        ).hexdigest()
        evidence = {
            "approvalGuardSha256": "e" * 64,
            "approvalItemId": "approval-item",
            "approvalPolicy": "on-request",
            "approvalVerificationMethod": spike.THREAD_VERIFICATION_METHOD,
            "approvalsReviewer": "user",
            "commandSha256": {"approval": approval_hash, "proof": proof_hash},
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "cwd": spike.REMOTE_WORKSPACE,
            "environmentId": "env_test",
            "nativeProjectId": "01a-project",
            "networkAccess": False,
            "projectRoot": spike.REMOTE_WORKSPACE,
            "proofItemId": "proof-item",
            "runtimeWorkspaceRoots": [spike.REMOTE_WORKSPACE],
            "sandboxType": "workspaceWrite",
            "threadId": "thread-new",
            "turnId": "turn-new",
            "verifiedAt": 1_788_000_100,
        }
        if combined:
            evidence["historicalVerificationMethod"] = evidence[
                "approvalVerificationMethod"
            ]
            evidence["approvalVerificationMethod"] = (
                spike.APPROVAL_VERIFICATION_METHOD
            )
            evidence["approvalObservation"] = self.approval_observation(
                challenge, evidence
            )
        return evidence

    def approval_observation(self, challenge: dict, thread: dict) -> dict:
        baseline = challenge["threadBaseline"]
        return {
            "approvalCommandStartedAtEpochMilliseconds": 1_788_000_010_010,
            "approvalCommandCompletedAtEpochMilliseconds": 1_788_000_010_100,
            "approvalCommandSha256": thread["commandSha256"]["approval"],
            "approvalGuardSha256": thread["approvalGuardSha256"],
            "approvalItemId": thread["approvalItemId"],
            "baselineThreadIdsSha256": spike.approval_observer_thread_ids_sha256(
                baseline["threadIds"]
            ),
            "challengeSha256": spike.phone_challenge_sha256(challenge),
            "controllerThreadBinding": spike.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "createdAfterEpochSeconds": baseline["createdAtEpochSeconds"],
            "cwd": spike.REMOTE_WORKSPACE,
            "environmentId": thread["environmentId"],
            "nativeProjectId": thread["nativeProjectId"],
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
            "verificationMethod": spike.APPROVAL_OBSERVER_VERIFICATION_METHOD,
        }

    def safe_state(self) -> dict:
        challenge = self.phone_challenge()
        challenge_sha = spike.phone_challenge_sha256(challenge)
        proof_sha = hashlib.sha256(
            spike.proof_bytes(challenge, challenge["proofSource"])
        ).hexdigest()
        thread = self.thread_evidence()
        checkpoint_commit = "1" * 40
        checkpoint_tree = "2" * 40
        bundle_sha = "3" * 64
        manifest_file_sha = "4" * 64
        restore_test = {
            "bundleLocalSha256": bundle_sha,
            "manifestLocalSha256": manifest_file_sha,
            "restoredCommit": checkpoint_commit,
            "restoredTree": checkpoint_tree,
            "restoredFileCount": 7,
            "verifiedAt": "2026-09-01T20:09:00+00:00",
        }
        state = {
            "schemaVersion": 1,
            "revision": 1,
            "runId": "p0-test",
            "identity": {},
            "runtime": {
                "outputs": {
                    "InstanceId": "i-0123456789abcdef0",
                    "WorkspaceVolumeId": "vol-0123456789abcdef0",
                }
            },
            "workspace": {
                "lease": "CLOUD_PRIMARY",
                "cloudPath": spike.REMOTE_WORKSPACE,
                "baselineCommit": "baseline",
                "checkpoints": [
                    {
                        "commit": checkpoint_commit,
                        "tree": checkpoint_tree,
                        "bundleSha256": bundle_sha,
                        "manifestFileSha256": manifest_file_sha,
                        "fileCount": 7,
                        "s3VersionId": "bundle-version",
                        "s3ManifestVersionId": "manifest-version",
                        "restoreTest": restore_test,
                        "phoneChallengeSha256": challenge_sha,
                        "phoneProofSha256": proof_sha,
                        "phoneProofSource": challenge["proofSource"],
                    }
                ],
            },
            "readiness": {
                key: True for key in spike.SAFE_TO_CLOSE_REQUIRED_GATES
            },
        }
        readiness = state["readiness"]
        readiness.update(
            {
                "providerEnvironmentId": "env_test",
                "nativeProjectId": "01a-project",
                "challenge": challenge,
                "activeChallengeSha256": challenge_sha,
                "approvalEvidence": {
                    "approvalObservation": thread["approvalObservation"],
                    "approvalGuardSha256": thread["approvalGuardSha256"],
                    "approvalPolicy": thread["approvalPolicy"],
                    "approvalVerificationMethod": thread[
                        "approvalVerificationMethod"
                    ],
                    "approvalsReviewer": thread["approvalsReviewer"],
                    "challengeSha256": challenge_sha,
                    "commandSha256": thread["commandSha256"]["approval"],
                    "controllerThreadBinding": thread["controllerThreadBinding"],
                    "controllerThreadProjectId": thread[
                        "controllerThreadProjectId"
                    ],
                    "environmentId": thread["environmentId"],
                    "historicalVerificationMethod": thread[
                        "historicalVerificationMethod"
                    ],
                    "itemId": thread["approvalItemId"],
                    "nativeProjectId": thread["nativeProjectId"],
                    "networkAccess": thread["networkAccess"],
                    "proofCommandSha256": thread["commandSha256"]["proof"],
                    "proofItemId": thread["proofItemId"],
                    "projectRoot": thread["projectRoot"],
                    "runtimeWorkspaceRoots": thread["runtimeWorkspaceRoots"],
                    "sandboxType": thread["sandboxType"],
                    "threadId": thread["threadId"],
                    "turnId": thread["turnId"],
                    "verifiedAt": thread["verifiedAt"],
                },
                "phoneThreadEvidence": {
                    **thread,
                    "challengeSha256": challenge_sha,
                    "proofSha256": proof_sha,
                },
                "safeToCloseEvidence": {
                    "autoStopRemainingSeconds": 7200,
                    "baselineCommit": "baseline",
                    "challengeSha256": challenge_sha,
                    "checkpointCommit": checkpoint_commit,
                    "checkpointTree": checkpoint_tree,
                    "environmentId": "env_test",
                    "instanceId": "i-0123456789abcdef0",
                    "nativeProjectId": "01a-project",
                    "projectRoot": spike.REMOTE_WORKSPACE,
                    "proofSha256": proof_sha,
                    "proofSource": challenge["proofSource"],
                    "restoreTest": restore_test,
                    "runId": "p0-test",
                    "s3ManifestVersionId": "manifest-version",
                    "s3VersionId": "bundle-version",
                    "verifiedAt": "2026-09-01T20:10:00+00:00",
                    "workspaceVolumeId": "vol-0123456789abcdef0",
                },
            }
        )
        return state

    def runner_status(self) -> dict:
        return {
            "active": True,
            "healthy": True,
            "ready": True,
            "health": {"fresh": True, "healthy": True, "ready": True},
        }

    def remote_status(self) -> dict:
        return {
            "status": "connected",
            "controllerPresent": True,
            "controllerProjectVisibility": {
                "status": "unknown",
                "verified": False,
            },
            "environmentId": "env_test",
            "nativeProjectId": "01a-project",
            "projectRoot": spike.REMOTE_WORKSPACE,
            "serverProjectRegistered": True,
            "workspace": spike.REMOTE_WORKSPACE,
        }

    def connector_status(self) -> dict:
        return {
            "readyForPhoneProof": True,
            "serverProjectRegistered": True,
            "controllerProjectVisibility": {
                "status": "unknown",
                "verified": False,
            },
            "workspace": spike.REMOTE_WORKSPACE,
            "daemon": {
                "managedCodexVersion": "0.152.1",
                "cliVersion": "0.152.1",
                "appServerVersion": "0.152.1",
                "socketPath": "/home/lift/.codex/app-server-control/app-server-control.sock",
            },
            "remote": {
                "status": "connected",
                "environmentId": "env_test",
                "controllerPresent": True,
                "pairedClientCount": 1,
                "serverName": "lift-cloud",
            },
            "project": {
                "id": "01a-project",
                "root": spike.REMOTE_WORKSPACE,
                "trusted": True,
            },
        }

    def test_managed_status_is_read_only_and_requires_exact_native_project(self) -> None:
        raw = json.dumps(self.connector_status())
        with mock.patch.object(spike, "send_command", return_value=raw) as send:
            status = spike.managed_remote_status("i-test", spike.REMOTE_WORKSPACE)

        commands = send.call_args.args[1]
        self.assertIn("codex_project.py status --name lift", commands[-1])
        self.assertNotIn("remote-control start", commands[-1])
        self.assertTrue(status["serverProjectRegistered"])
        self.assertEqual(
            {"status": "unknown", "verified": False},
            status["controllerProjectVisibility"],
        )
        self.assertNotIn("nativeProjectRegistered", status)
        self.assertEqual("01a-project", status["nativeProjectId"])

        invalid = self.connector_status()
        invalid["project"]["root"] = "/home/lift/Documents/Codex/projectless"
        with mock.patch.object(spike, "send_command", return_value=json.dumps(invalid)):
            with self.assertRaisesRegex(spike.SpikeError, "projectRoot"):
                spike.managed_remote_status("i-test", spike.REMOTE_WORKSPACE)

        falsely_visible = self.connector_status()
        falsely_visible["controllerProjectVisibility"] = {
            "status": "verified",
            "verified": True,
        }
        with mock.patch.object(
            spike, "send_command", return_value=json.dumps(falsely_visible)
        ):
            with self.assertRaisesRegex(
                spike.SpikeError, "controllerProjectVisibility"
            ):
                spike.managed_remote_status("i-test", spike.REMOTE_WORKSPACE)

    def test_thread_baseline_is_exact_bounded_and_read_only(self) -> None:
        baseline = self.thread_baseline()
        with mock.patch.object(
            spike, "send_command", return_value=json.dumps(baseline)
        ) as send:
            observed = spike.managed_thread_baseline(
                "i-0123456789abcdef0", spike.REMOTE_WORKSPACE
            )

        self.assertEqual(baseline, observed)
        command = send.call_args.args[1][-1]
        self.assertIn("thread-baseline --name lift", command)
        self.assertNotIn("remote-control start", command)

        oversized = self.thread_baseline()
        oversized["threadIds"] = [
            f"thread-{index:03d}"
            for index in range(spike.MAX_BASELINE_THREAD_IDS + 1)
        ]
        with mock.patch.object(
            spike, "send_command", return_value=json.dumps(oversized)
        ):
            with self.assertRaisesRegex(spike.SpikeError, "malformed or too large"):
                spike.managed_thread_baseline(
                    "i-0123456789abcdef0", spike.REMOTE_WORKSPACE
                )

    def test_thread_verification_binds_fresh_task_and_native_approval(self) -> None:
        challenge = self.phone_challenge()
        historical = self.thread_evidence(combined=False)
        observation = self.approval_observation(challenge, historical)
        with (
            mock.patch.object(
                spike, "send_command", return_value=json.dumps(historical)
            ) as send,
            mock.patch.object(
                spike,
                "managed_approval_observer_evidence",
                return_value=observation,
            ),
        ):
            observed = spike.managed_thread_verification(
                "i-0123456789abcdef0", spike.REMOTE_WORKSPACE, challenge
            )

        expected = copy.deepcopy(historical)
        expected["historicalVerificationMethod"] = spike.THREAD_VERIFICATION_METHOD
        expected["approvalVerificationMethod"] = spike.APPROVAL_VERIFICATION_METHOD
        expected["approvalObservation"] = observation
        self.assertEqual(expected, observed)
        command = send.call_args.args[1][-1]
        self.assertIn("verify-thread", command)
        self.assertIn("--baseline-thread-id thread-a", command)
        self.assertIn("--baseline-thread-id thread-z", command)
        self.assertIn("--approval-nonce " + "b" * 32, command)
        self.assertIn("--approval-guard-sha256 " + "e" * 64, command)

        mutations = {
            "network": lambda value: value.update(networkAccess=True),
            "guard": lambda value: value.update(approvalGuardSha256="f" * 64),
            "method": lambda value: value.update(
                approvalVerificationMethod="completed-command-only"
            ),
            "policy": lambda value: value.update(approvalPolicy="untrusted"),
        }
        for description, mutate in mutations.items():
            with self.subTest(description=description):
                unsafe = self.thread_evidence(combined=False)
                mutate(unsafe)
                with mock.patch.object(
                    spike, "send_command", return_value=json.dumps(unsafe)
                ):
                    with self.assertRaisesRegex(spike.SpikeError, "unbound evidence"):
                        spike.managed_thread_verification(
                            "i-0123456789abcdef0", spike.REMOTE_WORKSPACE, challenge
                        )

    def test_phone_prompt_requires_new_task_two_calls_and_user_approval(self) -> None:
        prompt = spike.phone_challenge_prompt(
            {"serverName": "lift-cloud"}, self.phone_challenge(), restart=True
        )

        self.assertIn("create a brand-new task", prompt)
        self.assertIn("choose Add new folder", prompt)
        self.assertIn(spike.REMOTE_WORKSPACE, prompt)
        self.assertIn("controller-side project visibility has not been verified", prompt)
        self.assertNotIn("native project named lift", prompt)
        self.assertIn("two separate terminal calls", prompt)
        self.assertIn("request escalated permission", prompt)
        self.assertIn("LIFT_APPROVAL_CANARY=" + "b" * 32, prompt)
        self.assertIn("/usr/bin/curl", prompt)
        self.assertIn(".lift/post-restart-proof.json", prompt)
        self.assertLess(
            prompt.index("/usr/bin/curl"),
            prompt.index(".lift/post-restart-proof.json"),
        )
        self.assertIn("run any other terminal command", prompt)

    def test_post_restart_arm_and_verify_are_thread_and_approval_bound(self) -> None:
        state = {
            "schemaVersion": 1,
            "revision": 10,
            "runId": "p0-test",
            "runtime": {
                "outputs": {
                    "InstanceId": "i-0123456789abcdef0",
                    "WorkspaceVolumeId": "vol-0123456789abcdef0",
                }
            },
            "workspace": {
                "lease": "CLOUD_PRIMARY",
                "cloudPath": spike.REMOTE_WORKSPACE,
            },
            "connection": {"state": "RESTART_RECOVERED_AWAITING_PHONE"},
            "readiness": {
                "restartEvidence": {
                    "runnerHealthy": True,
                    "environmentPreserved": True,
                    "environmentIdAfter": "env_test",
                },
                "safeToClose": True,
            },
        }
        remote = self.remote_status() | {"serverName": "lift-cloud"}
        baseline = self.thread_baseline()
        output = io.StringIO()
        with (
            mock.patch.object(spike, "load_state", return_value=state),
            mock.patch.object(spike, "assert_identity"),
            mock.patch.object(
                spike,
                "validated_stack_context",
                return_value=state["runtime"]["outputs"],
            ),
            mock.patch.object(
                spike, "managed_runner_status", return_value=self.runner_status()
            ),
            mock.patch.object(spike, "managed_remote_status", return_value=remote),
            mock.patch.object(
                spike, "managed_thread_baseline", return_value=baseline
            ),
            mock.patch.object(
                spike,
                "managed_approval_observer_arm",
                return_value={"observer": "ready"},
            ),
            mock.patch.object(
                spike.secrets,
                "token_hex",
                side_effect=["a" * 32, "b" * 32],
            ),
            mock.patch.object(spike, "atomic_state"),
            mock.patch.object(spike, "record_event"),
            contextlib.redirect_stdout(output),
        ):
            spike.cmd_readiness(mock.Mock(action="arm-restart"))

        challenge = state["readiness"]["postRestartChallenge"]
        self.assertEqual(challenge, state["readiness"]["challenge"])
        self.assertIsNot(challenge, state["readiness"]["challenge"])
        self.assertEqual(
            spike.phone_challenge_sha256(challenge),
            state["readiness"]["activeChallengeSha256"],
        )
        self.assertEqual(baseline, challenge["threadBaseline"])
        self.assertEqual("b" * 32, challenge["approvalNonce"])
        self.assertFalse(state["readiness"]["safeToClose"])
        self.assertFalse(state["readiness"]["approvalRoundTripVerified"])
        self.assertIn("create a brand-new task", json.loads(output.getvalue())["phonePrompt"])

        output = io.StringIO()
        evidence = self.thread_evidence()
        with (
            mock.patch.object(spike, "load_state", return_value=state),
            mock.patch.object(spike, "assert_identity"),
            mock.patch.object(
                spike,
                "validated_stack_context",
                return_value=state["runtime"]["outputs"],
            ),
            mock.patch.object(
                spike, "managed_runner_status", return_value=self.runner_status()
            ),
            mock.patch.object(spike, "managed_remote_status", return_value=remote),
            mock.patch.object(
                spike,
                "verify_workspace_json_proof",
                return_value={"cwd": spike.REMOTE_WORKSPACE},
            ),
            mock.patch.object(
                spike, "managed_thread_verification", return_value=evidence
            ) as verify_thread,
            mock.patch.object(spike, "atomic_state"),
            mock.patch.object(spike, "record_event"),
            contextlib.redirect_stdout(output),
        ):
            spike.cmd_readiness(mock.Mock(action="verify-restart"))

        verify_thread.assert_called_once_with(
            "i-0123456789abcdef0", spike.REMOTE_WORKSPACE, challenge
        )
        self.assertTrue(state["readiness"]["providerPhoneProbeVerified"])
        self.assertTrue(state["readiness"]["approvalRoundTripVerified"])
        self.assertEqual("thread-new", state["readiness"]["approvalEvidence"]["threadId"])
        self.assertEqual(
            "approval-item", state["readiness"]["approvalEvidence"]["itemId"]
        )
        self.assertEqual(
            "POST_RESTART_PHONE_AND_APPROVAL_VERIFIED_AWAITING_CHECKPOINT",
            state["connection"]["state"],
        )
        observed = json.loads(output.getvalue())
        self.assertTrue(observed["approvalRoundTripVerified"])
        self.assertFalse(observed["safeToClose"])

    def test_version_three_proof_binds_environment_and_native_project(self) -> None:
        challenge = self.phone_challenge()

        proof = json.loads(spike.proof_bytes(challenge, "codex-phone-post-restart"))

        self.assertEqual("env_test", proof["environmentId"])
        self.assertEqual("01a-project", proof["nativeProjectId"])
        self.assertEqual(spike.REMOTE_WORKSPACE, proof["projectRoot"])

    def test_post_restart_checkpoint_plan_keeps_exact_proof_source(self) -> None:
        readiness = self.safe_state()["readiness"]

        plan = spike.checkpoint_evidence_plan(readiness, "phone")

        self.assertEqual("codex-phone-post-restart", plan["proofSource"])
        self.assertEqual("post-restart-phone-proof", plan["label"])
        self.assertEqual(
            spike.proof_bytes(
                readiness["challenge"], "codex-phone-post-restart"
            ),
            plan["expectedEvidence"][".lift/post-restart-proof.json"],
        )

    def test_stale_post_restart_alias_cannot_authorize_current_challenge(self) -> None:
        stale = self.phone_challenge()
        current = copy.deepcopy(stale)
        current["nonce"] = "e" * 32
        current["approvalNonce"] = "f" * 32
        readiness = {
            "challenge": current,
            "activeChallengeSha256": spike.phone_challenge_sha256(current),
            "postRestartChallenge": stale,
        }

        with self.assertRaisesRegex(spike.SpikeError, "stale or ambiguous"):
            spike.active_phone_challenge(
                readiness,
                expected_source="codex-phone-post-restart",
                require_post_restart_alias=True,
            )

    def test_approval_policy_schema_matches_connector(self) -> None:
        valid = {
            "granular": {
                "mcp_elicitations": False,
                "rules": True,
                "sandbox_approval": True,
                "skill_approval": False,
            }
        }
        self.assertTrue(spike.valid_approval_policy(valid))
        for invalid in (
            {"granular": {"sandbox_approval": True}},
            {
                "granular": {
                    "mcp_elicitations": False,
                    "rules": True,
                    "sandbox_approval": True,
                    "unknown": False,
                }
            },
            "never",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(spike.valid_approval_policy(invalid))

    def test_workspace_proof_uses_physical_dirfd_walk_and_exact_fixed_path(self) -> None:
        challenge = self.phone_challenge()
        expected = spike.proof_bytes(challenge, "codex-phone-post-restart")
        observed = {
            "dataHex": expected.hex(),
            "path": (
                spike.REMOTE_WORKSPACE + "/.lift/post-restart-proof.json"
            ),
            "resolvedWorkspace": spike.REMOTE_WORKSPACE,
        }
        with mock.patch.object(
            spike, "send_command", return_value=json.dumps(observed)
        ) as send:
            proof = spike.verify_workspace_json_proof(
                instance_id="i-0123456789abcdef0",
                workspace=spike.REMOTE_WORKSPACE,
                challenge=challenge,
                source="codex-phone-post-restart",
                description="post-restart phone",
            )

        self.assertEqual(json.loads(expected), proof)
        remote_command = send.call_args.args[1][-1]
        self.assertIn("O_NOFOLLOW", remote_command)
        self.assertIn("relative.parts[:-1]", remote_command)
        self.assertNotIn("cat /home/lift", remote_command)

        unsafe = copy.deepcopy(challenge)
        unsafe["proofRelativePath"] = ".lift/other.json"
        with mock.patch.object(spike, "send_command") as send:
            with self.assertRaisesRegex(spike.SpikeError, "proof path is unsafe"):
                spike.verify_workspace_json_proof(
                    instance_id="i-0123456789abcdef0",
                    workspace=spike.REMOTE_WORKSPACE,
                    challenge=unsafe,
                    source="codex-phone-post-restart",
                    description="post-restart phone",
                )
            send.assert_not_called()

    def test_parser_supports_post_restart_verification(self) -> None:
        args = spike.build_parser().parse_args(["readiness", "verify-restart"])

        self.assertEqual("verify-restart", args.action)
        self.assertIs(args.handler, spike.cmd_readiness)

    def test_safe_to_close_requires_bound_approval_round_trip(self) -> None:
        state = self.safe_state()
        self.assertTrue(spike.safe_to_close(state))

        state["readiness"]["approvalRoundTripVerified"] = False
        self.assertFalse(spike.safe_to_close(state))
        state["readiness"]["approvalRoundTripVerified"] = True
        state["readiness"]["approvalEvidence"]["nativeProjectId"] = "wrong"
        self.assertFalse(spike.safe_to_close(state))

    def test_safe_to_close_rejects_tampered_challenge_evidence(self) -> None:
        mutations = {
            "active digest": lambda readiness: readiness.update(
                activeChallengeSha256="0" * 64
            ),
            "proof digest": lambda readiness: readiness[
                "phoneThreadEvidence"
            ].update(proofSha256="0" * 64),
            "approval policy": lambda readiness: readiness[
                "approvalEvidence"
            ].update(approvalPolicy="never"),
            "approval guard": lambda readiness: readiness[
                "approvalEvidence"
            ].update(approvalGuardSha256="f" * 64),
            "approval method": lambda readiness: readiness[
                "phoneThreadEvidence"
            ].update(approvalVerificationMethod="completed-command-only"),
            "checkpoint binding": lambda readiness: readiness[
                "safeToCloseEvidence"
            ].update(challengeSha256="0" * 64),
            "legacy evidence shape": lambda readiness: readiness[
                "approvalEvidence"
            ].update(unexpected=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                state = self.safe_state()
                mutate(state["readiness"])
                self.assertFalse(spike.safe_to_close(state))

    def test_safe_to_close_requires_exact_restore_and_versioned_checkpoint(self) -> None:
        mutations = {
            "negative timer": lambda state: state["readiness"][
                "safeToCloseEvidence"
            ].update(autoStopRemainingSeconds=-1),
            "short timer": lambda state: state["readiness"][
                "safeToCloseEvidence"
            ].update(autoStopRemainingSeconds=3599),
            "boolean timer": lambda state: state["readiness"][
                "safeToCloseEvidence"
            ].update(autoStopRemainingSeconds=True),
            "empty bundle version": lambda state: state["readiness"][
                "safeToCloseEvidence"
            ].update(s3VersionId=""),
            "blank manifest version": lambda state: state["workspace"][
                "checkpoints"
            ][-1].update(s3ManifestVersionId=" "),
            "missing checkpoint restore": lambda state: state["workspace"][
                "checkpoints"
            ][-1].pop("restoreTest"),
            "empty restore": lambda state: (
                state["workspace"]["checkpoints"][-1].update(restoreTest={}),
                state["readiness"]["safeToCloseEvidence"].update(restoreTest={}),
            ),
            "invalid restore hash": lambda state: state["workspace"][
                "checkpoints"
            ][-1]["restoreTest"].update(bundleLocalSha256="not-a-sha"),
            "restore commit mismatch": lambda state: state["workspace"][
                "checkpoints"
            ][-1]["restoreTest"].update(restoredCommit="f" * 40),
            "safe restore differs from latest": lambda state: state["readiness"][
                "safeToCloseEvidence"
            ].update(
                restoreTest={
                    **state["readiness"]["safeToCloseEvidence"]["restoreTest"],
                    "verifiedAt": "2026-09-01T20:09:01+00:00",
                }
            ),
            "checkpoint commit differs": lambda state: state["workspace"][
                "checkpoints"
            ][-1].update(commit="e" * 40),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                state = self.safe_state()
                mutate(state)
                self.assertFalse(spike.safe_to_close(state))

    def test_invalidation_resets_approval_evidence(self) -> None:
        state = self.safe_state()

        spike.invalidate_safe_to_close(
            state, reset_phone_probe=False, reset_workload=True
        )

        self.assertFalse(state["readiness"]["approvalRoundTripVerified"])
        self.assertNotIn("approvalEvidence", state["readiness"])
        self.assertNotIn("activeChallengeSha256", state["readiness"])
        self.assertNotIn("postRestartChallenge", state["readiness"])

    def test_live_safe_to_close_requires_fresh_exact_runner_and_remote(self) -> None:
        state = self.safe_state()
        runner = self.runner_status()
        remote = self.remote_status()
        self.assertTrue(spike.live_safe_to_close(state, runner, remote, 7200))

        mutations = [
            ("runner.active", lambda: runner.update(active=False)),
            ("runner.ready", lambda: runner.update(ready=False)),
            ("health.fresh", lambda: runner["health"].update(fresh=False)),
            ("remote.controller", lambda: remote.update(controllerPresent=False)),
            ("remote.environment", lambda: remote.update(environmentId="other")),
            ("remote.project", lambda: remote.update(nativeProjectId="other")),
            ("remote.root", lambda: remote.update(projectRoot="/wrong")),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                runner = self.runner_status()
                remote = self.remote_status()
                mutate()
                self.assertFalse(spike.live_safe_to_close(state, runner, remote, 7200))

        for remaining in (-1, 0, 3599, True):
            with self.subTest(auto_stop_remaining_seconds=remaining):
                self.assertFalse(
                    spike.live_safe_to_close(
                        state,
                        self.runner_status(),
                        self.remote_status(),
                        remaining,
                    )
                )

    def test_managed_auto_stop_reads_live_timer_without_trusting_cached_value(self) -> None:
        with mock.patch.object(spike, "send_command", return_value="3599") as send:
            self.assertEqual(
                3599,
                spike.managed_auto_stop_remaining_seconds(
                    "i-0123456789abcdef0"
                ),
            )

        commands = send.call_args.args[1]
        self.assertIn("systemctl is-active --quiet lift-spike-autostop.timer", commands)
        self.assertTrue(any("NextElapseUSecMonotonic" in command for command in commands))
        self.assertFalse(any('test "$REMAINING" -ge' in command for command in commands))

        for raw in ("", "not-a-duration"):
            with self.subTest(raw=raw), mock.patch.object(
                spike, "send_command", return_value=raw
            ):
                with self.assertRaisesRegex(spike.SpikeError, "did not return a duration"):
                    spike.managed_auto_stop_remaining_seconds(
                        "i-0123456789abcdef0"
                    )

    def test_status_rechecks_live_auto_stop_window(self) -> None:
        state = self.safe_state()
        state["readiness"]["safeToClose"] = True

        def aws_response(service: str, operation: str, *args: str) -> dict:
            if service == "ec2":
                return {"Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]}
            if service == "ssm":
                return {"InstanceInformationList": [{"PingStatus": "Online"}]}
            raise AssertionError((service, operation, args))

        output = io.StringIO()
        with (
            mock.patch.object(spike, "load_state", return_value=state),
            mock.patch.object(spike, "assert_identity"),
            mock.patch.object(
                spike,
                "validated_stack_context",
                return_value=state["runtime"]["outputs"],
            ),
            mock.patch.object(spike, "aws_json", side_effect=aws_response),
            mock.patch.object(spike, "send_command", return_value='{"status":"ready"}'),
            mock.patch.object(
                spike, "managed_runner_status", return_value=self.runner_status()
            ),
            mock.patch.object(
                spike, "managed_remote_status", return_value=self.remote_status()
            ),
            mock.patch.object(
                spike, "managed_auto_stop_remaining_seconds", return_value=3599
            ) as timer,
            contextlib.redirect_stdout(output),
        ):
            spike.cmd_status(mock.Mock())

        observed = json.loads(output.getvalue())
        timer.assert_called_once_with("i-0123456789abcdef0")
        self.assertEqual(3599, observed["autoStopRemainingSeconds"])
        self.assertFalse(observed["liveReadiness"]["safeToClose"])

    def test_status_revalidates_without_mutating_persisted_state(self) -> None:
        state = self.safe_state()
        state["readiness"]["safeToClose"] = True
        before = copy.deepcopy(state)

        def aws_response(service: str, operation: str, *args: str) -> dict:
            if service == "ec2":
                return {"Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]}
            if service == "ssm":
                return {"InstanceInformationList": [{"PingStatus": "Online"}]}
            raise AssertionError((service, operation, args))

        output = io.StringIO()
        with (
            mock.patch.object(spike, "load_state", return_value=state),
            mock.patch.object(spike, "assert_identity"),
            mock.patch.object(
                spike,
                "validated_stack_context",
                return_value=state["runtime"]["outputs"],
            ),
            mock.patch.object(spike, "aws_json", side_effect=aws_response),
            mock.patch.object(spike, "send_command", return_value='{"status":"ready"}'),
            mock.patch.object(
                spike, "managed_runner_status", return_value=self.runner_status()
            ),
            mock.patch.object(
                spike,
                "managed_remote_status",
                side_effect=spike.SpikeError("controller disconnected"),
            ),
            contextlib.redirect_stdout(output),
        ):
            spike.cmd_status(mock.Mock())

        observed = json.loads(output.getvalue())
        self.assertFalse(observed["liveReadiness"]["safeToClose"])
        self.assertTrue(observed["persistedSafeToCloseCache"])
        self.assertEqual(before, state)


if __name__ == "__main__":
    unittest.main()
