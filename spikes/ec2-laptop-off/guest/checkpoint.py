#!/usr/bin/env python3
"""Create an immutable Lift-private Git checkpoint and recovery bundle."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


WORKSPACE_ROOT = Path("/home/lift/workspaces")
LEDGER_ROOT = Path("/var/lib/lift/ledger")
STATE_ROOT = Path("/var/lib/lift-spike/workspaces")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SAFE_VOLUME_ID = re.compile(r"^vol-[0-9a-f]{8,17}$")
ZERO_OID = "0" * 40
FIXTURE_MARKER_PATH = ".lift-spike-fixture.json"


class CheckpointError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
    replace_env: bool = False,
) -> subprocess.CompletedProcess[str]:
    environment = {} if replace_env else os.environ.copy()
    if env is not None:
        environment.update(env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise CheckpointError(
            f"command failed ({' '.join(command)}): {completed.stderr.strip()}"
        )
    return completed


def run_bytes(command: list[str]) -> bytes:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    completed = subprocess.run(command, env=environment, capture_output=True)
    if completed.returncode != 0:
        raise CheckpointError(
            f"command failed ({' '.join(command)}): "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def git(
    ledger: Path,
    arguments: list[str],
    *,
    workspace: Path | None = None,
    index: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "GIT_AUTHOR_NAME": "Lift",
        "GIT_AUTHOR_EMAIL": "spike@lift.invalid",
        "GIT_COMMITTER_NAME": "Lift",
        "GIT_COMMITTER_EMAIL": "spike@lift.invalid",
    })
    if workspace is not None:
        environment["GIT_WORK_TREE"] = str(workspace)
    if index is not None:
        environment["GIT_INDEX_FILE"] = str(index)
    return run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            f"--git-dir={ledger}",
            *arguments,
        ],
        cwd=workspace,
        env=environment,
        input_text=input_text,
        check=check,
        replace_env=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nul_paths(value: str) -> list[str]:
    return [path for path in value.split("\0") if path]


def inside_workspace(relative: str) -> bool:
    path = Path(relative)
    return (
        bool(relative)
        and not path.is_absolute()
        and ".." not in path.parts
        and relative != ".git"
        and not relative.startswith(".git/")
    )


def validate_marker_value(value: object) -> dict[str, Any]:
    expected_keys = {
        "approvedIgnoredPath",
        "excludedSentinelPath",
        "kind",
        "schemaVersion",
    }
    approved = value.get("approvedIgnoredPath") if isinstance(value, dict) else None
    excluded = value.get("excludedSentinelPath") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("schemaVersion") != 1
        or value.get("kind") != "lift-disposable-fixture"
        or not isinstance(approved, str)
        or not inside_workspace(approved)
        or not isinstance(excluded, str)
        or not inside_workspace(excluded)
        or approved == excluded
    ):
        raise CheckpointError("immutable baseline fixture marker is invalid")
    return value


def path_is_excluded(relative: str, excluded: str) -> bool:
    return relative == excluded or relative.startswith(excluded.rstrip("/") + "/")


def baseline_fixture_policy(ledger: Path, baseline_commit: str) -> dict[str, Any]:
    try:
        marker_bytes = run_bytes(
            [
                "git",
                f"--git-dir={ledger}",
                "cat-file",
                "blob",
                f"{baseline_commit}:{FIXTURE_MARKER_PATH}",
            ]
        )
        marker = validate_marker_value(json.loads(marker_bytes.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("immutable baseline fixture marker is invalid") from exc
    policy = {
        "schemaVersion": 1,
        "markerPath": FIXTURE_MARKER_PATH,
        "markerSha256": hashlib.sha256(marker_bytes).hexdigest(),
        "approvedIgnoredPath": marker["approvedIgnoredPath"],
        "excludedSentinelPath": marker["excludedSentinelPath"],
    }
    tree_paths = {
        path.decode("utf-8")
        for path in run_bytes(
            [
                "git",
                f"--git-dir={ledger}",
                "ls-tree",
                "-r",
                "-z",
                "--name-only",
                baseline_commit,
            ]
        ).split(b"\0")
        if path
    }
    excluded = str(policy["excludedSentinelPath"])
    if any(path_is_excluded(path, excluded) for path in tree_paths):
        raise CheckpointError("hard-excluded fixture path entered the baseline")
    return policy


def verify_workspace_fixture_policy(
    workspace: Path,
    policy: dict[str, Any],
) -> None:
    marker_path = workspace / str(policy["markerPath"])
    try:
        info = marker_path.lstat()
        marker_bytes = marker_path.read_bytes()
        marker = validate_marker_value(json.loads(marker_bytes.decode("utf-8")))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("cloud fixture marker is invalid") from exc
    if (
        marker_path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_size > 4096
        or hashlib.sha256(marker_bytes).hexdigest() != policy["markerSha256"]
        or marker["approvedIgnoredPath"] != policy["approvedIgnoredPath"]
        or marker["excludedSentinelPath"] != policy["excludedSentinelPath"]
    ):
        raise CheckpointError("cloud fixture marker differs from the baseline policy")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CheckpointError(f"JSON at {path} must be an object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def workspace_git(
    workspace: Path, arguments: list[str], *, as_lift: bool, check: bool = True
) -> subprocess.CompletedProcess[str]:
    command = [
        "env",
        "HOME=/home/lift" if as_lift else f"HOME={os.environ.get('HOME', '/tmp')}",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_OPTIONAL_LOCKS=0",
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        *arguments,
    ]
    if as_lift:
        command = ["runuser", "-u", "lift", "--", *command]
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return run(
        command,
        cwd=workspace,
        env=environment,
        check=check,
        replace_env=True,
    )


def workspace_fingerprint(workspace: Path, *, as_lift: bool) -> dict[str, Any]:
    git_dir = workspace / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise CheckpointError("workspace Git administration path is not a physical directory")
    index = git_dir / "index"
    if index.exists() and (index.is_symlink() or not stat.S_ISREG(index.stat().st_mode)):
        raise CheckpointError("workspace Git index is not a physical regular file")
    return {
        "head": workspace_git(workspace, ["rev-parse", "HEAD"], as_lift=as_lift).stdout.strip(),
        "refs": workspace_git(
            workspace,
            ["for-each-ref", "--format=%(refname) %(objectname)"],
            as_lift=as_lift,
        ).stdout,
        "indexSha256": sha256_file(index) if index.is_file() else None,
        "status": workspace_git(
            workspace,
            ["status", "--porcelain=v2", "--untracked-files=all"],
            as_lift=as_lift,
        ).stdout,
    }


def workspace_content_entries(
    workspace: Path,
    *,
    as_lift: bool,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    tracked = set(
        nul_paths(
            workspace_git(
                workspace,
                ["ls-files", "-z"],
                as_lift=as_lift,
            ).stdout
        )
    )
    untracked = set(
        nul_paths(
            workspace_git(
                workspace,
                ["ls-files", "--others", "--exclude-standard", "-z"],
                as_lift=as_lift,
            ).stdout
        )
    )
    included = tracked | untracked | {str(policy["approvedIgnoredPath"])}
    excluded = str(policy["excludedSentinelPath"])
    entries: list[dict[str, Any]] = []
    for relative in sorted(included):
        if path_is_excluded(relative, excluded):
            continue
        if not inside_workspace(relative):
            raise CheckpointError(f"unsafe workspace path selected for checkpoint: {relative}")
        absolute = workspace / relative
        try:
            info = absolute.lstat()
        except FileNotFoundError:
            continue
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISREG(info.st_mode):
            entry = {
                "path": relative,
                "type": "file",
                "sha256": sha256_file(absolute),
                "size": info.st_size,
                "executable": bool(mode & stat.S_IXUSR),
            }
        elif stat.S_ISLNK(info.st_mode):
            target = os.readlink(absolute)
            encoded_target = target.encode("utf-8")
            entry = {
                "path": relative,
                "type": "symlink",
                "sha256": hashlib.sha256(encoded_target).hexdigest(),
                "size": len(encoded_target),
                "executable": False,
                "target": target,
            }
        else:
            raise CheckpointError(f"unsupported workspace entry: {relative}")
        entries.append(entry)
    return entries


def manifest_content_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise CheckpointError("checkpoint manifest has no entries")
    entries: list[dict[str, Any]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise CheckpointError("checkpoint manifest contains an invalid entry")
        try:
            entry = {
                key: raw[key]
                for key in ("path", "type", "sha256", "size", "executable")
            }
        except KeyError as exc:
            raise CheckpointError("checkpoint manifest contains an invalid entry") from exc
        if raw.get("type") == "symlink":
            entry["target"] = raw.get("target")
        entries.append(entry)
    return sorted(entries, key=lambda entry: str(entry["path"]))


def verify_workspace_tree_content(
    workspace: Path,
    *,
    as_lift: bool,
    policy: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    if workspace_content_entries(
        workspace,
        as_lift=as_lift,
        policy=policy,
    ) != manifest_content_entries(manifest):
        raise CheckpointError(
            "checkpoint tree and independently scanned workspace content differ"
        )


def cloud_git_snapshot(workspace: Path, *, as_lift: bool) -> dict[str, Any]:
    head = workspace_git(workspace, ["rev-parse", "HEAD"], as_lift=as_lift).stdout.strip()
    refs: list[dict[str, str]] = []
    for line in workspace_git(
        workspace,
        ["for-each-ref", "--format=%(refname)%09%(objectname)"],
        as_lift=as_lift,
    ).stdout.splitlines():
        name, separator, object_id = line.partition("\t")
        if not separator or not name.startswith("refs/"):
            raise CheckpointError("cloud Git ref listing was malformed")
        refs.append({"name": name, "objectId": object_id})
    reflog_result = workspace_git(
        workspace,
        ["reflog", "show", "--all", "--format=%H"],
        as_lift=as_lift,
        check=False,
    )
    if reflog_result.returncode not in (0, 1):
        raise CheckpointError("cloud Git reflog could not be inspected")
    reflog_commits = sorted(set(line for line in reflog_result.stdout.splitlines() if line))
    payload: dict[str, Any] = {
        "head": head,
        "refs": sorted(refs, key=lambda item: item["name"]),
        "reflogCommits": reflog_commits,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload["sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def import_cloud_objects(
    ledger: Path, workspace: Path, bundle: Path, *, as_lift: bool
) -> None:
    workspace_git(
        workspace,
        ["bundle", "create", str(bundle), "--all", "--reflog", "HEAD"],
        as_lift=as_lift,
    )
    info = bundle.lstat()
    if not stat.S_ISREG(info.st_mode) or bundle.is_symlink():
        raise CheckpointError("cloud history staging artifact is not a regular file")
    if as_lift and info.st_uid != pwd.getpwnam("lift").pw_uid:
        raise CheckpointError("cloud history staging artifact has the wrong owner")
    os.chmod(bundle, 0o600)
    git(ledger, ["bundle", "unbundle", str(bundle)])


def history_ref_plan(
    snapshot: dict[str, Any], *, run_id: str, workspace_id: str, ordinal: int
) -> list[dict[str, str]]:
    prefix = (
        f"refs/lift/{workspace_id}/sessions/{run_id}/git-history/{ordinal:04d}"
    )
    planned = [
        {"source": "HEAD", "ref": f"{prefix}/head", "objectId": snapshot["head"]}
    ]
    for item in snapshot["refs"]:
        suffix = item["name"][len("refs/") :]
        planned.append(
            {
                "source": item["name"],
                "ref": f"{prefix}/refs/{suffix}",
                "objectId": item["objectId"],
            }
        )
    for object_id in snapshot["reflogCommits"]:
        planned.append(
            {
                "source": "reflog",
                "ref": f"{prefix}/reflog/{object_id}",
                "objectId": object_id,
            }
        )
    return planned


def publish_object_ref(ledger: Path, ref: str, object_id: str) -> None:
    existing = git(
        ledger, ["rev-parse", "--verify", "--quiet", ref], check=False
    )
    if existing.returncode == 0:
        if existing.stdout.strip() != object_id:
            raise CheckpointError(f"immutable history ref already differs: {ref}")
        return
    if existing.returncode != 1:
        raise CheckpointError(f"unable to inspect immutable history ref: {ref}")
    git(ledger, ["update-ref", "--no-deref", ref, object_id, ZERO_OID])


def tree_manifest(
    ledger: Path,
    *,
    run_id: str,
    workspace_id: str,
    checkpoint_ref: str,
    commit: str,
    tree: str,
    parents: list[str],
    git_snapshot_sha256: str,
    excluded_path: str,
) -> dict[str, Any]:
    raw = run_bytes(
        ["git", f"--git-dir={ledger}", "ls-tree", "-r", "-z", "--full-tree", tree]
    )
    entries: list[dict[str, Any]] = []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        metadata, separator, path_bytes = encoded.partition(b"\t")
        if not separator:
            raise CheckpointError("checkpoint tree listing was malformed")
        mode_bytes, object_type_bytes, object_id_bytes = metadata.split(b" ", 2)
        path = path_bytes.decode("utf-8")
        relative = Path(path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path == ".git"
            or path.startswith(".git/")
        ):
            raise CheckpointError(f"unsafe path in checkpoint tree: {path}")
        if path_is_excluded(path, excluded_path):
            raise CheckpointError("hard-excluded fixture path entered the checkpoint")
        mode = mode_bytes.decode("ascii")
        object_type = object_type_bytes.decode("ascii")
        object_id = object_id_bytes.decode("ascii")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            raise CheckpointError(f"unsupported checkpoint entry: {mode} {object_type} {path}")
        content = run_bytes(
            ["git", f"--git-dir={ledger}", "cat-file", "blob", object_id]
        )
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
                raise CheckpointError(
                    f"symbolic link target is not UTF-8: {path}"
                ) from exc
        entries.append(entry)
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "runId": run_id,
        "workspaceId": workspace_id,
        "checkpointRef": checkpoint_ref,
        "commit": commit,
        "tree": tree,
        "parents": parents,
        "gitSnapshotSha256": git_snapshot_sha256,
        "entries": entries,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload["manifestSha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def staged_tree(
    ledger: Path,
    workspace: Path,
    parent: str,
    index: Path,
    *,
    as_lift: bool,
    policy: dict[str, Any],
) -> str:
    index.unlink(missing_ok=True)
    git(ledger, ["rev-parse", f"{parent}^{{tree}}"])
    git(ledger, ["read-tree", "--empty"], workspace=workspace, index=index)
    selected = [
        str(entry["path"])
        for entry in workspace_content_entries(
            workspace,
            as_lift=as_lift,
            policy=policy,
        )
    ]
    if selected:
        git(
            ledger,
            [
                "--literal-pathspecs",
                "add",
                "-f",
                "-A",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
            ],
            workspace=workspace,
            index=index,
            input_text="\0".join(selected) + "\0",
        )
    excluded_path = str(policy["excludedSentinelPath"])
    captured = set(
        nul_paths(
            git(
                ledger,
                ["ls-files", "-z"],
                workspace=workspace,
                index=index,
            ).stdout
        )
    )
    removals = sorted(
        path for path in captured if path_is_excluded(path, excluded_path)
    )
    if removals:
        git(
            ledger,
            ["update-index", "--force-remove", "-z", "--stdin"],
            workspace=workspace,
            index=index,
            input_text="\0".join(removals) + "\0",
        )
    remaining = set(
        nul_paths(
            git(
                ledger,
                ["ls-files", "-z"],
                workspace=workspace,
                index=index,
            ).stdout
        )
    )
    if any(path_is_excluded(path, excluded_path) for path in remaining):
        raise CheckpointError("hard-excluded fixture path entered the private index")
    return git(ledger, ["write-tree"], workspace=workspace, index=index).stdout.strip()


def resolve_commit(ledger: Path, revision: str) -> str:
    return git(ledger, ["rev-parse", f"{revision}^{{commit}}" ]).stdout.strip()


def ref_commit(ledger: Path, ref: str) -> str | None:
    completed = git(
        ledger,
        ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout.strip()
    if completed.returncode == 1:
        return None
    raise CheckpointError(f"unable to inspect immutable checkpoint ref {ref}")


def durable_device(path: Path) -> str:
    return run(["findmnt", "-n", "-o", "MAJ:MIN", "-T", str(path)]).stdout.strip()


def ebs_volume_id(device: str) -> str:
    serial = run(["lsblk", "-ndo", "SERIAL", f"/dev/block/{device}"]).stdout.strip()
    if re.fullmatch(r"vol[0-9a-f]{8,17}", serial):
        return f"vol-{serial[3:]}"
    if SAFE_VOLUME_ID.fullmatch(serial):
        return serial
    raise CheckpointError("workspace device did not expose an AWS EBS volume serial")


def fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_checkpoint_locked(
    *,
    workspace: Path,
    ledger: Path,
    state_path: Path,
    checkpoints_root: Path,
    run_id: str,
    workspace_id: str,
    ordinal: int,
    label: str,
    expected_volume_id: str | None,
    required_path: str | None,
    required_sha256: str | None,
    required_size: int | None,
    require_durable_mount: bool = True,
) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(run_id) or not SAFE_ID.fullmatch(workspace_id):
        raise CheckpointError("run and workspace IDs must be safe lowercase identifiers")
    if not SAFE_LABEL.fullmatch(label):
        raise CheckpointError("checkpoint label must be a safe lowercase identifier")
    if ordinal < 1 or ordinal > 9999:
        raise CheckpointError("checkpoint ordinal must be between 1 and 9999")

    if workspace.is_symlink() or not workspace.is_dir() or workspace.resolve() != workspace:
        raise CheckpointError("workspace path is not a physical directory")
    if ledger.is_symlink() or not ledger.is_dir() or ledger.resolve() != ledger:
        raise CheckpointError("private ledger path is not a physical directory")
    if state_path.is_symlink() or not state_path.is_file():
        raise CheckpointError("workspace reconstruction state is missing or unsafe")

    state = read_json(state_path)
    if state.get("schemaVersion") != 1:
        raise CheckpointError("unsupported workspace reconstruction state")
    expected_state = {
        "runId": run_id,
        "workspaceId": workspace_id,
        "workspacePath": str(workspace),
        "ledgerPath": str(ledger),
    }
    if any(state.get(key) != value for key, value in expected_state.items()):
        raise CheckpointError("workspace reconstruction identity does not match checkpoint request")

    baseline_ref = state.get("baselineRef")
    baseline_commit = state.get("baselineCommit")
    if not isinstance(baseline_ref, str) or not isinstance(baseline_commit, str):
        raise CheckpointError("workspace reconstruction state omitted its baseline")
    if resolve_commit(ledger, baseline_ref) != baseline_commit:
        raise CheckpointError("private ledger baseline does not match reconstruction state")
    fixture_policy = baseline_fixture_policy(ledger, baseline_commit)
    stored_policy = state.get("fixturePolicy")
    if stored_policy is None:
        state["fixturePolicy"] = fixture_policy
        atomic_json(state_path, state)
    elif stored_policy != fixture_policy:
        raise CheckpointError(
            "workspace reconstruction policy does not match the immutable baseline"
        )
    verify_workspace_fixture_policy(workspace, fixture_policy)
    excluded_path = str(fixture_policy["excludedSentinelPath"])

    storage_device: str | None = None
    storage_volume_id: str | None = None
    if require_durable_mount:
        if not isinstance(expected_volume_id, str) or not SAFE_VOLUME_ID.fullmatch(
            expected_volume_id
        ):
            raise CheckpointError("an exact expected EBS volume ID is required")
        workspace_device = durable_device(workspace)
        ledger_device = durable_device(ledger)
        root_device = durable_device(Path("/"))
        if not workspace_device or workspace_device != ledger_device:
            raise CheckpointError("workspace and private ledger are not on the same durable device")
        if workspace_device == root_device:
            raise CheckpointError("checkpoint refuses to use the instance root disk")
        storage_device = workspace_device
        storage_volume_id = ebs_volume_id(workspace_device)
        if storage_volume_id != expected_volume_id:
            raise CheckpointError("workspace mount is not backed by the expected EBS volume")

    checkpoints = state.get("checkpoints", [])
    if not isinstance(checkpoints, list) or any(not isinstance(item, dict) for item in checkpoints):
        raise CheckpointError("workspace checkpoint history is invalid")
    existing_record = next(
        (item for item in checkpoints if item.get("ordinal") == ordinal), None
    )
    if existing_record is None and ordinal != len(checkpoints) + 1:
        raise CheckpointError("checkpoint ordinals must be contiguous")
    if existing_record is not None and existing_record.get("label") != label:
        raise CheckpointError("checkpoint ordinal already has a different immutable label")

    parent_ref = checkpoints[-1]["ref"] if checkpoints and existing_record is None else baseline_ref
    if existing_record is not None:
        parent_ref = existing_record.get("parentRef")
    if not isinstance(parent_ref, str):
        raise CheckpointError("checkpoint parent ref is invalid")
    parent_commit = resolve_commit(ledger, parent_ref)
    checkpoint_ref = (
        f"refs/lift/{workspace_id}/sessions/{run_id}/checkpoints/"
        f"{ordinal:04d}-{label}"
    )
    if existing_record is not None and existing_record.get("ref") != checkpoint_ref:
        raise CheckpointError("checkpoint history does not match its immutable ref")

    as_lift = require_durable_mount
    original = workspace_fingerprint(workspace, as_lift=as_lift)
    git_snapshot = cloud_git_snapshot(workspace, as_lift=as_lift)
    checkpoints_root.mkdir(parents=True, exist_ok=True)
    os.chmod(checkpoints_root, 0o700)
    with tempfile.TemporaryDirectory(prefix="checkpoint-index-", dir=checkpoints_root) as temporary_name:
        temporary = Path(temporary_name)
        if as_lift:
            lift_user = pwd.getpwnam("lift")
            cloud_temporary = Path(tempfile.mkdtemp(prefix="lift-cloud-history-", dir="/tmp"))
            os.chown(cloud_temporary, lift_user.pw_uid, lift_user.pw_gid)
            os.chmod(cloud_temporary, 0o700)
        else:
            cloud_temporary = temporary / "cloud-history"
            cloud_temporary.mkdir(mode=0o700)
        try:
            cloud_bundle = cloud_temporary / "cloud-history.bundle"
            import_cloud_objects(ledger, workspace, cloud_bundle, as_lift=as_lift)
        finally:
            shutil.rmtree(cloud_temporary)
        first_tree = staged_tree(
            ledger,
            workspace,
            parent_commit,
            temporary / "first.index",
            as_lift=as_lift,
            policy=fixture_policy,
        )
        second_tree = staged_tree(
            ledger,
            workspace,
            parent_commit,
            temporary / "second.index",
            as_lift=as_lift,
            policy=fixture_policy,
        )
        if first_tree != second_tree:
            raise CheckpointError("workspace changed while the checkpoint was being captured")
        tree = first_tree
        cloud_head = resolve_commit(ledger, git_snapshot["head"])
        parents = [parent_commit]
        ancestor = git(
            ledger,
            ["merge-base", "--is-ancestor", cloud_head, parent_commit],
            check=False,
        )
        if ancestor.returncode not in (0, 1):
            raise CheckpointError("cloud Git ancestry could not be verified")
        if cloud_head != parent_commit and ancestor.returncode == 1:
            parents.append(cloud_head)

        existing_commit = ref_commit(ledger, checkpoint_ref)
        changed = existing_commit is None
        if existing_commit is not None:
            existing_tree = git(
                ledger, ["show", "-s", "--format=%T", existing_commit]
            ).stdout.strip()
            existing_parents = git(
                ledger, ["show", "-s", "--format=%P", existing_commit]
            ).stdout.strip()
            if existing_tree != tree or existing_parents != " ".join(parents):
                raise CheckpointError("immutable checkpoint ref already exists with different content")
            commit = existing_commit
        else:
            parent_arguments: list[str] = []
            for parent in parents:
                parent_arguments.extend(["-p", parent])
            commit = git(
                ledger,
                ["commit-tree", tree, *parent_arguments],
                input_text=(
                    f"Lift checkpoint {ordinal:04d}: {label}\n\n"
                    f"Run: {run_id}\nWorkspace: {workspace_id}\n"
                ),
            ).stdout.strip()

        manifest = tree_manifest(
            ledger,
            run_id=run_id,
            workspace_id=workspace_id,
            checkpoint_ref=checkpoint_ref,
            commit=commit,
            tree=tree,
            parents=parents,
            git_snapshot_sha256=git_snapshot["sha256"],
            excluded_path=excluded_path,
        )
        verify_workspace_tree_content(
            workspace,
            as_lift=as_lift,
            policy=fixture_policy,
            manifest=manifest,
        )
        required_values = (required_path, required_sha256, required_size)
        if any(value is not None for value in required_values):
            if not all(value is not None for value in required_values):
                raise CheckpointError("required checkpoint evidence must be fully specified")
            relative = Path(str(required_path))
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or str(required_path).startswith(".git/")
                or not str(required_path)
                or not isinstance(required_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", required_sha256)
                or not isinstance(required_size, int)
                or required_size < 0
            ):
                raise CheckpointError("required checkpoint evidence declaration is invalid")
            required_entry = next(
                (entry for entry in manifest["entries"] if entry["path"] == required_path),
                None,
            )
            if (
                required_entry is None
                or required_entry.get("type") != "file"
                or required_entry.get("sha256") != required_sha256
                or required_entry.get("size") != required_size
                or required_entry.get("executable") is not False
            ):
                raise CheckpointError("required phone evidence is not exact in the checkpoint")
        third_tree = staged_tree(
            ledger,
            workspace,
            parent_commit,
            temporary / "third.index",
            as_lift=as_lift,
            policy=fixture_policy,
        )
        after = workspace_fingerprint(workspace, as_lift=as_lift)
        after_git_snapshot = cloud_git_snapshot(workspace, as_lift=as_lift)
        if third_tree != tree or after != original or after_git_snapshot != git_snapshot:
            raise CheckpointError("workspace changed while the checkpoint was being captured")
        verify_workspace_tree_content(
            workspace,
            as_lift=as_lift,
            policy=fixture_policy,
            manifest=manifest,
        )

    if existing_record is not None:
        if (
            existing_record.get("gitSnapshotSha256") != git_snapshot["sha256"]
            or existing_record.get("cloudHead") != cloud_head
        ):
            raise CheckpointError("immutable checkpoint Git history changed on retry")

    history_refs = history_ref_plan(
        git_snapshot, run_id=run_id, workspace_id=workspace_id, ordinal=ordinal
    )
    if existing_record is not None and existing_record.get("historyRefs") != history_refs:
        raise CheckpointError("immutable checkpoint history-ref map changed on retry")

    if existing_commit is None:
        git(ledger, ["update-ref", "--no-deref", checkpoint_ref, commit, ZERO_OID])
    for item in history_refs:
        publish_object_ref(ledger, item["ref"], item["objectId"])

    manifest_path = checkpoints_root / f"{ordinal:04d}-{label}-manifest.json"
    if manifest_path.exists():
        if read_json(manifest_path) != manifest:
            raise CheckpointError("immutable checkpoint manifest already differs")
    else:
        atomic_json(manifest_path, manifest)
    manifest_file_sha = sha256_file(manifest_path)

    bundle_refs = [baseline_ref]
    for item in checkpoints:
        if item.get("ordinal", 0) > ordinal:
            continue
        item_ref = item.get("ref")
        if isinstance(item_ref, str) and item_ref not in bundle_refs:
            bundle_refs.append(item_ref)
    if checkpoint_ref not in bundle_refs:
        bundle_refs.append(checkpoint_ref)
    for item in history_refs:
        if item["ref"] not in bundle_refs:
            bundle_refs.append(item["ref"])

    bundle: Path | None = None
    bundle_sha: str | None = None
    if existing_record is not None:
        candidate = Path(str(existing_record.get("bundlePath", "")))
        expected_sha = existing_record.get("bundleSha256")
        if (
            isinstance(expected_sha, str)
            and candidate.is_file()
            and not candidate.is_symlink()
            and sha256_file(candidate) == expected_sha
        ):
            bundle = candidate
            bundle_sha = expected_sha
    if bundle is None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="checkpoint-bundle-", suffix=".tmp", dir=checkpoints_root
        )
        os.close(descriptor)
        temporary_bundle = Path(temporary_name)
        temporary_bundle.unlink()
        try:
            git(ledger, ["bundle", "create", str(temporary_bundle), *bundle_refs])
            os.chmod(temporary_bundle, 0o600)
            fsync_file(temporary_bundle)
            bundle_sha = sha256_file(temporary_bundle)
            if (
                existing_record is not None
                and existing_record.get("bundleSha256") != bundle_sha
            ):
                raise CheckpointError("recreated immutable recovery bundle differs")
            bundle = checkpoints_root / f"{bundle_sha}.bundle"
            if bundle.exists():
                if bundle.is_symlink() or not bundle.is_file():
                    raise CheckpointError("content-addressed recovery bundle path is unsafe")
                if sha256_file(bundle) != bundle_sha:
                    raise CheckpointError("existing content-addressed recovery bundle is corrupt")
            else:
                os.replace(temporary_bundle, bundle)
                fsync_file(bundle)
                directory = os.open(checkpoints_root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            temporary_bundle.unlink(missing_ok=True)
    if bundle is None or bundle_sha is None:
        raise CheckpointError("recovery bundle was not created")
    git(ledger, ["bundle", "verify", str(bundle)])

    record = {
        "schemaVersion": 1,
        "ordinal": ordinal,
        "label": label,
        "createdAt": existing_record.get("createdAt") if existing_record else now_iso(),
        "ref": checkpoint_ref,
        "commit": commit,
        "tree": tree,
        "parentRef": parent_ref,
        "parentCommit": parent_commit,
        "parents": parents,
        "cloudHead": cloud_head,
        "gitSnapshotSha256": git_snapshot["sha256"],
        "fixturePolicy": fixture_policy,
        "historyRefs": history_refs,
        "manifestPath": str(manifest_path),
        "manifestSha256": manifest["manifestSha256"],
        "manifestFileSha256": manifest_file_sha,
        "manifestSize": manifest_path.stat().st_size,
        "bundlePath": str(bundle),
        "bundleSha256": bundle_sha,
        "bundleSize": bundle.stat().st_size,
        "fileCount": len(manifest["entries"]),
        "storageDevice": storage_device,
        "workspaceVolumeId": storage_volume_id,
    }
    if existing_record is not None:
        immutable_keys = (
            "ref",
            "commit",
            "tree",
            "parentRef",
            "parentCommit",
            "parents",
            "cloudHead",
            "gitSnapshotSha256",
            "fixturePolicy",
            "historyRefs",
            "manifestSha256",
            "manifestFileSha256",
            "bundleSha256",
        )
        if any(existing_record.get(key) != record.get(key) for key in immutable_keys):
            raise CheckpointError("stored checkpoint metadata changed on retry")
        record = {**existing_record, **record}
        checkpoints[checkpoints.index(existing_record)] = record
        state["checkpoints"] = checkpoints
        state["latestCheckpointRef"] = checkpoint_ref
        state["latestCheckpointCommit"] = commit
        atomic_json(state_path, state)
    else:
        checkpoints.append(record)
        state["checkpoints"] = checkpoints
        state["latestCheckpointRef"] = checkpoint_ref
        state["latestCheckpointCommit"] = commit
        atomic_json(state_path, state)

    recovery_record = checkpoints_root / f"{ordinal:04d}-{label}.json"
    if recovery_record.exists():
        existing_recovery = read_json(recovery_record)
        immutable_recovery_keys = (
            "ref",
            "commit",
            "tree",
            "parentRef",
            "parentCommit",
            "parents",
            "cloudHead",
            "gitSnapshotSha256",
            "fixturePolicy",
            "historyRefs",
            "manifestSha256",
            "manifestFileSha256",
            "bundleSha256",
        )
        if any(
            existing_recovery.get(key) != record.get(key)
            for key in immutable_recovery_keys
        ):
            raise CheckpointError("immutable recovery record already differs")
        if existing_recovery != record:
            atomic_json(recovery_record, record)
    else:
        atomic_json(recovery_record, record)

    return {**record, "changed": changed}


def create_checkpoint(
    *,
    workspace: Path,
    ledger: Path,
    state_path: Path,
    checkpoints_root: Path,
    run_id: str,
    workspace_id: str,
    ordinal: int,
    label: str,
    expected_volume_id: str | None = None,
    required_path: str | None = None,
    required_sha256: str | None = None,
    required_size: int | None = None,
    require_durable_mount: bool,
) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(run_id) or not SAFE_ID.fullmatch(workspace_id):
        raise CheckpointError("run and workspace IDs must be safe lowercase identifiers")
    if not SAFE_LABEL.fullmatch(label):
        raise CheckpointError("checkpoint label must be a safe lowercase identifier")
    if ordinal < 1 or ordinal > 9999:
        raise CheckpointError("checkpoint ordinal must be between 1 and 9999")
    checkpoints_root.mkdir(parents=True, exist_ok=True)
    os.chmod(checkpoints_root, 0o700)
    lock_path = checkpoints_root / ".checkpoint.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _create_checkpoint_locked(
            workspace=workspace,
            ledger=ledger,
            state_path=state_path,
            checkpoints_root=checkpoints_root,
            run_id=run_id,
            workspace_id=workspace_id,
            ordinal=ordinal,
            label=label,
            expected_volume_id=expected_volume_id,
            required_path=required_path,
            required_sha256=required_sha256,
            required_size=required_size,
            require_durable_mount=require_durable_mount,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--ordinal", required=True, type=int)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expected-volume-id", required=True)
    parser.add_argument("--required-path", required=True)
    parser.add_argument("--required-sha256", required=True)
    parser.add_argument("--required-size", required=True, type=int)
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise CheckpointError("checkpoint creation must run as root")
        lift_user = pwd.getpwnam("lift")
        workspace = WORKSPACE_ROOT / args.workspace_id
        if workspace.stat().st_uid != lift_user.pw_uid:
            raise CheckpointError("workspace is not owned by the isolated lift user")
        result = create_checkpoint(
            workspace=workspace,
            ledger=LEDGER_ROOT / f"{args.run_id}.git",
            state_path=STATE_ROOT / f"{args.workspace_id}.json",
            checkpoints_root=LEDGER_ROOT / "checkpoints" / args.run_id,
            run_id=args.run_id,
            workspace_id=args.workspace_id,
            ordinal=args.ordinal,
            label=args.label,
            expected_volume_id=args.expected_volume_id,
            required_path=args.required_path,
            required_sha256=args.required_sha256,
            required_size=args.required_size,
            require_durable_mount=True,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CheckpointError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
