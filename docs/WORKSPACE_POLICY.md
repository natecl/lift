# Reviewed Workspace Policy

Last updated: 2026-09-02

## Current implementation status

This document defines the reviewed real-workspace policy boundary that must sit in front of Lift Off, cloud checkpoints, and Land.

The current implementation slice is deliberately local-only. [`workspace_policy.py`](../spikes/ec2-laptop-off/workspace_policy.py) inspects one physical Git worktree, produces a reviewable candidate, binds an explicit decision for every discovered path, compiles the approved paths into a deterministic effective policy, strictly decodes that portable policy, classifies a caller-supplied candidate under a trusted in-process assumption, and revalidates the resulting return plan against that same supplied candidate. Its focused test module passes 77 tests.

This is a policy foundation, not a transfer implementation. It does not yet build or upload a generic baseline `B`, reconstruct an arbitrary real workspace on EC2, apply the policy inside the guest checkpoint path, import a policy-bound final `C`, capture policy-bound `L`, or carry the policy through merge, receipt, acknowledgement, and lease return. None of the live fixture evidence exercised this module.

The generated disposable fixture remains the only workspace accepted by the live EC2 harness. Its marker-based policy and its existing clean and deliberate-conflict evidence remain a compatibility adapter, not permission to relax the real-workspace boundary.

Until the later integration stages in this document are implemented and verified:

- no real project should be sent through the fixture `lift-off` command;
- no compiled initial path list should be treated as the permanent cloud or return allowlist;
- no UI should claim that reviewed real-workspace Lift Off is available;
- the existing fixture safety claims remain narrower than the product contract.

## Product contract

Lift moves a selected project, not a laptop and not a home directory. The user chooses one workspace, sees what Lift proposes to move, explicitly approves any ignored or sensitive state, and receives a durable policy-bound handoff.

The intended experience remains:

> Click `Lift Off`, wait for `Safe to close`, close the laptop, continue from the provider's existing phone application, and later choose `Land Workspace` to bring the work back.

That simple experience depends on a strict internal rule: discovery is not transfer permission. Finding a path never authorizes Lift to copy it.

The policy boundary must preserve these product constraints:

- the selected workspace is a physical directory and one exact Git worktree root;
- paths outside that root remain default-deny;
- Git administration state, keychains, SSH private keys, password stores, browser cookie databases, and equivalent private device state are hard-excluded;
- ignored and sensitive files require an explicit decision before the initial transfer;
- a later agent-created ordinary source file can return even though it did not exist at Lift Off;
- a later sensitive, newly ignored, unsafe, or unsupported path never becomes returnable merely because an agent ran `git add -f`;
- a policy mismatch at any boundary fails closed;
- the user's branch, refs, real index, and working tree are not changed by discovery or capture;
- a clean Land never erases the private `B/C/L/M` session history or its receipt.

## Model

The reviewed policy flow is:

```text
physical worktree
      |
      | read-only discovery
      v
CandidateManifestV1
      |
      | one explicit decision per candidate path
      v
ApprovalV1
      |
      | deterministic compilation
      v
EffectivePolicyV1
      |
      | trusted local classification of one supplied candidate
      v
ReturnPlanV1
      |
      | future policy-bound capture integration
      v
 B / checkpoint / C / L / M / receipt
```

Every arrow through `ReturnPlanV1` exists locally. The final capture arrow is the next integration boundary. Lift must eventually recompute the relevant digest at both sides of every trust boundary and reject missing, mixed, stale, or changed inputs.

## Candidate manifest

`CandidateManifestV1` is local-only evidence. It describes what exists and why each path was classified, but it grants no permission to transfer content.

The candidate binds:

- the canonical physical workspace root;
- root and `.git` filesystem identities;
- current `HEAD` and branch identity;
- hashes of the real Git index, refs listing, and privately copied standard excludes sources;
- a canonical UTF-8 byte-order-sorted path set with normalization/case-collision rejection;
- supported content hashes, sizes, executable state, and safe symbolic-link targets;
- Git state such as tracked, staged, dirty, untracked, and ignored;
- sensitive, hard-excluded, and unsupported classifications;
- one digest over the complete canonical candidate.

