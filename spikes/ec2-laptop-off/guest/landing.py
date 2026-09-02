#!/usr/bin/env python3
"""Durable guest-side ownership gate for a fixture Land operation.

The record written by this module lives on the encrypted workspace volume.  It
is intentionally separate from controller state: once ``FREEZE_REQUESTED`` is
durable, a workload start must fail closed until a later, exact local
acknowledgement returns ownership to the original computer.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, UTC
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterator


WORKSPACE_ROOT = Path("/home/lift/workspaces")
LEDGER_ROOT = Path("/var/lib/lift/ledger")
RECONSTRUCTION_STATE_ROOT = Path("/var/lib/lift-spike/workspaces")
RUNNER_PATH = Path("/opt/lift-spike/runner.py")
RUNNER_UNIT = "lift-workload.service"
LINGER_ROOT = Path("/var/lib/systemd/linger")
LANDING_DIRECTORY_NAME = "landing"
SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 1024 * 1024
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SAFE_VOLUME_ID = re.compile(r"^vol-[0-9a-f]{8,17}$")
OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_BUCKET = re.compile(r"^(?=.{3,63}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$")

PHASE_CLOUD_PRIMARY = "CLOUD_PRIMARY"
PHASE_FREEZE_REQUESTED = "FREEZE_REQUESTED"
PHASE_CLOUD_FROZEN = "CLOUD_FROZEN"
PHASE_FINAL_CHECKPOINT_RECORDED = "FINAL_CHECKPOINT_RECORDED"
PHASE_ACKNOWLEDGED = "ACKNOWLEDGED"
PHASES = (
    PHASE_CLOUD_PRIMARY,
    PHASE_FREEZE_REQUESTED,
    PHASE_CLOUD_FROZEN,
    PHASE_FINAL_CHECKPOINT_RECORDED,
    PHASE_ACKNOWLEDGED,
)
PHASE_INDEX = {phase: index for index, phase in enumerate(PHASES)}


class LandingError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _physical_directory(path: Path, description: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LandingError(f"cannot inspect {description}: {path}") from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise LandingError(f"{description} is not a physical directory")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise LandingError(f"{description} must use its canonical physical path")
    return resolved


def _private_directory(
    path: Path,
    description: str,
    *,
    create: bool = False,
    tighten_legacy: bool = False,
) -> Path:
    if create and not path.exists() and not path.is_symlink():
        parent = _physical_directory(path.parent, f"{description} parent")
        descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.mkdir(path.name, 0o700, dir_fd=descriptor)
            os.fsync(descriptor)
        except FileExistsError:
            pass
        finally:
            os.close(descriptor)
    resolved = _physical_directory(path, description)
    metadata = resolved.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        metadata.st_uid == os.geteuid()
        and tighten_legacy
        and mode != 0o700
        and mode & 0o022 == 0
    ):
        os.chmod(resolved, 0o700)
        metadata = resolved.stat()
        mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid != os.geteuid() or mode != 0o700:
        raise LandingError(
            f"{description} must be owned by the current service identity with mode 0700"
        )
    return resolved


def _secure_regular_file(path: Path, description: str) -> bytes:
    parent = _private_directory(path.parent, f"{description} directory")
    directory = os.open(
        parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory,
        )
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > MAX_RECORD_BYTES
            ):
                raise LandingError(f"unsafe {description}")
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                if not chunk:
                    raise LandingError(f"short read from {description}")
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LandingError(f"cannot read {description}: {path}") from exc
    finally:
        os.close(directory)


def _read_private_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(_secure_regular_file(path, description).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LandingError(f"invalid JSON in {description}") from exc
    if not isinstance(value, dict):
        raise LandingError(f"{description} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    parent = _private_directory(path.parent, "landing state directory")
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        raise LandingError("landing state exceeds its size limit")
    directory = os.open(
        parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
    try:
        if path.exists() or path.is_symlink():
            _secure_regular_file(path, "existing landing state")
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        try:
            offset = 0
            while offset < len(encoded):
                written = os.write(descriptor, encoded[offset:])
                if written <= 0:
                    raise LandingError("could not write complete landing state")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def _validate_id(value: str, description: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise LandingError(f"{description} must be a safe lowercase identifier")
    return value


def _workspace_identity(workspace: Path) -> tuple[Path, str]:
    workspace = _physical_directory(workspace, "workspace")
    root = _physical_directory(WORKSPACE_ROOT, "workspace root")
    if workspace.parent != root:
        raise LandingError("workspace must be an immediate child of the workspace root")
    workspace_id = _validate_id(workspace.name, "workspace ID")
    return workspace, workspace_id


def _landing_root() -> Path:
    ledger_root = _private_directory(LEDGER_ROOT, "private ledger root")
    return _private_directory(
        ledger_root / LANDING_DIRECTORY_NAME,
        "landing state directory",
        create=True,
    )


def _state_path(workspace_id: str) -> Path:
    return _landing_root() / f"{_validate_id(workspace_id, 'workspace ID')}.json"


def _lock_path(workspace_id: str) -> Path:
    return _landing_root() / f"{_validate_id(workspace_id, 'workspace ID')}.lock"


@contextmanager
def lifecycle_lock(workspace: Path) -> Iterator[None]:
    """Serialize workload-start and Land transitions for one workspace.

    Callers such as the provider-blind runner should hold this lock while
    calling :func:`require_cloud_primary` and while committing a start.
    """

    _, workspace_id = _workspace_identity(workspace)
    lock_path = _lock_path(workspace_id)
    parent = _private_directory(lock_path.parent, "landing state directory")
    directory = os.open(
        parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            lock_path.name,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise LandingError("unsafe landing lifecycle lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        os.close(directory)


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, capture_output=True)
    if check and completed.returncode != 0:
        raise LandingError(
            f"command failed ({' '.join(command)}): {completed.stderr.strip()}"
        )
    return completed


def _mount_device(path: Path) -> str:
    return _run(["findmnt", "-n", "-o", "MAJ:MIN", "-T", str(path)]).stdout.strip()


def _volume_id(device: str) -> str:
    serial = _run(["lsblk", "-ndo", "SERIAL", f"/dev/block/{device}"]).stdout.strip()
    if re.fullmatch(r"vol[0-9a-f]{8,17}", serial):
        return f"vol-{serial[3:]}"
    if SAFE_VOLUME_ID.fullmatch(serial):
        return serial
    raise LandingError("workspace device did not expose an AWS EBS volume serial")


def _storage_identity(workspace: Path, ledger: Path) -> tuple[str, str]:
    workspace_device = _mount_device(workspace)
    ledger_device = _mount_device(ledger)
    root_device = _mount_device(Path("/"))
    if not workspace_device or workspace_device != ledger_device:
        raise LandingError("workspace and private ledger are not on the same device")
    if workspace_device == root_device:
        raise LandingError("landing state must be stored on the workspace data volume")
    return workspace_device, _volume_id(workspace_device)


def _legacy_reconstruction(workspace: Path, workspace_id: str) -> dict[str, Any]:
    state_path = RECONSTRUCTION_STATE_ROOT / f"{workspace_id}.json"
    _private_directory(
        RECONSTRUCTION_STATE_ROOT,
        "legacy reconstruction state directory",
        tighten_legacy=True,
    )
    state = _read_private_json(state_path, "workspace reconstruction state")
    run_id = _validate_id(state.get("runId"), "run ID")
    expected = {
        "schemaVersion": 1,
        "runId": run_id,
        "workspaceId": workspace_id,
        "workspacePath": str(workspace),
        "ledgerPath": str(LEDGER_ROOT / f"{run_id}.git"),
    }
    if any(state.get(key) != value for key, value in expected.items()):
        raise LandingError("legacy reconstruction state does not match the workspace")
    baseline_ref = state.get("baselineRef")
    baseline_commit = state.get("baselineCommit")
    expected_baseline_ref = (
        f"refs/lift/{workspace_id}/sessions/{run_id}/baseline"
    )
    if baseline_ref != expected_baseline_ref or not isinstance(
        baseline_commit, str
    ) or OBJECT_ID.fullmatch(baseline_commit) is None:
        raise LandingError("legacy reconstruction state has an invalid baseline")
    ledger = _private_directory(
        Path(state["ledgerPath"]),
        "session private ledger",
        tighten_legacy=True,
    )
    _, volume_id = _storage_identity(workspace, ledger)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "operationId": f"{run_id}-land",
        "runId": run_id,
        "workspaceId": workspace_id,
        "workspacePath": str(workspace),
        "ledgerPath": str(ledger),
        "baselineRef": baseline_ref,
        "baselineCommit": baseline_commit,
        "workspaceVolumeId": volume_id,
        "phase": PHASE_CLOUD_PRIMARY,
        "lease": "CLOUD_PRIMARY",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def _validate_checkpoint(value: object, state: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "schemaVersion",
        "ordinal",
        "label",
        "ref",
        "commit",
        "tree",
        "parents",
        "bundleSha256",
        "manifestSha256",
        "manifestFileSha256",
        "s3Bucket",
        "s3ObjectKey",
        "s3VersionId",
        "s3ManifestObjectKey",
        "s3ManifestVersionId",
        "restoreTest",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise LandingError("final checkpoint record has an invalid shape")
    ordinal = value.get("ordinal")
    if (
        value.get("schemaVersion") != 1
        or not isinstance(ordinal, int)
        or isinstance(ordinal, bool)
        or not 1 <= ordinal <= 9999
        or value.get("label") != "land-final"
    ):
        raise LandingError("final checkpoint identity is invalid")
    expected_ref = (
        f"refs/lift/{state['workspaceId']}/sessions/{state['runId']}/"
        f"checkpoints/{ordinal:04d}-land-final"
    )
    commit = value.get("commit")
    tree = value.get("tree")
    parents = value.get("parents")
    bundle_sha = value.get("bundleSha256")
    manifest_content_sha = value.get("manifestSha256")
    manifest_sha = value.get("manifestFileSha256")
    bucket = value.get("s3Bucket")
    version_id = value.get("s3VersionId")
    manifest_version_id = value.get("s3ManifestVersionId")
    if (
        value.get("ref") != expected_ref
        or not isinstance(commit, str)
        or OBJECT_ID.fullmatch(commit) is None
        or not isinstance(tree, str)
        or OBJECT_ID.fullmatch(tree) is None
        or not isinstance(parents, list)
        or not parents
        or any(not isinstance(parent, str) or OBJECT_ID.fullmatch(parent) is None for parent in parents)
        or not isinstance(bundle_sha, str)
        or SHA256.fullmatch(bundle_sha) is None
        or not isinstance(manifest_content_sha, str)
        or SHA256.fullmatch(manifest_content_sha) is None
        or not isinstance(manifest_sha, str)
        or SHA256.fullmatch(manifest_sha) is None
        or not isinstance(bucket, str)
        or SAFE_BUCKET.fullmatch(bucket) is None
        or ".." in bucket
        or not isinstance(version_id, str)
        or not version_id
        or not isinstance(manifest_version_id, str)
        or not manifest_version_id
    ):
        raise LandingError("final checkpoint record is malformed")
    if value.get("s3ObjectKey") != (
        f"sessions/{state['runId']}/checkpoints/{bundle_sha}.bundle"
    ) or value.get("s3ManifestObjectKey") != (
        f"sessions/{state['runId']}/checkpoints/{manifest_sha}.manifest.json"
    ):
        raise LandingError("final checkpoint object keys are not canonical")
    restore = value.get("restoreTest")
    restore_keys = {
        "bundleLocalSha256",
        "manifestLocalSha256",
        "restoredCommit",
        "restoredTree",
        "restoredFileCount",
        "verifiedAt",
    }
    if (
        not isinstance(restore, dict)
        or set(restore) != restore_keys
        or restore.get("bundleLocalSha256") != bundle_sha
        or restore.get("manifestLocalSha256") != manifest_sha
        or restore.get("restoredCommit") != commit
        or restore.get("restoredTree") != tree
        or not isinstance(restore.get("restoredFileCount"), int)
        or isinstance(restore.get("restoredFileCount"), bool)
        or restore["restoredFileCount"] < 0
        or not _valid_timestamp(restore.get("verifiedAt"))
    ):
        raise LandingError("final checkpoint restore evidence is invalid")
    return json.loads(json.dumps(value, sort_keys=True))


def _validate_acknowledgement(
    value: object, state: dict[str, Any], checkpoint: dict[str, Any]
) -> dict[str, Any]:
    keys = {
        "schemaVersion",
        "kind",
        "operationId",
        "runId",
        "workspaceId",
        "baseline",
        "cloudFinal",
        "recoveryObjects",
        "localLand",
        "finalLocalManifest",
        "finalLocalManifestSha256",
        "acknowledgementSha256",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise LandingError("local acknowledgement has an invalid shape")
    claimed_ack_sha = value.get("acknowledgementSha256")
    unsigned = {key: item for key, item in value.items() if key != "acknowledgementSha256"}
    if (
        not isinstance(claimed_ack_sha, str)
        or SHA256.fullmatch(claimed_ack_sha) is None
        or hashlib.sha256(
            json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        != claimed_ack_sha
    ):
        raise LandingError("local acknowledgement hash is invalid")
    expected_receipt_ref = (
        f"refs/lift/{state['workspaceId']}/sessions/{state['runId']}/land-receipt"
    )
    baseline = value.get("baseline")
    cloud_final = value.get("cloudFinal")
    recovery = value.get("recoveryObjects")
    local_land = value.get("localLand")
    local_manifest = value.get("finalLocalManifest")
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != "lift-land-acknowledgement"
        or value.get("operationId") != state["operationId"]
        or value.get("runId") != state["runId"]
        or value.get("workspaceId") != state["workspaceId"]
        or baseline
        != {"ref": state["baselineRef"], "commit": state["baselineCommit"]}
        or cloud_final
        != {
            "checkpointRef": checkpoint["ref"],
            "landRef": (
                f"refs/lift/{state['workspaceId']}/sessions/"
                f"{state['runId']}/cloud-final"
            ),
            "commit": checkpoint["commit"],
            "tree": checkpoint["tree"],
            "parents": checkpoint["parents"],
        }
    ):
        raise LandingError("local acknowledgement is not bound to this Land operation")
    expected_recovery = {
        "bundle": {
            "sha256": checkpoint["bundleSha256"],
            "s3ObjectKey": checkpoint["s3ObjectKey"],
            "s3VersionId": checkpoint["s3VersionId"],
        },
        "manifest": {
            "sha256": checkpoint["manifestSha256"],
            "fileSha256": checkpoint["manifestFileSha256"],
            "s3ObjectKey": checkpoint["s3ManifestObjectKey"],
            "s3VersionId": checkpoint["s3ManifestVersionId"],
        },
    }
    if recovery != expected_recovery or not isinstance(local_land, dict):
        raise LandingError("local acknowledgement recovery identity differs")
    receipt_commit = local_land.get("receiptCommit")
    merge_commit = local_land.get("mergeResultCommit")
    if (
        set(local_land)
        != {
            "resultSha256",
            "outcome",
            "localReturnRef",
            "localReturnCommit",
            "mergeResultRef",
            "mergeResultCommit",
            "verifiedAt",
            "receiptRef",
            "receiptCommit",
            "receiptSha256",
        }
        or local_land.get("outcome") != "APPLIED"
        or local_land.get("receiptRef") != expected_receipt_ref
        or any(
            not isinstance(local_land.get(key), str)
            or OBJECT_ID.fullmatch(local_land[key]) is None
            for key in ("localReturnCommit", "mergeResultCommit", "receiptCommit")
        )
        or any(
            not isinstance(local_land.get(key), str)
            or SHA256.fullmatch(local_land[key]) is None
            for key in ("resultSha256", "receiptSha256")
        )
        or not _valid_timestamp(local_land.get("verifiedAt"))
        or not isinstance(receipt_commit, str)
        or not isinstance(merge_commit, str)
    ):
        raise LandingError("local acknowledgement receipt is invalid")
    if not isinstance(local_manifest, dict):
        raise LandingError("local acknowledgement manifest is invalid")
    claimed_manifest_sha = value.get("finalLocalManifestSha256")
    unsigned_manifest = {
        key: item for key, item in local_manifest.items() if key != "manifestSha256"
    }
    if (
        not isinstance(claimed_manifest_sha, str)
        or SHA256.fullmatch(claimed_manifest_sha) is None
        or local_manifest.get("manifestSha256") != claimed_manifest_sha
        or hashlib.sha256(
            json.dumps(
                unsigned_manifest, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        != claimed_manifest_sha
        or local_manifest.get("runId") != state["runId"]
        or local_manifest.get("workspaceId") != state["workspaceId"]
        or local_manifest.get("mergeResultCommit") != merge_commit
    ):
        raise LandingError("local acknowledgement manifest is not exact")
    return json.loads(json.dumps(value, sort_keys=True))


def _validate_state(value: object, workspace: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LandingError("landing state must be a JSON object")
    workspace, workspace_id = _workspace_identity(workspace)
    run_id = value.get("runId")
    if not isinstance(run_id, str) or SAFE_ID.fullmatch(run_id) is None:
        raise LandingError("landing state has an invalid run ID")
    base_keys = {
        "schemaVersion",
        "operationId",
        "runId",
        "workspaceId",
        "workspacePath",
        "ledgerPath",
        "baselineRef",
        "baselineCommit",
        "workspaceVolumeId",
        "phase",
        "lease",
        "createdAt",
        "updatedAt",
    }
    phase = value.get("phase")
    allowed = set(base_keys)
    if phase in {PHASE_FREEZE_REQUESTED, PHASE_CLOUD_FROZEN}:
        allowed.add("freeze")
    elif phase == PHASE_FINAL_CHECKPOINT_RECORDED:
        allowed.update({"freeze", "finalCheckpoint"})
    elif phase == PHASE_ACKNOWLEDGED:
        allowed.update({"freeze", "finalCheckpoint", "acknowledgement"})
    if set(value) != allowed:
        raise LandingError("landing state has an invalid shape for its phase")
    ledger = LEDGER_ROOT / f"{run_id}.git"
    expected = {
        "schemaVersion": SCHEMA_VERSION,
        "operationId": f"{run_id}-land",
        "runId": run_id,
        "workspaceId": workspace_id,
        "workspacePath": str(workspace),
        "ledgerPath": str(ledger),
        "baselineRef": f"refs/lift/{workspace_id}/sessions/{run_id}/baseline",
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise LandingError("landing state identity does not match the workspace")
    if (
        phase not in PHASE_INDEX
        or value.get("lease")
        != ("CLOUD_PRIMARY" if phase == PHASE_CLOUD_PRIMARY else "LOCAL_PRIMARY" if phase == PHASE_ACKNOWLEDGED else "LANDING")
        or not isinstance(value.get("baselineCommit"), str)
        or OBJECT_ID.fullmatch(value["baselineCommit"]) is None
        or not isinstance(value.get("workspaceVolumeId"), str)
        or SAFE_VOLUME_ID.fullmatch(value["workspaceVolumeId"]) is None
        or not _valid_timestamp(value.get("createdAt"))
        or not _valid_timestamp(value.get("updatedAt"))
    ):
        raise LandingError("landing state contains invalid lifecycle metadata")
    _private_directory(ledger, "session private ledger")
    if "freeze" in value:
        freeze = value["freeze"]
        expected_freeze_keys = {"requestedAt"}
        if PHASE_INDEX[phase] >= PHASE_INDEX[PHASE_CLOUD_FROZEN]:
            expected_freeze_keys.update(
                {
                    "frozenAt",
                    "runnerState",
                    "workspaceWriterUid",
                    "userManagerFence",
                }
            )
        if (
            not isinstance(freeze, dict)
            or set(freeze) != expected_freeze_keys
            or not _valid_timestamp(freeze.get("requestedAt"))
            or freeze.get("runnerState", "inactive") != "inactive"
            or (
                "workspaceWriterUid" in freeze
                and (
                    not isinstance(freeze["workspaceWriterUid"], int)
                    or isinstance(freeze["workspaceWriterUid"], bool)
                    or freeze["workspaceWriterUid"] <= 0
                )
            )
            or (
                "frozenAt" in freeze
                and not _valid_timestamp(freeze.get("frozenAt"))
            )
        ):
            raise LandingError("landing freeze record is invalid")
        if "userManagerFence" in freeze:
            user_fence = freeze["userManagerFence"]
            writer_uid = freeze.get("workspaceWriterUid")
            if user_fence != {
                "uid": writer_uid,
                "user": "lift",
                "unit": f"user@{writer_uid}.service",
                "unitMasked": True,
                "lingerDisabled": True,
            }:
                raise LandingError("landing user-manager fence is invalid")
    if "finalCheckpoint" in value:
        _validate_checkpoint(value["finalCheckpoint"], value)
    if "acknowledgement" in value:
        _validate_acknowledgement(
            value["acknowledgement"], value, value["finalCheckpoint"]
        )
    return value


def _read_state(workspace: Path) -> dict[str, Any] | None:
    _, workspace_id = _workspace_identity(workspace)
    path = _state_path(workspace_id)
    if not path.exists() and not path.is_symlink():
        return None
    return _validate_state(_read_private_json(path, "landing state"), workspace)


def _write_state(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    _, workspace_id = _workspace_identity(workspace)
    validated = _validate_state(state, workspace)
    _atomic_json(_state_path(workspace_id), validated)
    return validated


def _load_or_migrate_state(
    workspace: Path, *, allow_legacy_missing: bool
) -> dict[str, Any]:
    state = _read_state(workspace)
    if state is not None:
        return state
    if not allow_legacy_missing:
        raise LandingError("workspace has no durable ownership record")
    workspace, workspace_id = _workspace_identity(workspace)
    migrated = _legacy_reconstruction(workspace, workspace_id)
    return _write_state(workspace, migrated)


def _assert_state_storage(workspace: Path, state: dict[str, Any]) -> None:
    _, live_volume_id = _storage_identity(workspace, Path(state["ledgerPath"]))
    if live_volume_id != state.get("workspaceVolumeId"):
        raise LandingError("durable ownership record belongs to another EBS volume")


def require_cloud_primary(
    workspace: Path, allow_legacy_missing: bool = True
) -> dict[str, Any]:
    """Fail unless the EBS-backed ownership record authorizes cloud writes.

    The caller must hold :func:`lifecycle_lock` across this check and the
    workload-start decision.  ``allow_legacy_missing`` exists only to migrate
    the already-deployed Phase 0 fixture from its reconstruction record.
    """

    state = _load_or_migrate_state(
        workspace, allow_legacy_missing=allow_legacy_missing
    )
    _assert_state_storage(workspace, state)
    if state.get("phase") != PHASE_CLOUD_PRIMARY or state.get("lease") != "CLOUD_PRIMARY":
        raise LandingError("workspace ownership does not permit a cloud workload start")
    return state


def _stop_runner() -> dict[str, Any]:
    completed = _run(["python3", str(RUNNER_PATH), "stop"])
    try:
        value = json.loads(completed.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise LandingError("provider-blind runner stop returned invalid JSON") from exc
    if not isinstance(value, dict) or value.get("state") != "inactive":
        raise LandingError("provider-blind runner did not report an inactive state")
    return value


def _runner_stopped() -> None:
    active = _run(["systemctl", "is-active", RUNNER_UNIT], check=False)
    enabled = _run(["systemctl", "is-enabled", RUNNER_UNIT], check=False)
    if active.returncode == 0 or active.stdout.strip() not in {
        "inactive",
        "failed",
        "unknown",
    }:
        raise LandingError("provider-blind workload service is still active")
    if enabled.returncode == 0 or enabled.stdout.strip() not in {
        "disabled",
        "not-found",
        "static",
    }:
        raise LandingError("provider-blind workload service is still enabled")


def _workspace_writer_uid(workspace: Path) -> int:
    uid = workspace.stat().st_uid
    try:
        identity = pwd.getpwuid(uid)
    except KeyError as exc:
        raise LandingError("workspace writer UID has no local account") from exc
    if uid <= 0 or identity.pw_name != "lift":
        raise LandingError("workspace writer is not the isolated lift account")
    return uid


def _fence_user_manager(uid: int) -> dict[str, Any]:
    """Prevent same-UID user units from recreating a cloud writer."""

    try:
        identity = pwd.getpwuid(uid)
    except KeyError as exc:
        raise LandingError("workspace writer UID has no local account") from exc
    if uid <= 0 or identity.pw_name != "lift":
        raise LandingError("user-manager fence requires the isolated lift account")
    unit = f"user@{uid}.service"
    _run(["loginctl", "disable-linger", identity.pw_name])
    _run(["systemctl", "mask", "--now", unit])
    active = _run(["systemctl", "is-active", unit], check=False)
    enabled = _run(["systemctl", "is-enabled", unit], check=False)
    linger_path = LINGER_ROOT / identity.pw_name
    if (
        active.returncode == 0
        or active.stdout.strip() not in {"inactive", "failed", "unknown"}
        or enabled.returncode == 0
        or enabled.stdout.strip() != "masked"
        or linger_path.exists()
        or linger_path.is_symlink()
    ):
        raise LandingError("isolated user manager is not durably fenced")
    return {
        "uid": uid,
        "user": identity.pw_name,
        "unit": unit,
        "unitMasked": True,
        "lingerDisabled": True,
    }


def _probe_user_manager_fence(uid: int) -> dict[str, Any]:
    """Read back the user-manager fence without repairing it."""

    try:
        identity = pwd.getpwuid(uid)
    except KeyError as exc:
        raise LandingError("workspace writer UID has no local account") from exc
    if uid <= 0 or identity.pw_name != "lift":
        raise LandingError("user-manager fence requires the isolated lift account")
    unit = f"user@{uid}.service"
    active = _run(["systemctl", "is-active", unit], check=False)
    enabled = _run(["systemctl", "is-enabled", unit], check=False)
    linger_path = LINGER_ROOT / identity.pw_name
    if (
        active.returncode == 0
        or active.stdout.strip() not in {"inactive", "failed", "unknown"}
        or enabled.returncode == 0
        or enabled.stdout.strip() != "masked"
        or linger_path.exists()
        or linger_path.is_symlink()
    ):
        raise LandingError("isolated user manager is not durably fenced")
    return {
        "uid": uid,
        "user": identity.pw_name,
        "unit": unit,
        "unitMasked": True,
        "lingerDisabled": True,
    }


def _pids_for_uid(uid: int, proc_root: Path = Path("/proc")) -> list[int]:
    """Return processes whose kernel-reported UID set includes ``uid``.

    The owner of ``/proc/<pid>`` is not authoritative: Linux deliberately
    reports some nondumpable unprivileged processes as root-owned. The Uid
    tuple in ``/proc/<pid>/status`` retains the real/effective/saved/fs IDs and
    therefore cannot be used by such a writer to disappear from the freeze.
    """

    pids: list[int] = []
    for candidate in proc_root.iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            with (candidate / "status").open("rb") as handle:
                status = handle.read(64 * 1024 + 1)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LandingError(
                f"cannot inspect process identity for PID {candidate.name}"
            ) from exc
        if len(status) > 64 * 1024:
            raise LandingError("process identity record exceeds its size limit")
        uid_line = next(
            (line for line in status.splitlines() if line.startswith(b"Uid:")),
            None,
        )
        try:
            values = [int(value) for value in uid_line.split()[1:]]
        except (AttributeError, ValueError) as exc:
            raise LandingError(
                f"process identity record is malformed for PID {candidate.name}"
            ) from exc
        if len(values) != 4:
            raise LandingError(
                f"process identity record is malformed for PID {candidate.name}"
            )
        if uid in values:
            pids.append(int(candidate.name))
    return sorted(pids)


def _quiesce_workspace_user(workspace: Path, timeout_seconds: float = 10.0) -> int:
    uid = workspace.stat().st_uid
    if uid == 0 or uid == os.geteuid():
        raise LandingError("workspace writer identity is not safely isolated from Land")
    for pid in _pids_for_uid(uid):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout_seconds
    remaining = _pids_for_uid(uid)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = _pids_for_uid(uid)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + min(timeout_seconds, 5.0)
    remaining = _pids_for_uid(uid)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = _pids_for_uid(uid)
    if remaining:
        raise LandingError("workspace writer processes remained after freeze")
    return uid


def _probe_workspace_user_quiescent(workspace: Path) -> int:
    """Verify that the workspace writer has no processes without killing any."""

    uid = _workspace_writer_uid(workspace)
    if _pids_for_uid(uid):
        raise LandingError("workspace writer processes reappeared after freeze")
    return uid


def _assert_frozen(
    workspace: Path,
    *,
    stopped_probe: Callable[[], None] | None = None,
    writer_probe: Callable[[Path], int] | None = None,
    user_manager_probe: Callable[[int], dict[str, Any]] | None = None,
) -> tuple[int, dict[str, Any]]:
    (stopped_probe or _runner_stopped)()
    writer_uid = _workspace_writer_uid(workspace)
    fence = (user_manager_probe or _fence_user_manager)(writer_uid)
    observed_uid = (writer_probe or _quiesce_workspace_user)(workspace)
    if observed_uid != writer_uid:
        raise LandingError("workspace writer identity changed during freeze")
    confirmed_fence = (user_manager_probe or _fence_user_manager)(writer_uid)
    if confirmed_fence != fence:
        raise LandingError("isolated user-manager fence changed during freeze")
    return writer_uid, fence


def _assert_freeze_evidence(
    state: dict[str, Any], writer_uid: int, user_manager_fence: dict[str, Any]
) -> None:
    freeze = state.get("freeze")
    if not isinstance(freeze, dict) or (
        freeze.get("workspaceWriterUid") != writer_uid
        or freeze.get("userManagerFence") != user_manager_fence
    ):
        raise LandingError("live cloud freeze differs from its durable evidence")


def freeze_landing(
    *,
    workspace: Path,
    run_id: str,
    workspace_id: str,
    expected_volume_id: str,
    stop_runner: Callable[[], dict[str, Any]] | None = None,
    stopped_probe: Callable[[], None] | None = None,
    writer_probe: Callable[[Path], int] | None = None,
    user_manager_probe: Callable[[int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace, actual_workspace_id = _workspace_identity(workspace)
    if _validate_id(workspace_id, "workspace ID") != actual_workspace_id:
        raise LandingError("freeze workspace ID does not match its physical path")
    _validate_id(run_id, "run ID")
    if SAFE_VOLUME_ID.fullmatch(expected_volume_id) is None:
        raise LandingError("freeze requires an exact EBS volume ID")
    with lifecycle_lock(workspace):
        state = _load_or_migrate_state(workspace, allow_legacy_missing=True)
        _assert_state_storage(workspace, state)
        if (
            state["runId"] != run_id
            or state["workspaceId"] != workspace_id
            or state["workspaceVolumeId"] != expected_volume_id
        ):
            raise LandingError("freeze request does not match durable workspace identity")
        if PHASE_INDEX[state["phase"]] >= PHASE_INDEX[PHASE_ACKNOWLEDGED]:
            return {**state, "changed": False}
        if PHASE_INDEX[state["phase"]] >= PHASE_INDEX[PHASE_CLOUD_FROZEN]:
            writer_uid, user_manager_fence = _assert_frozen(
                workspace,
                stopped_probe=stopped_probe,
                writer_probe=writer_probe,
                user_manager_probe=user_manager_probe,
            )
            _assert_freeze_evidence(state, writer_uid, user_manager_fence)
            return {**state, "changed": False}
        if state["phase"] == PHASE_CLOUD_PRIMARY:
            requested_at = now_iso()
            state.update(
                {
                    "phase": PHASE_FREEZE_REQUESTED,
                    "lease": "LANDING",
                    "freeze": {"requestedAt": requested_at},
                    "updatedAt": requested_at,
                }
            )
            _write_state(workspace, state)
        runner_result = (stop_runner or _stop_runner)()
        if not isinstance(runner_result, dict) or runner_result.get("state") != "inactive":
            raise LandingError("runner stop result was not an inactive state")
        writer_uid, user_manager_fence = _assert_frozen(
            workspace,
            stopped_probe=stopped_probe,
            writer_probe=writer_probe,
            user_manager_probe=user_manager_probe,
        )
        frozen_at = now_iso()
        state.update(
            {
                "phase": PHASE_CLOUD_FROZEN,
                "lease": "LANDING",
                "freeze": {
                    "requestedAt": state["freeze"]["requestedAt"],
                    "frozenAt": frozen_at,
                    "runnerState": "inactive",
                    "workspaceWriterUid": writer_uid,
                    "userManagerFence": user_manager_fence,
                },
                "updatedAt": frozen_at,
            }
        )
        _write_state(workspace, state)
        return {**state, "changed": True}


def status_landing(
    *,
    workspace: Path,
    allow_legacy_missing: bool = False,
    stopped_probe: Callable[[], None] | None = None,
    writer_probe: Callable[[Path], int] | None = None,
    user_manager_probe: Callable[[int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace, _ = _workspace_identity(workspace)
    with lifecycle_lock(workspace):
        state = _load_or_migrate_state(
            workspace, allow_legacy_missing=allow_legacy_missing
        )
        _assert_state_storage(workspace, state)
        if state["phase"] in {
            PHASE_CLOUD_FROZEN,
            PHASE_FINAL_CHECKPOINT_RECORDED,
        }:
            writer_uid, user_manager_fence = _assert_frozen(
                workspace,
                stopped_probe=stopped_probe or _runner_stopped,
                writer_probe=writer_probe or _probe_workspace_user_quiescent,
                user_manager_probe=(
                    user_manager_probe or _probe_user_manager_fence
                ),
            )
            _assert_freeze_evidence(state, writer_uid, user_manager_fence)
        return {**state, "changed": False}


def record_final_checkpoint(
    *,
    workspace: Path,
    run_id: str,
    workspace_id: str,
    expected_volume_id: str,
    checkpoint: dict[str, Any],
    stopped_probe: Callable[[], None] | None = None,
    writer_probe: Callable[[Path], int] | None = None,
    user_manager_probe: Callable[[int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace, actual_workspace_id = _workspace_identity(workspace)
    if workspace_id != actual_workspace_id:
        raise LandingError("checkpoint workspace ID does not match its physical path")
    with lifecycle_lock(workspace):
        state = _load_or_migrate_state(workspace, allow_legacy_missing=False)
        _assert_state_storage(workspace, state)
        if (
            state["runId"] != run_id
            or state["workspaceId"] != workspace_id
            or state["workspaceVolumeId"] != expected_volume_id
        ):
            raise LandingError("checkpoint request does not match durable workspace identity")
        if PHASE_INDEX[state["phase"]] < PHASE_INDEX[PHASE_CLOUD_FROZEN]:
            raise LandingError("final checkpoint cannot be recorded before cloud freeze")
        writer_uid, user_manager_fence = _assert_frozen(
            workspace,
            stopped_probe=stopped_probe,
            writer_probe=writer_probe,
            user_manager_probe=user_manager_probe,
        )
        _assert_freeze_evidence(state, writer_uid, user_manager_fence)
        normalized = _validate_checkpoint(checkpoint, state)
        existing = state.get("finalCheckpoint")
        if existing is not None:
            if existing != normalized:
                raise LandingError("immutable final checkpoint already differs")
            return {**state, "changed": False}
        if state["phase"] != PHASE_CLOUD_FROZEN:
            raise LandingError("landing state cannot accept a new final checkpoint")
        changed_at = now_iso()
        state.update(
            {
                "phase": PHASE_FINAL_CHECKPOINT_RECORDED,
                "lease": "LANDING",
                "finalCheckpoint": normalized,
                "updatedAt": changed_at,
            }
        )
        _write_state(workspace, state)
        return {**state, "changed": True}


def acknowledge_landing(
    *,
    workspace: Path,
    run_id: str,
    workspace_id: str,
    expected_volume_id: str,
    acknowledgement: dict[str, Any],
    stopped_probe: Callable[[], None] | None = None,
    writer_probe: Callable[[Path], int] | None = None,
    user_manager_probe: Callable[[int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workspace, actual_workspace_id = _workspace_identity(workspace)
    if workspace_id != actual_workspace_id:
        raise LandingError("acknowledgement workspace ID does not match its physical path")
    with lifecycle_lock(workspace):
        state = _load_or_migrate_state(workspace, allow_legacy_missing=False)
        _assert_state_storage(workspace, state)
        if (
            state["runId"] != run_id
            or state["workspaceId"] != workspace_id
            or state["workspaceVolumeId"] != expected_volume_id
        ):
            raise LandingError("acknowledgement does not match durable workspace identity")
        checkpoint = state.get("finalCheckpoint")
        if not isinstance(checkpoint, dict):
            raise LandingError("local acknowledgement requires a final checkpoint")
        normalized = _validate_acknowledgement(
            acknowledgement, state, checkpoint
        )
        existing = state.get("acknowledgement")
        if existing is not None:
            if existing != normalized:
                raise LandingError("immutable local acknowledgement already differs")
            return {**state, "changed": False}
        if state["phase"] != PHASE_FINAL_CHECKPOINT_RECORDED:
            raise LandingError("landing state cannot accept a local acknowledgement")
        writer_uid, user_manager_fence = _assert_frozen(
            workspace,
            stopped_probe=stopped_probe,
            writer_probe=writer_probe,
            user_manager_probe=user_manager_probe,
        )
        _assert_freeze_evidence(state, writer_uid, user_manager_fence)
        changed_at = now_iso()
        state.update(
            {
                "phase": PHASE_ACKNOWLEDGED,
                "lease": "LOCAL_PRIMARY",
                "acknowledgement": normalized,
                "updatedAt": changed_at,
            }
        )
        _write_state(workspace, state)
        return {**state, "changed": True}


def _record_argument(path_value: str, description: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        raise LandingError(f"{description} path must be absolute")
    return _read_private_json(path, description)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "status", "record-checkpoint", "acknowledge"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-id", required=True)
        command.add_argument("--workspace-id", required=True)
        command.add_argument("--expected-volume-id", required=True)
        if name in {"record-checkpoint", "acknowledge"}:
            command.add_argument("--record", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if os.geteuid() != 0:
            raise LandingError("landing lifecycle commands must run as root")
        workspace_id = _validate_id(args.workspace_id, "workspace ID")
        workspace = WORKSPACE_ROOT / workspace_id
        common = {
            "workspace": workspace,
            "run_id": args.run_id,
            "workspace_id": workspace_id,
            "expected_volume_id": args.expected_volume_id,
        }
        if args.command == "freeze":
            result = freeze_landing(**common)
        elif args.command == "status":
            result = status_landing(workspace=workspace)
            if (
                result.get("runId") != args.run_id
                or result.get("workspaceVolumeId") != args.expected_volume_id
            ):
                raise LandingError("status request does not match durable workspace identity")
        elif args.command == "record-checkpoint":
            result = record_final_checkpoint(
                **common,
                checkpoint=_record_argument(args.record, "final checkpoint record"),
            )
        else:
            result = acknowledge_landing(
                **common,
                acknowledgement=_record_argument(args.record, "local acknowledgement"),
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (LandingError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
