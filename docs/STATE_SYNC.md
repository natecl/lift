# Workspace Handoff and Return Sync

Last updated: 2026-09-02

## Current implementation status

This document remains the authoritative complete Land design. The Phase 0 harness has proven an additive private checkpoint chain and exact restore for three cloud revisions on a generated disposable fixture. The current local fixture engine now implements private `L` capture, conservative `B/L/C` comparison, isolated return merge, journaled clean application with rollback, deliberate conflict preservation, immutable session refs, and a Git-backed receipt. These local mechanics pass clean, disjoint, conflicted, interrupted, tampered-state, exclusion, topology, symlink, and case-collision tests without moving the user's Git state.

Complete Land is not implemented. The remaining highest-value slice is the distributed lifecycle around that engine: enforce the real cloud freeze, create and restore-test one exact final `C`, import it into the local ledger, wait for an offline helper, durably acknowledge local completion, and return the ownership lease. The whole flow must remain one user action. See [`CURRENT_STATE.md`](CURRENT_STATE.md) for the ordered implementation plan and current evidence boundary.

## Product contract

Lift Off is a round trip:

```text
local workspace -> Lift workspace -> local workspace
```

At the end of a cloud session, the user chooses `Land Workspace`. Lift checkpoints the cloud workspace immediately. When the desktop helper can reach the original local folder, it safely applies the result and reports:

> Your latest changes are back on this Mac.

The user does not commit, push, pull, copy a patch, or run a terminal command.

## Why the first slice is not live two-way sync

Two unrestricted writers can silently destroy work, especially across macOS and Linux where path casing, symbolic links, permissions, file watchers, and editor buffers behave differently.

The first slice uses an ownership lease:

```text
LOCAL_PRIMARY -> LIFTING -> CLOUD_PRIMARY -> LANDING -> LOCAL_PRIMARY
```

- Local is primary before Lift Off.
- Cloud is primary after Lift Off reaches its durable handoff point.
- Land pauses cloud writers and creates a final immutable revision.
- Local becomes primary again only after the helper acknowledges a successful return.

Lift does not hard-lock the local directory. If the user edits it while lifted, Lift detects divergence and preserves both sides.

## Version model

Every sync decision compares three snapshots:

- `B`: the handoff baseline acknowledged by both local and cloud;
- `L`: the current local manifest;
- `C`: the final cloud manifest produced by Land.

Each snapshot has both:

- a content manifest used for transfer integrity, inclusion policy, recovery, and cross-platform validation; the fixture format is hash-bound today and the production format must also be authenticated;
- a commit in a Lift-private Git repository used for ancestry, diffing, and three-way merging.

A manifest entry contains at least:

```text
normalized relative path
entry type: file, directory, or symbolic link
content hash or link target hash
size
executable and permission bits that Lift supports
inclusion reason
```

Modification time is useful for scanning but is never proof that content matches. Paths are relative to the selected workspace and must be normalized without following symbolic links outside it.

The baseline covers:

- tracked files;
- uncommitted tracked changes;
- untracked files;
- explicitly approved ignored files;
- supported file modes and symbolic links.

Provider credentials, general home-directory state, caches, and reconstructed dependencies are excluded from the workspace manifest.

## Git-backed merge model

Lift uses the same core model as a pull request without requiring GitHub or changing the user's branch.

```text
original repository HEAD
          |
          B  synthetic Lift Off baseline
         / \
        L   C  local return state and final cloud state
         \ /
          M   verified merge result
```

The Git objects and refs live in a private Lift-owned bare repository outside the selected project. Each Lift Off creates an immutable session namespace. Example internal refs are:

```text
refs/lift/<workspace-id>/sessions/<session-id>/baseline
refs/lift/<workspace-id>/sessions/<session-id>/checkpoints/000001
refs/lift/<workspace-id>/sessions/<session-id>/checkpoints/000002
refs/lift/<workspace-id>/sessions/<session-id>/cloud-final
refs/lift/<workspace-id>/sessions/<session-id>/local-return
refs/lift/<workspace-id>/sessions/<session-id>/merge-result
refs/lift/<workspace-id>/sessions/<session-id>/land-receipt
```

These refs are implementation state, not branches in the user's repository, and are never pushed to a remote automatically.

### Capturing an uncommitted workspace

Lift must support dirty tracked files, staged files, untracked files, and explicitly approved ignored files without running `git add`, `git commit`, `git checkout`, or `git merge` against the user's real Git directory.

The helper:

