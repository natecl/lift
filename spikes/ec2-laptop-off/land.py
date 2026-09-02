"""Fixture-only, crash-resumable B/L/C reconciliation for Lift Land."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
from typing import Any, Iterable, Iterator
import unicodedata

from workspace import (
    WorkspaceError,
    capture_fixture_snapshot,
    content_manifest,
    fixture_policy_for_commit,
    validate_fixture_policy,
    workspace_state_fingerprint,
)


ZERO_OID = "0" * 40
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
SUPPORTED_MODES = {"100644", "100755", "120000"}
RECEIPT_NAME = "land-receipt.json"
JOURNAL_NAME = "apply-journal.json"
MERGE_NAME = "merge.json"
RESULT_NAME = "result.json"
IDENTITY_NAME = "operation.json"
LOCK_NAME = ".land.lock"
SYNTHETIC_COMMIT_DATE = "2000-01-01T00:00:00+00:00"
MAX_RECORD_SIZE = 4 * 1024 * 1024


class LandError(RuntimeError):
    pass


class _ConcurrentLocalChange(LandError):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"local path changed during Land: {path}")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _git_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("GIT_"):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    if extra:
        environment.update(extra)
    return environment


def _run_git(
    arguments: list[str],
    *,
    git_dir: Path | None = None,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgSign=false",
    ]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=_git_environment(),
        input=input_bytes,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise LandError(f"Git command failed ({' '.join(command)}): {stderr}")
    return completed


def _git_text(
    arguments: list[str],
    *,
    git_dir: Path | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> str:
    return _run_git(
        arguments,
        git_dir=git_dir,
        cwd=cwd,
        input_bytes=input_text.encode("utf-8") if input_text is not None else None,
        check=check,
    ).stdout.decode("utf-8")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _private_directory(path: Path, description: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise LandError(f"cannot inspect {description}: {path}") from exc
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise LandError(f"{description} is not a physical directory")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LandError(f"{description} must be owned by this user with mode 0700")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise LandError(f"{description} must use its canonical physical path")
    return resolved


def _ensure_private_directory(path: Path) -> Path:
    if not path.exists() and not path.is_symlink():
        parent = path.parent.resolve(strict=True)
        if parent != path.parent.absolute():
            raise LandError(f"private Land directory has a non-canonical parent: {path}")
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    return _private_directory(path, "private Land directory")


def _secure_regular_info(
    descriptor: int, *, description: str, max_size: int | None = None
) -> os.stat_result:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) & 0o077
        or (max_size is not None and info.st_size > max_size)
    ):
        raise LandError(f"unsafe {description}")
    return info


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _private_directory(path.parent, "Land record directory")
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECORD_SIZE:
        raise LandError(f"Land record is too large: {path.name}")
    directory = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = f".{path.name}.{secrets.token_hex(12)}.tmp"
    try:
        try:
            existing = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                _secure_regular_info(existing, description=f"Land record: {path}")
            finally:
                os.close(existing)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        try:
            offset = 0
            while offset < len(encoded):
                written = os.write(descriptor, encoded[offset:])
                if written <= 0:
                    raise LandError(f"could not write {path.name}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        _private_directory(path.parent, "Land record directory")
        directory = os.open(
            path.parent,
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
                info = _secure_regular_info(
                    descriptor,
                    description=f"Land record: {path}",
                    max_size=MAX_RECORD_SIZE,
                )
                chunks: list[bytes] = []
                remaining = info.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                    if not chunk:
                        raise LandError(f"short read from Land record: {path}")
                    chunks.append(chunk)
                    remaining -= len(chunk)
            finally:
                os.close(descriptor)
        finally:
            os.close(directory)
        value = json.loads(b"".join(chunks).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LandError(f"invalid Land record at {path}") from exc
    if not isinstance(value, dict):
        raise LandError(f"Land record at {path} must be an object")
    return value


def _validate_identity(run_id: str, workspace_id: str) -> str:
    if SAFE_ID.fullmatch(run_id) is None or SAFE_ID.fullmatch(workspace_id) is None:
        raise LandError("run and workspace IDs must be safe lowercase identifiers")
    return f"refs/lift/{workspace_id}/sessions/{run_id}"


def _physical_directory(path: Path, description: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise LandError(f"{description} is not a physical directory")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise LandError(f"{description} must use its canonical physical path")
    return resolved


def _prepare_operation_root(
    *,
    operation_root: Path,
    workspace: Path,
    ledger: Path,
    prefix: str,
) -> Path:
    operation_root = operation_root.absolute()
    if (
        operation_root == workspace
        or workspace in operation_root.parents
        or operation_root in workspace.parents
    ):
        raise LandError("Land operation state and workspace cannot contain one another")
    if (
        operation_root == ledger
        or ledger in operation_root.parents
        or operation_root in ledger.parents
    ):
        raise LandError("Land operation state and private ledger cannot contain one another")
    root = _ensure_private_directory(operation_root)
    if root.stat().st_dev != workspace.stat().st_dev:
        raise LandError("Land operation state must share the workspace filesystem")
    identity = {
        "schemaVersion": 1,
        "workspace": str(workspace),
        "ledger": str(ledger),
        "sessionPrefix": prefix,
    }
    identity_path = root / IDENTITY_NAME
    if identity_path.exists() or identity_path.is_symlink():
        if _read_json(identity_path) != identity:
            raise LandError("Land operation directory belongs to another operation")
    else:
        _atomic_json(identity_path, identity)
    return root


@contextmanager
def _operation_lock(operation_root: Path) -> Iterator[None]:
    directory = os.open(
        operation_root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        descriptor = os.open(
            LOCK_NAME,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        try:
            _secure_regular_info(descriptor, description="Land operation lock")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    finally:
        os.close(directory)


def _resolve_commit(ledger: Path, revision: str) -> str:
    commit = _git_text(["rev-parse", f"{revision}^{{commit}}"], git_dir=ledger).strip()
    if OBJECT_ID.fullmatch(commit) is None:
        raise LandError("Git returned an invalid commit ID")
    return commit


def _commit_tree(ledger: Path, commit: str) -> str:
    tree = _git_text(["show", "-s", "--format=%T", commit], git_dir=ledger).strip()
    if OBJECT_ID.fullmatch(tree) is None:
        raise LandError("Git returned an invalid tree ID")
    return tree


def _publish_ref(ledger: Path, ref_name: str, object_id: str) -> None:
    existing = _run_git(
        ["rev-parse", "--verify", "--quiet", ref_name],
        git_dir=ledger,
        check=False,
    )
    if existing.returncode == 0:
        if existing.stdout.decode("ascii").strip() != object_id:
            raise LandError(f"immutable Land ref already differs: {ref_name}")
        return
    if existing.returncode != 1:
        raise LandError(f"could not inspect immutable Land ref: {ref_name}")
    _git_text(
        ["update-ref", "--no-deref", ref_name, object_id, ZERO_OID],
        git_dir=ledger,
    )


def _local_git_history_record(
    *,
    ledger: Path,
    prefix: str,
    baseline_commit: str,
    local_commit: str,
    claimed: object | None = None,
) -> dict[str, Any]:
    history_prefix = f"{prefix}/git-history/local-return"
    listing = _git_text(
        [
            "for-each-ref",
            "--format=%(refname)%09%(objectname)",
            f"{history_prefix}/",
        ],
        git_dir=ledger,
    )
    head: str | None = None
    refs: list[dict[str, str]] = []
    reflog_commits: list[str] = []
    history_refs: list[dict[str, str]] = []
    for line in listing.splitlines():
        name, separator, object_id = line.partition("\t")
        if not separator or OBJECT_ID.fullmatch(object_id) is None:
            raise LandError("returning-local Git history ref listing is malformed")
        relative = name.removeprefix(f"{history_prefix}/")
        if relative == name:
            raise LandError("returning-local Git history escaped its session namespace")
        if relative == "head":
            if head is not None:
                raise LandError("returning-local Git history has multiple HEAD refs")
            head = object_id
            source = "HEAD"
        elif relative.startswith("refs/") and len(relative) > len("refs/"):
            source = relative
            refs.append({"name": source, "objectId": object_id})
        elif relative.startswith("reflog/"):
            recorded_commit = relative.removeprefix("reflog/")
            if (
                "/" in recorded_commit
                or OBJECT_ID.fullmatch(recorded_commit) is None
                or recorded_commit != object_id
            ):
                raise LandError("returning-local reflog ref is malformed")
            source = "reflog"
            reflog_commits.append(object_id)
        else:
            raise LandError("returning-local Git history contains an unknown ref")
        history_refs.append(
            {"source": source, "ref": name, "objectId": object_id}
        )
        if _run_git(
            ["cat-file", "-e", f"{object_id}^{{object}}"],
            git_dir=ledger,
            check=False,
        ).returncode != 0:
            raise LandError("returning-local Git history lost a referenced object")
    if head is None:
        raise LandError("returning-local Git history omitted HEAD")
    if _resolve_commit(ledger, head) != head:
        raise LandError("returning-local Git history HEAD is not a commit")
    parents = _git_text(
        ["show", "-s", "--format=%P", local_commit], git_dir=ledger
    ).strip()
    if parents != f"{baseline_commit} {head}":
        raise LandError("returning-local snapshot lost its original Git HEAD parent")
    refs.sort(key=lambda item: item["name"])
    reflog_commits.sort()
    snapshot: dict[str, Any] = {
        "head": head,
        "refs": refs,
        "reflogCommits": reflog_commits,
    }
    canonical = json.dumps(
        snapshot, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    history_refs.sort(
        key=lambda item: (
            0 if item["source"] == "HEAD" else 1 if item["source"] != "reflog" else 2,
            item["source"],
            item["ref"],
        )
    )
    record = {
        "schemaVersion": 1,
        "snapshotSha256": hashlib.sha256(canonical).hexdigest(),
        "head": head,
        "historyRefs": history_refs,
    }
    if claimed is not None and claimed != record:
        raise LandError("returning-local Git history record differs from private refs")
    return record


def _safe_path(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise LandError("Land tree contains an invalid path")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise LandError(f"Land tree path contains a control character: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise LandError(f"Land tree path escapes the workspace: {raw}")
    if any(part.casefold() == ".git" for part in path.parts):
        raise LandError(f"Land tree path aliases Git administration state: {raw}")
    return path


def _validate_symlink_target(path: PurePosixPath, target: str) -> None:
    if not target or "\x00" in target or PurePosixPath(target).is_absolute():
        raise LandError(f"unsafe symbolic link target at {path}")
    resolved: list[str] = list(path.parent.parts)
    for part in PurePosixPath(target).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                raise LandError(f"symbolic link escapes the workspace: {path}")
            resolved.pop()
        else:
            resolved.append(part)
    if any(part.casefold() == ".git" for part in resolved):
        raise LandError(f"symbolic link targets Git administration state: {path}")


def _tree_entries(ledger: Path, revision: str) -> dict[str, dict[str, Any]]:
    raw = _run_git(
        ["ls-tree", "-r", "-z", "--full-tree", revision], git_dir=ledger
    ).stdout
    entries: dict[str, dict[str, Any]] = {}
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        metadata, separator, path_bytes = encoded.partition(b"\t")
        if not separator:
            raise LandError("Land tree listing is malformed")
        try:
            mode_bytes, object_type, object_id_bytes = metadata.split(b" ", 2)
            path_text = path_bytes.decode("utf-8")
            mode = mode_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise LandError("Land tree contains unsupported path or metadata encoding") from exc
        path = _safe_path(path_text)
        if object_type != b"blob" or mode not in SUPPORTED_MODES:
            raise LandError(f"unsupported Land tree entry: {path_text}")
        if OBJECT_ID.fullmatch(object_id) is None:
            raise LandError("Land tree contains an invalid object ID")
        content = _run_git(["cat-file", "blob", object_id], git_dir=ledger).stdout
        entry: dict[str, Any] = {
            "path": path_text,
            "type": "symlink" if mode == "120000" else "file",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "executable": mode == "100755",
            "gitMode": mode,
            "gitObjectId": object_id,
        }
        if mode == "120000":
            try:
                target = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LandError(f"symbolic link target is not UTF-8: {path_text}") from exc
            _validate_symlink_target(path, target)
            entry["target"] = target
        entries[path_text] = entry

    paths = set(entries)
    for raw in paths:
        parts = PurePosixPath(raw).parts
        for length in range(1, len(parts)):
            ancestor = "/".join(parts[:length])
            if ancestor in paths:
                raise LandError(f"file and ancestor path collision: {ancestor} and {raw}")
    return entries


def _validate_fixture_tree_policy(
    *,
    ledger: Path,
    commit: str,
    expected_policy: dict[str, object],
    entries: dict[str, dict[str, Any]],
    description: str,
) -> None:
    try:
        actual_policy = fixture_policy_for_commit(ledger, commit)
    except WorkspaceError as exc:
        raise LandError(f"{description} fixture policy is invalid") from exc
    if actual_policy != expected_policy:
        raise LandError(f"{description} fixture policy differs from the handoff baseline")
    excluded = str(expected_policy["excludedSentinelPath"])
    if any(path == excluded or path.startswith(excluded.rstrip("/") + "/") for path in entries):
        raise LandError(f"hard-excluded fixture path entered {description}")


def _entry_identity(entry: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if entry is None:
        return None
    return (
        entry.get("type"),
        entry.get("sha256"),
        entry.get("size"),
        entry.get("executable"),
        entry.get("target"),
    )


def _manifest(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    projected = [
        {
            key: entry[key]
            for key in ("path", "type", "sha256", "size", "executable")
        }
        | ({"target": entry["target"]} if entry["type"] == "symlink" else {})
        for entry in (entries[path] for path in sorted(entries))
    ]
    payload: dict[str, Any] = {"schemaVersion": 1, "entries": projected}
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload["manifestSha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _normalize_workspace_manifest(value: dict[str, object]) -> dict[str, Any]:
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        raise LandError("workspace manifest has no entries")
    entries: dict[str, dict[str, Any]] = {}
    for raw in raw_entries:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise LandError("workspace manifest contains an invalid entry")
        entry = {
            key: raw[key]
            for key in ("path", "type", "sha256", "size", "executable")
        }
        if raw.get("type") == "symlink":
            entry["target"] = raw.get("target")
        entries[raw["path"]] = entry
    return _manifest(entries)


def _workspace_matches(
    workspace: Path,
    approved_ignored: tuple[str, ...],
    expected: dict[str, dict[str, Any]],
) -> bool:
    try:
        actual = _normalize_workspace_manifest(
            content_manifest(workspace, approved_ignored)
        )
    except WorkspaceError:
        return False
    return actual == _manifest(expected)


def _git_admin_matches(actual: dict[str, str], expected: dict[str, str]) -> bool:
    return all(
        actual.get(key) == expected.get(key)
        for key in ("head", "branch", "refs", "indexSha256")
    )


def _policy_conflicts(
    baseline: dict[str, dict[str, Any]],
    local: dict[str, dict[str, Any]],
    cloud: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    local_changes = {
        path
        for path in set(baseline) | set(local)
        if _entry_identity(baseline.get(path)) != _entry_identity(local.get(path))
    }
    cloud_changes = {
        path
        for path in set(baseline) | set(cloud)
        if _entry_identity(baseline.get(path)) != _entry_identity(cloud.get(path))
    }
    conflicts: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted(set(local) & set(cloud)):
        local_type = local[path].get("type")
        cloud_type = cloud[path].get("type")
        if local_type != cloud_type:
            conflicts[(path, "type-change")] = {
                "path": path,
                "reason": "type-change",
            }
    for path in sorted(local_changes & cloud_changes):
        if _entry_identity(local.get(path)) != _entry_identity(cloud.get(path)):
            conflicts[(path, "both-modified")] = {
                "path": path,
                "reason": "both-modified",
            }
    for local_path in sorted(local):
        for cloud_path in sorted(cloud):
            if local_path == cloud_path:
                continue
            if local_path.startswith(cloud_path + "/") or cloud_path.startswith(
                local_path + "/"
            ):
                display = min(local_path, cloud_path)
                conflicts[(display, "file-directory-topology")] = {
                    "path": display,
                    "reason": "file-directory-topology",
                }

    normalized_prefixes: dict[str, str] = {}
    for raw in sorted(set(local) | set(cloud)):
        parts = PurePosixPath(raw).parts
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            key = "/".join(
                unicodedata.normalize("NFC", part).casefold()
                for part in parts[:length]
            )
            previous = normalized_prefixes.get(key)
            if previous is not None and previous != prefix:
                display = min(previous, prefix)
                conflicts[(display, "case-unicode-collision")] = {
                    "path": display,
                    "reason": "case-unicode-collision",
                }
            else:
                normalized_prefixes[key] = prefix
    return [conflicts[key] for key in sorted(conflicts)]


def _prepare_worktree(ledger: Path, path: Path, revision: str) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise LandError(f"refusing to replace an unsafe Land worktree: {path}")
        removal = _run_git(
            ["worktree", "remove", "--force", str(path)],
            git_dir=ledger,
            check=False,
        )
        if removal.returncode != 0:
            raise LandError(
                "refusing to delete a directory Git did not verify as a Land worktree"
            )
    _git_text(["worktree", "prune"], git_dir=ledger)
    _git_text(["worktree", "add", "--detach", str(path), revision], git_dir=ledger)
    os.chmod(path, 0o700)


def _create_commit(
    ledger: Path,
    *,
    tree: str,
    parents: list[str],
    message: str,
) -> str:
    arguments = ["commit-tree", tree]
    for parent in parents:
        arguments.extend(["-p", parent])
    environment = _git_environment(
        {
            "GIT_AUTHOR_NAME": "Lift",
            "GIT_AUTHOR_EMAIL": "spike@lift.invalid",
            "GIT_COMMITTER_NAME": "Lift",
            "GIT_COMMITTER_EMAIL": "spike@lift.invalid",
            "GIT_AUTHOR_DATE": SYNTHETIC_COMMIT_DATE,
            "GIT_COMMITTER_DATE": SYNTHETIC_COMMIT_DATE,
        }
    )
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgSign=false",
        f"--git-dir={ledger}",
        *arguments,
    ]
    completed = subprocess.run(
        command,
        env=environment,
        input=(message.rstrip() + "\n").encode("utf-8"),
        capture_output=True,
    )
    if completed.returncode != 0:
        raise LandError(completed.stderr.decode("utf-8", errors="replace").strip())
    commit = completed.stdout.decode("ascii").strip()
    if OBJECT_ID.fullmatch(commit) is None:
        raise LandError("Git returned an invalid synthetic commit")
    return commit


def _merge_snapshots(
    *,
    ledger: Path,
    operation_root: Path,
    prefix: str,
    baseline_commit: str,
    local_commit: str,
    cloud_commit: str,
) -> dict[str, Any]:
    merge_path = operation_root / "merge-worktree"
    merge_record_path = operation_root / MERGE_NAME
    if merge_record_path.exists():
        record = _read_json(merge_record_path)
        if (
            record.get("schemaVersion") != 1
            or record.get("baselineCommit") != baseline_commit
            or record.get("localCommit") != local_commit
            or record.get("cloudCommit") != cloud_commit
        ):
            raise LandError("persisted merge record belongs to another Land operation")
        if record.get("outcome") == "NEEDS_REVIEW":
            if record.get("conflictWorktree") != str(merge_path):
                raise LandError("persisted conflict worktree path is not canonical")
            if not merge_path.exists() and not merge_path.is_symlink():
                reasons = {
                    item.get("reason")
                    for item in record.get("conflicts", [])
                    if isinstance(item, dict)
                }
                if reasons and reasons <= {
                    "type-change",
                    "file-directory-topology",
                    "case-unicode-collision",
                }:
                    merge_path.mkdir(mode=0o700)
                    _fsync_directory(operation_root)
            _private_directory(merge_path, "preserved conflict worktree")
        elif record.get("outcome") == "MERGED_CLEAN":
            merge_ref = f"{prefix}/merge-result"
            merge_commit = _resolve_commit(ledger, merge_ref)
            if (
                record.get("mergeResultRef") != merge_ref
                or record.get("mergeResultCommit") != merge_commit
                or record.get("mergeResultTree") != _commit_tree(ledger, merge_commit)
            ):
                raise LandError("persisted merge result is not anchored by its private ref")
            parents = _git_text(
                ["show", "-s", "--format=%P", merge_commit], git_dir=ledger
            ).strip()
            if parents != f"{local_commit} {cloud_commit}":
                raise LandError("persisted merge result has unexpected parents")
            if record.get("manifest") != _manifest(_tree_entries(ledger, merge_commit)):
                raise LandError("persisted merge result manifest differs")
        else:
            raise LandError("persisted merge record has an invalid outcome")
        return record

    baseline = _tree_entries(ledger, baseline_commit)
    local = _tree_entries(ledger, local_commit)
    cloud = _tree_entries(ledger, cloud_commit)
    policy_conflicts = _policy_conflicts(baseline, local, cloud)

    structural_reasons = {
        "type-change",
        "file-directory-topology",
        "case-unicode-collision",
    }
    structural_conflicts = [
        item for item in policy_conflicts if item["reason"] in structural_reasons
    ]
    if structural_conflicts:
        if merge_path.exists() or merge_path.is_symlink():
            _private_directory(merge_path, "Land review directory")
            if any(merge_path.iterdir()):
                raise LandError("unrecorded Land review directory is not empty")
        else:
            merge_path.mkdir(mode=0o700)
            _fsync_directory(operation_root)
        record = {
            "schemaVersion": 1,
            "outcome": "NEEDS_REVIEW",
            "baselineCommit": baseline_commit,
            "localCommit": local_commit,
            "cloudCommit": cloud_commit,
            "conflicts": structural_conflicts,
            "conflictWorktree": str(merge_path),
            "proposedMergeRef": None,
            "proposedMergeCommit": None,
        }
        _atomic_json(merge_record_path, record)
        return record

    _prepare_worktree(ledger, merge_path, local_commit)
    merge = _run_git(
        [
            "-c",
            "user.name=Lift",
            "-c",
            "user.email=spike@lift.invalid",
            "merge",
            "--no-commit",
            "--no-ff",
            cloud_commit,
        ],
        cwd=merge_path,
        check=False,
    )
    if merge.returncode not in (0, 1):
        raise LandError(
            "isolated Land merge failed: "
            + merge.stderr.decode("utf-8", errors="replace").strip()
        )
    unmerged = [
        value
        for value in _git_text(
            ["diff", "--name-only", "--diff-filter=U", "-z"], cwd=merge_path
        ).split("\0")
        if value
    ]
    combined_conflicts = {
        (item["path"], item["reason"]): item for item in policy_conflicts
    }
    for path in unmerged:
        combined_conflicts[(path, "git-conflict")] = {
            "path": path,
            "reason": "git-conflict",
        }

    if combined_conflicts:
        proposed_ref: str | None = None
        proposed_commit: str | None = None
        if merge.returncode == 0:
            proposed_tree = _git_text(["write-tree"], cwd=merge_path).strip()
            _tree_entries(ledger, proposed_tree)
            proposed_commit = _create_commit(
                ledger,
                tree=proposed_tree,
                parents=[local_commit, cloud_commit],
                message="Preserve proposed Lift Land merge",
            )
            proposed_ref = f"{prefix}/proposed-merge"
            _publish_ref(ledger, proposed_ref, proposed_commit)
        record = {
            "schemaVersion": 1,
            "outcome": "NEEDS_REVIEW",
            "baselineCommit": baseline_commit,
            "localCommit": local_commit,
            "cloudCommit": cloud_commit,
            "conflicts": [combined_conflicts[key] for key in sorted(combined_conflicts)],
            "conflictWorktree": str(merge_path),
            "proposedMergeRef": proposed_ref,
            "proposedMergeCommit": proposed_commit,
        }
        _atomic_json(merge_record_path, record)
        return record

    if merge.returncode != 0:
        raise LandError("Git reported a conflict without identifying an unmerged path")
    merge_tree = _git_text(["write-tree"], cwd=merge_path).strip()
    _tree_entries(ledger, merge_tree)
    merge_commit = _create_commit(
        ledger,
        tree=merge_tree,
        parents=[local_commit, cloud_commit],
        message="Create verified Lift Land merge result",
    )
    merge_ref = f"{prefix}/merge-result"
    _publish_ref(ledger, merge_ref, merge_commit)
    record = {
        "schemaVersion": 1,
        "outcome": "MERGED_CLEAN",
        "baselineCommit": baseline_commit,
        "localCommit": local_commit,
        "cloudCommit": cloud_commit,
        "mergeResultRef": merge_ref,
        "mergeResultCommit": merge_commit,
        "mergeResultTree": merge_tree,
        "manifest": _manifest(_tree_entries(ledger, merge_commit)),
        "mergeWorktree": str(merge_path),
    }
    _atomic_json(merge_record_path, record)
    return record


def _write_private_blob(path: Path, content: bytes) -> None:
    _private_directory(path.parent, "private Land blob directory")
    directory = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        try:
            existing = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                _secure_regular_info(existing, description=f"private Land blob: {path}")
                digest = hashlib.sha256()
                size = 0
                for chunk in iter(lambda: os.read(existing, 1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                if digest.hexdigest() != hashlib.sha256(content).hexdigest() or size != len(
                    content
                ):
                    raise LandError(f"private Land blob already differs: {path}")
            finally:
                os.close(existing)
            return
        descriptor = os.open(
            path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        try:
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise LandError("could not stage complete Land blob")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory)
    finally:
        os.close(directory)


def _read_private_blob(path: Path, expected: dict[str, Any]) -> bytes:
    _private_directory(path.parent, "private Land blob directory")
    directory = os.open(
        path.parent,
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
            info = _secure_regular_info(
                descriptor, description=f"private Land blob: {path}"
            )
            chunks: list[bytes] = []
            remaining = info.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                if not chunk:
                    raise LandError(f"short read from private Land blob: {path}")
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
    content = b"".join(chunks)
    if (
        len(content) != expected["size"]
        or hashlib.sha256(content).hexdigest() != expected["sha256"]
    ):
        raise LandError(f"private Land blob is corrupt: {path}")
    return content


def _entry_content(ledger: Path, entry: dict[str, Any]) -> bytes:
    content = _run_git(
        ["cat-file", "blob", str(entry["gitObjectId"])], git_dir=ledger
    ).stdout
    if hashlib.sha256(content).hexdigest() != entry["sha256"] or len(content) != entry["size"]:
        raise LandError("private Git object no longer matches its Land manifest")
    return content


@contextmanager
def _parent_descriptor(
    root_descriptor: int, relative: PurePosixPath, *, create: bool
) -> Iterator[tuple[int, str]]:
    descriptor = os.dup(root_descriptor)
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(
                    part,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(
                    part,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
            os.close(descriptor)
            descriptor = child
        yield descriptor, relative.name
    finally:
        os.close(descriptor)


def _entry_at(parent_descriptor: int, name: str) -> dict[str, Any] | None:
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISREG(info.st_mode):
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        digest = hashlib.sha256()
        size = 0
        try:
            for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        finally:
            os.close(descriptor)
        return {
            "type": "file",
            "sha256": digest.hexdigest(),
            "size": size,
            "executable": bool(mode & stat.S_IXUSR),
            "target": None,
        }
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(name, dir_fd=parent_descriptor)
        return {
            "type": "symlink",
            "sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
            "size": len(target.encode("utf-8")),
            "executable": False,
            "target": target,
        }
    if stat.S_ISDIR(info.st_mode):
        return {"type": "directory"}
    raise LandError(f"unsupported local file type at {name}")


def _matches_entry(actual: dict[str, Any] | None, expected: dict[str, Any] | None) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    return _entry_identity(actual) == _entry_identity(expected)


def _entry_at_path(path: Path) -> dict[str, Any] | None:
    _private_directory(path.parent, "private Land recovery directory")
    descriptor = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        return _entry_at(descriptor, path.name)
    finally:
        os.close(descriptor)


def _preserve_original(
    *,
    parent_descriptor: int,
    name: str,
    current: dict[str, Any],
    moved_path: Path,
    relative: PurePosixPath,
) -> None:
    _private_directory(moved_path.parent, "private Land recovery directory")
    moved_descriptor = os.open(
        moved_path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if current["type"] not in {"file", "symlink"}:
            raise LandError("Land can preserve only regular files and symbolic links")
        if _entry_at(moved_descriptor, moved_path.name) is not None:
            raise LandError(f"Land recovery destination already exists: {moved_path}")
        try:
            os.rename(
                name,
                moved_path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=moved_descriptor,
            )
        except FileNotFoundError as exc:
            raise _ConcurrentLocalChange(str(relative)) from exc
        except OSError as exc:
            raise LandError(f"could not atomically preserve local path: {relative}") from exc
        os.fsync(moved_descriptor)
        os.fsync(parent_descriptor)
        try:
            preserved = _entry_at(moved_descriptor, moved_path.name)
            visible = _entry_at(parent_descriptor, name)
        except LandError as exc:
            raise _ConcurrentLocalChange(str(relative)) from exc
        if not _matches_entry(preserved, current) or visible is not None:
            raise _ConcurrentLocalChange(str(relative))
    finally:
        os.close(moved_descriptor)


def _install_after(
    *,
    parent_descriptor: int,
    name: str,
    relative: PurePosixPath,
    after: dict[str, Any],
    stage_path: Path,
    temporary_name: str,
) -> None:
    content = _read_private_blob(stage_path, after)
    if after["type"] == "symlink":
        try:
            target = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LandError(f"invalid staged symbolic link at {relative}") from exc
        _validate_symlink_target(relative, target)
        try:
            os.symlink(target, name, dir_fd=parent_descriptor)
        except FileExistsError as exc:
            raise _ConcurrentLocalChange(str(relative)) from exc
        os.fsync(parent_descriptor)
        return
    if after["type"] != "file":
        raise LandError(f"unsupported replacement type at {relative}")
    temporary = _entry_at(parent_descriptor, temporary_name)
    if temporary is not None and not _matches_entry(temporary, after):
        raise LandError(f"cannot prove staged install state for {relative}")
    if temporary is None:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o700 if after["executable"] else 0o600,
            dir_fd=parent_descriptor,
        )
        try:
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise LandError(f"short write while applying {relative}")
                offset += written
            os.fchmod(descriptor, 0o755 if after["executable"] else 0o644)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent_descriptor)
    try:
        os.link(
            temporary_name,
            name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileExistsError as exc:
        raise _ConcurrentLocalChange(str(relative)) from exc
    os.fsync(parent_descriptor)
    os.unlink(temporary_name, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)


def _apply_one(
    *,
    root_descriptor: int,
    operation: dict[str, Any],
    stage_path: Path | None,
    moved_path: Path,
) -> None:
    relative = _safe_path(operation["path"])
    after = operation.get("after")
    before = operation.get("before")
    try:
        context = _parent_descriptor(root_descriptor, relative, create=after is not None)
        with context as (parent_descriptor, name):
            current = _entry_at(parent_descriptor, name)
            moved = _entry_at_path(moved_path)
            temporary_name = operation["temporaryName"]
            temporary = _entry_at(parent_descriptor, temporary_name)
            if temporary is not None and not _matches_entry(temporary, after):
                raise LandError(f"cannot prove staged install state for {relative}")
            if _matches_entry(current, after):
                if temporary is not None:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
                if before is not None and not _matches_entry(moved, before):
                    raise LandError(f"preserved original is missing at {relative}")
                return
            if before is None:
                if moved is not None:
                    raise LandError(f"unexpected recovery entry for new path: {relative}")
                if current is not None:
                    raise LandError(f"local path appeared during Land: {relative}")
            else:
                if moved is not None:
                    if not _matches_entry(moved, before):
                        raise LandError(f"preserved original differs at {relative}")
                    if after is None and current is None:
                        return
                    if _matches_entry(current, before):
                        _preserve_original(
                            parent_descriptor=parent_descriptor,
                            name=name,
                            current=current,
                            moved_path=Path(operation["abandonedPath"]),
                            relative=relative,
                        )
                        current = None
                    if current is not None:
                        raise LandError(f"local path changed during Land: {relative}")
                else:
                    if not _matches_entry(current, before):
                        raise LandError(f"local path changed during Land: {relative}")
                    if current is None:
                        raise LandError(f"local path disappeared during Land: {relative}")
                    _preserve_original(
                        parent_descriptor=parent_descriptor,
                        name=name,
                        current=current,
                        moved_path=moved_path,
                        relative=relative,
                    )
            if after is not None:
                if stage_path is None:
                    raise LandError(f"Land staging payload is missing: {relative}")
                _install_after(
                    parent_descriptor=parent_descriptor,
                    name=name,
                    relative=relative,
                    after=after,
                    stage_path=stage_path,
                    temporary_name=temporary_name,
                )
    except FileNotFoundError as exc:
        raise LandError(f"local path parent disappeared during Land: {relative}") from exc


def _canonical_operations(
    *,
    ledger: Path,
    operation_root: Path,
    local_entries: dict[str, dict[str, Any]],
    merge_entries: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    stage_root = _ensure_private_directory(operation_root / "stage")
    recovery_root = _ensure_private_directory(operation_root / "pre-apply-recovery")
    moved_root = _ensure_private_directory(operation_root / "moved-originals")
    operations: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(set(local_entries) | set(merge_entries))):
        before = local_entries.get(path)
        after = merge_entries.get(path)
        if _entry_identity(before) == _entry_identity(after):
            continue
        if before is not None and after is not None and before["type"] != after["type"]:
            raise LandError(f"Land requires review for a type change: {path}")
        stage_path = stage_root / f"{index:06d}.blob" if after is not None else None
        recovery_path = (
            recovery_root / f"{index:06d}.blob" if before is not None else None
        )
        if stage_path is not None and after is not None:
            _write_private_blob(stage_path, _entry_content(ledger, after))
        if recovery_path is not None and before is not None:
            _write_private_blob(recovery_path, _entry_content(ledger, before))
        path_token = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        operations.append(
            {
                "path": path,
                "before": before,
                "after": after,
                "stagePath": str(stage_path) if stage_path is not None else None,
                "recoveryPath": (
                    str(recovery_path) if recovery_path is not None else None
                ),
                "movedPath": str(moved_root / f"{index:06d}.original"),
                "abandonedPath": str(moved_root / f"{index:06d}.partial"),
                "temporaryName": f".lift-land-{index:06d}-{path_token}.tmp",
            }
        )
    canonical = json.dumps(
        operations, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return operations, hashlib.sha256(canonical).hexdigest()


def _journal_operations(
    journal: dict[str, Any], canonical: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    raw = journal.get("operations")
    if not isinstance(raw, list) or len(raw) != len(canonical):
        raise LandError("persisted apply journal plan differs from canonical B/L/C")
    validated: list[dict[str, Any]] = []
    allowed = {
        "path",
        "before",
        "after",
        "stagePath",
        "recoveryPath",
        "movedPath",
        "abandonedPath",
        "temporaryName",
        "state",
    }
    for persisted, expected in zip(raw, canonical, strict=True):
        if (
            not isinstance(persisted, dict)
            or set(persisted) != allowed
            or persisted.get("state") not in {"PENDING", "INTENT", "APPLIED"}
            or any(persisted.get(key) != value for key, value in expected.items())
        ):
            raise LandError("persisted apply operation is not the canonical B/L/C plan")
        validated.append(persisted)
    return validated


def _prepare_journal(
    *,
    workspace: Path,
    ledger: Path,
    operation_root: Path,
    prefix: str,
    baseline_commit: str,
    local_commit: str,
    cloud_commit: str,
    merge_commit: str,
    original_fingerprint: dict[str, str] | None,
    approved_ignored: tuple[str, ...],
) -> dict[str, Any]:
    journal_path = operation_root / JOURNAL_NAME
    local_entries = _tree_entries(ledger, local_commit)
    merge_entries = _tree_entries(ledger, merge_commit)
    operations, plan_sha = _canonical_operations(
        ledger=ledger,
        operation_root=operation_root,
        local_entries=local_entries,
        merge_entries=merge_entries,
    )
    canonical_fields: dict[str, Any] = {
        "schemaVersion": 1,
        "workspace": str(workspace),
        "sessionPrefix": prefix,
        "baselineCommit": baseline_commit,
        "localCommit": local_commit,
        "cloudCommit": cloud_commit,
        "mergeCommit": merge_commit,
        "localManifest": _manifest(local_entries),
        "mergeManifest": _manifest(merge_entries),
        "planSha256": plan_sha,
        "localGitHistory": _local_git_history_record(
            ledger=ledger,
            prefix=prefix,
            baseline_commit=baseline_commit,
            local_commit=local_commit,
        ),
    }
    if journal_path.exists() or journal_path.is_symlink():
        journal: dict[str, Any] | None = None
        try:
            journal = _read_json(journal_path)
            if any(journal.get(key) != value for key, value in canonical_fields.items()):
                raise LandError("persisted apply journal differs from canonical B/L/C")
            if journal.get("phase") not in {
                "PREPARED",
                "APPLYING",
                "VERIFIED",
                "ROLLED_BACK",
            }:
                raise LandError("apply journal has an invalid phase")
            fingerprint = journal.get("originalGitFingerprint")
            if not isinstance(fingerprint, dict):
                raise LandError("apply journal omitted the original Git fingerprint")
            _journal_operations(journal, operations)
        except LandError:
            _rollback_to_local(
                workspace=workspace,
                canonical=operations,
                journal=journal,
            )
            raise
        return journal

    if original_fingerprint is None:
        raise LandError("a new apply journal requires the captured local Git state")
    if not _workspace_matches(workspace, approved_ignored, local_entries):
        raise LandError("local workspace changed after its return snapshot")
    if workspace_state_fingerprint(workspace) != original_fingerprint:
        raise LandError("local Git state changed after its return snapshot")
    journal = {
        **canonical_fields,
        "phase": "PREPARED",
        "originalGitFingerprint": original_fingerprint,
        "operations": [operation | {"state": "PENDING"} for operation in operations],
        "preparedAt": now_iso(),
    }
    _atomic_json(journal_path, journal)
    return journal


def _operation_observation(
    root_descriptor: int, operation: dict[str, Any]
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    relative = _safe_path(operation["path"])
    try:
        with _parent_descriptor(root_descriptor, relative, create=False) as (
            parent_descriptor,
            name,
        ):
            current = _entry_at(parent_descriptor, name)
            temporary = _entry_at(parent_descriptor, operation["temporaryName"])
    except FileNotFoundError:
        current = None
        temporary = None
    return current, _entry_at_path(Path(operation["movedPath"])), temporary


def _validate_partial_state(
    *, root_descriptor: int, journal: dict[str, Any]
) -> None:
    operations = journal["operations"]
    phase = journal["phase"]
    states = [operation["state"] for operation in operations]
    if phase == "PREPARED" and any(state != "PENDING" for state in states):
        raise LandError("a prepared journal cannot contain an applied operation")
    if phase == "VERIFIED" and any(state != "APPLIED" for state in states):
        raise LandError("a verified journal must contain only applied operations")
    if phase not in {"PREPARED", "APPLYING", "VERIFIED"}:
        raise LandError("apply journal cannot be resumed from this phase")
    seen_intent = False
    seen_pending = False
    for operation in operations:
        state = operation["state"]
        if state == "APPLIED" and (seen_intent or seen_pending):
            raise LandError("apply journal state order is impossible")
        if state == "INTENT":
            if seen_intent or seen_pending:
                raise LandError("apply journal contains multiple or reordered intents")
            seen_intent = True
        if state == "PENDING":
            seen_pending = True
        before = operation["before"]
        after = operation["after"]
        current, moved, temporary = _operation_observation(root_descriptor, operation)
        if state == "PENDING":
            valid = (
                _matches_entry(current, before)
                and moved is None
                and temporary is None
            )
        elif state == "APPLIED":
            valid = _matches_entry(current, after) and (
                _matches_entry(moved, before) if before is not None else moved is None
            ) and temporary is None
        elif before is None:
            valid = moved is None and (
                current is None or _matches_entry(current, after)
            ) and (temporary is None or _matches_entry(temporary, after))
        else:
            valid = (
                _matches_entry(current, before)
                and moved is None
                and temporary is None
            ) or (
                _matches_entry(moved, before)
                and (
                    current is None
                    or _matches_entry(current, before)
                    or _matches_entry(current, after)
                )
                and (temporary is None or _matches_entry(temporary, after))
            )
        if not valid:
            raise _ConcurrentLocalChange(operation["path"])


def _restore_from_moved(
    *,
    parent_descriptor: int,
    name: str,
    before: dict[str, Any],
    moved_path: Path,
) -> None:
    moved_descriptor = os.open(
        moved_path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        try:
            if before["type"] == "file":
                os.link(
                    moved_path.name,
                    name,
                    src_dir_fd=moved_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            else:
                target = os.readlink(moved_path.name, dir_fd=moved_descriptor)
                os.symlink(target, name, dir_fd=parent_descriptor)
        except FileExistsError as exc:
            raise LandError("local path appeared while rolling Land back") from exc
        os.fsync(parent_descriptor)
        os.unlink(moved_path.name, dir_fd=moved_descriptor)
        os.fsync(moved_descriptor)
    finally:
        os.close(moved_descriptor)


def _recover_concurrent_operation(
    *,
    parent_descriptor: int,
    name: str,
    relative: PurePosixPath,
    operation: dict[str, Any],
    current: dict[str, Any] | None,
    moved: dict[str, Any] | None,
    temporary: dict[str, Any] | None,
) -> None:
    """Keep racing user bytes visible when possible and recoverable otherwise."""

    after = operation["after"]
    abandoned_path = Path(operation["abandonedPath"])
    if temporary is not None and _matches_entry(temporary, after):
        if _entry_at_path(abandoned_path) is None:
            try:
                _preserve_original(
                    parent_descriptor=parent_descriptor,
                    name=operation["temporaryName"],
                    current=temporary,
                    moved_path=abandoned_path,
                    relative=relative,
                )
            except LandError:
                # A second race remains in the workspace or in private recovery.
                pass

    before = operation["before"]
    if moved is None or _matches_entry(moved, before):
        return
    if moved.get("type") not in {"file", "symlink"}:
        return

    if _matches_entry(current, after):
        if _entry_at_path(abandoned_path) is not None:
            return
        try:
            _preserve_original(
                parent_descriptor=parent_descriptor,
                name=name,
                current=current,
                moved_path=abandoned_path,
                relative=relative,
            )
        except LandError:
            # Never overwrite a second racing value; both copies remain recoverable.
            return
        current = None
    if current is not None:
        return
    try:
        _restore_from_moved(
            parent_descriptor=parent_descriptor,
            name=name,
            before=moved,
            moved_path=Path(operation["movedPath"]),
        )
    except LandError:
        # A recreated workspace name wins; the raced bytes remain in recovery.
        pass


def _rollback_to_local(
    *,
    workspace: Path,
    canonical: list[dict[str, Any]],
    journal: dict[str, Any] | None,
    preserve_paths: set[str] | None = None,
) -> None:
    preserve_paths = preserve_paths or set()
    root_descriptor = os.open(
        workspace,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for index in range(len(canonical) - 1, -1, -1):
            operation = canonical[index]
            relative = _safe_path(operation["path"])
            before = operation["before"]
            after = operation["after"]
            moved_path = Path(operation["movedPath"])
            try:
                context = _parent_descriptor(
                    root_descriptor, relative, create=before is not None
                )
                with context as (parent_descriptor, name):
                    current = _entry_at(parent_descriptor, name)
                    moved = _entry_at_path(moved_path)
                    temporary_name = operation["temporaryName"]
                    temporary = _entry_at(parent_descriptor, temporary_name)
                    state: str | None = None
                    if journal is not None:
                        raw_operations = journal.get("operations")
                        if isinstance(raw_operations, list) and index < len(raw_operations):
                            persisted = raw_operations[index]
                            if (
                                isinstance(persisted, dict)
                                and persisted.get("path") == operation["path"]
                                and persisted.get("state")
                                in {"PENDING", "INTENT", "APPLIED"}
                            ):
                                state = persisted["state"]
                    if operation["path"] in preserve_paths:
                        _recover_concurrent_operation(
                            parent_descriptor=parent_descriptor,
                            name=name,
                            relative=relative,
                            operation=operation,
                            current=current,
                            moved=moved,
                            temporary=temporary,
                        )
                        continue
                    if temporary is not None:
                        if state not in {"INTENT", "APPLIED"} or temporary.get(
                            "type"
                        ) != "file":
                            raise LandError(
                                f"refusing to remove an unproven temporary at {relative}"
                            )
                        abandoned_path = Path(operation["abandonedPath"])
                        abandoned = _entry_at_path(abandoned_path)
                        if abandoned is None:
                            _preserve_original(
                                parent_descriptor=parent_descriptor,
                                name=temporary_name,
                                current=temporary,
                                moved_path=abandoned_path,
                                relative=relative,
                            )
                        elif _matches_entry(abandoned, temporary):
                            os.unlink(temporary_name, dir_fd=parent_descriptor)
                            os.fsync(parent_descriptor)
                        else:
                            raise LandError(
                                f"abandoned install evidence differs at {relative}"
                            )
                    if before is None:
                        if current is None:
                            continue
                        if not _matches_entry(current, after):
                            raise LandError(
                                f"refusing to overwrite user change during rollback: {relative}"
                            )
                        os.unlink(name, dir_fd=parent_descriptor)
                        os.fsync(parent_descriptor)
                        continue
                    if _matches_entry(current, before):
                        if moved is not None:
                            if not _matches_entry(moved, before):
                                raise LandError(
                                    f"recovery original differs during rollback: {relative}"
                                )
                            moved_path.unlink()
                            _fsync_directory(moved_path.parent)
                        continue
                    if current is not None and not _matches_entry(current, after):
                        raise LandError(
                            f"refusing to overwrite user change during rollback: {relative}"
                        )
                    if current is not None:
                        os.unlink(name, dir_fd=parent_descriptor)
                        os.fsync(parent_descriptor)
                    if moved is not None:
                        if not _matches_entry(moved, before):
                            raise LandError(
                                f"recovery original differs during rollback: {relative}"
                            )
                        _restore_from_moved(
                            parent_descriptor=parent_descriptor,
                            name=name,
                            before=before,
                            moved_path=moved_path,
                        )
                    else:
                        recovery = operation.get("recoveryPath")
                        if not isinstance(recovery, str):
                            raise LandError(f"missing rollback payload for {relative}")
                        _install_after(
                            parent_descriptor=parent_descriptor,
                            name=name,
                            relative=relative,
                            after=before,
                            stage_path=Path(recovery),
                            temporary_name=temporary_name,
                        )
            except FileNotFoundError:
                if before is not None:
                    raise LandError(f"cannot restore missing parent for {relative}")
    finally:
        os.close(root_descriptor)
    if journal is not None:
        journal["phase"] = "ROLLED_BACK"
        journal["rolledBackAt"] = now_iso()


def _validate_preserved_originals(journal: dict[str, Any]) -> None:
    for operation in journal["operations"]:
        before = operation["before"]
        moved = _entry_at_path(Path(operation["movedPath"]))
        if before is None:
            if moved is not None:
                raise _ConcurrentLocalChange(operation["path"])
        elif not _matches_entry(moved, before):
            raise _ConcurrentLocalChange(operation["path"])


def _apply_journal(
    *,
    workspace: Path,
    ledger: Path,
    operation_root: Path,
    approved_ignored: tuple[str, ...],
    journal: dict[str, Any],
    fail_after_apply: int | None,
) -> dict[str, Any]:
    del ledger
    journal_path = operation_root / JOURNAL_NAME
    if journal.get("phase") == "ROLLED_BACK":
        raise LandError("interrupted Land was rolled back and requires a new operation")
    original_fingerprint = journal["originalGitFingerprint"]
    canonical = [
        {key: value for key, value in operation.items() if key != "state"}
        for operation in journal["operations"]
    ]
    root_descriptor = os.open(
        workspace,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        try:
            _validate_partial_state(root_descriptor=root_descriptor, journal=journal)
        except _ConcurrentLocalChange as exc:
            os.close(root_descriptor)
            root_descriptor = -1
            _rollback_to_local(
                workspace=workspace,
                canonical=canonical,
                journal=journal,
                preserve_paths={exc.path},
            )
            _atomic_json(journal_path, journal)
            raise
        except LandError:
            os.close(root_descriptor)
            root_descriptor = -1
            _rollback_to_local(
                workspace=workspace, canonical=canonical, journal=journal
            )
            _atomic_json(journal_path, journal)
            raise
        if not _git_admin_matches(
            workspace_state_fingerprint(workspace), original_fingerprint
        ):
            os.close(root_descriptor)
            root_descriptor = -1
            _rollback_to_local(
                workspace=workspace, canonical=canonical, journal=journal
            )
            _atomic_json(journal_path, journal)
            raise LandError("the user's branch, refs, or index changed during Land")
        if journal["phase"] == "PREPARED":
            if _normalize_workspace_manifest(
                content_manifest(workspace, approved_ignored)
            ) != journal["localManifest"]:
                raise LandError("local workspace changed before transactional apply")
            journal["phase"] = "APPLYING"
            journal["applyStartedAt"] = now_iso()
            _atomic_json(journal_path, journal)

        applied_this_run = 0
        for operation in journal["operations"]:
            if operation["state"] == "APPLIED":
                continue
            if operation["state"] == "PENDING":
                operation["state"] = "INTENT"
                _atomic_json(journal_path, journal)
            try:
                _apply_one(
                    root_descriptor=root_descriptor,
                    operation=operation,
                    stage_path=(
                        Path(operation["stagePath"])
                        if operation["stagePath"] is not None
                        else None
                    ),
                    moved_path=Path(operation["movedPath"]),
                )
            except _ConcurrentLocalChange as exc:
                os.close(root_descriptor)
                root_descriptor = -1
                _rollback_to_local(
                    workspace=workspace,
                    canonical=canonical,
                    journal=journal,
                    preserve_paths={exc.path},
                )
                _atomic_json(journal_path, journal)
                raise
            except LandError:
                os.close(root_descriptor)
                root_descriptor = -1
                _rollback_to_local(
                    workspace=workspace, canonical=canonical, journal=journal
                )
                _atomic_json(journal_path, journal)
                raise
            applied_this_run += 1
            if fail_after_apply is not None and applied_this_run == fail_after_apply:
                raise LandError("injected failure after atomic Land replacement")
            operation["state"] = "APPLIED"
            _atomic_json(journal_path, journal)
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)

    # Unchanged entries are not operations, so use the recorded canonical manifest here.
    expected_manifest = journal["mergeManifest"]
    if _normalize_workspace_manifest(
        content_manifest(workspace, approved_ignored)
    ) != expected_manifest:
        _rollback_to_local(workspace=workspace, canonical=canonical, journal=journal)
        _atomic_json(journal_path, journal)
        raise LandError("transactional Land result did not match the merge manifest")
    if not _git_admin_matches(
        workspace_state_fingerprint(workspace), original_fingerprint
    ):
        _rollback_to_local(workspace=workspace, canonical=canonical, journal=journal)
        _atomic_json(journal_path, journal)
        raise LandError("Land changed the user's branch, refs, or real index")
    try:
        _validate_preserved_originals(journal)
    except _ConcurrentLocalChange as exc:
        _rollback_to_local(
            workspace=workspace,
            canonical=canonical,
            journal=journal,
            preserve_paths={exc.path},
        )
        _atomic_json(journal_path, journal)
        raise
    journal["phase"] = "VERIFIED"
    journal.setdefault("verifiedAt", now_iso())
    _atomic_json(journal_path, journal)
    return journal


def _write_receipt(
    *,
    ledger: Path,
    operation_root: Path,
    prefix: str,
    baseline_commit: str,
    local_commit: str,
    cloud_commit: str,
    merge_commit: str,
    acknowledged_at: str,
) -> dict[str, Any]:
    receipt_path = operation_root / RECEIPT_NAME
    receipt_ref = f"{prefix}/land-receipt"
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "acknowledgedAt": acknowledged_at,
        "baselineCommit": baseline_commit,
        "localCommit": local_commit,
        "cloudCommit": cloud_commit,
        "mergeCommit": merge_commit,
        "mergeTree": _commit_tree(ledger, merge_commit),
        "localGitHistory": _local_git_history_record(
            ledger=ledger,
            prefix=prefix,
            baseline_commit=baseline_commit,
            local_commit=local_commit,
        ),
        "receiptRef": receipt_ref,
    }
    document_bytes = (
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    receipt_sha = hashlib.sha256(document_bytes).hexdigest()
    receipt_blob = _git_text(
        ["hash-object", "-w", "--stdin"],
        git_dir=ledger,
        input_text=document_bytes.decode("utf-8"),
    ).strip()
    if OBJECT_ID.fullmatch(receipt_blob) is None:
        raise LandError("Git returned an invalid receipt blob ID")
    tree_input = f"100644 blob {receipt_blob}\t{RECEIPT_NAME}\0".encode("utf-8")
    receipt_tree = _run_git(
        ["mktree", "-z"], git_dir=ledger, input_bytes=tree_input
    ).stdout.decode("ascii").strip()
    if OBJECT_ID.fullmatch(receipt_tree) is None:
        raise LandError("Git returned an invalid receipt tree ID")
    receipt_commit = _create_commit(
        ledger,
        tree=receipt_tree,
        parents=[merge_commit],
        message=f"Seal Lift Land receipt\n\nReceipt-SHA256: {receipt_sha}",
    )
    _publish_ref(ledger, receipt_ref, receipt_commit)
    if _commit_tree(ledger, receipt_commit) != receipt_tree:
        raise LandError("Land receipt commit tree differs")
    parents = _git_text(
        ["show", "-s", "--format=%P", receipt_commit], git_dir=ledger
    ).strip()
    if parents != merge_commit:
        raise LandError("Land receipt commit has an unexpected parent")
    tree_listing = _run_git(
        ["ls-tree", "-z", receipt_tree], git_dir=ledger
    ).stdout
    if tree_listing != tree_input:
        raise LandError("Land receipt tree contains unexpected entries")
    stored_document = _run_git(
        ["cat-file", "blob", receipt_blob], git_dir=ledger
    ).stdout
    if stored_document != document_bytes:
        raise LandError("Land receipt payload differs from its Git blob")
    receipt = {
        **document,
        "receiptSha256": receipt_sha,
        "receiptBlob": receipt_blob,
        "receiptTree": receipt_tree,
        "receiptCommit": receipt_commit,
    }
    if receipt_path.exists() or receipt_path.is_symlink():
        if _read_json(receipt_path) != receipt:
            raise LandError("immutable Land receipt record differs from private Git")
    else:
        _atomic_json(receipt_path, receipt)
    return receipt


def _completed_result(
    *,
    ledger: Path,
    operation_root: Path,
    prefix: str,
    baseline_ref: str,
    baseline_commit: str,
    cloud_commit: str,
) -> dict[str, Any] | None:
    result_path = operation_root / RESULT_NAME
    if not result_path.exists():
        return None
    result = _read_json(result_path)
    if result.get("schemaVersion") != 1:
        raise LandError("completed Land result has an invalid schema")
    outcome = result.get("outcome")
    if outcome == "APPLIED":
        journal = _read_json(operation_root / JOURNAL_NAME)
        merge_commit = _resolve_commit(ledger, f"{prefix}/merge-result")
        expected = {
            "baselineRef": baseline_ref,
            "baselineCommit": baseline_commit,
            "cloudFinalRef": f"{prefix}/cloud-final",
            "cloudFinalCommit": cloud_commit,
            "localReturnRef": f"{prefix}/local-return",
            "localReturnCommit": journal.get("localCommit"),
            "mergeResultRef": f"{prefix}/merge-result",
            "mergeResultCommit": merge_commit,
            "receiptRef": f"{prefix}/land-receipt",
            "applyJournal": str(operation_root / JOURNAL_NAME),
            "recoveryRoot": str(operation_root / "pre-apply-recovery"),
            "localGitHistory": _local_git_history_record(
                ledger=ledger,
                prefix=prefix,
                baseline_commit=baseline_commit,
                local_commit=str(journal.get("localCommit")),
                claimed=journal.get("localGitHistory"),
            ),
        }
        if (
            journal.get("phase") != "VERIFIED"
            or any(result.get(key) != value for key, value in expected.items())
            or result.get("verifiedAt") != journal.get("verifiedAt")
        ):
            raise LandError("completed Land result differs from its verified journal")
        receipt = _write_receipt(
            ledger=ledger,
            operation_root=operation_root,
            prefix=prefix,
            baseline_commit=baseline_commit,
            local_commit=str(journal["localCommit"]),
            cloud_commit=cloud_commit,
            merge_commit=merge_commit,
            acknowledged_at=str(journal["verifiedAt"]),
        )
        if result.get("receiptCommit") != receipt["receiptCommit"]:
            raise LandError("completed Land result differs from its durable receipt")
    elif outcome == "NEEDS_REVIEW":
        merge_record = _read_json(operation_root / MERGE_NAME)
        local_commit = _resolve_commit(ledger, f"{prefix}/local-return")
        conflict_path = operation_root / "merge-worktree"
        expected = {
            "baselineRef": baseline_ref,
            "baselineCommit": baseline_commit,
            "cloudFinalRef": f"{prefix}/cloud-final",
            "cloudFinalCommit": cloud_commit,
            "localReturnRef": f"{prefix}/local-return",
            "localReturnCommit": local_commit,
            "conflicts": merge_record.get("conflicts"),
            "conflictWorktree": str(conflict_path),
            "proposedMergeRef": merge_record.get("proposedMergeRef"),
            "proposedMergeCommit": merge_record.get("proposedMergeCommit"),
            "localGitHistory": _local_git_history_record(
                ledger=ledger,
                prefix=prefix,
                baseline_commit=baseline_commit,
                local_commit=local_commit,
            ),
        }
        if (
            merge_record.get("schemaVersion") != 1
            or merge_record.get("outcome") != "NEEDS_REVIEW"
            or merge_record.get("baselineCommit") != baseline_commit
            or merge_record.get("localCommit") != local_commit
            or merge_record.get("cloudCommit") != cloud_commit
            or any(result.get(key) != value for key, value in expected.items())
        ):
            raise LandError("completed conflict result differs from its merge record")
        proposed_ref = merge_record.get("proposedMergeRef")
        proposed_commit = merge_record.get("proposedMergeCommit")
        if (proposed_ref is None) != (proposed_commit is None):
            raise LandError("completed conflict result has incomplete proposed merge evidence")
        if proposed_ref is not None and (
            proposed_ref != f"{prefix}/proposed-merge"
            or _resolve_commit(ledger, proposed_ref) != proposed_commit
        ):
            raise LandError("completed conflict proposed merge ref differs")
        if result.get("conflictWorktree") != str(conflict_path):
            raise LandError("completed conflict result has a non-canonical path")
        try:
            _private_directory(conflict_path, "preserved conflict worktree")
        except LandError:
            raise LandError("completed conflict result lost its preserved worktree")
    else:
        raise LandError("completed Land result has an invalid outcome")
    return result


def _land_fixture_locked(
    *,
    workspace: Path,
    ledger: Path,
    run_id: str,
    workspace_id: str,
    baseline_ref: str,
    baseline_commit: str,
    cloud_ref: str,
    cloud_commit: str,
    approved_ignored: Iterable[str],
    operation_root: Path,
    fail_after_apply: int | None = None,
) -> dict[str, Any]:
    """Land one generated fixture without touching the user's Git administration state."""

    prefix = _validate_identity(run_id, workspace_id)
    approved_ignored = tuple(approved_ignored)

    baseline_commit = _resolve_commit(ledger, baseline_commit)
    cloud_commit = _resolve_commit(ledger, cloud_commit)
    if baseline_ref != f"{prefix}/baseline":
        raise LandError("Land baseline ref is outside the canonical session namespace")
    cloud_suffix = cloud_ref.removeprefix(f"{prefix}/checkpoints/")
    if (
        cloud_ref == cloud_suffix
        or re.fullmatch(r"[0-9]{4}-land-final", cloud_suffix) is None
    ):
        raise LandError("Land cloud ref is not the canonical final checkpoint")
    if _resolve_commit(ledger, baseline_ref) != baseline_commit:
        raise LandError("Land baseline ref does not match the expected commit")
    if _resolve_commit(ledger, cloud_ref) != cloud_commit:
        raise LandError("Land cloud ref does not match the final checkpoint")
    if _run_git(
        ["merge-base", "--is-ancestor", baseline_commit, cloud_commit],
        git_dir=ledger,
        check=False,
    ).returncode != 0:
        raise LandError("final cloud checkpoint is not descended from the handoff baseline")
    try:
        fixture_policy = fixture_policy_for_commit(ledger, baseline_commit)
    except WorkspaceError as exc:
        raise LandError("handoff baseline fixture policy is invalid") from exc
    baseline_entries = _tree_entries(ledger, baseline_commit)
    cloud_entries = _tree_entries(ledger, cloud_commit)
    _validate_fixture_tree_policy(
        ledger=ledger,
        commit=baseline_commit,
        expected_policy=fixture_policy,
        entries=baseline_entries,
        description="handoff baseline",
    )
    _validate_fixture_tree_policy(
        ledger=ledger,
        commit=cloud_commit,
        expected_policy=fixture_policy,
        entries=cloud_entries,
        description="final cloud checkpoint",
    )

    cloud_final_ref = f"{prefix}/cloud-final"
    _publish_ref(ledger, cloud_final_ref, cloud_commit)
    existing_result = _completed_result(
        ledger=ledger,
        operation_root=operation_root,
        prefix=prefix,
        baseline_ref=baseline_ref,
        baseline_commit=baseline_commit,
        cloud_commit=cloud_commit,
    )
    if existing_result is not None:
        return existing_result

    journal_path = operation_root / JOURNAL_NAME
    if journal_path.exists() or journal_path.is_symlink():
        local_ref = f"{prefix}/local-return"
        local_commit = _resolve_commit(ledger, local_ref)
        merge_commit = _resolve_commit(ledger, f"{prefix}/merge-result")
        journal = _prepare_journal(
            workspace=workspace,
            ledger=ledger,
            operation_root=operation_root,
            prefix=prefix,
            baseline_commit=baseline_commit,
            local_commit=local_commit,
            cloud_commit=cloud_commit,
            merge_commit=merge_commit,
            original_fingerprint=None,
            approved_ignored=approved_ignored,
        )
        try:
            merge_record = _merge_snapshots(
                ledger=ledger,
                operation_root=operation_root,
                prefix=prefix,
                baseline_commit=baseline_commit,
                local_commit=local_commit,
                cloud_commit=cloud_commit,
            )
            if merge_record.get("outcome") != "MERGED_CLEAN":
                raise LandError("an apply journal cannot belong to a review-only merge")
        except LandError:
            canonical = [
                {key: value for key, value in operation.items() if key != "state"}
                for operation in journal["operations"]
            ]
            _rollback_to_local(
                workspace=workspace, canonical=canonical, journal=journal
            )
            _atomic_json(journal_path, journal)
            raise
        applied = _apply_journal(
            workspace=workspace,
            ledger=ledger,
            operation_root=operation_root,
            approved_ignored=approved_ignored,
            journal=journal,
            fail_after_apply=fail_after_apply,
        )
        receipt = _write_receipt(
            ledger=ledger,
            operation_root=operation_root,
            prefix=prefix,
            baseline_commit=baseline_commit,
            local_commit=local_commit,
            cloud_commit=cloud_commit,
            merge_commit=merge_commit,
            acknowledged_at=applied["verifiedAt"],
        )
        result = {
            "schemaVersion": 1,
            "outcome": "APPLIED",
            "baselineRef": baseline_ref,
            "baselineCommit": baseline_commit,
            "cloudFinalRef": cloud_final_ref,
            "cloudFinalCommit": cloud_commit,
            "localReturnRef": f"{prefix}/local-return",
            "localReturnCommit": local_commit,
            "mergeResultRef": merge_record["mergeResultRef"],
            "mergeResultCommit": merge_commit,
            "receiptRef": receipt["receiptRef"],
            "receiptCommit": receipt["receiptCommit"],
            "applyJournal": str(journal_path),
            "recoveryRoot": str(operation_root / "pre-apply-recovery"),
            "verifiedAt": applied["verifiedAt"],
            "localGitHistory": journal["localGitHistory"],
        }
        _atomic_json(operation_root / RESULT_NAME, result)
        return result

    local_ref = f"{prefix}/local-return"
    try:
        local_capture = capture_fixture_snapshot(
            workspace=workspace,
            ledger=ledger,
            run_id=run_id,
            workspace_id=workspace_id,
            parent_commit=baseline_commit,
            ref_name=local_ref,
            message="Capture returning local fixture for Lift Land",
            approved_ignored=approved_ignored,
        )
    except WorkspaceError as exc:
        raise LandError(str(exc)) from exc
    local_git_history = _local_git_history_record(
        ledger=ledger,
        prefix=prefix,
        baseline_commit=baseline_commit,
        local_commit=local_capture.commit,
        claimed=local_capture.git_history,
    )

    merge_record = _merge_snapshots(
        ledger=ledger,
        operation_root=operation_root,
        prefix=prefix,
        baseline_commit=baseline_commit,
        local_commit=local_capture.commit,
        cloud_commit=cloud_commit,
    )
    if merge_record["outcome"] == "NEEDS_REVIEW":
        result = {
            "schemaVersion": 1,
            "outcome": "NEEDS_REVIEW",
            "baselineRef": baseline_ref,
            "baselineCommit": baseline_commit,
            "cloudFinalRef": cloud_final_ref,
            "cloudFinalCommit": cloud_commit,
            "localReturnRef": local_ref,
            "localReturnCommit": local_capture.commit,
            "conflicts": merge_record["conflicts"],
            "conflictWorktree": merge_record["conflictWorktree"],
            "proposedMergeRef": merge_record.get("proposedMergeRef"),
            "proposedMergeCommit": merge_record.get("proposedMergeCommit"),
            "localGitHistory": local_git_history,
        }
        _atomic_json(operation_root / RESULT_NAME, result)
        return result

    journal = _prepare_journal(
        workspace=workspace,
        ledger=ledger,
        operation_root=operation_root,
        prefix=prefix,
        baseline_commit=baseline_commit,
        local_commit=local_capture.commit,
        cloud_commit=cloud_commit,
        merge_commit=merge_record["mergeResultCommit"],
        original_fingerprint=local_capture.original,
        approved_ignored=approved_ignored,
    )
    applied = _apply_journal(
        workspace=workspace,
        ledger=ledger,
        operation_root=operation_root,
        approved_ignored=approved_ignored,
        journal=journal,
        fail_after_apply=fail_after_apply,
    )
    receipt = _write_receipt(
        ledger=ledger,
        operation_root=operation_root,
        prefix=prefix,
        baseline_commit=baseline_commit,
        local_commit=local_capture.commit,
        cloud_commit=cloud_commit,
        merge_commit=merge_record["mergeResultCommit"],
        acknowledged_at=applied["verifiedAt"],
    )
    result = {
        "schemaVersion": 1,
        "outcome": "APPLIED",
        "baselineRef": baseline_ref,
        "baselineCommit": baseline_commit,
        "cloudFinalRef": cloud_final_ref,
        "cloudFinalCommit": cloud_commit,
        "localReturnRef": local_ref,
        "localReturnCommit": local_capture.commit,
        "mergeResultRef": merge_record["mergeResultRef"],
        "mergeResultCommit": merge_record["mergeResultCommit"],
        "receiptRef": receipt["receiptRef"],
        "receiptCommit": receipt["receiptCommit"],
        "applyJournal": str(operation_root / JOURNAL_NAME),
        "recoveryRoot": str(operation_root / "pre-apply-recovery"),
        "verifiedAt": applied["verifiedAt"],
        "localGitHistory": journal["localGitHistory"],
    }
    _atomic_json(operation_root / RESULT_NAME, result)
    return result


