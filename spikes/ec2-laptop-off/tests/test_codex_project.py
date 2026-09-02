from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock
import uuid


SPIKE_ROOT = Path(__file__).resolve().parents[1]
GUEST_ROOT = SPIKE_ROOT / "guest"
sys.path.insert(0, str(GUEST_ROOT))

import codex_project  # noqa: E402


class FakeProjectClient:
    def __init__(self, projects: list[dict] | None = None) -> None:
        self.projects = list(projects or [])
        self.created_by_key: dict[str, dict] = {}
        self.create_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def request(self, method: str, params):
        if method == "project/list":
            return {"data": list(self.projects), "nextCursor": None}
        if method == "project/create":
            self.create_calls += 1
            key = params["idempotencyKey"]
            project = self.created_by_key.get(key)
            if project is None:
                project = {
                    "id": "019d-project",
                    "name": params["name"],
                    "roots": params["roots"],
                    "metadata": params["metadata"],
                }
                self.created_by_key[key] = project
                self.projects.append(project)
            return {"project": project}
        if method == "project/read":
            matches = [p for p in self.projects if p["id"] == params["projectId"]]
            if len(matches) != 1:
                raise AssertionError("missing fake project")
            return {"project": matches[0]}
        raise AssertionError(f"unexpected request: {method}")


class FakeThreadClient(FakeProjectClient):
    def __init__(
        self,
        project: dict,
        threads: list[dict],
        resume_results: dict[str, dict] | None = None,
        config_result: dict | None = None,
        hooks_result: dict | None = None,
        requirements_result: dict | None = None,
        plugin_result: dict | None = None,
    ) -> None:
        super().__init__([project])
        self.threads = list(threads)
        self.resume_results = resume_results or {}
        self.config_result = config_result
        self.hooks_result = hooks_result
        self.requirements_result = requirements_result
        self.plugin_result = plugin_result
        self.requests: list[tuple[str, object]] = []

    def request(self, method: str, params):
        self.requests.append((method, params))
        if method == "remoteControl/status/read":
            return {"status": "connected", "environmentId": "env-test"}
        if method == "remoteControl/client/list":
            return {"data": [{"opaque": "controller-details-must-not-escape"}]}
        if method == "thread/list":
            return {"data": list(self.threads), "nextCursor": None}
        if method == "thread/read":
            matches = [
                thread for thread in self.threads if thread["id"] == params["threadId"]
            ]
            if len(matches) != 1:
                raise AssertionError("missing fake thread")
            return {"thread": matches[0]}
        if method == "thread/resume":
            return self.resume_results[params["threadId"]]
        if method == "config/read":
            if self.config_result is not None:
                return self.config_result
            return {
                "config": {},
                "layers": [
                    {
                        "config": {},
                        "disabledReason": None,
                        "name": {
                            "file": str(codex_project.CODEX_HOME / "config.toml"),
                            "type": "user",
                        },
                        "version": "user-layer-v1",
                    }
                ],
                "origins": {},
            }
        if method == "hooks/list":
            if self.hooks_result is not None:
                return self.hooks_result
            return {
                "data": [
                    {
                        "cwd": params["cwds"][0],
                        "errors": [],
                        "hooks": [],
                        "warnings": [],
                    }
                ]
            }
        if method == "configRequirements/read":
            if self.requirements_result is not None:
                return self.requirements_result
            return {"requirements": None}
        if method == "plugin/list":
            if self.plugin_result is not None:
                return self.plugin_result
            return {
                "featuredPluginIds": [],
                "marketplaceLoadErrors": [],
                "marketplaces": [],
            }
        return super().request(method, params)


class CodexProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-codex-project-test-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace_root = self.root / "workspaces"
        self.workspace = self.workspace_root / "lift"
        self.workspace.mkdir(parents=True)
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir()
        self.state_root = self.codex_home / "lift"
        self.patchers = [
            mock.patch.object(codex_project, "WORKSPACE_ROOT", self.workspace_root),
            mock.patch.object(codex_project, "STATE_ROOT", self.state_root),
            mock.patch.object(codex_project, "CODEX_HOME", self.codex_home),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.state_path = codex_project.connector_state_path(self.workspace)

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def project(
        self,
        project_id: str | None = "019d-project",
        *,
        name: str = "lift",
        root: Path | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": project_id,
            "name": name,
            "roots": [{"path": str(root or self.workspace)}],
            "metadata": metadata
            if metadata is not None
            else codex_project.expected_metadata(self.workspace),
        }

    def thread(
        self,
        thread_id: str,
        *,
        created_at: int,
        turns: list[dict] | None = None,
        project_id: str | None = "019d-project",
        cwd: Path | None = None,
    ) -> dict:
        return {
            "id": thread_id,
            "projectId": project_id,
            "cwd": str(cwd or self.workspace),
            "createdAt": created_at,
            "turns": list(turns or []),
        }

    def command_item(
        self,
        item_id: str,
        command: str,
        *,
        cwd: Path | None = None,
        status: str = "completed",
        exit_code: int | None = 0,
        source: str = codex_project.UNIFIED_EXEC_COMMAND_SOURCE,
        plugin_id: str | None = None,
        script_path: str | None = None,
        wrapped: bool = True,
    ) -> dict:
        stored_command = (
            shlex.join(
                [
                    codex_project.UNIFIED_EXEC_SHELL,
                    codex_project.UNIFIED_EXEC_SHELL_ARGUMENT,
                    command,
                ]
            )
            if wrapped
            else command
        )
        return {
            "type": "commandExecution",
            "id": item_id,
            "command": stored_command,
            "cwd": str(cwd or self.workspace),
            "status": status,
            "exitCode": exit_code,
            "source": source,
            "pluginId": plugin_id,
            "scriptPath": script_path,
        }

    def proof_thread(
        self,
        thread_id: str,
        *,
        created_at: int,
        proof_path: str,
        proof_nonce: str,
        approval_nonce: str,
    ) -> dict:
        return self.thread(
            thread_id,
            created_at=created_at,
            project_id=None,
            turns=[
                {
                    "id": f"turn-{thread_id}",
                    "status": "completed",
                    "completedAt": created_at + 1,
                    "itemsView": "full",
                    "items": [
                        self.command_item(
                            f"approval-{thread_id}",
                            codex_project.approval_canary_command(approval_nonce),
                        ),
                        self.command_item(
                            f"proof-{thread_id}",
                            f"printf {proof_nonce} > {proof_path}",
                        ),
                    ],
                }
            ],
        )

    def resume_result(
        self,
        thread: dict,
        *,
        cwd: Path | None = None,
        runtime_roots: list[str] | None = None,
        approval_policy: object = "on-request",
        approvals_reviewer: str = "user",
        sandbox: dict | None = None,
    ) -> dict:
        resumed_thread = dict(thread)
        resumed_thread["turns"] = []
        return {
            "thread": resumed_thread,
            "cwd": str(cwd or self.workspace),
            "runtimeWorkspaceRoots": runtime_roots
            if runtime_roots is not None
            else [str(self.workspace)],
            "approvalPolicy": approval_policy,
            "approvalsReviewer": approvals_reviewer,
            "sandbox": sandbox
            if sandbox is not None
            else {"type": "workspaceWrite", "networkAccess": False},
        }

    def persist_project_state(self, project_id: str = "019d-project") -> None:
        state = codex_project.validated_state(
            self.state_path,
            self.workspace,
            create=True,
        )
        state["projectId"] = project_id
        codex_project.atomic_json(self.state_path, state)

    def test_workspace_must_be_real_and_below_reviewed_root(self) -> None:
        self.assertEqual(
            self.workspace,
            codex_project.validated_workspace(str(self.workspace)),
        )
        alias = self.workspace_root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(codex_project.ConnectorError, "real directory"):
            codex_project.validated_workspace(str(alias))
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaisesRegex(codex_project.ConnectorError, "below"):
            codex_project.validated_workspace(str(outside))

    def test_registration_state_persists_one_uuid_before_create(self) -> None:
        first = codex_project.validated_state(
            self.state_path, self.workspace, create=True
        )
        second = codex_project.validated_state(
            self.state_path, self.workspace, create=True
        )

        self.assertEqual(first["idempotencyKey"], second["idempotencyKey"])
        self.assertEqual(0o600, self.state_path.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.state_root.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.state_path.parent.stat().st_mode & 0o777)

    def test_registration_state_rejects_symlinked_private_root(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        self.state_root.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(codex_project.ConnectorError, "real directory"):
            codex_project.validated_state(
                self.state_path, self.workspace, create=True
            )

    def test_registration_state_rejects_permissive_modes(self) -> None:
        codex_project.validated_state(self.state_path, self.workspace, create=True)
        self.state_path.chmod(0o644)

        with self.assertRaisesRegex(codex_project.ConnectorError, "mode 0600"):
            codex_project.validated_state(
                self.state_path, self.workspace, create=False
            )

        self.state_path.chmod(0o600)
        self.state_root.chmod(0o755)
        with self.assertRaisesRegex(codex_project.ConnectorError, "mode 0700"):
            codex_project.validated_state(
                self.state_path, self.workspace, create=False
            )

    def test_registration_state_rejects_symlink_file_without_reading_referent(self) -> None:
        self.state_root.mkdir(mode=0o700)
        self.state_path.parent.mkdir(mode=0o700)
        outside = self.root / "outside-state.json"
        outside.write_text('{"projectId":"must-not-be-read"}\n', encoding="utf-8")
        self.state_path.symlink_to(outside)

        with self.assertRaisesRegex(codex_project.ConnectorError, "real regular file"):
            codex_project.validated_state(
                self.state_path, self.workspace, create=True
            )
        self.assertEqual(
            '{"projectId":"must-not-be-read"}\n', outside.read_text(encoding="utf-8")
        )

    def test_legacy_workspace_state_is_never_read_or_migrated(self) -> None:
        legacy_path = self.workspace / ".lift/provider-state/codex-project.json"
        legacy_path.parent.mkdir(parents=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "workspace": str(self.workspace),
                    "workspaceId": self.workspace.name,
                    "idempotencyKey": str(uuid.uuid4()),
                    "projectId": "legacy-project",
                }
            ),
            encoding="utf-8",
        )

        state = codex_project.validated_state(
            self.state_path, self.workspace, create=True
        )

        self.assertNotIn("projectId", state)
        self.assertTrue(legacy_path.exists())
        self.assertEqual(self.state_path, codex_project.connector_state_path(self.workspace))
        self.assertFalse(self.state_path.is_relative_to(self.workspace))

    def test_register_configures_without_remote_or_controller_readiness(self) -> None:
        client = FakeProjectClient()
        daemon = {"status": "running"}
        with (
            mock.patch.dict(os.environ, {"LIFT_WORKSPACE": str(self.workspace)}),
            mock.patch.object(codex_project, "daemon_status", return_value=daemon),
            mock.patch.object(codex_project, "validate_experimental_schema"),
            mock.patch.object(codex_project, "AppServerClient", return_value=client),
            mock.patch.object(codex_project, "ensure_trusted"),
            mock.patch.object(codex_project, "workspace_is_trusted", return_value=True),
            mock.patch.object(
                codex_project,
                "remote_readiness",
                side_effect=AssertionError("register must not inspect Remote readiness"),
            ),
        ):
            result = codex_project.cmd_register(argparse.Namespace(name="lift"))

        self.assertTrue(result["configured"])
        self.assertTrue(result["serverProjectRegistered"])
        self.assertEqual(
            {"status": "unknown", "verified": False},
            result["controllerProjectVisibility"],
        )
        self.assertNotIn("readyForPhoneProof", result)
        self.assertNotIn("remote", result)
        self.assertEqual("019d-project", result["project"]["id"])

    def test_status_does_not_equate_server_project_with_controller_visibility(
        self,
    ) -> None:
        project = self.project()
        state = codex_project.validated_state(
            self.state_path, self.workspace, create=True
        )
        state["projectId"] = project["id"]
        codex_project.atomic_json(self.state_path, state)
        remote = {
            "status": "connected",
            "environmentId": "env-test",
            "controllerPresent": True,
            "pairedClientCount": 1,
        }
        client = FakeProjectClient([project])
        with (
            mock.patch.dict(os.environ, {"LIFT_WORKSPACE": str(self.workspace)}),
            mock.patch.object(
                codex_project, "daemon_status", return_value={"status": "running"}
            ),
            mock.patch.object(codex_project, "AppServerClient", return_value=client),
            mock.patch.object(codex_project, "workspace_is_trusted", return_value=True),
            mock.patch.object(
                codex_project, "remote_readiness", return_value=remote
            ) as readiness,
        ):
            result = codex_project.cmd_status(argparse.Namespace(name="lift"))

        readiness.assert_called_once_with(client)
        self.assertTrue(result["configured"])
        self.assertTrue(result["readyForPhoneProof"])
        self.assertTrue(result["serverProjectRegistered"])
        self.assertEqual(
            {"status": "unknown", "verified": False},
            result["controllerProjectVisibility"],
        )
        self.assertNotIn("ready", result)
        self.assertEqual(remote, result["remote"])

    def test_thread_baseline_emits_only_bound_identifiers_and_sorted_ids(self) -> None:
        project = self.project()
        self.persist_project_state(project["id"])
        client = FakeThreadClient(
            project,
            [
                self.thread("thread-z", created_at=100),
                self.thread("thread-a", created_at=99),
            ],
        )
        with (
            mock.patch.dict(os.environ, {"LIFT_WORKSPACE": str(self.workspace)}),
            mock.patch.object(codex_project, "daemon_status"),
            mock.patch.object(codex_project, "validate_experimental_schema"),
            mock.patch.object(codex_project, "AppServerClient", return_value=client),
            mock.patch.object(codex_project, "workspace_is_trusted", return_value=True),
            mock.patch.object(codex_project.time, "time", return_value=1234.9),
        ):
            result = codex_project.cmd_thread_baseline(argparse.Namespace(name="lift"))

        self.assertEqual(
            {
                "approvalGuardSha256",
                "createdAtEpochSeconds",
                "cwd",
                "environmentId",
                "nativeProjectId",
                "controllerThreadBinding",
                "controllerThreadProjectId",
                "projectRoot",
                "threadIds",
            },
            set(result),
        )
        self.assertEqual(1234, result["createdAtEpochSeconds"])
        self.assertEqual(["thread-a", "thread-z"], result["threadIds"])
        list_params = next(
            params for method, params in client.requests if method == "thread/list"
        )
        self.assertNotIn("projectId", list_params)
        self.assertEqual(str(self.workspace), list_params["cwd"])

    def test_verify_thread_binds_one_complete_turn_without_leaking_commands(self) -> None:
        project = self.project()
        self.persist_project_state(project["id"])
        proof_path = ".lift/proofs/remote-proof.txt"
        proof_nonce = "a1" * 16
        approval_nonce = "b2" * 16
        baseline = self.thread("thread-old", created_at=100)
        verified = self.proof_thread(
            "thread-new",
            created_at=200,
            proof_path=proof_path,
            proof_nonce=proof_nonce,
            approval_nonce=approval_nonce,
        )
        client = FakeThreadClient(
            project,
            [baseline, verified],
            {"thread-new": self.resume_result(verified)},
        )
        approval_guard = codex_project.approval_guard_sha256(client, self.workspace)
        expected_proof_command = f"printf {proof_nonce} > {proof_path}"
        proof_command_sha256 = hashlib.sha256(
            expected_proof_command.encode()
        ).hexdigest()
        args = argparse.Namespace(
            name="lift",
            created_after=200,
            baseline_thread_id=["thread-old"],
            proof_relative_path=proof_path,
            proof_nonce=proof_nonce,
            proof_command_sha256=proof_command_sha256,
            approval_nonce=approval_nonce,
            approval_guard_sha256=approval_guard,
        )
        with (
            mock.patch.dict(os.environ, {"LIFT_WORKSPACE": str(self.workspace)}),
            mock.patch.object(codex_project, "daemon_status"),
            mock.patch.object(codex_project, "validate_experimental_schema"),
            mock.patch.object(codex_project, "AppServerClient", return_value=client),
            mock.patch.object(codex_project, "workspace_is_trusted", return_value=True),
            mock.patch.object(codex_project.time, "time", return_value=250.9),
        ):
            result = codex_project.cmd_verify_thread(args)

        self.assertEqual("thread-new", result["threadId"])
        self.assertEqual(
            codex_project.CONTROLLER_THREAD_BINDING,
            result["controllerThreadBinding"],
        )
        self.assertIsNone(result["controllerThreadProjectId"])
        self.assertEqual("turn-thread-new", result["turnId"])
        self.assertEqual("proof-thread-new", result["proofItemId"])
        self.assertEqual("approval-thread-new", result["approvalItemId"])
        self.assertEqual("workspaceWrite", result["sandboxType"])
        self.assertIs(False, result["networkAccess"])
        self.assertEqual("user", result["approvalsReviewer"])
        self.assertEqual(approval_guard, result["approvalGuardSha256"])
        self.assertEqual(
            codex_project.APPROVAL_VERIFICATION_METHOD,
            result["approvalVerificationMethod"],
        )
        self.assertEqual(250, result["verifiedAt"])
        expected_approval_command = codex_project.approval_canary_command(
            approval_nonce
        )
        self.assertEqual(
            hashlib.sha256(expected_proof_command.encode()).hexdigest(),
            result["commandSha256"]["proof"],
        )
        self.assertEqual(
            hashlib.sha256(expected_approval_command.encode()).hexdigest(),
            result["commandSha256"]["approval"],
        )
        serialized = json.dumps(result, sort_keys=True)
        for secret_text in (
            proof_path,
            proof_nonce,
            approval_nonce,
            "https://example.com/",
            "controller-details-must-not-escape",
        ):
            self.assertNotIn(secret_text, serialized)
        self.assertIn(
            (
                "thread/read",
                {"threadId": "thread-new", "includeTurns": True},
            ),
            client.requests,
        )
        self.assertIn(
            (
                "thread/resume",
                {"threadId": "thread-new", "excludeTurns": True},
            ),
            client.requests,
        )

    def test_verify_thread_rejects_multiple_matching_post_baseline_threads(self) -> None:
        project = self.project()
        self.persist_project_state(project["id"])
        proof_path = "proof.txt"
        proof_nonce = "a1" * 16
        approval_nonce = "b2" * 16
        threads = [
            self.proof_thread(
                thread_id,
                created_at=200 + index,
                proof_path=proof_path,
                proof_nonce=proof_nonce,
                approval_nonce=approval_nonce,
            )
            for index, thread_id in enumerate(("thread-one", "thread-two"))
        ]
        client = FakeThreadClient(project, threads)
        approval_guard = codex_project.approval_guard_sha256(client, self.workspace)
        proof_command_sha256 = hashlib.sha256(
            f"printf {proof_nonce} > {proof_path}".encode()
        ).hexdigest()
        args = argparse.Namespace(
            name="lift",
            created_after=200,
            baseline_thread_id=[],
            proof_relative_path=proof_path,
            proof_nonce=proof_nonce,
            proof_command_sha256=proof_command_sha256,
            approval_nonce=approval_nonce,
            approval_guard_sha256=approval_guard,
        )
        with (
            mock.patch.dict(os.environ, {"LIFT_WORKSPACE": str(self.workspace)}),
            mock.patch.object(codex_project, "daemon_status"),
            mock.patch.object(codex_project, "validate_experimental_schema"),
            mock.patch.object(codex_project, "AppServerClient", return_value=client),
            mock.patch.object(codex_project, "workspace_is_trusted", return_value=True),
        ):
            with self.assertRaisesRegex(codex_project.ConnectorError, "exactly one"):
                codex_project.cmd_verify_thread(args)

    def test_matching_evidence_rejects_prior_turns_and_canary_not_first(self) -> None:
        proof_path = "proof.txt"
        proof_nonce = "a1" * 16
        approval_nonce = "b2" * 16
        valid = self.proof_thread(
            "thread-new",
            created_at=200,
            proof_path=proof_path,
            proof_nonce=proof_nonce,
            approval_nonce=approval_nonce,
        )
        proof_command_sha256 = hashlib.sha256(
            f"printf {proof_nonce} > {proof_path}".encode()
        ).hexdigest()
        reversed_commands = json.loads(json.dumps(valid))
        reversed_commands["turns"][0]["items"].reverse()
        with self.assertRaisesRegex(codex_project.ConnectorError, "first command"):
            codex_project.matching_turn_evidence(
                reversed_commands,
                self.workspace,
                proof_command_sha256,
                approval_nonce,
            )

        prior_turn = json.loads(json.dumps(valid["turns"][0]))
        prior_turn["id"] = "turn-prior"
        prior_turn["items"] = []
        with_prior_turn = json.loads(json.dumps(valid))
        with_prior_turn["turns"].insert(0, prior_turn)
        with self.assertRaisesRegex(codex_project.ConnectorError, "single-turn"):
            codex_project.matching_turn_evidence(
                with_prior_turn,
                self.workspace,
                proof_command_sha256,
                approval_nonce,
            )

    def test_matching_evidence_rejects_non_agent_or_plugin_command_provenance(self) -> None:
        proof_path = "proof.txt"
        proof_nonce = "a1" * 16
        approval_nonce = "b2" * 16
        variants = {
            "user shell": {"source": "userShell"},
            "plugin": {"pluginId": "example.plugin"},
            "plugin script": {"scriptPath": "scripts/run.sh"},
            "missing source": {"source": None},
        }
        for description, mutation in variants.items():
            with self.subTest(description=description):
                thread = self.proof_thread(
                    "thread-new",
                    created_at=200,
                    proof_path=proof_path,
                    proof_nonce=proof_nonce,
                    approval_nonce=approval_nonce,
                )
                thread["turns"][0]["items"][0].update(mutation)
                proof_command_sha256 = hashlib.sha256(
                    f"printf {proof_nonce} > {proof_path}".encode()
                ).hexdigest()
                with self.assertRaisesRegex(
                    codex_project.ConnectorError,
                    "ambiguous|first command",
                ):
                    codex_project.matching_turn_evidence(
                        thread,
                        self.workspace,
                        proof_command_sha256,
                        approval_nonce,
                    )

    def test_unified_exec_wrapper_requires_exact_shell_argv_and_inner_hash(self) -> None:
        inner = "printf proof > .lift/phone-proof.json"
        item = self.command_item("proof", inner)
        self.assertEqual(
            ("proof", inner),
            codex_project.successful_command(item, self.workspace),
        )
        invalid_wrappers = {
            "different shell": shlex.join(["/bin/sh", "-lc", inner]),
            "different shell flag": shlex.join(["/bin/bash", "-c", inner]),
            "extra wrapper argument": shlex.join(
                ["/bin/bash", "-lc", inner, "unexpected"]
            ),
            "unwrapped inner": inner,
        }
        for description, command in invalid_wrappers.items():
            with self.subTest(description=description):
                changed = dict(item)
                changed["command"] = command
                self.assertIsNone(
                    codex_project.successful_command(changed, self.workspace)
                )

    def test_controller_thread_identity_rejects_project_assignment(self) -> None:
        exact = self.thread("thread-new", created_at=200, project_id=None)
        self.assertEqual(
            ("thread-new", 200),
            codex_project.exact_controller_thread_identity(exact, self.workspace),
        )
        assigned = self.thread(
            "thread-new", created_at=200, project_id="019d-project"
        )
        with self.assertRaisesRegex(
            codex_project.ConnectorError, "project-unassigned"
        ):
            codex_project.exact_controller_thread_identity(
                assigned, self.workspace
            )

    def test_matching_evidence_rejects_other_tools_or_hook_items(self) -> None:
        proof_path = "proof.txt"
        proof_nonce = "a1" * 16
        approval_nonce = "b2" * 16
        proof_command_sha256 = hashlib.sha256(
            f"printf {proof_nonce} > {proof_path}".encode()
        ).hexdigest()
        for item_type in ("fileChange", "hookPrompt", "mcpToolCall"):
            with self.subTest(item_type=item_type):
                thread = self.proof_thread(
                    "thread-new",
                    created_at=200,
                    proof_path=proof_path,
                    proof_nonce=proof_nonce,
                    approval_nonce=approval_nonce,
                )
                thread["turns"][0]["items"].insert(
                    0,
                    {"id": f"other-{item_type}", "type": item_type},
                )
                with self.assertRaisesRegex(
                    codex_project.ConnectorError,
                    "unreviewed tool or hook",
                ):
                    codex_project.matching_turn_evidence(
                        thread,
                        self.workspace,
                        proof_command_sha256,
                        approval_nonce,
                    )

    def test_resume_settings_fail_closed_on_unsafe_or_unbound_configuration(self) -> None:
        project = self.project()
        thread = self.thread("thread-new", created_at=200)
        unsafe_results = {
            "dangerous sandbox": self.resume_result(
                thread,
                sandbox={"type": "dangerFullAccess"},
            ),
            "network enabled": self.resume_result(
                thread,
                sandbox={"type": "workspaceWrite", "networkAccess": True},
            ),
            "restricted external sandbox": self.resume_result(
                thread,
                sandbox={"type": "externalSandbox", "networkAccess": "restricted"},
            ),
            "never approve": self.resume_result(
                thread,
                approval_policy="never",
            ),
            "automatic reviewer": self.resume_result(
                thread,
                approvals_reviewer="auto_review",
            ),
            "wrong roots": self.resume_result(
                thread,
                runtime_roots=[str(self.workspace_root / "other")],
            ),
        }
        for description, result in unsafe_results.items():
            with self.subTest(description=description):
                client = FakeThreadClient(
                    project,
                    [thread],
                    {thread["id"]: result},
                )
                with self.assertRaises(codex_project.ConnectorError):
                    codex_project.verified_resume_settings(
                        client,
                        thread["id"],
                        self.workspace,
                    )

    def test_proof_inputs_reject_traversal_short_nonces_and_duplicates(self) -> None:
        for unsafe_path in ("../proof", "/tmp/proof", "proof//file", "proof\\file"):
            with self.subTest(path=unsafe_path):
                with self.assertRaises(codex_project.ConnectorError):
                    codex_project.validated_proof_relative_path(unsafe_path)
        with self.assertRaises(codex_project.ConnectorError):
            codex_project.validated_nonce("abcd", "proof-nonce")
        with self.assertRaises(codex_project.ConnectorError):
            codex_project.validated_baseline_thread_ids(["same", "same"])

    def test_approval_canary_requires_assignment_and_exact_curl_executable(self) -> None:
        nonce = "a1" * 16
        valid = codex_project.approval_canary_command(nonce)
        self.assertTrue(codex_project.matches_approval_canary_command(valid, nonce))
        invalid_commands = {
            "wrong executable": valid.replace("/usr/bin/curl", "curl"),
            "no trailing slash": valid.replace(
                "https://example.com/", "https://example.com"
            ),
            "extra URL": valid + " https://attacker.example/",
            "curl next": valid + " --next https://attacker.example/",
            "curl config": valid.replace(
                "/usr/bin/curl --disable",
                "/usr/bin/curl --config /tmp/curlrc --disable",
            ),
            "different output": valid.replace("/dev/null", "/tmp/result"),
            "shell suffix": valid + "; /usr/bin/true",
            "environment leakage": valid.replace("/usr/bin/env -i", "/usr/bin/env"),
        }
        for description, command in invalid_commands.items():
            with self.subTest(description=description):
                self.assertFalse(
                    codex_project.matches_approval_canary_command(command, nonce)
                )

    def test_approval_guard_rejects_any_rule_file(self) -> None:
        rules = self.codex_home / "rules"
        rules.mkdir()
        (rules / "default.rules").write_text(
            'prefix_rule(pattern=["/usr/bin/env"], decision="allow")\n',
            encoding="utf-8",
        )
        client = FakeThreadClient(self.project(), [])
        with self.assertRaisesRegex(codex_project.ConnectorError, "to be empty"):
            codex_project.approval_guard_sha256(client, self.workspace)

    def test_approval_guard_rejects_opaque_active_layer(self) -> None:
        client = FakeThreadClient(
            self.project(),
            [],
            config_result={
                "config": {},
                "layers": [
                    {
                        "config": {},
                        "disabledReason": None,
                        "name": {
                            "id": "managed-1",
                            "name": "managed",
                            "type": "enterpriseManaged",
                        },
                        "version": "managed-v1",
                    }
                ],
                "origins": {},
            },
        )
        with self.assertRaisesRegex(codex_project.ConnectorError, "opaque active"):
            codex_project.approval_guard_sha256(client, self.workspace)

    def test_approval_guard_rejects_inline_and_effective_hooks(self) -> None:
        inline = FakeThreadClient(
            self.project(),
            [],
            config_result={
                "config": {"hooks": {"PermissionRequest": []}},
                "layers": [
                    {
                        "config": {"hooks": {"PermissionRequest": []}},
                        "disabledReason": None,
                        "name": {
                            "file": str(self.codex_home / "config.toml"),
                            "type": "user",
                        },
                        "version": "user-layer-v1",
                    }
                ],
                "origins": {},
            },
        )
        with self.assertRaisesRegex(codex_project.ConnectorError, "hooks configured"):
            codex_project.approval_guard_sha256(inline, self.workspace)

        effective = FakeThreadClient(
            self.project(),
            [],
            hooks_result={
                "data": [
                    {
                        "cwd": str(self.workspace),
                        "errors": [],
                        "hooks": [
                            {
                                "currentHash": "hook-hash",
                                "enabled": True,
                                "eventName": "permissionRequest",
                                "handlerType": "command",
                                "isManaged": False,
                                "key": "hook-key",
                                "pluginId": None,
                                "source": "user",
                                "sourcePath": str(self.codex_home / "hooks.json"),
                                "trustStatus": "trusted",
                            }
                        ],
                        "warnings": [],
                    }
                ]
            },
        )
        with self.assertRaisesRegex(codex_project.ConnectorError, "every effective"):
            codex_project.approval_guard_sha256(effective, self.workspace)

    def test_approval_guard_accepts_provider_null_hook_defaults(self) -> None:
        client = FakeThreadClient(
            self.project(),
            [],
            config_result={
                "config": {"hooks": None},
                "layers": [
                    {
                        "config": {"hooks": None},
                        "disabledReason": None,
                        "name": {
                            "file": str(self.codex_home / "config.toml"),
                            "type": "user",
                        },
                        "version": "user-layer-v1",
                    }
                ],
                "origins": {},
            },
        )

        digest = codex_project.approval_guard_sha256(client, self.workspace)

        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertIn(
            ("hooks/list", {"cwds": [str(self.workspace)]}),
            client.requests,
        )
        self.assertIn(("configRequirements/read", None), client.requests)

    def test_approval_guard_rejects_file_and_managed_hooks(self) -> None:
        (self.codex_home / "hooks.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(codex_project.ConnectorError, "to be absent"):
            codex_project.approval_guard_sha256(
                FakeThreadClient(self.project(), []),
                self.workspace,
            )
        (self.codex_home / "hooks.json").unlink()

        managed = FakeThreadClient(
            self.project(),
            [],
            requirements_result={
                "requirements": {
                    "hooks": {
                        "PermissionRequest": [
                            {
                                "matcher": None,
                                "hooks": [{"type": "prompt"}],
                            }
                        ]
                    }
                }
            },
        )
        with self.assertRaisesRegex(codex_project.ConnectorError, "managed Codex hooks"):
            codex_project.approval_guard_sha256(managed, self.workspace)

    def test_approval_guard_binds_enabled_plugins_and_rejects_malformed_state(self) -> None:
        enabled = FakeThreadClient(
            self.project(),
            [],
            plugin_result={
                "featuredPluginIds": [],
                "marketplaceLoadErrors": [],
                "marketplaces": [
                    {
                        "name": "local",
                        "plugins": [
                            {
                                "enabled": True,
                                "id": "plugin.example",
                                "installed": True,
                                "name": "Example",
                                "source": {"type": "local", "path": "/tmp/plugin"},
                            }
                        ],
                    }
                ],
            },
        )
        enabled_digest = codex_project.approval_guard_sha256(enabled, self.workspace)
        disabled_result = json.loads(json.dumps(enabled.plugin_result))
        disabled_result["marketplaces"][0]["plugins"][0]["enabled"] = False
        disabled = FakeThreadClient(
            self.project(),
            [],
            plugin_result=disabled_result,
        )
        disabled_digest = codex_project.approval_guard_sha256(
            disabled,
            self.workspace,
        )
        self.assertNotEqual(enabled_digest, disabled_digest)

        load_error = FakeThreadClient(
            self.project(),
            [],
            plugin_result={
                "marketplaceLoadErrors": [{"message": "broken"}],
                "marketplaces": [],
            },
        )
        with self.assertRaisesRegex(codex_project.ConnectorError, "returned errors"):
            codex_project.approval_guard_sha256(load_error, self.workspace)

    def test_approval_guard_bounds_plugin_count_and_canonical_state(self) -> None:
        plugin = {
            "enabled": False,
            "id": "plugin.example",
            "installed": True,
            "name": "Example",
            "source": {"type": "remote"},
        }
        too_many = FakeThreadClient(
            self.project(),
            [],
            plugin_result={
                "featuredPluginIds": [],
                "marketplaceLoadErrors": [],
                "marketplaces": [
                    {"name": "remote", "plugins": [plugin, dict(plugin)]}
                ],
            },
        )
        with (
            mock.patch.object(codex_project, "MAX_PLUGINS", 1),
            self.assertRaisesRegex(codex_project.ConnectorError, "verification limit"),
        ):
            codex_project.approval_guard_sha256(too_many, self.workspace)

        bounded = FakeThreadClient(
            self.project(),
            [],
            plugin_result={
                "featuredPluginIds": [],
                "marketplaceLoadErrors": [],
                "marketplaces": [{"name": "remote", "plugins": [plugin]}],
            },
        )
        with (
            mock.patch.object(codex_project, "MAX_PLUGIN_STATE_BYTES", 1),
            self.assertRaisesRegex(codex_project.ConnectorError, "state exceeds"),
        ):
            codex_project.approval_guard_sha256(bounded, self.workspace)

    def test_plugin_list_alone_gets_the_larger_bounded_response_limit(self) -> None:
        client = codex_project.AppServerClient(Path("/unused"))
        client.transport = mock.Mock()
        client.transport.receive_json.side_effect = [
            {"id": 1, "result": {"marketplaces": []}},
            {"id": 2, "result": {"data": []}},
        ]

        client.request("plugin/list", {})
        client.request("thread/list", {})

        self.assertEqual(
            [
                mock.call(codex_project.MAX_PLUGIN_MESSAGE_BYTES),
                mock.call(codex_project.MAX_MESSAGE_BYTES),
            ],
            client.transport.receive_json.call_args_list,
        )

    def test_zero_projects_creates_once_and_replays_same_project(self) -> None:
        state = codex_project.new_state(self.workspace)
        client = FakeProjectClient()

        project, created = codex_project.ensure_project(
            client, self.workspace, "lift", state
        )

        self.assertTrue(created)
        self.assertEqual("019d-project", project["id"])
        self.assertEqual(2, client.create_calls)
        self.assertEqual(1, len(client.projects))

    def test_exact_existing_lift_project_is_reused(self) -> None:
        expected = self.project()
        client = FakeProjectClient([expected])
        state = codex_project.new_state(self.workspace)

        project, created = codex_project.ensure_project(
            client, self.workspace, "lift", state
        )

        self.assertFalse(created)
        self.assertEqual(expected, project)
        self.assertEqual(0, client.create_calls)

    def test_conflicting_same_root_project_fails_closed(self) -> None:
        conflict = self.project(metadata={})
        client = FakeProjectClient([conflict])

        with self.assertRaisesRegex(codex_project.ConnectorError, "non-Lift"):
            codex_project.ensure_project(
                client, self.workspace, "lift", codex_project.new_state(self.workspace)
            )

    def test_duplicate_same_root_projects_fail_closed(self) -> None:
        client = FakeProjectClient(
            [self.project("project-one"), self.project("project-two")]
        )

        with self.assertRaisesRegex(codex_project.ConnectorError, "multiple"):
            codex_project.ensure_project(
                client, self.workspace, "lift", codex_project.new_state(self.workspace)
            )

    def test_saved_project_cannot_silently_rotate(self) -> None:
        state = codex_project.new_state(self.workspace)
        state["projectId"] = "deleted-project"

        with self.assertRaisesRegex(codex_project.ConnectorError, "no longer matches"):
            codex_project.ensure_project(
                FakeProjectClient(), self.workspace, "lift", state
            )

    def test_websocket_client_masks_requests_and_reads_server_json(self) -> None:
        client_socket, server_socket = socket.socketpair()
        transport = codex_project.UnixWebSocket(Path("/unused"))
        transport.socket = client_socket
        observed: dict[str, object] = {}

        def server() -> None:
            first, second = server_socket.recv(2)
            self.assertEqual(0x81, first)
            self.assertTrue(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", server_socket.recv(2))[0]
            mask = server_socket.recv(4)
            payload = server_socket.recv(length)
            decoded = bytes(
                byte ^ mask[index % 4] for index, byte in enumerate(payload)
            )
            observed.update(json.loads(decoded))
            response = json.dumps({"id": 1, "result": {"ok": True}}).encode()
            server_socket.sendall(bytes([0x81, len(response)]) + response)

        thread = threading.Thread(target=server)
        thread.start()
        try:
            transport.send_json({"method": "project/list", "id": 1, "params": {}})
            response = transport.receive_json()
        finally:
            thread.join(timeout=2)
            client_socket.close()
            server_socket.close()

        self.assertEqual("project/list", observed["method"])
        self.assertEqual({"id": 1, "result": {"ok": True}}, response)


if __name__ == "__main__":
    unittest.main()
