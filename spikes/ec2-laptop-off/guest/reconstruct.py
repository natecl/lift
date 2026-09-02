#!/usr/bin/env python3
"""Verify and atomically reconstruct the disposable fixture on the EC2 disk."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


DATA_ROOT = Path("/srv/lift-data")
WORKSPACE_ROOT = Path("/home/lift/workspaces")
LEDGER_ROOT = Path("/var/lib/lift/ledger")
STATE_ROOT = Path("/var/lib/lift-spike/workspaces")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
EXPECTED_ARCHIVE_MEMBERS = {"ledger.bundle", "manifest.json", "session.json"}
FIXTURE_MARKER_PATH = ".lift-spike-fixture.json"


class ReconstructError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise ReconstructError(
            f"command failed ({' '.join(command)}): {completed.stderr.strip()}"
        )
    return completed.stdout


def git(arguments: list[str], *, cwd: Path | None = None) -> str:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgSign=false",
            *arguments,
        ],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ReconstructError(
            f"Git command failed ({' '.join(arguments)}): {completed.stderr.strip()}"
        )
    return completed.stdout


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconstructError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReconstructError(f"JSON at {path} must be an object")
    return value


def inside_workspace(relative: str) -> bool:
    path = Path(relative)
    return (
        bool(relative)
        and not path.is_absolute()
        and ".." not in path.parts
        and relative != ".git"
        and not relative.startswith(".git/")
    )


def validate_fixture_policy_shape(value: object) -> dict[str, Any]:
    expected_keys = {
        "schemaVersion",
        "markerPath",
        "markerSha256",
        "approvedIgnoredPath",
        "excludedSentinelPath",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ReconstructError("Lift Off session omitted its fixture policy")
    marker_path = value.get("markerPath")
    marker_sha = value.get("markerSha256")
    approved = value.get("approvedIgnoredPath")
    excluded = value.get("excludedSentinelPath")
    if (
        value.get("schemaVersion") != 1
        or marker_path != FIXTURE_MARKER_PATH
        or not isinstance(marker_sha, str)
        or re.fullmatch(r"[0-9a-f]{64}", marker_sha) is None
        or not isinstance(approved, str)
        or not inside_workspace(approved)
        or not isinstance(excluded, str)
        or not inside_workspace(excluded)
        or approved == excluded
        or marker_path in {approved, excluded}
    ):
        raise ReconstructError("Lift Off fixture policy is invalid")
    return value


def validate_fixture_policy(
    value: object,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    value = validate_fixture_policy_shape(value)
    marker_path = str(value["markerPath"])
    marker_sha = str(value["markerSha256"])
    excluded = str(value["excludedSentinelPath"])
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ReconstructError("Lift Off fixture policy has no manifest")
    marker_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("path") == marker_path
        ),
        None,
    )
    if (
        not isinstance(marker_entry, dict)
        or marker_entry.get("type") != "file"
        or marker_entry.get("sha256") != marker_sha
    ):
        raise ReconstructError("baseline fixture marker does not match its pinned policy")
    if any(
        isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and (
            entry["path"] == excluded
            or entry["path"].startswith(excluded.rstrip("/") + "/")
        )
        for entry in entries
    ):
        raise ReconstructError("hard-excluded fixture path entered the Lift Off manifest")
    return value


def verify_fixture_marker(workspace: Path, policy: dict[str, Any]) -> None:
    marker_path = workspace / str(policy["markerPath"])
    try:
        info = marker_path.lstat()
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes.decode("utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconstructError("reconstructed fixture marker is invalid") from exc
    if (
        marker_path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_size > 4096
        or hashlib.sha256(marker_bytes).hexdigest() != policy["markerSha256"]
        or not isinstance(marker, dict)
        or set(marker)
        != {
            "approvedIgnoredPath",
            "excludedSentinelPath",
            "kind",
            "schemaVersion",
        }
        or marker.get("schemaVersion") != 1
        or marker.get("kind") != "lift-disposable-fixture"
        or marker.get("approvedIgnoredPath") != policy["approvedIgnoredPath"]
        or marker.get("excludedSentinelPath") != policy["excludedSentinelPath"]
    ):
        raise ReconstructError("reconstructed fixture marker differs from pinned policy")


def verify_manifest(workspace: Path, manifest: dict[str, Any]) -> None:
    raw_entries = manifest.get("entries")
    if manifest.get("schemaVersion") != 1 or not isinstance(raw_entries, list):
        raise ReconstructError("unsupported manifest")
    expected_paths: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ReconstructError("invalid manifest entry")
        relative = entry["path"]
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or relative.startswith(".git/"):
            raise ReconstructError(f"unsafe manifest path: {relative}")
        if relative in expected_paths:
            raise ReconstructError(f"duplicate manifest path: {relative}")
        if (
            not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
            or not isinstance(entry.get("size"), int)
            or entry["size"] < 0
            or not isinstance(entry.get("executable"), bool)
        ):
            raise ReconstructError(f"invalid manifest metadata: {relative}")
        expected_paths.add(relative)
        absolute = workspace / relative
        try:
            info = absolute.lstat()
        except FileNotFoundError as exc:
            raise ReconstructError(f"missing manifest path: {relative}") from exc
        if entry.get("type") == "file":
            if not stat.S_ISREG(info.st_mode):
                raise ReconstructError(f"expected a regular file: {relative}")
            if sha256_file(absolute) != entry.get("sha256"):
                raise ReconstructError(f"content hash mismatch: {relative}")
            if info.st_size != entry.get("size"):
                raise ReconstructError(f"content size mismatch: {relative}")
            if bool(stat.S_IMODE(info.st_mode) & stat.S_IXUSR) != entry.get("executable"):
                raise ReconstructError(f"executable mode mismatch: {relative}")
        elif entry.get("type") == "symlink":
            if not stat.S_ISLNK(info.st_mode):
                raise ReconstructError(f"expected a symbolic link: {relative}")
            target = os.readlink(absolute)
            if hashlib.sha256(target.encode("utf-8")).hexdigest() != entry.get("sha256"):
                raise ReconstructError(f"symbolic-link hash mismatch: {relative}")
            if entry.get("target") != target:
                raise ReconstructError(f"symbolic-link target mismatch: {relative}")
            if entry.get("size") != len(target.encode("utf-8")):
                raise ReconstructError(f"symbolic-link size mismatch: {relative}")
            if entry.get("executable") is not False:
                raise ReconstructError(f"symbolic-link mode mismatch: {relative}")
        else:
            raise ReconstructError(f"unsupported entry type: {relative}")

    actual_paths: set[str] = set()
    for root, directories, files in os.walk(workspace, followlinks=False):
        root_path = Path(root)
        if root_path == workspace:
            directories[:] = [name for name in directories if name != ".git"]
        for name in files:
            actual_paths.add(str((root_path / name).relative_to(workspace)))
        for name in directories:
            candidate = root_path / name
            if candidate.is_symlink():
                actual_paths.add(str(candidate.relative_to(workspace)))
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        unexpected = sorted(actual_paths - expected_paths)
        raise ReconstructError(
            f"manifest path mismatch; missing={missing}, unexpected={unexpected}"
        )


def chown_tree(path: Path, uid: int, gid: int) -> None:
    for root, directories, files in os.walk(path, followlinks=False):
        os.chown(root, uid, gid, follow_symlinks=False)
        for name in directories:
            os.chown(Path(root) / name, uid, gid, follow_symlinks=False)
        for name in files:
            os.chown(Path(root) / name, uid, gid, follow_symlinks=False)


def reconstruct(args: argparse.Namespace) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ReconstructError("reconstruction must run as root")
    if not SAFE_ID.fullmatch(args.run_id) or not SAFE_ID.fullmatch(args.workspace_id):
        raise ReconstructError("run and workspace IDs must be safe lowercase identifiers")
    package = Path(args.package).resolve(strict=True)
    if sha256_file(package) != args.sha256:
        raise ReconstructError("Lift Off package hash mismatch")

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    LEDGER_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    target = WORKSPACE_ROOT / args.workspace_id
    ledger = LEDGER_ROOT / f"{args.run_id}.git"
    state_path = STATE_ROOT / f"{args.workspace_id}.json"

    if state_path.exists():
        state = read_json(state_path)
        if (
            state.get("runId") == args.run_id
            and state.get("packageSha256") == args.sha256
            and target.is_dir()
            and not target.is_symlink()
        ):
            stored_policy = validate_fixture_policy_shape(state.get("fixturePolicy"))
            verify_fixture_marker(target, stored_policy)
            return {**state, "changed": False}
        raise ReconstructError("an incompatible workspace reconstruction already exists")
    if target.exists() or target.is_symlink():
        raise ReconstructError("target workspace already exists without a committed reconstruction")

    # Keep staging and the provider-visible workspace under the same mount path.
    # Linux does not permit rename(2) across a bind-mount boundary, even when the
    # source and destination ultimately refer to the same backing EBS filesystem.
    staging_parent = WORKSPACE_ROOT / ".lift-staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    os.chmod(staging_parent, 0o700)
    with tempfile.TemporaryDirectory(prefix=f"{args.run_id}-", dir=staging_parent) as temp_name:
        temporary = Path(temp_name)
        extracted = temporary / "package"
        extracted.mkdir()
        with tarfile.open(package, "r:gz") as archive:
            member_names = {member.name for member in archive.getmembers()}
            if member_names != EXPECTED_ARCHIVE_MEMBERS:
                raise ReconstructError(f"unexpected archive members: {sorted(member_names)}")
            for member in archive.getmembers():
                if not member.isfile():
                    raise ReconstructError("Lift Off archive may contain regular files only")
            archive.extractall(extracted, filter="data")

        session = read_json(extracted / "session.json")
        manifest = read_json(extracted / "manifest.json")
        if session.get("runId") != args.run_id or session.get("workspaceId") != args.workspace_id:
            raise ReconstructError("package identity does not match the requested reconstruction")
        canonical = json.dumps(
            {"schemaVersion": manifest.get("schemaVersion"), "entries": manifest.get("entries")},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        manifest_sha = hashlib.sha256(canonical).hexdigest()
        if manifest.get("manifestSha256") != manifest_sha:
            raise ReconstructError("manifest self-hash mismatch")
        if session.get("manifestSha256") != manifest_sha:
            raise ReconstructError("session manifest hash mismatch")
        fixture_policy = validate_fixture_policy(
            session.get("fixturePolicy"),
            manifest,
        )

        if ledger.exists():
            if ledger.is_symlink() or not ledger.is_dir():
                raise ReconstructError("private ledger path is not a physical directory")
            existing_commit = git(
                [
                    f"--git-dir={ledger}",
                    "rev-parse",
                    f"{session['baselineRef']}^{{commit}}",
                ]
            ).strip()
            if existing_commit != session["baselineCommit"]:
                raise ReconstructError("existing private ledger does not match this package")
        else:
            git(["init", "--bare", str(ledger)])
            git(
                [
                    f"--git-dir={ledger}",
                    "fetch",
                    "--no-tags",
                    str(extracted / "ledger.bundle"),
                    f"{session['baselineRef']}:{session['baselineRef']}",
                ]
            )
        temporary_workspace = temporary / "workspace"
        git(["clone", "--no-checkout", str(ledger), str(temporary_workspace)])
        git(["checkout", "--detach", session["baselineCommit"]], cwd=temporary_workspace)
        verify_manifest(temporary_workspace, manifest)
        verify_fixture_marker(temporary_workspace, fixture_policy)

        lift_user = pwd.getpwnam("lift")
        chown_tree(temporary_workspace, lift_user.pw_uid, lift_user.pw_gid)
        os.replace(temporary_workspace, target)

    if target.is_symlink() or target.resolve(strict=True) != target:
        raise ReconstructError("provider-visible workspace is not a physical directory")
    mount_source = run(["findmnt", "-n", "-o", "SOURCE", "-T", str(target)]).strip()
    if not mount_source or mount_source == run(["findmnt", "-n", "-o", "SOURCE", "-T", "/"]).strip():
        raise ReconstructError("provider-visible workspace is not on the separate data volume")

    state = {
        "schemaVersion": 1,
        "runId": args.run_id,
        "workspaceId": args.workspace_id,
        "workspacePath": str(target),
        "ledgerPath": str(ledger),
        "baselineCommit": session["baselineCommit"],
        "baselineRef": session["baselineRef"],
        "manifestSha256": manifest_sha,
        "fixturePolicy": fixture_policy,
        "packageSha256": args.sha256,
        "mountSource": mount_source,
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(state_path, 0o600)
    return {**state, "changed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconstruct(args), sort_keys=True))
        return 0
    except ReconstructError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