1. creates or updates a private bare mirror of the repository history;
2. uses a Lift-owned temporary index pointed at the selected working directory;
3. seeds that index from the current repository `HEAD`;
4. adds included working-tree content to the private index, force-adding only ignored files the user explicitly approved;
5. writes synthetic baseline commit `B` into the private object database;
6. records the user's real index separately so staged-versus-unstaged intent is not silently rewritten.

The user's branch, refs, index, and working tree remain untouched.

### Cloud history

The Lift workspace starts from `B`. Every periodic checkpoint creates a new reachable commit in the session chain; it does not replace or orphan the preceding checkpoint. Real commits created by the user or agent remain in the history, and a synthetic checkpoint commit captures any additional dirty cloud state so `C` always represents the exact final tree.

### Return merge

When the helper returns, it captures current local state as synthetic commit `L`, with `B` as its merge base. Lift then checks out `L` into an isolated temporary worktree owned by the private repository and merges `C` there.

- A clean three-way merge produces result `M`.
- A conflicted merge remains entirely in the isolated worktree for review.
- Lift validates `M` against the content manifest and platform rules before touching the original folder.
- On a clean merge, Lift transactionally applies only `L -> M` to the original working tree. It does not create a commit or move the user's branch by default.
- The user's existing Git index is preserved. Cloud changes return as reviewable working-tree changes unless the user explicitly chooses a different behavior.

This is PR-like reconciliation without turning every Lift session into a public or remote branch.

## Durable session ledger

A successful clean merge seals a session; it never erases it. Lift retains the full private session ledger until the user explicitly deletes that session, workspace, or account under the documented deletion policy.

The ledger contains:

- immutable session ID, workspace ID, and timestamps;
- baseline commit and manifest;
- the complete cloud checkpoint commit chain;
- user or agent-created Git commits that are ancestors of the final checkpoint;
- final cloud commit and manifest;
- returning-local synthetic commit;
- merge-result commit, including a clean result;
- Land receipt containing the locally acknowledged revision;
- provider, connection-recipe, helper, runtime-image, and state-schema versions;
- supported provider session reference when officially portable;
- task goal and generated continuation summary when available;
- safe-to-close readiness evidence class;
- merge outcome, conflicts, recovery locations, and acknowledgement status.

The ledger does not require Lift to copy provider-owned conversations. Raw prompts, transcripts, approvals, and provider protocol state remain provider-owned unless an official export exists and the user explicitly enables retention.

Session history enables:

- a timeline of every Lift Off and Land;
- inspection of exactly what changed during one cloud session;
- restoration to any durable checkpoint;
- comparison between sessions;
- incident recovery and audit;
- optional future export as a sanitized branch or bundle.

Routine cleanup may remove temporary staging directories, completed operation journals after their recovery window, caches, and unreachable duplicate transfer objects. It must not garbage-collect commits, manifests, receipts, or metadata reachable from a retained session ledger.

## Optional GitHub integration

GitHub can become an optional review and collaboration surface later:

- publish a sanitized Lift session branch;
- open a pull request with the cloud diff;
- use GitHub checks and review;
- merge through the user's existing repository policy.

This requires an explicit connected GitHub account and per-session approval. A GitHub branch must never include approved ignored files, provider state, secrets, or other workspace-only content merely because the private Lift snapshot contains them. The default personal round trip remains local and works with no remote repository.

## Lift Off algorithm

1. Scan the selected folder and create candidate manifest `B`.
2. Apply established include and exclude rules and ask only about new exceptions.
3. Read and hash included content into a local staging snapshot.
4. Rescan paths that changed during capture; retry rather than uploading an inconsistent mixture.
5. Upload missing content-addressed objects and verify their hashes in the cloud.
6. Reconstruct the cloud workspace in staging and verify it against `B`.
7. Write synthetic commit `B` and record it as the common acknowledged revision in the private Lift repository.
8. Transfer the ownership lease to cloud.
9. Start the remote workload and continue the separate safe-to-close checks.

The local project is not modified during Lift Off.

## Cloud checkpointing

While cloud is primary, the state engine creates recoverable manifest revisions:

- after a quiet period following filesystem activity;
- before workspace stop or restart;
- before a risky lifecycle operation;
- when the user requests a snapshot;
- as a mandatory full scan during Land.

Filesystem events may identify dirty paths, but the final Land checkpoint must perform a complete manifest verification. Do not depend on an event stream alone.

## Land algorithm

