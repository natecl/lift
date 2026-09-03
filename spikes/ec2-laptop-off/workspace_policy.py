"""Local-only discovery and approval policy for a real Lift workspace.

This module deliberately has no transfer, ledger, or cloud dependencies.  It
turns a physical Git worktree into a reviewable candidate, binds explicit path
decisions to that exact candidate, and emits a portable policy containing only
approved entries.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from typing import Iterable, Mapping
import unicodedata


CATEGORY_ORDER = (
    "tracked",
    "staged",
    "dirty",
    "untracked",
    "ignored",
    "sensitive",
    "hard-excluded",
    "unsupported",
)
DECISIONS = frozenset({"include", "exclude"})

_HARD_EXCLUDED_COMPONENTS = frozenset(
    {
        ".git",
        ".gnupg",
        ".password-store",
        ".ssh",
    }
)
_PROTECTED_ACCOUNT_COMPONENTS = frozenset(
    {
        ".aws",
        ".codex",
        ".docker",
        ".gnupg",
        ".kube",
        ".password-store",
        ".ssh",
        "keychains",
    }
)
_HARD_EXCLUDED_BASENAMES = frozenset(
    {
        ".credentials.json",
        ".git-credentials",
        "cookies",
        "cookies.binarycookies",
        "cookies.sqlite",
        "key3.db",
        "key4.db",
        "login data",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "login.keychain",
        "login.keychain-db",
        "logins.json",
        "signons.sqlite",
        "web data",
    }
)
_HARD_EXCLUDED_SUFFIXES = (
    ".kdbx",
    ".keychain",
    ".keychain-db",
    ".p12",
    ".pfx",
)
_SENSITIVE_BASENAMES = frozenset(
    {
        ".envrc",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
        "credentials.toml",
        "credentials.yaml",
        "credentials.yml",
        "secrets.json",
        "secrets.toml",
        "secrets.yaml",
        "secrets.yml",
    }
)
_SENSITIVE_SUFFIXES = (".key", ".pem")
_DATABASE_SUFFIXES = (".db", ".db3", ".sqlite", ".sqlite3")
_DATABASE_SIDECAR_SUFFIXES = ("-journal", "-shm", "-wal")
_MAX_PATH_BYTES = 1024
_MAX_COMPONENT_BYTES = 255
_MAX_PATH_DEPTH = 64
_MAX_WORKSPACE_ENTRIES = 100_000
_MAX_FILE_BYTES = 512 * 1024 * 1024
_MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024
_MAX_GIT_INDEX_BYTES = 512 * 1024 * 1024
_MAX_EXCLUDES_BYTES = 4 * 1024 * 1024
_GIT_COMMAND_TIMEOUT_SECONDS = 30
_TRUSTED_GIT_CANDIDATES = (Path("/usr/bin/git"), Path("/bin/git"))
_CONTENT_SCAN_BYTES = 64 * 1024
_CONTENT_SCAN_OVERLAP = 4 * 1024
_PRIVATE_KEY_MARKERS = (
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"PuTTY-User-Key-File-",
)
_KNOWN_TOKEN_PATTERN = re.compile(
    rb"(?:AKIA|ASIA)[0-9A-Z]{16}|"
    rb"github_pat_[A-Za-z0-9_]{20,}|"
    rb"gh[pousr]_[A-Za-z0-9]{20,}|"
    rb"sk-[A-Za-z0-9_-]{20,}"
)
_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    rb"(?im)(?:^|[,{]\s*)[\"']?"
    rb"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    rb"private[_-]?token|aws[_-]?access[_-]?key[_-]?id|"
    rb"aws[_-]?secret[_-]?access[_-]?key|aws[_-]?session[_-]?token|password)"
    rb"[\"']?\s*[:=]\s*[\"']?([^\"'\s,}#]{8,})"
)
_PLACEHOLDER_CREDENTIAL_VALUES = frozenset(
    {
        b"changeme",
        b"dummy",
        b"example",
        b"fake",
        b"placeholder",
        b"replace-me",
        b"replace_me",
        b"test",
    }
)
_IN_PROGRESS_GIT_NAMES = frozenset(
    {
        "BISECT_START",
        "CHERRY_PICK_HEAD",
        "HEAD.lock",
        "MERGE_HEAD",
        "REBASE_HEAD",
        "REVERT_HEAD",
        "config.lock",
        "index.lock",
        "packed-refs.lock",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
        "shallow.lock",
    }
)
_NETWORK_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "davfs",
        "fuse.rclone",
        "fuse.sshfs",
        "glusterfs",
        "nfs",
        "nfs4",
        "smb",
        "smb2",
        "smb3",
        "smbfs",
    }
)


class WorkspacePolicyError(RuntimeError):
    """The selected workspace or a proposed approval is unsafe or invalid."""


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_git_sha1(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def canonical_sha256(value: object) -> str:
    """Return SHA-256 of the one canonical JSON representation used by Lift."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _new_git_sha1():
    try:
        return hashlib.sha1(usedforsecurity=False)
    except TypeError:  # pragma: no cover - compatibility with older Python builds
        return hashlib.sha1()


def _git_blob_sha1(value: bytes) -> str:
    digest = _new_git_sha1()
    digest.update(f"blob {len(value)}\0".encode("ascii"))
    digest.update(value)
    return digest.hexdigest()


def _validate_relative_path(path: str) -> None:
    if not path or "\x00" in path:
        raise WorkspacePolicyError("workspace contains an invalid empty path")
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspacePolicyError("workspace path is not valid UTF-8") from exc
    candidate = PurePosixPath(path)
    if (
        path == "."
        or path != candidate.as_posix()
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise WorkspacePolicyError(f"workspace path is outside its root: {path!r}")
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise WorkspacePolicyError(
            "workspace paths containing control characters are unsupported"
        )
    if len(encoded) > _MAX_PATH_BYTES or len(candidate.parts) > _MAX_PATH_DEPTH:
        raise WorkspacePolicyError("workspace path exceeds the portable v1 limit")
    if any(
        len(part.encode("utf-8")) > _MAX_COMPONENT_BYTES for part in candidate.parts
    ):
        raise WorkspacePolicyError(
            "workspace path component exceeds the portable v1 limit"
        )


def _sorted_paths(paths: Iterable[str]) -> list[str]:
    values = list(paths)
    for value in values:
        _validate_relative_path(value)
    return sorted(values, key=lambda value: value.encode("utf-8"))


def _validate_unique_ordered_paths(paths: list[str], *, label: str) -> None:
    expected = _sorted_paths(paths)
    if paths != expected or len(paths) != len(set(paths)):
        raise WorkspacePolicyError(f"{label} paths are not uniquely ordered")
    portable: dict[str, str] = {}
    for path in paths:
        key = unicodedata.normalize("NFC", path).casefold()
        previous = portable.setdefault(key, path)
        if previous != path:
            raise WorkspacePolicyError(f"{label} paths collide after normalization")


def _categories(*values: str) -> tuple[str, ...]:
    selected = set(values)
    unknown = selected.difference(CATEGORY_ORDER)
    if unknown:
        raise WorkspacePolicyError(
            f"unknown candidate classification: {sorted(unknown)!r}"
        )
    return tuple(value for value in CATEGORY_ORDER if value in selected)


def _disposition(categories: tuple[str, ...]) -> str:
    category_set = set(categories)
    if category_set.intersection({"hard-excluded", "unsupported"}):
        return "stays-local"
    if category_set.intersection({"ignored", "sensitive"}):
        return "needs-approval"
    return "will-move"


@dataclass(frozen=True)
class WorkspaceIdentityV1:
    root_device: int
    root_inode: int
    git_device: int
    git_inode: int
    head: str
    branch: str | None
    index_sha256: str
    refs_sha256: str
    excludes_sha256: str

    def assert_valid(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (
                self.root_device,
                self.root_inode,
                self.git_device,
                self.git_inode,
            )
        ):
            raise WorkspacePolicyError("workspace physical identity is invalid")
        if not _is_git_sha1(self.head):
            raise WorkspacePolicyError("workspace HEAD identity is invalid")
        if not isinstance(self.branch, str) or not self.branch:
            raise WorkspacePolicyError("workspace branch identity is invalid")
        if (
            not _is_sha256(self.index_sha256)
            or not _is_sha256(self.refs_sha256)
            or not _is_sha256(self.excludes_sha256)
        ):
            raise WorkspacePolicyError("workspace Git state identity is invalid")

    def to_dict(self) -> dict[str, object]:
        self.assert_valid()
        return {
            "branch": self.branch,
            "gitDevice": self.git_device,
            "gitInode": self.git_inode,
            "head": self.head,
            "excludesSha256": self.excludes_sha256,
            "indexSha256": self.index_sha256,
            "refsSha256": self.refs_sha256,
            "rootDevice": self.root_device,
            "rootInode": self.root_inode,
        }


@dataclass(frozen=True)
class CandidateEntryV1:
    path: str
    kind: str
    categories: tuple[str, ...]
    disposition: str
    sha256: str | None = None
    size: int | None = None
    executable: bool = False
    link_target: str | None = None
    unsupported_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "categories": list(self.categories),
            "disposition": self.disposition,
            "executable": self.executable,
            "kind": self.kind,
            "path": self.path,
        }
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        if self.size is not None:
            value["size"] = self.size
        if self.link_target is not None:
            value["linkTarget"] = self.link_target
        if self.unsupported_reason is not None:
            value["unsupportedReason"] = self.unsupported_reason
        return value


@dataclass(frozen=True)
class CandidateManifestV1:
    """A local-only, immutable review candidate for one physical worktree."""

    root: Path
    identity: WorkspaceIdentityV1
    entries: tuple[CandidateEntryV1, ...]
    candidate_sha256: str

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "kind": "lift-candidate-manifest",
            "schemaVersion": 1,
            "workspaceIdentity": self.identity.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        value = self.unsigned_dict()
        value["candidateSha256"] = self.candidate_sha256
        return value

    def assert_valid(self) -> None:
        if self.root != self.root.resolve(strict=True):
            raise WorkspacePolicyError("candidate root is no longer canonical")
        _validate_entry_collection_bounds(self.entries, label="candidate")
        paths = [entry.path for entry in self.entries]
        _validate_unique_ordered_paths(paths, label="candidate")
        for entry in self.entries:
            _validate_entry(entry)
        _validate_symlink_closure(
            {entry.path: entry for entry in self.entries},
            label="candidate",
        )
        self.identity.assert_valid()
        if canonical_sha256(self.unsigned_dict()) != self.candidate_sha256:
            raise WorkspacePolicyError("candidate manifest digest is invalid")


@dataclass(frozen=True)
class PathDecisionV1:
    path: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "path": self.path}


@dataclass(frozen=True)
class ApprovalScopeV1:
    """Nonsecret operation identity that prevents cross-run approval reuse."""

    run_id: str
    workspace_id: str
    helper_version: str

    def assert_valid(self) -> None:
        if (
            not isinstance(self.run_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.run_id) is None
        ):
            raise WorkspacePolicyError("approval run ID is invalid")
        if (
            not isinstance(self.workspace_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.workspace_id)
            is None
        ):
            raise WorkspacePolicyError("approval workspace ID is invalid")
        if (
            not isinstance(self.helper_version, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", self.helper_version)
            is None
        ):
            raise WorkspacePolicyError("approval helper version is invalid")

    def to_dict(self) -> dict[str, str]:
        self.assert_valid()
        return {
            "helperVersion": self.helper_version,
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
        }


@dataclass(frozen=True)
class ApprovalV1:
    """Local approval bound to one candidate and one decision for every path."""

    candidate_sha256: str
    scope: ApprovalScopeV1
    decisions: tuple[PathDecisionV1, ...]
    approval_sha256: str

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "candidateSha256": self.candidate_sha256,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "kind": "lift-workspace-approval",
            "schemaVersion": 1,
            "scope": self.scope.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        value = self.unsigned_dict()
        value["approvalSha256"] = self.approval_sha256
        return value


@dataclass(frozen=True)
class PolicyEntryV1:
    path: str
    kind: str
    categories: tuple[str, ...]
    sha256: str | None
    size: int | None
    executable: bool
    link_target: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "categories": list(self.categories),
            "executable": self.executable,
            "kind": self.kind,
            "path": self.path,
        }
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        if self.size is not None:
            value["size"] = self.size
        if self.link_target is not None:
            value["linkTarget"] = self.link_target
        return value


