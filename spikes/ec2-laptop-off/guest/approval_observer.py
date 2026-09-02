#!/usr/bin/env python3
"""Observe one exact Codex App Server approval-and-proof turn without answering it.

This founder-spike helper is deliberately read-only.  It subscribes to one
fresh thread, records the approval request and both exact command lifecycles,
and writes only normalized, nonsecret evidence after the turn completes. The
provider's originating client remains solely responsible for the decision.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import time
from typing import Any, Callable

import codex_project


SCHEMA_VERSION = 8
VERIFICATION_METHOD = (
    "observed-folder-bound-metadata-aware-local-exec-environment-request-"
    "resolved-source-schema-amendment-consistent-wrapped-summary-success-v8"
)
READY_VERIFICATION_METHOD = "observer-initialized-folder-polling-v8"
REQUEST_EXECUTION_ENVIRONMENT_ID = "local"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_ID_BYTES = 512
MAX_THREAD_PAGES = 100
MAX_THREADS_PER_PAGE = 100
MAX_OUTPUT_BYTES = 64 * 1024
POLL_INTERVAL_SECONDS = 0.2
SOCKET_POLL_SECONDS = 0.5
MAX_TIMEOUT_SECONDS = 3600
MAX_GOAL_CLEARED_SNAPSHOTS = 2
MAX_REQUEST_TO_ITEM_START_LAG_MILLISECONDS = 10_000

BENIGN_ITEM_TYPES = {"agentMessage", "plan", "reasoning", "userMessage"}
PENDING_UNIFIED_EXEC_SOURCES = {
    "agent",
    codex_project.UNIFIED_EXEC_COMMAND_SOURCE,
}
BENIGN_ITEM_NOTIFICATION_PREFIXES = (
    "item/agentMessage/",
    "item/plan/",
    "item/reasoning/",
)
BENIGN_THREAD_NOTIFICATIONS = {
    "thread/started",
    "thread/status/changed",
    "thread/tokenUsage/updated",
    "turn/started",
}
FORBIDDEN_METHOD_FRAGMENTS = (
    "autoApproval",
    "dynamicTool",
    "fileChange",
    "hook/",
    "mcp",
    "permissions/requestApproval",
    "requestUserInput",
    "turn/diff/",
)


class ObserverError(RuntimeError):
    """Fail-closed approval observation error."""


def _validated_id(value: Any, description: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > MAX_ID_BYTES
        or "\x00" in value
    ):
        raise ObserverError(f"{description} is invalid")
    return value


def _validated_request_id(value: Any) -> str | int:
    if isinstance(value, bool):
        raise ObserverError("approval request ID is invalid")
    if isinstance(value, int):
        if value < 0:
            raise ObserverError("approval request ID is invalid")
        return value
    return _validated_id(value, "approval request ID")


def _validated_epoch(value: Any, description: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverError(f"{description} is invalid")
    return value


def _validated_sha256(value: Any) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ObserverError("expected approval command SHA-256 is invalid")
    return value


def _thread_ids_sha256(thread_ids: frozenset[str]) -> str:
    canonical = json.dumps(
        sorted(thread_ids), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _remaining(deadline: float, clock: Callable[[], float]) -> float:
    remaining = deadline - clock()
    if remaining <= 0:
        raise ObserverError("approval observation timed out")
    return remaining


class RpcSession:
    """Small JSON-RPC session that intentionally cannot answer server requests."""

    def __init__(self, transport: Any, *, clock: Callable[[], float] = time.monotonic):
        self.transport = transport
        self.clock = clock
        self.next_id = 1
        self.inbox: deque[dict[str, Any]] = deque()

    def __enter__(self) -> RpcSession:
        self.transport.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.transport.close()

    def initialize(self, deadline: float) -> None:
        self.transport.send_json(
            {
                "id": 0,
                "method": "initialize",
                "params": {
                    "capabilities": {"experimentalApi": True},
                    "clientInfo": {
                        "name": "lift-approval-observer",
                        "title": "Lift approval observer",
                        "version": "0.1.0",
                    },
                },
            }
        )
        result = self._await_response(0, deadline)
        if (
            not isinstance(result, dict)
            or result.get("codexHome") != str(codex_project.CODEX_HOME)
        ):
            raise ObserverError("Codex App Server initialized with an unexpected home")
        self.transport.send_json({"method": "initialized", "params": {}})

    def call(self, method: str, params: dict[str, Any], deadline: float) -> Any:
        request_id = self.next_id
        self.next_id += 1
        self.transport.send_json(
            {"id": request_id, "method": method, "params": params}
        )
        return self._await_response(request_id, deadline)

    def _await_response(self, request_id: int, deadline: float) -> Any:
        while True:
            message = self._receive(deadline)
            if message is None:
                continue
            if message.get("id") == request_id and "method" not in message:
                if message.get("error") is not None:
                    raise ObserverError("Codex App Server request failed")
                if "result" not in message:
                    raise ObserverError("Codex App Server response omitted its result")
                return message["result"]
            if "method" in message:
                # Never answer a server request.  Queue it for strict validation.
                self.inbox.append(message)
                continue
            raise ObserverError("Codex App Server returned an unexpected response")

    def next_message(self, deadline: float) -> dict[str, Any] | None:
        if self.inbox:
            return self.inbox.popleft()
        return self._receive(deadline)

    def _receive(self, deadline: float) -> dict[str, Any] | None:
        wait = min(_remaining(deadline, self.clock), SOCKET_POLL_SECONDS)
        connection = getattr(self.transport, "socket", None)
        if connection is not None and hasattr(connection, "settimeout"):
            connection.settimeout(wait)
        try:
            message = self.transport.receive_json()
        except (TimeoutError, socket.timeout):
            return None
        except codex_project.ConnectorError as exc:
            if isinstance(exc.__cause__, (TimeoutError, socket.timeout)):
                return None
            raise ObserverError("Codex App Server transport failed") from exc
        if not isinstance(message, dict):
            raise ObserverError("Codex App Server returned a non-object message")
        return message


def _folder_thread_identity(
    thread: Any,
    workspace: Path,
) -> tuple[str, int]:
    if not isinstance(thread, dict):
        raise ObserverError("thread/list returned an invalid thread")
    thread_id = _validated_id(thread.get("id"), "thread ID")
    created_at = _validated_epoch(thread.get("createdAt"), "thread creation time")
    project_id = thread.get("projectId")
    if project_id is not None and (not isinstance(project_id, str) or not project_id):
        raise ObserverError("thread/list returned an invalid project assignment")
    if thread.get("cwd") != str(workspace):
        raise ObserverError("thread/list returned a thread outside the exact folder")
    return thread_id, created_at


def _controller_thread_identity(
    thread: Any,
    workspace: Path,
) -> tuple[str, int]:
    thread_id, created_at = _folder_thread_identity(thread, workspace)
    if thread.get("projectId") is not None:
        raise ObserverError("controller thread is not project-unassigned")
    return thread_id, created_at


def _list_fresh_threads(
    rpc: RpcSession,
    workspace: Path,
    created_after: int,
    baseline_thread_ids: frozenset[str],
    deadline: float,
) -> list[dict[str, Any]]:
    cursor: str | None = None
    seen: set[str] = set()
    fresh: list[dict[str, Any]] = []
    for _ in range(MAX_THREAD_PAGES):
        result = rpc.call(
            "thread/list",
            {
                "cursor": cursor,
                "cwd": str(workspace),
                "limit": MAX_THREADS_PER_PAGE,
                "sortDirection": "asc",
                "sortKey": "created_at",
            },
            deadline,
        )
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ObserverError("thread/list returned an invalid result")
        for thread in result["data"]:
            thread_id, created_at = _folder_thread_identity(thread, workspace)
            if thread_id in seen:
                raise ObserverError("thread/list returned a duplicate thread")
            seen.add(thread_id)
            if thread_id not in baseline_thread_ids and created_at >= created_after:
                _controller_thread_identity(thread, workspace)
                fresh.append(thread)
        cursor = result.get("nextCursor")
        if cursor is None:
            return fresh
        if not isinstance(cursor, str) or not cursor:
            raise ObserverError("thread/list returned an invalid cursor")
    raise ObserverError("thread/list pagination exceeded the safety limit")


def _validate_resume(
    result: Any,
    thread_id: str,
    workspace: Path,
) -> None:
    if not isinstance(result, dict):
        raise ObserverError("thread/resume returned an invalid result")
    thread = result.get("thread")
    observed_id, _ = _controller_thread_identity(thread, workspace)
    if observed_id != thread_id or thread.get("turns") != []:
        raise ObserverError("thread/resume changed thread identity or returned turns")
    if result.get("cwd") != str(workspace):
        raise ObserverError("thread/resume returned an unexpected cwd")
    if result.get("runtimeWorkspaceRoots") != [str(workspace)]:
        raise ObserverError("thread/resume returned unexpected workspace roots")
    if result.get("approvalPolicy") != "on-request":
        raise ObserverError("approval observer requires the on-request policy")
    if result.get("approvalsReviewer") != "user":
        raise ObserverError("approval observer requires the user reviewer")
    sandbox = result.get("sandbox")
    if (
        not isinstance(sandbox, dict)
        or sandbox.get("type") not in {"readOnly", "workspaceWrite"}
        or sandbox.get("networkAccess") is not False
    ):
        raise ObserverError("approval observer requires a network-disabled sandbox")


def _inner_command_sha256(command: Any) -> str:
    try:
        inner = codex_project.unified_exec_inner_command(command)
    except codex_project.ConnectorError as exc:
        raise ObserverError("approval command used an unexpected wrapper") from exc
    return hashlib.sha256(inner.encode("utf-8")).hexdigest()


def _validate_command_item(
    item: Any,
    *,
    item_id: str,
    workspace: Path,
    expected_sha256: str,
    completed: bool,
) -> None:
    if not isinstance(item, dict) or item.get("type") != "commandExecution":
        raise ObserverError("approval command item has the wrong type")
    if item.get("id") != item_id:
        raise ObserverError("approval command item ID changed")
    if item.get("cwd") != str(workspace):
        raise ObserverError("approval command cwd changed")
    if _inner_command_sha256(item.get("command")) != expected_sha256:
        raise ObserverError("approval command hash changed")
    source = item.get("source")
    if completed:
        if source != codex_project.UNIFIED_EXEC_COMMAND_SOURCE:
            raise ObserverError(
                "completed approval command did not originate from unified exec startup"
            )
    elif source not in PENDING_UNIFIED_EXEC_SOURCES:
        raise ObserverError("pending approval command has unexpected provenance")
    if item.get("pluginId") is not None or item.get("scriptPath") is not None:
        raise ObserverError("approval command has plugin or script provenance")
    if completed and (item.get("status") != "completed" or item.get("exitCode") != 0):
        raise ObserverError("approved command did not complete successfully")


def _validate_turn_summary(
    turn: dict[str, Any],
    *,
    last_agent_message_id: str,
) -> None:
    expected_turn_keys = {
        "completedAt",
        "durationMs",
        "error",
        "id",
        "items",
        "itemsView",
        "startedAt",
        "status",
    }
    if set(turn) != expected_turn_keys:
        raise ObserverError("turn/completed returned an unexpected turn schema")
    items = turn.get("items")
    if turn.get("itemsView") != "summary" or not isinstance(items, list):
        raise ObserverError("turn/completed omitted its source-authentic summary")
    if len(items) != 1 or not isinstance(items[0], dict):
        raise ObserverError("turn/completed returned an ambiguous summary")
    item = items[0]
    if set(item) != {
        "delivery",
        "id",
        "memoryCitation",
        "phase",
        "text",
        "type",
    }:
        raise ObserverError("turn/completed returned an unexpected summary item schema")
    text = item.get("text")
    if (
        item.get("type") != "agentMessage"
        or _validated_id(item.get("id"), "summary agent message ID")
        != last_agent_message_id
        or not isinstance(text, str)
        or not text.strip()
        or item.get("phase") not in {None, "final_answer"}
        or item.get("memoryCitation") is not None
        or item.get("delivery") is not None
    ):
        raise ObserverError("turn/completed summary did not match the observed final answer")


class ApprovalLifecycle:
    def __init__(
        self,
        *,
        thread_id: str,
        workspace: Path,
        project_id: str,
        environment_id: str,
        approval_sha256: str,
        proof_sha256: str,
        created_after: int,
        challenge_sha256: str,
        approval_guard_sha256: str,
        baseline_thread_ids_sha256: str,
    ) -> None:
        self.thread_id = thread_id
        self.workspace = workspace
        self.project_id = project_id
        self.environment_id = environment_id
        self.approval_sha256 = approval_sha256
        self.proof_sha256 = proof_sha256
        self.created_after = created_after
        self.challenge_sha256 = challenge_sha256
        self.approval_guard_sha256 = approval_guard_sha256
        self.baseline_thread_ids_sha256 = baseline_thread_ids_sha256
        self.turn_id: str | None = None
        self.approval_item_id: str | None = None
        self.proof_item_id: str | None = None
        self.request_id: str | int | None = None
        self.request_environment_id: str | None = None
        self.request_started_at_ms: int | None = None
        self.resolved = False
        self.approval_started_at_ms: int | None = None
        self.approval_completed_at_ms: int | None = None
        self.proof_started_at_ms: int | None = None
        self.proof_completed_at_ms: int | None = None
        self.started_command_ids: set[str] = set()
        self.last_agent_message_id: str | None = None
        self.goal_cleared_count = 0
        self.thread_name_updated_count = 0

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        if not isinstance(method, str):
            raise ObserverError("Codex App Server sent an unexpected response")
        params = message.get("params")
        if not isinstance(params, dict):
            raise ObserverError("Codex App Server event omitted params")

        message_thread_id = params.get("threadId")
        if isinstance(message_thread_id, str) and message_thread_id != self.thread_id:
            if "id" in message:
                raise ObserverError("observer received a request for another thread")
            return None
        if "id" in message:
            return self._handle_server_request(message, method, params)
        if method == "serverRequest/resolved":
            self._handle_resolved(params)
            return None
        if method == "thread/goal/cleared":
            self._handle_thread_goal_cleared(params)
            return None
        if method == "thread/name/updated":
            self._handle_thread_name_updated(params)
            return None
        if any(fragment in method for fragment in FORBIDDEN_METHOD_FRAGMENTS):
            raise ObserverError("approval turn emitted an unexpected tool or mutation event")
        if method == "item/started":
            self._handle_item_started(params)
            return None
        if method == "item/completed":
            return self._handle_item_completed(params)
        if method == "item/commandExecution/outputDelta":
            self._handle_command_delta(params)
            return None
        if method == "item/commandExecution/terminalInteraction":
            raise ObserverError("approval command requested terminal interaction")
        if method == "turn/started":
            self._handle_turn_started(params)
            return None
        if method == "turn/completed":
            return self._handle_turn_completed(params)
        if method in BENIGN_THREAD_NOTIFICATIONS or method.startswith(
            BENIGN_ITEM_NOTIFICATION_PREFIXES
        ):
            return None
        if message_thread_id == self.thread_id:
            safe_method = (
                method
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,127}", method)
                else "invalid-method"
            )
            raise ObserverError(
                f"approval turn emitted an unexpected event: {safe_method}"
            )
        return None

    def _handle_thread_goal_cleared(self, params: dict[str, Any]) -> None:
        if set(params) != {"threadId"} or params.get("threadId") != self.thread_id:
            raise ObserverError("thread goal snapshot was not exactly bound")
        if (
            self.goal_cleared_count >= MAX_GOAL_CLEARED_SNAPSHOTS
            or self.request_id is not None
            or self.approval_started_at_ms is not None
            or self.approval_completed_at_ms is not None
            or self.proof_started_at_ms is not None
            or self.proof_completed_at_ms is not None
        ):
            raise ObserverError("thread goal snapshot exceeded its bound or was late")
        self.goal_cleared_count += 1

    def _handle_thread_name_updated(self, params: dict[str, Any]) -> None:
        if set(params) != {"threadId", "threadName"}:
            raise ObserverError("thread name update schema was not exact")
        name = params.get("threadName")
        if (
            params.get("threadId") != self.thread_id
            or not isinstance(name, str)
            or not name
            or name != name.strip()
            or "\x00" in name
            or len(name.encode("utf-8")) > MAX_ID_BYTES
        ):
            raise ObserverError("thread name update was not exactly bound")
        if self.thread_name_updated_count >= 1:
            raise ObserverError("thread name update was ambiguous")
        self.thread_name_updated_count += 1

    def _handle_server_request(
        self,
        message: dict[str, Any],
        method: str,
        params: dict[str, Any],
    ) -> None:
        if method != "item/commandExecution/requestApproval" or self.request_id is not None:
            raise ObserverError("observer received an unexpected or ambiguous server request")
        request_id = _validated_request_id(message.get("id"))
        thread_id = _validated_id(params.get("threadId"), "approval thread ID")
        turn_id = _validated_id(params.get("turnId"), "approval turn ID")
        item_id = _validated_id(params.get("itemId"), "approval item ID")
        started_at_ms = _validated_epoch(
            params.get("startedAtMs"), "approval request start time"
        )
        if thread_id != self.thread_id:
            raise ObserverError("approval request thread changed")
        if started_at_ms < self.created_after * 1000:
            raise ObserverError("approval request predates the thread baseline")
        if params.get("environmentId") != REQUEST_EXECUTION_ENVIRONMENT_ID:
            raise ObserverError("approval request environment changed")
        if params.get("cwd") != str(self.workspace):
            raise ObserverError("approval request cwd changed")
        if _inner_command_sha256(params.get("command")) != self.approval_sha256:
            raise ObserverError("approval request command hash did not match")
        if params.get("kind", "command") != "command":
            raise ObserverError("approval request was not a command approval")
        if params.get("approvalId") is not None:
            raise ObserverError("approval request used an unexpected callback kind")
        if params.get("networkApprovalContext") is not None:
            raise ObserverError("approval request was a managed-network approval")
        if any(
            params.get(key) is not None
            for key in (
                "additionalPermissions",
                "proposedNetworkPolicyAmendments",
            )
        ):
            raise ObserverError("approval request proposed extra permissions")
        amendment = params.get("proposedExecpolicyAmendment")
        if (
            not isinstance(amendment, list)
            or not amendment
            or not all(
                isinstance(part, str)
                and part
                and part == part.strip()
                and "\x00" not in part
                and len(part.encode("utf-8")) <= MAX_ID_BYTES
                for part in amendment
            )
        ):
            raise ObserverError("approval request amendment was not source-authentic")
        expected_decisions = [
            "accept",
            {
                "acceptWithExecpolicyAmendment": {
                    "execpolicy_amendment": amendment,
                }
            },
            "cancel",
        ]
        if params.get("availableDecisions") != expected_decisions:
            raise ObserverError("approval request offered an unexpected decision set")
        if self.turn_id is not None and self.turn_id != turn_id:
            raise ObserverError("approval request turn changed")
        if self.approval_item_id is not None and self.approval_item_id != item_id:
            raise ObserverError("approval request item changed")
        if self.approval_completed_at_ms is not None:
            raise ObserverError("approval request arrived after command completion")
        if (
            self.approval_started_at_ms is None
            or self.approval_item_id != item_id
            or started_at_ms > self.approval_started_at_ms
            or self.approval_started_at_ms - started_at_ms
            > MAX_REQUEST_TO_ITEM_START_LAG_MILLISECONDS
        ):
            raise ObserverError("approval request and command start were not source-ordered")
        self.turn_id = turn_id
        self.approval_item_id = item_id
        self.request_id = request_id
        self.request_environment_id = REQUEST_EXECUTION_ENVIRONMENT_ID
        self.request_started_at_ms = started_at_ms
        return None

    def _handle_resolved(self, params: dict[str, Any]) -> None:
        if self.request_id is None or self.resolved:
            raise ObserverError("approval resolution was missing or ambiguous")
        if (
            params.get("threadId") != self.thread_id
            or _validated_request_id(params.get("requestId")) != self.request_id
        ):
            raise ObserverError("approval resolution did not match the request")
        self.resolved = True

    def _handle_turn_started(self, params: dict[str, Any]) -> None:
        if params.get("threadId") != self.thread_id:
            raise ObserverError("turn/started changed thread identity")
        turn = params.get("turn")
        if not isinstance(turn, dict):
            raise ObserverError("turn/started omitted its turn")
        turn_id = _validated_id(turn.get("id"), "turn ID")
        if self.turn_id is not None and self.turn_id != turn_id:
            raise ObserverError("observer saw multiple turns")
        self.turn_id = turn_id

    def _handle_item_started(self, params: dict[str, Any]) -> None:
        self._validate_lifecycle_binding(params)
        item = params.get("item")
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ObserverError("item/started omitted its item")
        if item["type"] == "commandExecution":
            candidate_id = _validated_id(item.get("id"), "command item ID")
            started_at_ms = _validated_epoch(
                params.get("startedAtMs"), "command start time"
            )
            if candidate_id in self.started_command_ids:
                raise ObserverError("approval turn repeated a command start")
            command_sha256 = _inner_command_sha256(item.get("command"))
            if command_sha256 == self.approval_sha256:
                if (
                    self.approval_item_id is not None
                    and self.approval_item_id != candidate_id
                ):
                    raise ObserverError("approval command item identity changed")
                if self.proof_item_id is not None:
                    raise ObserverError("approval command started after the proof command")
                if self.request_id is not None or self.request_started_at_ms is not None:
                    raise ObserverError("approval command start arrived after its request")
                self.approval_item_id = candidate_id
                self.approval_started_at_ms = started_at_ms
                expected_sha256 = self.approval_sha256
            elif command_sha256 == self.proof_sha256:
                if self.approval_completed_at_ms is None:
                    raise ObserverError("proof command started before approval command success")
                if started_at_ms < self.approval_completed_at_ms:
                    raise ObserverError("proof command timestamp predates approval success")
                if self.proof_item_id is not None and self.proof_item_id != candidate_id:
                    raise ObserverError("proof command item identity changed")
                self.proof_item_id = candidate_id
                self.proof_started_at_ms = started_at_ms
                expected_sha256 = self.proof_sha256
            else:
                raise ObserverError("approval turn contains another command")
            self.started_command_ids.add(candidate_id)
            _validate_command_item(
                item,
                item_id=candidate_id,
                workspace=self.workspace,
                expected_sha256=expected_sha256,
                completed=False,
            )
        elif item["type"] not in BENIGN_ITEM_TYPES:
            raise ObserverError("approval turn contains an unexpected tool or mutation")

    def _handle_item_completed(self, params: dict[str, Any]) -> dict[str, Any] | None:
        self._validate_lifecycle_binding(params)
        item = params.get("item")
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ObserverError("item/completed omitted its item")
        if item["type"] == "commandExecution":
            candidate_id = _validated_id(item.get("id"), "command item ID")
            command_sha256 = _inner_command_sha256(item.get("command"))
            completed_at_ms = _validated_epoch(
                params.get("completedAtMs"),
                "command completion time",
            )
            if command_sha256 == self.approval_sha256:
                if (
                    self.request_id is None
                    or not self.resolved
                    or self.approval_completed_at_ms is not None
                    or self.approval_item_id != candidate_id
                    or self.request_started_at_ms is None
                ):
                    raise ObserverError("approval command completed out of protocol order")
                if completed_at_ms < self.request_started_at_ms:
                    raise ObserverError("approval command completed before its request")
                if (
                    self.approval_started_at_ms is not None
                    and completed_at_ms < self.approval_started_at_ms
                ):
                    raise ObserverError("approval command completed before its start")
                expected_sha256 = self.approval_sha256
                self.approval_completed_at_ms = completed_at_ms
            elif command_sha256 == self.proof_sha256:
                if (
                    self.approval_completed_at_ms is None
                    or self.proof_started_at_ms is None
                    or self.proof_completed_at_ms is not None
                    or self.proof_item_id != candidate_id
                    or completed_at_ms < self.approval_completed_at_ms
                    or completed_at_ms < self.proof_started_at_ms
                ):
                    raise ObserverError("proof command completed out of protocol order")
                expected_sha256 = self.proof_sha256
                self.proof_completed_at_ms = completed_at_ms
            else:
                raise ObserverError("approval turn contains another command")
            _validate_command_item(
                item,
                item_id=candidate_id,
                workspace=self.workspace,
                expected_sha256=expected_sha256,
                completed=True,
            )
        elif item["type"] == "agentMessage":
            candidate_id = _validated_id(
                item.get("id"), "completed agent message ID"
            )
            text = item.get("text")
            phase = item.get("phase")
            if not isinstance(text, str) or phase not in {
                None,
                "commentary",
                "final_answer",
            }:
                raise ObserverError("completed agent message schema was invalid")
            if phase in {None, "final_answer"} and text.strip():
                self.last_agent_message_id = candidate_id
        elif item["type"] not in BENIGN_ITEM_TYPES:
            raise ObserverError("approval turn contains an unexpected tool or mutation")
        return None

    def _handle_command_delta(self, params: dict[str, Any]) -> None:
        self._validate_lifecycle_binding(params)
        item_id = params.get("itemId")
        approval_output = item_id == self.approval_item_id and self.resolved
        proof_output = (
            item_id == self.proof_item_id
            and self.approval_completed_at_ms is not None
        )
        if not approval_output and not proof_output:
            raise ObserverError("command output was not bound to the approved command")

    def _validate_lifecycle_binding(self, params: dict[str, Any]) -> None:
        if params.get("threadId") != self.thread_id:
            raise ObserverError("item lifecycle changed thread identity")
        turn_id = _validated_id(params.get("turnId"), "item lifecycle turn ID")
        if self.turn_id is not None and self.turn_id != turn_id:
            raise ObserverError("item lifecycle changed turn identity")
        self.turn_id = turn_id

    def _handle_turn_completed(self, params: dict[str, Any]) -> dict[str, Any]:
        if (
            self.goal_cleared_count == 0
            or self.request_id is None
            or not self.resolved
            or self.approval_completed_at_ms is None
            or self.proof_completed_at_ms is None
            or self.approval_item_id is None
            or self.proof_item_id is None
            or self.request_started_at_ms is None
            or self.request_environment_id is None
            or self.last_agent_message_id is None
        ):
            raise ObserverError("turn completed before the exact approval lifecycle")
        if params.get("threadId") != self.thread_id:
            raise ObserverError("turn/completed changed thread identity")
        if set(params) != {"threadId", "turn"}:
            raise ObserverError("turn/completed returned an unexpected event schema")
        turn = params.get("turn")
        if not isinstance(turn, dict):
            raise ObserverError("turn/completed omitted its turn")
        if turn.get("id") != self.turn_id or turn.get("status") != "completed":
            raise ObserverError("approval turn did not complete successfully")
        if turn.get("error") is not None:
            raise ObserverError("approval turn completed with an error")
        _validate_turn_summary(
            turn,
            last_agent_message_id=self.last_agent_message_id,
        )
        started_at = _validated_epoch(turn.get("startedAt"), "turn start time")
        completed_at = _validated_epoch(
            turn.get("completedAt"), "turn completion time"
        )
        duration_ms = _validated_epoch(turn.get("durationMs"), "turn duration")
        if completed_at < started_at or duration_ms < 0:
            raise ObserverError("turn/completed returned invalid timing metadata")
        if completed_at < self.proof_completed_at_ms // 1000:
            raise ObserverError("turn completed before the proof command")
        return {
            "approvalGuardSha256": self.approval_guard_sha256,
            "approvalCommandStartedAtEpochMilliseconds": self.approval_started_at_ms,
            "approvalCommandCompletedAtEpochMilliseconds": (
                self.approval_completed_at_ms
            ),
            "approvalCommandSha256": self.approval_sha256,
            "approvalItemId": self.approval_item_id,
            "baselineThreadIdsSha256": self.baseline_thread_ids_sha256,
            "challengeSha256": self.challenge_sha256,
            "controllerThreadBinding": codex_project.CONTROLLER_THREAD_BINDING,
            "controllerThreadProjectId": None,
            "createdAfterEpochSeconds": self.created_after,
            "cwd": str(self.workspace),
            "environmentId": self.environment_id,
            "nativeProjectId": self.project_id,
            "observedAtEpochSeconds": int(time.time()),
            "proofCommandCompletedAtEpochMilliseconds": self.proof_completed_at_ms,
            "proofCommandStartedAtEpochMilliseconds": self.proof_started_at_ms,
            "proofCommandSha256": self.proof_sha256,
            "proofItemId": self.proof_item_id,
            "requestId": self.request_id,
            "requestEnvironmentId": self.request_environment_id,
            "requestStartedAtEpochMilliseconds": self.request_started_at_ms,
            "schemaVersion": SCHEMA_VERSION,
            "threadId": self.thread_id,
            "threadGoalClearedCount": self.goal_cleared_count,
            "threadNameUpdatedCount": self.thread_name_updated_count,
            "turnCompletedAtEpochSeconds": completed_at,
            "turnId": self.turn_id,
            "verificationMethod": VERIFICATION_METHOD,
        }

def observe_approval(
    rpc: RpcSession,
    *,
    workspace: Path,
    project_id: str,
    environment_id: str,
    created_after: int,
    baseline_thread_ids: frozenset[str],
    expected_approval_command_sha256: str,
    expected_proof_command_sha256: str,
    challenge_sha256: str,
    approval_guard_sha256: str,
    timeout_seconds: float,
    ready: Callable[[dict[str, Any]], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    project_id = _validated_id(project_id, "native project ID")
    environment_id = _validated_id(environment_id, "environment ID")
    created_after = _validated_epoch(created_after, "created-after")
    expected_approval_command_sha256 = _validated_sha256(
        expected_approval_command_sha256
    )
    expected_proof_command_sha256 = _validated_sha256(expected_proof_command_sha256)
    if expected_approval_command_sha256 == expected_proof_command_sha256:
        raise ObserverError("approval and proof command hashes must differ")
    challenge_sha256 = _validated_sha256(challenge_sha256)
    approval_guard_sha256 = _validated_sha256(approval_guard_sha256)
    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ObserverError("timeout must be greater than zero and at most one hour")
    baseline_thread_ids = frozenset(
        _validated_id(thread_id, "baseline thread ID")
        for thread_id in baseline_thread_ids
    )
    deadline = clock() + timeout_seconds
    rpc.initialize(deadline)
    baseline_thread_ids_sha256 = _thread_ids_sha256(baseline_thread_ids)

    initial_candidates = _list_fresh_threads(
        rpc,
        workspace,
        created_after,
        baseline_thread_ids,
        deadline,
    )
    if initial_candidates:
        raise ObserverError("a fresh post-baseline thread existed before observer readiness")
    if ready is not None:
        ready(
            {
                "approvalGuardSha256": approval_guard_sha256,
                "baselineThreadIdsSha256": baseline_thread_ids_sha256,
                "challengeSha256": challenge_sha256,
                "controllerThreadBinding": codex_project.CONTROLLER_THREAD_BINDING,
                "controllerThreadProjectId": None,
                "approvalCommandSha256": expected_approval_command_sha256,
                "createdAfterEpochSeconds": created_after,
                "cwd": str(workspace),
                "environmentId": environment_id,
                "nativeProjectId": project_id,
                "proofCommandSha256": expected_proof_command_sha256,
                "schemaVersion": SCHEMA_VERSION,
                "verificationMethod": READY_VERIFICATION_METHOD,
            }
        )

    candidate: dict[str, Any] | None = None
    while candidate is None:
        candidates = _list_fresh_threads(
            rpc,
            workspace,
            created_after,
            baseline_thread_ids,
            deadline,
        )
        if len(candidates) > 1:
            raise ObserverError("multiple fresh post-baseline threads are ambiguous")
        if candidates:
            candidate = candidates[0]
            break
        sleep(min(POLL_INTERVAL_SECONDS, _remaining(deadline, clock)))

    thread_id, _ = _controller_thread_identity(candidate, workspace)
    resume = rpc.call(
        "thread/resume",
        {"excludeTurns": True, "threadId": thread_id},
        deadline,
    )
    _validate_resume(resume, thread_id, workspace)

    lifecycle = ApprovalLifecycle(
        thread_id=thread_id,
        workspace=workspace,
        project_id=project_id,
        environment_id=environment_id,
        approval_sha256=expected_approval_command_sha256,
        proof_sha256=expected_proof_command_sha256,
        created_after=created_after,
        challenge_sha256=challenge_sha256,
        approval_guard_sha256=approval_guard_sha256,
        baseline_thread_ids_sha256=baseline_thread_ids_sha256,
    )
    evidence: dict[str, Any] | None = None
    while evidence is None:
        message = rpc.next_message(deadline)
        if message is None:
            continue
        evidence = lifecycle.handle(message)

    final_candidates = _list_fresh_threads(
        rpc,
        workspace,
        created_after,
        baseline_thread_ids,
        deadline,
    )
    final_ids = {
        _controller_thread_identity(item, workspace)[0]
        for item in final_candidates
    }
    if final_ids != {thread_id}:
        raise ObserverError("fresh post-baseline thread set changed during observation")
    return evidence


def atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    if not path.is_absolute():
        raise ObserverError("output path must be absolute")
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
        resolved_parent = parent.resolve(strict=True)
    except OSError as exc:
        raise ObserverError("cannot inspect output directory") from exc
    if (
        stat.S_ISLNK(parent_metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or resolved_parent != parent
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise ObserverError("output directory is not private and trusted")
    if path.exists() or path.is_symlink():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise ObserverError("cannot inspect existing output") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ObserverError("existing output is not a private regular file")
    payload = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8") + b"\n"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ObserverError("approval evidence exceeds the output limit")
    descriptor = -1
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = ""
        os.chmod(path, 0o600, follow_symlinks=False)
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise ObserverError("cannot atomically write approval evidence") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--created-after", required=True, type=int)
    parser.add_argument("--baseline-thread-id", action="append", default=[])
    parser.add_argument("--expected-approval-command-sha256", required=True)
    parser.add_argument("--expected-proof-command-sha256", required=True)
    parser.add_argument("--challenge-sha256", required=True)
    parser.add_argument("--approval-guard-sha256", required=True)
    parser.add_argument("--ready-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        workspace = codex_project.validated_workspace(args.workspace)
        transport = codex_project.UnixWebSocket(
            codex_project.CONTROL_SOCKET,
            timeout_seconds=max(1, min(args.timeout, 10)),
        )
        with RpcSession(transport) as rpc:
            evidence = observe_approval(
                rpc,
                workspace=workspace,
                project_id=args.project_id,
                environment_id=args.environment_id,
                created_after=args.created_after,
                baseline_thread_ids=frozenset(args.baseline_thread_id),
                expected_approval_command_sha256=(
                    args.expected_approval_command_sha256
                ),
                expected_proof_command_sha256=args.expected_proof_command_sha256,
                challenge_sha256=args.challenge_sha256,
                approval_guard_sha256=args.approval_guard_sha256,
                timeout_seconds=args.timeout,
                ready=lambda value: atomic_private_json(args.ready_output, value),
            )
        atomic_private_json(args.output, evidence)
        print(json.dumps({"observed": True, "output": str(args.output)}, sort_keys=True))
        return 0
    except (ObserverError, codex_project.ConnectorError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