Candidate categories are descriptive and may overlap. For example, a force-added `.env` can be both `tracked` and `sensitive`. Security categories take precedence over Git categories.

The user-facing dispositions are:

- `will-move`: ordinary supported project state selected by the conservative default;
- `needs-approval`: ignored or sensitive state that can move only after an explicit include decision;
- `stays-local`: hard-excluded or unsupported state that approval cannot override.

Hard-excluded entries must not expose their content hash, size, target, or bytes in the portable policy. The candidate itself remains on the user's Mac.

Discovery performs no Git write operation against the user's repository. It rejects the account home and workspace roots beneath protected account-private components. It uses a private index copy; invokes a validated root-owned absolute system Git with a minimal environment independent of ambient `PATH`, `HOME`, loader variables, and Git selectors; privately copies, bounds, hashes, and explicitly applies configured standard excludes sources plus the implicit default or validated custom-XDG global ignore, then reopens every live source through an anchored component-wise no-follow walk and verifies its exact inode, metadata, and content digest; derives dirty state by comparing physical Git blob identities and modes with the index copy rather than invoking `git diff`; treats force-added ignored paths as ignored even when tracked; rejects detached, unborn, sparse, linked, nested-repository (including nested bare repository), gitlink, split-index, skip-worktree, assume-unchanged, partial/promisor, alternate-object-storage, and externally configured Git-filter cases; enforces entry and byte bounds; fails closed when the host mount table cannot be inspected; rejects identifiable network and nested filesystems; walks without following links; hashes and scans the full byte stream of regular files through file descriptors; verifies the opened root identity; and rechecks workspace, Git, excludes-source, mount, and file identity around inspection. Safe links must resolve, without escaping, to a dependency chain of reconstructable approved regular files or links. The capture integration must still perform fresh discovery and byte-bound reconstruction checks rather than treating a previously serialized candidate as proof of current filesystem completeness.

## Exact local v1 wire contracts

The wire examples below match the current `to_dict()` output exactly. Optional entry fields are shown where applicable. All self-hashes use Lift's canonical UTF-8 JSON encoding: keys sorted, no insignificant whitespace, and the self-hash field omitted from the hashed object.

`CandidateManifestV1.to_dict()` emits:

```json
{
  "candidateSha256": "<sha256>",
  "entries": [
    {
      "categories": ["tracked", "dirty"],
      "disposition": "will-move",
      "executable": false,
      "kind": "file",
      "path": "src/app.py",
      "sha256": "<sha256>",
      "size": 123
    }
  ],
  "kind": "lift-candidate-manifest",
  "schemaVersion": 1,
  "workspaceIdentity": {
    "branch": "main",
      "gitDevice": 1,
      "gitInode": 2,
      "head": "<40-hex-object-id>",
      "excludesSha256": "<sha256>",
      "indexSha256": "<sha256>",
    "refsSha256": "<sha256>",
    "rootDevice": 1,
    "rootInode": 3
  }
}
```

Candidate `kind` values are `file`, `symlink`, `absent`, `directory`, `excluded`, or `unsupported`; only transferable files, safe symlinks, and tracked tombstones can enter an effective policy. A symlink adds `linkTarget`. A locally excluded entry adds `unsupportedReason` and omits `sha256`, `size`, and `linkTarget`. The internal canonical root `Path` is intentionally not serialized.

`ApprovalV1.to_dict()` emits:

```json
{
  "approvalSha256": "<sha256>",
  "candidateSha256": "<sha256>",
  "decisions": [
    {"action": "include", "path": "src/app.py"}
  ],
  "kind": "lift-workspace-approval",
  "schemaVersion": 1,
  "scope": {
    "helperVersion": "workspace-policy-v1",
    "runId": "run-123",
    "workspaceId": "workspace-123"
  }
}
```

The only approval actions are `include` and `exclude`. The decision array is canonical and must cover the candidate path set exactly once.

## Approval

`ApprovalV1` binds an `include` or `exclude` action to every candidate path and to one exact candidate digest.

Approval rules are:

- every candidate path is decided exactly once;
- extra and missing decisions are invalid;
- hard-excluded and unsupported paths cannot be included;
- ignored and sensitive paths are excluded by default and move only after an explicit include decision;
- approval becomes stale when the candidate digest changes;
- compiling the same candidate and approval must produce the same policy digest.

