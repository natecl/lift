# Workspace Handoff and Return Sync

Last updated: 2026-09-02

## Current implementation status

This document remains the authoritative complete Land design. The Phase 0 harness has proven an additive private checkpoint chain and exact restore for four cloud revisions on a generated disposable fixture. The current tree implements the fixture's distributed Land transaction as well as its local reconciliation engine: an EBS-authoritative writer fence, one immutable final `C`, exact versioned S3 durability and restore, private quarantine import, `L` capture, conservative `B/L/C` comparison, isolated return merge, journaled clean application with rollback, exact acknowledgement, lease return, conflict preservation, immutable session refs, and a Git-backed receipt.

The full local suite passes, and both a clean transaction and a deliberate same-file conflict ran live on generated founder fixtures on 2026-09-02. This is not yet the customer experience: Land still lacks a dashboard action, automatic helper reconnection, an explicit real-workspace manifest/review boundary, and conflict-resolution UI. Additional repetition and interruption evidence also remain pending. See [`CURRENT_STATE.md`](CURRENT_STATE.md) for the current observed evidence boundary.

## Implemented fixture transaction

The live-fixture controller exposes one resumable Land action, while two durable journals divide authority:

```text
controller: REQUESTED -> CLOUD_FROZEN -> FINAL_CHECKPOINT_DURABLE
            -> IMPORTED
                 |-- clean -> RECONCILED -> ACK_DURABLE -> COMPLETE
                 `-- conflict -> NEEDS_REVIEW
guest EBS:  CLOUD_PRIMARY -> FREEZE_REQUESTED -> CLOUD_FROZEN
            -> FINAL_CHECKPOINT_RECORDED
                          |-- matching clean acknowledgement -> ACKNOWLEDGED
                          `-- conflict -> remain FINAL_CHECKPOINT_RECORDED
```

The EBS record, not a cached controller flag, is authoritative for whether a cloud workload may start. The guest writes `FREEZE_REQUESTED` before it stops the runner. The runner holds the same lifecycle lock and rechecks that the guest lease is `CLOUD_PRIMARY` immediately before activation; every `LANDING` phase and the final `LOCAL_PRIMARY` acknowledgement reject a new cloud workload start.

One operation has one ordinal and one `land-final` checkpoint. After the writer is frozen, retries revalidate or reuse that `C`; they never recapture a newer tree. Its Git bundle and hash manifest retain the baseline, complete checkpoint chain, and captured cloud Git history. They are verified on EBS, stored in private versioned S3, downloaded by exact object version into a local recovery location, restore-tested, and then verified again in a private quarantine before only the declared absent-or-identical refs enter the local ledger.

A clean local result produces a canonical acknowledgement that binds exact `C`, both S3 version IDs, the final local manifest, merge result, and retained Land receipt. The guest must match that acknowledgement to its recorded checkpoint before the controller returns the lease to `LOCAL_PRIMARY`. A conflict stops at `NEEDS_REVIEW`: exact `C`, the untouched local state, and the conflict result remain recoverable, the lease stays `LANDING`, and cloud writers stay fenced. Default compute shutdown is strictly post-acknowledgement; `--keep-compute-running` may leave the instance running, but it does not restore cloud write authority.

If the controller or helper disappears after freeze begins, the EBS fence and any completed final checkpoint remain durable and rerunning the same operation resumes or revalidates its phase. The present CLI does not yet accept a Land request while the original helper is entirely offline or automatically wake that helper; that product orchestration remains future work.

The clean live observation used founder fixture run `p0-20260901083520-4fee`. It sealed `0004-land-final` as commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, and verified its exact versioned S3 bundle and manifest through restore. The first attempt stopped safely at controller phase `FINAL_CHECKPOINT_DURABLE` because a `/run` parent-directory mode check failed. After the permission fix, rerunning the operation reused that exact `C` and produced `APPLIED` merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, receipt commit `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and acknowledgement SHA-256 `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`. The guest reached `ACKNOWLEDGED`, the controller lease became `LOCAL_PRIMARY`, and compute stopped afterward.

The deliberate-conflict observation used fresh fixture run `p0-20260902183748-a7b1`. Both local and cloud changed `REMOTE_TEST.md` differently from the same baseline. Land sealed restore-tested `0002-land-final` as the immutable `C`, imported it through quarantine, and returned `NEEDS_REVIEW` with the lease still `LANDING`. The original local content, branch, index, refs, reflog, and manifest remained byte-for-byte unchanged; the isolated conflict worktree retained all three Git stages for `B`, `L`, and `C`; no acknowledgement, local application, ownership return, or compute cleanup occurred; and the cloud runner remained fenced. Repeating the same plain Land command returned `changed: false` and reused the exact operation evidence and recovery objects.

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
LOCAL_PRIMARY -> LIFTING -> CLOUD_PRIMARY -> LANDING
                                                |-- clean + acknowledged -> LOCAL_PRIMARY
                                                `-- conflict -> NEEDS_REVIEW
                                                    (lease remains LANDING)
