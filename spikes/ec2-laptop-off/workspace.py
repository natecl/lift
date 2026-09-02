"""Disposable workspace fixture and Lift-private Git capture primitives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import tempfile
from typing import Iterable


FIXTURE_MARKER_PATH = ".lift-spike-fixture.json"


class WorkspaceError(RuntimeError):
    pass


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    replace_env: bool = False,
) -> str:
    merged_environment = {} if replace_env else os.environ.copy()
    if env is not None:
        merged_environment.update(env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=merged_environment,
        input=input_text,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise WorkspaceError(
            f"command failed ({' '.join(command)}): {completed.stderr.strip()}"
        )
    return completed.stdout


def _git(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> str:
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
    if env:
        environment.update(env)
    return _run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ],
        cwd=cwd,
        env=environment,
        input_text=input_text,
        replace_env=True,
    )


def _git_bytes(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> bytes:
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
    if env:
        environment.update(env)
    completed = subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ],
        cwd=cwd,
        env=environment,
        input=input_bytes,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise WorkspaceError(
            f"command failed ({' '.join(arguments)}): "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nul_paths(output: str) -> list[str]:
    return [value for value in output.split("\0") if value]


def _inside(relative: str) -> bool:
    path = Path(relative)
    return bool(relative) and not path.is_absolute() and ".." not in path.parts


def _validated_marker_value(marker: object) -> dict[str, object]:
    expected_keys = {
        "approvedIgnoredPath",
        "excludedSentinelPath",
        "kind",
        "schemaVersion",
    }
    approved = marker.get("approvedIgnoredPath") if isinstance(marker, dict) else None
    excluded = marker.get("excludedSentinelPath") if isinstance(marker, dict) else None
    if (
        not isinstance(marker, dict)
        or set(marker) != expected_keys
        or marker.get("schemaVersion") != 1
        or marker.get("kind") != "lift-disposable-fixture"
        or not isinstance(approved, str)
        or not _inside(approved)
        or not isinstance(excluded, str)
        or not _inside(excluded)
        or approved == excluded
    ):
        raise WorkspaceError("disposable fixture marker is missing or invalid")
    return marker


def _validated_fixture_marker(workspace: Path) -> dict[str, object]:
    marker_path = workspace / FIXTURE_MARKER_PATH
    try:
        marker_stat = marker_path.lstat()
        if (
            marker_path.is_symlink()
            or not stat.S_ISREG(marker_stat.st_mode)
            or marker_stat.st_size > 4096
        ):
            raise WorkspaceError("disposable fixture marker is unsafe")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("disposable fixture marker is missing or invalid") from exc
    return _validated_marker_value(marker)


def _fixture_policy(marker: dict[str, object], marker_sha256: str) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{64}", marker_sha256) is None:
        raise WorkspaceError("fixture marker hash is invalid")
    return {
        "schemaVersion": 1,
        "markerPath": FIXTURE_MARKER_PATH,
        "markerSha256": marker_sha256,
        "approvedIgnoredPath": marker["approvedIgnoredPath"],
        "excludedSentinelPath": marker["excludedSentinelPath"],
    }


def _workspace_fixture_policy(workspace: Path) -> dict[str, object]:
    marker = _validated_fixture_marker(workspace)
    return _fixture_policy(
        marker,
        sha256_file(workspace / FIXTURE_MARKER_PATH),
    )


def _commit_fixture_policy(ledger: Path, commit: str) -> dict[str, object]:
    try:
        marker_bytes = _git_bytes(
            [
                f"--git-dir={ledger}",
                "cat-file",
                "blob",
                f"{commit}:{FIXTURE_MARKER_PATH}",
            ]
        )
        marker = json.loads(marker_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("baseline fixture marker is invalid") from exc
    return _fixture_policy(_validated_marker_value(marker), sha256_bytes(marker_bytes))


def _index_path(workspace: Path) -> Path:
    raw = _git(["rev-parse", "--git-path", "index"], cwd=workspace).strip()
    path = Path(raw)
    return path if path.is_absolute() else workspace / path


def _state_fingerprint(workspace: Path) -> dict[str, str]:
    index = _index_path(workspace)
    return {
        "head": _git(["rev-parse", "HEAD"], cwd=workspace).strip(),
        "branch": _git(["symbolic-ref", "--short", "HEAD"], cwd=workspace).strip(),
        "refs": _git(
            ["for-each-ref", "--format=%(refname) %(objectname)"],
            cwd=workspace,
        ),
        "indexSha256": sha256_file(index),
        "status": _git(["status", "--porcelain=v2", "--untracked-files=all"], cwd=workspace),
    }


def workspace_state_fingerprint(workspace: Path) -> dict[str, str]:
    """Return the user-visible Git state that private operations must preserve."""

    return _state_fingerprint(workspace.resolve(strict=True))


def validate_fixture_policy(
    workspace: Path, approved_ignored: Iterable[str]
) -> dict[str, object]:
    """Validate the marker-gated Phase 0 inclusion policy."""

    workspace = workspace.resolve(strict=True)
    marker = _validated_fixture_marker(workspace)
    if tuple(approved_ignored) != (marker["approvedIgnoredPath"],):
        raise WorkspaceError("fixture operation requires its one approved ignored path")
    return marker


def fixture_policy_for_commit(ledger: Path, commit: str) -> dict[str, object]:
    """Return the immutable fixture transfer policy stored in a private commit."""

    if ledger.is_symlink() or not ledger.is_dir():
        raise WorkspaceError("private ledger is not a physical directory")
    ledger = ledger.resolve(strict=True)
    resolved_commit = _git(
        [f"--git-dir={ledger}", "rev-parse", f"{commit}^{{commit}}"]
    ).strip()
    return _commit_fixture_policy(ledger, resolved_commit)


def create_fixture(path: Path) -> dict[str, str]:
    path = path.resolve()
    if path.exists():
        marker = path / ".lift-spike-fixture.json"
        if not marker.is_file():
            raise WorkspaceError(f"refusing to reuse unmarked directory: {path}")
        return json.loads(marker.read_text(encoding="utf-8"))

    path.mkdir(parents=True)
    _git(["init", "--initial-branch=main"], cwd=path)
    _git(["config", "user.name", "Lift Spike"], cwd=path)
    _git(["config", "user.email", "spike@lift.invalid"], cwd=path)

    (path / ".gitignore").write_text("approved-state/\nexcluded.env\n", encoding="utf-8")
    (path / "README.md").write_text(
        "# Disposable Lift EC2 fixture\n\nThis repository contains no user project data.\n",
        encoding="utf-8",
    )
    (path / "REMOTE_TEST.md").write_text(
        "Status: waiting for an EC2 phone-issued Codex task.\n", encoding="utf-8"
    )
    (path / "DIRTY_LOCAL.md").write_text("State: committed baseline.\n", encoding="utf-8")
    (path / "STAGED_AND_DIRTY.md").write_text("State: committed baseline.\n", encoding="utf-8")
    _git(["add", ".gitignore", "README.md", "REMOTE_TEST.md", "DIRTY_LOCAL.md", "STAGED_AND_DIRTY.md"], cwd=path)
    _git(["commit", "-m", "Create disposable Lift spike fixture"], cwd=path)

    (path / "DIRTY_LOCAL.md").write_text("State: dirty local tracked change.\n", encoding="utf-8")
    (path / "STAGED_AND_DIRTY.md").write_text("State: staged change.\n", encoding="utf-8")
    _git(["add", "STAGED_AND_DIRTY.md"], cwd=path)
    with (path / "STAGED_AND_DIRTY.md").open("a", encoding="utf-8") as handle:
        handle.write("State: additional unstaged change.\n")
    (path / "UNTRACKED.md").write_text("State: untracked and approved by default rules.\n", encoding="utf-8")
    (path / "approved-state").mkdir()
    (path / "approved-state" / "approved.txt").write_text(
        "This ignored fixture file is explicitly approved.\n", encoding="utf-8"
    )
    (path / "excluded.env").write_text(
        "LIFT_SENTINEL=THIS_FILE_MUST_NEVER_TRANSFER\n", encoding="utf-8"
    )

    marker_value = {
        "schemaVersion": 1,
        "kind": "lift-disposable-fixture",
        "approvedIgnoredPath": "approved-state/approved.txt",
        "excludedSentinelPath": "excluded.env",
    }
    (path / ".lift-spike-fixture.json").write_text(
        json.dumps(marker_value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return marker_value


def _is_hard_excluded(relative: str, excluded_paths: tuple[str, ...]) -> bool:
    return any(
        relative == excluded or relative.startswith(excluded.rstrip("/") + "/")
        for excluded in excluded_paths
    )


def _included_paths(
    workspace: Path,
    approved_ignored: Iterable[str],
    excluded_paths: tuple[str, ...],
) -> tuple[set[str], dict[str, str]]:
    tracked = set(_nul_paths(_git(["ls-files", "-z"], cwd=workspace)))
    untracked = set(
        _nul_paths(_git(["ls-files", "--others", "--exclude-standard", "-z"], cwd=workspace))
    )
    reasons = {path: "tracked" for path in tracked}
    reasons.update({path: "untracked" for path in untracked})
    included = tracked | untracked

    for raw in approved_ignored:
        if not _inside(raw):
            raise WorkspaceError(f"approved ignored path is unsafe: {raw}")
        candidate = workspace / raw
        if not candidate.exists() and not candidate.is_symlink():
            raise WorkspaceError(f"approved ignored path does not exist: {raw}")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
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
        ignore_check = subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "check-ignore",
                "--quiet",
                "--",
                raw,
            ],
            cwd=workspace,
            env=environment,
            capture_output=True,
        )
        if ignore_check.returncode not in (0, 1):
            raise WorkspaceError(f"unable to verify ignored path policy: {raw}")
        if ignore_check.returncode != 0:
            raise WorkspaceError(f"approved path is not ignored: {raw}")
        included.add(raw)
        reasons[raw] = "explicitly-approved-ignored"

    included = {
        relative
        for relative in included
        if not _is_hard_excluded(relative, excluded_paths)
    }
    reasons = {relative: reasons[relative] for relative in included}
    return included, reasons


def content_manifest(
    workspace: Path,
    approved_ignored: Iterable[str],
    *,
    excluded_paths: Iterable[str] | None = None,
) -> dict[str, object]:
    workspace = workspace.resolve(strict=True)
    marker = _validated_fixture_marker(workspace)
    if excluded_paths is None:
        excluded_paths = (str(marker["excludedSentinelPath"]),)
    excluded_paths = tuple(excluded_paths)
    if not excluded_paths or any(not _inside(path) for path in excluded_paths):
        raise WorkspaceError("hard-excluded fixture path is invalid")
    included, reasons = _included_paths(
        workspace,
        approved_ignored,
        excluded_paths,
    )
    entries: list[dict[str, object]] = []
    for relative in sorted(included):
        if relative == ".git" or relative.startswith(".git/"):
            raise WorkspaceError("Git administration files cannot enter the content manifest")
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
                "reason": reasons[relative],
            }
        elif stat.S_ISLNK(info.st_mode):
            target = os.readlink(absolute)
            resolved_target = (absolute.parent / target).resolve(strict=False)
            if resolved_target != workspace and workspace not in resolved_target.parents:
                raise WorkspaceError(f"symbolic link escapes the workspace: {relative}")
            target_relative = resolved_target.relative_to(workspace)
            if any(part.casefold() == ".git" for part in target_relative.parts):
                raise WorkspaceError(
                    f"symbolic link targets Git administration state: {relative}"
                )
            entry = {
                "path": relative,
                "type": "symlink",
                "sha256": sha256_bytes(target.encode("utf-8")),
                "target": target,
                "size": len(target.encode("utf-8")),
                "executable": False,
                "reason": reasons[relative],
            }
        else:
            raise WorkspaceError(f"unsupported file type: {relative}")
        entries.append(entry)

    payload: dict[str, object] = {"schemaVersion": 1, "entries": entries}
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload["manifestSha256"] = sha256_bytes(canonical)
    return payload


def _manifest_content_entries(manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise WorkspaceError("content manifest has no entries")
    entries: list[dict[str, object]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise WorkspaceError("content manifest contains an invalid entry")
        try:
            entry = {
                key: raw[key]
                for key in ("path", "type", "sha256", "size", "executable")
            }
        except KeyError as exc:
            raise WorkspaceError("content manifest contains an invalid entry") from exc
        if raw.get("type") == "symlink":
            entry["target"] = raw.get("target")
        entries.append(entry)
    return sorted(entries, key=lambda entry: str(entry["path"]))


def _tree_content_entries(ledger: Path, tree: str) -> list[dict[str, object]]:
    raw_tree = _git_bytes(
        [f"--git-dir={ledger}", "ls-tree", "-r", "-z", "--full-tree", tree]
    )
    entries: list[dict[str, object]] = []
    for encoded in raw_tree.split(b"\0"):
        if not encoded:
            continue
        metadata, separator, path_bytes = encoded.partition(b"\t")
        if not separator:
            raise WorkspaceError("private snapshot tree listing is malformed")
        try:
            mode_bytes, object_type, object_id_bytes = metadata.split(b" ", 2)
            path = path_bytes.decode("utf-8")
            mode = mode_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise WorkspaceError("private snapshot tree entry is invalid") from exc
        if object_type != b"blob" or mode not in {"100644", "100755", "120000"}:
            raise WorkspaceError(f"unsupported private snapshot entry: {path}")
        if not _inside(path) or path == ".git" or path.startswith(".git/"):
            raise WorkspaceError(f"unsafe private snapshot path: {path}")
        content = _git_bytes(
            [f"--git-dir={ledger}", "cat-file", "blob", object_id]
        )
        entry: dict[str, object] = {
            "path": path,
            "type": "symlink" if mode == "120000" else "file",
            "sha256": sha256_bytes(content),
            "size": len(content),
            "executable": mode == "100755",
        }
        if mode == "120000":
            try:
                entry["target"] = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WorkspaceError(
                    f"private snapshot symbolic link target is not UTF-8: {path}"
                ) from exc
        entries.append(entry)
    return sorted(entries, key=lambda entry: str(entry["path"]))


def _verify_tree_manifest(
    ledger: Path,
    tree: str,
    manifest: dict[str, object],
    excluded_paths: tuple[str, ...],
) -> None:
    tree_entries = _tree_content_entries(ledger, tree)
    if any(
        _is_hard_excluded(str(entry["path"]), excluded_paths)
        for entry in tree_entries
    ):
        raise WorkspaceError("hard-excluded fixture path entered the private tree")
    if tree_entries != _manifest_content_entries(manifest):
        raise WorkspaceError("private snapshot tree and full content manifest differ")


def _stage_selected_paths(
    workspace: Path,
    environment: dict[str, str],
    approved_ignored: tuple[str, ...],
    excluded_paths: tuple[str, ...],
) -> None:
    included, _ = _included_paths(
        workspace,
        approved_ignored,
        excluded_paths,
    )
    selected = sorted(
        path
        for path in included
        if (workspace / path).exists() or (workspace / path).is_symlink()
    )
    if not selected:
        return
    _git(
        [
            "--literal-pathspecs",
            "add",
            "-f",
            "-A",
            "--pathspec-from-file=-",
            "--pathspec-file-nul",
        ],
        cwd=workspace,
        env=environment,
        input_text="\0".join(selected) + "\0",
    )


def _hard_remove_private_paths(
    workspace: Path,
    environment: dict[str, str],
    excluded_paths: tuple[str, ...],
) -> None:
    captured = set(
        _nul_paths(_git(["ls-files", "-z"], cwd=workspace, env=environment))
    )
    removals = sorted(
        relative
        for relative in captured
        if _is_hard_excluded(relative, excluded_paths)
    )
    if removals:
        _git(
            ["update-index", "--force-remove", "-z", "--stdin"],
            cwd=workspace,
            env=environment,
            input_text="\0".join(removals) + "\0",
        )
    remaining = set(
        _nul_paths(_git(["ls-files", "-z"], cwd=workspace, env=environment))
    )
    if any(_is_hard_excluded(path, excluded_paths) for path in remaining):
        raise WorkspaceError("hard-excluded fixture path entered the private index")


@dataclass(frozen=True)
class BaselineCapture:
    commit: str
    ref: str
    manifest: dict[str, object]
    original: dict[str, str]
    fixture_policy: dict[str, object]


@dataclass(frozen=True)
class SnapshotCapture:
    commit: str
    tree: str
    ref: str
    manifest: dict[str, object]
    original: dict[str, str]
    git_history: dict[str, object]


def _git_history_snapshot(workspace: Path) -> dict[str, object]:
    head = _git(["rev-parse", "HEAD^{commit}"], cwd=workspace).strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise WorkspaceError("local Git HEAD is not a valid commit")
    refs: list[dict[str, str]] = []
    for line in _git(
        ["for-each-ref", "--format=%(refname)%09%(objectname)"],
        cwd=workspace,
    ).splitlines():
        name, separator, object_id = line.partition("\t")
        if (
            not separator
            or not name.startswith("refs/")
            or re.fullmatch(r"[0-9a-f]{40}", object_id) is None
        ):
            raise WorkspaceError("local Git ref listing is malformed")
        refs.append({"name": name, "objectId": object_id})
    reflog_commits = sorted(
        set(
            line
            for line in _git(
                ["reflog", "show", "--all", "--format=%H"],
                cwd=workspace,
            ).splitlines()
            if line
        )
    )
    if any(re.fullmatch(r"[0-9a-f]{40}", item) is None for item in reflog_commits):
        raise WorkspaceError("local Git reflog listing is malformed")
    payload: dict[str, object] = {
        "head": head,
        "refs": sorted(refs, key=lambda item: item["name"]),
        "reflogCommits": reflog_commits,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload["sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _history_ref_plan(
    snapshot: dict[str, object], *, prefix: str
) -> list[dict[str, str]]:
    head = snapshot["head"]
    refs = snapshot["refs"]
    reflog_commits = snapshot["reflogCommits"]
    if not isinstance(head, str) or not isinstance(refs, list) or not isinstance(
        reflog_commits, list
    ):
        raise WorkspaceError("local Git history snapshot is malformed")
    planned = [
        {
            "source": "HEAD",
            "ref": f"{prefix}/head",
            "objectId": head,
        }
    ]
    for item in refs:
        if not isinstance(item, dict):
            raise WorkspaceError("local Git history snapshot is malformed")
        name = item.get("name")
        object_id = item.get("objectId")
        if not isinstance(name, str) or not name.startswith("refs/") or not isinstance(
            object_id, str
        ):
            raise WorkspaceError("local Git history snapshot is malformed")
        planned.append(
            {
                "source": name,
                "ref": f"{prefix}/refs/{name.removeprefix('refs/')}",
                "objectId": object_id,
            }
        )
    for object_id in reflog_commits:
        if not isinstance(object_id, str):
            raise WorkspaceError("local Git history snapshot is malformed")
        planned.append(
            {
                "source": "reflog",
                "ref": f"{prefix}/reflog/{object_id}",
                "objectId": object_id,
            }
        )
    return planned


def _import_git_history(
    workspace: Path,
    ledger: Path,
    *,
    run_id: str,
    expected: dict[str, object],
) -> None:
    with tempfile.TemporaryDirectory(
        prefix=f"{run_id}-local-history-", dir=ledger.parent
    ) as temporary_name:
        bundle = Path(temporary_name) / "local-history.bundle"
        _git(
            ["bundle", "create", str(bundle), "--all", "--reflog", "HEAD"],
            cwd=workspace,
        )
        info = bundle.lstat()
        if bundle.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise WorkspaceError("local Git history bundle is unsafe")
        os.chmod(bundle, 0o600)
        if _git_history_snapshot(workspace) != expected:
            raise WorkspaceError("local Git history changed while it was captured")
        _git([f"--git-dir={ledger}", "bundle", "unbundle", str(bundle)])

    object_ids = {
        str(expected["head"]),
        *(str(item["objectId"]) for item in expected["refs"]),
        *(str(item) for item in expected["reflogCommits"]),
    }
    for object_id in sorted(object_ids):
        _git([f"--git-dir={ledger}", "cat-file", "-e", f"{object_id}^{{object}}"])


def _publish_snapshot_refs(
    ledger: Path,
    *,
    snapshot_ref: str,
    snapshot_commit: str,
    history_refs: list[dict[str, str]],
    history_prefix: str,
) -> None:
    desired = {snapshot_ref: snapshot_commit}
    desired.update({item["ref"]: item["objectId"] for item in history_refs})
    listing = _git(
        [
            f"--git-dir={ledger}",
            "for-each-ref",
            "--format=%(refname)%09%(objectname)",
            snapshot_ref,
            history_prefix,
        ]
    )
    existing: dict[str, str] = {}
    for line in listing.splitlines():
        name, separator, object_id = line.partition("\t")
        if not separator:
            raise WorkspaceError("private local-history ref listing is malformed")
        existing[name] = object_id
    if existing:
        if existing != desired:
            raise WorkspaceError("immutable local Git history refs already differ")
        return
    commands = "".join(
        f"create {name} {object_id}\n" for name, object_id in sorted(desired.items())
    )
    _git(
        [f"--git-dir={ledger}", "update-ref", "--stdin"],
        input_text=commands,
    )


def capture_fixture_snapshot(
    *,
    workspace: Path,
    ledger: Path,
    run_id: str,
    workspace_id: str,
    parent_commit: str,
    ref_name: str,
    message: str,
    approved_ignored: Iterable[str],
) -> SnapshotCapture:
    """Capture a fixture tree privately without touching the user's Git state."""

    workspace = workspace.resolve(strict=True)
    ledger = ledger.resolve(strict=True)
    if ledger.is_symlink() or not ledger.is_dir():
        raise WorkspaceError("private ledger is not a physical directory")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", run_id):
        raise WorkspaceError("snapshot run ID is invalid")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", workspace_id):
        raise WorkspaceError("snapshot workspace ID is invalid")
    expected_prefix = f"refs/lift/{workspace_id}/sessions/{run_id}/"
    if not ref_name.startswith(expected_prefix) or not _inside(
        ref_name[len(expected_prefix) :]
    ):
        raise WorkspaceError("snapshot ref is outside the immutable session namespace")
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise WorkspaceError("snapshot message is invalid")

    parent_commit = _git(
        [f"--git-dir={ledger}", "rev-parse", f"{parent_commit}^{{commit}}"]
    ).strip()
    fixture_policy = _commit_fixture_policy(ledger, parent_commit)
    if _workspace_fixture_policy(workspace) != fixture_policy:
        raise WorkspaceError("fixture marker differs from the immutable baseline policy")
    approved_ignored = tuple(approved_ignored)
    if approved_ignored != (fixture_policy["approvedIgnoredPath"],):
        raise WorkspaceError("fixture snapshot requires its baseline-approved ignored path")
    excluded_paths = (str(fixture_policy["excludedSentinelPath"]),)
    original = _state_fingerprint(workspace)
    git_history_snapshot = _git_history_snapshot(workspace)

    def capture_tree(index: Path) -> str:
        index.unlink(missing_ok=True)
        environment = {
            "GIT_DIR": str(ledger),
            "GIT_WORK_TREE": str(workspace),
            "GIT_INDEX_FILE": str(index),
        }
        _git(["read-tree", "--empty"], cwd=workspace, env=environment)
        _stage_selected_paths(
            workspace,
            environment,
            approved_ignored,
            excluded_paths,
        )
        _hard_remove_private_paths(workspace, environment, excluded_paths)
        return _git(["write-tree"], cwd=workspace, env=environment).strip()

    first_index = ledger.parent / f"{run_id}-return-first.index"
    second_index = ledger.parent / f"{run_id}-return-second.index"
    try:
        first_tree = capture_tree(first_index)
        second_tree = capture_tree(second_index)
    finally:
        first_index.unlink(missing_ok=True)
        second_index.unlink(missing_ok=True)
    if first_tree != second_tree:
        raise WorkspaceError("workspace changed while the private snapshot was captured")
    if _commit_fixture_policy(ledger, first_tree) != fixture_policy:
        raise WorkspaceError("private snapshot fixture marker differs from baseline policy")

    manifest = content_manifest(
        workspace,
        approved_ignored,
        excluded_paths=excluded_paths,
    )
    _verify_tree_manifest(ledger, first_tree, manifest, excluded_paths)
    final_manifest = content_manifest(
        workspace,
        approved_ignored,
        excluded_paths=excluded_paths,
    )
    if final_manifest != manifest:
        raise WorkspaceError("workspace changed after its private snapshot was captured")
    _verify_tree_manifest(ledger, first_tree, final_manifest, excluded_paths)
    if _state_fingerprint(workspace) != original:
        raise WorkspaceError("workspace changed after its private snapshot was captured")

    _import_git_history(
        workspace,
        ledger,
        run_id=run_id,
        expected=git_history_snapshot,
    )
    if (
        _state_fingerprint(workspace) != original
        or _git_history_snapshot(workspace) != git_history_snapshot
    ):
        raise WorkspaceError("local Git state changed while its history was captured")

    history_prefix = f"{expected_prefix}git-history/local-return"
    history_refs = _history_ref_plan(git_history_snapshot, prefix=history_prefix)
    head_commit = str(git_history_snapshot["head"])

    existing = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            f"--git-dir={ledger}",
            "rev-parse",
            "--verify",
            "--quiet",
            f"{ref_name}^{{commit}}",
        ],
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        | {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        },
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0:
        commit = existing.stdout.strip()
        existing_tree = _git(
            [f"--git-dir={ledger}", "show", "-s", "--format=%T", commit]
        ).strip()
        existing_parents = _git(
            [f"--git-dir={ledger}", "show", "-s", "--format=%P", commit]
        ).strip()
        if (
            existing_tree != first_tree
            or existing_parents != f"{parent_commit} {head_commit}"
        ):
            raise WorkspaceError("immutable private snapshot already differs")
    elif existing.returncode == 1:
        environment = {
            "GIT_AUTHOR_NAME": "Lift",
            "GIT_AUTHOR_EMAIL": "spike@lift.invalid",
            "GIT_COMMITTER_NAME": "Lift",
            "GIT_COMMITTER_EMAIL": "spike@lift.invalid",
        }
        commit = _git(
            [
                f"--git-dir={ledger}",
                "commit-tree",
                first_tree,
                "-p",
                parent_commit,
                "-p",
                head_commit,
            ],
            env=environment,
            input_text=message.rstrip() + "\n",
        ).strip()
    else:
        raise WorkspaceError("unable to inspect immutable private snapshot ref")

    _publish_snapshot_refs(
        ledger,
        snapshot_ref=ref_name,
        snapshot_commit=commit,
        history_refs=history_refs,
        history_prefix=history_prefix,
    )

    after = _state_fingerprint(workspace)
    if after != original:
        raise WorkspaceError("private snapshot changed the user's Git state")
    return SnapshotCapture(
        commit=commit,
        tree=first_tree,
        ref=ref_name,
        manifest=manifest,
        original=original,
        git_history={
            "schemaVersion": 1,
            "snapshotSha256": git_history_snapshot["sha256"],
            "head": head_commit,
            "historyRefs": history_refs,
        },
    )


