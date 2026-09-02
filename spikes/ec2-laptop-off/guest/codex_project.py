#!/usr/bin/env python3
"""Version-pinned Codex project registration for the Lift EC2 spike.

This connector is recipe-specific. The generic Lift runner only invokes its
reviewed process specs. The connector talks to Codex's own experimental App
Server project API and never reads or writes Codex's SQLite database directly.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import stat
import struct
import subprocess
import tempfile
import time
import tomllib
from typing import Any
import uuid


EXPECTED_CODEX_VERSION = "0.152.1"
CODEX_PATH = Path("/home/lift/.local/bin/codex")
CODEX_HOME = Path("/home/lift/.codex")
CONTROL_SOCKET = CODEX_HOME / "app-server-control" / "app-server-control.sock"
CONFIG_PATH = CODEX_HOME / "config.toml"
WORKSPACE_ROOT = Path("/home/lift/workspaces")
STATE_ROOT = CODEX_HOME / "lift"
STATE_FILE_NAME = "codex-project.json"
WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_STATE_BYTES = 64 * 1024
CLIENT_INFO = {"name": "lift", "title": "Lift", "version": "0.1.0"}
MAX_HTTP_HEADER_BYTES = 16 * 1024
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_PLUGIN_MESSAGE_BYTES = 16 * 1024 * 1024
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_THREAD_PAGES = 100
MAX_THREADS_PER_PAGE = 100
MAX_PROOF_CANDIDATES = 100
MAX_PROOF_PATH_BYTES = 4096
NONCE_PATTERN = re.compile(r"^[0-9A-Fa-f]{16,128}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_CONFIG_LAYERS = 64
MAX_CONFIG_LAYER_BYTES = 1024 * 1024
MAX_HOOKS = 256
MAX_HOOK_STATE_BYTES = 1024 * 1024
MAX_PLUGIN_MARKETPLACES = 64
MAX_PLUGINS = 8192
MAX_PLUGIN_STATE_BYTES = 16 * 1024 * 1024
APPROVAL_VERIFICATION_METHOD = (
    "fresh-folder-bound-project-unassigned-single-turn-exact-two-wrapped-command-"
    "network-denied-user-reviewer-no-rules-hooks-plugin-state-bound-no-plugin-"
    "provenance-or-mcp-tools-v6"
)
CONTROLLER_THREAD_BINDING = "folder-bound-project-unassigned-v1"
UNIFIED_EXEC_COMMAND_SOURCE = "unifiedExecStartup"
UNIFIED_EXEC_SHELL = "/bin/bash"
UNIFIED_EXEC_SHELL_ARGUMENT = "-lc"
APPROVAL_PROOF_TURN_ITEM_TYPES = {
    "agentMessage",
    "commandExecution",
    "plan",
    "reasoning",
    "userMessage",
}


class ConnectorError(RuntimeError):
    pass


def contained_path(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validated_workspace(raw_path: str | None) -> Path:
    if not raw_path:
        raise ConnectorError("LIFT_WORKSPACE is required")
    candidate = Path(raw_path)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ConnectorError("workspace must be an absolute real directory")
    try:
        workspace = candidate.resolve(strict=True)
        root = WORKSPACE_ROOT.resolve(strict=True)
    except OSError as exc:
        raise ConnectorError(f"cannot resolve workspace: {exc}") from exc
    if workspace != candidate or workspace == root or not contained_path(workspace, root):
        raise ConnectorError(f"workspace must be a direct real path below {root}")
    if not workspace.is_dir():
        raise ConnectorError("workspace is not a directory")
    current = workspace
    while current != root:
        if current.is_symlink():
            raise ConnectorError(f"workspace parent cannot be a symlink: {current}")
        current = current.parent
    return workspace


def _directory_metadata(path: Path, description: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ConnectorError(f"cannot inspect {description}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ConnectorError(f"{description} must be a real directory")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ConnectorError(f"cannot resolve {description}: {exc}") from exc
    if resolved != path:
        raise ConnectorError(f"{description} cannot contain a symlink")
    if metadata.st_uid != os.geteuid():
        raise ConnectorError(f"{description} must be owned by the connector user")
    return metadata


def _provider_state_parent() -> Path:
    parent = STATE_ROOT.parent
    metadata = _directory_metadata(parent, "Codex home")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise ConnectorError("Codex home cannot be group- or world-writable")
    return parent


def _private_directory(path: Path, description: str, *, create: bool) -> None:
    if not path.exists() and not path.is_symlink():
        if not create:
            raise ConnectorError("Codex project registration state is missing")
        try:
            path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        except OSError as exc:
            raise ConnectorError(f"cannot create {description}: {exc}") from exc
    metadata = _directory_metadata(path, description)
    if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE:
        raise ConnectorError(f"{description} must have mode 0700")


def connector_state_path(workspace: Path) -> Path:
    workspace_id = workspace.name
    if not WORKSPACE_ID_PATTERN.fullmatch(workspace_id):
        raise ConnectorError("workspace ID is invalid for connector state")
    return STATE_ROOT / workspace_id / STATE_FILE_NAME


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_descriptor = os.open(path.parent, directory_flags)
    except OSError as exc:
        raise ConnectorError(f"cannot open connector state directory: {exc}") from exc
    temporary_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        file_flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(
            temporary_name,
            file_flags,
            PRIVATE_FILE_MODE,
            dir_fd=directory_descriptor,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        os.fsync(directory_descriptor)
    except OSError as exc:
        raise ConnectorError(f"cannot persist connector state: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_descriptor)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory_descriptor)


def validate_state_parent(workspace: Path, *, create: bool) -> Path:
    _provider_state_parent()
    _private_directory(STATE_ROOT, "Lift connector state root", create=create)
    workspace_state = connector_state_path(workspace).parent
    _private_directory(
        workspace_state,
        "Lift workspace connector state directory",
        create=create,
    )
    return workspace_state


def new_state(workspace: Path) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "workspace": str(workspace),
        "workspaceId": workspace.name,
        "idempotencyKey": str(uuid.uuid4()),
    }


def validated_state(path: Path, workspace: Path, *, create: bool) -> dict[str, Any]:
    if path != connector_state_path(workspace):
        raise ConnectorError("connector state path is not workspace-bound")
    validate_state_parent(workspace, create=create)
    if not path.exists():
        if path.is_symlink():
            raise ConnectorError("connector state file cannot be a symlink")
        if not create:
            raise ConnectorError("Codex project registration state is missing")
        state = new_state(workspace)
        atomic_json(path, state)
        return state
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ConnectorError("connector state file must be a real regular file")
        if path.resolve(strict=True) != path:
            raise ConnectorError("connector state file cannot contain a symlink")
        if metadata.st_uid != os.geteuid():
            raise ConnectorError("connector state file must be owned by the connector user")
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE:
            raise ConnectorError("connector state file must have mode 0600")
        if metadata.st_size > MAX_STATE_BYTES:
            raise ConnectorError("connector state file is unexpectedly large")
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorError(f"cannot read connector state: {exc}") from exc
    if not isinstance(state, dict) or state.get("schemaVersion") != 1:
        raise ConnectorError("unsupported Codex project registration state")
    if state.get("workspace") != str(workspace) or state.get("workspaceId") != workspace.name:
        raise ConnectorError("Codex project registration state belongs to another workspace")
    key = state.get("idempotencyKey")
    try:
        parsed_key = uuid.UUID(key) if isinstance(key, str) else None
    except ValueError as exc:
        raise ConnectorError("Codex project idempotency key is invalid") from exc
    if parsed_key is None or str(parsed_key) != key:
        raise ConnectorError("Codex project idempotency key is invalid")
    project_id = state.get("projectId")
    if project_id is not None and (not isinstance(project_id, str) or not project_id):
        raise ConnectorError("Codex project ID is invalid")
    return state


def _read_capped_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > MAX_MESSAGE_BYTES:
            raise ConnectorError(f"schema file is unexpectedly large: {path.name}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorError(f"cannot read generated schema {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConnectorError(f"generated schema {path.name} is not an object")
    return value


def _method_names(value: Any) -> set[str]:
    methods: set[str] = set()
    if isinstance(value, dict):
        enum = value.get("enum")
        if isinstance(enum, list):
            methods.update(
                item for item in enum if isinstance(item, str) and "/" in item
            )
        for child in value.values():
            methods.update(_method_names(child))
    elif isinstance(value, list):
        for child in value:
            methods.update(_method_names(child))
    return methods


def _schema_definition(schema: dict[str, Any], name: str) -> dict[str, Any]:
    definitions = schema.get("definitions")
    value = definitions.get(name) if isinstance(definitions, dict) else None
    if not isinstance(value, dict):
        raise ConnectorError(f"Codex schema omitted {name}")
    return value


def _require_schema_fields(
    schema: dict[str, Any],
    name: str,
    *,
    properties: set[str],
    required: set[str],
) -> None:
    value = _schema_definition(schema, name)
    observed_properties = value.get("properties")
    observed_required = value.get("required", [])
    if (
        not isinstance(observed_properties, dict)
        or not properties.issubset(observed_properties)
        or not isinstance(observed_required, list)
        or not required.issubset(observed_required)
    ):
        raise ConnectorError(f"Codex {name} schema changed")


def _require_root_schema_fields(
    schema: dict[str, Any],
    name: str,
    *,
    properties: set[str],
    required: set[str],
) -> None:
    observed_properties = schema.get("properties")
    observed_required = schema.get("required", [])
    if (
        not isinstance(observed_properties, dict)
        or not properties.issubset(observed_properties)
        or not isinstance(observed_required, list)
        or not required.issubset(observed_required)
    ):
        raise ConnectorError(f"Codex {name} schema changed")


def _require_command_execution_schema(schema: dict[str, Any]) -> None:
    item = _schema_definition(schema, "ThreadItem")
    variants = item.get("oneOf")
    if not isinstance(variants, list):
        raise ConnectorError("Codex ThreadItem schema changed")
    command_variants: list[dict[str, Any]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        properties = variant.get("properties")
        item_type = properties.get("type") if isinstance(properties, dict) else None
        enum = item_type.get("enum") if isinstance(item_type, dict) else None
        if enum == ["commandExecution"]:
            command_variants.append(variant)
    if len(command_variants) != 1:
        raise ConnectorError("Codex commandExecution schema changed")
    command = command_variants[0]
    properties = command.get("properties")
    required = command.get("required")
    expected_properties = {
        "command",
        "cwd",
        "exitCode",
        "id",
        "pluginId",
        "scriptPath",
        "source",
        "status",
        "type",
    }
    expected_required = {"command", "cwd", "id", "status", "type"}
    if (
        not isinstance(properties, dict)
        or not expected_properties.issubset(properties)
        or not isinstance(required, list)
        or not expected_required.issubset(required)
    ):
        raise ConnectorError("Codex commandExecution schema changed")


def _require_hook_metadata_schema(schema: dict[str, Any]) -> None:
    hook = _schema_definition(schema, "HookMetadata")
    properties = hook.get("properties")
    required = hook.get("required")
    variants = hook.get("oneOf")
    common_properties = {
        "currentHash",
        "enabled",
        "eventName",
        "isManaged",
        "key",
        "pluginId",
        "source",
        "sourcePath",
        "trustStatus",
    }
    common_required = {
        "currentHash",
        "enabled",
        "eventName",
        "isManaged",
        "key",
        "source",
        "sourcePath",
        "trustStatus",
    }
    if (
        not isinstance(properties, dict)
        or not common_properties.issubset(properties)
        or not isinstance(required, list)
        or not common_required.issubset(required)
        or not isinstance(variants, list)
    ):
        raise ConnectorError("Codex HookMetadata schema changed")
    expected_variants = {
        "agent": {"handlerType"},
        "command": {"command", "handlerType"},
        "mcpTool": {"handlerType", "server", "tool"},
        "prompt": {"handlerType"},
    }
    observed_variants: dict[str, set[str]] = {}
    for variant in variants:
        if not isinstance(variant, dict):
            raise ConnectorError("Codex HookMetadata schema changed")
        variant_properties = variant.get("properties")
        variant_required = variant.get("required")
        handler = (
            variant_properties.get("handlerType")
            if isinstance(variant_properties, dict)
            else None
        )
        enum = handler.get("enum") if isinstance(handler, dict) else None
        if (
            not isinstance(variant_required, list)
            or not isinstance(enum, list)
            or len(enum) != 1
            or not isinstance(enum[0], str)
        ):
            raise ConnectorError("Codex HookMetadata schema changed")
        observed_variants[enum[0]] = set(variant_required)
    if observed_variants != expected_variants:
        raise ConnectorError("Codex HookMetadata schema changed")


def validate_experimental_schema() -> None:
    with tempfile.TemporaryDirectory(prefix="lift-codex-schema-") as temporary:
        try:
            completed = subprocess.run(
                [
                    str(CODEX_PATH),
                    "app-server",
                    "generate-json-schema",
                    "--experimental",
                    "--out",
                    temporary,
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConnectorError(f"cannot generate Codex experimental schema: {exc}") from exc
        if completed.returncode != 0:
            raise ConnectorError("Codex experimental schema generation failed")
        schema_root = Path(temporary)
        schema = _read_capped_json(schema_root / "ClientRequest.json")
        list_response = _read_capped_json(
            schema_root / "v2" / "ThreadListResponse.json"
        )
        read_response = _read_capped_json(
            schema_root / "v2" / "ThreadReadResponse.json"
        )
        resume_response = _read_capped_json(
            schema_root / "v2" / "ThreadResumeResponse.json"
        )
        config_read_response = _read_capped_json(
            schema_root / "v2" / "ConfigReadResponse.json"
        )
        config_requirements_read_response = _read_capped_json(
            schema_root / "v2" / "ConfigRequirementsReadResponse.json"
        )
        hooks_list_response = _read_capped_json(
            schema_root / "v2" / "HooksListResponse.json"
        )
        plugin_list_response = _read_capped_json(
            schema_root / "v2" / "PluginListResponse.json"
        )
        server_request = _read_capped_json(schema_root / "ServerRequest.json")
        server_notification = _read_capped_json(
            schema_root / "ServerNotification.json"
        )
    required_methods = {
        "config/read",
        "configRequirements/read",
        "config/value/write",
        "hooks/list",
        "plugin/list",
        "project/create",
        "project/list",
        "project/read",
        "remoteControl/client/list",
        "remoteControl/status/read",
        "thread/list",
        "thread/read",
        "thread/resume",
    }
    missing_methods = sorted(required_methods.difference(_method_names(schema)))
    if missing_methods:
        raise ConnectorError(
            "Codex experimental schema omitted required methods: "
            + ", ".join(missing_methods)
        )
    _require_schema_fields(
        schema,
        "ProjectCreateParams",
        properties={"idempotencyKey", "metadata", "name", "roots"},
        required={"idempotencyKey", "name", "roots"},
    )
    _require_schema_fields(
        schema,
        "ThreadListParams",
        properties={
            "cursor",
            "cwd",
            "limit",
            "projectId",
            "sortDirection",
            "sortKey",
        },
        required=set(),
    )
    _require_schema_fields(
        schema,
        "ThreadReadParams",
        properties={"includeTurns", "threadId"},
        required={"threadId"},
    )
    _require_schema_fields(
        schema,
        "ThreadResumeParams",
        properties={"excludeTurns", "threadId"},
        required={"threadId"},
    )
    _require_root_schema_fields(
        list_response,
        "ThreadListResponse",
        properties={"data", "nextCursor"},
        required={"data"},
    )
    _require_root_schema_fields(
        read_response,
        "ThreadReadResponse",
        properties={"thread"},
        required={"thread"},
    )
    _require_schema_fields(
        read_response,
        "Thread",
        properties={"createdAt", "cwd", "id", "projectId", "turns"},
        required={"createdAt", "cwd", "id", "projectId", "turns"},
    )
    _require_schema_fields(
        read_response,
        "Turn",
        properties={"completedAt", "id", "items", "itemsView", "status"},
        required={"id", "items", "status"},
    )
    _require_command_execution_schema(read_response)
    _require_root_schema_fields(
        resume_response,
        "ThreadResumeResponse",
        properties={
            "approvalPolicy",
            "approvalsReviewer",
            "cwd",
            "runtimeWorkspaceRoots",
            "sandbox",
            "thread",
        },
        required={
            "approvalPolicy",
            "approvalsReviewer",
            "cwd",
            "sandbox",
            "thread",
        },
    )
    _require_schema_fields(
        resume_response,
        "Thread",
        properties={"cwd", "id", "projectId", "turns"},
        required={"cwd", "id", "projectId", "turns"},
    )
    _require_root_schema_fields(
        config_read_response,
        "ConfigReadResponse",
        properties={"config", "layers", "origins"},
        required={"config", "origins"},
    )
    _require_root_schema_fields(
        config_requirements_read_response,
        "ConfigRequirementsReadResponse",
        properties={"requirements"},
        required=set(),
    )
    _require_root_schema_fields(
        hooks_list_response,
        "HooksListResponse",
        properties={"data"},
        required={"data"},
    )
    _require_schema_fields(
        hooks_list_response,
        "HooksListEntry",
        properties={"cwd", "errors", "hooks", "warnings"},
        required={"cwd", "errors", "hooks", "warnings"},
    )
    _require_hook_metadata_schema(hooks_list_response)
    _require_schema_fields(
        schema,
        "PluginListParams",
        properties={"cwds", "forceRefetch", "marketplaceKinds"},
        required=set(),
    )
    _require_root_schema_fields(
        plugin_list_response,
        "PluginListResponse",
        properties={"featuredPluginIds", "marketplaceLoadErrors", "marketplaces"},
        required={"marketplaces"},
    )
    _require_schema_fields(
        plugin_list_response,
        "PluginSummary",
        properties={"enabled", "id", "installed", "name", "source"},
        required={"enabled", "id", "installed", "name", "source"},
    )
    if "item/commandExecution/requestApproval" not in _method_names(server_request):
        raise ConnectorError("Codex approval request schema changed")
    _require_schema_fields(
        server_request,
        "CommandExecutionRequestApprovalParams",
        properties={
            "approvalId",
            "command",
            "cwd",
            "environmentId",
            "itemId",
            "kind",
            "networkApprovalContext",
            "startedAtMs",
            "threadId",
            "turnId",
        },
        required={"itemId", "startedAtMs", "threadId", "turnId"},
    )
    required_notifications = {
        "item/completed",
        "item/started",
        "serverRequest/resolved",
        "turn/completed",
    }
    missing_notifications = sorted(
        required_notifications.difference(_method_names(server_notification))
    )
    if missing_notifications:
        raise ConnectorError(
            "Codex approval notification schema changed: "
            + ", ".join(missing_notifications)
        )
    _require_schema_fields(
        server_notification,
        "ServerRequestResolvedNotification",
        properties={"requestId", "threadId"},
        required={"requestId", "threadId"},
    )
    _require_schema_fields(
        server_notification,
        "ItemStartedNotification",
        properties={"item", "startedAtMs", "threadId", "turnId"},
        required={"item", "startedAtMs", "threadId", "turnId"},
    )
    _require_schema_fields(
        server_notification,
        "ItemCompletedNotification",
        properties={"completedAtMs", "item", "threadId", "turnId"},
        required={"completedAtMs", "item", "threadId", "turnId"},
    )
    _require_schema_fields(
        server_notification,
        "TurnCompletedNotification",
        properties={"threadId", "turn"},
        required={"threadId", "turn"},
    )
    _require_schema_fields(
        server_notification,
        "Turn",
        properties={"completedAt", "error", "id", "items", "itemsView", "status"},
        required={"id", "items", "status"},
    )
    _require_command_execution_schema(server_notification)


def daemon_status() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(CODEX_PATH), "app-server", "daemon", "version"],
            check=False,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConnectorError(f"cannot inspect Codex daemon: {exc}") from exc
    if completed.returncode != 0 or len(completed.stdout.encode("utf-8")) > 64 * 1024:
        raise ConnectorError("Codex daemon version check failed")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        status = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise ConnectorError("Codex daemon returned invalid JSON") from exc
    if not isinstance(status, dict):
        raise ConnectorError("Codex daemon status is not an object")
    required = {
        "status": status.get("status") == "running",
        "backend": status.get("backend") == "pid",
        "managedCodexVersion": status.get("managedCodexVersion")
        == EXPECTED_CODEX_VERSION,
        "cliVersion": status.get("cliVersion") == EXPECTED_CODEX_VERSION,
        "appServerVersion": status.get("appServerVersion") == EXPECTED_CODEX_VERSION,
        "socketPath": status.get("socketPath") == str(CONTROL_SOCKET),
    }
    failed = sorted(name for name, passed in required.items() if not passed)
    if failed:
        raise ConnectorError("Codex daemon compatibility failed: " + ", ".join(failed))
    if not CONTROL_SOCKET.exists():
        raise ConnectorError("Codex App Server control socket is missing")
    return status


class UnixWebSocket:
    def __init__(self, path: Path, timeout_seconds: int = 10) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.socket: socket.socket | None = None
        self.buffer = bytearray()

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout_seconds)
        try:
            connection.connect(str(self.path))
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = (
                "GET / HTTP/1.1\r\n"
                "Host: localhost\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            connection.sendall(request)
            self.socket = connection
            headers = self._read_http_headers()
            self._validate_upgrade(headers, key)
        except Exception:
            connection.close()
            self.socket = None
            raise

    def _read_http_headers(self) -> bytes:
        marker = b"\r\n\r\n"
        while marker not in self.buffer:
            if len(self.buffer) >= MAX_HTTP_HEADER_BYTES:
                raise ConnectorError("WebSocket upgrade headers exceeded the limit")
            self.buffer.extend(self._recv(MAX_HTTP_HEADER_BYTES - len(self.buffer)))
        index = self.buffer.index(marker) + len(marker)
        headers = bytes(self.buffer[:index])
        del self.buffer[:index]
        return headers

    @staticmethod
    def _validate_upgrade(headers: bytes, key: str) -> None:
        try:
            lines = headers.decode("ascii").split("\r\n")
        except UnicodeDecodeError as exc:
            raise ConnectorError("WebSocket upgrade returned non-ASCII headers") from exc
        if not lines or " 101 " not in lines[0]:
            raise ConnectorError("Codex App Server refused the WebSocket upgrade")
        parsed: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            name, value = line.split(":", 1)
            parsed[name.strip().lower()] = value.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if parsed.get("sec-websocket-accept") != expected_accept:
            raise ConnectorError("WebSocket upgrade accept key did not match")
        if parsed.get("upgrade", "").lower() != "websocket":
            raise ConnectorError("WebSocket upgrade header was missing")

    def _recv(self, size: int) -> bytes:
        if self.socket is None:
            raise ConnectorError("WebSocket is not connected")
        try:
            chunk = self.socket.recv(size)
        except OSError as exc:
            raise ConnectorError(f"WebSocket receive failed: {exc}") from exc
        if not chunk:
            raise ConnectorError("Codex App Server closed the WebSocket")
        return chunk

    def _read_exact(self, size: int) -> bytes:
        while len(self.buffer) < size:
            self.buffer.extend(self._recv(size - len(self.buffer)))
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.socket is None:
            raise ConnectorError("WebSocket is not connected")
        if len(payload) > MAX_MESSAGE_BYTES:
            raise ConnectorError("WebSocket message exceeded the limit")
        first = 0x80 | opcode
        length = len(payload)
        if length <= 125:
            header = bytes([first, 0x80 | length])
        elif length <= 0xFFFF:
            header = bytes([first, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([first, 0x80 | 127]) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        try:
            self.socket.sendall(header + mask + masked)
        except OSError as exc:
            raise ConnectorError(f"WebSocket send failed: {exc}") from exc

    def send_json(self, value: dict[str, Any]) -> None:
        self._send_frame(
            0x1,
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        )

    def receive_json(
        self, max_message_bytes: int = MAX_MESSAGE_BYTES
    ) -> dict[str, Any]:
        if (
            isinstance(max_message_bytes, bool)
            or not isinstance(max_message_bytes, int)
            or max_message_bytes < 1
            or max_message_bytes > MAX_PLUGIN_MESSAGE_BYTES
        ):
            raise ConnectorError("invalid WebSocket receive limit")
        fragments = bytearray()
        expecting_continuation = False
        while True:
            first, second = self._read_exact(2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            if first & 0x70 or masked:
                raise ConnectorError("Codex App Server sent an invalid WebSocket frame")
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            if (
                length > max_message_bytes
                or len(fragments) + length > max_message_bytes
            ):
                raise ConnectorError("WebSocket message exceeded the limit")
            payload = self._read_exact(length)
            if opcode == 0x8:
                raise ConnectorError("Codex App Server closed the WebSocket")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x1 and not expecting_continuation:
                fragments.extend(payload)
                expecting_continuation = not final
            elif opcode == 0x0 and expecting_continuation:
                fragments.extend(payload)
                expecting_continuation = not final
            else:
                raise ConnectorError("Codex App Server sent an unexpected WebSocket opcode")
            if not expecting_continuation:
                try:
                    value = json.loads(fragments.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ConnectorError("Codex App Server returned invalid JSON") from exc
                if not isinstance(value, dict):
                    raise ConnectorError("Codex App Server returned a non-object message")
                return value

    def close(self) -> None:
        if self.socket is None:
            return
        try:
            self._send_frame(0x8, b"")
        except ConnectorError:
            pass
        self.socket.close()
        self.socket = None


class AppServerClient:
    def __init__(self, path: Path = CONTROL_SOCKET) -> None:
        self.transport = UnixWebSocket(path)
        self.next_id = 1

    def __enter__(self) -> AppServerClient:
        self.transport.connect()
        try:
            self.transport.send_json(
                {
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "clientInfo": CLIENT_INFO,
                        "capabilities": {"experimentalApi": True},
                    },
                }
            )
            response = self._wait_for(0)
            result = response.get("result")
            if not isinstance(result, dict) or result.get("codexHome") != str(CODEX_HOME):
                raise ConnectorError("Codex App Server initialized with an unexpected home")
            self.transport.send_json({"method": "initialized", "params": {}})
            return self
        except Exception:
            self.transport.close()
            raise

    def __exit__(self, *_: Any) -> None:
        self.transport.close()

    def _wait_for(
        self,
        request_id: int,
        *,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
    ) -> dict[str, Any]:
        while True:
            message = self.transport.receive_json(max_message_bytes)
            if message.get("id") != request_id:
                if "id" in message and "method" in message:
                    raise ConnectorError("Codex App Server sent an unexpected request")
                continue
            error = message.get("error")
            if error is not None:
                raise ConnectorError("Codex App Server request failed")
            if "result" not in message:
                raise ConnectorError("Codex App Server response omitted its result")
            return message

    def request(self, method: str, params: Any) -> Any:
        request_id = self.next_id
        self.next_id += 1
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = params
        self.transport.send_json(message)
        max_message_bytes = (
            MAX_PLUGIN_MESSAGE_BYTES if method == "plugin/list" else MAX_MESSAGE_BYTES
        )
        return self._wait_for(
            request_id,
            max_message_bytes=max_message_bytes,
        )["result"]


def list_projects(client: AppServerClient) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(100):
        result = client.request(
            "project/list",
            {
                "cursor": cursor,
                "limit": 100,
                "sortKey": "position",
                "sortDirection": "asc",
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ConnectorError("project/list returned an invalid result")
        page = result["data"]
        if not all(isinstance(project, dict) for project in page):
            raise ConnectorError("project/list returned an invalid project")
        projects.extend(page)
        cursor = result.get("nextCursor")
        if cursor is None:
            return projects
        if not isinstance(cursor, str) or not cursor:
            raise ConnectorError("project/list returned an invalid cursor")
    raise ConnectorError("project/list pagination exceeded the safety limit")


def project_result(result: Any) -> dict[str, Any]:
    project = result.get("project") if isinstance(result, dict) else None
    if not isinstance(project, dict):
        raise ConnectorError("Codex project response omitted the project")
    return project


def project_identity(project: dict[str, Any]) -> tuple[str, str, list[str], dict[str, str]]:
    project_id = project.get("id")
    name = project.get("name")
    roots = project.get("roots")
    metadata = project.get("metadata")
    if not isinstance(project_id, str) or not project_id:
        raise ConnectorError("Codex project has an invalid ID")
    if not isinstance(name, str) or not name:
        raise ConnectorError("Codex project has an invalid name")
    if not isinstance(roots, list) or not all(
        isinstance(root, dict) and isinstance(root.get("path"), str) for root in roots
    ):
        raise ConnectorError("Codex project has invalid roots")
    if not isinstance(metadata, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
    ):
        raise ConnectorError("Codex project has invalid metadata")
    return project_id, name, [root["path"] for root in roots], metadata


def expected_metadata(workspace: Path) -> dict[str, str]:
    return {
        "lift.schemaVersion": "1",
        "lift.workspaceId": workspace.name,
    }


def matches_project(project: dict[str, Any], workspace: Path, name: str) -> bool:
    _, observed_name, roots, metadata = project_identity(project)
    return (
        observed_name == name
        and roots == [str(workspace)]
        and metadata == expected_metadata(workspace)
    )


def ensure_project(
    client: AppServerClient,
    workspace: Path,
    name: str,
    state: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    projects = list_projects(client)
    same_root: list[dict[str, Any]] = []
    exact: list[dict[str, Any]] = []
    for project in projects:
        _, _, roots, _ = project_identity(project)
        if roots == [str(workspace)]:
            same_root.append(project)
            if matches_project(project, workspace, name):
                exact.append(project)
    if len(same_root) > 1 or len(exact) > 1:
        raise ConnectorError("multiple Codex projects claim the Lift workspace")
    if same_root and not exact:
        raise ConnectorError("a non-Lift Codex project already claims the workspace")

    saved_id = state.get("projectId")
    if saved_id is not None:
        saved = [project for project in projects if project.get("id") == saved_id]
        if len(saved) != 1 or not matches_project(saved[0], workspace, name):
            raise ConnectorError("the saved Codex project no longer matches the workspace")
        return saved[0], False
    if exact:
        return exact[0], False

    params = {
        "idempotencyKey": state["idempotencyKey"],
        "name": name,
        "roots": [{"path": str(workspace)}],
        "metadata": expected_metadata(workspace),
    }
    created = project_result(client.request("project/create", params))
    if not matches_project(created, workspace, name):
        raise ConnectorError("project/create returned a mismatched project")
    replayed = project_result(client.request("project/create", params))
    if project_identity(replayed)[0] != project_identity(created)[0]:
        raise ConnectorError("project/create idempotency replay changed project identity")
    return created, True


def read_project(client: AppServerClient, project_id: str) -> dict[str, Any]:
    return project_result(client.request("project/read", {"projectId": project_id}))


def ensure_trusted(client: AppServerClient, workspace: Path) -> None:
    if "." in str(workspace):
        raise ConnectorError("the Phase 0 trust writer does not support dots in workspace paths")
    client.request(
        "config/value/write",
        {
            "keyPath": f"projects.{workspace}.trust_level",
            "value": "trusted",
            "mergeStrategy": "upsert",
        },
    )
    if not workspace_is_trusted(workspace):
        raise ConnectorError("Codex did not persist trust for the Lift workspace")


def workspace_is_trusted(workspace: Path) -> bool:
    try:
        with CONFIG_PATH.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConnectorError(f"cannot verify Codex config: {exc}") from exc
    projects = config.get("projects")
    project = projects.get(str(workspace)) if isinstance(projects, dict) else None
    return isinstance(project, dict) and project.get("trust_level") == "trusted"


def verified_project(
    client: AppServerClient,
    workspace: Path,
    name: str,
    project_id: str,
) -> dict[str, Any]:
    project = read_project(client, project_id)
    if not matches_project(project, workspace, name):
        raise ConnectorError("project/read did not return the Lift project")
    listed = [item for item in list_projects(client) if item.get("id") == project_id]
    if len(listed) != 1 or not matches_project(listed[0], workspace, name):
        raise ConnectorError("project/list did not contain the exact Lift project")
    if not workspace_is_trusted(workspace):
        raise ConnectorError("the Lift workspace is not trusted by Codex")
    return project


def remote_readiness(client: AppServerClient) -> dict[str, Any]:
    status = client.request("remoteControl/status/read", None)
    if not isinstance(status, dict):
        raise ConnectorError("remoteControl/status/read returned an invalid result")
    environment_id = status.get("environmentId")
    if status.get("status") != "connected" or not isinstance(environment_id, str) or not environment_id:
        raise ConnectorError("Codex Remote is not connected")
    clients = client.request(
        "remoteControl/client/list", {"environmentId": environment_id}
    )
    data = clients.get("data") if isinstance(clients, dict) else None
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ConnectorError("remoteControl/client/list returned an invalid result")
    if not data:
        raise ConnectorError("Codex Remote has no paired controller")
    readiness = {
        "status": "connected",
        "environmentId": environment_id,
        "controllerPresent": True,
        "pairedClientCount": len(data),
    }
    server_name = status.get("serverName")
    if isinstance(server_name, str) and server_name:
        readiness["serverName"] = server_name
    return readiness


def list_workspace_threads(
    client: AppServerClient,
    workspace: Path,
) -> list[dict[str, Any]]:
    """List every thread for the exact folder, independent of project assignment."""
    threads: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    cursor: str | None = None
    for _ in range(MAX_THREAD_PAGES):
        result = client.request(
            "thread/list",
            {
                "cursor": cursor,
                "limit": MAX_THREADS_PER_PAGE,
                "sortKey": "created_at",
                "sortDirection": "asc",
                "cwd": str(workspace),
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ConnectorError("thread/list returned an invalid result")
        for thread in result["data"]:
            thread_id, created_at = folder_thread_identity(thread, workspace)
            if thread_id in seen_ids:
                raise ConnectorError("thread/list returned a duplicate thread")
            seen_ids.add(thread_id)
            threads.append(thread)
            if created_at < 0:
                raise ConnectorError("thread/list returned an invalid creation time")
        cursor = result.get("nextCursor")
        if cursor is None:
            return threads
        if not isinstance(cursor, str) or not cursor:
            raise ConnectorError("thread/list returned an invalid cursor")
    raise ConnectorError("thread/list pagination exceeded the safety limit")


def folder_thread_identity(
    thread: Any,
    workspace: Path,
) -> tuple[str, int]:
    if not isinstance(thread, dict):
        raise ConnectorError("Codex returned an invalid thread")
    thread_id = thread.get("id")
    created_at = thread.get("createdAt")
    if not isinstance(thread_id, str) or not thread_id or len(thread_id) > 256:
        raise ConnectorError("Codex returned an invalid thread ID")
    project_id = thread.get("projectId")
    if project_id is not None and (not isinstance(project_id, str) or not project_id):
        raise ConnectorError("Codex returned an invalid thread project assignment")
    if thread.get("cwd") != str(workspace):
        raise ConnectorError("Codex returned a thread outside the exact Lift folder")
    if isinstance(created_at, bool) or not isinstance(created_at, int):
        raise ConnectorError("Codex returned an invalid thread creation time")
    return thread_id, created_at


def exact_controller_thread_identity(
    thread: Any,
    workspace: Path,
) -> tuple[str, int]:
    thread_id, created_at = folder_thread_identity(thread, workspace)
    if thread.get("projectId") is not None:
        raise ConnectorError(
            "Codex controller thread must be folder-bound and project-unassigned"
        )
    return thread_id, created_at


def read_exact_thread(
    client: AppServerClient,
    thread_id: str,
    workspace: Path,
) -> dict[str, Any]:
    result = client.request(
        "thread/read",
        {"threadId": thread_id, "includeTurns": True},
    )
    thread = result.get("thread") if isinstance(result, dict) else None
    observed_id, _ = exact_controller_thread_identity(thread, workspace)
    if observed_id != thread_id:
        raise ConnectorError("thread/read changed thread identity")
    turns = thread.get("turns")
    if not isinstance(turns, list):
        raise ConnectorError("thread/read omitted full turn history")
    return thread


def validated_proof_relative_path(raw_path: str) -> str:
    if (
        not raw_path
        or raw_path != raw_path.strip()
        or "\\" in raw_path
        or "\x00" in raw_path
        or len(raw_path.encode("utf-8")) > MAX_PROOF_PATH_BYTES
    ):
        raise ConnectorError("proof-relative-path must be a safe relative POSIX path")
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or path.as_posix() != raw_path
        or path == PurePosixPath(".")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ConnectorError("proof-relative-path must be a safe relative POSIX path")
    return raw_path


def validated_nonce(raw_nonce: str, description: str) -> str:
    if not NONCE_PATTERN.fullmatch(raw_nonce):
        raise ConnectorError(f"{description} must be a bounded hexadecimal nonce")
    return raw_nonce


def validated_baseline_thread_ids(raw_ids: list[str]) -> set[str]:
    if not all(
        isinstance(thread_id, str) and 0 < len(thread_id) <= 256
        for thread_id in raw_ids
    ):
        raise ConnectorError("baseline thread ID is invalid")
    baseline = set(raw_ids)
    if len(baseline) != len(raw_ids):
        raise ConnectorError("baseline thread IDs must be unique")
    return baseline


def validated_sha256(raw_digest: str, description: str) -> str:
    if not SHA256_PATTERN.fullmatch(raw_digest):
        raise ConnectorError(f"{description} must be a lowercase SHA-256 digest")
    return raw_digest


def _normalized_layer_path(raw_path: Any, description: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or len(raw_path) > 4096:
        raise ConnectorError(f"{description} path is invalid")
    path = Path(raw_path)
    if not path.is_absolute() or path.as_posix() != raw_path or ".." in path.parts:
        raise ConnectorError(f"{description} path is not an absolute normalized path")
    return path


def _empty_rule_directory_state(path: Path) -> str:
    """Prove that one active config layer cannot auto-allow the canary."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise ConnectorError(f"cannot inspect Codex rules directory {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ConnectorError(f"Codex rules path must be a real directory: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ConnectorError(f"cannot resolve Codex rules directory {path}: {exc}") from exc
    if resolved != path:
        raise ConnectorError(f"Codex rules directory cannot contain a symlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            with os.scandir(descriptor) as entries:
                if next(entries, None) is not None:
                    raise ConnectorError(
                        "approval proof requires every active Codex rules directory "
                        f"to be empty: {path}"
                    )
        finally:
            os.close(descriptor)
    except ConnectorError:
        raise
    except OSError as exc:
        raise ConnectorError(f"cannot read Codex rules directory {path}: {exc}") from exc
    return "empty"


def _absent_hook_file_state(path: Path) -> str:
    """Fail closed if a file-backed hook source exists in an active layer."""
    try:
        path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise ConnectorError(f"cannot inspect Codex hook file {path}: {exc}") from exc
    raise ConnectorError(
        "approval proof requires file-backed Codex hooks to be absent: " f"{path}"
    )


def _effective_hook_state(client: AppServerClient, workspace: Path) -> dict[str, Any]:
    """Return bounded effective hook state after proving no hook can run."""
    result = client.request("hooks/list", {"cwds": [str(workspace)]})
    if not isinstance(result, dict) or set(result) != {"data"}:
        raise ConnectorError("hooks/list returned an invalid result")
    data = result.get("data")
    if not isinstance(data, list) or len(data) != 1:
        raise ConnectorError("hooks/list did not return the exact workspace")
    entry = data[0]
    if (
        not isinstance(entry, dict)
        or not {"cwd", "errors", "hooks", "warnings"}.issubset(entry)
        or entry.get("cwd") != str(workspace)
        or not isinstance(entry.get("errors"), list)
        or not isinstance(entry.get("warnings"), list)
        or not isinstance(entry.get("hooks"), list)
        or len(entry["hooks"]) > MAX_HOOKS
    ):
        raise ConnectorError("hooks/list returned malformed workspace hook state")
    if entry["errors"] or entry["warnings"]:
        raise ConnectorError("Codex hook discovery returned errors or warnings")
    for hook in entry["hooks"]:
        if (
            not isinstance(hook, dict)
            or not isinstance(hook.get("currentHash"), str)
            or not hook.get("currentHash")
            or not isinstance(hook.get("enabled"), bool)
            or not isinstance(hook.get("eventName"), str)
            or not isinstance(hook.get("handlerType"), str)
            or not isinstance(hook.get("isManaged"), bool)
            or not isinstance(hook.get("key"), str)
            or not hook.get("key")
            or not isinstance(hook.get("source"), str)
            or not isinstance(hook.get("sourcePath"), str)
            or not isinstance(hook.get("trustStatus"), str)
            or (hook.get("pluginId") is not None and not isinstance(hook["pluginId"], str))
        ):
            raise ConnectorError("hooks/list returned malformed hook metadata")
        if hook["enabled"]:
            raise ConnectorError(
                "approval proof requires every effective Codex hook to be disabled"
            )
    return result


def _managed_requirements_state(client: AppServerClient) -> dict[str, Any]:
    """Prove managed requirements do not inject an approval-affecting hook."""
    result = client.request("configRequirements/read", None)
    if not isinstance(result, dict) or not set(result).issubset({"requirements"}):
        raise ConnectorError("configRequirements/read returned an invalid result")
    requirements = result.get("requirements")
    if requirements is None:
        return result
    if not isinstance(requirements, dict):
        raise ConnectorError("managed Codex requirements are malformed")
    hooks = requirements.get("hooks")
    if hooks is not None:
        if not isinstance(hooks, dict):
            raise ConnectorError("managed Codex hook requirements are malformed")
        for event_name, groups in hooks.items():
            if event_name in {"managedDir", "windowsManagedDir"}:
                if groups is not None and not isinstance(groups, str):
                    raise ConnectorError("managed Codex hook directory is malformed")
                continue
            if not isinstance(groups, list):
                raise ConnectorError("managed Codex hook requirements are malformed")
            if groups:
                raise ConnectorError(
                    "approval proof requires managed Codex hooks to be empty"
                )
    return result


def _effective_plugin_state(client: AppServerClient, workspace: Path) -> dict[str, Any]:
    """Return a bounded digest that freezes the complete effective plugin state."""
    result = client.request(
        "plugin/list",
        {"cwds": [str(workspace)], "forceRefetch": False},
    )
    if not isinstance(result, dict) or "marketplaces" not in result:
        raise ConnectorError("plugin/list returned an invalid result")
    marketplaces = result.get("marketplaces")
    load_errors = result.get("marketplaceLoadErrors", [])
    featured = result.get("featuredPluginIds", [])
    if (
        not isinstance(marketplaces, list)
        or len(marketplaces) > MAX_PLUGIN_MARKETPLACES
        or not isinstance(load_errors, list)
        or load_errors
        or not isinstance(featured, list)
        or not all(isinstance(plugin_id, str) for plugin_id in featured)
    ):
        raise ConnectorError("Codex plugin discovery was malformed or returned errors")
    plugin_count = 0
    enabled_plugin_count = 0
    for marketplace in marketplaces:
        if (
            not isinstance(marketplace, dict)
            or not isinstance(marketplace.get("name"), str)
            or not isinstance(marketplace.get("plugins"), list)
        ):
            raise ConnectorError("plugin/list returned malformed marketplace state")
        plugin_count += len(marketplace["plugins"])
        if plugin_count > MAX_PLUGINS:
            raise ConnectorError("plugin/list exceeded the verification limit")
        for plugin in marketplace["plugins"]:
            if (
                not isinstance(plugin, dict)
                or not isinstance(plugin.get("id"), str)
                or not plugin.get("id")
                or not isinstance(plugin.get("name"), str)
                or not isinstance(plugin.get("enabled"), bool)
                or not isinstance(plugin.get("installed"), bool)
                or not isinstance(plugin.get("source"), dict)
            ):
                raise ConnectorError("plugin/list returned malformed plugin state")
            if plugin["enabled"]:
                enabled_plugin_count += 1
    try:
        canonical_plugins = json.dumps(
            result,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConnectorError("Codex plugin state is not canonical JSON") from exc
    if len(canonical_plugins) > MAX_PLUGIN_STATE_BYTES:
        raise ConnectorError("Codex plugin state exceeds the verification limit")
    return {
        "enabledPluginCount": enabled_plugin_count,
        "marketplaceCount": len(marketplaces),
        "pluginCount": plugin_count,
        "sha256": hashlib.sha256(canonical_plugins).hexdigest(),
    }


def approval_guard_sha256(client: AppServerClient, workspace: Path) -> str:
    """Hash active policy, plugin state, and the absence of effective hooks."""
    result = client.request(
        "config/read",
        {"cwd": str(workspace), "includeLayers": True},
    )
    if (
        not isinstance(result, dict)
        or set(result) != {"config", "layers", "origins"}
        or not isinstance(result.get("config"), dict)
        or not isinstance(result.get("origins"), dict)
    ):
        raise ConnectorError("config/read returned an invalid layered configuration")
    layers = result.get("layers")
    if not isinstance(layers, list) or not layers or len(layers) > MAX_CONFIG_LAYERS:
        raise ConnectorError("config/read did not return bounded active config layers")

    effective_config = result["config"]
    if effective_config.get("hooks") is not None:
        raise ConnectorError("approval proof cannot run with Codex hooks configured")
    rule_directories = {
        Path("/etc/codex/rules"),
        CODEX_HOME / "rules",
        workspace / ".codex" / "rules",
    }
    hook_files = {
        Path("/etc/codex/hooks.json"),
        CODEX_HOME / "hooks.json",
        workspace / ".codex" / "hooks.json",
    }
    for layer in layers:
        if not isinstance(layer, dict) or not {"config", "name", "version"}.issubset(
            layer
        ) or not set(layer).issubset({"config", "disabledReason", "name", "version"}):
            raise ConnectorError("config/read returned an invalid config layer")
        version = layer.get("version")
        disabled_reason = layer.get("disabledReason")
        source = layer.get("name")
        if (
            not isinstance(version, str)
            or not version
            or len(version) > 256
            or (disabled_reason is not None and (
                not isinstance(disabled_reason, str)
                or not disabled_reason
                or len(disabled_reason) > 1024
            ))
            or not isinstance(source, dict)
            or not isinstance(source.get("type"), str)
        ):
            raise ConnectorError("config/read returned malformed config layer metadata")
        source_type = source["type"]
        active = disabled_reason is None
        layer_config = layer.get("config")
        if not isinstance(layer_config, dict):
            raise ConnectorError("config/read returned malformed layer configuration")
        if active and layer_config.get("hooks") is not None:
            raise ConnectorError("approval proof cannot run with Codex hooks configured")
        if source_type == "user":
            if not set(source).issubset({"file", "profile", "type"}) or not {
                "file",
                "type",
            }.issubset(source):
                raise ConnectorError("user config layer source is invalid")
            config_path = _normalized_layer_path(source.get("file"), "user config")
            if config_path != CODEX_HOME / "config.toml":
                raise ConnectorError("user config layer is outside the pinned Codex home")
            if active:
                rule_directories.add(config_path.parent / "rules")
                hook_files.add(config_path.parent / "hooks.json")
        elif source_type in {
            "packagedDefaults",
            "system",
            "legacyManagedConfigTomlFromFile",
        }:
            if set(source) != {"file", "type"}:
                raise ConnectorError("file-backed config layer source is invalid")
            config_path = _normalized_layer_path(source.get("file"), source_type)
            if active:
                rule_directories.add(config_path.parent / "rules")
                hook_files.add(config_path.parent / "hooks.json")
        elif source_type == "project":
            if set(source) != {"dotCodexFolder", "type"}:
                raise ConnectorError("project config layer source is invalid")
            dot_codex = _normalized_layer_path(
                source.get("dotCodexFolder"), "project config"
            )
            if dot_codex != workspace / ".codex":
                raise ConnectorError("project config layer is outside the exact workspace")
            if active:
                rule_directories.add(dot_codex / "rules")
                hook_files.add(dot_codex / "hooks.json")
        elif source_type == "sessionFlags":
            if set(source) != {"type"}:
                raise ConnectorError("session config layer source is invalid")
        elif source_type in {
            "enterpriseManaged",
            "legacyManagedConfigTomlFromMdm",
            "mdm",
        }:
            if active:
                raise ConnectorError(
                    "approval proof cannot enumerate rules from an opaque active config layer"
                )
        else:
            raise ConnectorError(f"unknown Codex config layer source: {source_type}")

    try:
        canonical_layers = json.dumps(
            layers,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConnectorError("Codex config layers are not canonical JSON") from exc
    if len(canonical_layers) > MAX_CONFIG_LAYER_BYTES:
        raise ConnectorError("Codex config layers exceed the verification limit")
    rule_states = [
        {"path": str(path), "state": _empty_rule_directory_state(path)}
        for path in sorted(rule_directories, key=lambda candidate: candidate.as_posix())
    ]
    hook_file_states = [
        {"path": str(path), "state": _absent_hook_file_state(path)}
        for path in sorted(hook_files, key=lambda candidate: candidate.as_posix())
    ]
    effective_hooks = _effective_hook_state(client, workspace)
    managed_requirements = _managed_requirements_state(client)
    effective_plugins = _effective_plugin_state(client, workspace)
    guard = {
        "effectiveHooks": effective_hooks,
        "effectivePlugins": effective_plugins,
        "hookFiles": hook_file_states,
        "layers": json.loads(canonical_layers),
        "managedRequirements": managed_requirements,
        "rules": rule_states,
    }
    canonical_guard = json.dumps(
        guard,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(canonical_guard) > MAX_HOOK_STATE_BYTES + MAX_CONFIG_LAYER_BYTES:
        raise ConnectorError("Codex approval guard exceeds the verification limit")
    return hashlib.sha256(canonical_guard).hexdigest()


def unified_exec_inner_command(command: Any) -> str:
    if not isinstance(command, str) or not command:
        raise ConnectorError("commandExecution omitted its command")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ConnectorError("commandExecution wrapper is not valid shell syntax") from exc
    if (
        len(argv) != 3
        or argv[0] != UNIFIED_EXEC_SHELL
        or argv[1] != UNIFIED_EXEC_SHELL_ARGUMENT
        or not argv[2]
    ):
        raise ConnectorError("commandExecution used an unexpected unified-exec wrapper")
    return argv[2]


def successful_command(item: Any, workspace: Path) -> tuple[str, str] | None:
    if not isinstance(item, dict) or not isinstance(item.get("type"), str):
        raise ConnectorError("thread/read returned an invalid turn item")
    if item["type"] != "commandExecution":
        return None
    item_id = item.get("id")
    command = item.get("command")
    cwd = item.get("cwd")
    status = item.get("status")
    exit_code = item.get("exitCode")
    source = item.get("source")
    plugin_id = item.get("pluginId")
    script_path = item.get("scriptPath")
    if (
        not isinstance(item_id, str)
        or not item_id
        or len(item_id) > 256
        or not isinstance(command, str)
        or not isinstance(cwd, str)
        or not isinstance(status, str)
        or (exit_code is not None and isinstance(exit_code, bool))
        or (exit_code is not None and not isinstance(exit_code, int))
    ):
        raise ConnectorError("thread/read returned an invalid commandExecution item")
    if (
        status != "completed"
        or exit_code != 0
        or cwd != str(workspace)
        or source != UNIFIED_EXEC_COMMAND_SOURCE
        or plugin_id is not None
        or script_path is not None
    ):
        return None
    try:
        inner_command = unified_exec_inner_command(command)
    except ConnectorError:
        return None
    return item_id, inner_command


def approval_canary_tokens(approval_nonce: str) -> list[str]:
    validated_nonce(approval_nonce, "approval nonce")
    return [
        "/usr/bin/env",
        "-i",
        f"LIFT_APPROVAL_CANARY={approval_nonce}",
        "PATH=/usr/bin:/bin",
        "/usr/bin/curl",
        "--disable",
        "--noproxy",
        "*",
        "--proto",
        "=https",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "10",
        "--max-time",
        "30",
        "--output",
        "/dev/null",
        "https://example.com/",
    ]


def approval_canary_command(approval_nonce: str) -> str:
    return shlex.join(approval_canary_tokens(approval_nonce))


def matches_approval_canary_command(command: str, approval_nonce: str) -> bool:
    return command == approval_canary_command(approval_nonce)


def matching_turn_evidence(
    thread: dict[str, Any],
    workspace: Path,
    proof_command_sha256: str,
    approval_nonce: str,
) -> dict[str, str] | None:
    expected_proof_command_sha256 = validated_sha256(
        proof_command_sha256,
        "proof-command-sha256",
    )
    matching_turns: list[dict[str, str]] = []
    turns = thread["turns"]
    for turn in turns:
        if not isinstance(turn, dict):
            raise ConnectorError("thread/read returned an invalid turn")
        turn_id = turn.get("id")
        items = turn.get("items")
        completed_at = turn.get("completedAt")
        if (
            not isinstance(turn_id, str)
            or not turn_id
            or len(turn_id) > 256
            or not isinstance(items, list)
        ):
            raise ConnectorError("thread/read returned an invalid turn")
        if turn.get("status") != "completed":
            continue
        if (
            isinstance(completed_at, bool)
            or not isinstance(completed_at, int)
            or turn.get("itemsView") != "full"
        ):
            raise ConnectorError("thread/read returned an incomplete completed turn")
        proof_items: list[tuple[str, str]] = []
        approval_items: list[tuple[str, str]] = []
        command_items: list[tuple[str, str] | None] = []
        for item in items:
            if (
                not isinstance(item, dict)
                or item.get("type") not in APPROVAL_PROOF_TURN_ITEM_TYPES
            ):
                raise ConnectorError(
                    "approval proof turn contains an unreviewed tool or hook item"
                )
            command = successful_command(item, workspace)
            if item.get("type") == "commandExecution":
                command_items.append(command)
            if command is None:
                continue
            item_id, command_text = command
            command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
            if command_sha256 == expected_proof_command_sha256:
                proof_items.append((item_id, command_text))
            if matches_approval_canary_command(command_text, approval_nonce):
                approval_items.append((item_id, command_text))
        if not proof_items and not approval_items:
            continue
        if len(proof_items) != 1 or len(approval_items) != 1:
            raise ConnectorError("thread proof commands were ambiguous")
        proof_item_id, proof_command = proof_items[0]
        approval_item_id, approval_command = approval_items[0]
        if (
            len(command_items) != 2
            or any(command is None for command in command_items)
            or command_items[0] != (approval_item_id, approval_command)
            or command_items[1] != (proof_item_id, proof_command)
        ):
            raise ConnectorError(
                "approval canary must be the first command in the only proof turn"
            )
        matching_turns.append(
            {
                "turnId": turn_id,
                "proofItemId": proof_item_id,
                "approvalItemId": approval_item_id,
                "proofCommandSha256": hashlib.sha256(
                    proof_command.encode("utf-8")
                ).hexdigest(),
                "approvalCommandSha256": hashlib.sha256(
                    approval_command.encode("utf-8")
                ).hexdigest(),
            }
        )
    if len(matching_turns) > 1:
        raise ConnectorError("multiple completed turns matched the thread proof")
    if matching_turns and len(turns) != 1:
        raise ConnectorError("approval proof requires a fresh single-turn thread")
    return matching_turns[0] if matching_turns else None


def normalized_approval_policy(value: Any) -> str | dict[str, dict[str, bool]]:
    if isinstance(value, str):
        if value == "never":
            raise ConnectorError("thread approval policy cannot be never")
        if value not in {"untrusted", "on-request"}:
            raise ConnectorError("thread approval policy is invalid")
        return value
    if not isinstance(value, dict) or set(value) != {"granular"}:
        raise ConnectorError("thread approval policy is invalid")
    granular = value.get("granular")
    required = {"sandbox_approval", "rules", "mcp_elicitations"}
    optional = {"skill_approval", "request_permissions"}
    if (
        not isinstance(granular, dict)
        or not required.issubset(granular)
        or not set(granular).issubset(required | optional)
        or not all(isinstance(setting, bool) for setting in granular.values())
    ):
        raise ConnectorError("thread approval policy is invalid")
    return {"granular": dict(sorted(granular.items()))}


def normalized_sandbox(value: Any) -> tuple[str, bool | str]:
    if not isinstance(value, dict):
        raise ConnectorError("thread sandbox policy is invalid")
    sandbox_type = value.get("type")
    network_access = value.get("networkAccess")
    if sandbox_type in {"readOnly", "workspaceWrite"}:
        if network_access is not False:
            raise ConnectorError("thread sandbox network access is not disabled")
        return sandbox_type, False
    if sandbox_type == "externalSandbox":
        raise ConnectorError("thread sandbox cannot use externalSandbox")
    if sandbox_type == "dangerFullAccess":
        raise ConnectorError("thread sandbox cannot use dangerFullAccess")
    raise ConnectorError("thread sandbox policy is invalid")


def verified_resume_settings(
    client: AppServerClient,
    thread_id: str,
    workspace: Path,
) -> tuple[str, bool | str, str | dict[str, dict[str, bool]]]:
    result = client.request(
        "thread/resume",
        {"threadId": thread_id, "excludeTurns": True},
    )
    if not isinstance(result, dict):
        raise ConnectorError("thread/resume returned an invalid result")
    thread = result.get("thread")
    observed_id, _ = exact_controller_thread_identity(thread, workspace)
    if observed_id != thread_id or thread.get("turns") != []:
        raise ConnectorError("thread/resume changed thread identity or returned turns")
    if result.get("cwd") != str(workspace):
        raise ConnectorError("thread/resume returned an unexpected cwd")
    if result.get("runtimeWorkspaceRoots") != [str(workspace)]:
        raise ConnectorError("thread/resume returned unexpected runtime workspace roots")
    approval_policy = normalized_approval_policy(result.get("approvalPolicy"))
    if result.get("approvalsReviewer") != "user":
        raise ConnectorError("thread approvals reviewer is not the user")
    sandbox_type, network_access = normalized_sandbox(result.get("sandbox"))
    return sandbox_type, network_access, approval_policy


def configuration(
    daemon: dict[str, Any],
    workspace: Path,
    project: dict[str, Any],
    *,
    created: bool,
) -> dict[str, Any]:
    project_id, name, roots, _ = project_identity(project)
    return {
        "configured": True,
        "created": created,
        "controllerProjectVisibility": {
            "status": "unknown",
            "verified": False,
        },
        "experimentalApi": True,
        "provider": "codex",
        "serverProjectRegistered": True,
        "workspace": str(workspace),
        "daemon": daemon,
        "project": {
            "id": project_id,
            "name": name,
            "root": roots[0],
            "trusted": True,
        },
    }


def readiness(
    daemon: dict[str, Any],
    remote: dict[str, Any],
    workspace: Path,
    project: dict[str, Any],
    *,
    created: bool,
) -> dict[str, Any]:
    return {
        **configuration(daemon, workspace, project, created=created),
        "readyForPhoneProof": True,
        "remote": remote,
    }


def validated_project_name(raw_name: str) -> str:
    name = raw_name.strip()
    if not name or name != raw_name or len(name) > 128:
        raise ConnectorError("project name must be 1 to 128 characters")
    return name


def cmd_register(args: argparse.Namespace) -> dict[str, Any]:
    workspace = validated_workspace(os.environ.get("LIFT_WORKSPACE"))
    name = validated_project_name(args.name)
    daemon = daemon_status()
    validate_experimental_schema()
    state_path = connector_state_path(workspace)
    state = validated_state(state_path, workspace, create=True)
    with AppServerClient() as client:
        project, created = ensure_project(client, workspace, name, state)
        project_id = project_identity(project)[0]
        if state.get("projectId") != project_id:
            state["projectId"] = project_id
            atomic_json(state_path, state)
        ensure_trusted(client, workspace)
        project = verified_project(client, workspace, name, project_id)
    return configuration(daemon, workspace, project, created=created)


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    workspace = validated_workspace(os.environ.get("LIFT_WORKSPACE"))
    name = validated_project_name(args.name)
    daemon = daemon_status()
    state = validated_state(connector_state_path(workspace), workspace, create=False)
    project_id = state.get("projectId")
    if not isinstance(project_id, str):
        raise ConnectorError("Codex project registration is incomplete")
    with AppServerClient() as client:
        project = verified_project(client, workspace, name, project_id)
        remote = remote_readiness(client)
    return readiness(daemon, remote, workspace, project, created=False)


def cmd_thread_baseline(args: argparse.Namespace) -> dict[str, Any]:
    workspace = validated_workspace(os.environ.get("LIFT_WORKSPACE"))
    name = validated_project_name(args.name)
    daemon_status()
    validate_experimental_schema()
    state = validated_state(connector_state_path(workspace), workspace, create=False)
    project_id = state.get("projectId")
    if not isinstance(project_id, str):
        raise ConnectorError("Codex project registration is incomplete")
    with AppServerClient() as client:
        project = verified_project(client, workspace, name, project_id)
        native_project_id = project_identity(project)[0]
        remote = remote_readiness(client)
        approval_guard = approval_guard_sha256(client, workspace)
        created_at_epoch_seconds = int(time.time())
        threads = list_workspace_threads(client, workspace)
    return {
        "approvalGuardSha256": approval_guard,
        "controllerThreadBinding": CONTROLLER_THREAD_BINDING,
        "controllerThreadProjectId": None,
        "createdAtEpochSeconds": created_at_epoch_seconds,
        "cwd": str(workspace),
        "environmentId": remote["environmentId"],
        "nativeProjectId": native_project_id,
        "projectRoot": str(workspace),
        "threadIds": sorted(thread["id"] for thread in threads),
    }


def cmd_verify_thread(args: argparse.Namespace) -> dict[str, Any]:
    workspace = validated_workspace(os.environ.get("LIFT_WORKSPACE"))
    name = validated_project_name(args.name)
    validated_proof_relative_path(args.proof_relative_path)
    proof_nonce = validated_nonce(args.proof_nonce, "proof-nonce")
    approval_nonce = validated_nonce(args.approval_nonce, "approval-nonce")
    proof_command_sha256 = validated_sha256(
        args.proof_command_sha256,
        "proof-command-sha256",
    )
    expected_approval_guard = validated_sha256(
        args.approval_guard_sha256,
        "approval-guard-sha256",
    )
    if proof_nonce == approval_nonce:
        raise ConnectorError("proof and approval nonces must be distinct")
    if (
        isinstance(args.created_after, bool)
        or not isinstance(args.created_after, int)
        or args.created_after < 0
    ):
        raise ConnectorError("created-after must be a non-negative epoch")
    baseline_thread_ids = validated_baseline_thread_ids(args.baseline_thread_id)

    daemon_status()
    validate_experimental_schema()
    state = validated_state(connector_state_path(workspace), workspace, create=False)
    project_id = state.get("projectId")
    if not isinstance(project_id, str):
        raise ConnectorError("Codex project registration is incomplete")

    with AppServerClient() as client:
        project = verified_project(client, workspace, name, project_id)
        native_project_id = project_identity(project)[0]
        remote = remote_readiness(client)
        approval_guard = approval_guard_sha256(client, workspace)
        if approval_guard != expected_approval_guard:
            raise ConnectorError("Codex approval guard changed after the thread baseline")
        listed_threads = list_workspace_threads(client, workspace)
        candidates: list[tuple[dict[str, Any], int]] = []
        for listed in listed_threads:
            listed_id, listed_created_at = folder_thread_identity(listed, workspace)
            if (
                listed_id not in baseline_thread_ids
                and listed_created_at >= args.created_after
            ):
                candidates.append((listed, listed_created_at))
        if len(candidates) > MAX_PROOF_CANDIDATES:
            raise ConnectorError("too many post-baseline threads to verify safely")
        if len(candidates) != 1:
            raise ConnectorError("expected exactly one post-baseline folder thread")

        matches: list[tuple[str, dict[str, str]]] = []
        for listed, listed_created_at in candidates:
            thread_id = listed["id"]
            thread = read_exact_thread(
                client,
                thread_id,
                workspace,
            )
            _, read_created_at = exact_controller_thread_identity(thread, workspace)
            if read_created_at != listed_created_at:
                raise ConnectorError("thread/read changed thread creation time")
            evidence = matching_turn_evidence(
                thread,
                workspace,
                proof_command_sha256,
                approval_nonce,
            )
            if evidence is not None:
                matches.append((thread_id, evidence))
        if len(matches) != 1:
            raise ConnectorError("expected exactly one verified post-baseline thread")

        thread_id, evidence = matches[0]
        sandbox_type, network_access, approval_policy = verified_resume_settings(
            client,
            thread_id,
            workspace,
        )
        if approval_policy != "on-request":
            raise ConnectorError("approval proof requires the on-request policy")
        final_approval_guard = approval_guard_sha256(client, workspace)
        if final_approval_guard != approval_guard:
            raise ConnectorError("Codex approval guard changed during verification")
        final_remote = remote_readiness(client)
        if final_remote["environmentId"] != remote["environmentId"]:
            raise ConnectorError("Codex Remote environment changed during verification")
        remote = final_remote

    return {
        "approvalGuardSha256": approval_guard,
        "approvalItemId": evidence["approvalItemId"],
        "approvalPolicy": approval_policy,
        "approvalVerificationMethod": APPROVAL_VERIFICATION_METHOD,
        "approvalsReviewer": "user",
        "commandSha256": {
            "approval": evidence["approvalCommandSha256"],
            "proof": evidence["proofCommandSha256"],
        },
        "cwd": str(workspace),
        "controllerThreadBinding": CONTROLLER_THREAD_BINDING,
        "controllerThreadProjectId": None,
        "environmentId": remote["environmentId"],
        "nativeProjectId": native_project_id,
        "networkAccess": network_access,
        "projectRoot": str(workspace),
        "proofItemId": evidence["proofItemId"],
        "runtimeWorkspaceRoots": [str(workspace)],
        "sandboxType": sandbox_type,
        "threadId": thread_id,
        "turnId": evidence["turnId"],
        "verifiedAt": int(time.time()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, handler in (("register", cmd_register), ("status", cmd_status)):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--name", required=True)
        subparser.set_defaults(handler=handler)
    baseline = subparsers.add_parser("thread-baseline")
    baseline.add_argument("--name", required=True)
    baseline.set_defaults(handler=cmd_thread_baseline)
    verify = subparsers.add_parser("verify-thread")
    verify.add_argument("--name", required=True)
    verify.add_argument("--created-after", required=True, type=int)
    verify.add_argument("--baseline-thread-id", action="append", default=[])
    verify.add_argument("--proof-relative-path", required=True)
    verify.add_argument("--proof-nonce", required=True)
    verify.add_argument("--proof-command-sha256", required=True)
    verify.add_argument("--approval-nonce", required=True)
    verify.add_argument("--approval-guard-sha256", required=True)
    verify.set_defaults(handler=cmd_verify_thread)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        print(json.dumps(args.handler(args), sort_keys=True))
        return 0
    except ConnectorError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