```

- Local is primary before Lift Off.
- Cloud is primary after Lift Off reaches its durable handoff point.
- Land pauses cloud writers and creates a final immutable revision.
- Local becomes primary again only after the helper acknowledges a successful return.
- A conflict changes the controller phase to `NEEDS_REVIEW` but does not change the ownership lease out of `LANDING`.

Lift does not hard-lock the local directory. If the user edits it while lifted, Lift detects divergence and preserves both sides.

The ownership lease selects the authoritative **location**, not necessarily one process inside that location. The first slice runs one cloud agent. The north-star shared mode may run several agent tasks against the same directory while the workspace is `CLOUD_PRIMARY`; their task manager must checkpoint, attribute activity, detect overlapping writes, and fence every cloud writer before Land. Isolated and read-only modes provide stronger boundaries when requested. None of these modes permits unrestricted simultaneous local and cloud writing.

Future provider-owned cloud computers are execution participants, not additional workspace owners. Their task-scoped outputs must first enter the canonical Lift workspace through an attributable, checkpointed reconciliation that preserves the previous project state. Only a later return from that canonical workspace to a local computer uses `Land Workspace` and its `B/L/C` ownership transfer. Those integrations may reuse this document's hashing, quarantine, private-Git, and conflict-preservation primitives, but the current EBS guest journal is an implementation of the Lift-hosted first slice rather than a universal provider protocol. No external agent-computer gateway is implemented today.

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
- On a clean merge, Lift transactionally applies only `L -> M` to the original working tree. Each replaced original is first atomically renamed into private recovery and revalidated before the transaction is verified; a detected race fails closed and rolls the applied prefix back without overwriting the racing bytes. It does not create a commit or move the user's branch by default.
- The user's existing Git index is preserved. Cloud changes return as reviewable working-tree changes unless the user explicitly chooses a different behavior.

The current fixture core narrows but does not completely close the local-writer race: an already-open file descriptor can still modify a renamed inode after the final revalidation. The production helper must quiesce local writers or use an operating-system/filesystem snapshot boundary before applying to arbitrary workspaces.

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

1. Persist controller intent and move the workspace to `LANDING` before any recovery action could restart the workload.
2. On the encrypted workspace volume, write `FREEZE_REQUESTED` before gracefully stopping the provider and declared development processes that may write the workspace.
3. Under the shared lifecycle lock, verify runner inactivity and the absence of another declared workspace writer, then record `CLOUD_FROZEN`.
4. Perform a complete cloud scan and create the one next-ordinal immutable manifest and checkpoint commit `C`; no ordinary proof input is accepted for this `land-final` checkpoint.
5. Verify `C` on EBS, persist its required bundle and manifest as exact versioned S3 objects, independently restore-test them, and bind those identities into both journals.
6. If the desktop helper disconnects, keep the EBS fence and exact `C` pending. When it reconnects, reuse them rather than recapturing cloud state.
7. Download exact object versions outside the project, verify them in quarantine, and import only the declared recovery refs into the private local ledger.
8. Scan the original folder and write synthetic local commit `L` without touching the user's Git state.
9. Compute path-level changes for `B -> L` and `B -> C`, treating deletion, rename, type change, mode change, and content change explicitly.
10. Merge `C` into `L` in an isolated Lift worktree, producing clean result `M` or a preserved conflicted worktree, and verify every object hash.
11. Recheck affected local paths immediately before transactional application; on conflict, preserve every side and leave ownership in `LANDING`.
12. For an applied result, verify the final local manifest, persist the receipt and canonical acknowledgement for exact `C`, obtain the matching guest acknowledgement, return ownership to local, and seal the complete session ledger.
13. Only after ownership returns may Lift stop compute. A cleanup failure remains a retryable cost operation, not a reason to repeat reconciliation.

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

### Current evidence gate

Implementation and local tests cover the complete generated-fixture transaction, including write-intent ordering, strict runner gating, immutable checkpoint reuse, exact import, acknowledgement binding, clean application, and conflict preservation. The clean live E2E has verified the freeze, exact durable and imported `C`, local application, two-sided acknowledgement, lease return, and post-ack compute stop once. It also demonstrated fail-closed resume from `FINAL_CHECKPOINT_DURABLE` without recapturing `C`. A separate fresh live run verified the deliberate same-file conflict boundary once: exact `C` remained independently restorable, `B/L/C` remained recoverable, local state was untouched, the lease stayed `LANDING`, the runner stayed fenced, and an idempotent retry made no changes.

Fresh sessions must still repeat both clean and conflict outcomes and exercise additional phase interruptions and the offline-helper request/reconnect case. The conflict path also needs a user-facing resolution continuation. The capture boundary must then be replaced by an explicit reviewed manifest before one noncritical real workspace is attempted. Until those observations and product mechanisms exist, do not claim the complete product Land acceptance condition has passed.