def capture_baseline(
    *,
    workspace: Path,
    ledger: Path,
    run_id: str,
    workspace_id: str,
    approved_ignored: Iterable[str],
) -> BaselineCapture:
    workspace = workspace.resolve(strict=True)
    approved_ignored = tuple(approved_ignored)
    fixture_policy = _workspace_fixture_policy(workspace)
    if approved_ignored != (fixture_policy["approvedIgnoredPath"],):
        raise WorkspaceError("fixture capture requires its one approved ignored path")
    excluded_paths = (str(fixture_policy["excludedSentinelPath"]),)
    original = _state_fingerprint(workspace)
    head = original["head"]
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        _git(["init", "--bare", str(ledger)])

    _git([f"--git-dir={ledger}", "fetch", "--no-tags", str(workspace), head])
    ref = f"refs/lift/{workspace_id}/sessions/{run_id}/baseline"

    def capture_tree(index: Path) -> str:
        index.unlink(missing_ok=True)
        environment = {
            "GIT_DIR": str(ledger),
            "GIT_WORK_TREE": str(workspace),
            "GIT_INDEX_FILE": str(index),
        }
        _git(["read-tree", "--empty"], cwd=workspace, env=environment)
        _stage_selected_paths(
            workspace,
            environment,
            approved_ignored,
            excluded_paths,
        )
        _hard_remove_private_paths(workspace, environment, excluded_paths)
        return _git(["write-tree"], cwd=workspace, env=environment).strip()

    first_index = ledger.parent / f"{run_id}-baseline-first.index"
    second_index = ledger.parent / f"{run_id}-baseline-second.index"
    try:
        first_tree = capture_tree(first_index)
        second_tree = capture_tree(second_index)
    finally:
        first_index.unlink(missing_ok=True)
        second_index.unlink(missing_ok=True)
    if first_tree != second_tree:
        raise WorkspaceError("workspace changed while the baseline was captured")
    if _commit_fixture_policy(ledger, first_tree) != fixture_policy:
        raise WorkspaceError("captured fixture marker differs from baseline policy")

    manifest = content_manifest(
        workspace,
        approved_ignored,
        excluded_paths=excluded_paths,
    )
    _verify_tree_manifest(ledger, first_tree, manifest, excluded_paths)
    final_manifest = content_manifest(
        workspace,
        approved_ignored,
        excluded_paths=excluded_paths,
    )
    if final_manifest != manifest or _state_fingerprint(workspace) != original:
        raise WorkspaceError("workspace changed while the baseline was captured")
    _verify_tree_manifest(ledger, first_tree, final_manifest, excluded_paths)

    existing_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    existing_environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    existing = subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            f"--git-dir={ledger}",
            "rev-parse",
            "--verify",
            "--quiet",
            ref,
        ],
        env=existing_environment,
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0:
        commit = existing.stdout.strip()
        existing_tree = _git(
            [f"--git-dir={ledger}", "show", "-s", "--format=%T", commit]
        ).strip()
        existing_parents = _git(
            [f"--git-dir={ledger}", "show", "-s", "--format=%P", commit]
        ).strip()
        if existing_tree != first_tree or existing_parents != head:
            raise WorkspaceError("immutable baseline ref already exists with different content")
    elif existing.returncode == 1:
        environment = {
            "GIT_AUTHOR_NAME": "Lift",
            "GIT_AUTHOR_EMAIL": "spike@lift.invalid",
            "GIT_COMMITTER_NAME": "Lift",
            "GIT_COMMITTER_EMAIL": "spike@lift.invalid",
        }
        commit = _git(
            [f"--git-dir={ledger}", "commit-tree", first_tree, "-p", head],
            cwd=workspace,
            env=environment,
            input_text="Capture exact Lift Off baseline\n",
        ).strip()
        _git([f"--git-dir={ledger}", "update-ref", ref, commit, "0" * 40])
    else:
        raise WorkspaceError("unable to inspect immutable baseline ref")

    after = _state_fingerprint(workspace)
    if after != original:
        raise WorkspaceError("private capture changed the user's branch, refs, index, or working tree")
    return BaselineCapture(
        commit=commit,
        ref=ref,
        manifest=manifest,
        original=original,
        fixture_policy=fixture_policy,
    )


def build_lift_off_archive(
    *,
    destination: Path,
    ledger: Path,
    capture: BaselineCapture,
    run_id: str,
    workspace_id: str,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lift-spike-bundle-") as temporary_name:
        temporary = Path(temporary_name)
        bundle = temporary / "ledger.bundle"
        _git([f"--git-dir={ledger}", "bundle", "create", str(bundle), capture.ref])
        manifest = temporary / "manifest.json"
        manifest.write_text(
            json.dumps(capture.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        session = temporary / "session.json"
        session.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": run_id,
                    "workspaceId": workspace_id,
                    "baselineCommit": capture.commit,
                    "baselineRef": capture.ref,
                    "manifestSha256": capture.manifest["manifestSha256"],
                    "fixturePolicy": capture.fixture_policy,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(bundle, arcname="ledger.bundle", recursive=False)
            archive.add(manifest, arcname="manifest.json", recursive=False)
            archive.add(session, arcname="session.json", recursive=False)
    return sha256_file(destination)
