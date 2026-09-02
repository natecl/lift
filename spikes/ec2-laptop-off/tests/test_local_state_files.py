from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

import spike  # noqa: E402


class LocalStateFileTests(unittest.TestCase):
    def state(self) -> dict:
        run_id = "p0-20260901120000-abcd"
        account_id = "123456789012"
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
                "state": "NOT_CREATED",
                "stackName": f"lift-{run_id}",
            },
            "workspace": {"lease": "LOCAL_PRIMARY"},
            "connection": {"state": "DISCONNECTED"},
            "readiness": {},
        }

    def paths(self, root: Path):
        return mock.patch.multiple(
            spike,
            LOCAL_ROOT=root,
            STATE_PATH=root / "state.json",
            EVENTS_PATH=root / "events.ndjson",
        )

    @staticmethod
    def mode(path: Path) -> int:
        return stat.S_IMODE(path.lstat().st_mode)

    def test_atomic_state_creates_private_durable_files_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "control"
            real_fsync = os.fsync
            with self.paths(root), mock.patch.object(
                spike.os, "fsync", wraps=real_fsync
            ) as fsync:
                spike.atomic_state(self.state())
                loaded = spike.load_state()

            self.assertEqual(self.state(), loaded)
            self.assertEqual(0o700, self.mode(root))
            self.assertEqual(0o600, self.mode(root / "state.json"))
            self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual([], list(root.glob(".state.json.*.tmp")))

    def test_aws_identity_rejects_recreated_same_name_principal(self) -> None:
        state = self.state()
        with mock.patch.object(
            spike,
            "caller_identity",
            return_value={
                "accountId": state["identity"]["accountId"],
                "principalArn": state["identity"]["principalArn"],
                "userId": "AIDADIFFERENT",
            },
        ):
            with self.assertRaisesRegex(
                spike.SpikeError, "principal identity changed"
            ):
                spike.assert_identity(state)

    def test_aws_environment_rejects_endpoint_and_trust_overrides(self) -> None:
        overrides = {
            "AWS_ENDPOINT_URL": "https://attacker.invalid",
            "AWS_ENDPOINT_URL_STS": "https://attacker.invalid",
            "AWS_CA_BUNDLE": "/tmp/attacker-ca.pem",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "false",
            "BOTO_CONFIG": "/tmp/attacker-boto.cfg",
            "LIFT_ENVIRONMENT_SENTINEL": "preserved",
        }
        with mock.patch.dict(spike.os.environ, overrides, clear=False):
            environment = spike.scrubbed_environment()

        self.assertNotIn("AWS_ENDPOINT_URL", environment)
        self.assertNotIn("AWS_ENDPOINT_URL_STS", environment)
        self.assertNotIn("AWS_CA_BUNDLE", environment)
        self.assertNotIn("BOTO_CONFIG", environment)
        self.assertEqual("true", environment["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"])
        self.assertEqual("preserved", environment["LIFT_ENVIRONMENT_SENTINEL"])

    def test_owned_legacy_modes_are_tightened_without_losing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "control"
            root.mkdir(mode=0o755)
            os.chmod(root, 0o755)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(self.state()), encoding="utf-8")
            os.chmod(state_path, 0o644)
            events_path = root / "events.ndjson"
            original_line = '{"at":"before","type":"legacy"}\n'
            events_path.write_text(original_line, encoding="utf-8")
            os.chmod(events_path, 0o644)

            with self.paths(root):
                self.assertEqual(self.state(), spike.load_state())
                self.assertEqual(0o700, self.mode(root))
                self.assertEqual(0o600, self.mode(state_path))
                self.assertEqual(0o600, self.mode(events_path))
                spike.record_event("current", value=1)

            self.assertEqual(0o700, self.mode(root))
            self.assertEqual(0o600, self.mode(state_path))
            self.assertEqual(0o600, self.mode(events_path))
            lines = events_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(original_line), json.loads(lines[0]))
            self.assertEqual("current", json.loads(lines[1])["type"])

    def test_state_symlink_fails_closed_without_touching_referent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "control"
            root.mkdir(mode=0o700)
            victim = parent / "victim.json"
            original = json.dumps(self.state())
            victim.write_text(original, encoding="utf-8")
            original_mode = self.mode(victim)
            (root / "state.json").symlink_to(victim)

            with self.paths(root):
                with self.assertRaises(spike.SpikeError):
                    spike.load_state()
                with self.assertRaises(spike.SpikeError):
                    spike.atomic_state(self.state() | {"revision": 2})

            self.assertEqual(original, victim.read_text(encoding="utf-8"))
            self.assertEqual(original_mode, self.mode(victim))
            self.assertTrue((root / "state.json").is_symlink())

    def test_event_symlink_fails_closed_without_appending_to_referent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "control"
            root.mkdir(mode=0o700)
            victim = parent / "victim.log"
            victim.write_text("unchanged\n", encoding="utf-8")
            original_mode = self.mode(victim)
            (root / "events.ndjson").symlink_to(victim)

            with self.paths(root), self.assertRaises(spike.SpikeError):
                spike.record_event("must-not-append")

            self.assertEqual("unchanged\n", victim.read_text(encoding="utf-8"))
            self.assertEqual(original_mode, self.mode(victim))

    def test_symlinked_control_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            referent = parent / "referent"
            referent.mkdir(mode=0o700)
            root = parent / "control"
            root.symlink_to(referent, target_is_directory=True)

            with self.paths(root):
                with self.assertRaises(spike.SpikeError):
                    spike.atomic_state(self.state())
                with self.assertRaises(spike.SpikeError):
                    spike.record_event("must-not-write")

            self.assertEqual([], list(referent.iterdir()))

    def test_nonregular_and_oversized_control_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)

            nonregular_root = parent / "nonregular"
            nonregular_root.mkdir(mode=0o700)
            (nonregular_root / "state.json").mkdir()
            (nonregular_root / "events.ndjson").mkdir()
            with self.paths(nonregular_root):
                with self.assertRaises(spike.SpikeError):
                    spike.load_state()
                with self.assertRaises(spike.SpikeError):
                    spike.atomic_state(self.state())
                with self.assertRaises(spike.SpikeError):
                    spike.record_event("must-not-write")

            oversized_root = parent / "oversized"
            oversized_root.mkdir(mode=0o700)
            oversized_state = oversized_root / "state.json"
            with oversized_state.open("wb") as handle:
                handle.truncate(spike.MAX_LOCAL_STATE_BYTES + 1)
            os.chmod(oversized_state, 0o600)
            oversized_events = oversized_root / "events.ndjson"
            with oversized_events.open("wb") as handle:
                handle.truncate(spike.MAX_LOCAL_EVENTS_BYTES + 1)
            os.chmod(oversized_events, 0o600)
            with self.paths(oversized_root):
                with self.assertRaisesRegex(spike.SpikeError, "size limit"):
                    spike.load_state()
                with self.assertRaisesRegex(spike.SpikeError, "size limit"):
                    spike.atomic_state(self.state())
                with self.assertRaisesRegex(spike.SpikeError, "size limit"):
                    spike.record_event("must-not-write")

    def test_state_temp_uses_exclusive_random_name_without_truncating_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "control"
            root.mkdir(mode=0o700)
            collision = root / (".state.json." + "a" * 32 + ".tmp")
            collision.write_text("sentinel", encoding="utf-8")
            os.chmod(collision, 0o600)

            with self.paths(root), mock.patch.object(
                spike.secrets,
                "token_hex",
                side_effect=["a" * 32, "b" * 32],
            ):
                spike.atomic_state(self.state())

            self.assertEqual("sentinel", collision.read_text(encoding="utf-8"))
            self.assertTrue((root / "state.json").is_file())
            self.assertFalse((root / (".state.json." + "b" * 32 + ".tmp")).exists())

    def test_failed_atomic_replace_preserves_prior_state_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "control"
            with self.paths(root):
                spike.atomic_state(self.state())
                original = (root / "state.json").read_bytes()
                with mock.patch.object(
                    spike.os, "replace", side_effect=OSError("replace failed")
                ):
                    with self.assertRaisesRegex(spike.SpikeError, "persist"):
                        spike.atomic_state(self.state() | {"revision": 2})

            self.assertEqual(original, (root / "state.json").read_bytes())
            self.assertEqual([], list(root.glob(".state.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