Approval is not an evergreen permission for a pathname. It authorizes the exact initial bytes and metadata represented by the candidate. A changed file requires a new candidate and approval before Lift Off.

## Effective workspace policy

`EffectivePolicyV1` is the current portable, immutable result of candidate review. Its exact wire shape is:

```json
{
  "approvalSha256": "<sha256>",
  "candidateSha256": "<sha256>",
  "initialTransferEntries": [
    {
      "categories": ["tracked", "dirty"],
      "executable": false,
      "kind": "file",
      "path": "src/app.py",
      "sha256": "<sha256>",
      "size": 123
    }
  ],
  "kind": "lift-effective-workspace-policy",
  "policySha256": "<sha256>",
  "returnPolicy": {
    "classifierVersion": "workspace-policy-classifier-v1",
    "existingApprovedPaths": "allow",
    "hardExcludedPaths": "block",
    "newIgnoredPaths": "needs-review",
    "newOrdinaryPaths": "allow",
    "newSensitivePaths": "needs-review",
    "ruleset": "lift-return-v1",
    "specialFiles": "block",
    "unsafeLinks": "block"
  },
  "schemaVersion": 1,
  "scope": {
    "helperVersion": "workspace-policy-v1",
    "runId": "run-123",
    "workspaceId": "workspace-123"
  },
  "workspaceIdentitySha256": "<sha256>"
}
```

`policySha256` is the SHA-256 digest of the canonical object without the `policySha256` field. The classifier version, ruleset, helper version, run, and workspace scope are inside that digest because changing classification behavior or operation identity changes the meaning of the user's approval. `effective_policy_from_dict()` rejects unknown, missing, mistyped, noncanonical, colliding, or self-hash-invalid policy data.

The portable policy contains approved initial entries, not rejected-path metadata or secret bytes. The full candidate and approval may remain in private local evidence for review and recovery.

When the integration exists, changing the policy after B exists must create a new session. Lift must never mutate the policy attached to an existing immutable baseline.

## Initial transfer and return are different decisions

The initial transfer is an exact approved set. The return path is a fresh classification under durable rules.

This distinction prevents a subtle but severe bug:

```text
incorrect: paths allowed at C or L = paths that existed and were approved at B
correct:   paths allowed at C or L = every current path classified by return rules
```

If the initial path set were reused as the permanent allowlist, an agent-created `src/new-feature.ts` would silently disappear from checkpoints and Land because it did not exist at Lift Off.

Return classification uses this precedence:

```text
BLOCK > NEEDS_REVIEW > ALLOW
```

The first generic policy uses these semantics:

- an existing baseline-approved path remains eligible when modified or deleted;
- a new ordinary tracked path is included;
- a new ordinary nonignored untracked path is included;
- a new ignored path requires review;
- a new sensitive path requires review, even when tracked or force-added;
- an absent path that was not initially approved is an unknown tombstone and blocks capture;
- a hard-excluded path or unsupported type blocks capture;
- a symbolic link is supported only when its lexical and resolved target stay inside the workspace and outside Git administration state;
- case- or Unicode-colliding paths block automatic return to a case-insensitive local filesystem.

Git tracked status is evidence about repository state, not evidence that a path is safe. `git add -f .env` must never bypass the sensitive-path rule.

## Return plan

The current local foundation classifies a caller-supplied `CandidateManifestV1` with `classify_return_snapshot()` and emits this exact `ReturnPlanV1` wire shape. Its API name and type express the intended complete-snapshot contract; the current function does not authenticate that provenance or completeness:

```json
{
  "classifierVersion": "workspace-policy-classifier-v1",
  "decisions": [
    {
      "action": "ALLOW",
      "path": "src/new-feature.ts",
      "reason": "new-ordinary-path"
    }
  ],
  "kind": "lift-return-plan",
  "overallDisposition": "ALLOW",
  "planSha256": "<sha256>",
  "policySha256": "<sha256>",
  "role": "cloud-return",
  "schemaVersion": 1,
  "selectedAllowedEntries": [
    {
      "categories": ["untracked"],
      "executable": false,
      "kind": "file",
      "path": "src/new-feature.ts",
      "sha256": "<sha256>",
      "size": 123
    }
  ],
  "snapshotSha256": "<candidate-sha256>"
}
```

