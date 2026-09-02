#!/usr/bin/env python3
"""Reproducible Phase 0 harness for Lift's EC2 laptop-off feasibility test."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

from workspace import (
    WorkspaceError,
    build_lift_off_archive,
    capture_baseline,
    content_manifest,
    create_fixture,
    fixture_policy_for_commit,
    sha256_file,
)
from land import LandError, land_fixture, validate_conflicted_land_fixture
from live_land import (
    LiveLandError,
    build_land_acknowledgement,
    import_final_checkpoint,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LOCAL_ROOT = REPO_ROOT / ".lift-spike"
STATE_PATH = LOCAL_ROOT / "state.json"
EVENTS_PATH = LOCAL_ROOT / "events.ndjson"
LAND_CONTROLLER_LOCK_PATH = LOCAL_ROOT / "land-controller.lock"
MAX_LOCAL_STATE_BYTES = 1024 * 1024
MAX_LOCAL_EVENTS_BYTES = 16 * 1024 * 1024
MAX_LOCAL_EVENT_BYTES = 64 * 1024
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TEMPLATE_PATH = SCRIPT_DIR / "cloudformation.yaml"
GUEST_DIR = SCRIPT_DIR / "guest"
RECIPE_PATH = SCRIPT_DIR / "recipes" / "codex-headless.json"
CODEX_PROJECT_PATH = GUEST_DIR / "codex_project.py"
APPROVAL_OBSERVER_PATH = GUEST_DIR / "approval_observer.py"
LANDING_PATH = GUEST_DIR / "landing.py"

PROFILE = "lift-spike"
REGION = "us-east-1"
CANONICAL_OWNER = "099720109477"
AMI_PARAMETER = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
WORKSPACE_ID = "lift-ec2-spike"
REMOTE_WORKSPACE = f"/home/lift/workspaces/{WORKSPACE_ID}"
REMOTE_RUNTIME_PATH = "/opt/lift-spike"
REMOTE_RUNTIME_RELEASE_ROOT = "/opt/lift-spike-releases"
REMOTE_APPROVAL_OBSERVATION_ROOT = "/var/lib/lift-spike/approval-observations"
APPROVAL_OBSERVER_TIMEOUT_SECONDS = 15 * 60
RUN_ID_PATTERN = re.compile(r"^p0-[0-9]{14}-[0-9a-f]{4}$")
LAND_OPERATION_ID_PATTERN = re.compile(
    r"^p0-[0-9]{14}-[0-9a-f]{4}-land$"
)
INSTANCE_ID_PATTERN = re.compile(r"^i-[0-9a-f]{8,17}$")
VOLUME_ID_PATTERN = re.compile(r"^vol-[0-9a-f]{8,17}$")
AMI_ID_PATTERN = re.compile(r"^ami-[0-9a-f]{8,17}$")
VPC_ID_PATTERN = re.compile(r"^vpc-[0-9a-f]{8,17}$")
SECURITY_GROUP_ID_PATTERN = re.compile(r"^sg-[0-9a-f]{8,17}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
S3_BUCKET_PATTERN = re.compile(
    r"^(?=.{3,63}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$"
)
SAFE_STACK_STATUSES = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
REQUIRED_STACK_OUTPUTS = {
    "InstanceId",
    "WorkspaceVolumeId",
    "TransferBucketName",
    "WorkspacePath",
}
KNOWN_STACK_OUTPUTS = REQUIRED_STACK_OUTPUTS | {
    "LedgerPath",
    "VpcId",
    "SecurityGroupId",
}
MAX_BASELINE_THREAD_IDS = 100
MAX_BASELINE_THREAD_ARGUMENT_BYTES = 12 * 1024
PROOF_RELATIVE_PATH_BY_SOURCE = {
    "codex-phone": ".lift/phone-proof.json",
    "codex-phone-laptop-off": ".lift/laptop-off-proof.json",
    "codex-phone-post-restart": ".lift/post-restart-proof.json",
}
CHECKPOINT_LABEL_BY_SOURCE = {
    "codex-phone": "phone-proof",
    "codex-phone-laptop-off": "laptop-off-proof",
    "codex-phone-post-restart": "post-restart-phone-proof",
}
PHONE_PROOF_SOURCES = {"codex-phone", "codex-phone-post-restart"}
INTERACTIVE_WARNING = (
    "Interactive authentication and pairing must run in an unlogged SSM session. "
    "Their output must never be captured by the harness."
)
SAFE_TO_CLOSE_REQUIRED_GATES = (
    "storageDurable",
    "manifestVerified",
    "workloadHealthy",
    "providerPhoneProbeVerified",
    "approvalRoundTripVerified",
    "recoveryCheckpointDurable",
    "localStepsComplete",
)
MIN_AUTO_STOP_REMAINING_SECONDS = 60 * 60
MAX_S3_VERSION_ID_BYTES = 1024
LAND_PHASES = {
    "REQUESTED",
    "CLOUD_FROZEN",
    "FINAL_CHECKPOINT_DURABLE",
    "IMPORTED",
    "RECONCILED",
    "NEEDS_REVIEW",
    "ACK_DURABLE",
    "COMPLETE",
}
RESTORE_TEST_KEYS = {
    "bundleLocalSha256",
    "manifestLocalSha256",
    "restoredCommit",
    "restoredTree",
    "restoredFileCount",
    "verifiedAt",
}
THREAD_VERIFICATION_METHOD = (
    "fresh-folder-bound-project-unassigned-single-turn-exact-two-wrapped-command-"
    "network-denied-user-reviewer-no-rules-hooks-plugin-state-bound-no-plugin-"
    "provenance-or-mcp-tools-v6"
)
CONTROLLER_THREAD_BINDING = "folder-bound-project-unassigned-v1"
APPROVAL_OBSERVER_VERIFICATION_METHOD = (
    "observed-folder-bound-metadata-aware-local-exec-environment-request-"
    "resolved-source-schema-amendment-consistent-wrapped-summary-success-v8"
)
APPROVAL_OBSERVER_READY_METHOD = "observer-initialized-folder-polling-v8"
APPROVAL_REQUEST_EXECUTION_ENVIRONMENT_ID = "local"
APPROVAL_VERIFICATION_METHOD = (
    "observed-folder-bound-metadata-aware-local-exec-environment-request-"
    "resolved-source-schema-amendment-consistent-wrapped-summary-success-plus-"
    "guarded-inference-v12"
)
APPROVAL_OBSERVER_READY_KEYS = frozenset(
    {
        "approvalCommandSha256",
        "approvalGuardSha256",
        "baselineThreadIdsSha256",
        "challengeSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "createdAfterEpochSeconds",
        "cwd",
        "environmentId",
        "nativeProjectId",
        "proofCommandSha256",
        "schemaVersion",
        "verificationMethod",
    }
)
APPROVAL_OBSERVATION_KEYS = frozenset(
    {
        "approvalCommandCompletedAtEpochMilliseconds",
        "approvalCommandStartedAtEpochMilliseconds",
        "approvalCommandSha256",
        "approvalGuardSha256",
        "approvalItemId",
        "baselineThreadIdsSha256",
        "challengeSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "createdAfterEpochSeconds",
        "cwd",
        "environmentId",
        "nativeProjectId",
        "observedAtEpochSeconds",
        "proofCommandCompletedAtEpochMilliseconds",
        "proofCommandStartedAtEpochMilliseconds",
        "proofCommandSha256",
        "proofItemId",
        "requestId",
        "requestEnvironmentId",
        "requestStartedAtEpochMilliseconds",
        "schemaVersion",
        "threadId",
        "threadGoalClearedCount",
        "threadNameUpdatedCount",
        "turnCompletedAtEpochSeconds",
        "turnId",
        "verificationMethod",
    }
)


class SpikeError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@contextmanager
def land_controller_lock() -> Any:
    """Serialize the complete controller-side Land transaction.

    A single lock spans local state, exact S3 version selection, guest receipt,
    reconciliation, acknowledgement, and optional compute cleanup. Without it,
    two resume attempts could each create a different immutable S3 version for
    the same bytes and permanently disagree about the final checkpoint.
    """

    directory, name = private_parent_descriptor(LAND_CONTROLLER_LOCK_PATH)
    descriptor = -1
    try:
        descriptor = validated_private_file_descriptor(
            directory,
            name,
            os.O_RDWR,
            maximum_size=0,
            create=True,
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        os.close(directory)


def scrubbed_environment() -> dict[str, str]:
    environment = os.environ.copy()
    forbidden = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "AWS_CA_BUNDLE",
        "AWS_ENDPOINT_URL",
        "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS",
        "AWS_LOGIN_CACHE_DIRECTORY",
        "AWS_METADATA_SERVICE_ENDPOINT",
        "AWS_METADATA_SERVICE_ENDPOINT_MODE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "BOTO_CONFIG",
    }
    for key in list(environment):
        if key in forbidden or key.startswith("AWS_ENDPOINT_URL_"):
            environment.pop(key, None)
    environment["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"] = "true"
    return environment


def command_environment(command: list[str]) -> dict[str, str]:
    environment = scrubbed_environment()
    if command and Path(command[0]).name == "git":
        for key in list(environment):
            if key.startswith("GIT_"):
                environment.pop(key, None)
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
    return environment


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=command_environment(command),
        text=True,
        capture_output=capture,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip() if completed.stderr else ""
        raise SpikeError(f"command failed ({' '.join(command)}): {stderr}")
    return completed


def run_bytes(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        env=command_environment(command),
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise SpikeError(
            f"command failed ({' '.join(command)}): "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed


def aws_arguments(service: str, operation: str, *arguments: str) -> list[str]:
    return [
        "aws",
        service,
        operation,
        *arguments,
        "--profile",
        PROFILE,
        "--region",
        REGION,
        "--no-cli-pager",
    ]


def aws_json(service: str, operation: str, *arguments: str) -> dict[str, Any]:
    completed = run([*aws_arguments(service, operation, *arguments), "--output", "json"])
    try:
        value = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SpikeError(f"AWS returned invalid JSON for {service} {operation}") from exc
    if not isinstance(value, dict):
        raise SpikeError(f"AWS returned a non-object for {service} {operation}")
    return value


def aws_raw(service: str, operation: str, *arguments: str, timeout: int | None = None) -> str:
    return run(aws_arguments(service, operation, *arguments), timeout=timeout).stdout


def private_parent_descriptor(path: Path) -> tuple[int, str]:
    """Open one private control directory without following a symlink."""
    parent = path.parent
    name = path.name
    if not name or name in {".", ".."}:
        raise SpikeError("local control file path is invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(parent, flags)
    except FileNotFoundError:
        try:
            os.mkdir(parent, PRIVATE_DIRECTORY_MODE)
        except FileExistsError:
            pass
        except OSError as exc:
            raise SpikeError(f"cannot create private local control directory: {exc}") from exc
        try:
            descriptor = os.open(parent, flags)
        except OSError as exc:
            raise SpikeError(f"cannot open private local control directory: {exc}") from exc
    except OSError as exc:
        raise SpikeError(f"cannot open private local control directory: {exc}") from exc

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise SpikeError("local control directory must be a real owned directory")
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE:
            os.fchmod(descriptor, PRIVATE_DIRECTORY_MODE)
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE:
            raise SpikeError("local control directory must have mode 0700")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, name


def validated_private_file_descriptor(
    directory_descriptor: int,
    name: str,
    flags: int,
    *,
    maximum_size: int,
    create: bool = False,
) -> int:
    open_flags = flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if create:
        open_flags |= os.O_CREAT
    try:
        descriptor = os.open(
            name,
            open_flags,
            PRIVATE_FILE_MODE,
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        raise SpikeError(f"cannot open private local control file {name}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise SpikeError("local control file must be a single-link owned regular file")
        if metadata.st_size > maximum_size:
            raise SpikeError("local control file exceeds its size limit")
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE:
            raise SpikeError("local control file must have mode 0600")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def private_file_exists(path: Path, *, maximum_size: int) -> bool:
    directory_descriptor, name = private_parent_descriptor(path)
    try:
        try:
            descriptor = validated_private_file_descriptor(
                directory_descriptor,
                name,
                os.O_RDONLY,
                maximum_size=maximum_size,
            )
        except SpikeError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return False
            raise
        else:
            os.close(descriptor)
            return True
    finally:
        os.close(directory_descriptor)


def read_private_file(path: Path, *, maximum_size: int) -> bytes:
    directory_descriptor, name = private_parent_descriptor(path)
    try:
        descriptor = validated_private_file_descriptor(
            directory_descriptor,
            name,
            os.O_RDONLY,
            maximum_size=maximum_size,
        )
        try:
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(descriptor, min(65536, maximum_size + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > maximum_size:
                    raise SpikeError("local control file exceeds its size limit")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory_descriptor)


def atomic_state(value: dict[str, Any]) -> None:
    try:
        encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SpikeError("local spike state is not serializable") from exc
    if len(encoded) > MAX_LOCAL_STATE_BYTES:
        raise SpikeError("local spike state exceeds its size limit")

    directory_descriptor, name = private_parent_descriptor(STATE_PATH)
    temporary_name: str | None = None
    temporary_descriptor = -1
    try:
        try:
            existing = validated_private_file_descriptor(
                directory_descriptor,
                name,
                os.O_RDONLY,
                maximum_size=MAX_LOCAL_STATE_BYTES,
            )
        except SpikeError as exc:
            if not isinstance(exc.__cause__, FileNotFoundError):
                raise
        else:
            os.close(existing)

        for _ in range(16):
            candidate = f".{name}.{secrets.token_hex(16)}.tmp"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    PRIVATE_FILE_MODE,
                    dir_fd=directory_descriptor,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise SpikeError(f"cannot create private state temporary file: {exc}") from exc
            temporary_name = candidate
            break
        if temporary_name is None or temporary_descriptor < 0:
            raise SpikeError("cannot allocate a unique private state temporary file")

        offset = 0
        while offset < len(encoded):
            written = os.write(temporary_descriptor, encoded[offset:])
            if written <= 0:
                raise SpikeError("cannot write complete local spike state")
            offset += written
        os.fsync(temporary_descriptor)
        metadata = os.fstat(temporary_descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
            or metadata.st_size != len(encoded)
        ):
            raise SpikeError("private state temporary file failed validation")
        os.close(temporary_descriptor)
        temporary_descriptor = -1
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        temporary_name = None
        os.fsync(directory_descriptor)
    except OSError as exc:
        raise SpikeError(f"cannot persist local spike state: {exc}") from exc
    finally:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
        os.close(directory_descriptor)


def atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    try:
        encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SpikeError("private Land record is not serializable") from exc
    if len(encoded) > MAX_LOCAL_STATE_BYTES:
        raise SpikeError("private Land record exceeds its size limit")
    directory, name = private_parent_descriptor(path)
    temporary = f".{name}.{secrets.token_hex(16)}.tmp"
    descriptor = -1
    try:
        if private_file_exists(path, maximum_size=MAX_LOCAL_STATE_BYTES):
            pass
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
            dir_fd=directory,
        )
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise SpikeError("could not write complete private Land record")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
        ):
            raise SpikeError("private Land record temporary file is unsafe")
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except OSError as exc:
        raise SpikeError(f"cannot persist private Land record: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def valid_s3_bucket_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and S3_BUCKET_PATTERN.fullmatch(value) is not None
        and ".." not in value
        and ".-" not in value
        and "-." not in value
        and re.fullmatch(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}", value) is None
    )


def validate_loaded_state(state: Any) -> dict[str, Any]:
    if (
        not isinstance(state, dict)
        or type(state.get("schemaVersion")) is not int
        or state.get("schemaVersion") != 1
    ):
        raise SpikeError("unsupported local spike state")
    revision = state.get("revision")
    run_id = state.get("runId")
    workspace_id = state.get("workspaceId")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise SpikeError("local spike state has an invalid revision")
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise SpikeError("local spike state has an invalid run ID")
    if workspace_id != WORKSPACE_ID:
        raise SpikeError("local spike state has the wrong workspace ID")

    identity = state.get("identity")
    if not isinstance(identity, dict):
        raise SpikeError("local spike state has no immutable AWS identity")
    account_id = identity.get("accountId")
    principal_arn = identity.get("principalArn")
    if (
        not isinstance(account_id, str)
        or re.fullmatch(r"[0-9]{12}", account_id) is None
        or identity.get("profile") != PROFILE
        or identity.get("region") != REGION
        or principal_arn != f"arn:aws:iam::{account_id}:user/lift-admin"
        or not isinstance(identity.get("userId"), str)
        or not identity["userId"]
    ):
        raise SpikeError("local spike state has an invalid immutable AWS identity")

    runtime = state.get("runtime")
    if not isinstance(runtime, dict):
        raise SpikeError("local spike state has no runtime record")
    expected_stack_name = f"lift-{run_id}"
    if runtime.get("stackName") != expected_stack_name:
        raise SpikeError("local spike state has an invalid stack name")
    ami_id = runtime.get("amiId")
    if ami_id is not None and (
        not isinstance(ami_id, str) or AMI_ID_PATTERN.fullmatch(ami_id) is None
    ):
        raise SpikeError("local spike state has an invalid AMI ID")

    outputs = runtime.get("outputs")
    stack_id = runtime.get("stackId")
    if outputs is not None:
        if not isinstance(outputs, dict) or not REQUIRED_STACK_OUTPUTS.issubset(outputs):
            raise SpikeError("local spike state has incomplete stack outputs")
        if not set(outputs).issubset(KNOWN_STACK_OUTPUTS):
            raise SpikeError("local spike state has unknown stack outputs")
        if any(not isinstance(value, str) for value in outputs.values()):
            raise SpikeError("local spike state has a non-string stack output")
        if INSTANCE_ID_PATTERN.fullmatch(outputs["InstanceId"]) is None:
            raise SpikeError("local spike state has an invalid instance ID")
        if VOLUME_ID_PATTERN.fullmatch(outputs["WorkspaceVolumeId"]) is None:
            raise SpikeError("local spike state has an invalid workspace volume ID")
        if not valid_s3_bucket_name(outputs["TransferBucketName"]):
            raise SpikeError("local spike state has an invalid transfer bucket")
        if outputs["WorkspacePath"] != REMOTE_WORKSPACE:
            raise SpikeError("local spike state has a non-canonical workspace path")
        if outputs.get("LedgerPath", "/var/lib/lift/ledger") != "/var/lib/lift/ledger":
            raise SpikeError("local spike state has a non-canonical ledger path")
        if "VpcId" in outputs and VPC_ID_PATTERN.fullmatch(outputs["VpcId"]) is None:
            raise SpikeError("local spike state has an invalid VPC ID")
        if (
            "SecurityGroupId" in outputs
            and SECURITY_GROUP_ID_PATTERN.fullmatch(outputs["SecurityGroupId"]) is None
        ):
            raise SpikeError("local spike state has an invalid security group ID")
        stack_prefix = (
            f"arn:aws:cloudformation:{REGION}:{account_id}:stack/"
            f"{expected_stack_name}/"
        )
        if (
            not isinstance(stack_id, str)
            or re.fullmatch(
                re.escape(stack_prefix)
                + r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                stack_id,
            )
            is None
        ):
            raise SpikeError("local spike state has an invalid stack ID")
        if ami_id is None:
            raise SpikeError("local spike state with stack outputs has no AMI ID")
    elif stack_id is not None:
        raise SpikeError("local spike state has a stack ID without stack outputs")

    workspace = state.get("workspace")
    if not isinstance(workspace, dict):
        raise SpikeError("local spike state has no workspace record")
    if workspace.get("lease") not in {
        "LOCAL_PRIMARY",
        "LIFTING",
        "CLOUD_PRIMARY",
        "LANDING",
    }:
        raise SpikeError("local spike state has an invalid workspace lease")
    land_state = workspace.get("land")
    if land_state is not None:
        if not isinstance(land_state, dict) or land_state.get("schemaVersion") != 1:
            raise SpikeError("local spike state has an invalid Land operation")
        operation_id = land_state.get("operationId")
        phase = land_state.get("phase")
        ordinal = land_state.get("ordinal")
        if (
            not isinstance(operation_id, str)
            or LAND_OPERATION_ID_PATTERN.fullmatch(operation_id) is None
            or phase not in LAND_PHASES
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 1
            or ordinal > 9999
        ):
            raise SpikeError("local spike state has invalid Land operation identity")
        if phase == "COMPLETE" and workspace.get("lease") != "LOCAL_PRIMARY":
            raise SpikeError("completed Land state must return the local ownership lease")
        if phase != "COMPLETE" and workspace.get("lease") != "LANDING":
            raise SpikeError("incomplete Land state must retain the LANDING lease")
    expected_run_dir = LOCAL_ROOT / "runs" / run_id
    if (
        "localPath" in workspace
        and workspace["localPath"] != str(expected_run_dir / "fixture-local")
    ):
        raise SpikeError("local spike state has a non-canonical local workspace path")
    if (
        "ledgerPath" in workspace
        and workspace["ledgerPath"] != str(expected_run_dir / "ledger.git")
    ):
        raise SpikeError("local spike state has a non-canonical local ledger path")
    if "cloudPath" in workspace and workspace["cloudPath"] != REMOTE_WORKSPACE:
        raise SpikeError("local spike state has a non-canonical cloud workspace path")
    return state


def load_state() -> dict[str, Any]:
    try:
        raw = read_private_file(STATE_PATH, maximum_size=MAX_LOCAL_STATE_BYTES)
    except SpikeError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            raise SpikeError(
                "run `spike.py init --expected-account <account-id>` first"
            ) from exc
        raise
    if EVENTS_PATH.parent == STATE_PATH.parent:
        private_file_exists(EVENTS_PATH, maximum_size=MAX_LOCAL_EVENTS_BYTES)
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpikeError("local spike state is corrupt") from exc
    return validate_loaded_state(state)


def record_event(event_type: str, **details: Any) -> None:
    event = {"at": now_iso(), "type": event_type, **details}
    try:
        encoded = (
            json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SpikeError("local event is not serializable") from exc
    if len(encoded) > MAX_LOCAL_EVENT_BYTES:
        raise SpikeError("local event exceeds its size limit")

    directory_descriptor, name = private_parent_descriptor(EVENTS_PATH)
    try:
        descriptor = validated_private_file_descriptor(
            directory_descriptor,
            name,
            os.O_WRONLY | os.O_APPEND,
            maximum_size=MAX_LOCAL_EVENTS_BYTES,
            create=True,
        )
        try:
            current_size = os.fstat(descriptor).st_size
            if current_size + len(encoded) > MAX_LOCAL_EVENTS_BYTES:
                raise SpikeError("local event log exceeds its size limit")
            offset = 0
            while offset < len(encoded):
                written = os.write(descriptor, encoded[offset:])
                if written <= 0:
                    raise SpikeError("cannot append complete local event")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory_descriptor)
    except OSError as exc:
        raise SpikeError(f"cannot append local event: {exc}") from exc
    finally:
        os.close(directory_descriptor)


def caller_identity() -> dict[str, str]:
    identity = aws_json("sts", "get-caller-identity")
    return {
        "accountId": str(identity.get("Account", "")),
        "principalArn": str(identity.get("Arn", "")),
        "userId": str(identity.get("UserId", "")),
    }


def assert_identity(state: dict[str, Any]) -> dict[str, str]:
    expected = state["identity"]
    actual = caller_identity()
    if actual["accountId"] != expected["accountId"]:
        raise SpikeError("AWS account changed; refusing to continue")
    if actual["principalArn"] != expected["principalArn"]:
        raise SpikeError("AWS principal changed; refusing to continue")
    if actual["userId"] != expected["userId"]:
        raise SpikeError("AWS principal identity changed; refusing to continue")
    if actual["principalArn"].endswith(":root"):
        raise SpikeError("root AWS sessions are prohibited")
    return actual


def validate_ami(ami_id: Any) -> str:
    if not isinstance(ami_id, str) or AMI_ID_PATTERN.fullmatch(ami_id) is None:
        raise SpikeError("Canonical AMI selection did not contain a valid AMI ID")
    image = aws_json("ec2", "describe-images", "--image-ids", ami_id)
    images = image.get("Images", [])
    if (
        not isinstance(images, list)
        or len(images) != 1
        or not isinstance(images[0], dict)
        or images[0].get("ImageId") != ami_id
        or images[0].get("OwnerId") != CANONICAL_OWNER
    ):
        raise SpikeError("resolved AMI is not owned by Canonical")
    if images[0].get("Architecture") != "x86_64" or images[0].get("State") != "available":
        raise SpikeError("resolved AMI is not an available x86_64 image")
    return ami_id


def resolve_ami() -> str:
    parameter = aws_json("ssm", "get-parameter", "--name", AMI_PARAMETER)
    try:
        ami_id = parameter["Parameter"]["Value"]
    except (KeyError, TypeError) as exc:
        raise SpikeError("Canonical AMI parameter did not return an AMI ID") from exc
    return validate_ami(ami_id)


def describe_stack(stack_name: str) -> dict[str, Any]:
    response = aws_json("cloudformation", "describe-stacks", "--stack-name", stack_name)
    stacks = response.get("Stacks", [])
    if not isinstance(stacks, list) or len(stacks) != 1:
        raise SpikeError(f"expected exactly one stack named {stack_name}")
    stack = stacks[0]
    if not isinstance(stack, dict):
        raise SpikeError("CloudFormation returned a malformed stack")
    return stack


def assert_stack_absent_for_create(stack_name: str) -> None:
    """Fail closed unless CloudFormation proves this exact stack name is unused."""
    completed = run(
        [
            *aws_arguments(
                "cloudformation", "describe-stacks", "--stack-name", stack_name
            ),
            "--output",
            "json",
        ],
        check=False,
    )
    if completed.returncode == 0:
        raise SpikeError(
            "the unbound local state conflicts with an existing CloudFormation stack"
        )
    expected_error = (
        "An error occurred (ValidationError) when calling the DescribeStacks operation: "
        f"Stack with id {stack_name} does not exist"
    )
    # AWS CLI 2.35 added a stable diagnostic prefix to service errors. Keep
    # this proof fail-closed by accepting only the exact legacy response or
    # that same exact response with the documented CLI prefix.
    accepted_errors = {expected_error, f"aws: [ERROR]: {expected_error}"}
    if (
        (completed.stdout or "").strip()
        or (completed.stderr or "").strip() not in accepted_errors
    ):
        raise SpikeError(
            "CloudFormation did not prove that the exact stack name is available"
        )


def stack_output_map(stack: dict[str, Any]) -> dict[str, str]:
    raw_outputs = stack.get("Outputs", [])
    if not isinstance(raw_outputs, list):
        raise SpikeError("CloudFormation returned malformed stack outputs")
    outputs: dict[str, str] = {}
    for item in raw_outputs:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("OutputKey"), str)
            or not isinstance(item.get("OutputValue"), str)
            or item["OutputKey"] in outputs
        ):
            raise SpikeError("CloudFormation returned malformed stack outputs")
        outputs[item["OutputKey"]] = item["OutputValue"]
    return outputs


def stack_outputs(stack_name: str) -> dict[str, str]:
    return stack_output_map(describe_stack(stack_name))


def validated_stack_context(state: dict[str, Any]) -> dict[str, str]:
    validate_loaded_state(state)
    runtime = state["runtime"]
    stored_outputs = runtime.get("outputs")
    stack_name = runtime["stackName"]
    stack_id = runtime.get("stackId")
    if not isinstance(stored_outputs, dict) or not isinstance(stack_id, str):
        raise SpikeError("the deployed stack context is incomplete")

    stack = describe_stack(stack_name)
    if (
        stack.get("StackName") != stack_name
        or stack.get("StackId") != stack_id
        or stack.get("StackStatus") not in SAFE_STACK_STATUSES
    ):
        raise SpikeError("the live CloudFormation stack identity is not safe to use")
    live_outputs = stack_output_map(stack)
    if live_outputs != stored_outputs:
        raise SpikeError("the live CloudFormation outputs differ from local state")

    parameters = stack.get("Parameters", [])
    if not isinstance(parameters, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("ParameterKey"), str)
        or not isinstance(item.get("ParameterValue"), str)
        for item in parameters
    ):
        raise SpikeError("the live CloudFormation parameters are malformed")
    parameter_map: dict[str, str] = {}
    for item in parameters:
        if item["ParameterKey"] in parameter_map:
            raise SpikeError("the live CloudFormation parameters are malformed")
        parameter_map[item["ParameterKey"]] = item["ParameterValue"]
    expected_parameters = {
        "AmiId": runtime["amiId"],
        "InstanceType": "c7i-flex.large",
        "WorkspaceVolumeSize": "30",
        "AutoStopMinutes": "240",
        "SpikeId": state["runId"],
    }
    if any(parameter_map.get(key) != value for key, value in expected_parameters.items()):
        raise SpikeError("the live CloudFormation parameters differ from local state")

    response = aws_json(
        "cloudformation", "describe-stack-resources", "--stack-name", stack_id
    )
    raw_resources = response.get("StackResources", [])
    if not isinstance(raw_resources, list):
        raise SpikeError("CloudFormation returned malformed stack resources")
    resources: dict[str, dict[str, Any]] = {}
    for item in raw_resources:
        logical_id = item.get("LogicalResourceId") if isinstance(item, dict) else None
        if not isinstance(logical_id, str) or logical_id in resources:
            raise SpikeError("CloudFormation returned malformed stack resources")
        resources[logical_id] = item
    expected_resources = {
        "WorkspaceInstance": ("AWS::EC2::Instance", stored_outputs["InstanceId"]),
        "WorkspaceVolume": ("AWS::EC2::Volume", stored_outputs["WorkspaceVolumeId"]),
        "TransferBucket": ("AWS::S3::Bucket", stored_outputs["TransferBucketName"]),
    }
    for logical_id, (resource_type, physical_id) in expected_resources.items():
        resource = resources.get(logical_id, {})
        status = resource.get("ResourceStatus")
        if (
            resource.get("ResourceType") != resource_type
            or resource.get("PhysicalResourceId") != physical_id
            or status not in SAFE_STACK_STATUSES
        ):
            raise SpikeError(
                f"the live CloudFormation resource {logical_id} is not bound to local state"
            )
    return dict(stored_outputs)


def wait_for_ssm(instance_id: str, timeout_seconds: int = 600) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = aws_json(
            "ssm",
            "describe-instance-information",
            "--filters",
            f"Key=InstanceIds,Values={instance_id}",
        )
        items = response.get("InstanceInformationList", [])
        if items and items[0].get("PingStatus") == "Online":
            return
        time.sleep(10)
    raise SpikeError("instance did not become available through Systems Manager")


def send_command(instance_id: str, commands: list[str], comment: str, timeout_seconds: int = 900) -> str:
    script = "#!/usr/bin/env bash\n" + "\n".join(commands) + "\n"
    encoded_script = base64.b64encode(script.encode("utf-8")).decode("ascii")
    parameters = json.dumps(
        {
            "commands": [
                f"printf '%s' '{encoded_script}' | base64 --decode | /usr/bin/env bash"
            ],
            "executionTimeout": [str(timeout_seconds)],
        },
        separators=(",", ":"),
    )
    response = aws_json(
        "ssm",
        "send-command",
        "--instance-ids",
        instance_id,
        "--document-name",
        "AWS-RunShellScript",
        "--comment",
        comment,
        "--parameters",
        parameters,
    )
    try:
        command_id = response["Command"]["CommandId"]
    except (KeyError, TypeError) as exc:
        raise SpikeError("Systems Manager did not return a command ID") from exc

    # SSM can acknowledge SendCommand before the per-instance invocation exists.
    # Give the control plane a moment, then treat that eventual-consistency error
    # as a retry rather than a failed spike.
    time.sleep(1)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            invocation = aws_json(
                "ssm",
                "get-command-invocation",
                "--command-id",
                command_id,
                "--instance-id",
                instance_id,
            )
        except SpikeError as exc:
            if "InvocationDoesNotExist" not in str(exc):
                raise
            time.sleep(3)
            continue
        status = invocation.get("Status")
        if status == "Success":
            return str(invocation.get("StandardOutputContent", "")).strip()
        if status in {"Cancelled", "Cancelling", "Failed", "TimedOut"}:
            error = str(invocation.get("StandardErrorContent", "")).strip()
            raise SpikeError(f"SSM command {comment!r} failed ({status}): {error}")
        time.sleep(3)
    raise SpikeError(f"SSM command {comment!r} timed out")


def build_runtime_bundle(run_dir: Path) -> tuple[Path, str]:
    destination = run_dir / "artifacts" / "guest-runtime.tar.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(GUEST_DIR / "runner.py", arcname="runner.py", recursive=False)
        archive.add(CODEX_PROJECT_PATH, arcname="codex_project.py", recursive=False)
        archive.add(
            APPROVAL_OBSERVER_PATH,
            arcname="approval_observer.py",
            recursive=False,
        )
        archive.add(GUEST_DIR / "reconstruct.py", arcname="reconstruct.py", recursive=False)
        archive.add(GUEST_DIR / "checkpoint.py", arcname="checkpoint.py", recursive=False)
        archive.add(LANDING_PATH, arcname="landing.py", recursive=False)
        archive.add(RECIPE_PATH, arcname="recipes/codex-headless.json", recursive=False)
    return destination, sha256_file(destination)


def upload_file(path: Path, bucket: str, key: str) -> None:
    aws_raw(
        "s3",
        "cp",
        str(path),
        f"s3://{bucket}/{key}",
        "--sse",
        "AES256",
        timeout=300,
    )


def validated_runtime_install_context(
    state: dict[str, Any],
) -> tuple[str, str, str]:
    validate_loaded_state(state)
    runtime = state.get("runtime", {})
    outputs = runtime.get("outputs") if isinstance(runtime, dict) else None
    if not isinstance(outputs, dict):
        raise SpikeError("the runtime must exist before installing guest tools")
    run_id = state.get("runId")
    instance_id = outputs.get("InstanceId")
    bucket = outputs.get("TransferBucketName")
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise SpikeError("runtime installation received an invalid run ID")
    if (
        not isinstance(instance_id, str)
        or INSTANCE_ID_PATTERN.fullmatch(instance_id) is None
    ):
        raise SpikeError("runtime installation received an invalid instance ID")
    if not valid_s3_bucket_name(bucket):
        raise SpikeError("runtime installation received an invalid transfer bucket")
    return run_id, instance_id, bucket


def runtime_install_commands(
    *,
    bucket: str,
    runtime_key: str,
    runtime_sha: str,
    expected_files: dict[str, tuple[str, str]],
) -> list[str]:
    if SHA256_PATTERN.fullmatch(runtime_sha) is None:
        raise SpikeError("runtime bundle SHA-256 was invalid")
    if (
        not valid_s3_bucket_name(bucket)
        or re.fullmatch(
            rf"sessions/p0-[0-9]{{14}}-[0-9a-f]{{4}}/runtime/{runtime_sha}\.tar\.gz",
            runtime_key,
        )
        is None
    ):
        raise SpikeError("runtime object location was invalid")
    expected_names = {
        "runner.py",
        "codex_project.py",
        "approval_observer.py",
        "reconstruct.py",
        "checkpoint.py",
        "landing.py",
        "recipes/codex-headless.json",
    }
    if set(expected_files) != expected_names:
        raise SpikeError("runtime release file set was invalid")
    for relative_path, (expected_sha, expected_mode) in expected_files.items():
        if (
            relative_path.startswith("/")
            or ".." in Path(relative_path).parts
            or SHA256_PATTERN.fullmatch(expected_sha) is None
            or expected_mode not in {"0644", "0755"}
        ):
            raise SpikeError("runtime release metadata was invalid")

    release_path = f"{REMOTE_RUNTIME_RELEASE_ROOT}/{runtime_sha}"
    archive_uri = f"s3://{bucket}/{runtime_key}"
    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C",
        "umask 077",
        f"RUNTIME_SHA={shlex.quote(runtime_sha)}",
        f"ACTIVE_PATH={shlex.quote(REMOTE_RUNTIME_PATH)}",
        f"RELEASE_ROOT={shlex.quote(REMOTE_RUNTIME_RELEASE_ROOT)}",
        f"RELEASE_DIR={shlex.quote(release_path)}",
        'LOCK_PATH="/var/lib/lift-spike/runtime-install.lock"',
        'TMP_DIR=$(mktemp -d /var/lib/lift-spike/runtime.XXXXXX)',
        'STAGE_DIR=""',
        'ACTIVATE_LINK=""',
        'ROLLBACK_LINK=""',
        'LEGACY_DIR=""',
        'PREVIOUS_KIND="missing"',
        'PREVIOUS_TARGET=""',
        'SERVICE_UNIT="lift-workload.service"',
        'SERVICE_UNIT_PATH="/etc/systemd/system/lift-workload.service"',
        "SERVICE_WAS_PRESENT=0",
        "SERVICE_WAS_ACTIVE=0",
        "SERVICE_WAS_ENABLED=0",
        "SERVICE_STATE_CAPTURED=0",
        "SERVICE_MUTATION_STARTED=0",
        "SWITCH_STARTED=0",
        (
            "trap 'status=$?; printf \"%s\\n\" "
            "\"runtime install failed at script line $LINENO (status $status)\" "
            ">&2; exit \"$status\"' ERR"
        ),
        "cleanup_runtime_install() {",
        '  if [ -n "${STAGE_DIR:-}" ]; then rm -rf -- "$STAGE_DIR"; fi',
        '  if [ -n "${ACTIVATE_LINK:-}" ]; then rm -f -- "$ACTIVATE_LINK"; fi',
        '  if [ -n "${ROLLBACK_LINK:-}" ]; then rm -f -- "$ROLLBACK_LINK"; fi',
        '  rm -rf -- "$TMP_DIR"',
        "}",
        "fail_closed_service() {",
        '  systemctl disable --now "$SERVICE_UNIT" >/dev/null 2>&1 || true',
        '  systemctl reset-failed "$SERVICE_UNIT" >/dev/null 2>&1 || true',
        '  if systemctl is-active --quiet "$SERVICE_UNIT"; then return 1; fi',
        '  if systemctl is-enabled --quiet "$SERVICE_UNIT"; then return 1; fi',
        "  return 0",
        "}",
        "validate_runnable_runtime() {",
        '  local runtime="$1"',
        '  test -d "$runtime"',
        '  test ! -L "$runtime"',
        '  test -d "$runtime/recipes"',
        '  test ! -L "$runtime/recipes"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$runtime")" = "755:0:0:directory"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$runtime/recipes")" = "755:0:0:directory"',
        '  test -z "$(find "$runtime" -xdev -type l -print -quit)"',
        '  test -f "$runtime/runner.py"',
        '  test ! -L "$runtime/runner.py"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$runtime/runner.py")" = "755:0:0:regular file"',
        '  test -f "$runtime/recipes/codex-headless.json"',
        '  test ! -L "$runtime/recipes/codex-headless.json"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$runtime/recipes/codex-headless.json")" = "644:0:0:regular file"',
        "}",
        "validate_active_runtime() {",
        '  local active_target active_name',
        '  if [ -L "$ACTIVE_PATH" ]; then',
        '    active_target=$(realpath -e -- "$ACTIVE_PATH")',
        '    case "$active_target" in "$RELEASE_ROOT"/*) ;; *) return 1 ;; esac',
        '    active_name=${active_target##*/}',
        '    printf \'%s\\n\' "$active_name" | grep -Eq \'^[0-9a-f]{64}$\'',
        '    validate_runnable_runtime "$active_target"',
        '  elif [ -d "$ACTIVE_PATH" ]; then',
        '    validate_runnable_runtime "$ACTIVE_PATH"',
        "  else",
        "    return 1",
        "  fi",
        "}",
        "capture_service_intent() {",
        '  local load_state active_state enabled_state',
        '  load_state=$(systemctl show "$SERVICE_UNIT" --property=LoadState --value 2>/dev/null || true)',
        '  active_state=$(systemctl show "$SERVICE_UNIT" --property=ActiveState --value 2>/dev/null || true)',
        '  enabled_state=$(systemctl is-enabled "$SERVICE_UNIT" 2>/dev/null || true)',
        '  case "$load_state" in',
        "    loaded)",
        "      SERVICE_WAS_PRESENT=1",
        '      case "$active_state" in',
        '        active|activating|reloading) SERVICE_WAS_ACTIVE=1 ;;',
        '        inactive|failed) SERVICE_WAS_ACTIVE=0 ;;',
        '        *) return 1 ;;',
        "      esac",
        '      case "$enabled_state" in',
        '        enabled) SERVICE_WAS_ENABLED=1 ;;',
        '        disabled) SERVICE_WAS_ENABLED=0 ;;',
        '        *) return 1 ;;',
        "      esac",
        "      ;;",
        "    not-found)",
        "      SERVICE_WAS_PRESENT=0",
        '      case "$active_state" in inactive|"") ;; *) return 1 ;; esac',
        '      case "$enabled_state" in not-found|"") ;; *) return 1 ;; esac',
        "      ;;",
        '    *) return 1 ;;',
        "  esac",
        "  SERVICE_STATE_CAPTURED=1",
        "}",
        "remove_inactive_service_definition() {",
        '  fail_closed_service || return 1',
        '  if [ -e "$SERVICE_UNIT_PATH" ] || [ -L "$SERVICE_UNIT_PATH" ]; then',
        '    test -f "$SERVICE_UNIT_PATH"',
        '    test ! -L "$SERVICE_UNIT_PATH"',
        '    test "$(stat -c \'%a:%u:%g:%F\' -- "$SERVICE_UNIT_PATH")" = "644:0:0:regular file"',
        '    rm -f -- "$SERVICE_UNIT_PATH" || return 1',
        "  fi",
        "  systemctl daemon-reload || return 1",
        '  local load_state active_state enabled_state',
        '  load_state=$(systemctl show "$SERVICE_UNIT" --property=LoadState --value 2>/dev/null || true)',
        '  active_state=$(systemctl show "$SERVICE_UNIT" --property=ActiveState --value 2>/dev/null || true)',
        '  enabled_state=$(systemctl is-enabled "$SERVICE_UNIT" 2>/dev/null || true)',
        '  test "$load_state" = "not-found"',
        '  case "$active_state" in inactive|"") ;; *) return 1 ;; esac',
        '  case "$enabled_state" in not-found|"") ;; *) return 1 ;; esac',
        "}",
        "quiesce_service() {",
        "  SERVICE_MUTATION_STARTED=1",
        '  if [ "$SERVICE_WAS_PRESENT" -eq 1 ]; then',
        '    systemctl disable --now "$SERVICE_UNIT"',
        "  fi",
        '  if systemctl is-active --quiet "$SERVICE_UNIT"; then return 1; fi',
        '  if systemctl is-enabled --quiet "$SERVICE_UNIT"; then return 1; fi',
        "}",
        "restore_service_intent() {",
        '  if [ "$SERVICE_STATE_CAPTURED" -ne 1 ]; then return 1; fi',
        '  if [ "$SERVICE_WAS_ACTIVE" -eq 0 ] && [ "$SERVICE_WAS_ENABLED" -eq 0 ]; then',
        '    if systemctl is-active --quiet "$SERVICE_UNIT"; then return 1; fi',
        '    if systemctl is-enabled --quiet "$SERVICE_UNIT"; then return 1; fi',
        '    if [ -L "$ACTIVE_PATH" ] || [ -d "$ACTIVE_PATH" ]; then',
        "      validate_active_runtime || return 1",
        '    elif [ "$PREVIOUS_KIND" != "missing" ]; then',
        "      return 1",
        "    fi",
        '    if [ "$SERVICE_WAS_PRESENT" -eq 1 ]; then remove_inactive_service_definition || return 1; fi',
        "    return 0",
        "  fi",
        "  validate_active_runtime || return 1",
        (
            '  python3 "$ACTIVE_PATH/runner.py" start '
            '--recipe "$ACTIVE_PATH/recipes/codex-headless.json" '
            f"--workspace {shlex.quote(REMOTE_WORKSPACE)} >/dev/null || return 1"
        ),
        '  if [ "$SERVICE_WAS_ACTIVE" -eq 0 ]; then',
        '    systemctl stop "$SERVICE_UNIT" || return 1',
        "  fi",
        '  if [ "$SERVICE_WAS_ENABLED" -eq 0 ]; then',
        '    systemctl disable "$SERVICE_UNIT" || return 1',
        "  fi",
        '  if [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then',
        '    systemctl is-active --quiet "$SERVICE_UNIT" || return 1',
        '    python3 "$ACTIVE_PATH/runner.py" status >/dev/null || return 1',
        "  elif systemctl is-active --quiet \"$SERVICE_UNIT\"; then",
        "    return 1",
        "  fi",
        '  if [ "$SERVICE_WAS_ENABLED" -eq 1 ]; then',
        '    systemctl is-enabled --quiet "$SERVICE_UNIT" || return 1',
        "  elif systemctl is-enabled --quiet \"$SERVICE_UNIT\"; then",
        "    return 1",
        "  fi",
        "}",
        "rollback_active_runtime() {",
        '  case "$PREVIOUS_KIND" in',
        "    symlink)",
        '      ROLLBACK_LINK=$(mktemp "$RELEASE_ROOT/.rollback.XXXXXX") || return 1',
        '      rm -f -- "$ROLLBACK_LINK" || return 1',
        '      ln -s -- "$PREVIOUS_TARGET" "$ROLLBACK_LINK" || return 1',
        '      mv -Tf -- "$ROLLBACK_LINK" "$ACTIVE_PATH" || return 1',
        '      ROLLBACK_LINK=""',
        "      ;;",
        "    directory)",
        '      if [ -n "$LEGACY_DIR" ] && [ -d "$LEGACY_DIR" ]; then',
        '        if [ -L "$ACTIVE_PATH" ]; then rm -f -- "$ACTIVE_PATH" || return 1; fi',
        '        if [ -e "$ACTIVE_PATH" ] || [ -L "$ACTIVE_PATH" ]; then return 1; fi',
        '        mv -T -- "$LEGACY_DIR" "$ACTIVE_PATH" || return 1',
        '        LEGACY_DIR=""',
        "      fi",
        "      ;;",
        "    missing)",
        '      if [ -L "$ACTIVE_PATH" ]; then rm -f -- "$ACTIVE_PATH" || return 1; fi',
        "      ;;",
        "    *) return 1 ;;",
        "  esac",
        '  sync -f "$RELEASE_ROOT" || return 1',
        "}",
        "verify_previous_active_runtime() {",
        '  case "$PREVIOUS_KIND" in',
        "    symlink)",
        '      test -L "$ACTIVE_PATH"',
        '      test "$(realpath -e -- "$ACTIVE_PATH")" = "$PREVIOUS_TARGET"',
        '      validate_runnable_runtime "$PREVIOUS_TARGET"',
        "      ;;",
        "    directory)",
        '      test -d "$ACTIVE_PATH"',
        '      test ! -L "$ACTIVE_PATH"',
        '      validate_runnable_runtime "$ACTIVE_PATH"',
        "      ;;",
        "    missing)",
        '      test ! -e "$ACTIVE_PATH"',
        '      test ! -L "$ACTIVE_PATH"',
        "      ;;",
        "    *) return 1 ;;",
        "  esac",
        "}",
        "finish_runtime_install() {",
        "  local status=$?",
        "  local recovery_failed=0",
        "  trap - ERR",
        "  trap - EXIT",
        "  set +e",
        '  if [ "$status" -ne 0 ] && [ "$SERVICE_MUTATION_STARTED" -eq 1 ]; then',
        "    if fail_closed_service; then",
        '      if [ "$SWITCH_STARTED" -eq 1 ]; then',
        '        if ! rollback_active_runtime >/dev/null 2>&1 || ! verify_previous_active_runtime >/dev/null 2>&1; then recovery_failed=1; fi',
        "      fi",
        '      if ! restore_service_intent >/dev/null 2>&1; then',
        "        recovery_failed=1",
        "        fail_closed_service || recovery_failed=1",
        "      fi",
        "    else",
        "      recovery_failed=1",
        "    fi",
        '    if [ "$recovery_failed" -ne 0 ]; then',
        "      fail_closed_service || true",
        "      printf '%s\\n' 'runtime install recovery could not restore the prior state' >&2",
        "    fi",
        "  fi",
        "  cleanup_runtime_install",
        '  exit "$status"',
        "}",
        "trap finish_runtime_install EXIT",
        'if [ ! -e "$LOCK_PATH" ] && [ ! -L "$LOCK_PATH" ]; then',
        '  (set -o noclobber; : > "$LOCK_PATH") 2>/dev/null || true',
        "fi",
        'test -f "$LOCK_PATH"',
        'test ! -L "$LOCK_PATH"',
        'test "$(stat -c \'%a:%u:%g:%h\' -- "$LOCK_PATH")" = "600:0:0:1"',
        'exec 9<>"$LOCK_PATH"',
        "flock -n 9",
        "validate_release() {",
        '  local release="$1"',
        '  test -d "$release"',
        '  test ! -L "$release"',
        '  test -d "$release/recipes"',
        '  test ! -L "$release/recipes"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$release")" = "755:0:0:directory"',
        '  test "$(stat -c \'%a:%u:%g:%F\' -- "$release/recipes")" = "755:0:0:directory"',
        '  test -z "$(find "$release" -xdev -type l -print -quit)"',
        '  test "$(find "$release" -xdev -mindepth 1 -printf . | wc -c)" -eq 8',
    ]
    for relative_path, (expected_sha, expected_mode) in sorted(expected_files.items()):
        installed_path = f'$release/{relative_path}'
        numeric_mode = expected_mode.lstrip("0")
        commands.extend(
            [
                f'test -f "{installed_path}"',
                f'test ! -L "{installed_path}"',
                (
                    f'test "$(sha256sum -- "{installed_path}" | cut -d \' \' -f 1)" '
                    f"= {shlex.quote(expected_sha)}"
                ),
                (
                    f'test "$(stat -c \'%a:%u:%g:%F\' -- "{installed_path}")" '
                    f'= "{numeric_mode}:0:0:regular file"'
                ),
            ]
        )
    commands.extend(
        [
            "}",
            'install -d -o root -g root -m 0755 "$RELEASE_ROOT"',
            'test ! -L "$RELEASE_ROOT"',
            'test "$(stat -c \'%a:%u:%g:%F\' -- "$RELEASE_ROOT")" = "755:0:0:directory"',
            (
                f"aws s3 cp {shlex.quote(archive_uri)} "
                '"$TMP_DIR/runtime.tar.gz" --only-show-errors'
            ),
            'test "$(sha256sum -- "$TMP_DIR/runtime.tar.gz" | cut -d \' \' -f 1)" = "$RUNTIME_SHA"',
            (
                "expected_archive_members=$(printf '%s\\n' "
                "approval_observer.py checkpoint.py codex_project.py landing.py "
                "recipes/codex-headless.json "
                "reconstruct.py runner.py | sort)"
            ),
            'actual_archive_members=$(tar -tzf "$TMP_DIR/runtime.tar.gz" | sort)',
            'test "$actual_archive_members" = "$expected_archive_members"',
            'if [ -e "$RELEASE_DIR" ] || [ -L "$RELEASE_DIR" ]; then',
            '  validate_release "$RELEASE_DIR"',
            "else",
            '  STAGE_DIR=$(mktemp -d "$RELEASE_ROOT/.stage.$RUNTIME_SHA.XXXXXX")',
            '  install -d -o root -g root -m 0700 "$TMP_DIR/unpack"',
            '  tar -xzf "$TMP_DIR/runtime.tar.gz" -C "$TMP_DIR/unpack" --no-same-owner --no-same-permissions',
            '  chown root:root "$STAGE_DIR"',
            '  chmod 0755 "$STAGE_DIR"',
            '  install -d -o root -g root -m 0755 "$STAGE_DIR/recipes"',
        ]
    )
    for relative_path, (_, expected_mode) in sorted(expected_files.items()):
        source_path = f'$TMP_DIR/unpack/{relative_path}'
        destination_path = f'$STAGE_DIR/{relative_path}'
        commands.extend(
            [
                f'test -f "{source_path}"',
                f'test ! -L "{source_path}"',
                (
                    f"install -o root -g root -m {expected_mode} "
                    f'"{source_path}" "{destination_path}"'
                ),
            ]
        )
    commands.extend(
        [
            '  validate_release "$STAGE_DIR"',
            '  if mv -T -- "$STAGE_DIR" "$RELEASE_DIR" 2>/dev/null; then',
            '    STAGE_DIR=""',
            "  else",
            '    validate_release "$RELEASE_DIR"',
            "  fi",
            "fi",
            'validate_release "$RELEASE_DIR"',
            'sync -f "$RELEASE_DIR"',
            'sync -f "$RELEASE_ROOT"',
            'if [ -L "$ACTIVE_PATH" ]; then',
            '  PREVIOUS_KIND="symlink"',
            '  PREVIOUS_TARGET=$(realpath -e -- "$ACTIVE_PATH")',
            '  case "$PREVIOUS_TARGET" in "$RELEASE_ROOT"/*) ;; *) exit 1 ;; esac',
            '  PREVIOUS_NAME=${PREVIOUS_TARGET##*/}',
            '  printf \'%s\\n\' "$PREVIOUS_NAME" | grep -Eq \'^[0-9a-f]{64}$\'',
            '  validate_runnable_runtime "$PREVIOUS_TARGET"',
            'elif [ -d "$ACTIVE_PATH" ]; then',
            '  PREVIOUS_KIND="directory"',
            '  validate_runnable_runtime "$ACTIVE_PATH"',
            'elif [ -e "$ACTIVE_PATH" ]; then',
            "  exit 1",
            "fi",
            "capture_service_intent",
            'ACTIVATE_LINK=$(mktemp "$RELEASE_ROOT/.activate.XXXXXX")',
            'rm -f -- "$ACTIVATE_LINK"',
            'ln -s -- "$RELEASE_DIR" "$ACTIVATE_LINK"',
            "quiesce_service",
            "SWITCH_STARTED=1",
            'if [ "$PREVIOUS_KIND" = "directory" ]; then',
            '  LEGACY_DIR=$(mktemp -d "$RELEASE_ROOT/.legacy.XXXXXX")',
            '  rmdir -- "$LEGACY_DIR"',
            '  mv -T -- "$ACTIVE_PATH" "$LEGACY_DIR"',
            "fi",
            'mv -Tf -- "$ACTIVATE_LINK" "$ACTIVE_PATH"',
            'ACTIVATE_LINK=""',
            'sync -f "$RELEASE_ROOT"',
            'test -L "$ACTIVE_PATH"',
            'test "$(realpath -e -- "$ACTIVE_PATH")" = "$RELEASE_DIR"',
            'validate_release "$RELEASE_DIR"',
            'python3 "$ACTIVE_PATH/runner.py" --help >/dev/null',
            'python3 "$ACTIVE_PATH/codex_project.py" --help >/dev/null',
            'python3 "$ACTIVE_PATH/approval_observer.py" --help >/dev/null',
            'python3 "$ACTIVE_PATH/checkpoint.py" --help >/dev/null',
            'python3 "$ACTIVE_PATH/landing.py" --help >/dev/null',
            "restore_service_intent",
            'if [ -n "$LEGACY_DIR" ]; then',
            '  OBSOLETE_LEGACY_DIR="$LEGACY_DIR"',
            '  LEGACY_DIR=""',
            '  rm -rf -- "$OBSOLETE_LEGACY_DIR" || true',
            '  sync -f "$RELEASE_ROOT" || true',
            "fi",
            "printf '%s' installed",
        ]
    )
    return commands


def install_runtime_bundle(state: dict[str, Any]) -> dict[str, str]:
    run_id, instance_id, bucket = validated_runtime_install_context(state)
    run_dir = LOCAL_ROOT / "runs" / run_id
    runtime_bundle, runtime_sha = build_runtime_bundle(run_dir)
    if SHA256_PATTERN.fullmatch(runtime_sha) is None:
        raise SpikeError("runtime bundle SHA-256 was invalid")
    runtime_key = f"sessions/{run_id}/runtime/{runtime_sha}.tar.gz"
    upload_file(runtime_bundle, bucket, runtime_key)
    expected_files = {
        "runner.py": (sha256_file(GUEST_DIR / "runner.py"), "0755"),
        "codex_project.py": (sha256_file(CODEX_PROJECT_PATH), "0755"),
        "approval_observer.py": (sha256_file(APPROVAL_OBSERVER_PATH), "0755"),
        "reconstruct.py": (sha256_file(GUEST_DIR / "reconstruct.py"), "0755"),
        "checkpoint.py": (sha256_file(GUEST_DIR / "checkpoint.py"), "0755"),
        "landing.py": (sha256_file(LANDING_PATH), "0755"),
        "recipes/codex-headless.json": (sha256_file(RECIPE_PATH), "0644"),
    }
    install_output = send_command(
        instance_id,
        runtime_install_commands(
            bucket=bucket,
            runtime_key=runtime_key,
            runtime_sha=runtime_sha,
            expected_files=expected_files,
        ),
        "Install provider-blind Lift spike runtime",
    )
    if not install_output.splitlines() or install_output.splitlines()[-1] != "installed":
        raise SpikeError("guest runtime installation did not complete")
    return {
        "runtimeBundleSha256": runtime_sha,
        "runtimeObjectKey": runtime_key,
        "runtimeReleasePath": f"{REMOTE_RUNTIME_RELEASE_ROOT}/{runtime_sha}",
        "runtimeActivePath": REMOTE_RUNTIME_PATH,
        "runnerSha256": expected_files["runner.py"][0],
        "codexProjectSha256": expected_files["codex_project.py"][0],
        "approvalObserverSha256": expected_files["approval_observer.py"][0],
        "checkpointSha256": expected_files["checkpoint.py"][0],
        "landingSha256": expected_files["landing.py"][0],
        "recipeSha256": expected_files["recipes/codex-headless.json"][0],
    }


def validated_lift_off_context(
    state: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    validate_loaded_state(state)
    runtime = state["runtime"]
    if runtime.get("state") != "RUNNING":
        raise SpikeError("runtime must be RUNNING before Lift Off")
    outputs = validated_stack_context(state)
    return state["runId"], outputs


def lift_off_reconstruct_commands(
    *, run_id: str, bucket: str, package_sha: str
) -> list[str]:
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise SpikeError("Lift Off received an invalid run ID")
    if not valid_s3_bucket_name(bucket):
        raise SpikeError("Lift Off received an invalid transfer bucket")
    if (
        not isinstance(package_sha, str)
        or SHA256_PATTERN.fullmatch(package_sha) is None
    ):
        raise SpikeError("Lift Off received an invalid package SHA-256")
    object_key = f"sessions/{run_id}/lift-off/{package_sha}.tar.gz"
    archive_uri = f"s3://{bucket}/{object_key}"
    remote_package = f"/var/lib/lift-spike/packages/{package_sha}.tar.gz"
    return [
        "set -euo pipefail",
        "install -d -o root -g root -m 0700 /var/lib/lift-spike/packages",
        shlex.join(
            [
                "aws",
                "s3",
                "cp",
                archive_uri,
                remote_package,
                "--only-show-errors",
            ]
        ),
        shlex.join(
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
                WORKSPACE_ID,
            ]
        ),
    ]


def head_s3_object(
    bucket: str, key: str, *, version_id: str | None = None
) -> dict[str, Any] | None:
    if version_id is not None and not valid_s3_version_id(version_id):
        raise SpikeError("S3 checkpoint version identity is invalid")
    arguments = [
        "--bucket",
        bucket,
        "--key",
        key,
        "--checksum-mode",
        "ENABLED",
    ]
    if version_id is not None:
        arguments.extend(["--version-id", version_id])
    completed = run(
        [
            *aws_arguments(
                "s3api",
                "head-object",
                *arguments,
            ),
            "--output",
            "json",
        ],
        check=False,
    )
    if completed.returncode == 0:
        try:
            value = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise SpikeError("S3 returned invalid checkpoint metadata") from exc
        if not isinstance(value, dict):
            raise SpikeError("S3 returned non-object checkpoint metadata")
        return value
    error = completed.stderr or ""
    if "(404)" in error or "Not Found" in error or "NoSuchKey" in error:
        return None
    raise SpikeError(f"unable to inspect S3 checkpoint object: {error.strip()}")


def ensure_s3_recovery_object(
    *,
    instance_id: str,
    bucket: str,
    key: str,
    remote_path: str,
    sha256: str,
    size: int,
    description: str,
    expected_version_id: str | None = None,
) -> dict[str, Any]:
    expected_checksum = base64.b64encode(bytes.fromhex(sha256)).decode("ascii")
    head = head_s3_object(bucket, key, version_id=expected_version_id)
    if head is None:
        if expected_version_id is not None:
            raise SpikeError(f"the exact {description} S3 version is missing")
        upload_raw = send_command(
            instance_id,
            [
                "set -euo pipefail",
                (
                    "aws s3api put-object "
                    f"--bucket {shlex.quote(bucket)} "
                    f"--key {shlex.quote(key)} "
                    f"--body {shlex.quote(remote_path)} "
                    "--server-side-encryption AES256 "
                    f"--metadata {shlex.quote('sha256=' + sha256)} "
                    "--checksum-algorithm SHA256 "
                    f"--region {shlex.quote(REGION)} --no-cli-pager --output json"
                ),
            ],
            f"Upload encrypted {description}",
            timeout_seconds=300,
        )
        try:
            upload = json.loads(upload_raw)
        except json.JSONDecodeError as exc:
            raise SpikeError(f"{description} upload did not return valid JSON") from exc
        uploaded_version_id = upload.get("VersionId")
        if (
            upload.get("ChecksumSHA256") != expected_checksum
            or not valid_s3_version_id(uploaded_version_id)
        ):
            raise SpikeError(f"{description} upload checksum did not match EBS")
        head = head_s3_object(bucket, key, version_id=uploaded_version_id)
    if head is None:
        raise SpikeError(f"{description} was not readable after upload")
    metadata = head.get("Metadata", {})
    version_id = head.get("VersionId")
    if (
        head.get("ContentLength") != size
        or head.get("ServerSideEncryption") != "AES256"
        or head.get("ChecksumSHA256") != expected_checksum
        or not isinstance(metadata, dict)
        or metadata.get("sha256") != sha256
        or not valid_s3_version_id(version_id)
        or (expected_version_id is not None and version_id != expected_version_id)
    ):
        raise SpikeError(
            f"{description} failed size, encryption, checksum, or version checks"
        )
    return head


def checkpoint_tree_entries(git_dir: Path, tree: str) -> list[dict[str, Any]]:
    raw = run_bytes(
        ["git", f"--git-dir={git_dir}", "ls-tree", "-r", "-z", "--full-tree", tree]
    ).stdout
    entries: list[dict[str, Any]] = []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        metadata, separator, path_bytes = encoded.partition(b"\t")
        if not separator:
            raise SpikeError("restored checkpoint tree listing was malformed")
        mode_bytes, object_type_bytes, object_id_bytes = metadata.split(b" ", 2)
        path = path_bytes.decode("utf-8")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or path.startswith(".git/"):
            raise SpikeError(f"unsafe path in restored checkpoint: {path}")
        mode = mode_bytes.decode("ascii")
        object_type = object_type_bytes.decode("ascii")
        object_id = object_id_bytes.decode("ascii")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            raise SpikeError(f"unsupported restored checkpoint entry: {path}")
        content = run_bytes(
            ["git", f"--git-dir={git_dir}", "cat-file", "blob", object_id]
        ).stdout
        entry = {
            "path": path,
            "type": "symlink" if mode == "120000" else "file",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "executable": mode == "100755",
            "gitMode": mode,
            "gitObjectId": object_id,
        }
        if mode == "120000":
            try:
                entry["target"] = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SpikeError(
                    f"restored symbolic link target is not UTF-8: {path}"
                ) from exc
        entries.append(entry)
    return entries


def download_versioned_object(
    *,
    bucket: str,
    key: str,
    version_id: str,
    destination: Path,
    sha256: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    if destination.is_file() and sha256_file(destination) == sha256:
        return
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        aws_raw(
            "s3api",
            "get-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--version-id",
            version_id,
            str(temporary),
            timeout=300,
        )
        if sha256_file(temporary) != sha256:
            raise SpikeError("downloaded recovery object failed its SHA-256 check")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def restore_test_checkpoint(
    *,
    run_id: str,
    workspace_id: str,
    bucket: str,
    bundle: dict[str, Any],
    manifest_object: dict[str, Any],
    checkpoint: dict[str, Any],
    expected_evidence: dict[str, bytes],
) -> dict[str, Any]:
    evidence_root = LOCAL_ROOT / "runs" / run_id / "evidence" / "recovery"
    bundle_path = evidence_root / f"{checkpoint['bundleSha256']}.bundle"
    manifest_path = evidence_root / f"{checkpoint['manifestFileSha256']}.manifest.json"
    download_versioned_object(
        bucket=bucket,
        key=checkpoint["s3ObjectKey"],
        version_id=bundle["VersionId"],
        destination=bundle_path,
        sha256=checkpoint["bundleSha256"],
    )
    download_versioned_object(
        bucket=bucket,
        key=checkpoint["s3ManifestObjectKey"],
        version_id=manifest_object["VersionId"],
        destination=manifest_path,
        sha256=checkpoint["manifestFileSha256"],
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SpikeError("downloaded checkpoint manifest was invalid") from exc
    claimed_manifest_sha = manifest.pop("manifestSha256", None)
    canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8")
    actual_manifest_sha = hashlib.sha256(canonical).hexdigest()
    manifest["manifestSha256"] = claimed_manifest_sha
    if claimed_manifest_sha != actual_manifest_sha:
        raise SpikeError("downloaded checkpoint manifest failed its self-hash")
    expected_manifest = {
        "schemaVersion": 1,
        "runId": run_id,
        "workspaceId": workspace_id,
        "checkpointRef": checkpoint["ref"],
        "commit": checkpoint["commit"],
        "tree": checkpoint["tree"],
        "parents": checkpoint["parents"],
        "gitSnapshotSha256": checkpoint["gitSnapshotSha256"],
        "manifestSha256": checkpoint["manifestSha256"],
    }
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise SpikeError("downloaded checkpoint manifest identity did not match")
    manifest_paths = {entry.get("path") for entry in manifest.get("entries", [])}
    if "excluded.env" in manifest_paths:
        raise SpikeError("excluded fixture sentinel path entered the recovery manifest")
    evidence_entries: dict[str, dict[str, Any]] = {}
    for evidence_path, evidence_bytes in expected_evidence.items():
        evidence_entry = next(
            (
                entry
                for entry in manifest.get("entries", [])
                if entry.get("path") == evidence_path
            ),
            None,
        )
        if (
            not isinstance(evidence_entry, dict)
            or evidence_entry.get("type") != "file"
            or evidence_entry.get("sha256")
            != hashlib.sha256(evidence_bytes).hexdigest()
            or evidence_entry.get("size") != len(evidence_bytes)
            or evidence_entry.get("executable") is not False
        ):
            raise SpikeError(
                f"restored checkpoint is not bound to exact evidence {evidence_path}"
            )
        evidence_entries[evidence_path] = evidence_entry

    with tempfile.TemporaryDirectory(prefix="lift-recovery-verify-") as temporary_name:
        restore_repo = Path(temporary_name) / "restore.git"
        run(["git", "init", "--bare", str(restore_repo)])
        listed_heads: dict[str, str] = {}
        for line in run(["git", "bundle", "list-heads", str(bundle_path)]).stdout.splitlines():
            object_id, separator, ref = line.partition(" ")
            if separator:
                listed_heads[ref] = object_id
        recovery_checkpoints = checkpoint.get("recoveryCheckpointRefs")
        recovery_history = checkpoint.get(
            "recoveryHistoryRefs", checkpoint["historyRefs"]
        )
        if recovery_checkpoints is not None:
            expected_heads = {
                item["ref"]: item["objectId"]
                for item in [*recovery_checkpoints, *recovery_history]
            }
            if listed_heads != expected_heads:
                raise SpikeError(
                    "recovery bundle head map differs from its complete declared history"
                )
        else:
            # Backward-compatible verification for already-durable proof
            # checkpoints from the earlier spike runtime. Land checkpoints
            # always carry the complete, exact map above.
            expected_heads = {
                checkpoint["ref"]: checkpoint["commit"],
                **{item["ref"]: item["objectId"] for item in recovery_history},
            }
            if any(
                listed_heads.get(ref) != object_id
                for ref, object_id in expected_heads.items()
            ):
                raise SpikeError(
                    "recovery bundle head map omitted preserved cloud Git history"
                )
        run(
            [
                "git",
                f"--git-dir={restore_repo}",
                "fetch",
                "--no-tags",
                str(bundle_path),
                *[f"{ref}:{ref}" for ref in expected_heads],
            ]
        )
        restored_commit = run(
            ["git", f"--git-dir={restore_repo}", "rev-parse", f"{checkpoint['ref']}^{{commit}}"]
        ).stdout.strip()
        restored_tree = run(
            ["git", f"--git-dir={restore_repo}", "show", "-s", "--format=%T", restored_commit]
        ).stdout.strip()
        restored_parents = run(
            ["git", f"--git-dir={restore_repo}", "show", "-s", "--format=%P", restored_commit]
        ).stdout.strip().split()
        if (
            restored_commit != checkpoint["commit"]
            or restored_tree != checkpoint["tree"]
            or restored_parents != checkpoint["parents"]
        ):
            raise SpikeError("restored Git checkpoint identity did not match")
        entries = checkpoint_tree_entries(restore_repo, restored_tree)
        if entries != manifest.get("entries"):
            raise SpikeError("restored Git contents did not match the SHA-256 manifest")
        for evidence_path, evidence_bytes in expected_evidence.items():
            restored_evidence = run_bytes(
                [
                    "git",
                    f"--git-dir={restore_repo}",
                    "cat-file",
                    "blob",
                    evidence_entries[evidence_path]["gitObjectId"],
                ]
            ).stdout
            if restored_evidence != evidence_bytes:
                raise SpikeError(
                    f"restored evidence bytes did not match {evidence_path}"
                )
        for history in recovery_history:
            restored_object = run(
                ["git", f"--git-dir={restore_repo}", "rev-parse", history["ref"]]
            ).stdout.strip()
            if restored_object != history["objectId"]:
                raise SpikeError("restored bundle omitted cloud Git history")
    return {
        "bundleLocalSha256": sha256_file(bundle_path),
        "manifestLocalSha256": sha256_file(manifest_path),
        "restoredCommit": checkpoint["commit"],
        "restoredTree": checkpoint["tree"],
        "restoredFileCount": len(manifest["entries"]),
        "verifiedAt": now_iso(),
    }


def valid_git_object_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def valid_aware_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def valid_s3_version_id(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or value == "null"
    ):
        return False
    try:
        encoded_size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return encoded_size <= MAX_S3_VERSION_ID_BYTES


def valid_restore_test(value: Any, checkpoint: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != RESTORE_TEST_KEYS
        or not isinstance(checkpoint, dict)
    ):
        return False
    restored_file_count = value.get("restoredFileCount")
    checkpoint_file_count = checkpoint.get("fileCount")
    return (
        isinstance(value.get("bundleLocalSha256"), str)
        and SHA256_PATTERN.fullmatch(value["bundleLocalSha256"]) is not None
        and value.get("bundleLocalSha256") == checkpoint.get("bundleSha256")
        and isinstance(value.get("manifestLocalSha256"), str)
        and SHA256_PATTERN.fullmatch(value["manifestLocalSha256"]) is not None
        and value.get("manifestLocalSha256")
        == checkpoint.get("manifestFileSha256")
        and valid_git_object_id(value.get("restoredCommit"))
        and value.get("restoredCommit") == checkpoint.get("commit")
        and valid_git_object_id(value.get("restoredTree"))
        and value.get("restoredTree") == checkpoint.get("tree")
        and isinstance(restored_file_count, int)
        and not isinstance(restored_file_count, bool)
        and restored_file_count >= 0
        and isinstance(checkpoint_file_count, int)
        and not isinstance(checkpoint_file_count, bool)
        and checkpoint_file_count == restored_file_count
        and valid_aware_iso8601(value.get("verifiedAt"))
    )


def safe_to_close(state: dict[str, Any]) -> bool:
    readiness = state.get("readiness", {})
    workspace = state.get("workspace", {})
    runtime = state.get("runtime", {})
    evidence = readiness.get("safeToCloseEvidence", {})
    approval = readiness.get("approvalEvidence", {})
    phone_thread = readiness.get("phoneThreadEvidence", {})
    try:
        challenge, challenge_sha = active_phone_challenge(readiness)
        proof_source = challenge["proofSource"]
        expected_proof_sha = hashlib.sha256(
            proof_bytes(challenge, proof_source)
        ).hexdigest()
        expected_approval_command_sha256 = hashlib.sha256(
            approval_canary_command(challenge["approvalNonce"]).encode("utf-8")
        ).hexdigest()
        expected_proof_command_sha256 = hashlib.sha256(
            phone_proof_command(challenge).encode("utf-8")
        ).hexdigest()
    except (KeyError, SpikeError):
        return False
    thread_baseline = challenge.get("threadBaseline", {})
    thread_hashes = (
        phone_thread.get("commandSha256") if isinstance(phone_thread, dict) else {}
    )
    approval_observation = (
        phone_thread.get("approvalObservation")
        if isinstance(phone_thread, dict)
        else None
    )
    checkpoints = workspace.get("checkpoints", [])
    latest = (
        checkpoints[-1]
        if isinstance(checkpoints, list)
        and checkpoints
        and isinstance(checkpoints[-1], dict)
        else {}
    )
    approval_keys = {
        "approvalObservation",
        "approvalGuardSha256",
        "approvalPolicy",
        "approvalVerificationMethod",
        "approvalsReviewer",
        "challengeSha256",
        "commandSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "environmentId",
        "historicalVerificationMethod",
        "itemId",
        "nativeProjectId",
        "networkAccess",
        "proofCommandSha256",
        "proofItemId",
        "projectRoot",
        "runtimeWorkspaceRoots",
        "sandboxType",
        "threadId",
        "turnId",
        "verifiedAt",
    }
    phone_thread_keys = {
        "approvalObservation",
        "approvalGuardSha256",
        "approvalItemId",
        "approvalPolicy",
        "approvalVerificationMethod",
        "approvalsReviewer",
        "challengeSha256",
        "commandSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "cwd",
        "environmentId",
        "historicalVerificationMethod",
        "nativeProjectId",
        "networkAccess",
        "projectRoot",
        "proofItemId",
        "proofSha256",
        "runtimeWorkspaceRoots",
        "sandboxType",
        "threadId",
        "turnId",
        "verifiedAt",
    }
    safe_evidence_keys = {
        "autoStopRemainingSeconds",
        "baselineCommit",
        "challengeSha256",
        "checkpointCommit",
        "checkpointTree",
        "environmentId",
        "instanceId",
        "nativeProjectId",
        "projectRoot",
        "proofSha256",
        "proofSource",
        "restoreTest",
        "runId",
        "s3ManifestVersionId",
        "s3VersionId",
        "verifiedAt",
        "workspaceVolumeId",
    }
    return (
        workspace.get("lease") == "CLOUD_PRIMARY"
        and all(readiness.get(key) is True for key in SAFE_TO_CLOSE_REQUIRED_GATES)
        and isinstance(approval, dict)
        and set(approval) == approval_keys
        and isinstance(approval.get("threadId"), str)
        and bool(approval.get("threadId"))
        and isinstance(approval.get("turnId"), str)
        and bool(approval.get("turnId"))
        and isinstance(approval.get("itemId"), str)
        and bool(approval.get("itemId"))
        and isinstance(approval.get("commandSha256"), str)
        and SHA256_PATTERN.fullmatch(approval.get("commandSha256")) is not None
        and isinstance(approval.get("proofCommandSha256"), str)
        and SHA256_PATTERN.fullmatch(approval.get("proofCommandSha256")) is not None
        and approval.get("challengeSha256") == challenge_sha
        and approval.get("controllerThreadBinding") == CONTROLLER_THREAD_BINDING
        and approval.get("controllerThreadProjectId") is None
        and approval.get("environmentId") == readiness.get("providerEnvironmentId")
        and approval.get("nativeProjectId") == readiness.get("nativeProjectId")
        and approval.get("projectRoot") == REMOTE_WORKSPACE
        and approval.get("networkAccess") is False
        and approval.get("approvalsReviewer") == "user"
        and approval.get("sandboxType") in {"readOnly", "workspaceWrite"}
        and approval.get("runtimeWorkspaceRoots") == [REMOTE_WORKSPACE]
        and approval.get("approvalPolicy") == "on-request"
        and approval.get("approvalVerificationMethod")
        == APPROVAL_VERIFICATION_METHOD
        and approval.get("historicalVerificationMethod")
        == THREAD_VERIFICATION_METHOD
        and isinstance(approval.get("approvalGuardSha256"), str)
        and SHA256_PATTERN.fullmatch(approval["approvalGuardSha256"]) is not None
        and approval.get("approvalGuardSha256")
        == thread_baseline.get("approvalGuardSha256")
        and isinstance(phone_thread, dict)
        and set(phone_thread) == phone_thread_keys
        and phone_thread.get("challengeSha256") == challenge_sha
        and phone_thread.get("proofSha256") == expected_proof_sha
        and phone_thread.get("controllerThreadBinding")
        == CONTROLLER_THREAD_BINDING
        and phone_thread.get("controllerThreadProjectId") is None
        and phone_thread.get("threadId") == approval.get("threadId")
        and phone_thread.get("turnId") == approval.get("turnId")
        and phone_thread.get("approvalItemId") == approval.get("itemId")
        and phone_thread.get("proofItemId") == approval.get("proofItemId")
        and phone_thread.get("environmentId") == approval.get("environmentId")
        and phone_thread.get("nativeProjectId") == approval.get("nativeProjectId")
        and phone_thread.get("projectRoot") == REMOTE_WORKSPACE
        and isinstance(thread_hashes, dict)
        and thread_hashes.get("approval") == approval.get("commandSha256")
        and thread_hashes.get("proof") == approval.get("proofCommandSha256")
        and thread_hashes.get("approval") == expected_approval_command_sha256
        and thread_hashes.get("proof") == expected_proof_command_sha256
        and SHA256_PATTERN.fullmatch(thread_hashes.get("approval", "")) is not None
        and SHA256_PATTERN.fullmatch(thread_hashes.get("proof", "")) is not None
        and phone_thread.get("approvalPolicy") == approval.get("approvalPolicy")
        and phone_thread.get("approvalVerificationMethod")
        == approval.get("approvalVerificationMethod")
        and phone_thread.get("historicalVerificationMethod")
        == approval.get("historicalVerificationMethod")
        and approval.get("approvalObservation") == approval_observation
        and approval_observation_is_bound(
            approval_observation,
            workspace=REMOTE_WORKSPACE,
            challenge=challenge,
            challenge_sha256=challenge_sha,
            approval_command_sha256=expected_approval_command_sha256,
            proof_command_sha256=expected_proof_command_sha256,
            thread_evidence=phone_thread,
        )
        and phone_thread.get("approvalGuardSha256")
        == approval.get("approvalGuardSha256")
        and phone_thread.get("approvalsReviewer") == approval.get("approvalsReviewer")
        and phone_thread.get("networkAccess") is False
        and phone_thread.get("sandboxType") == approval.get("sandboxType")
        and phone_thread.get("runtimeWorkspaceRoots") == [REMOTE_WORKSPACE]
        and phone_thread.get("cwd") == REMOTE_WORKSPACE
        and isinstance(thread_baseline, dict)
        and isinstance(thread_baseline.get("threadIds"), list)
        and phone_thread.get("threadId") not in thread_baseline.get("threadIds")
        and isinstance(thread_baseline.get("createdAtEpochSeconds"), int)
        and not isinstance(thread_baseline.get("createdAtEpochSeconds"), bool)
        and isinstance(phone_thread.get("verifiedAt"), int)
        and not isinstance(phone_thread.get("verifiedAt"), bool)
        and phone_thread.get("verifiedAt")
        >= thread_baseline.get("createdAtEpochSeconds")
        and isinstance(evidence, dict)
        and set(evidence) == safe_evidence_keys
        and evidence.get("challengeSha256") == challenge_sha
        and evidence.get("proofSha256") == expected_proof_sha
        and evidence.get("proofSource") == proof_source
        and evidence.get("runId") == state.get("runId")
        and evidence.get("baselineCommit") == workspace.get("baselineCommit")
        and evidence.get("instanceId") == runtime.get("outputs", {}).get("InstanceId")
        and evidence.get("workspaceVolumeId")
        == runtime.get("outputs", {}).get("WorkspaceVolumeId")
        and evidence.get("environmentId") == challenge.get("environmentId")
        and evidence.get("environmentId") == readiness.get("providerEnvironmentId")
        and evidence.get("nativeProjectId") == readiness.get("nativeProjectId")
        and evidence.get("projectRoot") == REMOTE_WORKSPACE
        and isinstance(evidence.get("autoStopRemainingSeconds"), int)
        and not isinstance(evidence.get("autoStopRemainingSeconds"), bool)
        and evidence.get("autoStopRemainingSeconds")
        >= MIN_AUTO_STOP_REMAINING_SECONDS
        and valid_aware_iso8601(evidence.get("verifiedAt"))
        and valid_git_object_id(latest.get("commit"))
        and valid_git_object_id(latest.get("tree"))
        and evidence.get("checkpointCommit") == latest.get("commit")
        and evidence.get("checkpointTree") == latest.get("tree")
        and valid_s3_version_id(evidence.get("s3VersionId"))
        and valid_s3_version_id(evidence.get("s3ManifestVersionId"))
        and valid_s3_version_id(latest.get("s3VersionId"))
        and valid_s3_version_id(latest.get("s3ManifestVersionId"))
        and evidence.get("s3VersionId") == latest.get("s3VersionId")
        and evidence.get("s3ManifestVersionId") == latest.get("s3ManifestVersionId")
        and valid_restore_test(latest.get("restoreTest"), latest)
        and evidence.get("restoreTest") == latest.get("restoreTest")
        and valid_restore_test(evidence.get("restoreTest"), latest)
        and latest.get("phoneChallengeSha256") == challenge_sha
        and latest.get("phoneProofSha256") == expected_proof_sha
        and latest.get("phoneProofSource") == proof_source
    )


def invalidate_safe_to_close(
    state: dict[str, Any], *, reset_phone_probe: bool, reset_workload: bool
) -> None:
    readiness = state.setdefault("readiness", {})
    readiness["safeToClose"] = False
    readiness["recoveryCheckpointDurable"] = False
    readiness["localStepsComplete"] = False
    readiness.pop("safeToCloseEvidence", None)
    if reset_phone_probe:
        readiness["providerPhoneProbeVerified"] = False
        readiness["controllerProjectVisibility"] = {
            "status": "unknown",
            "verified": False,
        }
        readiness.pop("nativeProjectRegistered", None)
        readiness.pop("providerEnvironmentId", None)
        readiness.pop("phoneThreadEvidence", None)
    if reset_workload:
        readiness["workloadHealthy"] = False
    if reset_phone_probe or reset_workload:
        readiness["approvalRoundTripVerified"] = False
        readiness.pop("approvalEvidence", None)
        readiness.pop("approvalObserverArm", None)
        readiness.pop("phoneThreadEvidence", None)
        readiness.pop("activeChallengeSha256", None)
        readiness.pop("postRestartChallenge", None)


def cmd_init(args: argparse.Namespace) -> None:
    if args.expected_account.strip() == "":
        raise SpikeError("expected AWS account ID is required")
    actual = caller_identity()
    if actual["accountId"] != args.expected_account:
        raise SpikeError("the active lift-spike profile is not the explicitly expected account")
    if actual["principalArn"].endswith(":root"):
        raise SpikeError("bind the profile to lift-admin instead of root")
    if not actual["principalArn"].endswith(":user/lift-admin"):
        raise SpikeError("the Phase 0 spike requires the lift-admin IAM user")

    if private_file_exists(STATE_PATH, maximum_size=MAX_LOCAL_STATE_BYTES):
        state = load_state()
        assert_identity(state)
        print(json.dumps(state, indent=2, sort_keys=True))
        return

    run_id = f"p0-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"
    state: dict[str, Any] = {
        "schemaVersion": 1,
        "revision": 1,
        "runId": run_id,
        "workspaceId": WORKSPACE_ID,
        "createdAt": now_iso(),
        "identity": {
            "profile": PROFILE,
            "region": REGION,
            **actual,
        },
        "runtime": {"state": "NOT_CREATED", "stackName": f"lift-{run_id}"},
        "workspace": {"lease": "LOCAL_PRIMARY"},
        "connection": {"state": "DISCONNECTED"},
        "readiness": {
            "storageDurable": False,
            "manifestVerified": False,
            "workloadHealthy": False,
            "serverProjectRegistered": False,
            "controllerProjectVisibility": {
                "status": "unknown",
                "verified": False,
            },
            "providerPhoneProbeVerified": False,
            "approvalRoundTripVerified": False,
            "recoveryCheckpointDurable": False,
            "localStepsComplete": False,
        },
    }
    atomic_state(state)
    record_event("run.initialized", runId=run_id, principalArn=actual["principalArn"], region=REGION)
    print(json.dumps(state, indent=2, sort_keys=True))


def cmd_doctor(_: argparse.Namespace) -> None:
    state = load_state()
    actual = assert_identity(state)
    ami_id = resolve_ami()
    aws_json(
        "cloudformation",
        "validate-template",
        "--template-body",
        f"file://{TEMPLATE_PATH}",
    )
    tools = {
        "aws": shutil.which("aws"),
        "git": shutil.which("git"),
        "python3": shutil.which("python3"),
        "sessionManagerPlugin": shutil.which("session-manager-plugin"),
    }
    result = {
        "identity": actual,
        "region": REGION,
        "amiId": ami_id,
        "canonicalOwnerVerified": True,
        "templateValid": True,
        "tools": tools,
        "interactiveReady": tools["sessionManagerPlugin"] is not None,
        "interactiveWarning": INTERACTIVE_WARNING,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


def cmd_up(_: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    run_id = state["runId"]
    runtime = state["runtime"]
    stack_name = runtime["stackName"]
    existing_deployment = runtime.get("outputs") is not None
    if existing_deployment:
        validated_stack_context(state)
    cached_ami_id = runtime.get("amiId")
    ami_id = validate_ami(cached_ami_id) if cached_ami_id is not None else resolve_ami()
    if not existing_deployment:
        assert_stack_absent_for_create(stack_name)
    run_dir = LOCAL_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runtime["amiId"] = ami_id
    runtime["state"] = "CREATING"
    state["revision"] += 1
    atomic_state(state)
    record_event("runtime.provisioning_started", stackName=stack_name, amiId=ami_id)

    run(
        [
            *aws_arguments("cloudformation", "deploy"),
            "--template-file",
            str(TEMPLATE_PATH),
            "--stack-name",
            stack_name,
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
            "--parameter-overrides",
            f"AmiId={ami_id}",
            "InstanceType=c7i-flex.large",
            "WorkspaceVolumeSize=30",
            "AutoStopMinutes=240",
            f"SpikeId={run_id}",
            "--no-fail-on-empty-changeset",
        ],
        timeout=1200,
    )

    if not existing_deployment:
        stack = describe_stack(stack_name)
        outputs = stack_output_map(stack)
        missing = sorted(REQUIRED_STACK_OUTPUTS.difference(outputs))
        if missing:
            raise SpikeError(f"stack is missing required outputs: {', '.join(missing)}")
        runtime["outputs"] = outputs
        runtime["stackId"] = stack.get("StackId")
    outputs = validated_stack_context(state)
    runtime["state"] = "BOOTSTRAPPING"
    state["revision"] += 1
    atomic_state(state)

    instance_id = outputs["InstanceId"]
    aws_raw("ec2", "wait", "instance-status-ok", "--instance-ids", instance_id, timeout=900)
    wait_for_ssm(instance_id)
    outputs = validated_stack_context(state)
    instance_id = outputs["InstanceId"]
    bootstrap_raw = send_command(
        instance_id,
        [
            "set -e",
            "for i in $(seq 1 90); do if [ -s /var/lib/lift-spike/bootstrap.json ]; then cat /var/lib/lift-spike/bootstrap.json; exit 0; fi; sleep 10; done",
            "echo 'bootstrap marker did not appear' >&2",
            "exit 1",
        ],
        "Wait for Lift spike bootstrap",
        timeout_seconds=960,
    )
    try:
        bootstrap = json.loads(bootstrap_raw)
    except json.JSONDecodeError as exc:
        raise SpikeError("bootstrap marker was not valid JSON") from exc
    if bootstrap.get("status") != "ready":
        raise SpikeError("guest bootstrap did not report ready")
    if bootstrap.get("codex_version") != "codex-cli 0.152.1":
        raise SpikeError("guest Codex version does not match the reviewed recipe")
    if bootstrap.get("sandbox_ready") is not True:
        raise SpikeError("guest Codex sandbox preflight did not pass")

    runtime_install = install_runtime_bundle(state)

    runtime.update(
        {
            "state": "RUNNING",
            "bootstrap": bootstrap,
            **runtime_install,
            "expiresAfterBootMinutes": 240,
        }
    )
    state["readiness"]["storageDurable"] = True
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "runtime.ready",
        instanceId=instance_id,
        workspaceVolumeId=outputs["WorkspaceVolumeId"],
        codexVersion=bootstrap.get("codex_version"),
        sandboxReady=bootstrap.get("sandbox_ready"),
    )
    print(json.dumps({"runtime": runtime, "bootstrap": bootstrap}, indent=2, sort_keys=True))


def cmd_lift_off(_: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    run_id, outputs = validated_lift_off_context(state)
    run_dir = LOCAL_ROOT / "runs" / run_id
    fixture = run_dir / "fixture-local"
    marker = create_fixture(fixture)
    ledger = run_dir / "ledger.git"
    capture = capture_baseline(
        workspace=fixture,
        ledger=ledger,
        run_id=run_id,
        workspace_id=WORKSPACE_ID,
        approved_ignored=[marker["approvedIgnoredPath"]],
    )
    artifact = run_dir / "artifacts" / "lift-off.tar.gz"
    package_sha = build_lift_off_archive(
        destination=artifact,
        ledger=ledger,
        capture=capture,
        run_id=run_id,
        workspace_id=WORKSPACE_ID,
    )
    reconstruct_commands = lift_off_reconstruct_commands(
        run_id=run_id,
        bucket=outputs["TransferBucketName"],
        package_sha=package_sha,
    )
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "baseline-manifest.json").write_text(
        json.dumps(capture.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (evidence_dir / "local-original.json").write_text(
        json.dumps(capture.original, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    refreshed_outputs = validated_stack_context(state)
    if refreshed_outputs != outputs:
        raise SpikeError("the Lift Off stack context changed during local capture")
    outputs = refreshed_outputs
    object_key = f"sessions/{run_id}/lift-off/{package_sha}.tar.gz"
    upload_file(artifact, outputs["TransferBucketName"], object_key)
    reconstruct_raw = send_command(
        outputs["InstanceId"],
        reconstruct_commands,
        "Reconstruct verified disposable Lift workspace",
    )
    try:
        reconstruction = json.loads(reconstruct_raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SpikeError("workspace reconstruction did not return valid JSON") from exc
    if reconstruction.get("manifestSha256") != capture.manifest["manifestSha256"]:
        raise SpikeError("cloud reconstruction manifest does not match local baseline")

    state["workspace"] = {
        "lease": "LIFTING",
        "localPath": str(fixture),
        "cloudPath": REMOTE_WORKSPACE,
        "ledgerPath": str(ledger),
        "baselineCommit": capture.commit,
        "baselineRef": capture.ref,
        "baselineManifestSha256": capture.manifest["manifestSha256"],
        "packageSha256": package_sha,
        "objectKey": object_key,
        "originalHead": capture.original["head"],
        "originalIndexSha256": capture.original["indexSha256"],
        "cloudReconstruction": reconstruction,
    }
    invalidate_safe_to_close(state, reset_phone_probe=True, reset_workload=True)
    state["readiness"]["manifestVerified"] = True
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "workspace.reconstructed",
        baselineCommit=capture.commit,
        manifestSha256=capture.manifest["manifestSha256"],
        cloudPath=REMOTE_WORKSPACE,
    )
    print(json.dumps(state["workspace"], indent=2, sort_keys=True))


def cmd_status(_: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    local_snapshot = json.loads(json.dumps(state))
    persisted_safe = local_snapshot.get("readiness", {}).pop("safeToClose", False)
    result: dict[str, Any] = {
        "local": local_snapshot,
        "persistedSafeToCloseCache": persisted_safe,
        "liveReadiness": {
            "evaluatedAt": now_iso(),
            "safeToClose": False,
            "validForSeconds": 30,
        },
    }
    runtime = state.get("runtime", {})
    outputs = runtime.get("outputs")
    if outputs:
        outputs = validated_stack_context(state)
        instance_id = outputs["InstanceId"]
        ec2 = aws_json("ec2", "describe-instances", "--instance-ids", instance_id)
        result["ec2"] = ec2["Reservations"][0]["Instances"][0]["State"]["Name"]
        ssm = aws_json(
            "ssm",
            "describe-instance-information",
            "--filters",
            f"Key=InstanceIds,Values={instance_id}",
        )
        items = ssm.get("InstanceInformationList", [])
        result["ssm"] = items[0].get("PingStatus") if items else "NotRegistered"
        if result["ssm"] == "Online":
            try:
                bootstrap_raw = send_command(
                    instance_id,
                    ["set -euo pipefail", "cat /var/lib/lift-spike/bootstrap.json"],
                    "Read Lift guest bootstrap status",
                    timeout_seconds=60,
                )
                result["guestBootstrap"] = json.loads(bootstrap_raw)
                runner = managed_runner_status(instance_id)
                result["runner"] = runner
                workspace = state.get("workspace", {})
                if workspace.get("cloudPath") != REMOTE_WORKSPACE:
                    raise SpikeError("the persisted cloud workspace is not canonical")
                remote = managed_remote_status(instance_id, REMOTE_WORKSPACE)
                result["remote"] = remote
                auto_stop_remaining_seconds = managed_auto_stop_remaining_seconds(
                    instance_id
                )
                result["autoStopRemainingSeconds"] = auto_stop_remaining_seconds
                current = live_safe_to_close(
                    state, runner, remote, auto_stop_remaining_seconds
                )
                result["liveReadiness"] = {
                    "evaluatedAt": now_iso(),
                    "safeToClose": current,
                    "validForSeconds": 30,
                    "reason": None
                    if current
                    else "one or more durable, approval, runner, or provider gates failed",
                }
            except (SpikeError, json.JSONDecodeError) as exc:
                result["liveReadiness"]["reason"] = str(exc)
        else:
            result["liveReadiness"]["reason"] = "the guest is not online through Systems Manager"
    print(json.dumps(result, indent=2, sort_keys=True))


def cmd_install_runtime(_: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    outputs = validated_stack_context(state)
    wait_for_ssm(outputs["InstanceId"], timeout_seconds=120)
    invalidate_safe_to_close(state, reset_phone_probe=False, reset_workload=True)
    state["runtime"]["runtimeDeploymentState"] = "INSTALLING"
    state["revision"] += 1
    atomic_state(state)
    record_event("runtime.tools_install_started")
    try:
        installed = install_runtime_bundle(state)
    except Exception:
        state["runtime"]["runtimeDeploymentState"] = "FAILED"
        state["revision"] += 1
        atomic_state(state)
        record_event("runtime.tools_install_failed")
        raise
    state["runtime"].update(installed)
    state["runtime"]["runtimeDeploymentState"] = "ACTIVE"
    state["revision"] += 1
    atomic_state(state)
    record_event("runtime.tools_installed", **installed)
    print(json.dumps(installed, indent=2, sort_keys=True))


def cmd_runner(args: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    outputs = validated_stack_context(state)
    workspace = state.get("workspace", {})
    instance_id = outputs.get("InstanceId")
    if (
        not isinstance(instance_id, str)
        or re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id) is None
        or workspace.get("cloudPath") != REMOTE_WORKSPACE
    ):
        raise SpikeError("runtime and workspace must exist first")
    if args.action == "start":
        command = (
            "python3 /opt/lift-spike/runner.py start "
            f"--recipe {shlex.quote('/opt/lift-spike/recipes/codex-headless.json')} "
            f"--workspace {shlex.quote(REMOTE_WORKSPACE)}"
        )
    else:
        command = f"python3 /opt/lift-spike/runner.py {args.action}"
    output = send_command(
        instance_id, ["set -euo pipefail", command], f"Lift runner {args.action}", 300
    )
    if args.action == "status":
        print(output)
        return
    invalidate_safe_to_close(state, reset_phone_probe=False, reset_workload=True)
    if args.action == "start":
        state["connection"]["state"] = "STARTING_REMOTE"
    elif args.action == "stop":
        state["connection"]["state"] = "CONNECTED"
    state["revision"] += 1
    atomic_state(state)
    record_event(f"runner.{args.action}")
    print(output)


def parse_last_json(raw: str, description: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SpikeError(f"{description} did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise SpikeError(f"{description} returned a non-object")
    return value


def managed_runner_status(instance_id: str) -> dict[str, Any]:
    raw = send_command(
        instance_id,
        ["set -euo pipefail", "python3 /opt/lift-spike/runner.py status"],
        "Verify Lift workload runner",
        timeout_seconds=60,
    )
    status = parse_last_json(raw, "runner status")
    if (
        status.get("recipeId") != "codex-headless-experimental"
        or status.get("workspace") != REMOTE_WORKSPACE
        or not isinstance(status.get("health"), dict)
    ):
        raise SpikeError("runner status did not match the Lift workload")
    return status


def managed_auto_stop_remaining_seconds(instance_id: str) -> int:
    raw = send_command(
        instance_id,
        [
            "set -euo pipefail",
            "systemctl is-active --quiet lift-spike-autostop.timer",
            (
                "DEADLINE_USEC=$(busctl get-property org.freedesktop.systemd1 "
                "/org/freedesktop/systemd1/unit/lift_2dspike_2dautostop_2etimer "
                "org.freedesktop.systemd1.Timer NextElapseUSecMonotonic | awk '{print $2}')"
            ),
            "UPTIME_USEC=$(awk '{printf \"%.0f\", $1 * 1000000}' /proc/uptime)",
            "REMAINING=$(( (DEADLINE_USEC - UPTIME_USEC) / 1000000 ))",
            "printf '%s' \"$REMAINING\"",
        ],
        "Read Lift spike auto-stop protection",
        timeout_seconds=60,
    )
    try:
        encoded_remaining = raw.splitlines()[-1]
    except IndexError as exc:
        raise SpikeError("auto-stop timer verification did not return a duration") from exc
    if re.fullmatch(r"-?[0-9]+", encoded_remaining) is None:
        raise SpikeError("auto-stop timer verification did not return a duration")
    remaining = int(encoded_remaining)
    return remaining


def live_safe_to_close(
    state: dict[str, Any],
    runner: dict[str, Any],
    remote: dict[str, Any],
    auto_stop_remaining_seconds: int,
) -> bool:
    readiness = state.get("readiness", {})
    health = runner.get("health", {})
    return (
        safe_to_close(state)
        and isinstance(auto_stop_remaining_seconds, int)
        and not isinstance(auto_stop_remaining_seconds, bool)
        and auto_stop_remaining_seconds >= MIN_AUTO_STOP_REMAINING_SECONDS
        and runner.get("active") is True
        and runner.get("healthy") is True
        and runner.get("ready") is True
        and isinstance(health, dict)
        and health.get("fresh") is True
        and health.get("healthy") is True
        and health.get("ready") is True
        and remote.get("status") == "connected"
        and remote.get("controllerPresent") is True
        and remote.get("environmentId") == readiness.get("providerEnvironmentId")
        and remote.get("nativeProjectId") == readiness.get("nativeProjectId")
        and remote.get("projectRoot") == REMOTE_WORKSPACE
        and remote.get("workspace") == REMOTE_WORKSPACE
    )


def cmd_restart_test(_: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    runtime = state.get("runtime", {})
    outputs = validated_stack_context(state)
    workspace = state.get("workspace", {})
    readiness = state.get("readiness", {})
    checkpoints = workspace.get("checkpoints", [])
    if workspace.get("cloudPath") != REMOTE_WORKSPACE:
        raise SpikeError("the verified runtime and cloud workspace must exist first")
    if (
        readiness.get("laptopOffProven") is not True
        or not isinstance(checkpoints, list)
        or len(checkpoints) < 2
        or checkpoints[-1].get("label") != "laptop-off-proof"
        or not isinstance(checkpoints[-1].get("restoreTest"), dict)
    ):
        raise SpikeError("durable laptop-off checkpoint 0002 must pass before restart testing")
    checkpoint = checkpoints[-1]
    instance_id = outputs["InstanceId"]
    expected_volume_id = outputs["WorkspaceVolumeId"]
    expected_environment_id = readiness.get("providerEnvironmentId")
    if not isinstance(expected_environment_id, str) or not expected_environment_id:
        raise SpikeError("the pre-restart provider environment identity is missing")
    (
        phone_challenge,
        phone_challenge_sha,
        phone_proof_source,
        phone_sha,
    ) = verified_phone_challenge(readiness)
    if phone_proof_source != "codex-phone":
        raise SpikeError("the recovery restart requires the original phone challenge")
    if (
        checkpoint.get("phoneChallengeSha256") != phone_challenge_sha
        or checkpoint.get("phoneProofSha256") != phone_sha
        or checkpoint.get("phoneProofSource") != phone_proof_source
    ):
        raise SpikeError("the restart checkpoint is not bound to the phone challenge")

    runner_before = parse_last_json(
        send_command(
            instance_id,
            ["set -euo pipefail", "python3 /opt/lift-spike/runner.py status"],
            "Verify reboot runner before EC2 stop",
            timeout_seconds=60,
        ),
        "runner status",
    )
    if runner_before.get("active") is not True or runner_before.get("healthy") is not True:
        raise SpikeError("the provider-neutral runner must be active and healthy before restart")
    remote_before = managed_remote_status(instance_id, REMOTE_WORKSPACE)
    if remote_before.get("environmentId") != expected_environment_id:
        raise SpikeError("the provider environment changed before the restart test")
    boot_before = send_command(
        instance_id,
        ["set -euo pipefail", "cat /proc/sys/kernel/random/boot_id"],
        "Capture pre-restart guest boot identity",
        timeout_seconds=60,
    ).splitlines()[-1]

    invalidate_safe_to_close(state, reset_phone_probe=True, reset_workload=True)
    state["connection"]["state"] = "STOPPING_FOR_RECOVERY_TEST"
    runtime["state"] = "STOPPING_FOR_RECOVERY_TEST"
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "runtime.restart_test_started",
        instanceId=instance_id,
        checkpointCommit=checkpoint["commit"],
        bootIdBefore=boot_before,
    )

    stop_completed = False
    start_requested = False
    try:
        aws_raw("ec2", "stop-instances", "--instance-ids", instance_id, timeout=120)
        aws_raw("ec2", "wait", "instance-stopped", "--instance-ids", instance_id, timeout=900)
        stop_completed = True
        state = load_state()
        state["runtime"]["state"] = "STOPPED_FOR_RECOVERY_TEST"
        state["revision"] += 1
        atomic_state(state)
        record_event("runtime.restart_test_instance_stopped", instanceId=instance_id)

        aws_raw("ec2", "start-instances", "--instance-ids", instance_id, timeout=120)
        start_requested = True
        aws_raw("ec2", "wait", "instance-status-ok", "--instance-ids", instance_id, timeout=900)
        wait_for_ssm(instance_id, timeout_seconds=600)
    except Exception as exc:
        if stop_completed and not start_requested:
            run(
                aws_arguments("ec2", "start-instances", "--instance-ids", instance_id),
                check=False,
                timeout=120,
            )
        failed_state = load_state()
        failed_state["runtime"]["state"] = "RESTART_RECOVERY_ATTENTION"
        failed_state["connection"]["state"] = "RESTART_RECOVERY_ATTENTION"
        failed_state["revision"] += 1
        atomic_state(failed_state)
        record_event("runtime.restart_test_failed", error=str(exc))
        raise

    volume = aws_json(
        "ec2", "describe-volumes", "--volume-ids", expected_volume_id
    ).get("Volumes", [])
    if (
        len(volume) != 1
        or volume[0].get("Encrypted") is not True
        or volume[0].get("State") != "in-use"
        or not any(
            attachment.get("InstanceId") == instance_id
            and attachment.get("State") == "attached"
            for attachment in volume[0].get("Attachments", [])
        )
    ):
        raise SpikeError("the exact encrypted workspace volume did not reattach")

    ledger_path = f"/var/lib/lift/ledger/{state['runId']}.git"
    laptop_challenge = readiness.get("laptopOffChallenge")
    if not isinstance(phone_challenge, dict) or not isinstance(laptop_challenge, dict):
        raise SpikeError("the restart evidence challenges are missing")
    laptop_challenge_sha = laptop_off_challenge_sha256(laptop_challenge)
    if (
        laptop_challenge_sha != readiness.get("laptopOffChallengeSha256")
        or checkpoint.get("evidenceChallengeSha256") != laptop_challenge_sha
        or checkpoint.get("evidenceProofSource") != "codex-phone-laptop-off"
    ):
        raise SpikeError("the restart checkpoint is not bound to the laptop-off challenge")
    phone_path = f"{REMOTE_WORKSPACE}/{phone_challenge['proofRelativePath']}"
    laptop_path = f"{REMOTE_WORKSPACE}/{laptop_challenge['proofRelativePath']}"
    manifest_ebs_path = (
        f"/var/lib/lift/ledger/checkpoints/{state['runId']}/"
        f"{checkpoint['ordinal']:04d}-{checkpoint['label']}-manifest.json"
    )
    phone_sha = hashlib.sha256(
        proof_bytes(phone_challenge, phone_proof_source)
    ).hexdigest()
    laptop_sha = hashlib.sha256(
        proof_bytes(laptop_challenge, "codex-phone-laptop-off")
    ).hexdigest()
    verified = send_command(
        instance_id,
        [
            "set -euo pipefail",
            f"test \"$(readlink -f {shlex.quote(REMOTE_WORKSPACE)})\" = {shlex.quote(REMOTE_WORKSPACE)}",
            (
                f"DEVICE=$(findmnt -n -o MAJ:MIN -T {shlex.quote(REMOTE_WORKSPACE)}); "
                "SERIAL=$(lsblk -ndo SERIAL /dev/block/$DEVICE); "
                "case \"$SERIAL\" in vol-*) ;; vol*) SERIAL=\"vol-${SERIAL#vol}\" ;; esac; "
                f"test \"$SERIAL\" = {shlex.quote(expected_volume_id)}"
            ),
            (
                f"test \"$(git --git-dir={shlex.quote(ledger_path)} rev-parse "
                f"{shlex.quote(checkpoint['ref'] + '^{commit}')})\" = "
                f"{shlex.quote(checkpoint['commit'])}"
            ),
            (
                f"test \"$(sha256sum {shlex.quote(checkpoint['ebsBundlePath'])} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(checkpoint['bundleSha256'])}"
            ),
            (
                f"test -f {shlex.quote(manifest_ebs_path)}; "
                f"test \"$(sha256sum {shlex.quote(manifest_ebs_path)} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(checkpoint['manifestFileSha256'])}"
            ),
            (
                f"test \"$(sha256sum {shlex.quote(phone_path)} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(phone_sha)}"
            ),
            (
                f"test \"$(sha256sum {shlex.quote(laptop_path)} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(laptop_sha)}"
            ),
            "systemctl is-enabled --quiet lift-workload.service",
            "printf '%s' verified",
        ],
        "Verify exact workspace recovery after EC2 restart",
        timeout_seconds=120,
    )
    if verified.splitlines()[-1] != "verified":
        raise SpikeError("workspace recovery verification did not complete")

    runner_after: dict[str, Any] = {}
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        runner_after = parse_last_json(
            send_command(
                instance_id,
                ["set -euo pipefail", "python3 /opt/lift-spike/runner.py status"],
                "Inspect rebooted provider-neutral runner",
                timeout_seconds=60,
            ),
            "runner status",
        )
        if runner_after.get("active") is True and runner_after.get("healthy") is True:
            break
        time.sleep(5)
    if runner_after.get("active") is not True or runner_after.get("healthy") is not True:
        raise SpikeError("provider-neutral runner did not recover healthy after restart")

    boot_after = send_command(
        instance_id,
        ["set -euo pipefail", "cat /proc/sys/kernel/random/boot_id"],
        "Capture post-restart guest boot identity",
        timeout_seconds=60,
    ).splitlines()[-1]
    if boot_after == boot_before:
        raise SpikeError("guest boot identity did not change across EC2 stop/start")
    remote_after = managed_remote_status(instance_id, REMOTE_WORKSPACE)
    environment_preserved = remote_after.get("environmentId") == expected_environment_id

    state = load_state()
    readiness = state["readiness"]
    runtime = state["runtime"]
    runtime["state"] = "RUNNING"
    readiness["storageDurable"] = True
    readiness["manifestVerified"] = True
    readiness["recoveryCheckpointDurable"] = True
    readiness["workloadHealthy"] = True
    readiness["providerPhoneProbeVerified"] = False
    readiness["localStepsComplete"] = False
    readiness["safeToClose"] = False
    readiness["providerEnvironmentId"] = remote_after["environmentId"]
    readiness["restartEvidence"] = {
        "verifiedAt": now_iso(),
        "instanceId": instance_id,
        "workspaceVolumeId": expected_volume_id,
        "checkpointCommit": checkpoint["commit"],
        "checkpointTree": checkpoint["tree"],
        "bootIdBefore": boot_before,
        "bootIdAfter": boot_after,
        "environmentIdBefore": expected_environment_id,
        "environmentIdAfter": remote_after["environmentId"],
        "environmentPreserved": environment_preserved,
        "runnerHealthy": True,
    }
    state["connection"]["state"] = (
        "RESTART_RECOVERED_AWAITING_PHONE_CONFIRMATION"
        if environment_preserved
        else "RESTART_RECOVERED_NEW_PROVIDER_ENVIRONMENT"
    )
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "runtime.restart_test_recovered",
        bootIdBefore=boot_before,
        bootIdAfter=boot_after,
        environmentPreserved=environment_preserved,
        checkpointCommit=checkpoint["commit"],
    )
    print(
        json.dumps(
            {
                "bootIdChanged": True,
                "checkpointRecovered": True,
                "environmentId": remote_after["environmentId"],
                "environmentPreserved": environment_preserved,
                "instanceId": instance_id,
                "runnerHealthy": True,
                "safeToClose": False,
                "workspaceVolumeId": expected_volume_id,
                "nextAction": "Confirm the recovered workspace once from the Codex phone app.",
            },
            indent=2,
            sort_keys=True,
        )
    )


def cmd_interactive(args: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    plugin = shutil.which("session-manager-plugin")
    if plugin is None:
        raise SpikeError("Session Manager plugin is required for unlogged interactive provider flows")
    outputs = validated_stack_context(state)
    if args.flow == "auth":
        remote_command = "sudo -iu lift env PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin codex login --device-auth"
    elif args.flow == "pair":
        remote_command = "sudo -iu lift env PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin codex remote-control pair --json"
    else:
        remote_command = "sudo -iu lift env PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin codex login status"
    print(INTERACTIVE_WARNING, file=sys.stderr)
    parameters = json.dumps({"command": [remote_command]}, separators=(",", ":"))
    completed = run(
        aws_arguments(
            "ssm",
            "start-session",
            "--target",
            outputs["InstanceId"],
            "--document-name",
            "AWS-StartInteractiveCommand",
            "--parameters",
            parameters,
        ),
        capture=False,
    )
    if completed.returncode != 0:
        raise SpikeError(f"interactive {args.flow} flow failed")


def managed_remote_status(instance_id: str, workspace: str) -> dict[str, Any]:
    command = (
        "sudo -u lift env HOME=/home/lift "
        f"LIFT_WORKSPACE={shlex.quote(workspace)} "
        "PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin "
        "python3 /opt/lift-spike/codex_project.py status --name lift"
    )
    raw = send_command(
        instance_id,
        ["set -euo pipefail", command],
        "Verify native Codex project and remote readiness",
        timeout_seconds=120,
    )
    try:
        connector = json.loads(raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SpikeError("Codex project readiness was not valid JSON") from exc
    if not isinstance(connector, dict):
        raise SpikeError("Codex project readiness returned a non-object")
    daemon = connector.get("daemon")
    remote = connector.get("remote")
    project = connector.get("project")
    controller_project_visibility = connector.get(
        "controllerProjectVisibility"
    )
    if not isinstance(daemon, dict) or not isinstance(remote, dict) or not isinstance(project, dict):
        raise SpikeError("Codex project readiness omitted required details")
    required = {
        "readyForPhoneProof": connector.get("readyForPhoneProof") is True,
        "serverProjectRegistered": connector.get("serverProjectRegistered") is True,
        "controllerProjectVisibility": controller_project_visibility
        == {"status": "unknown", "verified": False},
        "workspace": connector.get("workspace") == workspace,
        "remoteStatus": remote.get("status") == "connected",
        "controllerPresent": remote.get("controllerPresent") is True,
        "environmentId": isinstance(remote.get("environmentId"), str)
        and bool(remote.get("environmentId")),
        "projectId": isinstance(project.get("id"), str) and bool(project.get("id")),
        "projectRoot": project.get("root") == workspace,
        "projectTrusted": project.get("trusted") is True,
        "managedCodexVersion": daemon.get("managedCodexVersion") == "0.152.1",
        "cliVersion": daemon.get("cliVersion") == "0.152.1",
        "appServerVersion": daemon.get("appServerVersion") == "0.152.1",
        "socketPath": daemon.get("socketPath")
        == "/home/lift/.codex/app-server-control/app-server-control.sock",
    }
    failed = sorted(key for key, passed in required.items() if not passed)
    if failed:
        raise SpikeError(
            "native Codex project readiness failed: " + ", ".join(failed)
        )
    return {
        **remote,
        "controllerProjectVisibility": controller_project_visibility,
        "daemon": daemon,
        "nativeProjectId": project["id"],
        "projectRoot": project["root"],
        "serverProjectRegistered": True,
        "workspace": workspace,
    }


def managed_thread_baseline(instance_id: str, workspace: str) -> dict[str, Any]:
    if (
        INSTANCE_ID_PATTERN.fullmatch(instance_id) is None
        or workspace != REMOTE_WORKSPACE
    ):
        raise SpikeError("thread baseline requires the exact Lift runtime and workspace")
    command = (
        "sudo -u lift env HOME=/home/lift "
        f"LIFT_WORKSPACE={shlex.quote(workspace)} "
        "PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin "
        "python3 /opt/lift-spike/codex_project.py thread-baseline --name lift"
    )
    raw = send_command(
        instance_id,
        ["set -euo pipefail", command],
        "Capture native Codex thread baseline",
        timeout_seconds=120,
    )
    baseline = parse_last_json(raw, "Codex thread baseline")
    expected_keys = {
        "approvalGuardSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "createdAtEpochSeconds",
        "cwd",
        "environmentId",
        "nativeProjectId",
        "projectRoot",
        "threadIds",
    }
    thread_ids = baseline.get("threadIds")
    created_at = baseline.get("createdAtEpochSeconds")
    approval_guard = baseline.get("approvalGuardSha256")
    if (
        set(baseline) != expected_keys
        or isinstance(created_at, bool)
        or not isinstance(created_at, int)
        or created_at < 0
        or not isinstance(approval_guard, str)
        or SHA256_PATTERN.fullmatch(approval_guard) is None
        or baseline.get("controllerThreadBinding") != CONTROLLER_THREAD_BINDING
        or baseline.get("controllerThreadProjectId") is not None
        or baseline.get("cwd") != workspace
        or baseline.get("projectRoot") != workspace
        or not isinstance(baseline.get("environmentId"), str)
        or not baseline.get("environmentId")
        or not isinstance(baseline.get("nativeProjectId"), str)
        or not baseline.get("nativeProjectId")
        or not isinstance(thread_ids, list)
        or len(thread_ids) > MAX_BASELINE_THREAD_IDS
        or not all(
            isinstance(thread_id, str) and 0 < len(thread_id) <= 256
            for thread_id in thread_ids
        )
        or thread_ids != sorted(set(thread_ids))
        or sum(len(thread_id.encode("utf-8")) + 32 for thread_id in thread_ids)
        > MAX_BASELINE_THREAD_ARGUMENT_BYTES
    ):
        raise SpikeError("Codex thread baseline was malformed or too large")
    return baseline


def valid_approval_policy(value: Any) -> bool:
    if isinstance(value, str):
        return value in {"untrusted", "on-request"}
    if not isinstance(value, dict) or set(value) != {"granular"}:
        return False
    granular = value.get("granular")
    required = {"sandbox_approval", "rules", "mcp_elicitations"}
    optional = {"skill_approval", "request_permissions"}
    return (
        isinstance(granular, dict)
        and required.issubset(granular)
        and set(granular).issubset(required | optional)
        and all(isinstance(setting, bool) for setting in granular.values())
    )


def approval_observer_thread_ids_sha256(thread_ids: Any) -> str:
    if (
        not isinstance(thread_ids, list)
        or len(thread_ids) > MAX_BASELINE_THREAD_IDS
        or not all(
            isinstance(thread_id, str) and 0 < len(thread_id) <= 256
            for thread_id in thread_ids
        )
        or thread_ids != sorted(set(thread_ids))
    ):
        raise SpikeError("the approval observer thread baseline is invalid")
    canonical = json.dumps(
        thread_ids, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def approval_observer_unit_name(challenge_sha256: str) -> str:
    if SHA256_PATTERN.fullmatch(challenge_sha256) is None:
        raise SpikeError("the approval observer challenge SHA-256 is invalid")
    return f"lift-approval-observer-{challenge_sha256}.service"


def approval_observer_paths(challenge_sha256: str) -> tuple[str, str]:
    if SHA256_PATTERN.fullmatch(challenge_sha256) is None:
        raise SpikeError("the approval observer challenge SHA-256 is invalid")
    prefix = f"{REMOTE_APPROVAL_OBSERVATION_ROOT}/{challenge_sha256}"
    return f"{prefix}.ready.json", f"{prefix}.evidence.json"


def valid_observer_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and "\x00" not in value
        and len(value.encode("utf-8")) <= 512
    )


def approval_observer_ready_is_bound(
    evidence: Any,
    *,
    workspace: str,
    challenge: dict[str, Any],
    challenge_sha256: str,
    approval_command_sha256: str,
    proof_command_sha256: str,
) -> bool:
    baseline = challenge.get("threadBaseline")
    if not isinstance(baseline, dict):
        return False
    try:
        baseline_sha256 = approval_observer_thread_ids_sha256(
            baseline.get("threadIds")
        )
    except SpikeError:
        return False
    return (
        isinstance(evidence, dict)
        and set(evidence) == APPROVAL_OBSERVER_READY_KEYS
        and evidence.get("schemaVersion") == 8
        and evidence.get("verificationMethod") == APPROVAL_OBSERVER_READY_METHOD
        and evidence.get("challengeSha256") == challenge_sha256
        and evidence.get("controllerThreadBinding") == CONTROLLER_THREAD_BINDING
        and evidence.get("controllerThreadProjectId") is None
        and evidence.get("approvalGuardSha256")
        == baseline.get("approvalGuardSha256")
        and evidence.get("baselineThreadIdsSha256") == baseline_sha256
        and evidence.get("approvalCommandSha256") == approval_command_sha256
        and evidence.get("proofCommandSha256") == proof_command_sha256
        and evidence.get("createdAfterEpochSeconds")
        == baseline.get("createdAtEpochSeconds")
        and evidence.get("cwd") == workspace
        and evidence.get("environmentId") == challenge.get("environmentId")
        and evidence.get("nativeProjectId") == challenge.get("nativeProjectId")
    )


def approval_observation_is_bound(
    evidence: Any,
    *,
    workspace: str,
    challenge: dict[str, Any],
    challenge_sha256: str,
    approval_command_sha256: str,
    proof_command_sha256: str,
    thread_evidence: dict[str, Any],
) -> bool:
    baseline = challenge.get("threadBaseline")
    if not isinstance(baseline, dict):
        return False
    try:
        baseline_sha256 = approval_observer_thread_ids_sha256(
            baseline.get("threadIds")
        )
    except SpikeError:
        return False
    request_id = evidence.get("requestId") if isinstance(evidence, dict) else None
    valid_request_id = (
        isinstance(request_id, int)
        and not isinstance(request_id, bool)
        and request_id >= 0
    ) or valid_observer_identifier(request_id)
    integer_fields = (
        "approvalCommandCompletedAtEpochMilliseconds",
        "approvalCommandStartedAtEpochMilliseconds",
        "createdAfterEpochSeconds",
        "observedAtEpochSeconds",
        "proofCommandCompletedAtEpochMilliseconds",
        "proofCommandStartedAtEpochMilliseconds",
        "requestStartedAtEpochMilliseconds",
        "turnCompletedAtEpochSeconds",
    )
    if (
        not isinstance(evidence, dict)
        or set(evidence) != APPROVAL_OBSERVATION_KEYS
        or not valid_request_id
        or any(
            isinstance(evidence.get(key), bool)
            or not isinstance(evidence.get(key), int)
            or evidence[key] < 0
            for key in integer_fields
        )
        or any(
            not valid_observer_identifier(evidence.get(key))
            for key in ("approvalItemId", "proofItemId", "threadId", "turnId")
        )
    ):
        return False
    created_after = baseline.get("createdAtEpochSeconds")
    request_started_ms = evidence["requestStartedAtEpochMilliseconds"]
    approval_started_ms = evidence[
        "approvalCommandStartedAtEpochMilliseconds"
    ]
    approval_completed_ms = evidence[
        "approvalCommandCompletedAtEpochMilliseconds"
    ]
    proof_started_ms = evidence["proofCommandStartedAtEpochMilliseconds"]
    proof_completed_ms = evidence["proofCommandCompletedAtEpochMilliseconds"]
    turn_completed = evidence["turnCompletedAtEpochSeconds"]
    observed_at = evidence["observedAtEpochSeconds"]
    command_hashes = thread_evidence.get("commandSha256")
    return (
        evidence.get("schemaVersion") == 8
        and evidence.get("verificationMethod")
        == APPROVAL_OBSERVER_VERIFICATION_METHOD
        and evidence.get("challengeSha256") == challenge_sha256
        and evidence.get("controllerThreadBinding") == CONTROLLER_THREAD_BINDING
        and evidence.get("controllerThreadProjectId") is None
        and thread_evidence.get("controllerThreadBinding")
        == CONTROLLER_THREAD_BINDING
        and thread_evidence.get("controllerThreadProjectId") is None
        and evidence.get("approvalGuardSha256")
        == baseline.get("approvalGuardSha256")
        and evidence.get("baselineThreadIdsSha256") == baseline_sha256
        and evidence.get("createdAfterEpochSeconds") == created_after
        and evidence.get("approvalCommandSha256") == approval_command_sha256
        and evidence.get("proofCommandSha256") == proof_command_sha256
        and isinstance(command_hashes, dict)
        and command_hashes.get("approval") == approval_command_sha256
        and command_hashes.get("proof") == proof_command_sha256
        and evidence.get("cwd") == workspace
        and evidence.get("environmentId") == challenge.get("environmentId")
        and evidence.get("nativeProjectId") == challenge.get("nativeProjectId")
        and evidence.get("requestEnvironmentId")
        == APPROVAL_REQUEST_EXECUTION_ENVIRONMENT_ID
        and evidence.get("threadId") == thread_evidence.get("threadId")
        and isinstance(evidence.get("threadGoalClearedCount"), int)
        and not isinstance(evidence.get("threadGoalClearedCount"), bool)
        and 1 <= evidence["threadGoalClearedCount"] <= 2
        and isinstance(evidence.get("threadNameUpdatedCount"), int)
        and not isinstance(evidence.get("threadNameUpdatedCount"), bool)
        and 0 <= evidence["threadNameUpdatedCount"] <= 1
        and evidence.get("turnId") == thread_evidence.get("turnId")
        and evidence.get("approvalItemId")
        == thread_evidence.get("approvalItemId")
        and evidence.get("proofItemId") == thread_evidence.get("proofItemId")
        and isinstance(created_after, int)
        and not isinstance(created_after, bool)
        and request_started_ms >= created_after * 1000
        and request_started_ms <= approval_started_ms <= approval_completed_ms
        and approval_started_ms - request_started_ms <= 10_000
        and approval_completed_ms <= proof_started_ms <= proof_completed_ms
        and turn_completed >= proof_completed_ms // 1000
        and observed_at >= turn_completed
    )


def approval_canary_command(approval_nonce: str) -> str:
    if re.fullmatch(r"[0-9a-f]{32}", approval_nonce) is None:
        raise SpikeError("the approval nonce is malformed")
    return shlex.join(
        [
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
    )


def phone_proof_command(challenge: dict[str, Any]) -> str:
    phone_challenge_sha256(challenge)
    source = challenge["proofSource"]
    proof = proof_bytes(challenge, source).decode("utf-8").rstrip("\n")
    return (
        f"test \"$(pwd -P)\" = {shlex.quote(REMOTE_WORKSPACE)} && "
        "mkdir -p -- .lift && "
        f"printf '%s\\n' {shlex.quote(proof)} > "
        f"{shlex.quote(challenge['proofRelativePath'])}"
    )


def approval_observer_start_commands(
    *,
    workspace: str,
    challenge: dict[str, Any],
    previous_challenge_sha256: str | None = None,
) -> list[str]:
    if workspace != REMOTE_WORKSPACE:
        raise SpikeError("approval observation requires the exact Lift workspace")
    challenge_sha256 = phone_challenge_sha256(challenge)
    baseline = challenge.get("threadBaseline")
    if not isinstance(baseline, dict):
        raise SpikeError("approval observation requires a native thread baseline")
    created_after = baseline.get("createdAtEpochSeconds")
    thread_ids = baseline.get("threadIds")
    approval_guard_sha256 = baseline.get("approvalGuardSha256")
    if (
        isinstance(created_after, bool)
        or not isinstance(created_after, int)
        or created_after < 0
        or not isinstance(approval_guard_sha256, str)
        or SHA256_PATTERN.fullmatch(approval_guard_sha256) is None
    ):
        raise SpikeError("approval observation received a malformed thread baseline")
    approval_observer_thread_ids_sha256(thread_ids)
    if previous_challenge_sha256 is not None:
        if SHA256_PATTERN.fullmatch(previous_challenge_sha256) is None:
            raise SpikeError("the previous approval observer challenge is malformed")
        if previous_challenge_sha256 == challenge_sha256:
            previous_challenge_sha256 = None

    approval_command_sha256 = hashlib.sha256(
        approval_canary_command(challenge["approvalNonce"]).encode("utf-8")
    ).hexdigest()
    proof_command_sha256 = hashlib.sha256(
        phone_proof_command(challenge).encode("utf-8")
    ).hexdigest()
    ready_path, evidence_path = approval_observer_paths(challenge_sha256)
    unit = approval_observer_unit_name(challenge_sha256)
    observer_arguments = [
        "--workspace",
        workspace,
        "--project-id",
        challenge["nativeProjectId"],
        "--environment-id",
        challenge["environmentId"],
        "--created-after",
        str(created_after),
        "--expected-approval-command-sha256",
        approval_command_sha256,
        "--expected-proof-command-sha256",
        proof_command_sha256,
        "--challenge-sha256",
        challenge_sha256,
        "--approval-guard-sha256",
        approval_guard_sha256,
        "--ready-output",
        ready_path,
        "--output",
        evidence_path,
        "--timeout",
        str(APPROVAL_OBSERVER_TIMEOUT_SECONDS),
    ]
    for thread_id in thread_ids:
        observer_arguments.extend(("--baseline-thread-id", thread_id))
    properties = [
        "Type=exec",
        "RemainAfterExit=yes",
        "Restart=no",
        "User=root",
        "Group=root",
        "UMask=0077",
        "WorkingDirectory=/",
        f"RuntimeMaxSec={APPROVAL_OBSERVER_TIMEOUT_SECONDS + 30}",
        "TimeoutStopSec=5",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "PrivateNetwork=yes",
        "ProtectSystem=strict",
        "ProtectHome=read-only",
        "ProtectControlGroups=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelLogs=yes",
        "ProtectClock=yes",
        "ProtectHostname=yes",
        "LockPersonality=yes",
        "MemoryDenyWriteExecute=yes",
        "RestrictSUIDSGID=yes",
        "RestrictAddressFamilies=AF_UNIX",
        "SystemCallArchitectures=native",
        "IPAddressDeny=any",
        f"ReadWritePaths={REMOTE_APPROVAL_OBSERVATION_ROOT}",
        "StandardOutput=journal",
        "StandardError=journal",
    ]
    launch = [
        "systemd-run",
        f"--unit={unit}",
        "--quiet",
        *[f"--property={property_value}" for property_value in properties],
        "--setenv=HOME=/root",
        "--setenv=PATH=/usr/bin:/bin",
        "--setenv=PYTHONNOUSERSITE=1",
        "--setenv=PYTHONDONTWRITEBYTECODE=1",
        "--setenv=PYTHONPATH=",
        "--",
        "/usr/bin/python3",
    ]
    launch_command = (
        shlex.join(launch)
        + ' "$RUNTIME_RELEASE/approval_observer.py" '
        + shlex.join(observer_arguments)
    )
    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C",
        "umask 077",
        f"OBSERVATION_ROOT={shlex.quote(REMOTE_APPROVAL_OBSERVATION_ROOT)}",
        f"READY_PATH={shlex.quote(ready_path)}",
        f"EVIDENCE_PATH={shlex.quote(evidence_path)}",
        f"OBSERVER_UNIT={shlex.quote(unit)}",
        f"RUNTIME_ACTIVE={shlex.quote(REMOTE_RUNTIME_PATH)}",
        f"RUNTIME_RELEASE_ROOT={shlex.quote(REMOTE_RUNTIME_RELEASE_ROOT)}",
        'if [ ! -e "$OBSERVATION_ROOT" ]; then install -d -o root -g root -m 0700 "$OBSERVATION_ROOT"; fi',
        'test ! -L "$OBSERVATION_ROOT"',
        'test "$(stat -c \'%a:%u:%g:%F\' -- "$OBSERVATION_ROOT")" = "700:0:0:directory"',
        'RUNTIME_RELEASE=$(realpath -e -- "$RUNTIME_ACTIVE")',
        'case "$RUNTIME_RELEASE" in "$RUNTIME_RELEASE_ROOT"/[0-9a-f][0-9a-f]*) ;; *) exit 1 ;; esac',
        'test "$(stat -c \'%a:%u:%g:%F\' -- "$RUNTIME_RELEASE")" = "755:0:0:directory"',
        'test ! -L "$RUNTIME_RELEASE/approval_observer.py"',
        'test ! -L "$RUNTIME_RELEASE/codex_project.py"',
        (
            'test "$(sha256sum -- "$RUNTIME_RELEASE/approval_observer.py" | cut -d \' \' -f 1)" = '
            + shlex.quote(sha256_file(APPROVAL_OBSERVER_PATH))
        ),
        (
            'test "$(sha256sum -- "$RUNTIME_RELEASE/codex_project.py" | cut -d \' \' -f 1)" = '
            + shlex.quote(sha256_file(CODEX_PROJECT_PATH))
        ),
    ]
    if previous_challenge_sha256 is not None:
        previous_unit = approval_observer_unit_name(previous_challenge_sha256)
        commands.extend(
            [
                f"systemctl stop {shlex.quote(previous_unit)} >/dev/null 2>&1 || true",
                f"systemctl reset-failed {shlex.quote(previous_unit)} >/dev/null 2>&1 || true",
            ]
        )
    commands.extend(
        [
            'if [ -e "$EVIDENCE_PATH" ] || [ -L "$EVIDENCE_PATH" ]; then echo "approval observation already completed" >&2; exit 1; fi',
            'if [ -e "$READY_PATH" ] || [ -L "$READY_PATH" ]; then',
            '  test ! -L "$READY_PATH"',
            '  test "$(stat -c \'%a:%u:%g:%h:%F\' -- "$READY_PATH")" = "600:0:0:1:regular file"',
            '  systemctl is-active --quiet "$OBSERVER_UNIT"',
            '  test "$(stat -c %s -- "$READY_PATH")" -le 65536',
            '  cat -- "$READY_PATH"',
            "  exit 0",
            "fi",
            'systemctl stop "$OBSERVER_UNIT" >/dev/null 2>&1 || true',
            'systemctl reset-failed "$OBSERVER_UNIT" >/dev/null 2>&1 || true',
            launch_command,
            "for _ in {1..200}; do",
            '  if [ -s "$READY_PATH" ]; then break; fi',
            '  systemctl is-active --quiet "$OBSERVER_UNIT" || exit 1',
            "  sleep 0.1",
            "done",
            'test -s "$READY_PATH"',
            'test ! -L "$READY_PATH"',
            'test "$(stat -c \'%a:%u:%g:%h:%F\' -- "$READY_PATH")" = "600:0:0:1:regular file"',
            'test "$(stat -c %s -- "$READY_PATH")" -le 65536',
            'systemctl is-active --quiet "$OBSERVER_UNIT"',
            'cat -- "$READY_PATH"',
        ]
    )
    return commands


def managed_approval_observer_arm(
    instance_id: str,
    workspace: str,
    challenge: dict[str, Any],
    *,
    previous_challenge_sha256: str | None = None,
) -> dict[str, Any]:
    if INSTANCE_ID_PATTERN.fullmatch(instance_id) is None:
        raise SpikeError("approval observation received an invalid instance ID")
    challenge_sha256 = phone_challenge_sha256(challenge)
    approval_command_sha256 = hashlib.sha256(
        approval_canary_command(challenge["approvalNonce"]).encode("utf-8")
    ).hexdigest()
    proof_command_sha256 = hashlib.sha256(
        phone_proof_command(challenge).encode("utf-8")
    ).hexdigest()
    try:
        raw = send_command(
            instance_id,
            approval_observer_start_commands(
                workspace=workspace,
                challenge=challenge,
                previous_challenge_sha256=previous_challenge_sha256,
            ),
            "Arm root-owned native approval observer",
            timeout_seconds=60,
        )
        ready = parse_last_json(raw, "approval observer readiness")
        if not approval_observer_ready_is_bound(
            ready,
            workspace=workspace,
            challenge=challenge,
            challenge_sha256=challenge_sha256,
            approval_command_sha256=approval_command_sha256,
            proof_command_sha256=proof_command_sha256,
        ):
            raise SpikeError(
                "approval observer readiness was not bound to the challenge"
            )
        return ready
    except Exception:
        try:
            stop_managed_approval_observer(instance_id, challenge_sha256)
        except Exception:
            pass
        raise


def stop_managed_approval_observer(
    instance_id: str, challenge_sha256: str
) -> None:
    if INSTANCE_ID_PATTERN.fullmatch(instance_id) is None:
        raise SpikeError("approval observer stop received an invalid instance ID")
    unit = approval_observer_unit_name(challenge_sha256)
    send_command(
        instance_id,
        [
            "set -euo pipefail",
            f"systemctl stop {shlex.quote(unit)} >/dev/null 2>&1 || true",
            f"systemctl reset-failed {shlex.quote(unit)} >/dev/null 2>&1 || true",
            "printf '%s' stopped",
        ],
        "Stop native approval observer",
        timeout_seconds=30,
    )


def managed_approval_observer_evidence(
    instance_id: str,
    workspace: str,
    challenge: dict[str, Any],
    thread_evidence: dict[str, Any],
) -> dict[str, Any]:
    if (
        INSTANCE_ID_PATTERN.fullmatch(instance_id) is None
        or workspace != REMOTE_WORKSPACE
    ):
        raise SpikeError("approval observation requires the exact Lift runtime")
    challenge_sha256 = phone_challenge_sha256(challenge)
    approval_command_sha256 = hashlib.sha256(
        approval_canary_command(challenge["approvalNonce"]).encode("utf-8")
    ).hexdigest()
    proof_command_sha256 = hashlib.sha256(
        phone_proof_command(challenge).encode("utf-8")
    ).hexdigest()
    ready_path, evidence_path = approval_observer_paths(challenge_sha256)
    unit = approval_observer_unit_name(challenge_sha256)
    raw = send_command(
        instance_id,
        [
            "set -Eeuo pipefail",
            "export LC_ALL=C",
            f"OBSERVATION_ROOT={shlex.quote(REMOTE_APPROVAL_OBSERVATION_ROOT)}",
            f"READY_PATH={shlex.quote(ready_path)}",
            f"EVIDENCE_PATH={shlex.quote(evidence_path)}",
            f"OBSERVER_UNIT={shlex.quote(unit)}",
            'test ! -L "$OBSERVATION_ROOT"',
            'test "$(stat -c \'%a:%u:%g:%F\' -- "$OBSERVATION_ROOT")" = "700:0:0:directory"',
            'test "$(systemctl show "$OBSERVER_UNIT" --property=ActiveState --value)" = active',
            'test "$(systemctl show "$OBSERVER_UNIT" --property=SubState --value)" = exited',
            'test "$(systemctl show "$OBSERVER_UNIT" --property=Result --value)" = success',
            'test "$(systemctl show "$OBSERVER_UNIT" --property=ExecMainStatus --value)" = 0',
            'test ! -L "$READY_PATH"',
            'test "$(stat -c \'%a:%u:%g:%h:%F\' -- "$READY_PATH")" = "600:0:0:1:regular file"',
            'test ! -L "$EVIDENCE_PATH"',
            'test "$(stat -c \'%a:%u:%g:%h:%F\' -- "$EVIDENCE_PATH")" = "600:0:0:1:regular file"',
            'test "$(stat -c %s -- "$EVIDENCE_PATH")" -le 65536',
            'cat -- "$EVIDENCE_PATH"',
        ],
        "Read root-owned native approval observation",
        timeout_seconds=60,
    )
    evidence = parse_last_json(raw, "approval observer evidence")
    if not approval_observation_is_bound(
        evidence,
        workspace=workspace,
        challenge=challenge,
        challenge_sha256=challenge_sha256,
        approval_command_sha256=approval_command_sha256,
        proof_command_sha256=proof_command_sha256,
        thread_evidence=thread_evidence,
    ):
        raise SpikeError("approval observer returned unbound evidence")
    return evidence


def phone_challenge_sha256(
    challenge: Any, *, expected_source: str | None = None
) -> str:
    """Validate and identify one exact native-phone proof/approval challenge."""
    expected_keys = {
        "approvalNonce",
        "checkpointLabel",
        "environmentId",
        "expectedCwd",
        "issuedAt",
        "nativeProjectId",
        "nonce",
        "projectRoot",
        "proofRelativePath",
        "proofSource",
        "schemaVersion",
        "threadBaseline",
    }
    if not isinstance(challenge, dict) or set(challenge) != expected_keys:
        raise SpikeError("the native phone challenge schema is not exact")
    source = challenge.get("proofSource")
    if source not in PHONE_PROOF_SOURCES or (
        expected_source is not None and source != expected_source
    ):
        raise SpikeError("the native phone challenge source is invalid")
    nonce = challenge.get("nonce")
    approval_nonce = challenge.get("approvalNonce")
    environment_id = challenge.get("environmentId")
    native_project_id = challenge.get("nativeProjectId")
    issued_at = challenge.get("issuedAt")
    baseline = challenge.get("threadBaseline")
    if (
        challenge.get("schemaVersion") != 3
        or re.fullmatch(r"[0-9a-f]{32}", nonce or "") is None
        or re.fullmatch(r"[0-9a-f]{32}", approval_nonce or "") is None
        or nonce == approval_nonce
        or not isinstance(environment_id, str)
        or not 0 < len(environment_id) <= 256
        or not isinstance(native_project_id, str)
        or not 0 < len(native_project_id) <= 256
        or challenge.get("expectedCwd") != REMOTE_WORKSPACE
        or challenge.get("projectRoot") != REMOTE_WORKSPACE
        or challenge.get("proofRelativePath")
        != PROOF_RELATIVE_PATH_BY_SOURCE[source]
        or challenge.get("checkpointLabel") != CHECKPOINT_LABEL_BY_SOURCE[source]
        or not isinstance(issued_at, str)
        or not isinstance(baseline, dict)
    ):
        raise SpikeError("the native phone challenge is malformed")
    try:
        parsed_issued_at = datetime.fromisoformat(issued_at)
    except ValueError as exc:
        raise SpikeError("the native phone challenge issue time is invalid") from exc
    if parsed_issued_at.tzinfo is None or parsed_issued_at.utcoffset() is None:
        raise SpikeError("the native phone challenge issue time is not timezone-aware")

    baseline_keys = {
        "approvalGuardSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "createdAtEpochSeconds",
        "cwd",
        "environmentId",
        "nativeProjectId",
        "projectRoot",
        "threadIds",
    }
    created_at = baseline.get("createdAtEpochSeconds")
    thread_ids = baseline.get("threadIds")
    if (
        set(baseline) != baseline_keys
        or isinstance(created_at, bool)
        or not isinstance(created_at, int)
        or created_at < 0
        or not isinstance(baseline.get("approvalGuardSha256"), str)
        or SHA256_PATTERN.fullmatch(baseline["approvalGuardSha256"]) is None
        or baseline.get("controllerThreadBinding") != CONTROLLER_THREAD_BINDING
        or baseline.get("controllerThreadProjectId") is not None
        or baseline.get("cwd") != REMOTE_WORKSPACE
        or baseline.get("projectRoot") != REMOTE_WORKSPACE
        or baseline.get("environmentId") != environment_id
        or baseline.get("nativeProjectId") != native_project_id
        or not isinstance(thread_ids, list)
        or len(thread_ids) > MAX_BASELINE_THREAD_IDS
        or not all(
            isinstance(thread_id, str) and 0 < len(thread_id) <= 256
            for thread_id in thread_ids
        )
        or thread_ids != sorted(set(thread_ids))
        or sum(len(thread_id.encode("utf-8")) + 32 for thread_id in thread_ids)
        > MAX_BASELINE_THREAD_ARGUMENT_BYTES
    ):
        raise SpikeError("the native phone challenge thread baseline is malformed")
    canonical = json.dumps(
        challenge,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def active_phone_challenge(
    readiness: Any,
    *,
    expected_source: str | None = None,
    require_post_restart_alias: bool = False,
) -> tuple[dict[str, Any], str]:
    if not isinstance(readiness, dict):
        raise SpikeError("the readiness state is malformed")
    challenge = readiness.get("challenge")
    digest = phone_challenge_sha256(challenge, expected_source=expected_source)
    if readiness.get("activeChallengeSha256") != digest:
        raise SpikeError("the active native phone challenge identity changed")
    if require_post_restart_alias:
        alias = readiness.get("postRestartChallenge")
        if not isinstance(alias, dict) or alias != challenge:
            raise SpikeError("the post-restart challenge is stale or ambiguous")
    return challenge, digest


def laptop_off_challenge_sha256(challenge: Any) -> str:
    expected_keys = {
        "checkpointLabel",
        "environmentId",
        "expectedCwd",
        "issuedAt",
        "nativeProjectId",
        "nonce",
        "projectRoot",
        "proofRelativePath",
        "proofSource",
        "schemaVersion",
    }
    source = "codex-phone-laptop-off"
    if not isinstance(challenge, dict) or set(challenge) != expected_keys:
        raise SpikeError("the laptop-off challenge schema is not exact")
    issued_at = challenge.get("issuedAt")
    if (
        challenge.get("schemaVersion") != 3
        or re.fullmatch(r"[0-9a-f]{32}", challenge.get("nonce") or "") is None
        or challenge.get("expectedCwd") != REMOTE_WORKSPACE
        or challenge.get("projectRoot") != REMOTE_WORKSPACE
        or challenge.get("proofSource") != source
        or challenge.get("proofRelativePath")
        != PROOF_RELATIVE_PATH_BY_SOURCE[source]
        or challenge.get("checkpointLabel") != CHECKPOINT_LABEL_BY_SOURCE[source]
        or not isinstance(challenge.get("environmentId"), str)
        or not challenge.get("environmentId")
        or not isinstance(challenge.get("nativeProjectId"), str)
        or not challenge.get("nativeProjectId")
        or not isinstance(issued_at, str)
    ):
        raise SpikeError("the laptop-off challenge is malformed")
    try:
        parsed_issued_at = datetime.fromisoformat(issued_at)
    except ValueError as exc:
        raise SpikeError("the laptop-off challenge issue time is invalid") from exc
    if parsed_issued_at.tzinfo is None or parsed_issued_at.utcoffset() is None:
        raise SpikeError("the laptop-off challenge issue time is not timezone-aware")
    canonical = json.dumps(
        challenge,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verified_phone_challenge(
    readiness: Any,
) -> tuple[dict[str, Any], str, str, str]:
    challenge, challenge_sha = active_phone_challenge(readiness)
    source = challenge["proofSource"]
    proof_sha = hashlib.sha256(proof_bytes(challenge, source)).hexdigest()
    approval_command_sha256 = hashlib.sha256(
        approval_canary_command(challenge["approvalNonce"]).encode("utf-8")
    ).hexdigest()
    proof_command_sha256 = hashlib.sha256(
        phone_proof_command(challenge).encode("utf-8")
    ).hexdigest()
    phone_thread = readiness.get("phoneThreadEvidence")
    approval = readiness.get("approvalEvidence")
    baseline = challenge.get("threadBaseline")
    approval_observation = (
        phone_thread.get("approvalObservation")
        if isinstance(phone_thread, dict)
        else None
    )
    if (
        readiness.get("providerPhoneProbeVerified") is not True
        or readiness.get("approvalRoundTripVerified") is not True
        or not isinstance(phone_thread, dict)
        or not isinstance(approval, dict)
        or phone_thread.get("challengeSha256") != challenge_sha
        or approval.get("challengeSha256") != challenge_sha
        or phone_thread.get("controllerThreadBinding")
        != CONTROLLER_THREAD_BINDING
        or approval.get("controllerThreadBinding") != CONTROLLER_THREAD_BINDING
        or phone_thread.get("controllerThreadProjectId") is not None
        or approval.get("controllerThreadProjectId") is not None
        or phone_thread.get("proofSha256") != proof_sha
        or phone_thread.get("threadId") != approval.get("threadId")
        or phone_thread.get("turnId") != approval.get("turnId")
        or phone_thread.get("approvalItemId") != approval.get("itemId")
        or phone_thread.get("proofItemId") != approval.get("proofItemId")
        or phone_thread.get("environmentId") != challenge.get("environmentId")
        or approval.get("environmentId") != challenge.get("environmentId")
        or phone_thread.get("nativeProjectId") != challenge.get("nativeProjectId")
        or approval.get("nativeProjectId") != challenge.get("nativeProjectId")
        or phone_thread.get("projectRoot") != REMOTE_WORKSPACE
        or approval.get("projectRoot") != REMOTE_WORKSPACE
        or phone_thread.get("cwd") != REMOTE_WORKSPACE
        or phone_thread.get("runtimeWorkspaceRoots") != [REMOTE_WORKSPACE]
        or approval.get("runtimeWorkspaceRoots") != [REMOTE_WORKSPACE]
        or phone_thread.get("networkAccess") is not False
        or approval.get("networkAccess") is not False
        or phone_thread.get("approvalsReviewer") != "user"
        or approval.get("approvalsReviewer") != "user"
        or phone_thread.get("sandboxType") not in {"readOnly", "workspaceWrite"}
        or approval.get("sandboxType") != phone_thread.get("sandboxType")
        or phone_thread.get("approvalPolicy") != "on-request"
        or approval.get("approvalPolicy") != phone_thread.get("approvalPolicy")
        or not isinstance(baseline, dict)
        or not isinstance(baseline.get("approvalGuardSha256"), str)
        or SHA256_PATTERN.fullmatch(baseline["approvalGuardSha256"]) is None
        or phone_thread.get("approvalGuardSha256")
        != baseline.get("approvalGuardSha256")
        or approval.get("approvalGuardSha256")
        != baseline.get("approvalGuardSha256")
        or phone_thread.get("approvalVerificationMethod")
        != APPROVAL_VERIFICATION_METHOD
        or approval.get("approvalVerificationMethod")
        != APPROVAL_VERIFICATION_METHOD
        or phone_thread.get("historicalVerificationMethod")
        != THREAD_VERIFICATION_METHOD
        or approval.get("historicalVerificationMethod")
        != THREAD_VERIFICATION_METHOD
        or approval.get("approvalObservation") != approval_observation
        or not isinstance(phone_thread.get("commandSha256"), dict)
        or phone_thread["commandSha256"].get("approval")
        != approval.get("commandSha256")
        or phone_thread["commandSha256"].get("proof")
        != approval.get("proofCommandSha256")
        or phone_thread["commandSha256"].get("approval")
        != approval_command_sha256
        or phone_thread["commandSha256"].get("proof") != proof_command_sha256
        or SHA256_PATTERN.fullmatch(approval.get("commandSha256") or "") is None
        or SHA256_PATTERN.fullmatch(approval.get("proofCommandSha256") or "")
        is None
        or not approval_observation_is_bound(
            approval_observation,
            workspace=REMOTE_WORKSPACE,
            challenge=challenge,
            challenge_sha256=challenge_sha,
            approval_command_sha256=approval_command_sha256,
            proof_command_sha256=proof_command_sha256,
            thread_evidence=phone_thread,
        )
    ):
        raise SpikeError("the native phone proof and approval evidence are not bound")
    return challenge, challenge_sha, source, proof_sha


def checkpoint_evidence_plan(
    readiness: Any, evidence_kind: str
) -> dict[str, Any]:
    (
        phone_challenge,
        phone_challenge_sha,
        phone_proof_source,
        phone_proof_sha,
    ) = verified_phone_challenge(readiness)
    if evidence_kind == "phone":
        challenge = phone_challenge
        challenge_sha = phone_challenge_sha
        proof_source = phone_proof_source
    elif evidence_kind == "laptop-off":
        if readiness.get("laptopOffProven") is not True:
            raise SpikeError("the laptop-off workspace proof must be verified first")
        challenge = readiness.get("laptopOffChallenge")
        challenge_sha = laptop_off_challenge_sha256(challenge)
        if challenge_sha != readiness.get("laptopOffChallengeSha256"):
            raise SpikeError("the verified laptop-off challenge identity changed")
        proof_source = "codex-phone-laptop-off"
    else:
        raise SpikeError("the checkpoint evidence kind is unsupported")
    label = CHECKPOINT_LABEL_BY_SOURCE[proof_source]
    proof_relative_path = challenge["proofRelativePath"]
    expected_proof = proof_bytes(challenge, proof_source)
    phone_proof = proof_bytes(phone_challenge, phone_proof_source)
    expected_evidence = {phone_challenge["proofRelativePath"]: phone_proof}
    expected_evidence[proof_relative_path] = expected_proof
    return {
        "challenge": challenge,
        "challengeSha256": challenge_sha,
        "expectedEvidence": expected_evidence,
        "expectedProof": expected_proof,
        "label": label,
        "phoneChallenge": phone_challenge,
        "phoneChallengeSha256": phone_challenge_sha,
        "phoneProofSha256": phone_proof_sha,
        "phoneProofSource": phone_proof_source,
        "proofRelativePath": proof_relative_path,
        "proofSource": proof_source,
    }


def managed_thread_verification(
    instance_id: str,
    workspace: str,
    challenge: dict[str, Any],
) -> dict[str, Any]:
    if (
        INSTANCE_ID_PATTERN.fullmatch(instance_id) is None
        or workspace != REMOTE_WORKSPACE
    ):
        raise SpikeError("thread verification requires the exact Lift runtime and workspace")
    phone_challenge_sha256(challenge)
    baseline = challenge.get("threadBaseline")
    proof_relative_path = challenge.get("proofRelativePath")
    proof_nonce = challenge.get("nonce")
    approval_nonce = challenge.get("approvalNonce")
    if not isinstance(baseline, dict):
        raise SpikeError("the phone challenge omitted its native thread baseline")
    normalized_baseline = {
        key: baseline.get(key)
        for key in (
            "approvalGuardSha256",
            "controllerThreadBinding",
            "controllerThreadProjectId",
            "createdAtEpochSeconds",
            "cwd",
            "environmentId",
            "nativeProjectId",
            "projectRoot",
            "threadIds",
        )
    }
    thread_ids = normalized_baseline.get("threadIds")
    created_after = normalized_baseline.get("createdAtEpochSeconds")
    approval_guard = normalized_baseline.get("approvalGuardSha256")
    if (
        set(baseline) != set(normalized_baseline)
        or isinstance(created_after, bool)
        or not isinstance(created_after, int)
        or created_after < 0
        or not isinstance(approval_guard, str)
        or SHA256_PATTERN.fullmatch(approval_guard) is None
        or normalized_baseline.get("controllerThreadBinding")
        != CONTROLLER_THREAD_BINDING
        or normalized_baseline.get("controllerThreadProjectId") is not None
        or normalized_baseline.get("cwd") != workspace
        or normalized_baseline.get("projectRoot") != workspace
        or normalized_baseline.get("environmentId") != challenge.get("environmentId")
        or normalized_baseline.get("nativeProjectId")
        != challenge.get("nativeProjectId")
        or not isinstance(thread_ids, list)
        or len(thread_ids) > MAX_BASELINE_THREAD_IDS
        or not all(
            isinstance(thread_id, str) and 0 < len(thread_id) <= 256
            for thread_id in thread_ids
        )
        or thread_ids != sorted(set(thread_ids))
        or sum(len(thread_id.encode("utf-8")) + 32 for thread_id in thread_ids)
        > MAX_BASELINE_THREAD_ARGUMENT_BYTES
        or not isinstance(proof_relative_path, str)
        or Path(proof_relative_path).is_absolute()
        or ".." in Path(proof_relative_path).parts
        or re.fullmatch(r"[0-9a-f]{32}", proof_nonce or "") is None
        or re.fullmatch(r"[0-9a-f]{32}", approval_nonce or "") is None
        or proof_nonce == approval_nonce
    ):
        raise SpikeError("the native thread verification challenge is malformed")

    expected_approval_command_sha256 = hashlib.sha256(
        approval_canary_command(approval_nonce).encode("utf-8")
    ).hexdigest()
    expected_proof_command_sha256 = hashlib.sha256(
        phone_proof_command(challenge).encode("utf-8")
    ).hexdigest()

    arguments = [
        "python3",
        "/opt/lift-spike/codex_project.py",
        "verify-thread",
        "--name",
        "lift",
        "--created-after",
        str(created_after),
        "--proof-relative-path",
        proof_relative_path,
        "--proof-nonce",
        proof_nonce,
        "--proof-command-sha256",
        expected_proof_command_sha256,
        "--approval-nonce",
        approval_nonce,
        "--approval-guard-sha256",
        approval_guard,
    ]
    for thread_id in thread_ids:
        arguments.extend(("--baseline-thread-id", thread_id))
    command = (
        "sudo -u lift env HOME=/home/lift "
        f"LIFT_WORKSPACE={shlex.quote(workspace)} "
        "PATH=/home/lift/.local/bin:/usr/local/bin:/usr/bin:/bin "
        + shlex.join(arguments)
    )
    raw = send_command(
        instance_id,
        ["set -euo pipefail", command],
        "Verify native Codex phone thread and approval",
        timeout_seconds=180,
    )
    evidence = parse_last_json(raw, "Codex thread verification")
    expected_keys = {
        "approvalGuardSha256",
        "approvalItemId",
        "approvalPolicy",
        "approvalVerificationMethod",
        "approvalsReviewer",
        "commandSha256",
        "controllerThreadBinding",
        "controllerThreadProjectId",
        "cwd",
        "environmentId",
        "nativeProjectId",
        "networkAccess",
        "projectRoot",
        "proofItemId",
        "runtimeWorkspaceRoots",
        "sandboxType",
        "threadId",
        "turnId",
        "verifiedAt",
    }
    command_hashes = evidence.get("commandSha256")
    identifier_keys = (
        "approvalItemId",
        "proofItemId",
        "threadId",
        "turnId",
    )
    if (
        set(evidence) != expected_keys
        or any(
            not isinstance(evidence.get(key), str) or not evidence.get(key)
            for key in identifier_keys
        )
        or evidence.get("approvalItemId") == evidence.get("proofItemId")
        or evidence.get("threadId") in thread_ids
        or evidence.get("controllerThreadBinding") != CONTROLLER_THREAD_BINDING
        or evidence.get("controllerThreadProjectId") is not None
        or evidence.get("cwd") != workspace
        or evidence.get("projectRoot") != workspace
        or evidence.get("runtimeWorkspaceRoots") != [workspace]
        or evidence.get("environmentId") != challenge.get("environmentId")
        or evidence.get("nativeProjectId") != challenge.get("nativeProjectId")
        or evidence.get("networkAccess") is not False
        or evidence.get("sandboxType") not in {"readOnly", "workspaceWrite"}
        or evidence.get("approvalsReviewer") != "user"
        or evidence.get("approvalPolicy") != "on-request"
        or evidence.get("approvalVerificationMethod")
        != THREAD_VERIFICATION_METHOD
        or evidence.get("approvalGuardSha256") != approval_guard
        or not isinstance(command_hashes, dict)
        or set(command_hashes) != {"approval", "proof"}
        or any(
            not isinstance(command_hashes.get(key), str)
            or SHA256_PATTERN.fullmatch(command_hashes[key]) is None
            for key in ("approval", "proof")
        )
        or command_hashes.get("approval") != expected_approval_command_sha256
        or command_hashes.get("proof") != expected_proof_command_sha256
        or isinstance(evidence.get("verifiedAt"), bool)
        or not isinstance(evidence.get("verifiedAt"), int)
        or evidence["verifiedAt"] < created_after
    ):
        raise SpikeError("Codex thread verification returned unbound evidence")
    approval_observation = managed_approval_observer_evidence(
        instance_id,
        workspace,
        challenge,
        evidence,
    )
    evidence["historicalVerificationMethod"] = evidence[
        "approvalVerificationMethod"
    ]
    evidence["approvalVerificationMethod"] = APPROVAL_VERIFICATION_METHOD
    evidence["approvalObservation"] = approval_observation
    return evidence


def phone_challenge_prompt(
    remote: dict[str, Any], challenge: dict[str, Any], *, restart: bool
) -> str:
    source = challenge.get("proofSource")
    proof_relative_path = challenge.get("proofRelativePath")
    approval_nonce = challenge.get("approvalNonce")
    if (
        source not in {"codex-phone", "codex-phone-post-restart"}
        or not isinstance(proof_relative_path, str)
        or re.fullmatch(r"[0-9a-f]{32}", approval_nonce or "") is None
    ):
        raise SpikeError("cannot render a malformed phone challenge")
    proof_command = phone_proof_command(challenge)
    approval_command = approval_canary_command(approval_nonce)
    context = "recovered " if restart else ""
    controller_visibility = remote.get("controllerProjectVisibility")
    if controller_visibility == {"status": "verified", "verified": True}:
        project_selection = f"open the {context}native project named lift"
    else:
        project_selection = (
            "choose Add new folder and select the exact folder "
            f"{REMOTE_WORKSPACE}; this one-time selection is required because "
            "controller-side project visibility has not been verified"
        )
    return (
        f"On {remote.get('serverName', 'the Lift cloud host')}, {project_selection}, "
        "then create a brand-new task; do not reuse an existing task. "
        "Do not modify any file except the proof path below. In two separate terminal "
        f"calls, first run exactly: {approval_command}. For that first call, request "
        "escalated permission and wait for me to approve it in the native phone app. "
        f"Only after it succeeds, run exactly: {proof_command}. Do not combine the two "
        "terminal calls or run any other terminal command in this task. Finish only after "
        "both commands complete successfully."
    )


def proof_bytes(challenge: dict[str, Any], source: str) -> bytes:
    if source in PHONE_PROOF_SOURCES:
        phone_challenge_sha256(challenge, expected_source=source)
    elif source == "codex-phone-laptop-off":
        laptop_off_challenge_sha256(challenge)
    else:
        raise SpikeError("the proof challenge source is unsupported")
    nonce = challenge["nonce"]
    expected_cwd = challenge["expectedCwd"]
    schema_version = challenge["schemaVersion"]
    proof = {
        "schemaVersion": schema_version,
        "nonce": nonce,
        "cwd": expected_cwd,
        "source": source,
    }
    proof["environmentId"] = challenge["environmentId"]
    proof["nativeProjectId"] = challenge["nativeProjectId"]
    proof["projectRoot"] = challenge["projectRoot"]
    return (
        json.dumps(
            proof,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def verify_workspace_json_proof(
    *,
    instance_id: str,
    workspace: str,
    challenge: dict[str, Any],
    source: str,
    description: str,
) -> dict[str, Any]:
    relative_path = challenge.get("proofRelativePath")
    if (
        not isinstance(relative_path, str)
        or source not in PROOF_RELATIVE_PATH_BY_SOURCE
        or relative_path != PROOF_RELATIVE_PATH_BY_SOURCE[source]
    ):
        raise SpikeError(f"the {description} proof path is unsafe")
    remote_code = """