@dataclass(frozen=True)
class ReturnPolicyV1:
    """Policy for paths that appear or change while the cloud owns the workspace."""

    ruleset: str = "lift-return-v1"
    classifier_version: str = "workspace-policy-classifier-v1"
    existing_approved_paths: str = "allow"
    new_ordinary_paths: str = "allow"
    new_ignored_paths: str = "needs-review"
    new_sensitive_paths: str = "needs-review"
    hard_excluded_paths: str = "block"
    unsafe_links: str = "block"
    special_files: str = "block"

    def assert_valid(self) -> None:
        if self != ReturnPolicyV1():
            raise WorkspacePolicyError("return policy does not match the v1 ruleset")

    def to_dict(self) -> dict[str, str]:
        self.assert_valid()
        return {
            "classifierVersion": self.classifier_version,
            "existingApprovedPaths": self.existing_approved_paths,
            "hardExcludedPaths": self.hard_excluded_paths,
            "newIgnoredPaths": self.new_ignored_paths,
            "newOrdinaryPaths": self.new_ordinary_paths,
            "newSensitivePaths": self.new_sensitive_paths,
            "ruleset": self.ruleset,
            "specialFiles": self.special_files,
            "unsafeLinks": self.unsafe_links,
        }


@dataclass(frozen=True)
class EffectivePolicyV1:
    """Portable policy.  Excluded paths and their metadata are intentionally absent."""

    candidate_sha256: str
    approval_sha256: str
    workspace_identity_sha256: str
    scope: ApprovalScopeV1
    initial_transfer_entries: tuple[PolicyEntryV1, ...]
    return_policy: ReturnPolicyV1
    policy_sha256: str

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "approvalSha256": self.approval_sha256,
            "candidateSha256": self.candidate_sha256,
            "initialTransferEntries": [
                entry.to_dict() for entry in self.initial_transfer_entries
            ],
            "kind": "lift-effective-workspace-policy",
            "returnPolicy": self.return_policy.to_dict(),
            "schemaVersion": 1,
            "scope": self.scope.to_dict(),
            "workspaceIdentitySha256": self.workspace_identity_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        value = self.unsigned_dict()
        value["policySha256"] = self.policy_sha256
        return value

    def assert_valid(self) -> None:
        if (
            not _is_sha256(self.candidate_sha256)
            or not _is_sha256(self.approval_sha256)
            or not _is_sha256(self.workspace_identity_sha256)
        ):
            raise WorkspacePolicyError("effective policy binding digest is invalid")
        self.scope.assert_valid()
        self.return_policy.assert_valid()
        _validate_entry_collection_bounds(
            self.initial_transfer_entries,
            label="effective policy",
        )
        paths = [entry.path for entry in self.initial_transfer_entries]
        _validate_unique_ordered_paths(paths, label="effective policy")
        for entry in self.initial_transfer_entries:
            _validate_policy_entry(entry)
        _validate_symlink_closure(
            {entry.path: entry for entry in self.initial_transfer_entries},
            label="effective policy",
        )
        if canonical_sha256(self.unsigned_dict()) != self.policy_sha256:
            raise WorkspacePolicyError("effective policy digest is invalid")


@dataclass(frozen=True)
class ReturnPathDecisionV1:
    path: str
    action: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "path": self.path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReturnPlanV1:
    policy_sha256: str
    classifier_version: str
    role: str
    snapshot_sha256: str
    overall_disposition: str
    decisions: tuple[ReturnPathDecisionV1, ...]
    allowed_entries: tuple[PolicyEntryV1, ...]
    plan_sha256: str

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "classifierVersion": self.classifier_version,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "kind": "lift-return-plan",
            "overallDisposition": self.overall_disposition,
            "policySha256": self.policy_sha256,
            "role": self.role,
            "schemaVersion": 1,
            "selectedAllowedEntries": [
                entry.to_dict() for entry in self.allowed_entries
            ],
            "snapshotSha256": self.snapshot_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        value = self.unsigned_dict()
        value["planSha256"] = self.plan_sha256
        return value

    def assert_valid(self) -> None:
        """Validate structure and self-hash, not policy authorization semantics."""

        if not _is_sha256(self.policy_sha256) or not _is_sha256(self.snapshot_sha256):
            raise WorkspacePolicyError("return plan policy binding is invalid")
        if self.classifier_version != ReturnPolicyV1().classifier_version:
            raise WorkspacePolicyError("return plan classifier version is invalid")
        if self.role != "cloud-return":
            raise WorkspacePolicyError("return plan role is invalid")
        if len(self.decisions) > _MAX_WORKSPACE_ENTRIES:
            raise WorkspacePolicyError("return plan exceeds the v1 entry-count limit")
        _validate_entry_collection_bounds(self.allowed_entries, label="return plan")
        paths = [decision.path for decision in self.decisions]
        _validate_unique_ordered_paths(paths, label="return plan")
        for decision in self.decisions:
            _validate_relative_path(decision.path)
            if decision.action not in {"ALLOW", "BLOCK", "NEEDS_REVIEW"}:
                raise WorkspacePolicyError(
                    f"return action is invalid: {decision.path!r}"
                )
            if decision.reason not in {
                "approved-initial-path",
                "new-ordinary-path",
                "new-sensitive-or-ignored-path",
                "prohibited-or-unsupported-path",
                "unknown-tombstone",
            }:
                raise WorkspacePolicyError(
                    f"return reason is invalid: {decision.path!r}"
                )
        expected_overall = (
            "BLOCK"
            if any(decision.action == "BLOCK" for decision in self.decisions)
            else "NEEDS_REVIEW"
            if any(decision.action == "NEEDS_REVIEW" for decision in self.decisions)
            else "ALLOW"
        )
        if self.overall_disposition != expected_overall:
            raise WorkspacePolicyError("return plan overall disposition is invalid")
        allowed_paths = [entry.path for entry in self.allowed_entries]
        _validate_unique_ordered_paths(allowed_paths, label="selected return")
        for entry in self.allowed_entries:
            _validate_policy_entry(entry)
        _validate_symlink_closure(
            {entry.path: entry for entry in self.allowed_entries},
            label="selected return",
        )
        expected_allowed_paths = tuple(
            decision.path for decision in self.decisions if decision.action == "ALLOW"
        )
        if tuple(allowed_paths) != expected_allowed_paths:
            raise WorkspacePolicyError("return plan selected entries are invalid")
        if canonical_sha256(self.unsigned_dict()) != self.plan_sha256:
            raise WorkspacePolicyError("return plan digest is invalid")


@dataclass(frozen=True)
class _PhysicalEntry:
    kind: str
    sha256: str | None
    size: int | None
    executable: bool
    link_target: str | None = None
    unsupported_reason: str | None = None
    sensitive_content: bool = False
    git_blob_sha1: str | None = None


@dataclass(frozen=True)
class _RegularFileInspection:
    sha256: str
    size: int
    executable: bool
    private_key_material: bool
    sensitive_content: bool
    git_blob_sha1: str


_LinkEntry = CandidateEntryV1 | PolicyEntryV1 | _PhysicalEntry


def _required_symlink_targets(
    entries_by_path: Mapping[str, _LinkEntry],
    source_path: str,
) -> tuple[str, ...]:
    """Return the file/link chain required to reconstruct one symlink."""

    required: list[str] = []
    visited = {source_path}
    current_path = source_path
    while True:
        current = entries_by_path.get(current_path)
        if current is None or current.kind != "symlink" or current.link_target is None:
            raise WorkspacePolicyError(
                f"symlink target cannot be reconstructed: {source_path!r}"
            )
        normalized = _normalize_link_target(current_path, current.link_target)
        if normalized is None:
            raise WorkspacePolicyError(
                f"symlink target cannot be reconstructed: {source_path!r}"
            )
        target_path = normalized[1]
        if target_path in visited:
            raise WorkspacePolicyError(
                f"symlink target cycle cannot be reconstructed: {source_path!r}"
            )
        visited.add(target_path)
        target = entries_by_path.get(target_path)
        if (
            target is None
            or getattr(target, "unsupported_reason", None) is not None
            or getattr(target, "sensitive_content", False)
            or "sensitive" in getattr(target, "categories", ())
        ):
            raise WorkspacePolicyError(
                f"symlink target cannot be reconstructed: {source_path!r}"
            )
        required.append(target_path)
        if target.kind == "file":
            return tuple(required)
        if target.kind != "symlink":
            raise WorkspacePolicyError(
                f"symlink target cannot be reconstructed: {source_path!r}"
            )
        current_path = target_path


def _validate_symlink_closure(
    entries_by_path: Mapping[str, _LinkEntry],
    *,
    label: str,
) -> None:
    for path, entry in entries_by_path.items():
        if entry.kind != "symlink":
            continue
        try:
            _required_symlink_targets(entries_by_path, path)
        except WorkspacePolicyError as exc:
            raise WorkspacePolicyError(
                f"{label} symlink dependency is not closed: {path!r}"
            ) from exc


def _exclude_unreconstructable_physical_links(
    entries: dict[str, _PhysicalEntry],
) -> None:
    invalid: list[str] = []
    for path, entry in entries.items():
        if entry.kind != "symlink":
            continue
        try:
            _required_symlink_targets(entries, path)
        except WorkspacePolicyError:
            invalid.append(path)
    for path in invalid:
        entries[path] = _PhysicalEntry(
            kind="excluded",
            sha256=None,
            size=None,
            executable=False,
            unsupported_reason="unsafe-symbolic-link",
        )


def _validate_entry_collection_bounds(
    entries: tuple[CandidateEntryV1, ...] | tuple[PolicyEntryV1, ...],
    *,
    label: str,
) -> None:
    if len(entries) > _MAX_WORKSPACE_ENTRIES:
        raise WorkspacePolicyError(f"{label} exceeds the v1 entry-count limit")
    total_bytes = 0
    for entry in entries:
        if entry.size is None:
            continue
        if entry.kind == "file" and entry.size > _MAX_FILE_BYTES:
            raise WorkspacePolicyError(f"{label} exceeds the v1 per-file byte limit")
        total_bytes += entry.size
        if total_bytes > _MAX_TOTAL_BYTES:
            raise WorkspacePolicyError(f"{label} exceeds the v1 total-byte limit")


def _account_home_directory() -> Path:
    """Resolve the effective account's home without trusting ambient HOME."""

    try:
        raw_home = pwd.getpwuid(os.geteuid()).pw_dir
    except (KeyError, OSError) as exc:
        raise WorkspacePolicyError(
            "unable to determine the operating-system account home directory"
        ) from exc
    if (
        not isinstance(raw_home, str)
        or not raw_home
        or not Path(raw_home).is_absolute()
    ):
        raise WorkspacePolicyError(
            "unable to determine the operating-system account home directory"
        )
    try:
        home = Path(raw_home).resolve(strict=True)
    except OSError as exc:
        raise WorkspacePolicyError(
            "unable to resolve the operating-system account home directory"
        ) from exc
    if not home.is_dir():
        raise WorkspacePolicyError(
            "operating-system account home is not a physical directory"
        )
    return home


def _account_xdg_config_home() -> Path:
    """Resolve the effective XDG config root without accepting relative state."""

    raw_xdg = os.environ.get("XDG_CONFIG_HOME")
    if raw_xdg is None or raw_xdg == "":
        return _account_home_directory() / ".config"
    configured = Path(raw_xdg)
    if not configured.is_absolute():
        raise WorkspacePolicyError("XDG_CONFIG_HOME must be an absolute path")
    normalized = Path(os.path.normpath(configured))
    if normalized != configured:
        raise WorkspacePolicyError("XDG_CONFIG_HOME must be canonical")
    try:
        info = configured.lstat()
    except FileNotFoundError:
        return configured
    except OSError as exc:
        raise WorkspacePolicyError("XDG_CONFIG_HOME cannot be inspected") from exc
    try:
        resolved = configured.resolve(strict=True)
    except OSError as exc:
        raise WorkspacePolicyError("XDG_CONFIG_HOME cannot be resolved") from exc
    if (
        configured.is_symlink()
        or resolved != configured
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid not in {0, os.geteuid()}
    ):
        raise WorkspacePolicyError("XDG_CONFIG_HOME is not a trusted directory")
    return configured


