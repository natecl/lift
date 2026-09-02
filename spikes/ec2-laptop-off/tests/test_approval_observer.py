from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest


SPIKE_ROOT = Path(__file__).resolve().parents[1]
GUEST_ROOT = SPIKE_ROOT / "guest"
sys.path.insert(0, str(GUEST_ROOT))

import approval_observer  # noqa: E402


class FakeRpc:
    def __init__(
        self,
        *,
        workspace: Path,
        project_id: str,
        list_results: list[list[dict]],
        messages: list[dict],
    ) -> None:
        self.workspace = workspace
        self.project_id = project_id
        self.list_results = list(list_results)
        self.messages = list(messages)
        self.calls: list[tuple[str, dict]] = []
        self.initialized = False

    def initialize(self, _deadline: float) -> None:
        self.initialized = True

    def call(self, method: str, params: dict, _deadline: float):
        self.calls.append((method, params))
        if method == "thread/list":
            if not self.list_results:
                raise AssertionError("missing fake thread/list result")
            return {"data": self.list_results.pop(0), "nextCursor": None}
        if method == "thread/resume":
            thread_id = params["threadId"]
            return {
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "cwd": str(self.workspace),
                "runtimeWorkspaceRoots": [str(self.workspace)],
                "sandbox": {"networkAccess": False, "type": "workspaceWrite"},
                "thread": {
                    "createdAt": 200,
                    "cwd": str(self.workspace),
                    "id": thread_id,
                    "projectId": None,
                    "turns": [],
                },
            }
        raise AssertionError(f"unexpected fake request: {method}")

    def next_message(self, _deadline: float):
        if not self.messages:
            raise AssertionError("missing fake observer event")
        return self.messages.pop(0)


class ApprovalObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-observer-test-")
        self.workspace = Path(self.temporary.name).resolve()
        self.project_id = "project-lift"
        self.environment_id = "env-lift"
        self.thread_id = "thread-new"
        self.turn_id = "turn-new"
        self.item_id = "item-approval"
        self.proof_item_id = "item-proof"
        self.request_id = "request-approval"
        self.command = "/usr/bin/env -i TEST=1 /usr/bin/curl https://example.com/"
        self.command_sha256 = hashlib.sha256(self.command.encode()).hexdigest()
        self.proof_command = "printf proof > .lift/phone-proof.json"
        self.proof_command_sha256 = hashlib.sha256(
            self.proof_command.encode()
        ).hexdigest()
        self.challenge_sha256 = "c" * 64
        self.approval_guard_sha256 = "d" * 64

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def thread(self, thread_id: str | None = None) -> dict:
        return {
            "createdAt": 200,
            "cwd": str(self.workspace),
            "id": thread_id or self.thread_id,
            "projectId": None,
        }

    def request(self, **updates) -> dict:
        amendment = ["/usr/bin/curl"]
        params = {
            "approvalId": None,
            "command": self.wrapped(self.command),
            "cwd": str(self.workspace),
            "environmentId": approval_observer.REQUEST_EXECUTION_ENVIRONMENT_ID,
            "itemId": self.item_id,
            "kind": "command",
            "networkApprovalContext": None,
            "proposedExecpolicyAmendment": amendment,
            "availableDecisions": [
                "accept",
                {
                    "acceptWithExecpolicyAmendment": {
                        "execpolicy_amendment": amendment,
                    }
                },
                "cancel",
            ],
            "startedAtMs": 200_100,
            "threadId": self.thread_id,
            "turnId": self.turn_id,
        }
        params.update(updates)
        return {
            "id": self.request_id,
            "method": "item/commandExecution/requestApproval",
            "params": params,
        }

    def resolved(self, **updates) -> dict:
        params = {"requestId": self.request_id, "threadId": self.thread_id}
        params.update(updates)
        return {"method": "serverRequest/resolved", "params": params}

    def goal_cleared(self, **updates) -> dict:
        params = {"threadId": self.thread_id}
        params.update(updates)
        return {"method": "thread/goal/cleared", "params": params}

    def name_updated(self, **updates) -> dict:
        params = {"threadId": self.thread_id, "threadName": "Verify Lift proof"}
        params.update(updates)
        return {"method": "thread/name/updated", "params": params}

    def command_item(
        self,
        *,
        command: str | None = None,
        item_id: str | None = None,
        **updates,
    ) -> dict:
        item = {
            "command": self.wrapped(command or self.command),
            "cwd": str(self.workspace),
            "exitCode": 0,
            "id": item_id or self.item_id,
            "pluginId": None,
            "scriptPath": None,
            "source": approval_observer.codex_project.UNIFIED_EXEC_COMMAND_SOURCE,
            "status": "completed",
            "type": "commandExecution",
        }
        item.update(updates)
        return item

    def wrapped(self, inner: str) -> str:
        return shlex.join(
            [
                approval_observer.codex_project.UNIFIED_EXEC_SHELL,
                approval_observer.codex_project.UNIFIED_EXEC_SHELL_ARGUMENT,
                inner,
            ]
        )

    def started(
        self,
        *,
        command: str | None = None,
        item_id: str | None = None,
        started_at_ms: int = 200_150,
        **item_updates,
    ) -> dict:
        item = self.command_item(
            command=command,
            item_id=item_id,
            status="inProgress",
            **item_updates,
        )
        item.pop("exitCode")
        return {
            "method": "item/started",
            "params": {
                "item": item,
                "startedAtMs": started_at_ms,
                "threadId": self.thread_id,
                "turnId": self.turn_id,
            },
        }

    def completed(
        self,
        *,
        command: str | None = None,
        item_id: str | None = None,
        completed_at_ms: int = 200_200,
        **item_updates,
    ) -> dict:
        item = self.command_item(
            command=command, item_id=item_id, **item_updates
        )
        return {
            "method": "item/completed",
            "params": {
                "completedAtMs": completed_at_ms,
                "item": item,
                "threadId": self.thread_id,
                "turnId": self.turn_id,
            },
        }

    def proof_started(self) -> dict:
        return self.started(
            command=self.proof_command,
            item_id=self.proof_item_id,
            started_at_ms=200_250,
        )

    def proof_completed(
        self, *, completed_at_ms: int = 200_300, **updates
    ) -> dict:
        return self.completed(
            command=self.proof_command,
            item_id=self.proof_item_id,
            completed_at_ms=completed_at_ms,
            **updates,
        )

    def agent_message(
        self,
        *,
        item_id: str = "agent-final",
        text: str = "Proof created.",
        **updates,
    ) -> dict:
        item = {
            "delivery": None,
            "id": item_id,
            "memoryCitation": None,
            "phase": None,
            "text": text,
            "type": "agentMessage",
        }
        item.update(updates)
        return item

    def agent_completed(
        self,
        *,
        item_id: str = "agent-final",
        completed_at_ms: int = 200_350,
        **updates,
    ) -> dict:
        return {
            "method": "item/completed",
            "params": {
                "completedAtMs": completed_at_ms,
                "item": self.agent_message(item_id=item_id, **updates),
                "threadId": self.thread_id,
                "turnId": self.turn_id,
            },
        }

    def turn_completed(
        self,
        *,
        items: list[dict] | None = None,
        items_view: str = "summary",
        **updates,
    ) -> dict:
        turn = {
            "completedAt": 201,
            "durationMs": 1_000,
            "error": None,
            "id": self.turn_id,
            "items": [self.agent_message()] if items is None else items,
            "itemsView": items_view,
            "startedAt": 200,
            "status": "completed",
        }
        turn.update(updates)
        return {
            "method": "turn/completed",
            "params": {
                "threadId": self.thread_id,
                "turn": turn,
            },
        }

    def observe(self, *, messages: list[dict], list_results=None) -> dict:
        candidate = self.thread()
        ready: list[dict] = []
        rpc = FakeRpc(
            workspace=self.workspace,
            project_id=self.project_id,
            list_results=list_results or [[], [candidate], [candidate]],
            messages=messages,
        )
        evidence = approval_observer.observe_approval(
            rpc,
            workspace=self.workspace,
            project_id=self.project_id,
            environment_id=self.environment_id,
            created_after=200,
            baseline_thread_ids=frozenset({"thread-old"}),
            expected_approval_command_sha256=self.command_sha256,
            expected_proof_command_sha256=self.proof_command_sha256,
            challenge_sha256=self.challenge_sha256,
            approval_guard_sha256=self.approval_guard_sha256,
            timeout_seconds=10,
            ready=ready.append,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )
        self.assertTrue(rpc.initialized)
        self.assertEqual(1, len(ready))
        self.assertEqual(self.challenge_sha256, ready[0]["challengeSha256"])
        self.assertEqual(
            approval_observer.codex_project.CONTROLLER_THREAD_BINDING,
            ready[0]["controllerThreadBinding"],
        )
        self.assertIsNone(ready[0]["controllerThreadProjectId"])
        self.assertEqual(
            self.approval_guard_sha256, ready[0]["approvalGuardSha256"]
        )
        self.assertEqual(self.command_sha256, ready[0]["approvalCommandSha256"])
        self.assertEqual(self.proof_command_sha256, ready[0]["proofCommandSha256"])
        self.assertEqual(
            approval_observer.READY_VERIFICATION_METHOD,
            ready[0]["verificationMethod"],
        )
        return evidence

    def test_observes_bound_request_resolution_and_success_without_raw_command(self) -> None:
        evidence = self.observe(
            messages=[
                self.goal_cleared(),
                self.name_updated(),
                self.started(),
                self.request(),
                self.resolved(),
                self.completed(),
                self.proof_started(),
                self.proof_completed(),
                self.agent_completed(),
                self.turn_completed(),
            ]
        )

        self.assertEqual(self.thread_id, evidence["threadId"])
        self.assertEqual(self.turn_id, evidence["turnId"])
        self.assertEqual(self.item_id, evidence["approvalItemId"])
        self.assertEqual(self.proof_item_id, evidence["proofItemId"])
        self.assertEqual(self.request_id, evidence["requestId"])
        self.assertEqual("local", evidence["requestEnvironmentId"])
        self.assertEqual(
            200_150,
            evidence["approvalCommandStartedAtEpochMilliseconds"],
        )
        self.assertEqual(
            200_250,
            evidence["proofCommandStartedAtEpochMilliseconds"],
        )
        self.assertEqual(1, evidence["threadGoalClearedCount"])
        self.assertEqual(1, evidence["threadNameUpdatedCount"])
        self.assertEqual(self.command_sha256, evidence["approvalCommandSha256"])
        self.assertEqual(self.proof_command_sha256, evidence["proofCommandSha256"])
        self.assertEqual(self.challenge_sha256, evidence["challengeSha256"])
        self.assertEqual(
            self.approval_guard_sha256, evidence["approvalGuardSha256"]
        )
        self.assertEqual(200, evidence["createdAfterEpochSeconds"])
        self.assertEqual(
            approval_observer.VERIFICATION_METHOD,
            evidence["verificationMethod"],
        )
        self.assertNotIn(self.command, json.dumps(evidence, sort_keys=True))

    def test_rejects_mismatched_resolution_or_command_provenance(self) -> None:
        cases = {
            "wrong resolution": [
                self.goal_cleared(),
                self.started(),
                self.request(),
                self.resolved(requestId="other"),
            ],
            "missing source": [
                self.goal_cleared(),
                self.started(),
                self.request(),
                self.resolved(),
                self.completed(source=None),
            ],
            "plugin source": [
                self.goal_cleared(),
                self.started(),
                self.request(),
                self.resolved(),
                self.completed(pluginId="plugin.example"),
            ],
            "remote enrollment id used as execution environment": [
                self.goal_cleared(),
                self.started(),
                self.request(environmentId=self.environment_id),
            ],
            "missing execution environment": [
                self.goal_cleared(),
                self.started(),
                self.request(environmentId=None),
            ],
            "amendment decision mismatch": [
                self.goal_cleared(),
                self.started(),
                self.request(
                    availableDecisions=["accept", "cancel"],
                ),
            ],
            "camel-case amendment field": [
                self.goal_cleared(),
                self.started(),
                self.request(
                    availableDecisions=[
                        "accept",
                        {
                            "acceptWithExecpolicyAmendment": {
                                "execpolicyAmendment": ["/usr/bin/curl"],
                            }
                        },
                        "cancel",
                    ],
                ),
            ],
            "session decision added": [
                self.goal_cleared(),
                self.started(),
                self.request(
                    availableDecisions=[
                        "accept",
                        "acceptForSession",
                        {
                            "acceptWithExecpolicyAmendment": {
                                "execpolicy_amendment": ["/usr/bin/curl"],
                            }
                        },
                        "cancel",
                    ],
                ),
            ],
            "decision amendment differs": [
                self.goal_cleared(),
                self.started(),
                self.request(
                    availableDecisions=[
                        "accept",
                        {
                            "acceptWithExecpolicyAmendment": {
                                "execpolicy_amendment": ["/usr/bin/env"],
                            }
                        },
                        "cancel",
                    ],
                ),
            ],
            "missing decisions": [
                self.goal_cleared(),
                self.started(),
                self.request(availableDecisions=None),
            ],
            "reordered decisions": [
                self.goal_cleared(),
                self.started(),
                self.request(
                    availableDecisions=[
                        "cancel",
                        "accept",
                        {
                            "acceptWithExecpolicyAmendment": {
                                "execpolicy_amendment": ["/usr/bin/curl"],
                            }
                        },
                    ],
                ),
            ],
            "malformed amendment": [
                self.goal_cleared(),
                self.started(),
                self.request(proposedExecpolicyAmendment=[]),
            ],
            "additional permissions": [
                self.goal_cleared(),
                self.started(),
                self.request(additionalPermissions={"network": True}),
            ],
        }
        for description, messages in cases.items():
            with self.subTest(description=description):
                with self.assertRaises(approval_observer.ObserverError):
                    self.observe(messages=messages)

    def test_rejects_changed_shell_or_extra_wrapper_arguments(self) -> None:
        invalid = {
            "different shell": shlex.join(["/bin/sh", "-lc", self.command]),
            "different flag": shlex.join(["/bin/bash", "-c", self.command]),
            "extra argument": shlex.join(
                ["/bin/bash", "-lc", self.command, "unexpected"]
            ),
        }
        for description, command in invalid.items():
            with self.subTest(description=description):
                with self.assertRaisesRegex(
                    approval_observer.ObserverError, "unexpected wrapper"
                ):
                    approval_observer._inner_command_sha256(command)

    def test_validates_provider_command_start_timestamps_when_observed(self) -> None:
        evidence = self.observe(
            messages=[
                self.goal_cleared(),
                self.started(source="agent"),
                self.request(),
                self.resolved(),
                self.completed(),
                self.proof_started(),
                self.proof_completed(),
                self.agent_completed(),
                self.turn_completed(),
            ]
        )
        self.assertEqual(self.thread_id, evidence["threadId"])

        with self.assertRaisesRegex(
            approval_observer.ObserverError, "unexpected provenance"
        ):
            self.observe(messages=[self.started(source="userShell")])

        cases = {
            "request timestamp after approval start": [
                self.goal_cleared(),
                self.started(started_at_ms=200_150),
                self.request(startedAtMs=200_151),
            ],
            "request arrived before approval item start": [
                self.goal_cleared(),
                self.request(),
            ],
            "request-to-start lag exceeded": [
                self.goal_cleared(),
                self.started(started_at_ms=210_101),
                self.request(),
            ],
            "proof start before approval success": [
                self.goal_cleared(),
                self.started(),
                self.request(),
                self.resolved(),
                self.completed(),
                self.started(
                    command=self.proof_command,
                    item_id=self.proof_item_id,
                    started_at_ms=200_199,
                ),
            ],
            "proof completion before proof start": [
                self.goal_cleared(),
                self.started(),
                self.request(),
                self.resolved(),
                self.completed(),
                self.proof_started(),
                self.proof_completed(completed_at_ms=200_249),
            ],
        }
        for description, messages in cases.items():
            with self.subTest(description=description):
                with self.assertRaises(approval_observer.ObserverError):
                    self.observe(messages=messages)

    def test_rejects_unexpected_tool_event_before_approval(self) -> None:
        messages = [
            self.goal_cleared(),
            {
                "method": "item/completed",
                "params": {
                    "completedAtMs": 200_050,
                    "item": {"id": "file", "type": "fileChange"},
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                },
            },
            self.request(),
        ]
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            "unexpected tool or mutation",
        ):
            self.observe(messages=messages)

    def test_rejects_ambiguous_fresh_threads(self) -> None:
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            "multiple fresh",
        ):
            self.observe(
                messages=[],
                list_results=[[], [self.thread(), self.thread("thread-other")]],
            )

    def test_rejects_non_summary_item_in_completed_turn(self) -> None:
        extra = self.command_item(command="pwd", item_id="item-extra")
        messages = [
            self.goal_cleared(),
            self.started(),
            self.request(),
            self.resolved(),
            self.completed(),
            self.proof_started(),
            self.proof_completed(),
            self.agent_completed(),
            self.turn_completed(items=[extra]),
        ]
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            "summary item schema",
        ):
            self.observe(messages=messages)

    def test_requires_one_exact_early_thread_goal_clear_snapshot(self) -> None:
        valid_tail = [
            self.started(),
            self.request(),
            self.resolved(),
            self.completed(),
            self.proof_started(),
            self.proof_completed(),
            self.agent_completed(),
            self.turn_completed(),
        ]
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            "exact approval lifecycle",
        ):
            self.observe(messages=valid_tail)
        for description, prefix in {
            "extra payload": [self.goal_cleared(goal={})],
            "too many": [
                self.goal_cleared(),
                self.goal_cleared(),
                self.goal_cleared(),
            ],
            "late": [self.started(), self.request(), self.goal_cleared()],
        }.items():
            with self.subTest(description=description):
                with self.assertRaises(approval_observer.ObserverError):
                    self.observe(messages=prefix + valid_tail)

        evidence = self.observe(
            messages=[self.goal_cleared(), self.goal_cleared()] + valid_tail
        )
        self.assertEqual(2, evidence["threadGoalClearedCount"])

    def test_unknown_bound_event_reports_only_safe_method_name(self) -> None:
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            r"unexpected event: thread/settings/updated$",
        ):
            self.observe(
                messages=[
                    {
                        "method": "thread/settings/updated",
                        "params": {"threadId": self.thread_id},
                    }
                ]
            )

    def test_accepts_one_exact_thread_name_metadata_update_only(self) -> None:
        valid_tail = [
            self.started(),
            self.request(),
            self.resolved(),
            self.completed(),
            self.proof_started(),
            self.proof_completed(),
            self.agent_completed(),
            self.turn_completed(),
        ]
        for description, update in {
            "missing": {"threadName": None},
            "empty": {"threadName": ""},
            "padded": {"threadName": " padded "},
            "extra": {"unexpected": True},
        }.items():
            with self.subTest(description=description):
                with self.assertRaises(approval_observer.ObserverError):
                    self.observe(
                        messages=[self.goal_cleared(), self.name_updated(**update)]
                        + valid_tail
                    )
        with self.assertRaisesRegex(
            approval_observer.ObserverError,
            "ambiguous",
        ):
            self.observe(
                messages=[
                    self.goal_cleared(),
                    self.name_updated(),
                    self.name_updated(),
                ]
                + valid_tail
            )

    def test_replays_captured_mobile_method_flow_through_completion(self) -> None:
        def benign_item(item_id: str, item_type: str, completed: bool) -> dict:
            method = "item/completed" if completed else "item/started"
            timestamp = "completedAtMs" if completed else "startedAtMs"
            item = {"id": item_id, "type": item_type}
            if item_type == "agentMessage":
                item.update(
                    {
                        "delivery": None,
                        "memoryCitation": None,
                        "phase": (
                            "commentary" if item_id == "agent-before" else None
                        ),
                        "text": (
                            "I will verify the proof."
                            if item_id == "agent-before"
                            else "Proof created."
                        ),
                    }
                )
            return {
                "method": method,
                "params": {
                    timestamp: 200_010,
                    "item": item,
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                },
            }

        def target_notification(method: str, **params) -> dict:
            return {
                "method": method,
                "params": {"threadId": self.thread_id, **params},
            }

        global_rate_limits = {
            "method": "account/rateLimits/updated",
            "params": {"rateLimits": {"primary": None, "secondary": None}},
        }
        other_thread_noise = {
            "method": "thread/name/updated",
            "params": {
                "threadId": "title-helper-thread",
                "threadName": "Concurrent helper",
            },
        }

        messages = [
            {
                "method": "thread/status/changed",
                "params": {"threadId": self.thread_id},
            },
            {
                "method": "turn/started",
                "params": {
                    "threadId": self.thread_id,
                    "turn": {"id": self.turn_id},
                },
            },
            self.goal_cleared(),
            benign_item("user", "userMessage", False),
            benign_item("user", "userMessage", True),
            self.goal_cleared(),
            benign_item("agent-before", "agentMessage", False),
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": self.thread_id, "turnId": self.turn_id},
            },
            benign_item("agent-before", "agentMessage", True),
            other_thread_noise,
            self.name_updated(),
            self.started(source="agent"),
            self.request(),
            self.resolved(),
            target_notification("thread/status/changed", status={"type": "active"}),
            self.completed(),
            target_notification("thread/tokenUsage/updated", turnId=self.turn_id),
            global_rate_limits,
            self.proof_started(),
            self.proof_completed(),
            target_notification("thread/tokenUsage/updated", turnId=self.turn_id),
            global_rate_limits,
            benign_item("agent-after", "agentMessage", False),
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": self.thread_id, "turnId": self.turn_id},
            },
            benign_item("agent-after", "agentMessage", True),
            target_notification("thread/tokenUsage/updated", turnId=self.turn_id),
            global_rate_limits,
            target_notification("thread/status/changed", status={"type": "idle"}),
            self.turn_completed(
                items=[self.agent_message(item_id="agent-after")]
            ),
        ]
        evidence = self.observe(messages=messages)
        self.assertEqual(2, evidence["threadGoalClearedCount"])
        self.assertEqual(1, evidence["threadNameUpdatedCount"])

    def test_rejects_malformed_or_unbound_turn_summary(self) -> None:
        valid_prefix = [
            self.goal_cleared(),
            self.started(),
            self.request(),
            self.resolved(),
            self.completed(),
            self.proof_started(),
            self.proof_completed(),
            self.agent_completed(),
        ]
        cases = {
            "full view": self.turn_completed(items_view="full"),
            "wrong message": self.turn_completed(
                items=[self.agent_message(item_id="other-agent")]
            ),
            "empty text": self.turn_completed(
                items=[self.agent_message(text="   ")]
            ),
            "commentary phase": self.turn_completed(
                items=[self.agent_message(phase="commentary")]
            ),
            "memory citation": self.turn_completed(
                items=[self.agent_message(memoryCitation={"source": "memory"})]
            ),
            "missing duration": self.turn_completed(durationMs=None),
            "completion before start": self.turn_completed(
                startedAt=202, completedAt=201
            ),
        }
        for description, completion in cases.items():
            with self.subTest(description=description):
                with self.assertRaises(approval_observer.ObserverError):
                    self.observe(messages=valid_prefix + [completion])

    def test_atomic_output_is_private_and_replaces_regular_file(self) -> None:
        output = self.workspace / "evidence.json"
        approval_observer.atomic_private_json(output, {"observed": True})
        self.assertEqual(0o600, output.stat().st_mode & 0o777)
        self.assertEqual({"observed": True}, json.loads(output.read_text()))


if __name__ == "__main__":
    unittest.main()