import json
import os
import pwd
import stat
from pathlib import Path

workspace = Path(__WORKSPACE__)
relative = Path(__RELATIVE__)
if workspace.resolve(strict=True) != workspace:
    raise RuntimeError("workspace path is not physical")
expected_uid = pwd.getpwnam("lift").pw_uid
descriptors = []
try:
    current = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptors.append(current)
    root_metadata = os.fstat(current)
    if root_metadata.st_uid != expected_uid:
        raise RuntimeError("workspace owner changed")
    for component in relative.parts[:-1]:
        current = os.open(
            component,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=current,
        )
        descriptors.append(current)
        directory_metadata = os.fstat(current)
        if directory_metadata.st_uid != expected_uid:
            raise RuntimeError("proof ancestor owner changed")
    descriptor = os.open(
        relative.parts[-1],
        os.O_RDONLY | os.O_NOFOLLOW,
        dir_fd=current,
    )
    descriptors.append(descriptor)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != expected_uid:
        raise RuntimeError("proof is not a lift-owned regular file")
    chunks = []
    size = 0
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        size += len(chunk)
        if size > 65536:
            raise RuntimeError("proof exceeds size limit")
        chunks.append(chunk)
    data = b"".join(chunks)
finally:
    for descriptor in reversed(descriptors):
        os.close(descriptor)
