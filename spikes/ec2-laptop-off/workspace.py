"""Disposable workspace fixture and Lift-private Git capture primitives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
from typing import Iterable


class WorkspaceError(RuntimeError):
    pass


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> str:
    merged_environment = os.environ.copy()
    if env:
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
    return _run(["git", *arguments], cwd=cwd, env=env, input_text=input_text)


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


def _validated_fixture_marker(workspace: Path) -> dict[str, object]:
    marker_path = workspace / ".lift-spike-fixture.json"
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
            ["for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags"],
            cwd=workspace,
        ),
        "indexSha256": sha256_file(index),
        "status": _git(["status", "--porcelain=v2", "--untracked-files=all"], cwd=workspace),
    }


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


def _included_paths(workspace: Path, approved_ignored: Iterable[str]) -> tuple[set[str], dict[str, str]]:
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
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", raw], cwd=workspace
        ).returncode == 0
        if not ignored:
            raise WorkspaceError(f"approved path is not ignored: {raw}")
        included.add(raw)
        reasons[raw] = "explicitly-approved-ignored"

    return included, reasons


def content_manifest(
    workspace: Path,
    approved_ignored: Iterable[str],
) -> dict[str, object]:
    workspace = workspace.resolve(strict=True)
    included, reasons = _included_paths(workspace, approved_ignored)
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


@dataclass(frozen=True)
class BaselineCapture:
    commit: str
    ref: str
    manifest: dict[str, object]
    original: dict[str, str]


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
    marker = _validated_fixture_marker(workspace)
    if approved_ignored != (marker["approvedIgnoredPath"],):
        raise WorkspaceError("fixture capture requires its one approved ignored path")
    original = _state_fingerprint(workspace)
    head = original["head"]
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        _git(["init", "--bare", str(ledger)])

    _git([f"--git-dir={ledger}", "fetch", "--no-tags", str(workspace), head])
    private_index = ledger.parent / f"{run_id}-baseline.index"
    private_index.unlink(missing_ok=True)
    environment = {
        "GIT_DIR": str(ledger),
        "GIT_WORK_TREE": str(workspace),
        "GIT_INDEX_FILE": str(private_index),
        "GIT_AUTHOR_NAME": "Lift",
        "GIT_AUTHOR_EMAIL": "spike@lift.invalid",
        "GIT_COMMITTER_NAME": "Lift",
        "GIT_COMMITTER_EMAIL": "spike@lift.invalid",
    }
    ref = f"refs/lift/{workspace_id}/sessions/{run_id}/baseline"
    try:
        _git(["read-tree", head], cwd=workspace, env=environment)
        _git(["add", "-A", "--", "."], cwd=workspace, env=environment)
        for relative in approved_ignored:
            _git(["add", "-f", "--", relative], cwd=workspace, env=environment)
        captured = set(_nul_paths(_git(["ls-files", "-z"], cwd=workspace, env=environment)))
        excluded = marker["excludedSentinelPath"]
        if excluded in captured:
            raise WorkspaceError(f"excluded sentinel entered the private index: {excluded}")
        tree = _git(["write-tree"], cwd=workspace, env=environment).strip()
        existing = subprocess.run(
            ["git", f"--git-dir={ledger}", "rev-parse", "--verify", "--quiet", ref],
            text=True,
            capture_output=True,
        )
        if existing.returncode == 0:
            commit = existing.stdout.strip()
            existing_tree = _git([f"--git-dir={ledger}", "show", "-s", "--format=%T", commit]).strip()
            existing_parents = _git([f"--git-dir={ledger}", "show", "-s", "--format=%P", commit]).strip()
            if existing_tree != tree or existing_parents != head:
                raise WorkspaceError("immutable baseline ref already exists with different content")
        else:
            commit = _git(
                ["commit-tree", tree, "-p", head],
                cwd=workspace,
                env=environment,
                input_text="Capture exact Lift Off baseline\n",
            ).strip()
            _git([f"--git-dir={ledger}", "update-ref", ref, commit, "0" * 40])
    finally:
        private_index.unlink(missing_ok=True)

    manifest = content_manifest(workspace, approved_ignored)

    after = _state_fingerprint(workspace)
    if after != original:
        raise WorkspaceError("private capture changed the user's branch, refs, index, or working tree")
    return BaselineCapture(commit=commit, ref=ref, manifest=manifest, original=original)


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