def land_fixture(
    *,
    workspace: Path,
    ledger: Path,
    run_id: str,
    workspace_id: str,
    baseline_ref: str,
    baseline_commit: str,
    cloud_ref: str,
    cloud_commit: str,
    approved_ignored: Iterable[str],
    operation_root: Path,
    fail_after_apply: int | None = None,
) -> dict[str, Any]:
    """Land one generated fixture without touching the user's Git administration state."""

    prefix = _validate_identity(run_id, workspace_id)
    workspace = _physical_directory(workspace, "local fixture workspace")
    ledger = _physical_directory(ledger, "Lift-private ledger")
    approved = tuple(approved_ignored)
    validate_fixture_policy(workspace, approved)
    operation_root = _prepare_operation_root(
        operation_root=operation_root,
        workspace=workspace,
        ledger=ledger,
        prefix=prefix,
    )
    with _operation_lock(operation_root):
        operation_root = _prepare_operation_root(
            operation_root=operation_root,
            workspace=workspace,
            ledger=ledger,
            prefix=prefix,
        )
        return _land_fixture_locked(
            workspace=workspace,
            ledger=ledger,
            run_id=run_id,
            workspace_id=workspace_id,
            baseline_ref=baseline_ref,
            baseline_commit=baseline_commit,
            cloud_ref=cloud_ref,
            cloud_commit=cloud_commit,
            approved_ignored=approved,
            operation_root=operation_root,
            fail_after_apply=fail_after_apply,
        )