print(json.dumps({
    "dataHex": data.hex(),
    "path": str(workspace / relative),
    "resolvedWorkspace": str(workspace.resolve(strict=True)),
}, separators=(",", ":"), sort_keys=True))
""".replace("__WORKSPACE__", repr(workspace)).replace(
        "__RELATIVE__", repr(relative_path)
    )
    raw = send_command(
        instance_id,
        [
            "set -euo pipefail",
            "python3 -c " + shlex.quote(remote_code),
        ],
        f"Verify {description} workspace proof",
        timeout_seconds=60,
    )
    try:
        observed = json.loads(raw.splitlines()[-1])
        proof = json.loads(bytes.fromhex(observed["dataHex"]))
    except (json.JSONDecodeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise SpikeError(f"{description} proof was not valid JSON") from exc
    expected = json.loads(proof_bytes(challenge, source))
    if (
        proof != expected
        or observed.get("path") != f"{workspace}/{relative_path}"
        or observed.get("resolvedWorkspace") != workspace
    ):
        raise SpikeError(f"{description} proof did not match the armed challenge")
    return proof


def current_mac_boot_time() -> datetime:
    completed = run(["sysctl", "-n", "kern.boottime"])
    match = re.search(r"sec = (\d+)", completed.stdout)
    if match is None:
        raise SpikeError("unable to parse the current Mac kernel boot time")
    return datetime.fromtimestamp(int(match.group(1)), UTC)


def verify_laptop_off_proof(
    *,
    state: dict[str, Any],
    instance_id: str,
    workspace: str,
    remote: dict[str, Any],
) -> dict[str, Any]:
    readiness = state.get("readiness", {})
    challenge = readiness.get("laptopOffChallenge")
    if not isinstance(challenge, dict):
        raise SpikeError("the laptop-off challenge is missing")
    if remote.get("environmentId") != challenge.get("environmentId"):
        raise SpikeError("the managed remote environment changed after laptop-off was armed")
    if remote.get("environmentId") != readiness.get("providerEnvironmentId"):
        raise SpikeError("the phone-verified Codex environment changed before laptop-off proof")

    relative_path = challenge.get("proofRelativePath")
    if relative_path != PROOF_RELATIVE_PATH_BY_SOURCE["codex-phone-laptop-off"]:
        raise SpikeError("the laptop-off proof path is unsafe")
    expected = proof_bytes(challenge, "codex-phone-laptop-off")
    expected_sha = hashlib.sha256(expected).hexdigest()
    expected_volume_id = state["runtime"]["outputs"]["WorkspaceVolumeId"]

    remote_code = """
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path