1. Move the workspace to `LANDING` and reject new remote workload starts.
2. Gracefully pause or stop the provider process and declared development processes that may write the workspace.
3. Perform a complete cloud scan and create immutable manifest and checkpoint commit `C`.
4. Persist `C` and its required objects independently of running compute.
5. If the desktop helper is offline, stop compute if requested and leave Land pending.
6. When the helper reconnects, scan the original folder and write synthetic local commit `L` without touching the user's Git state.
7. Compute path-level changes for `B -> L` and `B -> C`, treating deletion, rename, type change, mode change, and content change explicitly.
8. Merge `C` into `L` in an isolated Lift worktree, producing clean result `M` or a preserved conflicted worktree, and verify every object hash.
9. Recheck affected local paths immediately before applying the result.
10. Apply or preserve changes according to the reconciliation rules below.
11. Verify the resulting local manifest and send an acknowledgement for `C`.
12. Write an immutable Land receipt, return ownership to local, and seal the complete session ledger. Clean merge history remains restorable.

## Reconciliation rules

### Local matches the baseline

Apply the entire `B -> C` delta automatically.

### Local and cloud changed different paths

Assemble and verify the combined result in staging. Apply it automatically only when the operations are independent. A delete on one side and a modification or child-path addition on the other is a conflict.

### Both changed the same path

Never choose a winner silently. Preserve:

- the untouched current local workspace;
- the final cloud revision;
- a proposed merge when a reliable three-way text merge is possible.

For a Git workspace, Lift keeps the conflicted merge in a clearly named isolated return worktree and presents a PR-like file and conflict view. For non-Git content and approved ignored files, use a sibling recovery directory. Binary, type-change, case-collision, and symlink conflicts always require review.

### Original local folder is missing

Keep Land pending and let the user reconnect the folder or choose a new destination. Do not create a replacement at an inferred path.

## Crash-safe local application

There is no portable atomic rename for a whole nonempty project directory. Lift therefore uses a transactional application:

1. Stage the complete delta on the same filesystem when possible.
2. Create a pre-apply recovery revision.
3. Write a durable operation journal.
4. Recheck the local precondition.
5. Replace individual files atomically and move deletions into recovery storage.
6. Preserve supported modes without following symbolic links.
7. Verify the final manifest.
8. Mark the journal complete and acknowledge the cloud revision.

After a crash, the helper reads the journal and deterministically finishes or restores the pre-apply revision. It never guesses from timestamps.

## User experience

The workspace card uses plain-language state:

```text
On this Mac
Lifting
Lifted - working in the cloud
Bringing changes back
Back on this Mac
Needs review - both copies were edited
```

If the user opens the original folder while it is cloud-primary, Lift shows:

> This workspace is still lifted.

The primary action is `Bring changes back`, which starts Land. If local divergence already exists, Lift says `Nothing was overwritten` and opens the preserved result for review.

## First-slice implementation boundary

Build:

- one Git workspace on macOS local and Ubuntu cloud;
- a Lift-private bare repository, private refs, and isolated merge worktree;
- tracked, uncommitted, untracked, and approved ignored files;
- versioned hash manifests and staged transfer;
- one local device and one cloud workspace;
- one-button Land with offline completion;
- recovery copy, journaled apply, and conflict preservation.

Defer:

- unrestricted continuous bidirectional sync;
- automatic GitHub branch pushes or pull requests;
- multiple local devices writing the same workspace;
- automatic semantic merge of complex conflicts;
- operating-system metadata beyond the explicitly supported subset;
- dependencies, caches, running processes, and provider credentials as file-sync content.

## Required tests

1. Dirty tracked and untracked files complete a no-conflict round trip.
2. Approved ignored files return without exposing unrelated ignored content.
3. File creation, deletion, rename, executable-bit change, and symbolic link round-trip correctly.
4. Land completes after being requested while the laptop is offline.
5. Local edits to a different file produce a verified combined result.
6. Local and cloud edits to the same file preserve both versions.
7. Delete-versus-modify and file-versus-directory changes become conflicts.
8. A crash during local application recovers without lost or duplicated content.
9. Case-insensitive path collisions are caught before application on macOS.
10. Binary and large-file changes verify by content hash.
11. Repeating Lift Off or Land after a network retry is idempotent.
12. No cloud revision is deleted before acknowledgement or another durable recovery copy exists.
13. Capture and return do not move the user's branch or mutate the user's real Git index.
14. Private Lift refs and explicitly approved ignored files are never pushed to a Git remote automatically.
15. A clean Land retains baseline, checkpoint chain, final cloud state, local return state, merge result, and acknowledgement receipt until explicit user deletion.

## Acceptance condition

The first slice passes when a user can Lift Off with an uncommitted project, change it through Codex while the laptop is off, choose Land, reopen the laptop, and see the exact verified result locally. A deliberate local conflict must preserve both copies and explain what happened without requiring Git expertise.