def validate_conflicted_land_fixture(
    *,
    workspace: Path,
    ledger: Path,
    run_id: str,
    workspace_id: str,
    baseline_ref: str,
    baseline_commit: str,
    cloud_ref: str,
    cloud_commit: str,
    approved_ignored: Iterable[str],
    operation_root: Path,
) -> dict[str, Any]:
    """Revalidate an existing review hold without reconstructing missing state."""

    prefix = _validate_identity(run_id, workspace_id)
    workspace = _physical_directory(workspace, "local fixture workspace")
    ledger = _physical_directory(ledger, "Lift-private ledger")
    approved = tuple(approved_ignored)
    validate_fixture_policy(workspace, approved)

    operation_root = operation_root.absolute()
    if (
        operation_root == workspace
        or workspace in operation_root.parents
        or operation_root in workspace.parents
        or operation_root == ledger
        or ledger in operation_root.parents
        or operation_root in ledger.parents
    ):
        raise LandError(
            "Land operation state cannot contain the workspace or private ledger"
        )
    operation_root = _private_directory(
        operation_root, "existing conflict operation directory"
    )
    if operation_root.stat().st_dev != workspace.stat().st_dev:
        raise LandError("Land operation state must share the workspace filesystem")

    expected_identity = {
        "schemaVersion": 1,
        "workspace": str(workspace),
        "ledger": str(ledger),
        "sessionPrefix": prefix,
    }
    if _read_json(operation_root / IDENTITY_NAME) != expected_identity:
        raise LandError("Land operation directory belongs to another operation")
    result = _read_json(operation_root / RESULT_NAME)
    if result.get("outcome") != "NEEDS_REVIEW":
        raise LandError("cached Land operation is not a conflict result")
    merge = _read_json(operation_root / MERGE_NAME)
    if merge.get("outcome") != "NEEDS_REVIEW":
        raise LandError("cached Land merge is not a conflict result")
    for forbidden_name in (JOURNAL_NAME, RECEIPT_NAME):
        forbidden = operation_root / forbidden_name
        if forbidden.exists() or forbidden.is_symlink():
            raise LandError("conflicted Land operation contains apply-only state")

    lock_path = operation_root / LOCK_NAME
    directory = os.open(
        operation_root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        try:
            descriptor = os.open(
                lock_path.name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
        except OSError as exc:
            raise LandError("cached Land operation lost its lifecycle lock") from exc
        try:
            _secure_regular_info(
                descriptor, description="cached Land operation lock", max_size=0
            )
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)

    cloud_final_ref = f"{prefix}/cloud-final"
    if _resolve_commit(ledger, cloud_final_ref) != cloud_commit:
        raise LandError("cached Land cloud-final ref differs")

    with _operation_lock(operation_root):
        verified = _land_fixture_locked(
            workspace=workspace,
            ledger=ledger,
            run_id=run_id,
            workspace_id=workspace_id,
            baseline_ref=baseline_ref,
            baseline_commit=baseline_commit,
            cloud_ref=cloud_ref,
            cloud_commit=cloud_commit,
            approved_ignored=approved,
            operation_root=operation_root,
        )
    if verified.get("outcome") != "NEEDS_REVIEW":
        raise LandError("cached Land operation is no longer a conflict result")
    return verified