workspace = Path(__WORKSPACE__)
relative = Path(__RELATIVE__)
proof = workspace / relative
if workspace.resolve(strict=True) != workspace:
    raise RuntimeError("workspace path is not physical")
expected_uid = pwd.getpwnam("lift").pw_uid
descriptors = []
try:
    current = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptors.append(current)
    workspace_metadata = os.fstat(current)
    parent_metadata = workspace_metadata
    if workspace_metadata.st_uid != expected_uid:
        raise RuntimeError("workspace owner changed")
    for component in relative.parts[:-1]:
        current = os.open(
            component,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=current,
        )
        descriptors.append(current)
        parent_metadata = os.fstat(current)
        if parent_metadata.st_uid != expected_uid:
            raise RuntimeError("proof ancestor owner changed")
    descriptor = os.open(
        relative.parts[-1],
        os.O_RDONLY | os.O_NOFOLLOW,
        dir_fd=current,
    )
    descriptors.append(descriptor)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != expected_uid:
        raise RuntimeError("proof is not a lift-owned regular file")
    chunks = []
    size = 0
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        size += len(chunk)
        if size > 65536:
            raise RuntimeError("proof exceeds size limit")
        chunks.append(chunk)
    data = b"".join(chunks)
finally:
    for descriptor in reversed(descriptors):
        os.close(descriptor)