Decision actions are exactly `ALLOW`, `NEEDS_REVIEW`, and `BLOCK`. Decision reasons are exactly `approved-initial-path`, `new-ordinary-path`, `new-sensitive-or-ignored-path`, `prohibited-or-unsupported-path`, and `unknown-tombstone`. `overallDisposition` takes the most restrictive action. Findings contain only path, action, and reason; allowed entries carry the approved content identity and metadata.

`validate_return_plan()` validates the plan's structure and self-hash, then recomputes the plan from the supplied policy and snapshot. It rejects a forged plan that merely carries a valid new self-hash. It does not itself scan a filesystem, authenticate who produced the snapshot, or prove that the supplied path set is complete. A malicious caller can omit a physical path, recompute a structurally valid candidate hash, and obtain a plan for only the remaining entries.

The current classifier is therefore trusted local/in-process policy logic only. Before any portable checkpoint or Land use, integration must require an authenticated scanner-produced complete physical snapshot bound to the exact `policySha256`, approval scope (`runId`, `workspaceId`, and `helperVersion`), intended capture role, and scanner/classifier version. The producer and consumer must bind captured bytes to that same snapshot and recheck around private tree construction. A bare self-hashed candidate crossing from the guest is not authority.

The current role is only `cloud-return`; a generic baseline, checkpoint, and returning-local capture planner are not implemented. When they are added, the plan must be recomputed around private tree construction, and the before/after plan and tree identities must match. Reusing an earlier path list for both checks is insufficient because a workspace can change between discovery and capture.

## Future snapshot and receipt binding

The following is the required integration contract, not current implementation evidence. The same immutable policy identity must cross every future trust boundary.

| Artifact | Required policy evidence |
|---|---|
| Baseline `B` manifest | `workspacePolicySha256`, role, tree, commit, and manifest self-hash |
| Baseline `B` commit | strict policy-hash commit trailer |
| Lift Off `session.json` | complete `EffectivePolicyV1` and matching hash |
| Guest reconstruction state | complete policy, matching hash, B ref and commit |
| Cloud checkpoint manifest | policy hash, checkpoint identity, tree, parents, entries, and manifest self-hash |
| Cloud checkpoint record | policy hash and exact manifest/bundle identities |
| Imported final `C` record | locally expected policy hash and verified remote policy hash |
| Returning-local `L` manifest and commit | policy hash and fresh local snapshot identity |
| Merge record and apply journal | policy hash plus exact `B/L/C/M` commits |
| Land result | policy hash, outcome, refs, and receipt identity |
| Git-backed Land receipt | policy hash plus exact `B/L/C/M` commits |
| Final local manifest | policy hash and exact received tree |
| Two-sided acknowledgement | policy hash, exact S3 versions, `C`, local result, receipt, and final manifest |

Generic policy-backed artifacts should use a new schema version and must not be accepted as fixture artifacts. Fixture schema-v1 records retain `fixturePolicy`. Generic records use `workspacePolicySha256`. The two forms are mutually exclusive.

Commit messages for policy-backed synthetic commits should contain a strict trailer such as:

```text
Lift-Workspace-Policy-SHA256: <64 lowercase hexadecimal characters>
```

The policy does not belong in the user-visible project tree. When integration is implemented, the full portable policy can travel inside nonsecret session metadata; the immutable commit trailer and manifest hash must bind it to the private ledger.

## Fail-closed outcomes

### Stale local approval

If the workspace, Git index, `HEAD`, refs, or approved content changes after review, Lift invalidates the candidate. Nothing uploads. The user reviews a fresh candidate.

### Policy mismatch after integration

When these artifacts exist, a differing policy hash among session metadata, B, reconstruction state, a checkpoint, C, L, a result, or a receipt must stop processing before publishing refs or touching the original workspace. The current local module validates only its candidate, approval, effective policy, snapshot, and return plan.

### Cloud review finding after integration

