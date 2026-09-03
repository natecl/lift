from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPIKE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPIKE_ROOT))

import workspace_policy as policy_module  # noqa: E402
from workspace_policy import (  # noqa: E402
    ApprovalScopeV1,
    CandidateEntryV1,
    CandidateManifestV1,
    PolicyEntryV1,
    ReturnPathDecisionV1,
    ReturnPolicyV1,
    WorkspacePolicyError,
    approve_candidate,
    canonical_sha256,
    classify_return_snapshot,
    compile_effective_policy,
    discover_workspace,
    effective_policy_from_dict,
    recommended_decisions,
    validate_candidate_unchanged,
    validate_effective_policy,
    validate_policy_dict,
    validate_return_plan,
)


def git(*arguments: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def entry(candidate, path: str):
    return next(item for item in candidate.entries if item.path == path)


def return_file(path: str, categories: tuple[str, ...]) -> CandidateEntryV1:
    if "hard-excluded" in categories or "unsupported" in categories:
        disposition = "stays-local"
        return CandidateEntryV1(
            path=path,
            kind="excluded",
            categories=categories,
            disposition=disposition,
            unsupported_reason="prohibited-private-state",
        )
    disposition = (
        "needs-approval"
        if "ignored" in categories or "sensitive" in categories
        else "will-move"
    )
    content = f"return:{path}".encode()
    return CandidateEntryV1(
        path=path,
        kind="file",
        categories=categories,
        disposition=disposition,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


def return_manifest(
    candidate: CandidateManifestV1,
    entries: tuple[CandidateEntryV1, ...],
) -> CandidateManifestV1:
    ordered = tuple(sorted(entries, key=lambda item: item.path.encode("utf-8")))
    unsigned = {
        "entries": [item.to_dict() for item in ordered],
        "kind": "lift-candidate-manifest",
        "schemaVersion": 1,
        "workspaceIdentity": candidate.identity.to_dict(),
    }
    return CandidateManifestV1(
        root=candidate.root,
        identity=candidate.identity,
        entries=ordered,
        candidate_sha256=canonical_sha256(unsigned),
    )


class RealWorkspacePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lift-policy-test-")
        self.root = Path(self.temporary.name).resolve()
        self.account_home = self.root / "account-home"
        self.account_home.mkdir()
        self.account_home_patch = mock.patch(
            "workspace_policy._account_home_directory",
            return_value=self.account_home,
        )
        self.account_home_patch.start()
        self.environment_patch = mock.patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.account_home / ".config")},
            clear=False,
        )
        self.environment_patch.start()
        self.workspace = self.root / "workspace"
        self.scope = ApprovalScopeV1(
            run_id="run-policy-test",
            workspace_id="workspace-policy-test",
            helper_version="0.1.0-test",
        )
        self.workspace.mkdir()
        git("init", "--initial-branch=main", cwd=self.workspace)
        git("config", "user.name", "Lift Policy Test", cwd=self.workspace)
        git("config", "user.email", "policy@lift.invalid", cwd=self.workspace)
        (self.workspace / ".gitignore").write_text(
            "ignored/\n.env.local\n",
            encoding="utf-8",
        )
        (self.workspace / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        (self.workspace / "staged.txt").write_text("base\n", encoding="utf-8")
        (self.workspace / "dirty.txt").write_text("base\n", encoding="utf-8")
        (self.workspace / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        (self.workspace / ".env.example").write_text(
            "TOKEN=placeholder\n",
            encoding="utf-8",
        )
        git("add", ".", cwd=self.workspace)
        git("commit", "-m", "base", cwd=self.workspace)

        (self.workspace / "staged.txt").write_text("staged\n", encoding="utf-8")
        git("add", "staged.txt", cwd=self.workspace)
        (self.workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        (self.workspace / "deleted.txt").unlink()
        (self.workspace / "untracked.txt").write_text("new\n", encoding="utf-8")
        (self.workspace / "ignored").mkdir()
        (self.workspace / "ignored" / "cache.txt").write_text(
            "ignored bytes\n",
            encoding="utf-8",
        )
        (self.workspace / ".env.local").write_text(
            "TOKEN=real-secret\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.environment_patch.stop()
        self.account_home_patch.stop()
        self.temporary.cleanup()

    def approve(self, candidate, decisions):
        return approve_candidate(candidate, decisions, scope=self.scope)

    def test_discovery_classifies_real_git_and_filesystem_state(self) -> None:
        candidate = discover_workspace(self.workspace)

        self.assertNotIn(".git", {item.path for item in candidate.entries})
        self.assertEqual(("tracked",), entry(candidate, "tracked.txt").categories)
        self.assertEqual(
            ("tracked", "staged"),
            entry(candidate, "staged.txt").categories,
        )
        self.assertEqual(
            ("tracked", "dirty"),
            entry(candidate, "dirty.txt").categories,
        )
        self.assertEqual("absent", entry(candidate, "deleted.txt").kind)
        self.assertEqual(
            ("tracked", "dirty"),
            entry(candidate, "deleted.txt").categories,
        )
        self.assertEqual(("untracked",), entry(candidate, "untracked.txt").categories)
        self.assertEqual(
            ("ignored",),
            entry(candidate, "ignored/cache.txt").categories,
        )
        self.assertEqual(
            ("ignored", "sensitive"),
            entry(candidate, ".env.local").categories,
        )
        self.assertEqual(
            ("tracked", "sensitive"),
            entry(candidate, ".env.example").categories,
        )
        self.assertEqual("will-move", entry(candidate, "untracked.txt").disposition)
        self.assertEqual("needs-approval", entry(candidate, ".env.local").disposition)
        self.assertEqual(
            candidate.candidate_sha256,
            discover_workspace(self.workspace).candidate_sha256,
        )

    def test_discovery_does_not_change_user_git_state(self) -> None:
        index_path = Path(
            git("rev-parse", "--git-path", "index", cwd=self.workspace).strip()
        )
        if not index_path.is_absolute():
            index_path = self.workspace / index_path
        before = {
            "head": git("rev-parse", "HEAD", cwd=self.workspace),
            "index": index_path.read_bytes(),
            "refs": git(
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                cwd=self.workspace,
            ),
            "status": git(
                "status",
                "--porcelain=v2",
                "--untracked-files=all",
                "--ignored=matching",
                cwd=self.workspace,
            ),
        }

        discover_workspace(self.workspace)

        self.assertEqual(before["head"], git("rev-parse", "HEAD", cwd=self.workspace))
        self.assertEqual(before["index"], index_path.read_bytes())
        self.assertEqual(
            before["refs"],
            git(
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                cwd=self.workspace,
            ),
        )
        self.assertEqual(
            before["status"],
            git(
                "status",
                "--porcelain=v2",
                "--untracked-files=all",
                "--ignored=matching",
                cwd=self.workspace,
            ),
        )

    def test_external_git_filter_is_rejected_before_it_can_execute(self) -> None:
        marker = self.root / "filter-executed"
        (self.workspace / ".gitattributes").write_text(
            "*.txt filter=spy\n",
            encoding="utf-8",
        )
        git("add", ".gitattributes", cwd=self.workspace)
        git(
            "config",
            "filter.spy.clean",
            f"touch {marker}",
            cwd=self.workspace,
        )

        with self.assertRaisesRegex(WorkspacePolicyError, "filter drivers"):
            discover_workspace(self.workspace)

        self.assertFalse(marker.exists())

    def test_external_git_filter_from_local_include_is_rejected(self) -> None:
        marker = self.root / "included-filter-executed"
        included = self.root / "included.gitconfig"
        included.write_text(
            f'[filter "included"]\n\tclean = touch {marker}\n',
            encoding="utf-8",
        )
        git("config", "include.path", str(included), cwd=self.workspace)

        with self.assertRaisesRegex(WorkspacePolicyError, "filter drivers"):
            discover_workspace(self.workspace)

        self.assertFalse(marker.exists())

    def test_transient_filter_race_cannot_execute_and_fails_closed(self) -> None:
        marker = self.root / "transient-filter-executed"
        (self.workspace / ".gitattributes").write_text(
            "*.txt filter=transient\n",
            encoding="utf-8",
        )
        git("add", ".gitattributes", cwd=self.workspace)
        original_git = policy_module._git
        injected = False

        def inject_after_index_read(root, arguments, **kwargs):
            nonlocal injected
            result = original_git(root, arguments, **kwargs)
            if arguments == ["ls-files", "--stage", "-z"] and not injected:
                git(
                    "config",
                    "filter.transient.clean",
                    f"touch {marker}",
                    cwd=self.workspace,
                )
                injected = True
            return result

        with mock.patch("workspace_policy._git", side_effect=inject_after_index_read):
            with self.assertRaisesRegex(WorkspacePolicyError, "filter drivers"):
                discover_workspace(self.workspace)

        self.assertTrue(injected)
        self.assertFalse(marker.exists())

    def test_discovery_does_not_use_git_diff_for_worktree_state(self) -> None:
        original_git = policy_module._git
        commands: list[tuple[str, ...]] = []

        def record_command(root, arguments, **kwargs):
            commands.append(tuple(arguments))
            return original_git(root, arguments, **kwargs)

        with mock.patch("workspace_policy._git", side_effect=record_command):
            discover_workspace(self.workspace)

        self.assertFalse(any(command[:1] == ("diff",) for command in commands))

    def test_raw_checkout_transformation_is_conservatively_dirty(self) -> None:
        (self.workspace / ".gitattributes").write_text(
            "crlf.txt text eol=crlf\n",
            encoding="utf-8",
        )
        (self.workspace / "crlf.txt").write_bytes(b"line\n")
        git("add", ".gitattributes", "crlf.txt", cwd=self.workspace)
        # This is the worktree representation Git produces for eol=crlf while
        # the index blob remains canonical LF bytes.
        (self.workspace / "crlf.txt").write_bytes(b"line\r\n")
        self.assertEqual(b"line\r\n", (self.workspace / "crlf.txt").read_bytes())

        candidate = discover_workspace(self.workspace)

        self.assertIn("dirty", entry(candidate, "crlf.txt").categories)

    def test_every_git_subprocess_disables_lazy_fetch(self) -> None:
        original_run = subprocess.run
        git_environments: list[dict[str, str]] = []

        def observe_environment(arguments, **kwargs):
            if arguments and Path(arguments[0]).name == "git":
                git_environments.append(kwargs["env"])
            return original_run(arguments, **kwargs)

        with mock.patch(
            "workspace_policy.subprocess.run",
            side_effect=observe_environment,
        ):
            discover_workspace(self.workspace)

        self.assertTrue(git_environments)
        self.assertTrue(
            all(
                environment.get("GIT_NO_LAZY_FETCH") == "1"
                for environment in git_environments
            )
        )

    def test_git_execution_ignores_ambient_path_and_loader_injection(self) -> None:
        project_bin = self.workspace / "project-bin"
        project_bin.mkdir()
        fake_git = project_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n: > repository-fake-git-ran\nexit 99\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        marker = self.workspace / "repository-fake-git-ran"

        with mock.patch.dict(
            os.environ,
            {
                "DYLD_INSERT_LIBRARIES": str(self.workspace / "attack.dylib"),
                "LD_PRELOAD": str(self.workspace / "attack.so"),
                "PATH": str(project_bin),
            },
            clear=False,
        ):
            discover_workspace(self.workspace)

        self.assertFalse(marker.exists())

    def test_missing_partial_clone_tree_is_rejected_before_object_access(self) -> None:
        tree = git("rev-parse", "HEAD^{tree}", cwd=self.workspace).strip()
        tree_object = self.workspace / ".git" / "objects" / tree[:2] / tree[2:]
        self.assertTrue(tree_object.is_file())
        tree_object.unlink()
        git("config", "remote.origin.promisor", "true", cwd=self.workspace)
        git(
            "config",
            "remote.origin.partialCloneFilter",
            "blob:none",
            cwd=self.workspace,
        )
        original_git = policy_module._git
        commands: list[tuple[str, ...]] = []

        def record_command(root, arguments, **kwargs):
            commands.append(tuple(arguments))
            return original_git(root, arguments, **kwargs)

        with mock.patch("workspace_policy._git", side_effect=record_command):
            with self.assertRaisesRegex(
                WorkspacePolicyError,
                "partial-clone|promisor",
            ):
                discover_workspace(self.workspace)

        self.assertFalse(
            any(
                command[:1] == ("ls-tree",) or "HEAD^{commit}" in command
                for command in commands
            )
        )

    def test_promisor_pack_and_object_alternates_are_rejected(self) -> None:
        promisor = self.workspace / ".git" / "objects" / "pack" / "fake.promisor"
        promisor.write_bytes(b"")
        with self.assertRaisesRegex(WorkspacePolicyError, "promisor Git"):
            discover_workspace(self.workspace)
        promisor.unlink()

        alternates = self.workspace / ".git" / "objects" / "info" / "alternates"
        alternates.write_text(str(self.root / "elsewhere"), encoding="utf-8")
        with self.assertRaisesRegex(WorkspacePolicyError, "alternate Git"):
            discover_workspace(self.workspace)

    def test_index_identity_hashes_raw_bytes_and_detects_format_only_drift(
        self,
    ) -> None:
        index_path = self.workspace / ".git" / "index"
        git("update-index", "--index-version=2", cwd=self.workspace)
        raw_v2 = index_path.read_bytes()
        candidate_v2 = discover_workspace(self.workspace)
        self.assertEqual(
            hashlib.sha256(raw_v2).hexdigest(),
            candidate_v2.identity.index_sha256,
        )
        self.assertEqual(raw_v2, index_path.read_bytes())

        git("update-index", "--index-version=4", cwd=self.workspace)
        raw_v4 = index_path.read_bytes()
        self.assertNotEqual(raw_v2, raw_v4)
        with self.assertRaisesRegex(WorkspacePolicyError, "changed after manifest"):
            validate_candidate_unchanged(candidate_v2)
        candidate_v4 = discover_workspace(self.workspace)
        self.assertEqual(
            hashlib.sha256(raw_v4).hexdigest(),
            candidate_v4.identity.index_sha256,
        )
        self.assertNotEqual(
            candidate_v2.identity.index_sha256,
            candidate_v4.identity.index_sha256,
        )
        self.assertNotEqual(
            candidate_v2.candidate_sha256, candidate_v4.candidate_sha256
        )

    def test_split_git_index_is_rejected(self) -> None:
        git("update-index", "--split-index", cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "split Git indexes"):
            discover_workspace(self.workspace)

    def test_approval_requires_an_exact_decision_for_every_path(self) -> None:
        candidate = discover_workspace(self.workspace)
        decisions = recommended_decisions(candidate)
        decisions.pop("tracked.txt")
        with self.assertRaisesRegex(WorkspacePolicyError, "every candidate path"):
            self.approve(candidate, decisions)

        decisions = recommended_decisions(candidate)
        decisions["not-in-candidate"] = "exclude"
        with self.assertRaisesRegex(WorkspacePolicyError, "every candidate path"):
            self.approve(candidate, decisions)

    def test_sensitive_and_ignored_paths_need_path_level_inclusion(self) -> None:
        candidate = discover_workspace(self.workspace)
        defaults = recommended_decisions(candidate)
        default_approval = self.approve(candidate, defaults)
        default_policy = compile_effective_policy(candidate, default_approval)
        default_paths = {item.path for item in default_policy.initial_transfer_entries}
        self.assertNotIn(".env.example", default_paths)
        self.assertNotIn(".env.local", default_paths)
        self.assertNotIn("ignored/cache.txt", default_paths)

        explicit = recommended_decisions(candidate)
        explicit[".env.example"] = "include"
        explicit["ignored/cache.txt"] = "include"
        approval = self.approve(candidate, explicit)
        policy = compile_effective_policy(candidate, approval)
        policy_paths = {item.path for item in policy.initial_transfer_entries}
        self.assertIn(".env.example", policy_paths)
        self.assertIn("ignored/cache.txt", policy_paths)
        self.assertNotIn(".env.local", policy_paths)
        validate_effective_policy(candidate, approval, policy)

    def test_account_global_ignore_file_is_copied_bound_and_applied(self) -> None:
        excludes = self.account_home / "global-ignore"
        excludes.write_text("global-only.secret\n", encoding="utf-8")
        (self.account_home / ".gitconfig").write_text(
            f"[core]\n\texcludesFile = {excludes}\n",
            encoding="utf-8",
        )
        (self.workspace / "global-only.secret").write_bytes(b"opaque bytes")

        candidate = discover_workspace(self.workspace)
        ignored = entry(candidate, "global-only.secret")

        self.assertIn("ignored", ignored.categories)
        self.assertNotIn("untracked", ignored.categories)
        self.assertEqual("needs-approval", ignored.disposition)
        self.assertEqual(
            "exclude",
            recommended_decisions(candidate)["global-only.secret"],
        )
        before = candidate.identity.excludes_sha256

        excludes.write_text("different-global-only.secret\n", encoding="utf-8")
        after = discover_workspace(self.workspace).identity.excludes_sha256
        self.assertNotEqual(before, after)

    def test_default_xdg_global_ignore_file_is_copied_bound_and_applied(self) -> None:
        excludes = self.account_home / ".config" / "git" / "ignore"
        excludes.parent.mkdir(parents=True)
        excludes.write_text("default-global.secret\n", encoding="utf-8")
        (self.workspace / "default-global.secret").write_bytes(b"opaque bytes")

        candidate = discover_workspace(self.workspace)
        ignored = entry(candidate, "default-global.secret")

        self.assertIn("ignored", ignored.categories)
        self.assertNotIn("untracked", ignored.categories)
        self.assertEqual("needs-approval", ignored.disposition)
        self.assertEqual(
            "exclude",
            recommended_decisions(candidate)["default-global.secret"],
        )

    def test_custom_xdg_global_ignore_file_is_copied_bound_and_applied(self) -> None:
        custom_xdg = self.root / "custom-xdg"
        excludes = custom_xdg / "git" / "ignore"
        excludes.parent.mkdir(parents=True)
        excludes.write_text("custom-xdg-only.secret\n", encoding="utf-8")
        (self.workspace / "custom-xdg-only.secret").write_bytes(b"opaque bytes")

        with mock.patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(custom_xdg)},
            clear=False,
        ):
            candidate = discover_workspace(self.workspace)

        ignored = entry(candidate, "custom-xdg-only.secret")
        self.assertIn("ignored", ignored.categories)
        self.assertNotIn("untracked", ignored.categories)
        self.assertEqual("needs-approval", ignored.disposition)
        self.assertEqual(
            "exclude",
            recommended_decisions(candidate)["custom-xdg-only.secret"],
        )

    def test_global_ignore_ancestor_swap_is_rejected(self) -> None:
        config_root = self.account_home / ".config"
        original_git_directory = config_root / "git"
        replacement_git_directory = config_root / "git-replacement"
        original_git_directory.mkdir(parents=True)
        replacement_git_directory.mkdir()
        (original_git_directory / "ignore").write_text(
            "old-only.secret\n",
            encoding="utf-8",
        )
        (replacement_git_directory / "ignore").write_text(
            "rotated.secret\n",
            encoding="utf-8",
        )
        (self.workspace / "rotated.secret").write_bytes(b"opaque bytes")
        displaced_git_directory = config_root / "git-old"
        original_path_sets = policy_module._git_path_sets
        swapped = False

        def swap_ancestor(*args, **kwargs):
            nonlocal swapped
            original_git_directory.rename(displaced_git_directory)
            replacement_git_directory.rename(original_git_directory)
            swapped = True
            return original_path_sets(*args, **kwargs)

        with mock.patch(
            "workspace_policy._git_path_sets",
            side_effect=swap_ancestor,
        ):
            with self.assertRaisesRegex(
                WorkspacePolicyError,
                "excludes path changed",
            ):
                discover_workspace(self.workspace)

        self.assertTrue(swapped)

    def test_hard_exclusions_are_non_overridable_and_never_become_portable(
        self,
    ) -> None:
        private_bytes = b"PRIVATE-KEY-MATERIAL-NEVER-TRANSFER"
        private_path = self.workspace / "id_ed25519"
        private_path.write_bytes(private_bytes)
        candidate = discover_workspace(self.workspace)
        private_entry = entry(candidate, "id_ed25519")
        self.assertIn("sensitive", private_entry.categories)
        self.assertIn("hard-excluded", private_entry.categories)
        self.assertIsNone(private_entry.sha256)

        override = recommended_decisions(candidate)
        override["id_ed25519"] = "include"
        with self.assertRaisesRegex(WorkspacePolicyError, "hard-excluded"):
            self.approve(candidate, override)

        approval = self.approve(candidate, recommended_decisions(candidate))
        policy = compile_effective_policy(candidate, approval)
        portable = json.dumps(policy.to_dict(), sort_keys=True)
        self.assertNotIn("id_ed25519", portable)
        self.assertNotIn(hashlib.sha256(private_bytes).hexdigest(), portable)
        self.assertNotIn(
            ".git", {item.path for item in policy.initial_transfer_entries}
        )

    def test_every_keychain_database_name_is_hard_excluded(self) -> None:
        secret = b"custom-keychain-database-secret"
        (self.workspace / "Work.keychain-db").write_bytes(secret)

        candidate = discover_workspace(self.workspace)
        keychain = entry(candidate, "Work.keychain-db")

        self.assertIn("hard-excluded", keychain.categories)
        self.assertIn("sensitive", keychain.categories)
        self.assertIsNone(keychain.sha256)
        self.assertIsNone(keychain.size)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        portable = json.dumps(policy.to_dict(), sort_keys=True)
        self.assertNotIn("Work.keychain-db", portable)
        self.assertNotIn(hashlib.sha256(secret).hexdigest(), portable)

    def test_git_credential_store_is_hard_excluded(self) -> None:
        secret = b"https://alice:not-a-known-token@example.com\n"
        (self.workspace / ".git-credentials").write_bytes(secret)

        candidate = discover_workspace(self.workspace)
        credential_store = entry(candidate, ".git-credentials")

        self.assertIn("hard-excluded", credential_store.categories)
        self.assertIn("sensitive", credential_store.categories)
        self.assertEqual("stays-local", credential_store.disposition)
        self.assertIsNone(credential_store.sha256)
        self.assertIsNone(credential_store.size)
        defaults = recommended_decisions(candidate)
        self.assertEqual("exclude", defaults[".git-credentials"])
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, defaults),
        )
        portable = json.dumps(policy.to_dict(), sort_keys=True)
        self.assertNotIn(".git-credentials", portable)
        self.assertNotIn(hashlib.sha256(secret).hexdigest(), portable)

    def test_opaque_database_and_credential_paths_default_to_exclusion(self) -> None:
        (self.workspace / "data").mkdir()
        (self.workspace / ".docker").mkdir()
        (self.workspace / ".kube").mkdir()
        (self.workspace / "profile").mkdir()
        paths = {
            "data/customers.sqlite": b"opaque database bytes",
            "data/customers.sqlite-wal": b"opaque database sidecar bytes",
            ".docker/config.json": b"opaque docker credential store",
            ".kube/config": b"opaque kube credential store",
            "secrets.yaml": b"opaque yaml values",
            ".envrc": b"opaque environment values",
            "profile/Cookies-journal": b"opaque browser cookie journal",
            "profile/cookies.sqlite-wal": b"opaque browser cookie wal",
        }
        for path, content in paths.items():
            (self.workspace / path).write_bytes(content)

        candidate = discover_workspace(self.workspace)
        defaults = recommended_decisions(candidate)

        for path in paths:
            self.assertIn("sensitive", entry(candidate, path).categories)
            self.assertEqual("exclude", defaults[path])
        for path in (
            ".docker/config.json",
            ".kube/config",
            "profile/Cookies-journal",
            "profile/cookies.sqlite-wal",
        ):
            self.assertIn("hard-excluded", entry(candidate, path).categories)
            self.assertEqual("stays-local", entry(candidate, path).disposition)
        for path in (
            ".envrc",
            "data/customers.sqlite",
            "data/customers.sqlite-wal",
            "secrets.yaml",
        ):
            self.assertEqual("needs-approval", entry(candidate, path).disposition)

        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, defaults),
        )
        portable = json.dumps(policy.to_dict(), sort_keys=True)
        for path in paths:
            self.assertNotIn(path, portable)

    def test_all_excluded_path_metadata_is_absent_from_portable_policy(self) -> None:
        candidate = discover_workspace(self.workspace)
        decisions = recommended_decisions(candidate)
        decisions["untracked.txt"] = "exclude"
        approval = self.approve(candidate, decisions)
        policy = compile_effective_policy(candidate, approval)
        serialized = json.dumps(policy.to_dict(), sort_keys=True)

        for excluded in (
            ".env.example",
            ".env.local",
            "ignored/cache.txt",
            "untracked.txt",
        ):
            self.assertNotIn(excluded, serialized)

    def test_content_or_path_drift_invalidates_the_candidate(self) -> None:
        candidate = discover_workspace(self.workspace)
        (self.workspace / "tracked.txt").write_text("changed later\n", encoding="utf-8")
        with self.assertRaisesRegex(
            WorkspacePolicyError, "changed after manifest approval"
        ):
            validate_candidate_unchanged(candidate)

        (self.workspace / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        candidate = discover_workspace(self.workspace)
        (self.workspace / "new-after-review.txt").write_text("late\n", encoding="utf-8")
        with self.assertRaisesRegex(
            WorkspacePolicyError, "changed after manifest approval"
        ):
            validate_candidate_unchanged(candidate)

    def test_git_index_drift_invalidates_the_candidate(self) -> None:
        candidate = discover_workspace(self.workspace)
        git("add", "dirty.txt", cwd=self.workspace)
        with self.assertRaisesRegex(
            WorkspacePolicyError, "changed after manifest approval"
        ):
            validate_candidate_unchanged(candidate)

    def test_unmodified_candidate_passes_drift_validation(self) -> None:
        candidate = discover_workspace(self.workspace)
        current = validate_candidate_unchanged(candidate)
        self.assertEqual(candidate.candidate_sha256, current.candidate_sha256)

    def test_unsafe_symlink_is_hard_excluded_without_target_or_content(self) -> None:
        outside = self.root / "outside-secret.txt"
        outside.write_text("OUTSIDE-SECRET-BYTES\n", encoding="utf-8")
        os.symlink(outside, self.workspace / "escape")

        candidate = discover_workspace(self.workspace)
        unsafe = entry(candidate, "escape")
        self.assertEqual("excluded", unsafe.kind)
        self.assertIn("unsupported", unsafe.categories)
        self.assertIn("hard-excluded", unsafe.categories)
        self.assertIsNone(unsafe.link_target)
        self.assertIsNone(unsafe.sha256)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        serialized = json.dumps(policy.to_dict(), sort_keys=True)
        self.assertNotIn("escape", serialized)
        self.assertNotIn("outside-secret", serialized)

    def test_safe_relative_symlink_can_be_approved_by_normal_rules(self) -> None:
        os.symlink("tracked.txt", self.workspace / "tracked-link")
        candidate = discover_workspace(self.workspace)
        safe_link = entry(candidate, "tracked-link")
        self.assertEqual("symlink", safe_link.kind)
        self.assertEqual("tracked.txt", safe_link.link_target)
        self.assertEqual(("untracked",), safe_link.categories)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        self.assertIn(
            "tracked-link", {item.path for item in policy.initial_transfer_entries}
        )

    def test_symlink_to_empty_directory_is_hard_excluded(self) -> None:
        (self.workspace / "empty-directory").mkdir()
        os.symlink("empty-directory", self.workspace / "directory-link")

        candidate = discover_workspace(self.workspace)
        directory_link = entry(candidate, "directory-link")

        self.assertEqual("excluded", directory_link.kind)
        self.assertIn("hard-excluded", directory_link.categories)
        self.assertIn("unsupported", directory_link.categories)
        self.assertIsNone(directory_link.link_target)

    def test_compile_rejects_included_symlink_with_excluded_target(self) -> None:
        os.symlink("tracked.txt", self.workspace / "tracked-link")
        candidate = discover_workspace(self.workspace)
        decisions = recommended_decisions(candidate)
        self.assertEqual("include", decisions["tracked-link"])
        decisions["tracked.txt"] = "exclude"

        approval = self.approve(candidate, decisions)

        with self.assertRaisesRegex(WorkspacePolicyError, "symlink dependency"):
            compile_effective_policy(candidate, approval)

    def test_symlink_recommendations_follow_ignored_target_decision(self) -> None:
        os.symlink("ignored/cache.txt", self.workspace / "ignored-link")
        candidate = discover_workspace(self.workspace)

        defaults = recommended_decisions(candidate)
        self.assertEqual("exclude", defaults["ignored/cache.txt"])
        self.assertEqual("exclude", defaults["ignored-link"])
        compile_effective_policy(candidate, self.approve(candidate, defaults))

        explicit = dict(defaults)
        explicit["ignored/cache.txt"] = "include"
        explicit["ignored-link"] = "include"
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, explicit),
        )
        included = {item.path for item in policy.initial_transfer_entries}
        self.assertIn("ignored/cache.txt", included)
        self.assertIn("ignored-link", included)

    def test_symlinks_into_private_or_sensitive_paths_are_hard_excluded(self) -> None:
        private_directory = self.workspace / ".ssh"
        private_directory.mkdir()
        (private_directory / "custom-key").write_text("secret\n", encoding="utf-8")
        (self.workspace / "opaque-sensitive.txt").write_text(
            "AWS_ACCESS_KEY_ID=AKIAAAAAAAAAAAAAAAAA\n",
            encoding="utf-8",
        )
        os.symlink(".ssh/custom-key", self.workspace / "private-link")
        os.symlink(".env.example", self.workspace / "sensitive-link")
        os.symlink(
            "opaque-sensitive.txt",
            self.workspace / "content-sensitive-link",
        )

        candidate = discover_workspace(self.workspace)
        for path in (
            "content-sensitive-link",
            "private-link",
            "sensitive-link",
        ):
            link = entry(candidate, path)
            self.assertEqual("excluded", link.kind)
            self.assertIn("hard-excluded", link.categories)
            self.assertIn("unsupported", link.categories)
            self.assertIsNone(link.link_target)

    def test_noncanonical_or_control_character_symlink_target_is_rejected(self) -> None:
        os.symlink("./tracked.txt", self.workspace / "noncanonical-link")
        os.symlink("bad\nname", self.workspace / "control-link")

        candidate = discover_workspace(self.workspace)

        for path in ("control-link", "noncanonical-link"):
            link = entry(candidate, path)
            self.assertEqual("excluded", link.kind)
            self.assertEqual("unsafe-symbolic-link", link.unsupported_reason)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO is unavailable")
    def test_special_files_are_classified_unsupported_and_hard_excluded(self) -> None:
        os.mkfifo(self.workspace / "agent.pipe")
        candidate = discover_workspace(self.workspace)
        special = entry(candidate, "agent.pipe")
        self.assertEqual("unsupported", special.kind)
        self.assertIn("unsupported", special.categories)
        self.assertIn("hard-excluded", special.categories)
        self.assertEqual("stays-local", special.disposition)

    def test_nested_repository_is_rejected(self) -> None:
        nested = self.workspace / "vendor" / "nested"
        nested.mkdir(parents=True)
        git("init", cwd=nested)
        with self.assertRaisesRegex(WorkspacePolicyError, "nested Git repositories"):
            discover_workspace(self.workspace)

    def test_nested_bare_repository_is_rejected_before_its_files_are_hashed(
        self,
    ) -> None:
        nested = self.workspace / "vendor" / "nested.git"
        nested.mkdir(parents=True)
        git("init", "--bare", cwd=nested)
        inspected_names: list[str] = []
        original_inspect = policy_module._inspect_regular_file_at

        def record_inspection(parent_fd, name, expected):
            inspected_names.append(name)
            return original_inspect(parent_fd, name, expected)

        candidate = None
        with mock.patch(
            "workspace_policy._inspect_regular_file_at",
            side_effect=record_inspection,
        ):
            with self.assertRaisesRegex(
                WorkspacePolicyError,
                "nested bare Git repositories",
            ):
                candidate = discover_workspace(self.workspace)

        self.assertIsNone(candidate)
        self.assertNotIn("HEAD", inspected_names)
        self.assertNotIn("config", inspected_names)

    def test_private_key_content_is_hard_excluded_regardless_of_filename(self) -> None:
        private_bytes = (
            b"-----BEGIN OPENSSH PRIVATE KEY-----\n"
            b"b3BlbnNzaC1rZXktdjEAAAAA\n"
            b"-----END OPENSSH PRIVATE KEY-----\n"
        )
        (self.workspace / "ordinary-notes.txt").write_bytes(private_bytes)

        candidate = discover_workspace(self.workspace)
        private_entry = entry(candidate, "ordinary-notes.txt")

        self.assertIn("hard-excluded", private_entry.categories)
        self.assertIn("sensitive", private_entry.categories)
        self.assertEqual("private-key-material", private_entry.unsupported_reason)
        self.assertIsNone(private_entry.sha256)
        self.assertIsNone(private_entry.size)

    def test_private_key_content_is_detected_after_the_first_scan_chunk(self) -> None:
        marker = b"-----BEGIN OPENSSH PRIVATE KEY-----"
        (self.workspace / "late-notes.txt").write_bytes(b"A" * 65_537 + marker)

        candidate = discover_workspace(self.workspace)
        private_entry = entry(candidate, "late-notes.txt")

        self.assertIn("hard-excluded", private_entry.categories)
        self.assertEqual("private-key-material", private_entry.unsupported_reason)

    def test_private_key_marker_spanning_scan_chunks_is_detected(self) -> None:
        marker = b"-----BEGIN OPENSSH PRIVATE KEY-----"
        split = 17
        prefix = b"A" * (64 * 1024 - split)
        (self.workspace / "boundary-notes.txt").write_bytes(prefix + marker)

        candidate = discover_workspace(self.workspace)
        private_entry = entry(candidate, "boundary-notes.txt")

        self.assertIn("hard-excluded", private_entry.categories)
        self.assertEqual("private-key-material", private_entry.unsupported_reason)

    def test_known_credential_content_requires_explicit_approval(self) -> None:
        (self.workspace / "ordinary-config.txt").write_text(
            "aws_access_key_id = AKIA1234567890ABCDEF\n",
            encoding="utf-8",
        )

        candidate = discover_workspace(self.workspace)
        credential = entry(candidate, "ordinary-config.txt")

        self.assertIn("sensitive", credential.categories)
        self.assertEqual("needs-approval", credential.disposition)
        self.assertEqual(
            "exclude",
            recommended_decisions(candidate)["ordinary-config.txt"],
        )

    def test_credential_assignment_content_requires_explicit_approval(self) -> None:
        (self.workspace / "ordinary-config.txt").write_text(
            "API_KEY=super-secret-value\n",
            encoding="utf-8",
        )

        candidate = discover_workspace(self.workspace)
        credential = entry(candidate, "ordinary-config.txt")

        self.assertIn("sensitive", credential.categories)
        self.assertEqual("needs-approval", credential.disposition)
        self.assertEqual(
            "exclude",
            recommended_decisions(candidate)["ordinary-config.txt"],
        )

    def test_gitlink_submodule_entry_is_rejected(self) -> None:
        head = git("rev-parse", "HEAD", cwd=self.workspace).strip()
        git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{head},vendor/submodule",
            cwd=self.workspace,
        )
        with self.assertRaisesRegex(WorkspacePolicyError, "submodules"):
            discover_workspace(self.workspace)

    def test_linked_worktree_is_rejected(self) -> None:
        linked = self.root / "linked"
        git("worktree", "add", "-b", "linked-test", str(linked), cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "linked worktrees"):
            discover_workspace(linked)

    def test_selecting_a_repository_subdirectory_is_rejected(self) -> None:
        child = self.workspace / "child"
        child.mkdir()
        with self.assertRaisesRegex(
            WorkspacePolicyError, "exactly one Git worktree root"
        ):
            discover_workspace(child)

    def test_symlinked_workspace_root_is_rejected(self) -> None:
        link = self.root / "workspace-link"
        os.symlink(self.workspace, link)
        with self.assertRaisesRegex(WorkspacePolicyError, "physical directory"):
            discover_workspace(link)

    def test_root_swap_between_validation_and_open_is_rejected(self) -> None:
        original_workspace = self.root / "workspace-before-swap"
        original_open = os.open
        swapped = False

        def swap_at_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is None and Path(path) == self.workspace and not swapped:
                self.workspace.rename(original_workspace)
                self.workspace.mkdir()
                swapped = True
            if dir_fd is None:
                return original_open(path, flags, mode)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        try:
            with mock.patch("workspace_policy.os.open", side_effect=swap_at_open):
                with self.assertRaisesRegex(
                    WorkspacePolicyError,
                    "root changed while it was opened",
                ):
                    discover_workspace(self.workspace)
        finally:
            if swapped:
                self.workspace.rmdir()
                original_workspace.rename(self.workspace)

        self.assertTrue(swapped)

    def test_exact_home_directory_root_is_rejected_but_a_child_is_allowed(self) -> None:
        with mock.patch(
            "workspace_policy._resolved_home_directory",
            return_value=self.workspace,
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "home directory"):
                discover_workspace(self.workspace)

        with mock.patch(
            "workspace_policy._resolved_home_directory",
            return_value=self.root,
        ):
            self.assertEqual(self.workspace, discover_workspace(self.workspace).root)

    def test_home_directory_guard_ignores_ambient_home_override(self) -> None:
        with (
            mock.patch(
                "workspace_policy._account_home_directory",
                return_value=self.workspace,
            ),
            mock.patch.dict(
                os.environ,
                {"HOME": str(self.account_home)},
                clear=False,
            ),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "home directory"):
                discover_workspace(self.workspace)

    def test_workspace_below_account_private_directory_is_rejected(self) -> None:
        private_workspace = self.account_home / ".docker"
        private_workspace.mkdir()
        git("init", "--initial-branch=main", cwd=private_workspace)
        (private_workspace / "config.json").write_bytes(
            b"opaque docker credential store"
        )

        with self.assertRaisesRegex(
            WorkspacePolicyError,
            "protected account-private directory",
        ):
            discover_workspace(private_workspace)

    def test_in_progress_git_operation_is_rejected(self) -> None:
        (self.workspace / ".git" / "MERGE_HEAD").write_text(
            "0" * 40 + "\n",
            encoding="ascii",
        )
        with self.assertRaisesRegex(WorkspacePolicyError, "in-progress Git"):
            discover_workspace(self.workspace)

    def test_workspace_file_count_and_byte_limits_fail_closed(self) -> None:
        with mock.patch.object(policy_module, "_MAX_WORKSPACE_ENTRIES", 1):
            with self.assertRaisesRegex(WorkspacePolicyError, "entry-count"):
                discover_workspace(self.workspace)
        with mock.patch.object(policy_module, "_MAX_FILE_BYTES", 3):
            with self.assertRaisesRegex(WorkspacePolicyError, "per-file"):
                discover_workspace(self.workspace)
        with mock.patch.object(policy_module, "_MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(WorkspacePolicyError, "total-byte"):
                discover_workspace(self.workspace)

    def test_identifiable_same_device_child_mount_is_rejected(self) -> None:
        mounted = self.workspace / "mounted"
        mounted.mkdir()
        (mounted / "outside.txt").write_text("outside\n", encoding="utf-8")
        mounts = frozenset({"mounted"})

        with mock.patch(
            "workspace_policy._identifiable_nested_mounts",
            return_value=mounts,
        ):
            with self.assertRaisesRegex(
                WorkspacePolicyError,
                "nested workspace mount",
            ):
                discover_workspace(self.workspace)

    def test_git_directory_nested_mount_and_mount_topology_drift_are_rejected(
        self,
    ) -> None:
        with mock.patch(
            "workspace_policy._identifiable_nested_mounts",
            return_value=frozenset({".git"}),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "Git administration"):
                discover_workspace(self.workspace)

        with mock.patch(
            "workspace_policy._identifiable_nested_mounts",
            side_effect=(frozenset(), frozenset({"late-mount"})),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "mount topology"):
                discover_workspace(self.workspace)

    def test_linux_bind_and_darwin_null_mounts_are_identified_by_mountpoint(
        self,
    ) -> None:
        linux_mountinfo = (
            "36 25 0:42 / / rw - ext4 /dev/root rw\n"
            f"37 36 0:42 /outside {self.workspace}/bound rw - ext4 /dev/root rw\n"
        )
        with (
            mock.patch.object(policy_module.sys, "platform", "linux"),
            mock.patch.object(
                policy_module.Path,
                "read_text",
                return_value=linux_mountinfo,
            ),
        ):
            self.assertIn(
                "bound",
                policy_module._identifiable_nested_mounts(self.workspace),
            )

        darwin_mount = subprocess.CompletedProcess(
            args=["/sbin/mount"],
            returncode=0,
            stdout=(
                (
                    "/dev/disk on / (apfs, local)\n"
                    f"outside on {self.workspace}/null (copy) (nullfs, local)\n"
                ).encode()
            ),
            stderr=b"",
        )
        with (
            mock.patch.object(policy_module.sys, "platform", "darwin"),
            mock.patch.object(policy_module.Path, "is_file", return_value=True),
            mock.patch("workspace_policy.subprocess.run", return_value=darwin_mount),
        ):
            self.assertIn(
                "null (copy)",
                policy_module._identifiable_nested_mounts(self.workspace),
            )

    def test_mount_table_inspection_failures_are_rejected(self) -> None:
        with (
            mock.patch.object(policy_module.sys, "platform", "linux"),
            mock.patch.object(
                policy_module.Path,
                "read_text",
                side_effect=OSError("unavailable"),
            ),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "mount table"):
                policy_module._mount_table()

        with (
            mock.patch.object(policy_module.sys, "platform", "linux"),
            mock.patch.object(policy_module.Path, "read_text", return_value="bad\n"),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "parseable"):
                policy_module._mount_table()

        darwin_failures = (
            subprocess.TimeoutExpired(["/sbin/mount"], 5),
            subprocess.CompletedProcess(
                args=["/sbin/mount"], returncode=1, stdout=b"", stderr=b"failure"
            ),
            subprocess.CompletedProcess(
                args=["/sbin/mount"], returncode=0, stdout=b"\xff", stderr=b""
            ),
            subprocess.CompletedProcess(
                args=["/sbin/mount"], returncode=0, stdout=b"not a mount\n", stderr=b""
            ),
        )
        for failure in darwin_failures:
            with self.subTest(failure=failure):
                with (
                    mock.patch.object(policy_module.sys, "platform", "darwin"),
                    mock.patch.object(
                        policy_module.Path,
                        "is_file",
                        return_value=True,
                    ),
                    mock.patch(
                        "workspace_policy.subprocess.run",
                        side_effect=failure
                        if isinstance(failure, BaseException)
                        else None,
                        return_value=None
                        if isinstance(failure, BaseException)
                        else failure,
                    ),
                ):
                    with self.assertRaisesRegex(WorkspacePolicyError, "mount table"):
                        policy_module._mount_table()

    def test_mount_table_must_cover_root_and_platform_must_be_supported(self) -> None:
        with mock.patch(
            "workspace_policy._mount_table",
            return_value=(("/somewhere-else", "apfs"),),
        ):
            with self.assertRaisesRegex(WorkspacePolicyError, "not represented"):
                policy_module._filesystem_type(self.workspace)
            with self.assertRaisesRegex(WorkspacePolicyError, "not represented"):
                policy_module._identifiable_nested_mounts(self.workspace)

        with mock.patch.object(policy_module.sys, "platform", "unsupported-os"):
            with self.assertRaisesRegex(WorkspacePolicyError, "does not support"):
                policy_module._mount_table()

    def test_tampered_digests_are_rejected(self) -> None:
        candidate = discover_workspace(self.workspace)
        tampered_candidate = replace(candidate, candidate_sha256="0" * 64)
        with self.assertRaisesRegex(WorkspacePolicyError, "digest"):
            recommended_decisions(tampered_candidate)

        approval = self.approve(candidate, recommended_decisions(candidate))
        tampered_approval = replace(approval, approval_sha256="0" * 64)
        with self.assertRaisesRegex(WorkspacePolicyError, "approval digest"):
            compile_effective_policy(candidate, tampered_approval)

        policy = compile_effective_policy(candidate, approval)
        tampered_policy = replace(policy, policy_sha256="0" * 64)
        with self.assertRaisesRegex(WorkspacePolicyError, "effective policy digest"):
            validate_effective_policy(candidate, approval, tampered_policy)

    def test_approval_cannot_be_reused_for_another_candidate(self) -> None:
        candidate = discover_workspace(self.workspace)
        approval = self.approve(candidate, recommended_decisions(candidate))
        (self.workspace / "untracked.txt").write_text("different\n", encoding="utf-8")
        changed = discover_workspace(self.workspace)
        with self.assertRaisesRegex(
            WorkspacePolicyError, "different workspace candidate"
        ):
            compile_effective_policy(changed, approval)

    def test_approval_scope_is_bound_and_rejects_path_like_ids(self) -> None:
        candidate = discover_workspace(self.workspace)
        decisions = recommended_decisions(candidate)
        with self.assertRaisesRegex(WorkspacePolicyError, "run ID"):
            approve_candidate(
                candidate,
                decisions,
                scope=ApprovalScopeV1(
                    run_id="../../escape",
                    workspace_id="workspace",
                    helper_version="1.0.0",
                ),
            )

        approval = self.approve(candidate, decisions)
        policy = compile_effective_policy(candidate, approval)
        self.assertEqual(self.scope, approval.scope)
        self.assertEqual(self.scope, policy.scope)
        self.assertEqual(
            canonical_sha256(candidate.identity.to_dict()),
            policy.workspace_identity_sha256,
        )
        portable = policy.to_dict()
        self.assertIn("initialTransferEntries", portable)
        self.assertNotIn("entries", portable)
        self.assertEqual(
            "workspace-policy-classifier-v1",
            portable["returnPolicy"]["classifierVersion"],
        )

    def test_return_classifier_handles_new_ordinary_review_and_block_paths(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        approval = self.approve(candidate, recommended_decisions(candidate))
        policy = compile_effective_policy(candidate, approval)
        returned = (
            return_file("generated.py", ("untracked",)),
            return_file("generated.env", ("untracked", "sensitive")),
            return_file("ignored/new-cache.txt", ("ignored",)),
            return_file("id_ed25519", ("untracked", "sensitive", "hard-excluded")),
            return_file("tracked-force-added.env", ("tracked", "sensitive")),
        )

        snapshot = return_manifest(candidate, returned)
        plan = classify_return_snapshot(policy, snapshot)
        actions = {decision.path: decision.action for decision in plan.decisions}
        self.assertEqual("ALLOW", actions["generated.py"])
        self.assertEqual("NEEDS_REVIEW", actions["generated.env"])
        self.assertEqual("NEEDS_REVIEW", actions["ignored/new-cache.txt"])
        self.assertEqual("BLOCK", actions["id_ed25519"])
        self.assertEqual("NEEDS_REVIEW", actions["tracked-force-added.env"])
        self.assertEqual("BLOCK", plan.overall_disposition)
        self.assertEqual(
            {"generated.py"},
            {item.path for item in plan.allowed_entries},
        )
        self.assertEqual("cloud-return", plan.role)
        self.assertEqual(snapshot.candidate_sha256, plan.snapshot_sha256)
        serialized = plan.to_dict()
        findings = [
            item for item in serialized["decisions"] if item["action"] != "ALLOW"
        ]
        self.assertTrue(findings)
        self.assertTrue(
            all(set(item) == {"action", "path", "reason"} for item in findings)
        )
        validate_return_plan(policy, snapshot, plan)

    def test_force_added_ignored_path_stays_review_only_on_return(self) -> None:
        initial = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            initial,
            self.approve(initial, recommended_decisions(initial)),
        )
        opaque = self.workspace / "ignored" / "force-added.bin"
        opaque.write_bytes(b"opaque bytes without credential-shaped content\n")
        git("add", "--force", "ignored/force-added.bin", cwd=self.workspace)

        snapshot = discover_workspace(self.workspace)
        returned = entry(snapshot, "ignored/force-added.bin")
        self.assertEqual(
            ("tracked", "staged", "ignored"),
            returned.categories,
        )
        plan = classify_return_snapshot(policy, snapshot)
        decisions = {decision.path: decision for decision in plan.decisions}
        self.assertEqual("NEEDS_REVIEW", decisions[returned.path].action)

        explicit = recommended_decisions(snapshot)
        explicit[returned.path] = "include"
        approved_policy = compile_effective_policy(
            snapshot,
            self.approve(snapshot, explicit),
        )
        approved = next(
            item
            for item in approved_policy.initial_transfer_entries
            if item.path == returned.path
        )
        self.assertEqual(returned.categories, approved.categories)

    def test_return_symlink_is_not_allowed_without_review_only_target(self) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        target = return_file("ignored-target.bin", ("ignored",))
        link_target = b"ignored-target.bin"
        link = CandidateEntryV1(
            path="ordinary-link",
            kind="symlink",
            categories=("untracked",),
            disposition="will-move",
            sha256=hashlib.sha256(link_target).hexdigest(),
            size=len(link_target),
            link_target=link_target.decode(),
        )
        snapshot = return_manifest(candidate, (link, target))

        plan = classify_return_snapshot(policy, snapshot)
        actions = {decision.path: decision.action for decision in plan.decisions}

        self.assertEqual("NEEDS_REVIEW", actions[target.path])
        self.assertEqual("NEEDS_REVIEW", actions[link.path])
        self.assertNotIn(link.path, {item.path for item in plan.allowed_entries})

    def test_return_classifier_requires_manifest_shape_and_has_no_git_sentinel(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )

        with self.assertRaisesRegex(WorkspacePolicyError, "CandidateManifestV1"):
            classify_return_snapshot(policy, candidate.entries)  # type: ignore[arg-type]

        plan = classify_return_snapshot(policy, candidate)
        self.assertNotIn(".git", {decision.path for decision in plan.decisions})
        self.assertFalse(
            any(
                decision.action == "BLOCK"
                and decision.reason == "prohibited-or-unsupported-path"
                for decision in plan.decisions
            )
        )

    def test_return_plan_must_be_reclassified_not_merely_rehashed(self) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        sensitive = return_file("new-token.env", ("untracked", "sensitive"))
        snapshot = return_manifest(candidate, (sensitive,))
        plan = classify_return_snapshot(policy, snapshot)
        forged_entry = PolicyEntryV1(
            path=sensitive.path,
            kind=sensitive.kind,
            categories=sensitive.categories,
            sha256=sensitive.sha256,
            size=sensitive.size,
            executable=sensitive.executable,
        )
        forged = replace(
            plan,
            decisions=(
                ReturnPathDecisionV1(
                    path=sensitive.path,
                    action="ALLOW",
                    reason="new-ordinary-path",
                ),
            ),
            overall_disposition="ALLOW",
            allowed_entries=(forged_entry,),
            plan_sha256="0" * 64,
        )
        forged = replace(
            forged,
            plan_sha256=canonical_sha256(forged.unsigned_dict()),
        )

        forged.assert_valid()
        with self.assertRaisesRegex(WorkspacePolicyError, "does not match"):
            validate_return_plan(policy, snapshot, forged)

    def test_return_plan_binds_complete_snapshot_content_type_and_mode(self) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        original = return_file("generated.py", ("untracked",))
        first_snapshot = return_manifest(candidate, (original,))
        first = classify_return_snapshot(policy, first_snapshot)
        changed_bytes = classify_return_snapshot(
            policy,
            return_manifest(candidate, (replace(original, sha256="a" * 64),)),
        )
        changed_mode = classify_return_snapshot(
            policy,
            return_manifest(candidate, (replace(original, executable=True),)),
        )
        link = CandidateEntryV1(
            path="generated.py",
            kind="symlink",
            categories=("untracked",),
            disposition="will-move",
            sha256=hashlib.sha256(b"tracked.txt").hexdigest(),
            size=len(b"tracked.txt"),
            link_target="tracked.txt",
        )
        link_target = return_file("tracked.txt", ("tracked",))
        changed_type = classify_return_snapshot(
            policy,
            return_manifest(candidate, (link, link_target)),
        )

        self.assertNotEqual(first.snapshot_sha256, changed_bytes.snapshot_sha256)
        self.assertNotEqual(first.plan_sha256, changed_bytes.plan_sha256)
        self.assertNotEqual(first.plan_sha256, changed_mode.plan_sha256)
        self.assertNotEqual(first.plan_sha256, changed_type.plan_sha256)
        self.assertEqual("ALLOW", first.overall_disposition)

    def test_return_classifier_allows_changes_to_an_initially_approved_sensitive_path(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        decisions = recommended_decisions(candidate)
        decisions[".env.example"] = "include"
        policy = compile_effective_policy(candidate, self.approve(candidate, decisions))
        returned = return_file(".env.example", ("tracked", "sensitive"))

        snapshot = return_manifest(candidate, (returned,))
        plan = classify_return_snapshot(policy, snapshot)

        self.assertEqual("ALLOW", plan.decisions[0].action)
        self.assertEqual("approved-initial-path", plan.decisions[0].reason)

    def test_tracked_deletion_is_an_explicit_portable_tombstone(self) -> None:
        candidate = discover_workspace(self.workspace)
        deleted = entry(candidate, "deleted.txt")
        self.assertEqual("absent", deleted.kind)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        tombstone = next(
            item
            for item in policy.initial_transfer_entries
            if item.path == "deleted.txt"
        )
        self.assertEqual("absent", tombstone.kind)
        self.assertIsNone(tombstone.sha256)
        self.assertIsNone(tombstone.size)

    def test_hard_link_is_unsupported_without_hashing_its_bytes(self) -> None:
        os.link(self.workspace / "untracked.txt", self.workspace / "hard-link.txt")
        candidate = discover_workspace(self.workspace)
        for path in ("hard-link.txt", "untracked.txt"):
            hard_link = entry(candidate, path)
            self.assertIn("unsupported", hard_link.categories)
            self.assertIn("hard-excluded", hard_link.categories)
            self.assertIsNone(hard_link.sha256)

    def test_detached_unborn_and_sparse_worktrees_are_rejected(self) -> None:
        git("checkout", "--detach", cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "detached"):
            discover_workspace(self.workspace)

        unborn = self.root / "unborn"
        unborn.mkdir()
        git("init", "--initial-branch=main", cwd=unborn)
        with self.assertRaisesRegex(WorkspacePolicyError, "unborn"):
            discover_workspace(unborn)

        git("checkout", "main", cwd=self.workspace)
        git("sparse-checkout", "init", "--cone", cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "sparse"):
            discover_workspace(self.workspace)

    def test_skip_worktree_and_assume_unchanged_index_flags_are_rejected(self) -> None:
        git("update-index", "--skip-worktree", "tracked.txt", cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "skip-worktree"):
            discover_workspace(self.workspace)

        git("update-index", "--no-skip-worktree", "tracked.txt", cwd=self.workspace)
        git("update-index", "--assume-unchanged", "tracked.txt", cwd=self.workspace)
        with self.assertRaisesRegex(WorkspacePolicyError, "assume-unchanged"):
            discover_workspace(self.workspace)

    def test_control_characters_and_excessive_depth_are_rejected(self) -> None:
        (self.workspace / "bad\nname.txt").write_text("bad\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspacePolicyError, "control characters"):
            discover_workspace(self.workspace)
        (self.workspace / "bad\nname.txt").unlink()

        parent = self.workspace
        for _ in range(65):
            parent = parent / "d"
            parent.mkdir()
        (parent / "too-deep.txt").write_text("deep\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspacePolicyError, "portable v1 limit"):
            discover_workspace(self.workspace)

    def test_identifiable_network_filesystem_is_rejected(self) -> None:
        with mock.patch("workspace_policy._filesystem_type", return_value="nfs4"):
            with self.assertRaisesRegex(WorkspacePolicyError, "network filesystems"):
                discover_workspace(self.workspace)

    def test_policy_schema_rejects_unsafe_or_normalization_colliding_entries(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        base = policy.initial_transfer_entries[0]
        unsafe = replace(base, path="../outside")
        with self.assertRaisesRegex(WorkspacePolicyError, "outside its root"):
            replace(policy, initial_transfer_entries=(unsafe,)).assert_valid()

        composed = replace(base, path="caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt")
        decomposed = replace(base, path="cafe\N{COMBINING ACUTE ACCENT}.txt")
        colliding = tuple(
            sorted((composed, decomposed), key=lambda item: item.path.encode())
        )
        with self.assertRaisesRegex(
            WorkspacePolicyError, "collide after normalization"
        ):
            replace(policy, initial_transfer_entries=colliding).assert_valid()

    def test_return_policy_object_is_strict(self) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        weakened = replace(
            policy,
            return_policy=ReturnPolicyV1(hard_excluded_paths="allow"),
        )
        with self.assertRaisesRegex(WorkspacePolicyError, "v1 ruleset"):
            weakened.assert_valid()

    def test_effective_policy_strict_decoder_round_trips_and_rejects_tampering(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )
        payload = policy.to_dict()
        self.assertEqual(policy, effective_policy_from_dict(payload))
        self.assertIsNone(validate_policy_dict(payload))

        unknown = json.loads(json.dumps(payload))
        unknown["unexpected"] = True
        with self.assertRaisesRegex(WorkspacePolicyError, "schema"):
            effective_policy_from_dict(unknown)

        float_version = json.loads(json.dumps(payload))
        float_version["schemaVersion"] = 1.0
        with self.assertRaisesRegex(WorkspacePolicyError, "version"):
            effective_policy_from_dict(float_version)

        tampered = json.loads(json.dumps(payload))
        hashed_entry = next(
            item for item in tampered["initialTransferEntries"] if "sha256" in item
        )
        hashed_entry["sha256"] = (
            "f" * 64 if hashed_entry["sha256"] != "f" * 64 else "e" * 64
        )
        with self.assertRaisesRegex(WorkspacePolicyError, "digest"):
            effective_policy_from_dict(tampered)

        weakened_return = json.loads(json.dumps(payload))
        weakened_return["returnPolicy"]["hardExcludedPaths"] = "allow"
        with self.assertRaisesRegex(WorkspacePolicyError, "v1 ruleset"):
            effective_policy_from_dict(weakened_return)

        unknown_entry = json.loads(json.dumps(payload))
        unknown_entry["initialTransferEntries"][0]["unknown"] = "value"
        with self.assertRaisesRegex(WorkspacePolicyError, "entry schema"):
            effective_policy_from_dict(unknown_entry)

    def test_effective_policy_decoder_rejects_redundant_null_entry_fields(
        self,
    ) -> None:
        candidate = discover_workspace(self.workspace)
        policy = compile_effective_policy(
            candidate,
            self.approve(candidate, recommended_decisions(candidate)),
        )

        file_payload = policy.to_dict()
        file_entry = next(
            item
            for item in file_payload["initialTransferEntries"]
            if item["kind"] == "file"
        )
        file_entry["linkTarget"] = None
        with self.assertRaisesRegex(WorkspacePolicyError, "noncanonical"):
            effective_policy_from_dict(file_payload)

        absent_payload = policy.to_dict()
        absent_entry = next(
            item
            for item in absent_payload["initialTransferEntries"]
            if item["kind"] == "absent"
        )
        absent_entry["sha256"] = None
        absent_entry["size"] = None
        absent_entry["linkTarget"] = None
        with self.assertRaisesRegex(WorkspacePolicyError, "noncanonical"):
            effective_policy_from_dict(absent_payload)


if __name__ == "__main__":
    unittest.main()