workspace_device = subprocess.run(
    ["findmnt", "-n", "-o", "MAJ:MIN", "-T", str(workspace)],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
root_device = subprocess.run(
    ["findmnt", "-n", "-o", "MAJ:MIN", "-T", "/"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
serial = subprocess.run(
    ["lsblk", "-ndo", "SERIAL", f"/dev/block/{workspace_device}"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if re.fullmatch(r"vol[0-9a-f]{8,17}", serial):
    serial = f"vol-{serial[3:]}"
print(json.dumps({
    "ctimeNs": metadata.st_ctime_ns,
    "dataHex": data.hex(),
    "isRegular": stat.S_ISREG(metadata.st_mode),
    "isSymlink": stat.S_ISLNK(metadata.st_mode),
    "mode": stat.S_IMODE(metadata.st_mode),
    "mtimeNs": metadata.st_mtime_ns,
    "owner": pwd.getpwuid(metadata.st_uid).pw_name,
    "parentOwner": pwd.getpwuid(parent_metadata.st_uid).pw_name,
    "path": str(proof),
    "resolvedWorkspace": str(workspace.resolve(strict=True)),
    "rootDevice": root_device,
    "sha256": hashlib.sha256(data).hexdigest(),
    "size": len(data),
    "sameDeviceAsWorkspace": metadata.st_dev == workspace_metadata.st_dev,
    "worldWritable": bool(stat.S_IMODE(metadata.st_mode) & stat.S_IWOTH),
    "workspaceDevice": workspace_device,
    "workspaceVolumeId": serial,
}, separators=(",", ":"), sort_keys=True))
""".replace("__WORKSPACE__", repr(workspace)).replace(
        "__RELATIVE__", repr(relative_path)
    )
    raw = send_command(
        instance_id,
        ["set -euo pipefail", "python3 -c " + shlex.quote(remote_code)],
        "Verify laptop-off workspace proof",
        timeout_seconds=60,
    )
    try:
        observed = json.loads(raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SpikeError("laptop-off proof evidence was not valid JSON") from exc
    if not isinstance(observed, dict):
        raise SpikeError("laptop-off proof evidence was not an object")

    try:
        issued_at = datetime.fromisoformat(challenge["issuedAt"])
        proof_mtime = datetime.fromtimestamp(observed["mtimeNs"] / 1_000_000_000, UTC)
        proof_ctime = datetime.fromtimestamp(observed["ctimeNs"] / 1_000_000_000, UTC)
        observed_bytes = bytes.fromhex(observed["dataHex"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SpikeError("laptop-off proof metadata was malformed") from exc
    mac_boot = current_mac_boot_time()
    expected_path = f"{workspace}/{relative_path}"
    checks = {
        "bytesExact": observed_bytes == expected,
        "ctimeAfterChallenge": proof_ctime >= issued_at,
        "ctimeBeforeCurrentMacBoot": proof_ctime < mac_boot,
        "environmentExact": remote.get("environmentId") == challenge.get("environmentId"),
        "mtimeAfterChallenge": proof_mtime >= issued_at,
        "mtimeBeforeCurrentMacBoot": proof_mtime < mac_boot,
        "ownerExact": observed.get("owner") == "lift",
        "parentOwnerExact": observed.get("parentOwner") == "lift",
        "pathExact": observed.get("path") == expected_path,
        "regularNotSymlink": observed.get("isRegular") is True
        and observed.get("isSymlink") is False,
        "sha256Exact": observed.get("sha256") == expected_sha,
        "sizeExact": observed.get("size") == len(expected),
        "sameDeviceAsWorkspace": observed.get("sameDeviceAsWorkspace") is True,
        "notWorldWritable": observed.get("worldWritable") is False,
        "workspacePathExact": observed.get("resolvedWorkspace") == workspace,
        "workspaceSeparateFromRoot": observed.get("workspaceDevice")
        != observed.get("rootDevice"),
        "workspaceVolumeExact": observed.get("workspaceVolumeId")
        == expected_volume_id,
    }
    clock_raw = send_command(
        instance_id,
        [
            "set -euo pipefail",
            "test \"$(timedatectl show --value -p NTPSynchronized)\" = yes",
            "printf '%s' synchronized",
        ],
        "Verify EC2 clock synchronization",
        timeout_seconds=60,
    )
    checks["ec2ClockSynchronized"] = clock_raw.splitlines()[-1] == "synchronized"
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise SpikeError("laptop-off proof verification failed: " + ", ".join(failed))
    return {
        "challengeIssuedAt": challenge["issuedAt"],
        "environmentId": remote["environmentId"],
        "fileCtime": proof_ctime.isoformat(),
        "fileMtime": proof_mtime.isoformat(),
        "fileMode": oct(observed["mode"]),
        "fileOwner": observed["owner"],
        "fileSha256": observed["sha256"],
        "fileSize": observed["size"],
        "macBootAt": mac_boot.isoformat(),
        "proofPath": expected_path,
        "verifiedAt": now_iso(),
        "workspaceVolumeId": expected_volume_id,
    }


def cmd_readiness(args: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    outputs = validated_stack_context(state)
    workspace = state.get("workspace", {})
    cloud_path = workspace.get("cloudPath")
    if not outputs or cloud_path != REMOTE_WORKSPACE:
        raise SpikeError("the verified cloud workspace must exist first")

    runner = managed_runner_status(outputs["InstanceId"])
    health = runner.get("health")
    if (
        runner.get("active") is not True
        or runner.get("healthy") is not True
        or runner.get("ready") is not True
        or not isinstance(health, dict)
        or health.get("fresh") is not True
        or health.get("healthy") is not True
        or health.get("ready") is not True
    ):
        raise SpikeError("the provider-neutral workload is not freshly ready")
    remote = managed_remote_status(outputs["InstanceId"], cloud_path)
    if args.action == "arm-restart":
        restart_evidence = state.get("readiness", {}).get("restartEvidence")
        if (
            not isinstance(restart_evidence, dict)
            or restart_evidence.get("runnerHealthy") is not True
            or restart_evidence.get("environmentPreserved") is not True
            or remote.get("environmentId") != restart_evidence.get("environmentIdAfter")
        ):
            raise SpikeError("verified restart recovery must pass before phone confirmation")
        baseline = managed_thread_baseline(outputs["InstanceId"], cloud_path)
        if (
            baseline.get("environmentId") != remote.get("environmentId")
            or baseline.get("nativeProjectId") != remote.get("nativeProjectId")
            or baseline.get("projectRoot") != remote.get("projectRoot")
        ):
            raise SpikeError("the native thread baseline changed provider binding")
        nonce = secrets.token_hex(16)
        approval_nonce = secrets.token_hex(16)
        proof_relative = ".lift/post-restart-proof.json"
        challenge = {
            "schemaVersion": 3,
            "nonce": nonce,
            "approvalNonce": approval_nonce,
            "issuedAt": now_iso(),
            "environmentId": remote["environmentId"],
            "nativeProjectId": remote["nativeProjectId"],
            "projectRoot": remote["projectRoot"],
            "expectedCwd": cloud_path,
            "proofRelativePath": proof_relative,
            "proofSource": "codex-phone-post-restart",
            "checkpointLabel": "post-restart-phone-proof",
            "threadBaseline": baseline,
        }
        challenge_sha = phone_challenge_sha256(
            challenge, expected_source="codex-phone-post-restart"
        )
        previous_challenge_sha = state.get("readiness", {}).get(
            "activeChallengeSha256"
        )
        if not isinstance(previous_challenge_sha, str) or (
            SHA256_PATTERN.fullmatch(previous_challenge_sha) is None
        ):
            previous_challenge_sha = None
        observer_ready = managed_approval_observer_arm(
            outputs["InstanceId"],
            cloud_path,
            challenge,
            previous_challenge_sha256=previous_challenge_sha,
        )
        invalidate_safe_to_close(
            state, reset_phone_probe=True, reset_workload=False
        )
        state["readiness"]["workloadHealthy"] = True
        state["readiness"]["serverProjectRegistered"] = remote[
            "serverProjectRegistered"
        ]
        state["readiness"]["controllerProjectVisibility"] = remote[
            "controllerProjectVisibility"
        ]
        state["readiness"]["challenge"] = challenge
        state["readiness"]["activeChallengeSha256"] = challenge_sha
        state["readiness"]["postRestartChallenge"] = json.loads(
            json.dumps(challenge)
        )
        state["readiness"]["approvalObserverArm"] = observer_ready
        state["readiness"]["postRestartPhoneVerified"] = False
        state["connection"]["state"] = "RESTART_RECOVERED_AWAITING_PHONE_PROOF"
        state["revision"] += 1
        try:
            atomic_state(state)
        except Exception:
            try:
                stop_managed_approval_observer(outputs["InstanceId"], challenge_sha)
            except Exception:
                pass
            raise
        record_event(
            "readiness.post_restart_phone_probe_armed",
            environmentId=remote["environmentId"],
            proofRelativePath=proof_relative,
        )
        print(
            json.dumps(
                {
                    "environmentId": remote["environmentId"],
                    "expectedCwd": cloud_path,
                    "nativeProjectId": remote["nativeProjectId"],
                    "serverProjectRegistered": remote[
                        "serverProjectRegistered"
                    ],
                    "controllerProjectVisibility": remote[
                        "controllerProjectVisibility"
                    ],
                    "approvalObserverReady": True,
                    "phonePrompt": phone_challenge_prompt(
                        remote, challenge, restart=True
                    ),
                    "safeToClose": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.action == "verify-restart":
        if state.get("connection", {}).get("state") != (
            "RESTART_RECOVERED_AWAITING_PHONE_PROOF"
        ):
            raise SpikeError("the post-restart phone probe is not the active transition")
        challenge, challenge_sha = active_phone_challenge(
            state.get("readiness", {}),
            expected_source="codex-phone-post-restart",
            require_post_restart_alias=True,
        )
        if remote.get("environmentId") != challenge.get("environmentId"):
            raise SpikeError("the Codex environment changed after restart proof was armed")
        if remote.get("nativeProjectId") != challenge.get("nativeProjectId"):
            raise SpikeError("the native Codex project changed after restart proof was armed")
        if remote.get("projectRoot") != challenge.get("projectRoot"):
            raise SpikeError("the native Codex project root changed after restart proof was armed")
        proof = verify_workspace_json_proof(
            instance_id=outputs["InstanceId"],
            workspace=cloud_path,
            challenge=challenge,
            source="codex-phone-post-restart",
            description="post-restart phone",
        )
        thread = managed_thread_verification(
            outputs["InstanceId"], cloud_path, challenge
        )
        state["readiness"]["postRestartPhoneVerified"] = True
        state["readiness"]["providerPhoneProbeVerified"] = True
        state["readiness"]["observedCwd"] = proof["cwd"]
        state["readiness"]["providerEnvironmentId"] = remote["environmentId"]
        state["readiness"]["serverProjectRegistered"] = True
        state["readiness"]["controllerProjectVisibility"] = {
            "status": "folder-bound-project-unassigned",
            "verified": False,
        }
        state["readiness"]["nativeProjectId"] = remote["nativeProjectId"]
        state["readiness"]["workloadHealthy"] = True
        state["readiness"]["phoneThreadEvidence"] = {
            **thread,
            "challengeSha256": challenge_sha,
            "proofSha256": hashlib.sha256(
                proof_bytes(challenge, "codex-phone-post-restart")
            ).hexdigest(),
        }
        state["readiness"]["approvalRoundTripVerified"] = True
        state["readiness"]["approvalEvidence"] = {
            "approvalObservation": thread["approvalObservation"],
            "approvalGuardSha256": thread["approvalGuardSha256"],
            "controllerThreadBinding": thread["controllerThreadBinding"],
            "controllerThreadProjectId": thread["controllerThreadProjectId"],
            "approvalVerificationMethod": thread["approvalVerificationMethod"],
            "historicalVerificationMethod": thread[
                "historicalVerificationMethod"
            ],
            "verifiedAt": thread["verifiedAt"],
            "environmentId": thread["environmentId"],
            "nativeProjectId": thread["nativeProjectId"],
            "projectRoot": thread["projectRoot"],
            "runtimeWorkspaceRoots": thread["runtimeWorkspaceRoots"],
            "threadId": thread["threadId"],
            "turnId": thread["turnId"],
            "itemId": thread["approvalItemId"],
            "proofItemId": thread["proofItemId"],
            "commandSha256": thread["commandSha256"]["approval"],
            "proofCommandSha256": thread["commandSha256"]["proof"],
            "sandboxType": thread["sandboxType"],
            "networkAccess": thread["networkAccess"],
            "approvalPolicy": thread["approvalPolicy"],
            "approvalsReviewer": thread["approvalsReviewer"],
            "challengeSha256": challenge_sha,
        }
        state["workspace"]["lease"] = "CLOUD_PRIMARY"
        state["connection"]["state"] = (
            "POST_RESTART_PHONE_AND_APPROVAL_VERIFIED_AWAITING_CHECKPOINT"
        )
        state["revision"] += 1
        atomic_state(state)
        record_event(
            "readiness.post_restart_phone_probe_verified",
            environmentId=remote["environmentId"],
            nativeProjectId=remote["nativeProjectId"],
            observedCwd=proof["cwd"],
            threadId=thread["threadId"],
            approvalItemId=thread["approvalItemId"],
        )
        print(
            json.dumps(
                {
                    "environmentId": remote["environmentId"],
                    "nativeProjectId": remote["nativeProjectId"],
                    "observedCwd": proof["cwd"],
                    "postRestartPhoneVerified": True,
                    "approvalRoundTripVerified": True,
                    "threadId": thread["threadId"],
                    "safeToClose": False,
                    "remainingGate": "following durable recovery checkpoint",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.action == "arm-offline":
        auto_stop_remaining_seconds = managed_auto_stop_remaining_seconds(
            outputs["InstanceId"]
        )
        if (
            state.get("readiness", {}).get("safeToClose") is not True
            or not live_safe_to_close(
                state, runner, remote, auto_stop_remaining_seconds
            )
        ):
            raise SpikeError("all safe-to-close gates must pass before arming laptop-off proof")
        nonce = secrets.token_hex(16)
        proof_relative = ".lift/laptop-off-proof.json"
        challenge = {
            "schemaVersion": 3,
            "nonce": nonce,
            "issuedAt": now_iso(),
            "environmentId": remote["environmentId"],
            "nativeProjectId": remote["nativeProjectId"],
            "projectRoot": remote["projectRoot"],
            "expectedCwd": cloud_path,
            "proofRelativePath": proof_relative,
            "proofSource": "codex-phone-laptop-off",
            "checkpointLabel": "laptop-off-proof",
        }
        challenge_sha = laptop_off_challenge_sha256(challenge)
        state["readiness"]["laptopOffChallenge"] = challenge
        state["readiness"]["laptopOffChallengeSha256"] = challenge_sha
        state["readiness"]["laptopOffProven"] = False
        state["readiness"].pop("laptopOffEvidence", None)
        state["connection"]["state"] = "READY_AWAITING_LAPTOP_OFF_PROOF"
        state["revision"] += 1
        atomic_state(state)
        record_event(
            "readiness.laptop_off_probe_armed",
            environmentId=remote["environmentId"],
            proofRelativePath=proof_relative,
        )
        proof = proof_bytes(challenge, "codex-phone-laptop-off").decode("utf-8").rstrip("\n")
        phone_prompt = (
            f"After this Mac is fully shut down, connect from the Codex phone app to "
            f"{remote.get('serverName', 'the Lift cloud host')}. In {cloud_path}, do not "
            f"modify any other file. Create {proof_relative} with these exact bytes and a "
            f"final newline: {proof}"
        )
        print(
            json.dumps(
                {
                    "environmentId": remote["environmentId"],
                    "expectedCwd": cloud_path,
                    "phonePrompt": phone_prompt,
                    "safeToClose": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.action == "arm":
        baseline = managed_thread_baseline(outputs["InstanceId"], cloud_path)
        if (
            baseline.get("environmentId") != remote.get("environmentId")
            or baseline.get("nativeProjectId") != remote.get("nativeProjectId")
            or baseline.get("projectRoot") != remote.get("projectRoot")
        ):
            raise SpikeError("the native thread baseline changed provider binding")
        nonce = secrets.token_hex(16)
        approval_nonce = secrets.token_hex(16)
        proof_relative = ".lift/phone-proof.json"
        challenge = {
            "schemaVersion": 3,
            "nonce": nonce,
            "approvalNonce": approval_nonce,
            "issuedAt": now_iso(),
            "environmentId": remote["environmentId"],
            "nativeProjectId": remote["nativeProjectId"],
            "projectRoot": remote["projectRoot"],
            "expectedCwd": cloud_path,
            "proofRelativePath": proof_relative,
            "proofSource": "codex-phone",
            "checkpointLabel": "phone-proof",
            "threadBaseline": baseline,
        }
        challenge_sha = phone_challenge_sha256(
            challenge, expected_source="codex-phone"
        )
        previous_challenge_sha = state.get("readiness", {}).get(
            "activeChallengeSha256"
        )
        if not isinstance(previous_challenge_sha, str) or (
            SHA256_PATTERN.fullmatch(previous_challenge_sha) is None
        ):
            previous_challenge_sha = None
        observer_ready = managed_approval_observer_arm(
            outputs["InstanceId"],
            cloud_path,
            challenge,
            previous_challenge_sha256=previous_challenge_sha,
        )
        invalidate_safe_to_close(
            state, reset_phone_probe=True, reset_workload=False
        )
        state["readiness"]["challenge"] = challenge
        state["readiness"]["activeChallengeSha256"] = challenge_sha
        state["readiness"]["approvalObserverArm"] = observer_ready
        state["readiness"].pop("postRestartChallenge", None)
        state["readiness"]["workloadHealthy"] = True
        state["readiness"]["serverProjectRegistered"] = remote[
            "serverProjectRegistered"
        ]
        state["readiness"]["controllerProjectVisibility"] = remote[
            "controllerProjectVisibility"
        ]
        state["connection"]["state"] = "PAIRED_AWAITING_PHONE_PROBE"
        state["revision"] += 1
        try:
            atomic_state(state)
        except Exception:
            try:
                stop_managed_approval_observer(outputs["InstanceId"], challenge_sha)
            except Exception:
                pass
            raise
        record_event(
            "readiness.phone_probe_armed",
            environmentId=remote["environmentId"],
            proofRelativePath=proof_relative,
        )
        print(
            json.dumps(
                {
                    "environmentId": remote["environmentId"],
                    "expectedCwd": cloud_path,
                    "nativeProjectId": remote["nativeProjectId"],
                    "serverProjectRegistered": remote[
                        "serverProjectRegistered"
                    ],
                    "controllerProjectVisibility": remote[
                        "controllerProjectVisibility"
                    ],
                    "approvalObserverReady": True,
                    "phonePrompt": phone_challenge_prompt(
                        remote, challenge, restart=False
                    ),
                    "safeToClose": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.action == "verify-offline":
        laptop_challenge = state.get("readiness", {}).get("laptopOffChallenge")
        if (
            laptop_off_challenge_sha256(laptop_challenge)
            != state.get("readiness", {}).get("laptopOffChallengeSha256")
        ):
            raise SpikeError("the active laptop-off challenge identity changed")
        evidence = verify_laptop_off_proof(
            state=state,
            instance_id=outputs["InstanceId"],
            workspace=cloud_path,
            remote=remote,
        )
        invalidate_safe_to_close(state, reset_phone_probe=False, reset_workload=False)
        state["readiness"]["laptopOffProven"] = True
        state["readiness"]["laptopOffEvidence"] = evidence
        state["readiness"]["providerEnvironmentId"] = remote["environmentId"]
        state["readiness"]["workloadHealthy"] = True
        state["workspace"]["lease"] = "CLOUD_PRIMARY"
        state["connection"]["state"] = "LAPTOP_OFF_PROVEN_AWAITING_CHECKPOINT"
        state["revision"] += 1
        atomic_state(state)
        record_event(
            "readiness.laptop_off_probe_verified",
            environmentId=remote["environmentId"],
            proofSha256=evidence["fileSha256"],
            proofMtime=evidence["fileMtime"],
            macBootAt=evidence["macBootAt"],
        )
        print(
            json.dumps(
                {
                    "environmentId": remote["environmentId"],
                    "laptopOffProven": True,
                    "proofTimeline": {
                        "challengeIssuedAt": evidence["challengeIssuedAt"],
                        "proofFileMtime": evidence["fileMtime"],
                        "currentMacBootAt": evidence["macBootAt"],
                    },
                    "safeToClose": False,
                    "remainingGate": "durable laptop-off recovery checkpoint",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if state.get("connection", {}).get("state") != "PAIRED_AWAITING_PHONE_PROBE":
        raise SpikeError("the normal phone probe is not the active transition")
    challenge, challenge_sha = active_phone_challenge(
        state.get("readiness", {}), expected_source="codex-phone"
    )
    if remote.get("environmentId") != challenge.get("environmentId"):
        raise SpikeError("the managed remote environment changed after the phone probe was armed")
    if remote.get("nativeProjectId") != challenge.get("nativeProjectId"):
        raise SpikeError("the native Codex project changed after the phone probe was armed")
    if remote.get("projectRoot") != challenge.get("projectRoot"):
        raise SpikeError("the native Codex project root changed after the phone probe was armed")
    proof = verify_workspace_json_proof(
        instance_id=outputs["InstanceId"],
        workspace=cloud_path,
        challenge=challenge,
        source="codex-phone",
        description="phone",
    )
    thread = managed_thread_verification(
        outputs["InstanceId"], cloud_path, challenge
    )

    state["readiness"]["providerPhoneProbeVerified"] = True
    state["readiness"]["observedCwd"] = proof["cwd"]
    state["readiness"]["providerEnvironmentId"] = remote["environmentId"]
    state["readiness"]["serverProjectRegistered"] = True
    state["readiness"]["controllerProjectVisibility"] = {
        "status": "folder-bound-project-unassigned",
        "verified": False,
    }
    state["readiness"]["nativeProjectId"] = remote["nativeProjectId"]
    state["readiness"]["workloadHealthy"] = True
    state["readiness"]["phoneThreadEvidence"] = {
        **thread,
        "challengeSha256": challenge_sha,
        "proofSha256": hashlib.sha256(
            proof_bytes(challenge, "codex-phone")
        ).hexdigest(),
    }
    state["readiness"]["approvalRoundTripVerified"] = True
    state["readiness"]["approvalEvidence"] = {
        "approvalObservation": thread["approvalObservation"],
        "approvalGuardSha256": thread["approvalGuardSha256"],
        "controllerThreadBinding": thread["controllerThreadBinding"],
        "controllerThreadProjectId": thread["controllerThreadProjectId"],
        "approvalVerificationMethod": thread["approvalVerificationMethod"],
        "historicalVerificationMethod": thread["historicalVerificationMethod"],
        "verifiedAt": thread["verifiedAt"],
        "environmentId": thread["environmentId"],
        "nativeProjectId": thread["nativeProjectId"],
        "projectRoot": thread["projectRoot"],
        "runtimeWorkspaceRoots": thread["runtimeWorkspaceRoots"],
        "threadId": thread["threadId"],
        "turnId": thread["turnId"],
        "itemId": thread["approvalItemId"],
        "proofItemId": thread["proofItemId"],
        "commandSha256": thread["commandSha256"]["approval"],
        "proofCommandSha256": thread["commandSha256"]["proof"],
        "sandboxType": thread["sandboxType"],
        "networkAccess": thread["networkAccess"],
        "approvalPolicy": thread["approvalPolicy"],
        "approvalsReviewer": thread["approvalsReviewer"],
        "challengeSha256": challenge_sha,
    }
    state["workspace"]["lease"] = "CLOUD_PRIMARY"
    state["connection"]["state"] = (
        "PHONE_AND_APPROVAL_VERIFIED_AWAITING_CHECKPOINT"
    )
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "readiness.phone_probe_verified",
        environmentId=remote["environmentId"],
        observedCwd=proof["cwd"],
        threadId=thread["threadId"],
        approvalItemId=thread["approvalItemId"],
    )
    print(
        json.dumps(
            {
                "environmentId": remote["environmentId"],
                "observedCwd": proof["cwd"],
                "phoneProbeVerified": True,
                "approvalRoundTripVerified": True,
                "threadId": thread["threadId"],
                "safeToClose": False,
                "remainingGate": "following durable recovery checkpoint",
            },
            indent=2,
            sort_keys=True,
        )
    )


def ensure_instance_online(instance_id: str) -> None:
    if INSTANCE_ID_PATTERN.fullmatch(instance_id) is None:
        raise SpikeError("cannot start an invalid EC2 instance identity")
    response = aws_json("ec2", "describe-instances", "--instance-ids", instance_id)
    reservations = response.get("Reservations", [])
    instances = [
        instance
        for reservation in reservations
        if isinstance(reservation, dict)
        for instance in reservation.get("Instances", [])
        if isinstance(instance, dict)
    ]
    if len(instances) != 1 or instances[0].get("InstanceId") != instance_id:
        raise SpikeError("EC2 did not return the exact Lift instance")
    state_name = instances[0].get("State", {}).get("Name")
    if state_name == "stopping":
        aws_raw(
            "ec2", "wait", "instance-stopped", "--instance-ids", instance_id,
            timeout=900,
        )
        state_name = "stopped"
    if state_name == "stopped":
        aws_json("ec2", "start-instances", "--instance-ids", instance_id)
        aws_raw(
            "ec2", "wait", "instance-running", "--instance-ids", instance_id,
            timeout=600,
        )
        aws_raw(
            "ec2", "wait", "instance-status-ok", "--instance-ids", instance_id,
            timeout=900,
        )
    elif state_name == "pending":
        aws_raw(
            "ec2", "wait", "instance-running", "--instance-ids", instance_id,
            timeout=600,
        )
        aws_raw(
            "ec2", "wait", "instance-status-ok", "--instance-ids", instance_id,
            timeout=900,
        )
    elif state_name != "running":
        raise SpikeError(f"Lift EC2 instance cannot Land from state {state_name!r}")
    wait_for_ssm(instance_id)


def _checkpoint_ref_map(
    value: Any, *, prefix: str, description: str
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise SpikeError(f"guest checkpoint returned invalid {description}")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not item["ref"].startswith(prefix)
            or not valid_git_object_id(item.get("objectId"))
            or item["ref"] in seen
        ):
            raise SpikeError(f"guest checkpoint returned invalid {description}")
        seen.add(item["ref"])
        result.append({"ref": item["ref"], "objectId": item["objectId"]})
    return result


def validate_land_guest_checkpoint(
    *,
    state: dict[str, Any],
    outputs: dict[str, str],
    checkpoint: Any,
) -> dict[str, Any]:
    if not isinstance(checkpoint, dict):
        raise SpikeError("guest Land checkpoint returned a non-object")
    workspace = state["workspace"]
    land_state = workspace["land"]
    run_id = state["runId"]
    ordinal = land_state["ordinal"]
    prefix = f"refs/lift/{WORKSPACE_ID}/sessions/{run_id}"
    expected_ref = f"{prefix}/checkpoints/{ordinal:04d}-land-final"
    all_checkpoints = workspace.get("checkpoints", [])
    if (
        not isinstance(all_checkpoints, list)
        or any(not isinstance(item, dict) for item in all_checkpoints)
        or [item.get("ordinal") for item in all_checkpoints]
        != list(range(1, len(all_checkpoints) + 1))
        or any(item.get("ordinal", 0) > ordinal for item in all_checkpoints)
    ):
        raise SpikeError("Land final checkpoint ordinal is not the next immutable slot")
    prior_checkpoints = [
        item for item in all_checkpoints if item.get("ordinal", 0) < ordinal
    ]
    existing_final = next(
        (item for item in all_checkpoints if item.get("ordinal") == ordinal), None
    )
    if ordinal != len(prior_checkpoints) + 1 or (
        existing_final is not None and existing_final.get("label") != "land-final"
    ):
        raise SpikeError("Land final checkpoint ordinal is not the next immutable slot")
    expected_parent_ref = (
        prior_checkpoints[-1]["ref"]
        if prior_checkpoints
        else workspace["baselineRef"]
    )
    expected_parent_commit = (
        prior_checkpoints[-1]["commit"]
        if prior_checkpoints
        else workspace["baselineCommit"]
    )
    required_sha_fields = (
        "bundleSha256",
        "manifestSha256",
        "manifestFileSha256",
        "gitSnapshotSha256",
    )
    if any(
        not isinstance(checkpoint.get(key), str)
        or SHA256_PATTERN.fullmatch(checkpoint[key]) is None
        for key in required_sha_fields
    ):
        raise SpikeError("guest Land checkpoint returned invalid SHA-256 identities")
    if any(
        not valid_git_object_id(checkpoint.get(key))
        for key in ("commit", "tree", "cloudHead")
    ):
        raise SpikeError("guest Land checkpoint returned invalid Git identities")
    if (
        isinstance(checkpoint.get("bundleSize"), bool)
        or not isinstance(checkpoint.get("bundleSize"), int)
        or checkpoint["bundleSize"] <= 0
        or isinstance(checkpoint.get("manifestSize"), bool)
        or not isinstance(checkpoint.get("manifestSize"), int)
        or checkpoint["manifestSize"] <= 0
        or isinstance(checkpoint.get("fileCount"), bool)
        or not isinstance(checkpoint.get("fileCount"), int)
        or checkpoint["fileCount"] < 0
    ):
        raise SpikeError("guest Land checkpoint returned invalid recovery object sizes")
    parents = checkpoint.get("parents")
    if (
        not isinstance(parents, list)
        or len(parents) not in {1, 2}
        or parents[0] != expected_parent_commit
        or any(not valid_git_object_id(parent) for parent in parents)
        or (
            len(parents) == 2
            and (
                parents[1] != checkpoint["cloudHead"]
                or parents[1] == expected_parent_commit
            )
        )
    ):
        raise SpikeError(
            "guest Land checkpoint is not chained from the last durable checkpoint"
        )
    history_refs = _checkpoint_ref_map(
        checkpoint.get("historyRefs"),
        prefix=f"{prefix}/git-history/{ordinal:04d}/",
        description="current cloud Git history",
    )
    recovery_history_refs = _checkpoint_ref_map(
        checkpoint.get("recoveryHistoryRefs"),
        prefix=f"{prefix}/git-history/",
        description="complete cloud Git recovery history",
    )
    recovery_checkpoint_refs = _checkpoint_ref_map(
        checkpoint.get("recoveryCheckpointRefs"),
        prefix=f"{prefix}/",
        description="complete checkpoint recovery history",
    )
    expected_recovery_checkpoints = [
        {"ref": workspace["baselineRef"], "objectId": workspace["baselineCommit"]},
        *[
            {"ref": item["ref"], "objectId": item["commit"]}
            for item in prior_checkpoints
        ],
        {"ref": expected_ref, "objectId": checkpoint["commit"]},
    ]
    if recovery_checkpoint_refs != expected_recovery_checkpoints:
        raise SpikeError("Land recovery bundle checkpoint map is not complete and exact")
    expected_recovery_history: list[dict[str, str]] = []
    seen_history: set[str] = set()
    for prior in prior_checkpoints:
        for item in prior.get("recoveryHistoryRefs", prior.get("historyRefs", [])):
            if item["ref"] not in seen_history:
                expected_recovery_history.append(
                    {"ref": item["ref"], "objectId": item["objectId"]}
                )
                seen_history.add(item["ref"])
    for item in history_refs:
        if item["ref"] not in seen_history:
            expected_recovery_history.append(item)
            seen_history.add(item["ref"])
    if recovery_history_refs != expected_recovery_history:
        raise SpikeError("Land recovery bundle Git history map is not complete and exact")

    expected = {
        "schemaVersion": 1,
        "ordinal": ordinal,
        "label": "land-final",
        "ref": expected_ref,
        "parentRef": expected_parent_ref,
        "parentCommit": expected_parent_commit,
        "bundlePath": (
            f"/var/lib/lift/ledger/checkpoints/{run_id}/"
            f"{checkpoint['bundleSha256']}.bundle"
        ),
        "manifestPath": (
            f"/var/lib/lift/ledger/checkpoints/{run_id}/"
            f"{ordinal:04d}-land-final-manifest.json"
        ),
        "workspaceVolumeId": outputs["WorkspaceVolumeId"],
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise SpikeError("guest Land checkpoint identity differs from the requested final C")
    try:
        policy = fixture_policy_for_commit(
            Path(workspace["ledgerPath"]), workspace["baselineCommit"]
        )
    except WorkspaceError as exc:
        raise SpikeError("local baseline fixture policy is invalid") from exc
    if checkpoint.get("fixturePolicy") != policy:
        raise SpikeError("guest Land checkpoint fixture policy differs from baseline")
    return {
        **checkpoint,
        "historyRefs": history_refs,
        "recoveryHistoryRefs": recovery_history_refs,
        "recoveryCheckpointRefs": recovery_checkpoint_refs,
    }


def verify_land_checkpoint_on_ebs(
    *, instance_id: str, run_id: str, checkpoint: dict[str, Any]
) -> None:
    ledger_path = f"/var/lib/lift/ledger/{run_id}.git"
    refs = [
        *checkpoint["recoveryCheckpointRefs"],
        *checkpoint["recoveryHistoryRefs"],
    ]
    commands = [
        "set -euo pipefail",
        f"test -f {shlex.quote(checkpoint['bundlePath'])}",
        f"test ! -L {shlex.quote(checkpoint['bundlePath'])}",
        f"test \"$(stat -c %a {shlex.quote(checkpoint['bundlePath'])})\" = 600",
        f"test -f {shlex.quote(checkpoint['manifestPath'])}",
        f"test ! -L {shlex.quote(checkpoint['manifestPath'])}",
        f"test \"$(stat -c %a {shlex.quote(checkpoint['manifestPath'])})\" = 600",
        (
            f"test \"$(sha256sum {shlex.quote(checkpoint['bundlePath'])} | cut -d ' ' -f 1)\" "
            f"= {shlex.quote(checkpoint['bundleSha256'])}"
        ),
        (
            f"test \"$(sha256sum {shlex.quote(checkpoint['manifestPath'])} | cut -d ' ' -f 1)\" "
            f"= {shlex.quote(checkpoint['manifestFileSha256'])}"
        ),
        *[
            (
                f"test \"$(git --git-dir={shlex.quote(ledger_path)} rev-parse "
                f"{shlex.quote(item['ref'])})\" = {shlex.quote(item['objectId'])}"
            )
            for item in refs
        ],
        (
            f"test \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(checkpoint['bundlePath'])})\" "
            f"= \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(REMOTE_WORKSPACE)})\""
        ),
        (
            f"test \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(checkpoint['manifestPath'])})\" "
            f"= \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(REMOTE_WORKSPACE)})\""
        ),
        (
            f"git --git-dir={shlex.quote(ledger_path)} bundle verify "
            f"{shlex.quote(checkpoint['bundlePath'])} >/dev/null 2>&1"
        ),
        "printf '%s' verified",
    ]
    verified = send_command(
        instance_id,
        commands,
        "Verify frozen final Land checkpoint on EBS",
        timeout_seconds=180,
    )
    if not verified.splitlines() or verified.splitlines()[-1] != "verified":
        raise SpikeError("frozen final Land checkpoint failed EBS verification")


def make_land_checkpoint_durable(
    *,
    state: dict[str, Any],
    outputs: dict[str, str],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    run_id = state["runId"]
    instance_id = outputs["InstanceId"]
    verify_land_checkpoint_on_ebs(
        instance_id=instance_id, run_id=run_id, checkpoint=checkpoint
    )
    bucket = outputs["TransferBucketName"]
    object_key = f"sessions/{run_id}/checkpoints/{checkpoint['bundleSha256']}.bundle"
    manifest_object_key = (
        f"sessions/{run_id}/checkpoints/"
        f"{checkpoint['manifestFileSha256']}.manifest.json"
    )
    existing = state["workspace"]["land"].get("finalCheckpoint", {})
    if existing and any(
        existing.get(key) != checkpoint.get(key)
        for key in (
            "ref",
            "commit",
            "tree",
            "bundleSha256",
            "manifestFileSha256",
        )
    ):
        raise SpikeError("saved final Land checkpoint differs from the frozen guest checkpoint")
    bundle_head = ensure_s3_recovery_object(
        instance_id=instance_id,
        bucket=bucket,
        key=object_key,
        remote_path=checkpoint["bundlePath"],
        sha256=checkpoint["bundleSha256"],
        size=checkpoint["bundleSize"],
        description="final Land Git recovery bundle",
        expected_version_id=existing.get("s3VersionId"),
    )
    manifest_head = ensure_s3_recovery_object(
        instance_id=instance_id,
        bucket=bucket,
        key=manifest_object_key,
        remote_path=checkpoint["manifestPath"],
        sha256=checkpoint["manifestFileSha256"],
        size=checkpoint["manifestSize"],
        description="final Land SHA-256 manifest",
        expected_version_id=existing.get("s3ManifestVersionId"),
    )
    versioning = aws_json("s3api", "get-bucket-versioning", "--bucket", bucket)
    if versioning.get("Status") != "Enabled":
        raise SpikeError("S3 recovery bucket versioning is not enabled")
    volume = aws_json(
        "ec2", "describe-volumes", "--volume-ids", outputs["WorkspaceVolumeId"]
    ).get("Volumes", [])
    if (
        len(volume) != 1
        or volume[0].get("Encrypted") is not True
        or volume[0].get("State") != "in-use"
        or not any(
            attachment.get("InstanceId") == instance_id
            and attachment.get("State") == "attached"
            for attachment in volume[0].get("Attachments", [])
        )
    ):
        raise SpikeError("final Land checkpoint EBS volume is not encrypted and attached")
    durable = {
        **checkpoint,
        "runId": run_id,
        "workspaceId": WORKSPACE_ID,
        "baselineRef": state["workspace"]["baselineRef"],
        "baselineCommit": state["workspace"]["baselineCommit"],
        "ebsBundlePath": checkpoint["bundlePath"],
        "s3Bucket": bucket,
        "s3ObjectKey": object_key,
        "s3VersionId": bundle_head["VersionId"],
        "s3ChecksumSHA256": base64.b64encode(
            bytes.fromhex(checkpoint["bundleSha256"])
        ).decode("ascii"),
        "s3ManifestObjectKey": manifest_object_key,
        "s3ManifestVersionId": manifest_head["VersionId"],
        "s3ManifestChecksumSHA256": base64.b64encode(
            bytes.fromhex(checkpoint["manifestFileSha256"])
        ).decode("ascii"),
    }
    restore = restore_test_checkpoint(
        run_id=run_id,
        workspace_id=WORKSPACE_ID,
        bucket=bucket,
        bundle=bundle_head,
        manifest_object=manifest_head,
        checkpoint=durable,
        expected_evidence={},
    )
    if not valid_restore_test(restore, durable):
        raise SpikeError("final Land checkpoint restore test returned invalid evidence")
    if existing:
        saved_restore = existing.get("restoreTest")
        if not valid_restore_test(saved_restore, existing):
            raise SpikeError("saved final Land restore evidence is invalid")
        if any(
            saved_restore.get(key) != restore.get(key)
            for key in RESTORE_TEST_KEYS
            if key != "verifiedAt"
        ):
            raise SpikeError("final Land restore evidence changed on retry")
        restore = saved_restore
    durable["restoreTest"] = restore
    return durable


def guest_landing_action(
    *,
    instance_id: str,
    run_id: str,
    volume_id: str,
    action: str,
    record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action not in {"freeze", "status", "record-checkpoint", "acknowledge"}:
        raise SpikeError("invalid guest Land lifecycle action")
    command = (
        "python3 /opt/lift-spike/landing.py "
        f"{shlex.quote(action)} "
        f"--run-id {shlex.quote(run_id)} "
        f"--workspace-id {shlex.quote(WORKSPACE_ID)} "
        f"--expected-volume-id {shlex.quote(volume_id)}"
    )
    commands = ["set -euo pipefail", "umask 077"]
    if record is not None:
        if action not in {"record-checkpoint", "acknowledge"}:
            raise SpikeError("guest Land record was supplied to an invalid action")
        encoded = base64.b64encode(
            (json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode(
                "utf-8"
            )
        ).decode("ascii")
        commands.extend(
            [
                'RECORD_DIR="/run/lift-spike-land"',
                'install -d -o root -g root -m 0700 "$RECORD_DIR"',
                'test ! -L "$RECORD_DIR"',
                (
                    'test "$(stat -c \'%a:%u:%g:%F\' -- "$RECORD_DIR")" '
                    '= "700:0:0:directory"'
                ),
                'RECORD=$(mktemp "$RECORD_DIR/record.XXXXXX")',
                "trap 'rm -f -- \"$RECORD\"' EXIT",
                f"printf '%s' {shlex.quote(encoded)} | base64 --decode > \"$RECORD\"",
                'chmod 0600 "$RECORD"',
                f'{command} --record "$RECORD"',
            ]
        )
    else:
        commands.append(command)
    raw = send_command(
        instance_id,
        commands,
        f"Lift Land lifecycle: {action}",
        timeout_seconds=300,
    )
    return parse_last_json(raw, f"guest Land {action}")


def guest_land_checkpoint(
    *, state: dict[str, Any], outputs: dict[str, str]
) -> dict[str, Any]:
    land_state = state["workspace"]["land"]
    raw = send_command(
        outputs["InstanceId"],
        [
            "set -euo pipefail",
            (
                "python3 /opt/lift-spike/checkpoint.py "
                f"--run-id {shlex.quote(state['runId'])} "
                f"--workspace-id {shlex.quote(WORKSPACE_ID)} "
                f"--ordinal {land_state['ordinal']} --label land-final "
                f"--expected-volume-id {shlex.quote(outputs['WorkspaceVolumeId'])} "
                "--land-final"
            ),
        ],
        "Seal immutable final Land checkpoint",
        timeout_seconds=300,
    )
    return validate_land_guest_checkpoint(
        state=state,
        outputs=outputs,
        checkpoint=parse_last_json(raw, "guest final Land checkpoint"),
    )


def guest_checkpoint_receipt(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "ordinal": checkpoint["ordinal"],
        "label": "land-final",
        "ref": checkpoint["ref"],
        "commit": checkpoint["commit"],
        "tree": checkpoint["tree"],
        "parents": checkpoint["parents"],
        "bundleSha256": checkpoint["bundleSha256"],
        "manifestSha256": checkpoint["manifestSha256"],
        "manifestFileSha256": checkpoint["manifestFileSha256"],
        "s3Bucket": checkpoint["s3Bucket"],
        "s3ObjectKey": checkpoint["s3ObjectKey"],
        "s3VersionId": checkpoint["s3VersionId"],
        "s3ManifestObjectKey": checkpoint["s3ManifestObjectKey"],
        "s3ManifestVersionId": checkpoint["s3ManifestVersionId"],
        "restoreTest": checkpoint["restoreTest"],
    }


def prepare_local_land_paths(state: dict[str, Any]) -> tuple[Path, Path, Path]:
    run_dir = LOCAL_ROOT / "runs" / state["runId"]
    workspace = Path(state["workspace"]["localPath"])
    ledger = Path(state["workspace"]["ledgerPath"])
    expected = {
        run_dir: "local Lift run directory",
        ledger: "local Lift-private ledger",
        workspace: "original local workspace",
    }
    for path, description in expected.items():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise SpikeError(f"cannot inspect {description}: {path}") from exc
        if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise SpikeError(f"{description} is not a physical directory")
        if path.resolve(strict=True) != path.absolute():
            raise SpikeError(f"{description} has a non-canonical path")
        if metadata.st_uid != os.geteuid():
            raise SpikeError(f"{description} is not owned by the current user")
    # Tighten the pre-Land spike's legacy 0755 private directories before C is
    # downloaded. This is safe because they are Lift-owned fixture paths.
    os.chmod(run_dir, 0o700)
    os.chmod(ledger, 0o700)
    land_root = run_dir / "land"
    land_root.mkdir(mode=0o700, exist_ok=True)
    if land_root.is_symlink() or not land_root.is_dir():
        raise SpikeError("local Land state root is unsafe")
    os.chmod(land_root, 0o700)
    return workspace, ledger, land_root


def validate_existing_local_land_paths(
    state: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Read-only validation for an already-persisted local Land operation."""

    run_dir = LOCAL_ROOT / "runs" / state["runId"]
    workspace = Path(state["workspace"]["localPath"])
    ledger = Path(state["workspace"]["ledgerPath"])
    land_root = run_dir / "land"
    expected = {
        run_dir: ("local Lift run directory", True),
        ledger: ("local Lift-private ledger", True),
        workspace: ("original local workspace", False),
        land_root: ("local Land state root", True),
    }
    for path, (description, private) in expected.items():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise SpikeError(f"cannot inspect {description}: {path}") from exc
        if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise SpikeError(f"{description} is not a physical directory")
        if path.resolve(strict=True) != path.absolute():
            raise SpikeError(f"{description} has a non-canonical path")
        if metadata.st_uid != os.geteuid():
            raise SpikeError(f"{description} is not owned by the current user")
        if private and stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE:
            raise SpikeError(f"{description} must have mode 0700")
    return workspace, ledger, land_root


def final_local_land_manifest(
    *,
    state: dict[str, Any],
    workspace: Path,
    ledger: Path,
    land_result: dict[str, Any],
    approved_ignored: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    merge_commit = land_result.get("mergeResultCommit")
    if not valid_git_object_id(merge_commit):
        raise SpikeError("applied Land result has no valid merge commit")
    merge_tree = run(
        [
            "git",
            f"--git-dir={ledger}",
            "show",
            "-s",
            "--format=%T",
            merge_commit,
        ]
    ).stdout.strip()
    if not valid_git_object_id(merge_tree):
        raise SpikeError("applied Land result has no valid merge tree")
    expected_entries = checkpoint_tree_entries(ledger, merge_tree)

    def observed_entries() -> list[dict[str, Any]]:
        try:
            observed = content_manifest(workspace, approved_ignored)
        except WorkspaceError as exc:
            raise SpikeError(
                "cannot verify the actual local workspace before acknowledgement"
            ) from exc
        raw_entries = observed.get("entries")
        if not isinstance(raw_entries, list):
            raise SpikeError("actual local workspace manifest is malformed")
        projected: list[dict[str, Any]] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise SpikeError("actual local workspace manifest is malformed")
            try:
                entry = {
                    key: raw[key]
                    for key in ("path", "type", "sha256", "size", "executable")
                }
            except KeyError as exc:
                raise SpikeError(
                    "actual local workspace manifest is malformed"
                ) from exc
            if entry["type"] == "symlink":
                entry["target"] = raw.get("target")
            projected.append(entry)
        return projected

    expected_content = [
        {
            key: entry[key]
            for key in ("path", "type", "sha256", "size", "executable")
        }
        | ({"target": entry["target"]} if entry["type"] == "symlink" else {})
        for entry in expected_entries
    ]
    first_observed = observed_entries()
    second_observed = observed_entries()
    if first_observed != second_observed or second_observed != expected_content:
        raise SpikeError(
            "actual local workspace changed after the verified Land apply"
        )

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "runId": state["runId"],
        "workspaceId": WORKSPACE_ID,
        "mergeResultRef": land_result["mergeResultRef"],
        "mergeResultCommit": merge_commit,
        "mergeResultTree": merge_tree,
        "entries": expected_entries,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    manifest_sha = hashlib.sha256(canonical).hexdigest()
    payload["manifestSha256"] = manifest_sha
    return payload, manifest_sha


def persist_land_progress(
    state: dict[str, Any], phase: str, event_type: str, **details: Any
) -> None:
    if phase not in LAND_PHASES:
        raise SpikeError("cannot persist an invalid Land phase")
    state["workspace"]["land"]["phase"] = phase
    state["revision"] += 1
    atomic_state(state)
    record_event(event_type, operationId=state["workspace"]["land"]["operationId"], **details)


def stop_compute_after_land(state: dict[str, Any], outputs: dict[str, str]) -> dict[str, Any]:
    verified = validated_stack_context(state)
    if verified != outputs:
        raise SpikeError("stack identity changed before Land compute cleanup")
    instance_id = outputs["InstanceId"]
    response = aws_json("ec2", "describe-instances", "--instance-ids", instance_id)
    instances = [
        instance
        for reservation in response.get("Reservations", [])
        if isinstance(reservation, dict)
        for instance in reservation.get("Instances", [])
        if isinstance(instance, dict)
    ]
    if len(instances) != 1 or instances[0].get("InstanceId") != instance_id:
        raise SpikeError("EC2 cleanup did not return the exact Lift instance")
    before = instances[0].get("State", {}).get("Name")
    if before == "running":
        aws_json("ec2", "stop-instances", "--instance-ids", instance_id)
        aws_raw(
            "ec2", "wait", "instance-stopped", "--instance-ids", instance_id,
            timeout=900,
        )
    elif before not in {"stopped", "stopping"}:
        raise SpikeError(f"cannot stop landed EC2 instance from state {before!r}")
    elif before == "stopping":
        aws_raw(
            "ec2", "wait", "instance-stopped", "--instance-ids", instance_id,
            timeout=900,
        )
    return {"instanceId": instance_id, "state": "stopped", "stoppedAt": now_iso()}


def finish_land_after_guest_ack(
    *,
    state: dict[str, Any],
    outputs: dict[str, str],
    guest_ack: dict[str, Any],
    keep_compute_running: bool,
) -> None:
    workspace_state = state["workspace"]
    land_state = workspace_state["land"]
    acknowledgement = land_state["acknowledgement"]
    if guest_ack.get("acknowledgement") != acknowledgement:
        raise SpikeError("guest acknowledgement differs from the durable local record")
    land_state["guestAcknowledgement"] = guest_ack
    workspace_state["lease"] = "LOCAL_PRIMARY"
    state["connection"]["state"] = "LANDED"
    state["readiness"]["safeToClose"] = False
    if land_state.get("phase") != "COMPLETE":
        persist_land_progress(
            state,
            "COMPLETE",
            "land.complete",
            acknowledgementSha256=acknowledgement["acknowledgementSha256"],
        )

    if keep_compute_running:
        cleanup: dict[str, Any] = {"state": "running", "requested": False}
        land_state["computeCleanup"] = cleanup
        state["revision"] += 1
        atomic_state(state)
        record_event("land.compute_retained", instanceId=outputs["InstanceId"])
    else:
        try:
            cleanup = stop_compute_after_land(state, outputs)
            state["runtime"]["state"] = "STOPPED"
            land_state["computeCleanup"] = cleanup
            state["revision"] += 1
            atomic_state(state)
            record_event("land.compute_stopped", instanceId=outputs["InstanceId"])
        except SpikeError as exc:
            cleanup = {"state": "pending", "error": str(exc)}
            land_state["computeCleanup"] = cleanup
            state["revision"] += 1
            atomic_state(state)
            record_event("land.compute_cleanup_pending", error=str(exc))

    final_checkpoint = land_state["finalCheckpoint"]
    land_result = land_state["result"]
    print(
        json.dumps(
            {
                "outcome": "APPLIED",
                "lease": "LOCAL_PRIMARY",
                "cloudCheckpoint": final_checkpoint["ref"],
                "cloudCommit": final_checkpoint["commit"],
                "localMergeCommit": land_result["mergeResultCommit"],
                "receiptCommit": land_result["receiptCommit"],
                "acknowledgementSha256": acknowledgement[
                    "acknowledgementSha256"
                ],
                "compute": cleanup,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _cmd_land_locked(args: argparse.Namespace) -> None:
    state = load_state()
    workspace_state = state["workspace"]
    existing_land = workspace_state.get("land")
    if (
        isinstance(existing_land, dict)
        and existing_land.get("phase") == "COMPLETE"
        and workspace_state.get("lease") == "LOCAL_PRIMARY"
    ):
        cleanup = existing_land.get("computeCleanup")
        if args.keep_compute_running and not isinstance(cleanup, dict):
            # COMPLETE can become durable immediately before the post-ack
            # compute disposition. Preserve the explicit no-stop decision on
            # a retry instead of returning an ambiguous null result.
            cleanup = {"state": "running", "requested": False}
            existing_land["computeCleanup"] = cleanup
            state["revision"] += 1
            atomic_state(state)
            record_event("land.compute_retained")
        elif (
            not args.keep_compute_running
            and (
                not isinstance(cleanup, dict)
                or cleanup.get("state") != "stopped"
            )
        ):
            # A guest acknowledgement safely returns write ownership before
            # infrastructure cleanup. If the first stop attempt failed or the
            # controller crashed in that narrow window, a repeated Land must
            # finish the cleanup rather than treating COMPLETE as terminal.
            assert_identity(state)
            outputs = validated_stack_context(state)
            try:
                cleanup = stop_compute_after_land(state, outputs)
                state["runtime"]["state"] = "STOPPED"
                existing_land["computeCleanup"] = cleanup
                state["revision"] += 1
                atomic_state(state)
                record_event("land.compute_stopped", instanceId=outputs["InstanceId"])
            except SpikeError as exc:
                cleanup = {"state": "pending", "error": str(exc)}
                existing_land["computeCleanup"] = cleanup
                state["revision"] += 1
                atomic_state(state)
                record_event("land.compute_cleanup_pending", error=str(exc))
        print(
            json.dumps(
                {
                    "land": existing_land,
                    "lease": "LOCAL_PRIMARY",
                    "outcome": "APPLIED",
                    "changed": False,
                    "compute": cleanup,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    assert_identity(state)
    outputs = validated_stack_context(state)
    if workspace_state.get("cloudPath") != REMOTE_WORKSPACE:
        raise SpikeError("the verified cloud workspace must exist before Land")
    instance_id = outputs["InstanceId"]
    if (
        isinstance(existing_land, dict)
        and existing_land.get("phase") == "NEEDS_REVIEW"
    ):
        workspace, ledger, land_root = validate_existing_local_land_paths(state)
        final_checkpoint = existing_land.get("finalCheckpoint")
        validated_checkpoint = validate_land_guest_checkpoint(
            state=state,
            outputs=outputs,
            checkpoint=final_checkpoint,
        )
        if validated_checkpoint != final_checkpoint:
            raise SpikeError("saved final Land checkpoint changed on conflict retry")
        matching_checkpoints = [
            checkpoint
            for checkpoint in workspace_state.get("checkpoints", [])
            if checkpoint.get("ordinal") == existing_land["ordinal"]
        ]
        if matching_checkpoints != [final_checkpoint]:
            raise SpikeError(
                "workspace checkpoint history lost the final conflict checkpoint"
            )

        guest_status = guest_landing_action(
            instance_id=instance_id,
            run_id=state["runId"],
            volume_id=outputs["WorkspaceVolumeId"],
            action="status",
        )
        expected_guest_status = {
            "operationId": existing_land["operationId"],
            "runId": state["runId"],
            "workspaceId": WORKSPACE_ID,
            "workspaceVolumeId": outputs["WorkspaceVolumeId"],
            "baselineRef": workspace_state["baselineRef"],
            "baselineCommit": workspace_state["baselineCommit"],
            "phase": "FINAL_CHECKPOINT_RECORDED",
            "lease": "LANDING",
            "finalCheckpoint": guest_checkpoint_receipt(final_checkpoint),
            "changed": False,
        }
        if any(
            guest_status.get(key) != value
            for key, value in expected_guest_status.items()
        ):
            raise SpikeError(
                "guest conflict hold is not the exact live frozen Land state"
            )

        try:
            fixture_policy = fixture_policy_for_commit(
                ledger, workspace_state["baselineCommit"]
            )
        except WorkspaceError as exc:
            raise SpikeError("local baseline fixture policy is invalid") from exc
        saved_result = existing_land.get("result")
        verified_result = validate_conflicted_land_fixture(
            workspace=workspace,
            ledger=ledger,
            run_id=state["runId"],
            workspace_id=WORKSPACE_ID,
            baseline_ref=workspace_state["baselineRef"],
            baseline_commit=workspace_state["baselineCommit"],
            cloud_ref=final_checkpoint["ref"],
            cloud_commit=final_checkpoint["commit"],
            approved_ignored=(str(fixture_policy["approvedIgnoredPath"]),),
            operation_root=land_root / "operation",
        )
        if (
            not isinstance(saved_result, dict)
            or saved_result.get("outcome") != "NEEDS_REVIEW"
            or verified_result != saved_result
        ):
            raise SpikeError("saved local Land conflict result changed on retry")
        print(
            json.dumps(
                {
                    "land": existing_land,
                    "lease": "LANDING",
                    "outcome": "NEEDS_REVIEW",
                    "changed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    workspace, ledger, land_root = prepare_local_land_paths(state)
    cloud_primary = workspace_state.get("lease") == "CLOUD_PRIMARY"
    if cloud_primary:
        # Land may need to replace/restart the active runner in order to add
        # the EBS-backed ownership fence. Invalidate the old readiness proof
        # before starting the instance or touching that service, while the
        # cloud retains ownership until the new fence is installed.
        invalidate_safe_to_close(
            state, reset_phone_probe=False, reset_workload=True
        )
        state["connection"]["state"] = "LAND_RUNTIME_INSTALLING"
        state["runtime"]["runtimeDeploymentState"] = "INSTALLING"
        state["revision"] += 1
        atomic_state(state)
        record_event("land.runtime_install_started")
    ensure_instance_online(instance_id)

    if cloud_primary:
        # Install the fenced runtime while the cloud still legitimately owns
        # the workspace. Once local LANDING is persisted, runtime recovery must
        # never attempt to restart the writer.
        try:
            runtime_install = install_runtime_bundle(state)
        except Exception:
            state["runtime"]["runtimeDeploymentState"] = "FAILED"
            state["connection"]["state"] = "LAND_RUNTIME_INSTALL_FAILED"
            state["revision"] += 1
            atomic_state(state)
            record_event("land.runtime_install_failed")
            raise
        state["runtime"].update(runtime_install)
        state["runtime"]["runtimeDeploymentState"] = "ACTIVE"
        state["revision"] += 1
        atomic_state(state)
        record_event(
            "land.runtime_ready",
            runtimeBundleSha256=runtime_install["runtimeBundleSha256"],
        )
        checkpoints = workspace_state.get("checkpoints", [])
        if (
            not isinstance(checkpoints, list)
            or [item.get("ordinal") for item in checkpoints]
            != list(range(1, len(checkpoints) + 1))
        ):
            raise SpikeError("workspace checkpoint history is not contiguous")
        operation_id = f"{state['runId']}-land"
        workspace_state["land"] = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "phase": "REQUESTED",
            "ordinal": len(checkpoints) + 1,
            "requestedAt": now_iso(),
        }
        workspace_state["lease"] = "LANDING"
        state.setdefault("connection", {})["state"] = "LANDING"
        state.setdefault("readiness", {})["safeToClose"] = False
        persist_land_progress(state, "REQUESTED", "land.requested")
    elif workspace_state.get("lease") != "LANDING" or not isinstance(
        existing_land, dict
    ):
        raise SpikeError("Land requires the cloud ownership lease or a resumable operation")

    land_state = workspace_state["land"]
    if land_state["operationId"] != f"{state['runId']}-land":
        raise SpikeError("Land operation identity differs from this session")

    guest_freeze = guest_landing_action(
        instance_id=instance_id,
        run_id=state["runId"],
        volume_id=outputs["WorkspaceVolumeId"],
        action="freeze",
    )
    if guest_freeze.get("phase") == "ACKNOWLEDGED":
        if (
            land_state.get("phase") != "ACK_DURABLE"
            or guest_freeze.get("lease") != "LOCAL_PRIMARY"
            or not isinstance(land_state.get("acknowledgement"), dict)
        ):
            raise SpikeError(
                "guest returned an acknowledged Land that local state cannot prove"
            )
        finish_land_after_guest_ack(
            state=state,
            outputs=outputs,
            guest_ack=guest_freeze,
            keep_compute_running=args.keep_compute_running,
        )
        return
    if (
        guest_freeze.get("operationId") != land_state["operationId"]
        or guest_freeze.get("runId") != state["runId"]
        or guest_freeze.get("workspaceId") != WORKSPACE_ID
        or guest_freeze.get("workspaceVolumeId") != outputs["WorkspaceVolumeId"]
        or guest_freeze.get("baselineCommit") != workspace_state["baselineCommit"]
        or guest_freeze.get("lease") != "LANDING"
        or guest_freeze.get("phase")
        not in {"CLOUD_FROZEN", "FINAL_CHECKPOINT_RECORDED"}
    ):
        raise SpikeError("guest did not return the exact frozen Land lease")
    land_state["guestFreeze"] = guest_freeze
    if land_state["phase"] == "REQUESTED":
        persist_land_progress(
            state,
            "CLOUD_FROZEN",
            "land.cloud_frozen",
            workspaceWriterUid=guest_freeze.get("freeze", {}).get(
                "workspaceWriterUid"
            ),
        )

    guest_checkpoint = land_state.get("guestCheckpoint")
    if guest_checkpoint is None:
        guest_checkpoint = guest_land_checkpoint(state=state, outputs=outputs)
        land_state["guestCheckpoint"] = guest_checkpoint
        state["revision"] += 1
        atomic_state(state)
        record_event(
            "land.final_checkpoint_sealed",
            checkpointRef=guest_checkpoint["ref"],
            commit=guest_checkpoint["commit"],
        )
    else:
        guest_checkpoint = validate_land_guest_checkpoint(
            state=state, outputs=outputs, checkpoint=guest_checkpoint
        )

    final_checkpoint = make_land_checkpoint_durable(
        state=state,
        outputs=outputs,
        checkpoint=guest_checkpoint,
    )
    saved_final = land_state.get("finalCheckpoint")
    if saved_final is not None and saved_final != final_checkpoint:
        raise SpikeError("durable final Land checkpoint changed on retry")
    land_state["finalCheckpoint"] = final_checkpoint
    checkpoints = workspace_state.setdefault("checkpoints", [])
    existing_checkpoint = next(
        (
            item
            for item in checkpoints
            if item.get("ordinal") == final_checkpoint["ordinal"]
        ),
        None,
    )
    if existing_checkpoint is None:
        checkpoints.append(final_checkpoint)
    elif existing_checkpoint != final_checkpoint:
        raise SpikeError("workspace final checkpoint record changed on retry")
    if land_state["phase"] in {"CLOUD_FROZEN", "REQUESTED"}:
        persist_land_progress(
            state,
            "FINAL_CHECKPOINT_DURABLE",
            "land.final_checkpoint_durable",
            checkpointRef=final_checkpoint["ref"],
            commit=final_checkpoint["commit"],
            s3VersionId=final_checkpoint["s3VersionId"],
            s3ManifestVersionId=final_checkpoint["s3ManifestVersionId"],
        )

    guest_checkpoint_state = guest_landing_action(
        instance_id=instance_id,
        run_id=state["runId"],
        volume_id=outputs["WorkspaceVolumeId"],
        action="record-checkpoint",
        record=guest_checkpoint_receipt(final_checkpoint),
    )
    if (
        guest_checkpoint_state.get("phase") != "FINAL_CHECKPOINT_RECORDED"
        or guest_checkpoint_state.get("lease") != "LANDING"
        or guest_checkpoint_state.get("finalCheckpoint")
        != guest_checkpoint_receipt(final_checkpoint)
    ):
        raise SpikeError("guest did not durably bind the exact final Land checkpoint")
    land_state["guestCheckpointState"] = guest_checkpoint_state

    recovery_root = LOCAL_ROOT / "runs" / state["runId"] / "evidence" / "recovery"
    bundle_path = recovery_root / f"{final_checkpoint['bundleSha256']}.bundle"
    manifest_path = (
        recovery_root
        / f"{final_checkpoint['manifestFileSha256']}.manifest.json"
    )
    imported = import_final_checkpoint(
        ledger=ledger,
        quarantine_root=land_root / "quarantine",
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        checkpoint=final_checkpoint,
        run_id=state["runId"],
        workspace_id=WORKSPACE_ID,
        baseline_ref=workspace_state["baselineRef"],
        baseline_commit=workspace_state["baselineCommit"],
    )
    saved_import = land_state.get("import")
    if saved_import is not None and saved_import != imported:
        raise SpikeError("verified final Land import changed on retry")
    land_state["import"] = imported
    if land_state["phase"] == "FINAL_CHECKPOINT_DURABLE":
        persist_land_progress(
            state,
            "IMPORTED",
            "land.final_checkpoint_imported",
            importedRefsSha256=imported["importedRefsSha256"],
        )

    fixture_policy = fixture_policy_for_commit(
        ledger, workspace_state["baselineCommit"]
    )
    land_result = land_fixture(
        workspace=workspace,
        ledger=ledger,
        run_id=state["runId"],
        workspace_id=WORKSPACE_ID,
        baseline_ref=workspace_state["baselineRef"],
        baseline_commit=workspace_state["baselineCommit"],
        cloud_ref=final_checkpoint["ref"],
        cloud_commit=final_checkpoint["commit"],
        approved_ignored=(str(fixture_policy["approvedIgnoredPath"]),),
        operation_root=land_root / "operation",
    )
    saved_result = land_state.get("result")
    if saved_result is not None and saved_result != land_result:
        raise SpikeError("local Land result changed on retry")
    land_state["result"] = land_result
    if land_result.get("outcome") == "NEEDS_REVIEW":
        persist_land_progress(
            state,
            "NEEDS_REVIEW",
            "land.needs_review",
            conflictCount=len(land_result.get("conflicts", [])),
        )
        print(
            json.dumps(
                {
                    "outcome": "NEEDS_REVIEW",
                    "lease": "LANDING",
                    "conflicts": land_result.get("conflicts", []),
                    "conflictWorktree": land_result.get("conflictWorktree"),
                    "cloudCheckpoint": final_checkpoint["ref"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if land_result.get("outcome") != "APPLIED":
        raise SpikeError("local Land returned an unknown outcome")
    if land_state["phase"] == "IMPORTED":
        persist_land_progress(
            state,
            "RECONCILED",
            "land.local_reconciled",
            mergeResultCommit=land_result["mergeResultCommit"],
            receiptCommit=land_result["receiptCommit"],
        )

    receipt_path = land_root / "operation" / "land-receipt.json"
    try:
        receipt = json.loads(
            read_private_file(
                receipt_path, maximum_size=MAX_LOCAL_STATE_BYTES
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpikeError("local Land receipt is invalid") from exc
    ack_path = land_root / "acknowledgement.json"
    if private_file_exists(ack_path, maximum_size=MAX_LOCAL_STATE_BYTES):
        try:
            existing_ack = json.loads(
                read_private_file(
                    ack_path, maximum_size=MAX_LOCAL_STATE_BYTES
                ).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpikeError("saved local Land acknowledgement is invalid") from exc
        if not isinstance(existing_ack, dict):
            raise SpikeError("saved local Land acknowledgement is invalid")
        acknowledgement = build_land_acknowledgement(
            operation_id=land_state["operationId"],
            checkpoint=final_checkpoint,
            land_result=land_result,
            receipt=receipt,
            final_local_manifest=existing_ack.get("finalLocalManifest", {}),
            final_local_manifest_sha256=existing_ack.get(
                "finalLocalManifestSha256", ""
            ),
        )
        if existing_ack != acknowledgement or (
            isinstance(land_state.get("acknowledgement"), dict)
            and land_state["acknowledgement"] != acknowledgement
        ):
            raise SpikeError("saved local Land acknowledgement changed on retry")
    else:
        if land_state.get("phase") == "ACK_DURABLE" or isinstance(
            land_state.get("acknowledgement"), dict
        ):
            raise SpikeError("durable Land acknowledgement file is missing")
        local_manifest, local_manifest_sha = final_local_land_manifest(
            state=state,
            workspace=workspace,
            ledger=ledger,
            land_result=land_result,
            approved_ignored=(str(fixture_policy["approvedIgnoredPath"]),),
        )
        acknowledgement = build_land_acknowledgement(
            operation_id=land_state["operationId"],
            checkpoint=final_checkpoint,
            land_result=land_result,
            receipt=receipt,
            final_local_manifest=local_manifest,
            final_local_manifest_sha256=local_manifest_sha,
        )
        boundary_manifest, boundary_manifest_sha = final_local_land_manifest(
            state=state,
            workspace=workspace,
            ledger=ledger,
            land_result=land_result,
            approved_ignored=(str(fixture_policy["approvedIgnoredPath"]),),
        )
        if (
            boundary_manifest != local_manifest
            or boundary_manifest_sha != local_manifest_sha
        ):
            raise SpikeError(
                "actual local workspace changed before the Land cutover record"
            )
        # This atomic private file is the local cutover record. The cloud is
        # already frozen, so any later local write is new post-Land work and a
        # retry must reuse this exact received-state baseline rather than
        # falsely requiring the live workspace to remain unchanged forever.
        atomic_private_json(ack_path, acknowledgement)
    land_state["acknowledgement"] = acknowledgement
    if land_state["phase"] == "RECONCILED":
        persist_land_progress(
            state,
            "ACK_DURABLE",
            "land.acknowledgement_durable",
            acknowledgementSha256=acknowledgement["acknowledgementSha256"],
        )

    guest_ack = guest_landing_action(
        instance_id=instance_id,
        run_id=state["runId"],
        volume_id=outputs["WorkspaceVolumeId"],
        action="acknowledge",
        record=acknowledgement,
    )
    if (
        guest_ack.get("phase") != "ACKNOWLEDGED"
        or guest_ack.get("lease") != "LOCAL_PRIMARY"
        or guest_ack.get("acknowledgement") != acknowledgement
    ):
        raise SpikeError("guest did not durably return the local ownership lease")
    finish_land_after_guest_ack(
        state=state,
        outputs=outputs,
        guest_ack=guest_ack,
        keep_compute_running=args.keep_compute_running,
    )


def cmd_land(args: argparse.Namespace) -> None:
    with land_controller_lock():
        _cmd_land_locked(args)


def cmd_checkpoint(args: argparse.Namespace) -> None:
    state = load_state()
    assert_identity(state)
    readiness = state.get("readiness", {})
    workspace = state.get("workspace", {})
    outputs = validated_stack_context(state)
    if not outputs or workspace.get("cloudPath") != REMOTE_WORKSPACE:
        raise SpikeError("the verified cloud workspace must exist first")
    if workspace.get("lease") != "CLOUD_PRIMARY":
        raise SpikeError("the cloud workspace must hold the ownership lease")
    plan = checkpoint_evidence_plan(readiness, args.evidence)
    checkpoint_challenge_sha = plan["challengeSha256"]
    expected_evidence = plan["expectedEvidence"]
    expected_proof = plan["expectedProof"]
    label = plan["label"]
    phone_challenge = plan["phoneChallenge"]
    phone_challenge_sha = plan["phoneChallengeSha256"]
    phone_proof_sha = plan["phoneProofSha256"]
    phone_proof_source = plan["phoneProofSource"]
    proof_relative_path = plan["proofRelativePath"]
    proof_source = plan["proofSource"]
    expected_connection_states = {
        "codex-phone": "PHONE_AND_APPROVAL_VERIFIED_AWAITING_CHECKPOINT",
        "codex-phone-post-restart": (
            "POST_RESTART_PHONE_AND_APPROVAL_VERIFIED_AWAITING_CHECKPOINT"
        ),
        "codex-phone-laptop-off": "LAPTOP_OFF_PROVEN_AWAITING_CHECKPOINT",
    }
    if state.get("connection", {}).get("state") not in {
        expected_connection_states[proof_source],
        "CHECKPOINTING",
        "CHECKPOINTED_NOT_READY",
        "READY_SAFE_TO_CLOSE",
    }:
        raise SpikeError("the checkpoint request does not match the active transition")
    expected_proof_sha = hashlib.sha256(expected_proof).hexdigest()

    local_checkpoints = workspace.get("checkpoints", [])
    if (
        not isinstance(local_checkpoints, list)
        or any(not isinstance(item, dict) for item in local_checkpoints)
        or [item.get("ordinal") for item in local_checkpoints]
        != list(range(1, len(local_checkpoints) + 1))
    ):
        raise SpikeError("local checkpoint history is not contiguous")
    matching = [item for item in local_checkpoints if item.get("label") == label]
    if len(matching) > 1:
        raise SpikeError("local checkpoint history contains a duplicate label")
    existing_requested = matching[0] if matching else None
    ordinal = (
        existing_requested["ordinal"]
        if existing_requested is not None
        else len(local_checkpoints) + 1
    )
    if existing_requested is not None:
        expected_parent_ref = existing_requested.get("parentRef")
        expected_parent_commit = existing_requested.get("parentCommit")
    elif local_checkpoints:
        expected_parent_ref = local_checkpoints[-1].get("ref")
        expected_parent_commit = local_checkpoints[-1].get("commit")
    else:
        expected_parent_ref = workspace.get("baselineRef")
        expected_parent_commit = workspace.get("baselineCommit")
    if not isinstance(expected_parent_ref, str) or not isinstance(
        expected_parent_commit, str
    ):
        raise SpikeError("checkpoint parent identity is missing")

    invalidate_safe_to_close(state, reset_phone_probe=False, reset_workload=False)
    state["connection"]["state"] = "CHECKPOINTING"
    state["revision"] += 1
    atomic_state(state)
    record_event("checkpoint.started", ordinal=ordinal, label=label)

    run_id = state["runId"]
    instance_id = outputs["InstanceId"]
    checkpoint_raw = send_command(
        instance_id,
        [
            "set -euo pipefail",
            (
                "python3 /opt/lift-spike/checkpoint.py "
                f"--run-id {shlex.quote(run_id)} "
                f"--workspace-id {shlex.quote(WORKSPACE_ID)} "
                f"--ordinal {ordinal} --label {shlex.quote(label)} "
                f"--expected-volume-id {shlex.quote(outputs['WorkspaceVolumeId'])} "
                f"--required-path {shlex.quote(proof_relative_path)} "
                f"--required-sha256 {shlex.quote(expected_proof_sha)} "
                f"--required-size {len(expected_proof)}"
            ),
        ],
        "Create immutable Lift private-Git checkpoint",
        timeout_seconds=300,
    )
    try:
        checkpoint = json.loads(checkpoint_raw.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SpikeError("guest checkpoint did not return valid JSON") from exc
    if not isinstance(checkpoint, dict):
        raise SpikeError("guest checkpoint returned a non-object")

    expected_ref = (
        f"refs/lift/{WORKSPACE_ID}/sessions/{run_id}/checkpoints/"
        f"{ordinal:04d}-{label}"
    )
    commit = checkpoint.get("commit")
    tree = checkpoint.get("tree")
    bundle_sha = checkpoint.get("bundleSha256")
    bundle_size = checkpoint.get("bundleSize")
    manifest_sha = checkpoint.get("manifestSha256")
    manifest_file_sha = checkpoint.get("manifestFileSha256")
    manifest_size = checkpoint.get("manifestSize")
    file_count = checkpoint.get("fileCount")
    expected_bundle_path = (
        f"/var/lib/lift/ledger/checkpoints/{run_id}/{bundle_sha}.bundle"
    )
    expected_manifest_path = (
        f"/var/lib/lift/ledger/checkpoints/{run_id}/"
        f"{ordinal:04d}-{label}-manifest.json"
    )
    def valid_sha1(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 40
            and all(character in "0123456789abcdef" for character in value)
        )

    def valid_sha256(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )
    if (
        not valid_sha1(commit)
        or not valid_sha1(tree)
        or not valid_sha1(checkpoint.get("cloudHead"))
        or not valid_sha256(bundle_sha)
        or not valid_sha256(manifest_sha)
        or not valid_sha256(manifest_file_sha)
        or not valid_sha256(checkpoint.get("gitSnapshotSha256"))
    ):
        raise SpikeError("guest checkpoint returned invalid object hashes")
    if (
        not isinstance(bundle_size, int)
        or bundle_size <= 0
        or not isinstance(manifest_size, int)
        or manifest_size <= 0
        or not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count < 0
    ):
        raise SpikeError("guest checkpoint returned an invalid recovery object size or file count")
    parents = checkpoint.get("parents")
    history_refs = checkpoint.get("historyRefs")
    recovery_history_refs = checkpoint.get("recoveryHistoryRefs", history_refs)
    recovery_checkpoint_refs = checkpoint.get("recoveryCheckpointRefs")
    if (
        not isinstance(parents, list)
        or not parents
        or any(not valid_sha1(parent) for parent in parents)
        or not isinstance(history_refs, list)
        or not history_refs
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not item["ref"].startswith(
                f"refs/lift/{WORKSPACE_ID}/sessions/{run_id}/git-history/{ordinal:04d}/"
            )
            or not valid_sha1(item.get("objectId"))
            for item in history_refs
        )
        or not isinstance(recovery_history_refs, list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not item["ref"].startswith(
                f"refs/lift/{WORKSPACE_ID}/sessions/{run_id}/git-history/"
            )
            or not valid_sha1(item.get("objectId"))
            for item in recovery_history_refs
        )
        or not isinstance(recovery_checkpoint_refs, list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not item["ref"].startswith(
                f"refs/lift/{WORKSPACE_ID}/sessions/{run_id}/"
            )
            or not valid_sha1(item.get("objectId"))
            for item in recovery_checkpoint_refs
        )
    ):
        raise SpikeError("guest checkpoint returned invalid preserved Git history")
    expected = {
        "ordinal": ordinal,
        "label": label,
        "ref": expected_ref,
        "parentRef": expected_parent_ref,
        "parentCommit": expected_parent_commit,
        "bundlePath": expected_bundle_path,
        "manifestPath": expected_manifest_path,
        "workspaceVolumeId": outputs["WorkspaceVolumeId"],
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise SpikeError("guest checkpoint identity does not match the requested checkpoint")

    ledger_path = f"/var/lib/lift/ledger/{run_id}.git"
    history_verification_commands = [
        (
            f"test \"$(git --git-dir={shlex.quote(ledger_path)} rev-parse "
            f"{shlex.quote(item['ref'])})\" = {shlex.quote(item['objectId'])}"
        )
        for item in history_refs
    ]
    verified = send_command(
        instance_id,
        [
            "set -euo pipefail",
            f"test -f {shlex.quote(expected_bundle_path)}",
            f"test ! -L {shlex.quote(expected_bundle_path)}",
            f"test \"$(stat -c %a {shlex.quote(expected_bundle_path)})\" = 600",
            f"test -f {shlex.quote(expected_manifest_path)}",
            f"test ! -L {shlex.quote(expected_manifest_path)}",
            f"test \"$(stat -c %a {shlex.quote(expected_manifest_path)})\" = 600",
            (
                f"test \"$(sha256sum {shlex.quote(expected_bundle_path)} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(bundle_sha)}"
            ),
            (
                f"test \"$(sha256sum {shlex.quote(expected_manifest_path)} | cut -d ' ' -f 1)\" "
                f"= {shlex.quote(manifest_file_sha)}"
            ),
            (
                f"test \"$(git --git-dir={shlex.quote(ledger_path)} rev-parse "
                f"{shlex.quote(expected_ref + '^{commit}')} )\" = {shlex.quote(commit)}"
            ),
            (
                f"test \"$(git --git-dir={shlex.quote(ledger_path)} show -s --format=%T "
                f"{shlex.quote(commit)})\" = {shlex.quote(tree)}"
            ),
            (
                f"test \"$(git --git-dir={shlex.quote(ledger_path)} show -s --format=%P "
                f"{shlex.quote(commit)})\" = {shlex.quote(' '.join(parents))}"
            ),
            *history_verification_commands,
            (
                f"test \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(expected_bundle_path)})\" "
                f"= \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(REMOTE_WORKSPACE)})\""
            ),
            (
                f"test \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(expected_manifest_path)})\" "
                f"= \"$(findmnt -n -o MAJ:MIN -T {shlex.quote(REMOTE_WORKSPACE)})\""
            ),
            (
                f"git --git-dir={shlex.quote(ledger_path)} bundle verify "
                f"{shlex.quote(expected_bundle_path)} >/dev/null 2>&1"
            ),
            "printf '%s' verified",
        ],
        "Verify EBS checkpoint and recovery bundle",
        timeout_seconds=120,
    )
    if not verified.splitlines() or verified.splitlines()[-1] != "verified":
        raise SpikeError("EBS checkpoint verification did not complete")

    bucket = outputs["TransferBucketName"]
    object_key = f"sessions/{run_id}/checkpoints/{bundle_sha}.bundle"
    manifest_object_key = (
        f"sessions/{run_id}/checkpoints/{manifest_file_sha}.manifest.json"
    )
    head = ensure_s3_recovery_object(
        instance_id=instance_id,
        bucket=bucket,
        key=object_key,
        remote_path=expected_bundle_path,
        sha256=bundle_sha,
        size=bundle_size,
        description="checkpoint Git recovery bundle",
    )
    manifest_head = ensure_s3_recovery_object(
        instance_id=instance_id,
        bucket=bucket,
        key=manifest_object_key,
        remote_path=expected_manifest_path,
        sha256=manifest_file_sha,
        size=manifest_size,
        description="checkpoint SHA-256 manifest",
    )
    version_id = head["VersionId"]
    manifest_version_id = manifest_head["VersionId"]
    expected_checksum = base64.b64encode(bytes.fromhex(bundle_sha)).decode("ascii")
    expected_manifest_checksum = base64.b64encode(
        bytes.fromhex(manifest_file_sha)
    ).decode("ascii")
    versioning = aws_json(
        "s3api", "get-bucket-versioning", "--bucket", bucket
    )
    if versioning.get("Status") != "Enabled":
        raise SpikeError("S3 recovery bucket versioning is not enabled")

    volume = aws_json(
        "ec2", "describe-volumes", "--volume-ids", outputs["WorkspaceVolumeId"]
    ).get("Volumes", [])
    if (
        len(volume) != 1
        or volume[0].get("Encrypted") is not True
        or volume[0].get("State") != "in-use"
        or not any(
            attachment.get("InstanceId") == instance_id
            and attachment.get("State") == "attached"
            for attachment in volume[0].get("Attachments", [])
        )
    ):
        raise SpikeError("the EBS checkpoint volume is not encrypted and attached")

    auto_stop_remaining_seconds = managed_auto_stop_remaining_seconds(instance_id)
    if auto_stop_remaining_seconds < MIN_AUTO_STOP_REMAINING_SECONDS:
        raise SpikeError("the auto-stop timer has less than one hour remaining")

    remote = managed_remote_status(instance_id, REMOTE_WORKSPACE)
    if (
        remote.get("environmentId") != phone_challenge.get("environmentId")
        or remote.get("environmentId") != readiness.get("providerEnvironmentId")
        or remote.get("nativeProjectId") != phone_challenge.get("nativeProjectId")
        or remote.get("projectRoot") != phone_challenge.get("projectRoot")
    ):
        raise SpikeError("the phone-verified remote environment changed before checkpointing")
    durable_checkpoint = {
        "ordinal": ordinal,
        "label": label,
        "ref": expected_ref,
        "commit": commit,
        "tree": tree,
        "parentRef": checkpoint["parentRef"],
        "parentCommit": checkpoint["parentCommit"],
        "parents": parents,
        "cloudHead": checkpoint["cloudHead"],
        "gitSnapshotSha256": checkpoint["gitSnapshotSha256"],
        "historyRefs": history_refs,
        "recoveryHistoryRefs": recovery_history_refs,
        "recoveryCheckpointRefs": recovery_checkpoint_refs,
        "fileCount": file_count,
        "manifestSha256": manifest_sha,
        "manifestFileSha256": manifest_file_sha,
        "manifestSize": manifest_size,
        "bundleSha256": bundle_sha,
        "bundleSize": bundle_size,
        "ebsBundlePath": expected_bundle_path,
        "s3Bucket": bucket,
        "s3ObjectKey": object_key,
        "s3VersionId": version_id,
        "s3ChecksumSHA256": expected_checksum,
        "s3ManifestObjectKey": manifest_object_key,
        "s3ManifestVersionId": manifest_version_id,
        "s3ManifestChecksumSHA256": expected_manifest_checksum,
        "evidenceChallengeSha256": checkpoint_challenge_sha,
        "evidenceProofSha256": expected_proof_sha,
        "evidenceProofSource": proof_source,
        "phoneChallengeSha256": phone_challenge_sha,
        "phoneProofSha256": phone_proof_sha,
        "phoneProofSource": phone_proof_source,
    }
    restore_evidence = restore_test_checkpoint(
        run_id=run_id,
        workspace_id=WORKSPACE_ID,
        bucket=bucket,
        bundle=head,
        manifest_object=manifest_head,
        checkpoint=durable_checkpoint,
        expected_evidence=expected_evidence,
    )
    if not valid_restore_test(restore_evidence, durable_checkpoint):
        raise SpikeError("checkpoint restore test returned invalid or unbound evidence")
    durable_checkpoint["restoreTest"] = restore_evidence
    local_checkpoints = workspace.setdefault("checkpoints", [])
    existing_local = next(
        (item for item in local_checkpoints if item.get("ordinal") == ordinal), None
    )
    if existing_local is not None:
        immutable = (
            "ref",
            "commit",
            "tree",
            "gitSnapshotSha256",
            "manifestFileSha256",
            "bundleSha256",
            "s3ObjectKey",
            "s3ManifestObjectKey",
        )
        if any(existing_local.get(key) != durable_checkpoint.get(key) for key in immutable):
            raise SpikeError("local checkpoint record differs from immutable cloud evidence")
        existing_local.update(durable_checkpoint)
    else:
        local_checkpoints.append(durable_checkpoint)

    readiness["storageDurable"] = True
    readiness["manifestVerified"] = True
    readiness["workloadHealthy"] = True
    readiness["recoveryCheckpointDurable"] = True
    readiness["localStepsComplete"] = True
    readiness["providerEnvironmentId"] = remote["environmentId"]
    readiness["safeToCloseEvidence"] = {
        "verifiedAt": now_iso(),
        "runId": run_id,
        "baselineCommit": workspace["baselineCommit"],
        "instanceId": instance_id,
        "workspaceVolumeId": outputs["WorkspaceVolumeId"],
        "environmentId": remote["environmentId"],
        "nativeProjectId": remote["nativeProjectId"],
        "projectRoot": remote["projectRoot"],
        "checkpointCommit": commit,
        "checkpointTree": tree,
        "s3VersionId": version_id,
        "s3ManifestVersionId": manifest_version_id,
        "autoStopRemainingSeconds": auto_stop_remaining_seconds,
        "restoreTest": restore_evidence,
        "challengeSha256": phone_challenge_sha,
        "proofSha256": phone_proof_sha,
        "proofSource": phone_proof_source,
    }
    runner = managed_runner_status(instance_id)
    readiness["safeToClose"] = live_safe_to_close(
        state, runner, remote, auto_stop_remaining_seconds
    )
    state["connection"]["state"] = (
        "READY_SAFE_TO_CLOSE" if readiness["safeToClose"] else "CHECKPOINTED_NOT_READY"
    )
    state["revision"] += 1
    atomic_state(state)
    record_event(
        "checkpoint.durable",
        checkpointRef=expected_ref,
        commit=commit,
        bundleSha256=bundle_sha,
        s3ObjectKey=object_key,
        s3VersionId=version_id,
        safeToClose=readiness["safeToClose"],
    )

    missing = [
        key for key in SAFE_TO_CLOSE_REQUIRED_GATES if readiness.get(key) is not True
    ]
    print(
        json.dumps(
            {
                "checkpoint": durable_checkpoint,
                "environmentId": remote["environmentId"],
                "safeToClose": readiness["safeToClose"],
                "missingGates": missing,
                "nextAction": (
                    "Proceed to the EC2 stop/start recovery test."
                    if readiness["safeToClose"]
                    and readiness.get("laptopOffProven") is True
                    else "Close the laptop completely, then create the laptop-off proof from the phone."
                    if readiness["safeToClose"]
                    else "Resolve the remaining readiness gates before closing the laptop."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--expected-account", required=True)
    init.set_defaults(handler=cmd_init)
    doctor = subparsers.add_parser("doctor")
    doctor.set_defaults(handler=cmd_doctor)
    up = subparsers.add_parser("up")
    up.set_defaults(handler=cmd_up)
    lift_off = subparsers.add_parser("lift-off")
    lift_off.set_defaults(handler=cmd_lift_off)
    status = subparsers.add_parser("status")
    status.set_defaults(handler=cmd_status)
    install_runtime = subparsers.add_parser("install-runtime")
    install_runtime.set_defaults(handler=cmd_install_runtime)
    runner = subparsers.add_parser("runner")
    runner.add_argument("action", choices=("start", "stop", "status"))
    runner.set_defaults(handler=cmd_runner)
    restart_test = subparsers.add_parser("restart-test")
    restart_test.set_defaults(handler=cmd_restart_test)
    interactive = subparsers.add_parser("connection")
    interactive.add_argument("flow", choices=("auth", "pair", "status"))
    interactive.set_defaults(handler=cmd_interactive)
    readiness = subparsers.add_parser("readiness")
    readiness.add_argument(
        "action",
        choices=(
            "arm",
            "verify",
            "arm-offline",
            "verify-offline",
            "arm-restart",
            "verify-restart",
        ),
    )
    readiness.set_defaults(handler=cmd_readiness)
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument(
        "--evidence", choices=("phone", "laptop-off"), default="phone"
    )
    checkpoint.set_defaults(handler=cmd_checkpoint)
    land = subparsers.add_parser("land")
    land.add_argument("--keep-compute-running", action="store_true")
    land.set_defaults(handler=cmd_land)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.handler(args)
        return 0
    except (SpikeError, WorkspaceError, LandError, LiveLandError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
