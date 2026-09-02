from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
GUEST_ROOT = SPIKE_ROOT / "guest"
sys.path.insert(0, str(GUEST_ROOT))

import runner  # noqa: E402


class DetachedRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-runner-test-")
        self.root = Path(self.temporary.name).resolve()
        self.recipe_root = self.root / "recipes"
        self.recipe_root.mkdir()
        self.workspace_root = self.root / "workspaces"
        self.workspace = self.workspace_root / "example"
        self.workspace.mkdir(parents=True)
        self.persistent = self.root / "agent-state"
        self.persistent.mkdir()
        self.executable = self.root / "generic-agent"
        self.executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.executable.chmod(0o755)
        self.recipe_path = self.recipe_root / "generic.json"
        self.recipe = {
            "schemaVersion": 1,
            "id": "generic-remote",
            "processMode": "detached",
            "run": {
                "executable": str(self.executable),
                "arguments": ["start"],
                "timeoutSeconds": 10,
            },
            "health": {
                "executable": str(self.executable),
                "arguments": ["health"],
                "timeoutSeconds": 5,
                "intervalSeconds": 5,
                "failureThreshold": 2,
            },
            "stop": {
                "executable": str(self.executable),
                "arguments": ["stop"],
                "timeoutSeconds": 5,
            },
            "persistentPaths": [str(self.persistent)],
            "networkPolicy": {"outbound": "internet", "metadataAccess": False},
            "restartPolicy": "on-failure",
        }
        self.recipe_path.write_text(json.dumps(self.recipe), encoding="utf-8")
        self.patchers = [
            mock.patch.object(runner, "RECIPE_ROOT", self.recipe_root),
            mock.patch.object(runner, "WORKSPACE_ROOT", self.workspace_root),
            mock.patch.object(
                runner,
                "APPROVED_PERSISTENT_PATHS",
                frozenset({str(self.persistent)}),
            ),
            mock.patch.object(runner, "HEALTH_PATH", self.root / "run" / "health.json"),
            mock.patch.object(runner, "STATE_PATH", self.root / "runner-state.json"),
            mock.patch.object(runner, "UNIT_PATH", self.root / "lift-workload.service"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def test_detached_recipe_requires_generic_run_health_and_stop_specs(self) -> None:
        validated = runner.validated_recipe(self.recipe_path)
        self.assertEqual("detached", validated["processMode"])

        del self.recipe["stop"]
        self.recipe_path.write_text(json.dumps(self.recipe), encoding="utf-8")
        with self.assertRaisesRegex(runner.RunnerError, "stop must be an object"):
            runner.validated_recipe(self.recipe_path)

    def test_optional_prepare_process_is_validated(self) -> None:
        self.recipe["prepare"] = {
            "executable": str(self.executable),
            "arguments": ["prepare"],
            "timeoutSeconds": 5,
        }
        self.recipe_path.write_text(json.dumps(self.recipe), encoding="utf-8")

        validated = runner.validated_recipe(self.recipe_path)

        self.assertEqual(["prepare"], validated["prepare"]["arguments"])

    def test_process_environment_binds_the_exact_workspace(self) -> None:
        environment = runner.process_environment(self.workspace)

        self.assertEqual(str(self.workspace), environment["LIFT_WORKSPACE"])
        self.assertEqual("/home/lift", environment["HOME"])

    def test_unit_is_reboot_enabled_and_mount_bound_without_provider_logic(self) -> None:
        unit = runner.unit_text(self.recipe_path, self.workspace, self.recipe)

        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn(
            "ExecCondition=+/usr/bin/python3 /opt/lift-spike/runner.py gate "
            f"--workspace {self.workspace}",
            unit,
        )
        self.assertIn("RuntimeDirectory=lift-spike-runner", unit)
        self.assertIn(
            (
                f"RequiresMountsFor={self.workspace} {self.persistent} "
                f"{runner.landing.LEDGER_ROOT}"
            ),
            unit,
        )
        self.assertIn(f"WorkingDirectory={self.workspace}", unit)
        self.assertIn(f"ReadWritePaths={self.workspace} {self.persistent}", unit)
        self.assertNotIn(f'WorkingDirectory="{self.workspace}"', unit)
        self.assertNotIn("codex", unit.lower())
        self.assertNotIn("/home/lift/Documents", unit)
        self.assertNotIn("ReadWritePaths=/home/lift ", unit)
        self.assertNotIn("ReadWritePaths=/ ", unit)

    def test_start_holds_lifecycle_lock_through_systemd_activation(self) -> None:
        self.recipe["processMode"] = "foreground"
        self.recipe_path.write_text(json.dumps(self.recipe), encoding="utf-8")
        events: list[str] = []
        lock_held = False

        @contextlib.contextmanager
        def lifecycle_lock(workspace: Path):
            nonlocal lock_held
            self.assertEqual(self.workspace, workspace)
            lock_held = True
            events.append("lock-enter")
            try:
                yield
            finally:
                events.append("lock-exit")
                lock_held = False

        def require_cloud_primary(workspace: Path, *, allow_legacy_missing: bool):
            self.assertTrue(lock_held)
            self.assertEqual(self.workspace, workspace)
            self.assertTrue(allow_legacy_missing)
            events.append("lease")

        def fake_systemctl(*arguments: str, check: bool = True):
            self.assertTrue(lock_held)
            events.append("systemctl:" + " ".join(arguments))
            if arguments[0] == "is-active":
                return subprocess.CompletedProcess([], 0, "", "")
            if "--value" in arguments:
                return subprocess.CompletedProcess([], 0, "123\n", "")
            return subprocess.CompletedProcess([], 0, "", "")

        with (
            mock.patch.object(runner.os, "geteuid", return_value=0),
            mock.patch.object(runner.landing, "lifecycle_lock", lifecycle_lock),
            mock.patch.object(
                runner.landing,
                "require_cloud_primary",
                side_effect=require_cloud_primary,
            ),
            mock.patch.object(runner, "systemctl", side_effect=fake_systemctl),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.cmd_start(
                    mock.Mock(recipe=str(self.recipe_path), workspace=str(self.workspace))
                )

        self.assertLess(events.index("lock-enter"), events.index("lease"))
        self.assertLess(events.index("lease"), events.index("systemctl:enable --now lift-workload.service"))
        self.assertLess(events.index("systemctl:enable --now lift-workload.service"), events.index("lock-exit"))
        self.assertTrue(runner.STATE_PATH.is_file())
        self.assertIn("ExecCondition=+", runner.UNIT_PATH.read_text(encoding="utf-8"))

    def test_start_rejects_non_cloud_lease_before_any_lifecycle_mutation(self) -> None:
        @contextlib.contextmanager
        def lifecycle_lock(_: Path):
            yield

        with (
            mock.patch.object(runner.os, "geteuid", return_value=0),
            mock.patch.object(runner.landing, "lifecycle_lock", lifecycle_lock),
            mock.patch.object(
                runner.landing,
                "require_cloud_primary",
                side_effect=runner.landing.LandingError("lease is LANDING"),
            ) as require,
            mock.patch.object(runner, "systemctl") as systemctl,
        ):
            with self.assertRaisesRegex(runner.RunnerError, "rejected start"):
                runner.cmd_start(
                    mock.Mock(recipe=str(self.recipe_path), workspace=str(self.workspace))
                )

        require.assert_called_once_with(self.workspace, allow_legacy_missing=True)
        systemctl.assert_not_called()
        self.assertFalse(runner.STATE_PATH.exists())
        self.assertFalse(runner.UNIT_PATH.exists())

    def test_systemd_gate_is_strict_and_does_not_accept_missing_legacy_marker(self) -> None:
        with (
            mock.patch.object(runner.os, "geteuid", return_value=0),
            mock.patch.object(runner.landing, "require_cloud_primary") as require,
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.cmd_gate(mock.Mock(workspace=str(self.workspace)))

        require.assert_called_once_with(self.workspace, allow_legacy_missing=False)
        self.assertEqual("CLOUD_PRIMARY", json.loads(output.getvalue())["lease"])

    def test_active_legacy_unit_is_retrofitted_without_restarting_workload(self) -> None:
        self.recipe["processMode"] = "foreground"
        self.recipe_path.write_text(json.dumps(self.recipe), encoding="utf-8")
        runner.atomic_json(
            runner.STATE_PATH,
            {
                "processMode": "foreground",
                "readinessConfigured": False,
                "recipeId": self.recipe["id"],
                "recipePath": str(self.recipe_path),
                "recipeSha256": runner.recipe_hash(self.recipe_path),
                "workspace": str(self.workspace),
            },
        )
        runner.UNIT_PATH.write_text("legacy unit without a lease gate\n", encoding="utf-8")
        calls: list[tuple[str, ...]] = []

        @contextlib.contextmanager
        def lifecycle_lock(_: Path):
            yield

        def fake_systemctl(*arguments: str, check: bool = True):
            calls.append(arguments)
            if arguments[0] == "is-active":
                return subprocess.CompletedProcess([], 0, "", "")
            if "--value" in arguments:
                return subprocess.CompletedProcess([], 0, "123\n", "")
            return subprocess.CompletedProcess([], 0, "", "")

        with (
            mock.patch.object(runner.os, "geteuid", return_value=0),
            mock.patch.object(runner.landing, "lifecycle_lock", lifecycle_lock),
            mock.patch.object(runner.landing, "require_cloud_primary"),
            mock.patch.object(runner, "systemctl", side_effect=fake_systemctl),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.cmd_start(
                    mock.Mock(recipe=str(self.recipe_path), workspace=str(self.workspace))
                )

        self.assertIn(("daemon-reload",), calls)
        self.assertIn(("enable", runner.UNIT_NAME), calls)
        self.assertNotIn(("enable", "--now", runner.UNIT_NAME), calls)
        self.assertIn("ExecCondition=+", runner.UNIT_PATH.read_text(encoding="utf-8"))
        self.assertTrue(json.loads(output.getvalue())["changed"])

    def test_detached_supervisor_runs_start_health_and_stop(self) -> None:
        stop_event = threading.Event()
        phases: list[str] = []

        def invoke(_: dict, name: str, __: Path) -> None:
            phases.append(name)
            if name == "health":
                stop_event.set()

        with mock.patch.object(runner, "invoke_process", side_effect=invoke):
            runner.supervise_detached(
                self.recipe_path, self.recipe, self.workspace, stop_event
            )

        self.assertEqual(["run", "health", "stop"], phases)
        health = json.loads(runner.HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertTrue(health["healthy"])
        self.assertEqual("generic-remote", health["recipeId"])

    def test_detached_supervisor_prepares_after_start_before_health(self) -> None:
        self.recipe["prepare"] = {
            "executable": str(self.executable),
            "arguments": ["prepare"],
            "timeoutSeconds": 5,
        }
        stop_event = threading.Event()
        phases: list[str] = []

        def invoke(_: dict, name: str, __: Path) -> None:
            phases.append(name)
            if name == "health":
                stop_event.set()

        with mock.patch.object(runner, "invoke_process", side_effect=invoke):
            runner.supervise_detached(
                self.recipe_path, self.recipe, self.workspace, stop_event
            )

        self.assertEqual(["run", "prepare", "health", "stop"], phases)

    def test_readiness_failure_degrades_without_restarting_healthy_process(self) -> None:
        self.recipe["readiness"] = {
            "executable": str(self.executable),
            "arguments": ["readiness"],
            "timeoutSeconds": 5,
        }
        stop_event = threading.Event()
        phases: list[str] = []

        def invoke(_: dict, name: str, __: Path) -> None:
            phases.append(name)
            if name == "readiness":
                stop_event.set()
                raise runner.RunnerError("native workspace registration is missing")

        with mock.patch.object(runner, "invoke_process", side_effect=invoke):
            runner.supervise_detached(
                self.recipe_path, self.recipe, self.workspace, stop_event
            )

        self.assertEqual(["run", "health", "readiness", "stop"], phases)
        health = json.loads(runner.HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertTrue(health["healthy"])
        self.assertFalse(health["ready"])
        self.assertEqual(0, health["consecutiveFailures"])
        self.assertIn("registration is missing", health["readinessError"])

    def test_json_assertion_rejects_successful_process_with_wrong_state(self) -> None:
        self.executable.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"status\":\"stopped\"}'\n",
            encoding="utf-8",
        )
        process = {
            "executable": str(self.executable),
            "arguments": [],
            "timeoutSeconds": 5,
            "jsonEquals": {"/status": "running"},
        }
        with self.assertRaisesRegex(
            runner.RunnerError, "JSON assertion failed at /status"
        ):
            runner.invoke_process({"health": process}, "health", self.workspace)

    def test_json_nonempty_assertion_accepts_environment_identity(self) -> None:
        process = {"jsonNonEmpty": ["/environmentId"]}
        runner.assert_process_output(
            process,
            "run",
            b'{"environmentId":"env_example"}\n',
        )
        with self.assertRaisesRegex(runner.RunnerError, "nonempty assertion"):
            runner.assert_process_output(
                process,
                "run",
                b'{"environmentId":""}\n',
            )

    def test_repeated_health_failure_stops_and_fails_for_systemd_restart(self) -> None:
        phases: list[str] = []

        class ImmediateEvent:
            @staticmethod
            def is_set() -> bool:
                return False

            @staticmethod
            def wait(_: float) -> bool:
                return False

        def invoke(_: dict, name: str, __: Path) -> None:
            phases.append(name)
            if name == "health":
                raise runner.RunnerError("health command exited with status 1")

        with mock.patch.object(runner, "invoke_process", side_effect=invoke):
            with self.assertRaisesRegex(
                runner.RunnerError, "failed 2 consecutive times"
            ):
                runner.supervise_detached(
                    self.recipe_path,
                    self.recipe,
                    self.workspace,
                    ImmediateEvent(),  # type: ignore[arg-type]
                )

        self.assertEqual(["run", "health", "health", "stop"], phases)
        health = json.loads(runner.HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertFalse(health["healthy"])
        self.assertEqual(2, health["consecutiveFailures"])

    def test_partial_start_failure_still_invokes_idempotent_stop(self) -> None:
        phases: list[str] = []

        def invoke(_: dict, name: str, __: Path) -> None:
            phases.append(name)
            if name == "run":
                raise runner.RunnerError("run command timed out")

        with mock.patch.object(runner, "invoke_process", side_effect=invoke):
            with self.assertRaisesRegex(runner.RunnerError, "run command timed out"):
                runner.supervise_detached(
                    self.recipe_path,
                    self.recipe,
                    self.workspace,
                    threading.Event(),
                )

        self.assertEqual(["run", "stop"], phases)

    def test_health_snapshot_rejects_stale_or_wrong_workload_evidence(self) -> None:
        requested = {
            "processMode": "detached",
            "recipeSha256": runner.recipe_hash(self.recipe_path),
            "workspace": str(self.workspace),
            "healthIntervalSeconds": 5,
            "healthTimeoutSeconds": 5,
        }
        evidence = {
            "checkedAtEpochSeconds": time.time(),
            "healthy": True,
            "recipeSha256": requested["recipeSha256"],
            "supervisorPid": 123,
            "workspace": requested["workspace"],
        }
        runner.atomic_json(runner.HEALTH_PATH, evidence)
        self.assertTrue(runner.health_snapshot(requested, True, 123)["healthy"])

        evidence["recipeSha256"] = "0" * 64
        runner.atomic_json(runner.HEALTH_PATH, evidence)
        self.assertFalse(runner.health_snapshot(requested, True, 123)["healthy"])

        evidence["recipeSha256"] = requested["recipeSha256"]
        evidence["checkedAtEpochSeconds"] = time.time() - 60
        runner.atomic_json(runner.HEALTH_PATH, evidence)
        self.assertFalse(runner.health_snapshot(requested, True, 123)["healthy"])

        evidence["checkedAtEpochSeconds"] = time.time()
        runner.atomic_json(runner.HEALTH_PATH, evidence)
        self.assertFalse(runner.health_snapshot(requested, True, 456)["healthy"])

    def test_status_health_field_requires_fresh_healthy_evidence(self) -> None:
        requested = {
            "processMode": "detached",
            "recipeSha256": runner.recipe_hash(self.recipe_path),
            "workspace": str(self.workspace),
            "healthIntervalSeconds": 5,
            "healthTimeoutSeconds": 5,
        }
        runner.atomic_json(runner.STATE_PATH, requested)
        evidence = {
            "checkedAtEpochSeconds": time.time(),
            "healthy": True,
            "recipeSha256": requested["recipeSha256"],
            "supervisorPid": 123,
            "workspace": requested["workspace"],
        }
        runner.atomic_json(runner.HEALTH_PATH, evidence)

        def fake_systemctl(*arguments: str, check: bool = True):
            if arguments[0] == "is-active":
                return subprocess.CompletedProcess([], 0, "", "")
            if "--value" in arguments:
                return subprocess.CompletedProcess([], 0, "123\n", "")
            return subprocess.CompletedProcess(
                [], 0, "ActiveState=active\nSubState=running", ""
            )

        with mock.patch.object(runner, "systemctl", side_effect=fake_systemctl):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, runner.cmd_status(mock.Mock()))
                self.assertTrue(json.loads(output.getvalue())["healthy"])
                evidence["healthy"] = False
                runner.atomic_json(runner.HEALTH_PATH, evidence)
                output.seek(0)
                output.truncate()
                self.assertEqual(0, runner.cmd_status(mock.Mock()))
                self.assertFalse(json.loads(output.getvalue())["healthy"])

    def test_stop_fails_closed_when_systemd_cannot_stop(self) -> None:
        calls = 0

        def fake_systemctl(*arguments: str, check: bool = True):
            nonlocal calls
            calls += 1
            returncode = 1 if arguments[0] == "disable" else 0
            return subprocess.CompletedProcess([], returncode, "", "")

        with (
            mock.patch.object(runner.os, "geteuid", return_value=0),
            mock.patch.object(runner, "systemctl", side_effect=fake_systemctl),
        ):
            with self.assertRaisesRegex(runner.RunnerError, "could not disable"):
                runner.cmd_stop(mock.Mock())
        self.assertEqual(2, calls)

    def test_atomic_json_rejects_symlink_target_without_touching_referent(self) -> None:
        referent = self.root / "referent.json"
        referent.write_text("original\n", encoding="utf-8")
        target = self.root / "state.json"
        target.symlink_to(referent)

        with self.assertRaisesRegex(runner.RunnerError, "target cannot be a symbolic link"):
            runner.atomic_json(target, {"state": "updated"})

        self.assertTrue(target.is_symlink())
        self.assertEqual("original\n", referent.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.root.glob(".state.json.*.tmp")))

    def test_atomic_json_rejects_symlinked_parent(self) -> None:
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)

        with self.assertRaisesRegex(runner.RunnerError, "parent cannot be a symbolic link"):
            runner.atomic_json(linked_parent / "state.json", {"state": "updated"})

        self.assertFalse((real_parent / "state.json").exists())

    def test_atomic_json_replaces_file_with_durable_private_file(self) -> None:
        target = self.root / "state.json"
        target.write_text('{"state":"old"}\n', encoding="utf-8")
        target.chmod(0o644)
        original_inode = target.stat().st_ino
        synced_types: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(descriptor: int) -> None:
            synced_types.append(stat.S_IFMT(os.fstat(descriptor).st_mode))
            real_fsync(descriptor)

        with mock.patch.object(runner.os, "fsync", side_effect=recording_fsync):
            runner.atomic_json(target, {"state": "updated"})

        self.assertEqual({"state": "updated"}, json.loads(target.read_text(encoding="utf-8")))
        self.assertNotEqual(original_inode, target.stat().st_ino)
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))
        self.assertIn(stat.S_IFREG, synced_types)
        self.assertIn(stat.S_IFDIR, synced_types)
        self.assertEqual([], list(self.root.glob(".state.json.*.tmp")))

    def test_atomic_json_failed_replace_preserves_old_file_and_cleans_temp(self) -> None:
        target = self.root / "state.json"
        original = '{"state":"old"}\n'
        target.write_text(original, encoding="utf-8")

        with mock.patch.object(runner.os, "replace", side_effect=OSError("injected")):
            with self.assertRaisesRegex(runner.RunnerError, "cannot atomically write JSON"):
                runner.atomic_json(target, {"state": "updated"})

        self.assertEqual(original, target.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.root.glob(".state.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