If the cloud contains a new ignored or sensitive path, the future integration must not silently omit it or upload its bytes as part of a partial final C. Land must remain in `NEEDS_REVIEW`, the workspace ownership lease must remain `LANDING`, cloud writers must remain fenced, and the encrypted EBS workspace must remain authoritative until the user resolves or explicitly approves the finding.

A review report may contain the path, category, reason, and requested action. It must not contain the file contents. No acknowledgement, ownership return, or compute shutdown follows a policy review hold.

### Unsafe or unsupported cloud state

An escaping symlink, nested Git administration path, unsupported filesystem node, unreadable path, or observed identity race blocks local discovery today. The future cloud capture path must retain the durable workspace and report the blocked path without pretending an exact C exists.

### Returning-local review finding

If the local workspace changed while cloud was primary and now contains sensitive or unsafe state that cannot enter L, the future policy-aware Land path must leave the local workspace untouched and stop before automatic merge or application. A previously durable C must remain recoverable.

### Merge conflict

When valid B, L, and C exist but cannot merge safely, Land uses the existing `NEEDS_REVIEW` behavior: preserve both sides, retain the isolated conflict evidence, keep the lease at `LANDING`, and create no acknowledgement or cleanup.

### Clean result

Only a policy-consistent, exact, clean M can enter the journaled local apply. Lift verifies the final local manifest, persists the Git-backed receipt and matching acknowledgement, returns ownership to `LOCAL_PRIMARY`, and only then may stop compute.

## Git-history boundary

Private Git objects are workspace content. Selecting current paths does not implicitly authorize all objects reachable from the user's existing refs and reflogs.

The fixture implementation currently:

- fetches the fixture's original `HEAD` into the private ledger;
- imports local refs and reflog objects for L;
- imports cloud refs and reflog objects for checkpoints;
- may attach actual local or cloud commits as additional synthetic parents.

That is acceptable only for the generated disposable fixture. A real repository's historical objects may contain deleted credentials or files that are absent from the reviewed current manifest. Filtering B's visible tree does not remove those historical blobs from a Git bundle.

The first real-workspace integration therefore preserves Lift's own private snapshot history:

```text
B -> checkpoint 1 -> checkpoint 2 -> C
 \-> L ---------------------------> M
```

It records the source `HEAD`, branch, index hash, and refs hash as local identity metadata but does not automatically upload arbitrary user refs, reflogs, or their reachable object graph. Generic B is a synthetic snapshot root; generic checkpoints chain from Lift checkpoints; L descends from B; and M has L and C as parents.

Preserving native repository history later requires a separate explicit decision and a design that validates or sanitizes every reachable transferred object. It cannot be inferred from path approval. GitHub publication remains a separate, explicit, sanitized integration.

## Fixture compatibility

The marker-gated fixture is retained as a separate adapter while the reviewed path is integrated.

- Existing fixture functions and schema-v1 artifacts remain valid.
- Existing immutable fixture refs, checkpoints, results, and receipts are never rewritten.
- The legacy reconstruction-state fixture-policy backfill remains fixture-only.
- A generic operation cannot accept a `fixturePolicy` in place of a workspace policy.
- A fixture operation cannot accept a generic policy hash in place of its marker policy.
- A runtime release may support both adapters, but each session selects exactly one at reconstruction.

This allows the proven live fixture lifecycle to remain regression coverage without weakening its marker guard or misrepresenting it as arbitrary-project support.

## Staged integration order

### Stage 0: local policy foundation — current slice

- Discover exactly one physical Git worktree.
- Produce deterministic candidate categories and dispositions.
- Bind one decision to every candidate path.
- Compile a portable approved policy.
- Revalidate candidate drift and preserve Git state.
- Classify caller-supplied return candidates under immutable rules, independently of the initial path set, for trusted local/in-process use only.
- Reclassify return plans during validation and cover new ordinary, ignored, sensitive, prohibited, and tombstone paths.

No transfer occurs in this stage. The focused suite passes 77 tests; local verification does not constitute live-loop evidence.

### Stage 1: policy-bound B and reconstruction

- Add generic capture entry points beside the fixture functions.
- Capture only approved initial entries with a private index.
- Create policy-bound synthetic B without importing arbitrary repository history.
- Put the policy in schema-v2 session metadata.
- Validate the policy, B, and manifest during guest reconstruction.
- Persist the full policy and hash in schema-v2 reconstruction state.