def _trusted_git_executable() -> Path:
    """Return a root-owned system Git whose physical parent chain is immutable."""

    for candidate in _TRUSTED_GIT_CANDIDATES:
        try:
            resolved = candidate.resolve(strict=True)
            executable_info = resolved.stat()
        except OSError:
            continue
        if (
            not resolved.is_absolute()
            or not stat.S_ISREG(executable_info.st_mode)
            or executable_info.st_uid != 0
            or executable_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or not os.access(resolved, os.X_OK)
        ):
            continue
        trusted = True
        current = resolved.parent
        while True:
            try:
                parent_info = current.stat()
            except OSError:
                trusted = False
                break
            if (
                not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != 0
                or parent_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            ):
                trusted = False
                break
            if current == current.parent:
                break
            current = current.parent
        if trusted:
            return resolved
    raise WorkspacePolicyError("no trusted system Git executable is available")


def _git_environment(*, allow_standard_config: bool = False) -> dict[str, str]:
    home = _account_home_directory()
    xdg_config_home = _account_xdg_config_home()
    environment = {
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "XDG_CONFIG_HOME": str(xdg_config_home),
    }
    if not allow_standard_config:
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )
    return environment


def _git(
    root: Path,
    arguments: list[str],
    *,
    accepted_returncodes: tuple[int, ...] = (0,),
    extra_environment: Mapping[str, str] | None = None,
    allow_standard_config: bool = False,
    isolate_excludes_file: bool = True,
) -> tuple[int, bytes]:
    environment = _git_environment(allow_standard_config=allow_standard_config)
    if extra_environment is not None:
        environment.update(extra_environment)
    command = [
        str(_trusted_git_executable()),
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
    ]
    if isolate_excludes_file:
        command.extend(("-c", f"core.excludesFile={os.devnull}"))
    command.extend(arguments)
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspacePolicyError(
            f"unable to inspect the selected Git worktree ({arguments[0]})"
        ) from exc
    if completed.returncode not in accepted_returncodes:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise WorkspacePolicyError(
            f"unable to inspect the selected Git worktree ({arguments[0]}): {detail}"
        )
    return completed.returncode, completed.stdout


def _reject_external_git_filters(root: Path) -> None:
    code, configured = _git(
        root,
        [
            "config",
            "--includes",
            "--null",
            "--name-only",
            "--get-regexp",
            r"^filter\..*\.(clean|process|smudge)$",
        ],
        accepted_returncodes=(0, 1),
    )
    if code == 0 and configured:
        raise WorkspacePolicyError(
            "external Git filter drivers are unsupported during workspace discovery"
        )


