#!/usr/bin/env python3
"""Verify and import an exact final-cloud checkpoint for Lift Land.

This module is deliberately controller-side.  It accepts recovery artifacts that
have already been downloaded by exact S3 version, verifies them in a private
quarantine, and imports only the allowlisted Lift-private refs into the existing
session ledger.  It never discovers or opens a user's Git repository.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from workspace import WorkspaceError, fixture_policy_for_commit


SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SAFE_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
CHECKPOINT_SUFFIX = re.compile(r"^[0-9]{4}-[a-z0-9][a-z0-9-]{0,47}$")
FINAL_CHECKPOINT_SUFFIX = re.compile(r"^[0-9]{4}-land-final$")
MAX_MANIFEST_SIZE = 16 * 1024 * 1024
MAX_BUNDLE_SIZE = 1024 * 1024 * 1024
ZERO_OID = "0" * 40


class LiveLandError(RuntimeError):
    """The final checkpoint could not be safely imported or acknowledged."""


def _canonical_bytes(value: object, *, newline: bool = False) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            # Match the checkpoint/workspace canonicalization contract used by
            # the producer (the json module's stable ASCII escaping).
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise LiveLandError("value is not canonical JSON") from exc
    return encoded + (b"\n" if newline else b"")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _valid_oid(value: object) -> bool:
    return isinstance(value, str) and OBJECT_ID.fullmatch(value) is not None


def _valid_s3_version_id(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value == "null"
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= 1024
    except UnicodeEncodeError:
        return False


def _git_environment() -> dict[str, str]:
    # In particular, remove alternate object directories, injected config,
    # work-tree/index selectors, and tracing that could disclose paths.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return environment


def _run_git(
    arguments: Sequence[str],
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
        raise LiveLandError(
            f"Git verification failed ({' '.join(command)}): {stderr}"
        )
    return completed


def _git_text(
    arguments: Sequence[str],
    *,
    git_dir: Path | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> str:
    return _run_git(
        arguments, git_dir=git_dir, cwd=cwd, check=check
    ).stdout.decode("utf-8")


def _physical_bare_ledger(path: Path) -> Path:
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LiveLandError("Lift-private ledger is missing") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or bool(info.st_mode & 0o022)
    ):
        raise LiveLandError("Lift-private ledger is not a safe physical directory")
    if _git_text(["rev-parse", "--is-bare-repository"], git_dir=resolved).strip() != "true":
        raise LiveLandError("Lift-private ledger is not a bare Git repository")
    return resolved


def _private_directory(path: Path) -> Path:
    if path.exists() or path.is_symlink():
        try:
            info = path.lstat()
        except OSError as exc:
            raise LiveLandError("Land quarantine could not be inspected") from exc
        if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise LiveLandError("Land quarantine is not a private physical directory")
    else:
        try:
            parent = path.parent.resolve(strict=True)
            if not parent.is_dir():
                raise LiveLandError("Land quarantine parent is not a directory")
            path.mkdir(mode=0o700)
        except OSError as exc:
            raise LiveLandError("Land quarantine could not be created") from exc
    os.chmod(path, 0o700)
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise LiveLandError("Land quarantine path is not physical")
    return resolved


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _read_regular(
    path: Path, *, description: str, maximum: int, link_count: int = 1
) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise LiveLandError(f"{description} is missing") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != link_count
        or before.st_size < 1
        or before.st_size > maximum
    ):
        raise LiveLandError(f"{description} is not a safe regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
            or opened.st_nlink != link_count
            or not stat.S_ISREG(opened.st_mode)
        ):
            raise LiveLandError(f"{description} changed while it was opened")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) != before.st_size or len(value) > maximum:
            raise LiveLandError(f"{description} changed while it was read")
        return value
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _owned_retain_temporary(path: Path) -> Path:
    # The destination name is a verified content digest at every call site.  A
    # destination-scoped name lets a retry identify its own interrupted write
    # without sweeping unrelated .retain-* files from the quarantine.
    return path.with_name(f".retain-{path.name}")


def _retain_exact_file(path: Path, value: bytes) -> None:
    maximum = max(MAX_BUNDLE_SIZE, MAX_MANIFEST_SIZE)
    temporary = _owned_retain_temporary(path)
    destination_exists = path.exists() or path.is_symlink()
    temporary_exists = temporary.exists() or temporary.is_symlink()

    if destination_exists:
        if temporary_exists:
            destination_info = path.lstat()
            temporary_info = temporary.lstat()
            if (
                destination_info.st_dev == temporary_info.st_dev
                and destination_info.st_ino == temporary_info.st_ino
            ):
                existing = _read_regular(
                    path,
                    description="published retained quarantine artifact",
                    maximum=maximum,
                    link_count=2,
                )
                if existing != value:
                    raise LiveLandError(
                        "retained quarantine artifact already differs"
                    )
                temporary.unlink()
                _fsync_directory(path.parent)
            else:
                existing = _read_regular(
                    path,
                    description="retained quarantine artifact",
                    maximum=maximum,
                )
                if existing != value:
                    raise LiveLandError(
                        "retained quarantine artifact already differs"
                    )
                staged = _read_regular(
                    temporary,
                    description="owned retained quarantine temporary",
                    maximum=maximum,
                )
                if staged != value:
                    raise LiveLandError(
                        "owned retained quarantine temporary already differs"
                    )
                temporary.unlink()
                _fsync_directory(path.parent)
        existing = _read_regular(
            path,
            description="retained quarantine artifact",
            maximum=maximum,
        )
        if existing != value:
            raise LiveLandError("retained quarantine artifact already differs")
        os.chmod(path, 0o600)
        return

    if temporary_exists:
        staged = _read_regular(
            temporary,
            description="owned retained quarantine temporary",
            maximum=maximum,
        )
        if staged != value:
            raise LiveLandError("owned retained quarantine temporary already differs")
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(value):
                written = os.write(descriptor, value[offset:])
                if written < 1:
                    raise LiveLandError(
                        "owned retained quarantine temporary could not be written"
                    )
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(path.parent)

    try:
        os.link(temporary, path, follow_symlinks=False)
    except FileExistsError:
        # A concurrent publisher may have won after our initial inspection.
        # Re-entering validates both names and never replaces the winner.
        _retain_exact_file(path, value)
        return
    _fsync_directory(path.parent)
    temporary.unlink()
    _fsync_directory(path.parent)

    retained = _read_regular(
        path,
        description="retained quarantine artifact",
        maximum=maximum,
    )
    if retained != value:
        raise LiveLandError("retained quarantine artifact already differs")


def _resolve_ref(repo: Path, ref: str) -> str | None:
    symbolic = _run_git(["symbolic-ref", "--quiet", ref], git_dir=repo, check=False)
    if symbolic.returncode == 0:
        raise LiveLandError(f"immutable Lift ref is unexpectedly symbolic: {ref}")
    if symbolic.returncode not in (1, 128):
        raise LiveLandError(f"immutable Lift ref could not be inspected: {ref}")
    result = _run_git(
        ["show-ref", "--verify", "--hash", ref], git_dir=repo, check=False
    )
    if result.returncode in (1, 128):
        return None
    if result.returncode != 0:
        raise LiveLandError(f"immutable Lift ref could not be inspected: {ref}")
    object_id = result.stdout.decode("ascii").strip()
    if not _valid_oid(object_id):
        raise LiveLandError(f"immutable Lift ref has an invalid object ID: {ref}")
    return object_id


def _publish_absent_or_identical(repo: Path, refs: Mapping[str, str]) -> None:
    missing: list[tuple[str, str]] = []
    for ref, object_id in sorted(refs.items()):
        existing = _resolve_ref(repo, ref)
        if existing is None:
            missing.append((ref, object_id))
        elif existing != object_id:
            raise LiveLandError(f"immutable Lift ref already differs: {ref}")
    if not missing:
        return
    transaction = ["start"]
    transaction.extend(f"create {ref} {object_id}" for ref, object_id in missing)
    transaction.extend(["prepare", "commit", ""])
    _run_git(
        ["update-ref", "--stdin"],
        git_dir=repo,
        input_bytes="\n".join(transaction).encode("ascii"),
    )
    for ref, object_id in sorted(refs.items()):
        if _resolve_ref(repo, ref) != object_id:
            raise LiveLandError(f"immutable Lift ref was not published exactly: {ref}")


def _resolve_commit(repo: Path, value: str) -> str:
    result = _git_text(["rev-parse", f"{value}^{{commit}}"], git_dir=repo).strip()
    if not _valid_oid(result):
        raise LiveLandError("Git returned an invalid commit ID")
    return result


def _tree_for_commit(repo: Path, commit: str) -> str:
    tree = _git_text(["show", "-s", "--format=%T", commit], git_dir=repo).strip()
    if not _valid_oid(tree):
        raise LiveLandError("Git returned an invalid tree ID")
    return tree


def _parents_for_commit(repo: Path, commit: str) -> list[str]:
    parents = _git_text(["show", "-s", "--format=%P", commit], git_dir=repo).split()
    if any(not _valid_oid(parent) for parent in parents):
        raise LiveLandError("Git returned an invalid commit parent")
    return parents


def _safe_tree_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\x00" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(part.casefold() == ".git" for part in path.parts)
    ):
        raise LiveLandError(f"unsafe path in final checkpoint tree: {raw}")
    return path


def _validate_symlink(path: PurePosixPath, target: str) -> None:
    if not target or "\x00" in target or PurePosixPath(target).is_absolute():
        raise LiveLandError(f"unsafe symbolic link in final checkpoint: {path}")
    normalized = PurePosixPath(posixpath.normpath(str(path.parent / target)))
    if str(normalized) == ".." or str(normalized).startswith("../"):
        raise LiveLandError(f"symbolic link escapes final checkpoint: {path}")
    if any(part.casefold() == ".git" for part in normalized.parts):
        raise LiveLandError(f"symbolic link targets Git administration state: {path}")


def _tree_entries(repo: Path, tree: str, *, excluded_path: str) -> list[dict[str, Any]]:
    raw = _run_git(
        ["ls-tree", "-r", "-z", "--full-tree", tree], git_dir=repo
    ).stdout
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        metadata, separator, path_bytes = encoded.partition(b"\t")
        if not separator:
            raise LiveLandError("final checkpoint tree listing is malformed")
        try:
            mode_bytes, type_bytes, oid_bytes = metadata.split(b" ", 2)
            path_text = path_bytes.decode("utf-8")
            mode = mode_bytes.decode("ascii")
            object_type = type_bytes.decode("ascii")
            object_id = oid_bytes.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise LiveLandError("final checkpoint tree listing is malformed") from exc
        path = _safe_tree_path(path_text)
        if path_text in seen:
            raise LiveLandError("final checkpoint tree repeats a path")
        seen.add(path_text)
        if path_text == excluded_path or path_text.startswith(excluded_path + "/"):
            raise LiveLandError("hard-excluded fixture path entered final checkpoint")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            raise LiveLandError(f"unsupported final checkpoint entry: {path_text}")
        if not _valid_oid(object_id):
            raise LiveLandError("final checkpoint tree has an invalid object ID")
        content = _run_git(["cat-file", "blob", object_id], git_dir=repo).stdout
        entry: dict[str, Any] = {
            "path": path_text,
            "type": "symlink" if mode == "120000" else "file",
            "sha256": _sha256_bytes(content),
            "size": len(content),
            "executable": mode == "100755",
            "gitMode": mode,
            "gitObjectId": object_id,
        }
        if mode == "120000":
            try:
                target = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LiveLandError(
                    f"symbolic link target is not UTF-8: {path_text}"
                ) from exc
            _validate_symlink(path, target)
            entry["target"] = target
        entries.append(entry)
    return entries


def _manifest_from_bytes(value: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveLandError("final checkpoint manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise LiveLandError("final checkpoint manifest is not an object")
    claimed = manifest.get("manifestSha256")
    if not _valid_sha(claimed):
        raise LiveLandError("final checkpoint manifest self-hash is invalid")
    unsigned = {key: item for key, item in manifest.items() if key != "manifestSha256"}
    if _sha256_bytes(_canonical_bytes(unsigned)) != claimed:
        raise LiveLandError("final checkpoint manifest failed its self-hash")
    return manifest


def _checked_ref_item(
    raw: object,
    *,
    kind: str,
    prefix: str,
    baseline_ref: str,
) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise LiveLandError(f"{kind} recovery ref entry is invalid")
    allowed = {"ref", "objectId"} if kind == "checkpoint" else {
        "source",
        "ref",
        "objectId",
    }
    required = {"ref", "objectId"}
    if not required.issubset(raw) or not set(raw).issubset(allowed):
        raise LiveLandError(f"{kind} recovery ref entry is invalid")
    ref = raw.get("ref")
    object_id = raw.get("objectId")
    if not isinstance(ref, str) or not _valid_oid(object_id):
        raise LiveLandError(f"{kind} recovery ref entry is invalid")
    if kind == "checkpoint":
        suffix = ref.removeprefix(prefix + "/checkpoints/")
        if ref != baseline_ref and (
            suffix == ref or CHECKPOINT_SUFFIX.fullmatch(suffix) is None
        ):
            raise LiveLandError("recovery checkpoint ref is outside the session namespace")
        if ref != baseline_ref and int(suffix[:4]) < 1:
            raise LiveLandError("recovery checkpoint ordinal is invalid")
    else:
        suffix = ref.removeprefix(prefix + "/git-history/")
        match = re.fullmatch(
            r"([0-9]{4})/(head|refs/(.+)|reflog/([0-9a-f]{40}))", suffix
        )
        if (
            suffix == ref
            or match is None
            or int(match.group(1)) < 1
            or any(part in {"", ".", ".."} for part in suffix.split("/"))
        ):
            raise LiveLandError("recovery history ref is outside the session namespace")
        check = _run_git(["check-ref-format", ref], check=False)
        if check.returncode != 0:
            raise LiveLandError("recovery history ref is invalid")
        source = raw.get("source")
        if source is not None and (not isinstance(source, str) or not source):
            raise LiveLandError("recovery history source is invalid")
        if match.group(4) is not None and match.group(4) != object_id:
            raise LiveLandError("recovery reflog ref does not match its object ID")
    return ref, object_id


def _expected_bundle_heads(
    checkpoint: Mapping[str, Any],
    *,
    prefix: str,
    baseline_ref: str,
    baseline_commit: str,
    final_ref: str,
    final_commit: str,
) -> tuple[dict[str, str], dict[str, str]]:
    checkpoint_refs = checkpoint.get("recoveryCheckpointRefs")
    history_refs = checkpoint.get("recoveryHistoryRefs")
    if not isinstance(checkpoint_refs, list) or not isinstance(history_refs, list):
        raise LiveLandError("final checkpoint omitted its exact recovery ref maps")
    expected: dict[str, str] = {}
    publish: dict[str, str] = {}
    checkpoint_ref_order: list[str] = []
    for kind, values in (("checkpoint", checkpoint_refs), ("history", history_refs)):
        seen: set[str] = set()
        for raw in values:
            ref, object_id = _checked_ref_item(
                raw, kind=kind, prefix=prefix, baseline_ref=baseline_ref
            )
            if ref in seen or (ref in expected and expected[ref] != object_id):
                raise LiveLandError("final checkpoint recovery ref map is ambiguous")
            seen.add(ref)
            if ref in expected:
                raise LiveLandError("final checkpoint recovery ref map repeats a ref")
            expected[ref] = object_id
            if kind == "checkpoint":
                checkpoint_ref_order.append(ref)
            if ref != baseline_ref:
                publish[ref] = object_id
    if expected.get(baseline_ref) != baseline_commit:
        raise LiveLandError("recovery bundle is not bound to the local handoff baseline")
    if expected.get(final_ref) != final_commit:
        raise LiveLandError("recovery bundle is not bound to the final checkpoint")
    if (
        not checkpoint_ref_order
        or checkpoint_ref_order[0] != baseline_ref
        or checkpoint_ref_order[-1] != final_ref
    ):
        raise LiveLandError("recovery checkpoint ref order is not canonical")
    ordinals = [
        int(ref.removeprefix(prefix + "/checkpoints/")[:4])
        for ref in checkpoint_ref_order[1:]
    ]
    if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
        raise LiveLandError("recovery checkpoint ref order is not canonical")
    current_history = checkpoint.get("historyRefs")
    if current_history is not None:
        if not isinstance(current_history, list):
            raise LiveLandError("current checkpoint history ref map is invalid")
        recovered_history = {
            (item.get("ref"), item.get("objectId"))
            for item in history_refs
            if isinstance(item, dict)
        }
        for raw in current_history:
            ref, object_id = _checked_ref_item(
                raw, kind="history", prefix=prefix, baseline_ref=baseline_ref
            )
            if (ref, object_id) not in recovered_history:
                raise LiveLandError("current checkpoint history is missing from recovery map")
    return expected, publish


def _bundle_heads(bundle: Path) -> dict[str, str]:
    listed: dict[str, str] = {}
    output = _git_text(["bundle", "list-heads", str(bundle)])
    for line in output.splitlines():
        object_id, separator, ref = line.partition(" ")
        if not separator or not _valid_oid(object_id) or not ref or ref in listed:
            raise LiveLandError("recovery bundle head map is malformed")
        listed[ref] = object_id
    return listed


def _verify_checkpoint_record(
    checkpoint: Mapping[str, Any],
    *,
    prefix: str,
    baseline_ref: str,
    baseline_commit: str,
) -> tuple[str, str, str, list[str], dict[str, Any]]:
    final_ref = checkpoint.get("ref")
    final_commit = checkpoint.get("commit")
    final_tree = checkpoint.get("tree")
    parents = checkpoint.get("parents")
    fixture_policy = checkpoint.get("fixturePolicy")
    if not isinstance(final_ref, str):
        raise LiveLandError("final checkpoint ref is invalid")
    suffix = final_ref.removeprefix(prefix + "/checkpoints/")
    if suffix == final_ref or FINAL_CHECKPOINT_SUFFIX.fullmatch(suffix) is None:
        raise LiveLandError("checkpoint is not the canonical final Land checkpoint")
    if (
        not _valid_oid(final_commit)
        or not _valid_oid(final_tree)
        or not isinstance(parents, list)
        or any(not _valid_oid(parent) for parent in parents)
        or not parents
        or not isinstance(fixture_policy, dict)
    ):
        raise LiveLandError("final checkpoint Git identity is invalid")
    if checkpoint.get("ordinal") != int(suffix[:4]):
        raise LiveLandError("final checkpoint ordinal does not match its ref")
    if int(suffix[:4]) < 1:
        raise LiveLandError("final checkpoint ordinal is invalid")
    for key in ("bundleSha256", "manifestSha256", "manifestFileSha256"):
        if not _valid_sha(checkpoint.get(key)):
            raise LiveLandError(f"final checkpoint {key} is invalid")
    for key, maximum in (
        ("bundleSize", MAX_BUNDLE_SIZE),
        ("manifestSize", MAX_MANIFEST_SIZE),
    ):
        value = checkpoint.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > maximum:
            raise LiveLandError(f"final checkpoint {key} is invalid")
    if not _valid_s3_version_id(checkpoint.get("s3VersionId")) or not _valid_s3_version_id(
        checkpoint.get("s3ManifestVersionId")
    ):
        raise LiveLandError("final checkpoint S3 version identity is invalid")
    if checkpoint.get("baselineRef") not in (None, baseline_ref) or checkpoint.get(
        "baselineCommit"
    ) not in (None, baseline_commit):
        raise LiveLandError("final checkpoint baseline identity differs")
    return final_ref, final_commit, final_tree, list(parents), dict(fixture_policy)


def import_final_checkpoint(
    *,
    ledger: Path,
    quarantine_root: Path,
    bundle_path: Path,
    manifest_path: Path,
    checkpoint: Mapping[str, Any],
    run_id: str,
    workspace_id: str,
    baseline_ref: str,
    baseline_commit: str,
) -> dict[str, Any]:
    """Import a final Land checkpoint after exact, isolated verification.

    ``checkpoint`` is the controller's exact durable-checkpoint record and must
    include the two non-null S3 VersionIds.  ``bundle_path`` and
    ``manifest_path`` are already-downloaded objects for those versions.
    """

    if not SAFE_ID.fullmatch(run_id) or not SAFE_ID.fullmatch(workspace_id):
        raise LiveLandError("run and workspace IDs are invalid")
    prefix = f"refs/lift/{workspace_id}/sessions/{run_id}"
    if baseline_ref != f"{prefix}/baseline" or not _valid_oid(baseline_commit):
        raise LiveLandError("handoff baseline identity is invalid")
    ledger = _physical_bare_ledger(ledger)
    if _resolve_commit(ledger, baseline_ref) != baseline_commit:
        raise LiveLandError("local handoff baseline ref does not match its commit")
    try:
        local_fixture_policy = fixture_policy_for_commit(ledger, baseline_commit)
    except WorkspaceError as exc:
        raise LiveLandError("local handoff baseline fixture policy is invalid") from exc

    final_ref, final_commit, final_tree, parents, fixture_policy = (
        _verify_checkpoint_record(
            checkpoint,
            prefix=prefix,
            baseline_ref=baseline_ref,
            baseline_commit=baseline_commit,
        )
    )
    if fixture_policy != local_fixture_policy:
        raise LiveLandError("final checkpoint fixture policy differs from the baseline")
    expected_heads, publish_heads = _expected_bundle_heads(
        checkpoint,
        prefix=prefix,
        baseline_ref=baseline_ref,
        baseline_commit=baseline_commit,
        final_ref=final_ref,
        final_commit=final_commit,
    )

    bundle_bytes = _read_regular(
        bundle_path, description="downloaded final checkpoint bundle", maximum=MAX_BUNDLE_SIZE
    )
    manifest_bytes = _read_regular(
        manifest_path,
        description="downloaded final checkpoint manifest",
        maximum=MAX_MANIFEST_SIZE,
    )
    if (
        len(bundle_bytes) != checkpoint["bundleSize"]
        or _sha256_bytes(bundle_bytes) != checkpoint["bundleSha256"]
    ):
        raise LiveLandError("downloaded final checkpoint bundle is not exact")
    if (
        len(manifest_bytes) != checkpoint["manifestSize"]
        or _sha256_bytes(manifest_bytes) != checkpoint["manifestFileSha256"]
    ):
        raise LiveLandError("downloaded final checkpoint manifest file is not exact")

    manifest = _manifest_from_bytes(manifest_bytes)
    base_manifest_keys = {
        "schemaVersion",
        "runId",
        "workspaceId",
        "checkpointRef",
        "commit",
        "tree",
        "parents",
        "gitSnapshotSha256",
        "entries",
        "manifestSha256",
    }
    optional_bound_keys = {"baselineRef", "baselineCommit", "fixturePolicy"}
    if not base_manifest_keys.issubset(manifest) or not set(manifest).issubset(
        base_manifest_keys | optional_bound_keys
    ):
        raise LiveLandError("final checkpoint manifest schema is not exact")
    expected_manifest = {
        "schemaVersion": 1,
        "runId": run_id,
        "workspaceId": workspace_id,
        "checkpointRef": final_ref,
        "commit": final_commit,
        "tree": final_tree,
        "parents": parents,
        "gitSnapshotSha256": checkpoint.get("gitSnapshotSha256"),
        "manifestSha256": checkpoint["manifestSha256"],
    }
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise LiveLandError("final checkpoint manifest identity differs")
    for key, expected in (
        ("baselineRef", baseline_ref),
        ("baselineCommit", baseline_commit),
        ("fixturePolicy", fixture_policy),
    ):
        if key in manifest and manifest[key] != expected:
            raise LiveLandError(f"final checkpoint manifest {key} differs")

    quarantine = _private_directory(quarantine_root)
    if _is_within(quarantine, ledger) or _is_within(ledger, quarantine):
        raise LiveLandError("Land quarantine and private ledger must be separate")
    retained_bundle = quarantine / f"{checkpoint['bundleSha256']}.bundle"
    retained_manifest = quarantine / f"{checkpoint['manifestFileSha256']}.manifest.json"
    _retain_exact_file(retained_bundle, bundle_bytes)
    _retain_exact_file(retained_manifest, manifest_bytes)
    if _bundle_heads(retained_bundle) != expected_heads:
        raise LiveLandError("recovery bundle contains a non-exact head map")

    verification_parent = Path(
        tempfile.mkdtemp(prefix="verify-", dir=quarantine)
    )
    os.chmod(verification_parent, 0o700)
    try:
        verification_repo = verification_parent / "objects.git"
        _run_git(["init", "--bare", str(verification_repo)], cwd=verification_parent)
        _run_git(["bundle", "verify", str(retained_bundle)], git_dir=verification_repo)
        _run_git(["bundle", "unbundle", str(retained_bundle)], git_dir=verification_repo)
        for ref, object_id in expected_heads.items():
            exists = _run_git(
                ["cat-file", "-e", f"{object_id}^{{object}}"],
                git_dir=verification_repo,
                check=False,
            )
            if exists.returncode != 0:
                raise LiveLandError(f"recovery bundle omitted allowlisted object: {ref}")
        _publish_absent_or_identical(verification_repo, expected_heads)

        if _resolve_commit(verification_repo, final_ref) != final_commit:
            raise LiveLandError("recovered final checkpoint commit differs")
        if _tree_for_commit(verification_repo, final_commit) != final_tree:
            raise LiveLandError("recovered final checkpoint tree differs")
        if _parents_for_commit(verification_repo, final_commit) != parents:
            raise LiveLandError("recovered final checkpoint parents differ")
        if _resolve_commit(verification_repo, baseline_ref) != baseline_commit:
            raise LiveLandError("recovered baseline object differs")
        ancestry = _run_git(
            ["merge-base", "--is-ancestor", baseline_commit, final_commit],
            git_dir=verification_repo,
            check=False,
        )
        if ancestry.returncode != 0:
            raise LiveLandError("final checkpoint is not descended from the handoff baseline")
        try:
            recovered_baseline_policy = fixture_policy_for_commit(
                verification_repo, baseline_commit
            )
            recovered_final_policy = fixture_policy_for_commit(
                verification_repo, final_commit
            )
        except WorkspaceError as exc:
            raise LiveLandError("recovered fixture policy is invalid") from exc
        if recovered_baseline_policy != fixture_policy or recovered_final_policy != fixture_policy:
            raise LiveLandError("recovered fixture policy differs from the handoff baseline")
        entries = _tree_entries(
            verification_repo,
            final_tree,
            excluded_path=str(fixture_policy["excludedSentinelPath"]),
        )
        if manifest.get("entries") != entries:
            raise LiveLandError("recovered final tree entries differ from the manifest")

        sanitized_temporary = verification_parent / "sanitized.bundle"
        _run_git(
            ["bundle", "create", str(sanitized_temporary), *sorted(expected_heads)],
            git_dir=verification_repo,
        )
        if _bundle_heads(sanitized_temporary) != expected_heads:
            raise LiveLandError("sanitized recovery bundle head map differs")
        sanitized_sha = _sha256_bytes(sanitized_temporary.read_bytes())
        sanitized_bundle = quarantine / f"sanitized-{sanitized_sha}.bundle"
        _retain_exact_file(sanitized_bundle, sanitized_temporary.read_bytes())

        # Only after the isolated graph/content checks pass do objects enter the
        # durable ledger.  Unbundle writes objects but does not update refs.
        _run_git(["bundle", "verify", str(sanitized_bundle)], git_dir=ledger)
        _run_git(["bundle", "unbundle", str(sanitized_bundle)], git_dir=ledger)
        for ref, object_id in publish_heads.items():
            exists = _run_git(
                ["cat-file", "-e", f"{object_id}^{{object}}"],
                git_dir=ledger,
                check=False,
            )
            if exists.returncode != 0:
                raise LiveLandError(f"imported object is missing before ref publication: {ref}")
        _publish_absent_or_identical(ledger, publish_heads)
    finally:
        shutil.rmtree(verification_parent)

    # Re-read the local baseline last.  It was never included in the publication
    # set, so a remote bundle cannot replace or create it.
    if _resolve_commit(ledger, baseline_ref) != baseline_commit:
        raise LiveLandError("local handoff baseline changed during checkpoint import")
    if _resolve_commit(ledger, final_ref) != final_commit:
        raise LiveLandError("final checkpoint ref was not imported exactly")
    imported_refs = [
        {
            "kind": (
                "checkpoint" if ref.startswith(prefix + "/checkpoints/") else "history"
            ),
            "ref": ref,
            "objectId": object_id,
        }
        for ref, object_id in sorted(publish_heads.items())
    ]
    imported_refs_sha = _sha256_bytes(_canonical_bytes(imported_refs))
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "runId": run_id,
        "workspaceId": workspace_id,
        "baselineRef": baseline_ref,
        "baselineCommit": baseline_commit,
        "checkpointRef": final_ref,
        "checkpointCommit": final_commit,
        "checkpointTree": final_tree,
        "checkpointParents": parents,
        "fixturePolicy": fixture_policy,
        "bundleSha256": checkpoint["bundleSha256"],
        "bundleSize": checkpoint["bundleSize"],
        "manifestSha256": checkpoint["manifestSha256"],
        "manifestFileSha256": checkpoint["manifestFileSha256"],
        "manifestSize": checkpoint["manifestSize"],
        "s3VersionId": checkpoint["s3VersionId"],
        "s3ManifestVersionId": checkpoint["s3ManifestVersionId"],
        "fileCount": len(manifest["entries"]),
        "quarantinePath": str(quarantine),
        "importedRefs": imported_refs,
        "importedRefsSha256": imported_refs_sha,
    }
    record["importSha256"] = _sha256_bytes(_canonical_bytes(record))
    return record


def _canonical_mapping(value: Mapping[str, Any], description: str) -> dict[str, Any]:
    try:
        normalized = json.loads(_canonical_bytes(value).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # pragma: no cover
        raise LiveLandError(f"{description} is not canonical JSON") from exc
    if not isinstance(normalized, dict):
        raise LiveLandError(f"{description} is not an object")
    return normalized


def _verify_manifest_self_hash(
    manifest: Mapping[str, Any], expected_sha256: str
) -> dict[str, Any]:
    normalized = _canonical_mapping(manifest, "final local manifest")
    claimed = normalized.get("manifestSha256")
    if claimed != expected_sha256 or not _valid_sha(claimed):
        raise LiveLandError("final local manifest SHA-256 differs")
    unsigned = {key: value for key, value in normalized.items() if key != "manifestSha256"}
    if _sha256_bytes(_canonical_bytes(unsigned)) != claimed:
        raise LiveLandError("final local manifest failed its self-hash")
    return normalized


def _verify_receipt(receipt: Mapping[str, Any], land_result: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _canonical_mapping(receipt, "Land receipt")
    receipt_sha = normalized.get("receiptSha256")
    if not _valid_sha(receipt_sha):
        raise LiveLandError("Land receipt SHA-256 is invalid")
    unsigned = {
        key: value
        for key, value in normalized.items()
        if key not in {"receiptSha256", "receiptBlob", "receiptTree", "receiptCommit"}
    }
    if _sha256_bytes(_canonical_bytes(unsigned, newline=True)) != receipt_sha:
        raise LiveLandError("Land receipt failed its content hash")
    exact = {
        "baselineCommit": land_result.get("baselineCommit"),
        "cloudCommit": land_result.get("cloudFinalCommit"),
        "localCommit": land_result.get("localReturnCommit"),
        "mergeCommit": land_result.get("mergeResultCommit"),
        "receiptRef": land_result.get("receiptRef"),
        "receiptCommit": land_result.get("receiptCommit"),
    }
    if any(normalized.get(key) != value for key, value in exact.items()):
        raise LiveLandError("Land receipt is not bound to the local Land result")
    for key in ("receiptBlob", "receiptTree", "receiptCommit"):
        if not _valid_oid(normalized.get(key)):
            raise LiveLandError(f"Land receipt {key} is invalid")
    return normalized


def build_land_acknowledgement(
    *,
    operation_id: str,
    checkpoint: Mapping[str, Any],
    land_result: Mapping[str, Any],
    receipt: Mapping[str, Any],
    final_local_manifest: Mapping[str, Any],
    final_local_manifest_sha256: str,
) -> dict[str, Any]:
    """Build the canonical durable acknowledgement for one applied Land."""

    if not SAFE_OPERATION_ID.fullmatch(operation_id):
        raise LiveLandError("Land operation ID is invalid")
    normalized_checkpoint = _canonical_mapping(checkpoint, "final checkpoint")
    normalized_result = _canonical_mapping(land_result, "local Land result")
    if normalized_result.get("schemaVersion") != 1 or normalized_result.get("outcome") != "APPLIED":
        raise LiveLandError("only a verified applied Land can be acknowledged")
    normalized_receipt = _verify_receipt(receipt, normalized_result)
    normalized_manifest = _verify_manifest_self_hash(
        final_local_manifest, final_local_manifest_sha256
    )
    for key in ("bundleSha256", "manifestSha256", "manifestFileSha256"):
        if not _valid_sha(normalized_checkpoint.get(key)):
            raise LiveLandError(f"final checkpoint {key} is invalid")
    if not _valid_s3_version_id(normalized_checkpoint.get("s3VersionId")) or not _valid_s3_version_id(
        normalized_checkpoint.get("s3ManifestVersionId")
    ):
        raise LiveLandError("final checkpoint S3 version identity is invalid")
    checkpoint_ref = normalized_checkpoint.get("ref")
    if not isinstance(checkpoint_ref, str):
        raise LiveLandError("final checkpoint ref is invalid")
    identity = re.fullmatch(
        r"refs/lift/([a-z0-9][a-z0-9-]{2,63})/sessions/"
        r"([a-z0-9][a-z0-9-]{2,63})/checkpoints/([0-9]{4}-land-final)",
        checkpoint_ref,
    )
    if identity is None:
        raise LiveLandError("final checkpoint ref is not canonical")
    workspace_id, run_id, _ = identity.groups()
    if normalized_checkpoint.get("workspaceId") not in (None, workspace_id) or normalized_checkpoint.get(
        "runId"
    ) not in (None, run_id):
        raise LiveLandError("final checkpoint run or workspace identity differs")
    expected_cloud_final_ref = (
        f"refs/lift/{workspace_id}/sessions/{run_id}/cloud-final"
    )
    if (
        normalized_result.get("cloudFinalRef") != expected_cloud_final_ref
        or normalized_result.get("cloudFinalCommit") != normalized_checkpoint.get("commit")
        or not _valid_oid(normalized_result.get("baselineCommit"))
    ):
        raise LiveLandError("local Land result is not bound to the final checkpoint")
    baseline_ref = normalized_result.get("baselineRef")
    baseline_commit = normalized_result.get("baselineCommit")
    if (
        normalized_manifest.get("runId") != run_id
        or normalized_manifest.get("workspaceId") != workspace_id
        or normalized_manifest.get("mergeResultCommit")
        != normalized_result.get("mergeResultCommit")
    ):
        raise LiveLandError("final local manifest is not bound to the Land result")
    recovery = normalized_checkpoint.get("recoveryCheckpointRefs")
    if (
        not isinstance(baseline_ref, str)
        or not isinstance(recovery, list)
        or not any(
            isinstance(item, dict)
            and item.get("ref") == baseline_ref
            and item.get("objectId") == baseline_commit
            for item in recovery
        )
    ):
        raise LiveLandError("final checkpoint is not bound to the Land baseline")

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "lift-land-acknowledgement",
        "operationId": operation_id,
        "runId": run_id,
        "workspaceId": workspace_id,
        "baseline": {"ref": baseline_ref, "commit": baseline_commit},
        "cloudFinal": {
            "checkpointRef": checkpoint_ref,
            "landRef": expected_cloud_final_ref,
            "commit": normalized_checkpoint.get("commit"),
            "tree": normalized_checkpoint.get("tree"),
            "parents": normalized_checkpoint.get("parents"),
        },
        "recoveryObjects": {
            "bundle": {
                "sha256": normalized_checkpoint["bundleSha256"],
                "s3ObjectKey": normalized_checkpoint.get("s3ObjectKey"),
                "s3VersionId": normalized_checkpoint["s3VersionId"],
            },
            "manifest": {
                "sha256": normalized_checkpoint["manifestSha256"],
                "fileSha256": normalized_checkpoint["manifestFileSha256"],
                "s3ObjectKey": normalized_checkpoint.get("s3ManifestObjectKey"),
                "s3VersionId": normalized_checkpoint["s3ManifestVersionId"],
            },
        },
        "localLand": {
            "resultSha256": _sha256_bytes(_canonical_bytes(normalized_result)),
            "outcome": normalized_result["outcome"],
            "localReturnRef": normalized_result.get("localReturnRef"),
            "localReturnCommit": normalized_result.get("localReturnCommit"),
            "mergeResultRef": normalized_result.get("mergeResultRef"),
            "mergeResultCommit": normalized_result.get("mergeResultCommit"),
            "verifiedAt": normalized_result.get("verifiedAt"),
            "receiptRef": normalized_receipt["receiptRef"],
            "receiptCommit": normalized_receipt["receiptCommit"],
            "receiptSha256": normalized_receipt["receiptSha256"],
        },
        "finalLocalManifest": normalized_manifest,
        "finalLocalManifestSha256": final_local_manifest_sha256,
    }
    payload["acknowledgementSha256"] = _sha256_bytes(_canonical_bytes(payload))
    return payload