Acceptance boundary: one noncritical real Git workspace reconstructs locally or in an isolated guest test without changing its real Git state and without transferring an excluded byte.

### Stage 2: policy-bound cloud checkpoints and C

- Package the shared policy validator with the guest runtime.
- Re-scan the complete cloud workspace for every checkpoint.
- Include safe new tracked and untracked files.
- Produce review holds for new ignored or sensitive paths.
- Put the policy hash in every checkpoint commit, manifest, and record.
- Preserve the complete Lift checkpoint chain and exact recovery objects.

Acceptance boundary: a newly created ordinary source file appears in a restored checkpoint, while a newly force-added `.env` cannot appear in a transferable checkpoint.

### Stage 3: policy-aware Land

- Verify the policy before importing final C refs.
- Capture L under the same return rules.
- Carry the policy into merge records, journals, results, receipts, and acknowledgement.
- Stop before merge/application on a policy finding.
- Reuse the proven journal, rollback, race detection, writer fence, and acknowledgement ordering.

Acceptance boundary: one clean and one deliberate-conflict real-workspace round trip preserve the user's branch, refs, index, local work, B/C/L evidence, and receipt.

### Stage 4: product orchestration

- Add folder selection, grouped review, approval, progress, `Safe to close`, and `Land Workspace` surfaces.
- Keep the supported happy path free of terminals, SSH, copied tokens, and cloud consoles.
- Explain review findings in project language rather than Git internals.
- Resume a pending Land automatically when the desktop helper reconnects.

### Stage 5: live promotion evidence

- Repeat clean and conflicted runs from fresh sessions.
- Interrupt after approval, B capture, reconstruction, freeze, durable C, import, local application, and acknowledgement.
- Verify stable hashes, idempotent retries, unchanged user Git administration state, no excluded content, and no premature compute stop.
- Promote the capability only after security, credential isolation, provider compatibility, and zero-terminal experience gates pass.

## Regression coverage

The 77 focused local tests cover discovery and Git-state preservation; raw physical-content/index comparison without `git diff`; exact candidate approval; full-stream secret scanning; sensitive databases and credential filenames; ignored, force-added ignored, explicitly configured global-ignored, default XDG-global-ignored, and custom-XDG-global-ignored paths; global-ignore ancestor-swap rejection; hard-excluded credential and browser stores; trusted Git, home resolution, and protected account-root rejection; unsupported, link, mount-table, nested-mount, root-swap, path, and byte-limit cases; partial/promisor and alternate-object-store rejection; nested bare repositories; symlink dependency closure; candidate drift; strict canonical effective-policy decoding; modifications and tombstones for initially approved paths; new ordinary, ignored, sensitive, prohibited, and unsupported return paths; content/mode/type binding; and forged return-plan rejection.

The integration remains incomplete until tests additionally prove:

1. A new safe cloud-created tracked file enters a restored checkpoint and returns through Land.
2. A new safe cloud-created untracked file enters a restored checkpoint and returns through Land.
3. A baseline-approved ignored or sensitive file can be modified and returned end to end.
4. New ignored or sensitive state stops checkpoint/Land before a partial C, acknowledgement, lease return, or cleanup.
5. Hard exclusions never enter B, a checkpoint, C, L, M, a bundle, or a receipt.
6. A policy mismatch at every artifact boundary fails before ref publication or local mutation.
7. Generic bundles contain no arbitrary local refs, reflogs, ancestry, or unapproved historical blobs.
8. The real branch, refs, index, and working tree remain unchanged during generic capture.
9. A clean Land retains B, every checkpoint, C, L, M, and the receipt.
10. Every existing fixture test continues to pass through the fixture adapter.

## Not included in the current slice

- uploading or reconstructing a real project;
- changing the live fixture `lift-off` command;
- dashboard or folder-picker UI;
- resolving a return-policy finding;
- native repository-history migration;
- GitHub branch or pull-request publication;
- secrets injection or provider credential transport;
- automatic offline-helper continuation;
- a launch claim for arbitrary customer workspaces.

The immediate result is a trustworthy policy primitive. The next implementation step is to bind that primitive to B and reconstruction without weakening the existing fixture path.