def _reject_external_git_object_storage(root: Path, git_directory: Path) -> None:
    """Reject repositories whose objects could be fetched or read externally."""

    _, configured_raw = _git(
        root,
        ["config", "--includes", "--null", "--name-only", "--list"],
    )
    configured = {
        _decode_text(raw_name, label="Git configuration key").casefold()
        for raw_name in configured_raw.split(b"\0")
        if raw_name
    }
    unsafe_config = sorted(
        name
        for name in configured
        if name in {"core.alternaterefscommand", "extensions.partialclone"}
        or (
            name.startswith("remote.")
            and name.rsplit(".", 1)[-1] in {"partialclonefilter", "promisor"}
        )
    )
    if unsafe_config:
        raise WorkspacePolicyError(
            "partial-clone, promisor, and alternate Git object storage is unsupported"
        )

    git_fd = os.open(git_directory, _directory_open_flags())
    try:
        try:
            objects_info = os.stat("objects", dir_fd=git_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise WorkspacePolicyError("Git object directory is missing") from exc
        if not stat.S_ISDIR(objects_info.st_mode):
            raise WorkspacePolicyError("Git object directory must be physical")
        try:
            objects_fd = os.open(
                "objects",
                _directory_open_flags(),
                dir_fd=git_fd,
            )
        except OSError as exc:
            raise WorkspacePolicyError("Git object directory must be physical") from exc
        try:
            opened_objects = os.fstat(objects_fd)
            if (
                opened_objects.st_dev != objects_info.st_dev
                or opened_objects.st_ino != objects_info.st_ino
            ):
                raise WorkspacePolicyError(
                    "Git object directory changed while it was inspected"
                )
            for directory_name in ("info", "pack"):
                try:
                    directory_info = os.stat(
                        directory_name,
                        dir_fd=objects_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    continue
                if not stat.S_ISDIR(directory_info.st_mode):
                    raise WorkspacePolicyError(
                        "Git object storage contains a non-physical directory"
                    )
                try:
                    directory_fd = os.open(
                        directory_name,
                        _directory_open_flags(),
                        dir_fd=objects_fd,
                    )
                except OSError as exc:
                    raise WorkspacePolicyError(
                        "Git object storage contains a non-physical directory"
                    ) from exc
                try:
                    opened_directory = os.fstat(directory_fd)
                    if (
                        opened_directory.st_dev != directory_info.st_dev
                        or opened_directory.st_ino != directory_info.st_ino
                    ):
                        raise WorkspacePolicyError(
                            "Git object storage changed while it was inspected"
                        )
                    try:
                        names = {entry.name for entry in os.scandir(directory_fd)}
                    except OSError as exc:
                        raise WorkspacePolicyError(
                            "unable to inspect Git object storage"
                        ) from exc
                finally:
                    os.close(directory_fd)
                if directory_name == "info" and names.intersection(
                    {"alternates", "http-alternates"}
                ):
                    raise WorkspacePolicyError(
                        "alternate Git object storage is unsupported"
                    )
                if directory_name == "pack" and any(
                    name.endswith(".promisor") for name in names
                ):
                    raise WorkspacePolicyError(
                        "promisor Git object storage is unsupported"
                    )
        finally:
            os.close(objects_fd)
    finally:
        os.close(git_fd)


def _reject_split_git_index(root: Path) -> None:
    _, shared_index = _git(root, ["rev-parse", "--shared-index-path"])
    if shared_index.strip():
        raise WorkspacePolicyError("split Git indexes are unsupported")


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _has_nested_bare_repository_markers(directory_fd: int) -> bool:
    """Detect the canonical bare-repository layout from an anchored directory."""

    for name in ("HEAD", "config", "objects", "refs"):
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise WorkspacePolicyError(
                "unable to inspect a possible nested bare Git repository"
            ) from exc
    return True


def _raw_index_sha256(root: Path) -> str:
    git_fd = os.open(root / ".git", _directory_open_flags())
    try:
        try:
            info = os.stat("index", dir_fd=git_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise WorkspacePolicyError("Git index is missing") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise WorkspacePolicyError("Git index is not a physical regular file")
        return _hash_regular_file_at(
            git_fd,
            "index",
            info,
            max_bytes=_MAX_GIT_INDEX_BYTES,
        )
    finally:
        os.close(git_fd)


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise WorkspacePolicyError("unable to create a private Git index")
        offset += written


def _open_absolute_regular_without_links(path: Path) -> tuple[int, os.stat_result]:
    """Open an absolute regular file through an anchored no-follow component walk."""

    if (
        not path.is_absolute()
        or len(path.parts) < 2
        or any(component in {"", ".", ".."} for component in path.parts[1:])
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise WorkspacePolicyError(
            "configured Git excludes path is not safely openable"
        )
    directory_fd = os.open(os.sep, _directory_open_flags())
    try:
        for component in path.parts[1:-1]:
            try:
                next_fd = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                raise WorkspacePolicyError(
                    "configured Git excludes path traverses an unsafe directory"
                ) from exc
            os.close(directory_fd)
            directory_fd = next_fd
        name = path.parts[-1]
        try:
            expected = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise WorkspacePolicyError(
                "configured Git excludes file cannot be opened safely"
            ) from exc
        actual = os.fstat(descriptor)
        if (
            actual.st_dev != expected.st_dev
            or actual.st_ino != expected.st_ino
            or actual.st_mode != expected.st_mode
            or actual.st_size != expected.st_size
            or actual.st_mtime_ns != expected.st_mtime_ns
            or actual.st_ctime_ns != expected.st_ctime_ns
            or actual.st_nlink != expected.st_nlink
            or not stat.S_ISREG(actual.st_mode)
        ):
            os.close(descriptor)
            raise WorkspacePolicyError(
                "configured Git excludes file changed while it was opened"
            )
        return descriptor, actual
    finally:
        os.close(directory_fd)


def _descriptor_sha256(
    descriptor: int,
    expected: os.stat_result,
    *,
    label: str,
) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = expected.st_size
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            raise WorkspacePolicyError(f"{label} changed while it was read")
        digest.update(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise WorkspacePolicyError(f"{label} changed while it was read")
    after = os.fstat(descriptor)
    if (
        after.st_dev != expected.st_dev
        or after.st_ino != expected.st_ino
        or after.st_mode != expected.st_mode
        or after.st_size != expected.st_size
        or after.st_mtime_ns != expected.st_mtime_ns
        or after.st_ctime_ns != expected.st_ctime_ns
        or after.st_nlink != expected.st_nlink
    ):
        raise WorkspacePolicyError(f"{label} changed while it was read")
    return digest.hexdigest()


def _standard_exclude_source_paths(root: Path) -> tuple[Path, ...]:
    """Read effective core.excludesFile values with trusted account locations."""

    code, raw_paths = _git(
        root,
        [
            "config",
            "--includes",
            "--null",
            "--path",
            "--get-all",
            "core.excludesFile",
        ],
        accepted_returncodes=(0, 1),
        allow_standard_config=True,
        isolate_excludes_file=False,
    )
    if code == 1:
        default_path = _account_xdg_config_home() / "git" / "ignore"
        try:
            default_path.lstat()
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise WorkspacePolicyError(
                "default Git excludes file cannot be inspected"
            ) from exc
        return (default_path,)
    paths: list[Path] = []
    for raw_path in raw_paths.split(b"\0"):
        if not raw_path:
            continue
        configured = Path(_decode_text(raw_path, label="global Git excludes path"))
        if not configured.is_absolute():
            raise WorkspacePolicyError("configured Git excludes path must be absolute")
        paths.append(configured)
    return tuple(paths)


@contextmanager
def _private_standard_excludes(root: Path):
    """Copy configured excludes into bounded private files and bind their bytes."""

    configured_paths = _standard_exclude_source_paths(root)
    source_records: list[tuple[Path, int, os.stat_result, str]] = []
    private_paths: list[Path] = []
    source_identities: list[dict[str, object]] = []
    total_bytes = 0
    try:
        with tempfile.TemporaryDirectory(prefix="lift-private-excludes-") as directory:
            private_root = Path(directory)
            for index, configured in enumerate(configured_paths):
                source_fd, expected = _open_absolute_regular_without_links(configured)
                source_records.append((configured, source_fd, expected, ""))
                if (
                    not stat.S_ISREG(expected.st_mode)
                    or expected.st_nlink != 1
                    or expected.st_uid not in {0, os.geteuid()}
                    or expected.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                    or expected.st_size < 0
                ):
                    raise WorkspacePolicyError(
                        "configured Git excludes file is not a supported regular file"
                    )
                total_bytes += expected.st_size
                if total_bytes > _MAX_EXCLUDES_BYTES:
                    raise WorkspacePolicyError(
                        "configured Git excludes files exceed the byte limit"
                    )
                private_path = private_root / f"exclude-{index}"
                destination_fd = os.open(
                    private_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    os.lseek(source_fd, 0, os.SEEK_SET)
                    digest = hashlib.sha256()
                    remaining = expected.st_size
                    while remaining:
                        chunk = os.read(source_fd, min(1024 * 1024, remaining))
                        if not chunk:
                            raise WorkspacePolicyError(
                                "configured Git excludes file changed while it was copied"
                            )
                        digest.update(chunk)
                        _write_all(destination_fd, chunk)
                        remaining -= len(chunk)
                    if os.read(source_fd, 1):
                        raise WorkspacePolicyError(
                            "configured Git excludes file changed while it was copied"
                        )
                finally:
                    os.close(destination_fd)
                after_copy = os.fstat(source_fd)
                if (
                    after_copy.st_dev != expected.st_dev
                    or after_copy.st_ino != expected.st_ino
                    or after_copy.st_mode != expected.st_mode
                    or after_copy.st_size != expected.st_size
                    or after_copy.st_mtime_ns != expected.st_mtime_ns
                    or after_copy.st_ctime_ns != expected.st_ctime_ns
                    or after_copy.st_nlink != 1
                ):
                    raise WorkspacePolicyError(
                        "configured Git excludes file changed while it was copied"
                    )
                source_digest = digest.hexdigest()
                source_records[-1] = (
                    configured,
                    source_fd,
                    expected,
                    source_digest,
                )
                private_paths.append(private_path)
                source_identities.append(
                    {"sha256": source_digest, "size": expected.st_size}
                )

            excludes_sha256 = canonical_sha256({"sources": source_identities})
            yield tuple(private_paths), excludes_sha256

            if _standard_exclude_source_paths(root) != configured_paths:
                raise WorkspacePolicyError(
                    "configured Git excludes changed during workspace inspection"
                )
            for configured, source_fd, before, source_digest in source_records:
                after_use = os.fstat(source_fd)
                if (
                    after_use.st_dev != before.st_dev
                    or after_use.st_ino != before.st_ino
                    or after_use.st_mode != before.st_mode
                    or after_use.st_size != before.st_size
                    or after_use.st_mtime_ns != before.st_mtime_ns
                    or after_use.st_ctime_ns != before.st_ctime_ns
                    or after_use.st_nlink != 1
                ):
                    raise WorkspacePolicyError(
                        "configured Git excludes changed during workspace inspection"
                    )
                live_fd, live_info = _open_absolute_regular_without_links(configured)
                try:
                    if (
                        live_info.st_dev != before.st_dev
                        or live_info.st_ino != before.st_ino
                        or live_info.st_mode != before.st_mode
                        or live_info.st_size != before.st_size
                        or live_info.st_mtime_ns != before.st_mtime_ns
                        or live_info.st_ctime_ns != before.st_ctime_ns
                        or live_info.st_nlink != before.st_nlink
                        or _descriptor_sha256(
                            live_fd,
                            live_info,
                            label="configured Git excludes file",
                        )
                        != source_digest
                    ):
                        raise WorkspacePolicyError(
                            "configured Git excludes path changed during workspace inspection"
                        )
                finally:
                    os.close(live_fd)
    finally:
        for _configured, source_fd, _before, _digest in source_records:
            os.close(source_fd)


@contextmanager
def _private_index_copy(root: Path):
    """Yield a stable private index copy and the SHA-256 of its exact raw bytes."""

    git_fd = os.open(root / ".git", _directory_open_flags())
    try:
        try:
            expected = os.stat("index", dir_fd=git_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise WorkspacePolicyError("Git index is missing") from exc
        if (
            not stat.S_ISREG(expected.st_mode)
            or expected.st_nlink != 1
            or expected.st_size > _MAX_GIT_INDEX_BYTES
        ):
            raise WorkspacePolicyError("Git index is not a supported physical file")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        source_fd = os.open("index", flags, dir_fd=git_fd)
        try:
            before = os.fstat(source_fd)
            if (
                before.st_dev != expected.st_dev
                or before.st_ino != expected.st_ino
                or before.st_mode != expected.st_mode
                or before.st_size != expected.st_size
                or before.st_mtime_ns != expected.st_mtime_ns
                or before.st_ctime_ns != expected.st_ctime_ns
                or before.st_nlink != 1
            ):
                raise WorkspacePolicyError("Git index changed while it was copied")
            with tempfile.TemporaryDirectory(prefix="lift-private-index-") as directory:
                private_path = Path(directory) / "index"
                destination_fd = os.open(
                    private_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                digest = hashlib.sha256()
                try:
                    remaining = before.st_size
                    while remaining:
                        chunk = os.read(source_fd, min(1024 * 1024, remaining))
                        if not chunk:
                            raise WorkspacePolicyError(
                                "Git index changed while it was copied"
                            )
                        digest.update(chunk)
                        _write_all(destination_fd, chunk)
                        remaining -= len(chunk)
                    if os.read(source_fd, 1):
                        raise WorkspacePolicyError(
                            "Git index changed while it was copied"
                        )
                finally:
                    os.close(destination_fd)
                after = os.fstat(source_fd)
                if (
                    after.st_dev != before.st_dev
                    or after.st_ino != before.st_ino
                    or after.st_mode != before.st_mode
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or after.st_nlink != 1
                ):
                    raise WorkspacePolicyError("Git index changed while it was copied")
                copied_sha256 = digest.hexdigest()
                yield private_path, copied_sha256
                final = os.fstat(source_fd)
                if (
                    final.st_dev != before.st_dev
                    or final.st_ino != before.st_ino
                    or final.st_mode != before.st_mode
                    or final.st_size != before.st_size
                    or final.st_mtime_ns != before.st_mtime_ns
                    or final.st_ctime_ns != before.st_ctime_ns
                    or final.st_nlink != 1
                ):
                    raise WorkspacePolicyError(
                        "Git index changed during workspace inspection"
                    )
        finally:
            os.close(source_fd)
    finally:
        os.close(git_fd)


def _decode_text(value: bytes, *, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspacePolicyError(f"{label} is not valid UTF-8") from exc


def _nul_paths(value: bytes, *, label: str) -> set[str]:
    paths: set[str] = set()
    for raw in value.split(b"\0"):
        if not raw:
            continue
        path = _decode_text(raw, label=label)
        _validate_relative_path(path)
        paths.add(path)
    return paths


def _unescape_mountinfo_path(value: str) -> str:
    for encoded, decoded in (
        ("\\040", " "),
        ("\\011", "\t"),
        ("\\012", "\n"),
        ("\\134", "\\"),
    ):
        value = value.replace(encoded, decoded)
    return value


def _mount_table() -> tuple[tuple[str, str], ...]:
    """Return identifiable mount points and filesystem types without resolving paths."""

    mounts: list[tuple[str, str]] = []
    if sys.platform.startswith("linux"):
        try:
            lines = (
                Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise WorkspacePolicyError(
                "unable to inspect the host mount table"
            ) from exc
        for line in lines:
            left, separator, right = line.partition(" - ")
            left_parts = left.split(" ")
            right_parts = right.split(" ")
            if not separator or len(left_parts) < 5 or not right_parts:
                continue
            mount_point = os.path.normpath(_unescape_mountinfo_path(left_parts[4]))
            filesystem_type = right_parts[0].casefold()
            if os.path.isabs(mount_point) and filesystem_type:
                mounts.append((mount_point, filesystem_type))
        if not mounts:
            raise WorkspacePolicyError(
                "unable to inspect the host mount table: no parseable records"
            )
        return tuple(mounts)
    elif sys.platform == "darwin":
        mount_command = Path("/sbin/mount")
        if not mount_command.is_file():
            raise WorkspacePolicyError("unable to inspect the host mount table")
        try:
            completed = subprocess.run(
                [str(mount_command)],
                check=False,
                capture_output=True,
                env={"LC_ALL": "C", "PATH": os.defpath},
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspacePolicyError(
                "unable to inspect the host mount table"
            ) from exc
        if completed.returncode != 0:
            raise WorkspacePolicyError("unable to inspect the host mount table")
        try:
            lines = completed.stdout.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise WorkspacePolicyError(
                "unable to inspect the host mount table"
            ) from exc
        for line in lines:
            _source, separator, remainder = line.rpartition(" on ")
            mount_point, options_separator, options = remainder.rpartition(" (")
            if not separator or not options_separator or not options.endswith(")"):
                continue
            filesystem_type = options[:-1].split(",", 1)[0].strip().casefold()
            mount_point = os.path.normpath(_unescape_mountinfo_path(mount_point))
            if os.path.isabs(mount_point) and filesystem_type:
                mounts.append((mount_point, filesystem_type))
        if not mounts:
            raise WorkspacePolicyError(
                "unable to inspect the host mount table: no parseable records"
            )
        return tuple(mounts)
    raise WorkspacePolicyError(
        f"host platform does not support mount inspection: {sys.platform}"
    )


def _filesystem_type(root: Path) -> str:
    """Identify the filesystem containing root or fail closed."""

    root_text = str(root)
    selected: tuple[int, str] | None = None
    for mount_point, filesystem_type in _mount_table():
        if root_text != mount_point and not root_text.startswith(
            mount_point.rstrip("/") + "/"
        ):
            continue
        candidate = (len(mount_point), filesystem_type)
        if selected is None or candidate[0] > selected[0]:
            selected = candidate
    if selected is None:
        raise WorkspacePolicyError(
            "workspace root is not represented in the host mount table"
        )
    return selected[1]


def _identifiable_nested_mounts(root: Path) -> frozenset[str]:
    root_text = str(root)
    prefix = root_text.rstrip("/") + "/"
    nested: set[str] = set()
    mount_table = _mount_table()
    if not any(
        root_text == mount_point or root_text.startswith(mount_point.rstrip("/") + "/")
        for mount_point, _filesystem in mount_table
    ):
        raise WorkspacePolicyError(
            "workspace root is not represented in the host mount table"
        )
    for mount_point, _filesystem in mount_table:
        if not mount_point.startswith(prefix):
            continue
        relative = mount_point[len(prefix) :]
        try:
            _validate_relative_path(relative)
        except WorkspacePolicyError as exc:
            raise WorkspacePolicyError(
                "workspace contains an unsupported nested mount path"
            ) from exc
        nested.add(relative)
    return frozenset(nested)


def _reject_identifiable_network_filesystem(root: Path) -> None:
    filesystem_type = _filesystem_type(root)
    if filesystem_type in _NETWORK_FILESYSTEMS or any(
        filesystem_type.startswith(prefix)
        for prefix in ("fuse.sshfs", "nfs", "smb", "cifs", "ceph", "gluster")
    ):
        raise WorkspacePolicyError(
            "network filesystems are unsupported for workspace v1"
        )


def _content_classification(sample: bytes) -> tuple[bool, bool]:
    if any(marker in sample for marker in _PRIVATE_KEY_MARKERS):
        return True, True
    if _KNOWN_TOKEN_PATTERN.search(sample) is not None:
        return False, True
    for match in _CREDENTIAL_ASSIGNMENT_PATTERN.finditer(sample):
        value = match.group(1).strip().lower()
        if value not in _PLACEHOLDER_CREDENTIAL_VALUES:
            return False, True
    return False, False


def _inspect_regular_file_at(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
) -> _RegularFileInspection:
    if expected.st_size > _MAX_FILE_BYTES:
        raise WorkspacePolicyError("workspace file exceeds the v1 per-file byte limit")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if (
            before.st_dev != expected.st_dev
            or before.st_ino != expected.st_ino
            or not stat.S_ISREG(before.st_mode)
            or before.st_mode != expected.st_mode
            or before.st_size != expected.st_size
            or before.st_mtime_ns != expected.st_mtime_ns
            or before.st_ctime_ns != expected.st_ctime_ns
            or before.st_nlink != 1
        ):
            raise WorkspacePolicyError("workspace changed while a file was inspected")
        digest = hashlib.sha256()
        git_digest = _new_git_sha1()
        git_digest.update(f"blob {before.st_size}\0".encode("ascii"))
        scan_tail = b""
        private_key_material = False
        sensitive_content = False
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(_CONTENT_SCAN_BYTES, remaining))
            if not chunk:
                raise WorkspacePolicyError(
                    "workspace changed while a file was inspected"
                )
            digest.update(chunk)
            git_digest.update(chunk)
            remaining -= len(chunk)
            scan_window = scan_tail + chunk
            window_private_key, window_sensitive = _content_classification(scan_window)
            private_key_material = private_key_material or window_private_key
            sensitive_content = sensitive_content or window_sensitive
            scan_tail = scan_window[-_CONTENT_SCAN_OVERLAP:]
        if os.read(descriptor, 1):
            raise WorkspacePolicyError("workspace changed while a file was inspected")
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_mode != before.st_mode
            or after.st_size != before.st_size
            or after.st_nlink != 1
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise WorkspacePolicyError("workspace changed while a file was inspected")
        return _RegularFileInspection(
            sha256=digest.hexdigest(),
            size=before.st_size,
            executable=bool(before.st_mode & stat.S_IXUSR),
            private_key_material=private_key_material,
            sensitive_content=sensitive_content,
            git_blob_sha1=git_digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


def _hash_regular_file_at(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    *,
    max_bytes: int,
) -> str:
    if expected.st_size > max_bytes:
        raise WorkspacePolicyError("Git index exceeds the v1 byte limit")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if (
            before.st_dev != expected.st_dev
            or before.st_ino != expected.st_ino
            or not stat.S_ISREG(before.st_mode)
            or before.st_mode != expected.st_mode
            or before.st_size != expected.st_size
            or before.st_mtime_ns != expected.st_mtime_ns
            or before.st_ctime_ns != expected.st_ctime_ns
            or before.st_nlink != 1
        ):
            raise WorkspacePolicyError("Git index changed while it was inspected")
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise WorkspacePolicyError("Git index changed while it was inspected")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise WorkspacePolicyError("Git index changed while it was inspected")
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_mode != before.st_mode
            or after.st_size != before.st_size
            or after.st_nlink != 1
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise WorkspacePolicyError("Git index changed while it was inspected")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _hard_excluded_path(path: str) -> bool:
    components = tuple(component.casefold() for component in Path(path).parts)
    basename = components[-1]
    if any(component in _HARD_EXCLUDED_COMPONENTS for component in components):
        return True
    if basename in _HARD_EXCLUDED_BASENAMES:
        return True
    if basename.endswith(_HARD_EXCLUDED_SUFFIXES):
        return True
    cookie_store_names = (
        "cookies",
        "cookies.binarycookies",
        "cookies.sqlite",
        "cookies.sqlite3",
    )
    if any(
        basename == name
        or any(basename == f"{name}{sidecar}" for sidecar in _DATABASE_SIDECAR_SUFFIXES)
        for name in cookie_store_names
    ):
        return True
    if len(components) >= 2 and components[-2:] in {
        (".aws", "credentials"),
        (".codex", "auth.json"),
        (".docker", "config.json"),
        (".kube", "config"),
    }:
        return True
    return False


def _sensitive_path(path: str) -> bool:
    basename = Path(path).name.casefold()
    if basename == ".env" or basename.startswith(".env."):
        return True
    if basename in _SENSITIVE_BASENAMES or basename.endswith(_SENSITIVE_SUFFIXES):
        return True
    if basename.endswith(_DATABASE_SUFFIXES) or any(
        basename.endswith(f"{suffix}{sidecar}")
        for suffix in _DATABASE_SUFFIXES
        for sidecar in _DATABASE_SIDECAR_SUFFIXES
    ):
        return True
    return any(
        component.casefold() in {"credentials", "secret", "secrets"}
        for component in Path(path).parts[:-1]
    )


def _normalize_link_target(path: str, target: str) -> tuple[str, str] | None:
    try:
        encoded = target.encode("utf-8")
    except UnicodeEncodeError:
        return None
    target_path = PurePosixPath(target)
    if (
        not target
        or target_path.is_absolute()
        or "\x00" in target
        or any(ord(character) < 32 or ord(character) == 127 for character in target)
        or len(encoded) > _MAX_PATH_BYTES
        or len(target_path.parts) > _MAX_PATH_DEPTH
        or any(
            len(component.encode("utf-8")) > _MAX_COMPONENT_BYTES
            for component in target_path.parts
            if component not in {".", ".."}
        )
    ):
        return None
    normalized = posixpath.normpath(target)
    if normalized != target:
        return None
    lexical = posixpath.normpath(posixpath.join(posixpath.dirname(path), normalized))
    if lexical in {"", ".", ".."} or lexical.startswith("../"):
        return None
    try:
        _validate_relative_path(lexical)
    except WorkspacePolicyError:
        return None
    if _hard_excluded_path(lexical) or _sensitive_path(lexical):
        return None
    return normalized, lexical


def _safe_link_target(root: Path, path: str, target: str) -> str | None:
    normalized = _normalize_link_target(path, target)
    if normalized is None:
        return None
    normalized_target, _lexical = normalized
    try:
        resolved = (root / PurePosixPath(path).parent / normalized_target).resolve(
            strict=True
        )
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if resolved != root and root not in resolved.parents:
        return None
    if resolved == root:
        return None
    try:
        resolved_relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return None
    try:
        _validate_relative_path(resolved_relative)
    except WorkspacePolicyError:
        return None
    if _hard_excluded_path(resolved_relative) or _sensitive_path(resolved_relative):
        return None
    try:
        resolved_info = resolved.stat()
    except OSError:
        return None
    if not stat.S_ISREG(resolved_info.st_mode):
        return None
    return normalized_target


def _scan_physical_tree(
    root: Path,
    *,
    root_device: int,
    root_inode: int,
    nested_mounts: frozenset[str],
) -> dict[str, _PhysicalEntry]:
    entries: dict[str, _PhysicalEntry] = {}
    directory_flags = _directory_open_flags()
    entry_count = 0
    total_bytes = 0
    root_fd = os.open(root, directory_flags)
    try:
        opened_root = os.fstat(root_fd)
    except OSError as exc:
        os.close(root_fd)
        raise WorkspacePolicyError("unable to inspect the workspace root") from exc
    if (
        not stat.S_ISDIR(opened_root.st_mode)
        or opened_root.st_dev != root_device
        or opened_root.st_ino != root_inode
    ):
        os.close(root_fd)
        raise WorkspacePolicyError("workspace root changed while it was opened")

    def visit(directory_fd: int, prefix: tuple[str, ...]) -> None:
        nonlocal entry_count, total_bytes
        try:
            children = []
            with os.scandir(directory_fd) as iterator:
                for child in iterator:
                    if not prefix and child.name == ".git":
                        continue
                    if entry_count + len(children) >= _MAX_WORKSPACE_ENTRIES:
                        raise WorkspacePolicyError(
                            "workspace exceeds the v1 entry-count limit"
                        )
                    _validate_relative_path("/".join((*prefix, child.name)))
                    children.append(child)
        except OSError as exc:
            raise WorkspacePolicyError(
                "unable to inspect every workspace path"
            ) from exc
        children.sort(key=lambda child: child.name.encode("utf-8"))
        for child in children:
            path = "/".join((*prefix, child.name))
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise WorkspacePolicyError(
                    f"workspace changed while inspecting {path!r}"
                ) from exc

            if child.name == ".git":
                if not prefix:
                    continue
                raise WorkspacePolicyError(
                    f"nested Git repositories are not supported: {'/'.join(prefix)!r}"
                )

            entry_count += 1
            if entry_count > _MAX_WORKSPACE_ENTRIES:
                raise WorkspacePolicyError("workspace exceeds the v1 entry-count limit")

            if path in nested_mounts or info.st_dev != root_device:
                entries[path] = _PhysicalEntry(
                    kind="directory" if stat.S_ISDIR(info.st_mode) else "unsupported",
                    sha256=None,
                    size=None,
                    executable=False,
                    unsupported_reason="child-mount",
                )
                continue

            if _hard_excluded_path(path):
                entries[path] = _PhysicalEntry(
                    kind="directory" if stat.S_ISDIR(info.st_mode) else "excluded",
                    sha256=None,
                    size=None,
                    executable=False,
                    unsupported_reason="prohibited-private-state",
                )
                continue

            if stat.S_ISDIR(info.st_mode):
                try:
                    child_fd = os.open(child.name, directory_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise WorkspacePolicyError(
                        f"workspace changed while inspecting {path!r}"
                    ) from exc
                try:
                    opened = os.fstat(child_fd)
                    if opened.st_dev != info.st_dev or opened.st_ino != info.st_ino:
                        raise WorkspacePolicyError(
                            f"workspace changed while inspecting {path!r}"
                        )
                    if _has_nested_bare_repository_markers(child_fd):
                        raise WorkspacePolicyError(
                            f"nested bare Git repositories are not supported: {path!r}"
                        )
                    visit(child_fd, (*prefix, child.name))
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                if info.st_size > _MAX_FILE_BYTES:
                    raise WorkspacePolicyError(
                        f"workspace file exceeds the v1 per-file byte limit: {path!r}"
                    )
                total_bytes += info.st_size
                if total_bytes > _MAX_TOTAL_BYTES:
                    raise WorkspacePolicyError(
                        "workspace exceeds the v1 total-byte limit"
                    )
                if info.st_nlink != 1:
                    entries[path] = _PhysicalEntry(
                        kind="unsupported",
                        sha256=None,
                        size=None,
                        executable=False,
                        unsupported_reason="hard-linked-file",
                    )
                else:
                    inspection = _inspect_regular_file_at(
                        directory_fd, child.name, info
                    )
                    if inspection.private_key_material:
                        entries[path] = _PhysicalEntry(
                            kind="excluded",
                            sha256=None,
                            size=None,
                            executable=False,
                            unsupported_reason="private-key-material",
                            sensitive_content=True,
                        )
                    else:
                        entries[path] = _PhysicalEntry(
                            kind="file",
                            sha256=inspection.sha256,
                            size=inspection.size,
                            executable=inspection.executable,
                            sensitive_content=inspection.sensitive_content,
                            git_blob_sha1=inspection.git_blob_sha1,
                        )
            elif stat.S_ISLNK(info.st_mode):
                try:
                    target = os.readlink(child.name, dir_fd=directory_fd)
                except (OSError, UnicodeDecodeError) as exc:
                    raise WorkspacePolicyError(
                        f"unable to inspect symbolic link {path!r}"
                    ) from exc
                normalized_target = _safe_link_target(root, path, target)
                target_bytes = (
                    normalized_target.encode("utf-8")
                    if normalized_target is not None
                    else None
                )
                if target_bytes is not None:
                    total_bytes += len(target_bytes)
                    if total_bytes > _MAX_TOTAL_BYTES:
                        raise WorkspacePolicyError(
                            "workspace exceeds the v1 total-byte limit"
                        )
                entries[path] = _PhysicalEntry(
                    kind="symlink" if target_bytes is not None else "excluded",
                    sha256=_hash_bytes(target_bytes)
                    if target_bytes is not None
                    else None,
                    size=len(target_bytes) if target_bytes is not None else None,
                    executable=False,
                    link_target=normalized_target,
                    unsupported_reason=(
                        None if target_bytes is not None else "unsafe-symbolic-link"
                    ),
                    git_blob_sha1=(
                        _git_blob_sha1(target_bytes)
                        if target_bytes is not None
                        else None
                    ),
                )
            else:
                entries[path] = _PhysicalEntry(
                    kind="unsupported",
                    sha256=None,
                    size=None,
                    executable=False,
                    unsupported_reason="special-file",
                )

    try:
        visit(root_fd, ())
    finally:
        os.close(root_fd)
    _exclude_unreconstructable_physical_links(entries)
    return entries


def _resolved_home_directory() -> Path:
    return _account_home_directory()


def _reject_in_progress_git_operation(root: Path) -> None:
    git_fd = os.open(root / ".git", _directory_open_flags())
    try:
        try:
            names = {entry.name for entry in os.scandir(git_fd)}
        except OSError as exc:
            raise WorkspacePolicyError("unable to inspect Git operation state") from exc
    finally:
        os.close(git_fd)
    active = sorted(names.intersection(_IN_PROGRESS_GIT_NAMES))
    if active:
        raise WorkspacePolicyError(
            f"in-progress Git operations are unsupported: {active[0]}"
        )


def _validate_physical_worktree(
    workspace: Path,
) -> tuple[Path, os.stat_result, os.stat_result]:
    if not workspace.is_absolute():
        raise WorkspacePolicyError("selected workspace path must be absolute")
    requested = workspace.absolute()
    try:
        requested_info = requested.lstat()
    except FileNotFoundError as exc:
        raise WorkspacePolicyError("selected workspace does not exist") from exc
    if requested.is_symlink() or not stat.S_ISDIR(requested_info.st_mode):
        raise WorkspacePolicyError("selected workspace must be a physical directory")
    root = requested.resolve(strict=True)
    if root != requested:
        raise WorkspacePolicyError("selected workspace path traverses a symbolic link")
    account_home = _resolved_home_directory()
    if root == account_home:
        raise WorkspacePolicyError("select a project directory, not the home directory")
    try:
        account_relative = root.relative_to(account_home)
    except ValueError:
        account_relative = None
    if account_relative is not None and any(
        component.casefold() in _PROTECTED_ACCOUNT_COMPONENTS
        for component in account_relative.parts
    ):
        raise WorkspacePolicyError(
            "selected workspace is inside a protected account-private directory"
        )
    _reject_identifiable_network_filesystem(root)

    _, top_raw = _git(root, ["rev-parse", "--show-toplevel"])
    top = Path(_decode_text(top_raw, label="Git worktree root").strip()).resolve(
        strict=True
    )
    if top != root:
        raise WorkspacePolicyError("select exactly one Git worktree root")
    _, bare_raw = _git(root, ["rev-parse", "--is-bare-repository"])
    if bare_raw.strip() != b"false":
        raise WorkspacePolicyError("bare Git repositories are not supported")

    git_path = root / ".git"
    try:
        git_info = git_path.lstat()
    except FileNotFoundError as exc:
        raise WorkspacePolicyError("worktree has no physical .git directory") from exc
    if git_path.is_symlink() or not stat.S_ISDIR(git_info.st_mode):
        raise WorkspacePolicyError(
            "linked worktrees and redirected Git directories are unsupported"
        )
    if git_info.st_dev != requested_info.st_dev:
        raise WorkspacePolicyError("Git administration state is on a nested mount")
    _reject_in_progress_git_operation(root)
    _, git_dir_raw = _git(root, ["rev-parse", "--absolute-git-dir"])
    git_dir = Path(_decode_text(git_dir_raw, label="Git directory").strip()).resolve(
        strict=True
    )
    if git_dir != git_path.resolve(strict=True):
        raise WorkspacePolicyError(
            "Git administration state is outside the workspace root"
        )
    _, common_raw = _git(root, ["rev-parse", "--git-common-dir"])
    common = Path(_decode_text(common_raw, label="Git common directory").strip())
    if not common.is_absolute():
        common = root / common
    if common.resolve(strict=True) != git_dir:
        raise WorkspacePolicyError("linked Git worktrees are not supported")

    sparse_code, sparse_raw = _git(
        root,
        ["config", "--bool", "core.sparseCheckout"],
        accepted_returncodes=(0, 1),
    )
    if sparse_code == 0 and sparse_raw.strip() == b"true":
        raise WorkspacePolicyError("sparse Git worktrees are not supported")
    _reject_external_git_object_storage(root, git_dir)
    return root, requested_info, git_info


def _git_path_sets(
    root: Path,
    *,
    private_index: Path,
    private_excludes: tuple[Path, ...],
    physical: Mapping[str, _PhysicalEntry],
) -> tuple[set[str], set[str], set[str], set[str]]:
    _reject_external_git_filters(root)
    index_environment = {"GIT_INDEX_FILE": str(private_index)}
    _, stage_raw = _git(
        root,
        ["ls-files", "--stage", "-z"],
        extra_environment=index_environment,
    )
    index_entries: dict[str, tuple[str, str]] = {}
    for raw_record in stage_raw.split(b"\0"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        parts = metadata.split(b" ")
        if not separator or len(parts) != 3:
            raise WorkspacePolicyError("Git index returned malformed path metadata")
        mode_raw, object_id_raw, stage = parts
        path = _decode_text(raw_path, label="Git index path")
        _validate_relative_path(path)
        if mode_raw == b"160000":
            raise WorkspacePolicyError(f"Git submodules are not supported: {path!r}")
        if mode_raw == b"040000":
            raise WorkspacePolicyError("sparse Git index entries are not supported")
        if mode_raw not in {b"100644", b"100755", b"120000"}:
            raise WorkspacePolicyError(f"unsupported Git index mode for path: {path!r}")
        if stage != b"0":
            raise WorkspacePolicyError(
                f"unmerged Git index entries are unsupported: {path!r}"
            )
        object_id = _decode_text(object_id_raw, label="Git index object ID")
        if not _is_git_sha1(object_id) or set(object_id) == {"0"}:
            raise WorkspacePolicyError(
                f"Git intent-to-add or invalid index entries are unsupported: {path!r}"
            )
        if path in index_entries:
            raise WorkspacePolicyError(
                f"duplicate Git index path is unsupported: {path!r}"
            )
        index_entries[path] = (mode_raw.decode("ascii"), object_id)

    _, head_raw = _git(root, ["ls-tree", "-r", "--full-tree", "-z", "HEAD"])
    head_entries: dict[str, tuple[str, str]] = {}
    for raw_record in head_raw.split(b"\0"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        parts = metadata.split(b" ")
        if not separator or len(parts) != 3:
            raise WorkspacePolicyError("Git HEAD returned malformed tree metadata")
        mode_raw, object_type, object_id_raw = parts
        path = _decode_text(raw_path, label="Git HEAD path")
        _validate_relative_path(path)
        if mode_raw == b"160000" or object_type == b"commit":
            raise WorkspacePolicyError(f"Git submodules are not supported: {path!r}")
        if mode_raw not in {b"100644", b"100755", b"120000"} or object_type != b"blob":
            raise WorkspacePolicyError(f"unsupported Git HEAD entry: {path!r}")
        object_id = _decode_text(object_id_raw, label="Git HEAD object ID")
        if not _is_git_sha1(object_id):
            raise WorkspacePolicyError(f"Git HEAD object ID is invalid: {path!r}")
        if path in head_entries:
            raise WorkspacePolicyError(
                f"duplicate Git HEAD path is unsupported: {path!r}"
            )
        head_entries[path] = (mode_raw.decode("ascii"), object_id)

    tracked = set(index_entries).union(head_entries)

    _, flags_raw = _git(
        root,
        ["ls-files", "-v", "-z"],
        extra_environment=index_environment,
    )
    for raw_record in flags_raw.split(b"\0"):
        if not raw_record:
            continue
        flag, separator, raw_path = raw_record.partition(b" ")
        if not separator or len(flag) != 1:
            raise WorkspacePolicyError("Git index returned malformed path flags")
        path = _decode_text(raw_path, label="Git index path")
        _validate_relative_path(path)
        marker = flag.decode("ascii", errors="strict")
        if marker == "S" or marker.islower():
            raise WorkspacePolicyError(
                f"skip-worktree and assume-unchanged paths are unsupported: {path!r}"
            )

    staged = {
        path for path in tracked if index_entries.get(path) != head_entries.get(path)
    }
    # Deliberately compare raw bytes and modes, without Git's content-conversion
    # machinery. Built-in checkout transforms such as CRLF normalization may
    # therefore be reported as dirty; that conservative false positive avoids
    # executing repository-configured conversion drivers during discovery.
    dirty: set[str] = set()
    for path in tracked:
        index_entry = index_entries.get(path)
        physical_entry = physical.get(path)
        if index_entry is None:
            if physical_entry is not None:
                dirty.add(path)
            continue
        mode, object_id = index_entry
        expected_kind = "symlink" if mode == "120000" else "file"
        expected_executable = mode == "100755"
        if (
            physical_entry is None
            or physical_entry.kind != expected_kind
            or physical_entry.git_blob_sha1 != object_id
            or physical_entry.executable != expected_executable
        ):
            dirty.add(path)

    exclude_arguments = [
        f"--exclude-from={exclude_path}" for exclude_path in private_excludes
    ]
    _, ignored_raw = _git(
        root,
        [
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            *exclude_arguments,
            "-z",
        ],
        extra_environment=index_environment,
    )
    _, ignored_tracked_raw = _git(
        root,
        [
            "ls-files",
            "--cached",
            "--ignored",
            "--exclude-standard",
            *exclude_arguments,
            "-z",
        ],
        extra_environment=index_environment,
    )
    ignored = _nul_paths(ignored_raw, label="ignored Git path").union(
        _nul_paths(ignored_tracked_raw, label="ignored tracked Git path")
    )
    return (
        tracked,
        staged,
        dirty,
        ignored,
    )


def _workspace_identity(
    root: Path,
    root_info: os.stat_result,
    git_info: os.stat_result,
    *,
    excludes_sha256: str,
) -> WorkspaceIdentityV1:
    head_code, head_raw = _git(
        root,
        ["rev-parse", "--verify", "HEAD^{commit}"],
        accepted_returncodes=(0, 128),
    )
    if head_code != 0:
        raise WorkspacePolicyError("unborn Git worktrees are not supported")
    head = _decode_text(head_raw, label="Git HEAD").strip()
    if len(head) != 40 or any(
        character not in "0123456789abcdef" for character in head
    ):
        raise WorkspacePolicyError("Git HEAD is not a SHA-1 commit")
    branch_code, branch_raw = _git(
        root,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        accepted_returncodes=(0, 1),
    )
    if branch_code != 0:
        raise WorkspacePolicyError("detached Git worktrees are not supported")
    branch = _decode_text(branch_raw, label="Git branch").strip()
    index_sha256 = _raw_index_sha256(root)
    _, refs_raw = _git(
        root,
        ["for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)"],
    )
    return WorkspaceIdentityV1(
        root_device=root_info.st_dev,
        root_inode=root_info.st_ino,
        git_device=git_info.st_dev,
        git_inode=git_info.st_ino,
        head=head,
        branch=branch,
        index_sha256=index_sha256,
        refs_sha256=_hash_bytes(refs_raw),
        excludes_sha256=excludes_sha256,
    )


def _validate_entry(entry: CandidateEntryV1) -> None:
    _validate_relative_path(entry.path)
    if entry.kind not in {
        "absent",
        "directory",
        "excluded",
        "file",
        "symlink",
        "unsupported",
    }:
        raise WorkspacePolicyError(f"candidate entry kind is invalid: {entry.path!r}")
    if entry.categories != _categories(*entry.categories):
        raise WorkspacePolicyError(
            f"candidate categories are not canonical: {entry.path!r}"
        )
    if entry.disposition != _disposition(entry.categories):
        raise WorkspacePolicyError(f"candidate disposition is invalid: {entry.path!r}")
    category_set = set(entry.categories)
    if _hard_excluded_path(entry.path) and "hard-excluded" not in category_set:
        raise WorkspacePolicyError(
            f"prohibited path is not hard-excluded: {entry.path!r}"
        )
    if _sensitive_path(entry.path) and "sensitive" not in category_set:
        raise WorkspacePolicyError(
            f"sensitive path lacks classification: {entry.path!r}"
        )
    if "tracked" in category_set and "untracked" in category_set:
        raise WorkspacePolicyError(f"candidate Git categories conflict: {entry.path!r}")
    if "ignored" in category_set and "untracked" in category_set:
        raise WorkspacePolicyError(f"candidate Git categories conflict: {entry.path!r}")
    if category_set.intersection({"staged", "dirty"}) and "tracked" not in category_set:
        raise WorkspacePolicyError(
            f"candidate change lacks tracked identity: {entry.path!r}"
        )
    if "unsupported" in category_set and "hard-excluded" not in category_set:
        raise WorkspacePolicyError(
            f"unsupported candidate is not excluded: {entry.path!r}"
        )
    excluded = "hard-excluded" in category_set or "unsupported" in category_set
    if excluded and any(
        value is not None for value in (entry.sha256, entry.size, entry.link_target)
    ):
        raise WorkspacePolicyError(
            f"excluded entry contains portable metadata: {entry.path!r}"
        )
    if not excluded and entry.kind in {"file", "symlink"}:
        if (
            not _is_sha256(entry.sha256)
            or not isinstance(entry.size, int)
            or entry.size < 0
        ):
            raise WorkspacePolicyError(
                f"candidate entry has no content identity: {entry.path!r}"
            )
    if not isinstance(entry.executable, bool) or (
        entry.kind != "file" and entry.executable
    ):
        raise WorkspacePolicyError(
            f"candidate executable mode is invalid: {entry.path!r}"
        )
    if entry.kind == "symlink":
        normalized_link = (
            None
            if entry.link_target is None
            else _normalize_link_target(entry.path, entry.link_target)
        )
        if normalized_link is None or normalized_link[0] != entry.link_target:
            raise WorkspacePolicyError(
                f"candidate symbolic link has an unsafe target: {entry.path!r}"
            )
        target_bytes = entry.link_target.encode("utf-8")
        if entry.sha256 != _hash_bytes(target_bytes) or entry.size != len(target_bytes):
            raise WorkspacePolicyError(
                f"candidate symbolic link identity is invalid: {entry.path!r}"
            )
    elif entry.link_target is not None:
        raise WorkspacePolicyError(
            f"non-link candidate has a link target: {entry.path!r}"
        )
    if entry.kind == "absent" and not excluded:
        if "tracked" not in category_set or not category_set.intersection(
            {"staged", "dirty"}
        ):
            raise WorkspacePolicyError(
                f"candidate tombstone is not a tracked change: {entry.path!r}"
            )
        if entry.sha256 is not None or entry.size is not None or entry.executable:
            raise WorkspacePolicyError(
                f"candidate tombstone contains file metadata: {entry.path!r}"
            )
    if not excluded and entry.kind not in {"absent", "file", "symlink"}:
        raise WorkspacePolicyError(
            f"unsupported candidate entry is transferable: {entry.path!r}"
        )
    if excluded and entry.unsupported_reason is None:
        raise WorkspacePolicyError(
            f"excluded candidate has no local reason: {entry.path!r}"
        )
    if not excluded and entry.unsupported_reason is not None:
        raise WorkspacePolicyError(
            f"transferable candidate has an exclusion reason: {entry.path!r}"
        )


def _validate_policy_entry(entry: PolicyEntryV1) -> None:
    _validate_relative_path(entry.path)
    if entry.kind not in {"absent", "file", "symlink"}:
        raise WorkspacePolicyError(
            f"effective policy entry kind is invalid: {entry.path!r}"
        )
    if entry.categories != _categories(*entry.categories):
        raise WorkspacePolicyError(
            f"effective policy categories are not canonical: {entry.path!r}"
        )
    category_set = set(entry.categories)
    if _hard_excluded_path(entry.path):
        raise WorkspacePolicyError(f"prohibited path entered policy: {entry.path!r}")
    if _sensitive_path(entry.path) and "sensitive" not in category_set:
        raise WorkspacePolicyError(
            f"sensitive policy path lacks classification: {entry.path!r}"
        )
    if category_set.intersection({"hard-excluded", "unsupported"}):
        raise WorkspacePolicyError(
            f"excluded classifications entered policy: {entry.path!r}"
        )
    if "tracked" in category_set and "untracked" in category_set:
        raise WorkspacePolicyError(
            f"effective policy Git categories conflict: {entry.path!r}"
        )
    if "ignored" in category_set and "untracked" in category_set:
        raise WorkspacePolicyError(
            f"effective policy Git categories conflict: {entry.path!r}"
        )
    if category_set.intersection({"staged", "dirty"}) and "tracked" not in category_set:
        raise WorkspacePolicyError(
            f"effective policy change lacks tracked identity: {entry.path!r}"
        )
    if not isinstance(entry.executable, bool) or (
        entry.kind != "file" and entry.executable
    ):
        raise WorkspacePolicyError(f"effective policy mode is invalid: {entry.path!r}")
    if entry.kind in {"file", "symlink"}:
        if (
            not _is_sha256(entry.sha256)
            or not isinstance(entry.size, int)
            or entry.size < 0
        ):
            raise WorkspacePolicyError(
                f"effective policy content identity is invalid: {entry.path!r}"
            )
    else:
        if (
            entry.sha256 is not None
            or entry.size is not None
            or "tracked" not in category_set
            or not category_set.intersection({"staged", "dirty"})
        ):
            raise WorkspacePolicyError(
                f"effective policy tombstone is invalid: {entry.path!r}"
            )
    if entry.kind == "symlink":
        normalized_link = (
            None
            if entry.link_target is None
            else _normalize_link_target(entry.path, entry.link_target)
        )
        if normalized_link is None or normalized_link[0] != entry.link_target:
            raise WorkspacePolicyError(
                f"effective policy link target is invalid: {entry.path!r}"
            )
        target_bytes = entry.link_target.encode("utf-8")
        if entry.sha256 != _hash_bytes(target_bytes) or entry.size != len(target_bytes):
            raise WorkspacePolicyError(
                f"effective policy link identity is invalid: {entry.path!r}"
            )
    elif entry.link_target is not None:
        raise WorkspacePolicyError(
            f"non-link policy entry has a link target: {entry.path!r}"
        )


def _policy_entry(entry: CandidateEntryV1) -> PolicyEntryV1:
    if "hard-excluded" in entry.categories or "unsupported" in entry.categories:
        raise WorkspacePolicyError(
            f"excluded path entered the effective policy: {entry.path!r}"
        )
    result = PolicyEntryV1(
        path=entry.path,
        kind=entry.kind,
        categories=entry.categories,
        sha256=entry.sha256,
        size=entry.size,
        executable=entry.executable,
        link_target=entry.link_target,
    )
    _validate_policy_entry(result)
    return result


def discover_workspace(workspace: Path) -> CandidateManifestV1:
    """Inspect one physical Git worktree without uploading or mutating it."""

    root, root_info, git_info = _validate_physical_worktree(workspace)
    _reject_external_git_filters(root)
    _reject_split_git_index(root)
    nested_mounts_before = _identifiable_nested_mounts(root)
    if any(path == ".git" or path.startswith(".git/") for path in nested_mounts_before):
        raise WorkspacePolicyError("Git administration state is on a nested mount")
    if nested_mounts_before:
        raise WorkspacePolicyError(
            "nested workspace mount points are unsupported: "
            f"{sorted(nested_mounts_before)[0]!r}"
        )
    with _private_standard_excludes(root) as (
        private_excludes,
        excludes_sha256,
    ):
        identity_before = _workspace_identity(
            root,
            root_info,
            git_info,
            excludes_sha256=excludes_sha256,
        )
        with _private_index_copy(root) as (private_index, copied_index_sha256):
            if identity_before.index_sha256 != copied_index_sha256:
                raise WorkspacePolicyError(
                    "Git index changed before workspace inspection"
                )
            physical = _scan_physical_tree(
                root,
                root_device=root_info.st_dev,
                root_inode=root_info.st_ino,
                nested_mounts=nested_mounts_before,
            )
            tracked, staged, dirty, ignored = _git_path_sets(
                root,
                private_index=private_index,
                private_excludes=private_excludes,
                physical=physical,
            )

    all_paths = set(physical).union(tracked, staged, dirty, ignored)
    if len(all_paths) > _MAX_WORKSPACE_ENTRIES:
        raise WorkspacePolicyError("workspace exceeds the v1 entry-count limit")
    folded: dict[str, str] = {}
    for path in _sorted_paths(all_paths):
        portable_key = unicodedata.normalize("NFC", path).casefold()
        previous = folded.setdefault(portable_key, path)
        if previous != path:
            raise WorkspacePolicyError(
                f"normalization-colliding workspace paths are unsupported: {previous!r}, {path!r}"
            )

    blocked_prefixes = {
        path: item.unsupported_reason
        for path, item in physical.items()
        if item.kind == "directory" and item.unsupported_reason is not None
    }

    candidates: list[CandidateEntryV1] = []
    for path in _sorted_paths(all_paths):
        physical_entry = physical.get(path)
        matching_prefix = next(
            (
                prefix
                for prefix in blocked_prefixes
                if path == prefix or path.startswith(prefix + "/")
            ),
            None,
        )
        content_hard_excluded = (
            physical_entry is not None
            and physical_entry.unsupported_reason == "private-key-material"
        )
        is_hard_excluded = (
            _hard_excluded_path(path)
            or matching_prefix is not None
            or content_hard_excluded
        )
        is_unsupported = (
            physical_entry is not None
            and physical_entry.unsupported_reason is not None
            and physical_entry.unsupported_reason
            not in {"private-key-material", "prohibited-private-state"}
        )
        category_values: list[str] = []
        if path in tracked:
            category_values.append("tracked")
        if path in staged:
            category_values.append("staged")
        if path in dirty:
            category_values.append("dirty")
        if path not in tracked and path not in ignored:
            category_values.append("untracked")
        if path in ignored:
            category_values.append("ignored")
        if (
            _sensitive_path(path)
            or is_hard_excluded
            or (physical_entry is not None and physical_entry.sensitive_content)
        ):
            category_values.append("sensitive")
        if is_hard_excluded or is_unsupported:
            category_values.append("hard-excluded")
        if is_unsupported:
            category_values.append("unsupported")
        categories = _categories(*category_values)
        excluded = "hard-excluded" in categories

        if physical_entry is None:
            kind = "excluded" if excluded else "absent"
            sha256 = None
            size = None
            executable = False
            link_target = None
            unsupported_reason = (
                blocked_prefixes[matching_prefix]
                if matching_prefix is not None
                else "prohibited-private-state"
                if excluded
                else None
            )
        else:
            kind = physical_entry.kind
            sha256 = None if excluded else physical_entry.sha256
            size = None if excluded else physical_entry.size
            executable = False if excluded else physical_entry.executable
            link_target = None if excluded else physical_entry.link_target
            unsupported_reason = physical_entry.unsupported_reason
        candidates.append(
            CandidateEntryV1(
                path=path,
                kind=kind,
                categories=categories,
                disposition=_disposition(categories),
                sha256=sha256,
                size=size,
                executable=executable,
                link_target=link_target,
                unsupported_reason=unsupported_reason,
            )
        )

    entries = tuple(sorted(candidates, key=lambda entry: entry.path.encode("utf-8")))
    root_after, root_info_after, git_info_after = _validate_physical_worktree(root)
    if root_after != root:
        raise WorkspacePolicyError("workspace root changed while it was inspected")
    identity_after = _workspace_identity(
        root,
        root_info_after,
        git_info_after,
        excludes_sha256=excludes_sha256,
    )
    if identity_after != identity_before:
        raise WorkspacePolicyError(
            "Git state changed while the workspace was inspected"
        )
    if _identifiable_nested_mounts(root) != nested_mounts_before:
        raise WorkspacePolicyError(
            "workspace mount topology changed while it was inspected"
        )
    _reject_external_git_filters(root)
    _reject_external_git_object_storage(root, root / ".git")
    unsigned = {
        "entries": [entry.to_dict() for entry in entries],
        "kind": "lift-candidate-manifest",
        "schemaVersion": 1,
        "workspaceIdentity": identity_after.to_dict(),
    }
    candidate = CandidateManifestV1(
        root=root,
        identity=identity_after,
        entries=entries,
        candidate_sha256=canonical_sha256(unsigned),
    )
    candidate.assert_valid()
    return candidate


def recommended_decisions(candidate: CandidateManifestV1) -> dict[str, str]:
    """Return conservative UI defaults; review-only entries remain excluded."""

    candidate.assert_valid()
    decisions = {
        entry.path: "include" if entry.disposition == "will-move" else "exclude"
        for entry in candidate.entries
    }
    by_path = {entry.path: entry for entry in candidate.entries}
    for entry in candidate.entries:
        if entry.kind == "symlink" and any(
            decisions[target] != "include"
            for target in _required_symlink_targets(by_path, entry.path)
        ):
            decisions[entry.path] = "exclude"
    return decisions


def approve_candidate(
    candidate: CandidateManifestV1,
    decisions: Mapping[str, str],
    *,
    scope: ApprovalScopeV1,
) -> ApprovalV1:
    """Bind one explicit include/exclude decision to every candidate path."""

    candidate.assert_valid()
    scope.assert_valid()
    expected = {entry.path for entry in candidate.entries}
    actual = set(decisions)
    if actual != expected:
        missing = len(expected.difference(actual))
        extra = len(actual.difference(expected))
        raise WorkspacePolicyError(
            f"approval must decide every candidate path exactly once (missing={missing}, extra={extra})"
        )
    by_path = {entry.path: entry for entry in candidate.entries}
    approved: list[PathDecisionV1] = []
    for path in _sorted_paths(decisions):
        action = decisions[path]
        if action not in DECISIONS:
            raise WorkspacePolicyError(f"invalid approval decision for {path!r}")
        entry = by_path[path]
        if action == "include" and entry.disposition == "stays-local":
            raise WorkspacePolicyError(
                f"hard-excluded path cannot be approved: {path!r}"
            )
        approved.append(PathDecisionV1(path=path, action=action))
    unsigned = {
        "candidateSha256": candidate.candidate_sha256,
        "decisions": [decision.to_dict() for decision in approved],
        "kind": "lift-workspace-approval",
        "schemaVersion": 1,
        "scope": scope.to_dict(),
    }
    return ApprovalV1(
        candidate_sha256=candidate.candidate_sha256,
        scope=scope,
        decisions=tuple(approved),
        approval_sha256=canonical_sha256(unsigned),
    )


def _validate_approval(candidate: CandidateManifestV1, approval: ApprovalV1) -> None:
    candidate.assert_valid()
    approval.scope.assert_valid()
    if approval.candidate_sha256 != candidate.candidate_sha256:
        raise WorkspacePolicyError(
            "approval belongs to a different workspace candidate"
        )
    if canonical_sha256(approval.unsigned_dict()) != approval.approval_sha256:
        raise WorkspacePolicyError("approval digest is invalid")
    paths = [decision.path for decision in approval.decisions]
    _validate_unique_ordered_paths(paths, label="approval")
    if set(paths) != {entry.path for entry in candidate.entries}:
        raise WorkspacePolicyError(
            "approval does not decide the exact candidate path set"
        )
    by_path = {entry.path: entry for entry in candidate.entries}
    for decision in approval.decisions:
        if decision.action not in DECISIONS:
            raise WorkspacePolicyError(f"approval action is invalid: {decision.path!r}")
        if (
            decision.action == "include"
            and by_path[decision.path].disposition == "stays-local"
        ):
            raise WorkspacePolicyError(
                f"approval attempts to override a hard exclusion: {decision.path!r}"
            )


def compile_effective_policy(
    candidate: CandidateManifestV1,
    approval: ApprovalV1,
) -> EffectivePolicyV1:
    """Compile approved paths into the only policy allowed to leave the Mac."""

    _validate_approval(candidate, approval)
    entries_by_path = {entry.path: entry for entry in candidate.entries}
    portable: list[PolicyEntryV1] = []
    for decision in approval.decisions:
        if decision.action != "include":
            continue
        entry = entries_by_path[decision.path]
        portable.append(_policy_entry(entry))
    entries = tuple(sorted(portable, key=lambda entry: entry.path.encode("utf-8")))
    unsigned = {
        "approvalSha256": approval.approval_sha256,
        "candidateSha256": candidate.candidate_sha256,
        "initialTransferEntries": [entry.to_dict() for entry in entries],
        "kind": "lift-effective-workspace-policy",
        "returnPolicy": ReturnPolicyV1().to_dict(),
        "schemaVersion": 1,
        "scope": approval.scope.to_dict(),
        "workspaceIdentitySha256": canonical_sha256(candidate.identity.to_dict()),
    }
    policy = EffectivePolicyV1(
        candidate_sha256=candidate.candidate_sha256,
        approval_sha256=approval.approval_sha256,
        workspace_identity_sha256=canonical_sha256(candidate.identity.to_dict()),
        scope=approval.scope,
        initial_transfer_entries=entries,
        return_policy=ReturnPolicyV1(),
        policy_sha256=canonical_sha256(unsigned),
    )
    policy.assert_valid()
    return policy


def validate_candidate_unchanged(
    candidate: CandidateManifestV1,
    workspace: Path | None = None,
) -> CandidateManifestV1:
    """Rescan immediately before capture and reject any candidate drift."""

    candidate.assert_valid()
    current = discover_workspace(candidate.root if workspace is None else workspace)
    if (
        current.root != candidate.root
        or current.candidate_sha256 != candidate.candidate_sha256
    ):
        raise WorkspacePolicyError("workspace changed after manifest approval")
    return current


def validate_effective_policy(
    candidate: CandidateManifestV1,
    approval: ApprovalV1,
    policy: EffectivePolicyV1,
) -> None:
    """Verify all bindings and byte-for-byte deterministic policy compilation."""

    expected = compile_effective_policy(candidate, approval)
    policy.assert_valid()
    if policy != expected:
        raise WorkspacePolicyError(
            "effective policy does not match its candidate approval"
        )


def _require_exact_keys(
    value: object, keys: set[str], *, label: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise WorkspacePolicyError(f"{label} schema is invalid")
    return value


def effective_policy_from_dict(value: object) -> EffectivePolicyV1:
    """Strictly decode an untrusted portable policy and verify its self-hash."""

    raw = _require_exact_keys(
        value,
        {
            "approvalSha256",
            "candidateSha256",
            "initialTransferEntries",
            "kind",
            "policySha256",
            "returnPolicy",
            "schemaVersion",
            "scope",
            "workspaceIdentitySha256",
        },
        label="effective policy",
    )
    if type(raw["schemaVersion"]) is not int or raw["schemaVersion"] != 1:
        raise WorkspacePolicyError("effective policy version is invalid")
    if raw["kind"] != "lift-effective-workspace-policy":
        raise WorkspacePolicyError("effective policy kind is invalid")

    raw_scope = _require_exact_keys(
        raw["scope"],
        {"helperVersion", "runId", "workspaceId"},
        label="approval scope",
    )
    scope = ApprovalScopeV1(
        run_id=raw_scope["runId"],
        workspace_id=raw_scope["workspaceId"],
        helper_version=raw_scope["helperVersion"],
    )
    scope.assert_valid()

    raw_return = _require_exact_keys(
        raw["returnPolicy"],
        {
            "classifierVersion",
            "existingApprovedPaths",
            "hardExcludedPaths",
            "newIgnoredPaths",
            "newOrdinaryPaths",
            "newSensitivePaths",
            "ruleset",
            "specialFiles",
            "unsafeLinks",
        },
        label="return policy",
    )
    return_policy = ReturnPolicyV1(
        ruleset=raw_return["ruleset"],
        classifier_version=raw_return["classifierVersion"],
        existing_approved_paths=raw_return["existingApprovedPaths"],
        new_ordinary_paths=raw_return["newOrdinaryPaths"],
        new_ignored_paths=raw_return["newIgnoredPaths"],
        new_sensitive_paths=raw_return["newSensitivePaths"],
        hard_excluded_paths=raw_return["hardExcludedPaths"],
        unsafe_links=raw_return["unsafeLinks"],
        special_files=raw_return["specialFiles"],
    )
    return_policy.assert_valid()

    raw_entries = raw["initialTransferEntries"]
    if not isinstance(raw_entries, list) or len(raw_entries) > _MAX_WORKSPACE_ENTRIES:
        raise WorkspacePolicyError("initial transfer entries are invalid")
    entries: list[PolicyEntryV1] = []
    required_keys = {"categories", "executable", "kind", "path"}
    optional_keys = {"linkTarget", "sha256", "size"}
    for raw_entry_value in raw_entries:
        if not isinstance(raw_entry_value, dict):
            raise WorkspacePolicyError("initial transfer entry schema is invalid")
        raw_entry = raw_entry_value
        if not required_keys.issubset(raw_entry) or set(raw_entry).difference(
            required_keys | optional_keys
        ):
            raise WorkspacePolicyError("initial transfer entry schema is invalid")
        categories = raw_entry["categories"]
        if not isinstance(categories, list) or any(
            not isinstance(category, str) for category in categories
        ):
            raise WorkspacePolicyError("initial transfer entry categories are invalid")
        if not isinstance(raw_entry["path"], str) or not isinstance(
            raw_entry["kind"], str
        ):
            raise WorkspacePolicyError("initial transfer entry identity is invalid")
        if not isinstance(raw_entry["executable"], bool):
            raise WorkspacePolicyError("initial transfer entry mode is invalid")
        size = raw_entry.get("size")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
            raise WorkspacePolicyError("initial transfer entry size is invalid")
        sha256 = raw_entry.get("sha256")
        link_target = raw_entry.get("linkTarget")
        if sha256 is not None and not isinstance(sha256, str):
            raise WorkspacePolicyError("initial transfer entry digest is invalid")
        if link_target is not None and not isinstance(link_target, str):
            raise WorkspacePolicyError("initial transfer link target is invalid")
        parsed = PolicyEntryV1(
            path=raw_entry["path"],
            kind=raw_entry["kind"],
            categories=tuple(categories),
            sha256=sha256,
            size=size,
            executable=raw_entry["executable"],
            link_target=link_target,
        )
        _validate_policy_entry(parsed)
        if raw_entry != parsed.to_dict():
            raise WorkspacePolicyError("initial transfer entry schema is noncanonical")
        entries.append(parsed)

    for field in (
        "approvalSha256",
        "candidateSha256",
        "policySha256",
        "workspaceIdentitySha256",
    ):
        if not isinstance(raw[field], str):
            raise WorkspacePolicyError(f"effective policy {field} is invalid")
    policy = EffectivePolicyV1(
        candidate_sha256=raw["candidateSha256"],
        approval_sha256=raw["approvalSha256"],
        workspace_identity_sha256=raw["workspaceIdentitySha256"],
        scope=scope,
        initial_transfer_entries=tuple(entries),
        return_policy=return_policy,
        policy_sha256=raw["policySha256"],
    )
    policy.assert_valid()
    return policy


def validate_policy_dict(value: object) -> None:
    """Validate an untrusted policy payload without retaining it."""

    effective_policy_from_dict(value)


def classify_return_snapshot(
    policy: EffectivePolicyV1,
    snapshot: CandidateManifestV1,
) -> ReturnPlanV1:
    """Classify an in-process, scanner-produced cloud-return candidate.

    Approved initial paths may change or be deleted.  New ordinary paths may
    return automatically, while new ignored or sensitive paths require review
    and prohibited/unsupported objects block Land.  The candidate self-digest
    checks internal consistency; it does not authenticate capture provenance or
    prove completeness.  Do not pass an untrusted cloud artifact here until the
    capture integration authenticates both properties.
    """

    policy.assert_valid()
    if not isinstance(snapshot, CandidateManifestV1):
        raise WorkspacePolicyError("cloud return requires a CandidateManifestV1")
    snapshot.assert_valid()
    initial_paths = {entry.path for entry in policy.initial_transfer_entries}
    decisions: list[ReturnPathDecisionV1] = []
    for entry in snapshot.entries:
        categories = set(entry.categories)
        if _hard_excluded_path(entry.path) or categories.intersection(
            {"hard-excluded", "unsupported"}
        ):
            action = "BLOCK"
            reason = "prohibited-or-unsupported-path"
        elif entry.kind == "absent" and entry.path not in initial_paths:
            action = "BLOCK"
            reason = "unknown-tombstone"
        elif entry.path in initial_paths:
            action = "ALLOW"
            reason = "approved-initial-path"
        elif (
            "ignored" in categories
            or "sensitive" in categories
            or _sensitive_path(entry.path)
        ):
            action = "NEEDS_REVIEW"
            reason = "new-sensitive-or-ignored-path"
        else:
            action = "ALLOW"
            reason = "new-ordinary-path"
        decisions.append(
            ReturnPathDecisionV1(path=entry.path, action=action, reason=reason)
        )
    entries_by_path = {entry.path: entry for entry in snapshot.entries}
    decisions_by_path = {decision.path: decision for decision in decisions}
    dependency_closed: list[ReturnPathDecisionV1] = []
    for decision in decisions:
        entry = entries_by_path[decision.path]
        if decision.action != "ALLOW" or entry.kind != "symlink":
            dependency_closed.append(decision)
            continue
        dependency_actions = {
            decisions_by_path[target].action
            for target in _required_symlink_targets(entries_by_path, entry.path)
        }
        if "BLOCK" in dependency_actions:
            decision = ReturnPathDecisionV1(
                path=decision.path,
                action="BLOCK",
                reason="prohibited-or-unsupported-path",
            )
        elif "NEEDS_REVIEW" in dependency_actions:
            decision = ReturnPathDecisionV1(
                path=decision.path,
                action="NEEDS_REVIEW",
                reason="new-sensitive-or-ignored-path",
            )
        dependency_closed.append(decision)
    decisions = dependency_closed
    snapshot_sha256 = snapshot.candidate_sha256
    overall_disposition = (
        "BLOCK"
        if any(decision.action == "BLOCK" for decision in decisions)
        else "NEEDS_REVIEW"
        if any(decision.action == "NEEDS_REVIEW" for decision in decisions)
        else "ALLOW"
    )
    allowed_entries = tuple(
        _policy_entry(entries_by_path[decision.path])
        for decision in decisions
        if decision.action == "ALLOW"
    )
    unsigned = {
        "classifierVersion": policy.return_policy.classifier_version,
        "decisions": [decision.to_dict() for decision in decisions],
        "kind": "lift-return-plan",
        "overallDisposition": overall_disposition,
        "policySha256": policy.policy_sha256,
        "role": "cloud-return",
        "schemaVersion": 1,
        "selectedAllowedEntries": [entry.to_dict() for entry in allowed_entries],
        "snapshotSha256": snapshot_sha256,
    }
    plan = ReturnPlanV1(
        policy_sha256=policy.policy_sha256,
        classifier_version=policy.return_policy.classifier_version,
        role="cloud-return",
        snapshot_sha256=snapshot_sha256,
        overall_disposition=overall_disposition,
        decisions=tuple(decisions),
        allowed_entries=allowed_entries,
        plan_sha256=canonical_sha256(unsigned),
    )
    plan.assert_valid()
    return plan


def validate_return_plan(
    policy: EffectivePolicyV1,
    snapshot: CandidateManifestV1,
    plan: ReturnPlanV1,
) -> None:
    """Reclassify a trusted scanner snapshot; a plan self-hash is not authority."""

    plan.assert_valid()
    expected = classify_return_snapshot(policy, snapshot)
    if plan != expected:
        raise WorkspacePolicyError("return plan does not match its policy and snapshot")
