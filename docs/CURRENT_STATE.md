# Current State

Last verified: 2026-09-02

Repository baseline before the Land change set: merge commit `45eef0e2f668dceba84a1c0e0bd1404ce5305a95`, which includes the Phase 0 provider-evidence merge `b61bb9b42e3a36809d7947c1055e524da55954b5`
Land implementation baseline: the crash-safe fixture core begins at commit `ccceea7`; this change set adds the live controller, guest, tests, evidence, and knowledge-base reconciliation
Product phase: provider-path feasibility and the generated-fixture Land core—one clean return plus one deliberate conflict—passed live once each; a reviewed real-workspace policy foundation now passes locally, but generic capture, upload, and the real-workspace product loop are not yet implemented

This is the canonical short-to-medium-term memory for Lift. It answers four questions: what exists, what was actually observed, what was learned, and what should be built next. Detailed protocol evidence remains in [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md).

## Executive snapshot

- Lift's product north star is the persistent, project-centric cloud workspace where developers and user-chosen AI agents work together from any device. It remains infrastructure for existing agents, not a proprietary coding agent, phone chat, IDE, or Git host.
- The first wedge remains one active Mac coding workspace moved to one persistent Linux cloud workspace, controlled from the provider application the user already has. The complete target includes launching a completely new provider-native task from the phone after the laptop is offline, not only continuing a process started locally.
- The future workspace may originate locally, from GitHub, or empty; support shared, isolated, and read-only multi-agent tasks; add internet/browser/computer capabilities; and later add small-team participation. None of those broader capabilities is implemented by the current Phase 0 harness.
- The Codex-first provider path has passed once on a real Ubuntu EC2 instance with encrypted EBS: direct phone control, strongly corroborated laptop-off work, EC2 stop/start recovery, exact post-restart folder binding, a guarded approval/proof turn, an immutable following checkpoint, exact-version S3 restore, and a fresh `safeToClose: true` evaluation.
- The provider spike and its earlier evidence were merged through [PR #3](https://github.com/natecl/lift/pull/3), and the earlier consolidated product context was merged through [PR #4](https://github.com/natecl/lift/pull/4). The Land change set builds on crash-safe fixture-core commit `ccceea7` and includes the live controller/guest integration plus the current knowledge-base reconciliation. The current complete Python verification baseline is 277 passing tests plus passing Ruff, Python compilation, and diff checks. The separate local real-workspace policy module accounts for 77 focused tests. GitHub had no hosted status checks configured for the earlier PRs.
- The validated live capture path is still deliberately restricted to a generated disposable fixture. A new local-only foundation can discover one real Git worktree, bind exact per-path approval, compile and strictly decode a portable policy, classify paths in a caller-supplied candidate under a trusted in-process assumption, and revalidate a return plan against that same candidate. It does not authenticate scanner provenance or prove a supplied candidate is complete, upload or reconstruct a real project, or wire policy into baseline `B`, guest checkpoints, final `C`, `L`, merge, receipt, or acknowledgement.
- There is no product dashboard or signed desktop helper yet. Authentication, pairing, and proof still required founder-operated terminal steps.
- The fixture Land core has passed both outcomes once on live EC2/EBS/S3. The clean run froze one restore-tested final `C`, imported and applied it locally, durably acknowledged it, returned ownership, and stopped compute. A separate fresh conflict run preserved exact `B/L/C`, left the original local and Git state untouched, retained `LANDING`, fenced cloud writers, and changed nothing on retry. Automatic offline-helper continuation, conflict resolution, repeated runs, and additional interruption phases remain pending.
- Codex direct Remote remains experimental and founder-only. One passing run is evidence of feasibility, not provider support, repeatability, external-alpha safety, or market demand.

## What is now implemented

### Phase 0 runtime harness

The current spike tree under [`spikes/ec2-laptop-off/`](../spikes/ec2-laptop-off/) can:

- provision one isolated Ubuntu EC2 instance and a separate encrypted EBS workspace volume through CloudFormation;
- administer the instance without public ingress through AWS Systems Manager;
- reconstruct a generated Git fixture in the real provider-visible path `/home/lift/workspaces/lift-ec2-spike`;
- run a reviewed provider-neutral workload recipe through a generic detached process supervisor;
- install, authenticate, start, prepare, inspect, and recover the experimental Codex Remote workload through recipe-scoped code;
- distinguish generic process liveness from provider semantic readiness and end-to-end phone readiness;
- stop and start the instance while preserving the exact EBS workspace, checkpoint chain, and provider Remote environment;
- create immutable Lift-private Git checkpoint commits without moving the user's branch, refs, or real index;
- package checkpoint bundles and manifests into versioned private S3 objects;
- download exact object versions into a fresh location and verify bundle hashes, manifest hashes, Git commit, tree, retained history refs, file count, and evidence bytes;
- bind persisted local routing state back to the exact live CloudFormation stack, resource types, physical resource IDs, AMI owner and architecture, AWS account, principal ARN, and immutable STS user ID before acting;
- derive a short-lived safe-to-close verdict only after every required durability, runtime, provider, phone, approval, checkpoint, and auto-stop gate passes.

### Local reviewed real-workspace policy foundation

[`workspace_policy.py`](../spikes/ec2-laptop-off/workspace_policy.py) now implements the local policy primitive that must precede any real-project transfer:

- `discover_workspace()` inspects exactly one supported physical Git worktree without changing its branch, refs, index, or working tree;
- `CandidateManifestV1` classifies canonical paths across `tracked`, `staged`, `dirty`, `untracked`, `ignored`, `sensitive`, `hard-excluded`, and `unsupported`, with content identities only for transferable entries;
- `ApprovalV1` binds one `include` or `exclude` decision for every candidate path to the exact candidate plus run, workspace, and helper scope;
- `EffectivePolicyV1` contains only approved initial entries plus the immutable `lift-return-v1` rules, and its untrusted dictionary decoder is strict;
- `ReturnPlanV1` distinguishes the exact initial-transfer entries from later rule-based return classification, so a supplied ordinary agent-created file is allowed while a supplied new ignored or sensitive file requires review and supplied unsafe or unsupported state blocks;
- plan validation reclassifies the caller-supplied snapshot instead of accepting a newly self-hashed decision list, but does not prove that snapshot came from the scanner or includes every physical path.

The focused suite in [`test_workspace_policy.py`](../spikes/ec2-laptop-off/tests/test_workspace_policy.py) passes 77 tests covering Git and filesystem classification, exact approval, hard exclusions including credential and browser stores, full-stream secret-content detection, database and credential filename classification, configured, default, and custom-XDG account-global-ignore copying, binding, and ancestor-swap rejection, trusted Git execution, OS-derived home and protected-account-root protection, raw physical-content/index comparison without `git diff`, drift, path and size bounds, mount-table failure and identifiable mounts, root-swap rejection, safe-link dependency closure, partial/promisor/alternate object-store rejection, nested repositories including bare repositories, force-added ignored files, strict canonical policy decoding, new-file return behavior, tracked tombstones, and forged-plan rejection.

This module is deliberately free of transfer, ledger, cloud, checkpoint, and Land dependencies. Its candidate and approval remain local; only the compiled effective policy is intended to cross the future trust boundary. The generated fixture continues to use its existing marker adapter, and no live evidence yet exercises the generic policy. See [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md) for the exact schema and integration boundary.

### Provider-neutral execution boundary

The core supervisor does not contain `pairCodex`, `resumeClaude`, conversation transport, provider chat, or provider approval UI. It executes one reviewed process recipe with separate executable and arguments, working directory, approved persistent paths, health, readiness, restart, and resource declarations.

Codex-specific behavior is isolated to the experimental connection recipe and connector. This implements and preserves the intended architectural boundary: a future Claude or other remote-capable agent should add a recipe and compatibility test rather than a second workspace/runtime implementation. A second provider or genuinely unrelated remote-capable CLI is still required to validate that the abstraction is neutral in practice.

### Codex semantic-readiness repair

The first EC2 restart exposed a critical false positive. The Codex daemon was healthy and the Remote environment survived, but the native project registry was empty. New phone tasks therefore opened synthetic projectless directories outside Lift's narrow writable workspace. Older tasks also entered an approval loop in which no useful approval control appeared; the exact cause of that second symptom is not proven.

The repair now:

1. uses the version-pinned local App Server API through its Unix-domain socket;
2. idempotently creates or reads the exact server-side native project and root without depending on transient Remote connectivity or a controller;
3. keeps the nonsecret connector record outside the project tree;
4. reads the registered project back;
5. checks Remote and paired-controller prerequisites separately;
6. treats any semantic mismatch as `DEGRADED` rather than restarting an otherwise healthy daemon;
7. still requires a brand-new phone task and exact runtime-root evidence before safe-to-close.

This is the reason the initial phone attempt worked, the post-restart attempt failed, and the repaired attempt worked: process persistence and workspace continuity were real, but provider-owned semantic state needed explicit reconstruction and verification.

### Mobile folder behavior

The tested phone picker did not expose the separately registered server project. It showed `Chat` and `Add new folder`. Selecting the exact Lift workspace created a phone task with:

- the correct canonical `cwd`;
- the correct resume-time runtime root;
- `projectId: null`.

Lift therefore models the observed compatibility path as `folder-bound-project-unassigned`. It must not describe this as verified controller-side project visibility or project assignment. Server project registration, paired-controller presence, phone folder selection, and a correctly bound fresh task are four separate facts.

### Approval and proof evidence

The successful post-restart task used one canonically hashed challenge and exactly two expected agent-originated commands:

1. a network-disabled approval canary under exact `on-request` and user-review settings;
2. the independently reconstructed proof write inside the exact workspace.

A root-owned passive observer subscribed before the phone task and stayed through the request, matching resolution, both command lifecycles, and turn completion. A separate historical verifier then re-read the completed task and independently checked the exact command envelope, order, provenance, sandbox, policy, reviewer, workspace, thread, turn, and absence of extra tools or mutations. Both results, the policy/config/plugin guard, the phone proof, and the following checkpoint share one challenge digest.

Two protocol details mattered:

- the source-authentic nested approval-decision field is `execpolicy_amendment`, not `execpolicyAmendment`;
- the approval request execution environment is the exact string `local`, which is distinct from the Codex Remote environment ID.

The public provider protocol does not expose the selected decision or responder connection identity to the passive observer. `availableDecisions` is a presentation hint, not a server-enforced allowlist. The evidence therefore supports the guarded inference `request observed -> request resolved -> exact command succeeded` while using the founder-controlled official client. It does not cryptographically prove that a particular person or phone tapped a particular approval decision.

### Durable checkpoint chain and clean Land

The founder run retains four immutable Lift-private checkpoints:

| Ordinal | Label | Purpose | Restore result |
| --- | --- | --- | --- |
| `0001` | `phone-proof` | First direct phone workspace proof | Exact versioned bundle and manifest restored successfully |
| `0002` | `laptop-off-proof` | Challenge/proof created while the laptop-off sequence was being tested | Exact versioned bundle and manifest restored successfully and survived EC2 stop/start |
| `0003` | `post-restart-phone-proof` | Fresh phone binding, guarded approval, and proof after restart | Commit `674bd2722b961caf1e91db98f582330b6b4a54b5`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, and 12 files restored exactly |
| `0004` | `land-final` | One frozen final cloud state for Land | Commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, restored from the exact versioned S3 bundle and manifest |

Checkpoint history is additive. A later safe merge must never erase the baseline, cloud checkpoint chain, final cloud state, returning-local state, merge result, or Land receipt. Lift-private Git history remains outside the user's repository history unless the user explicitly authorizes a separate sanitized publication.

### Fixture Land core and clean live round trip

The local state engine proves the reconciliation boundary independently of live AWS resources or a real user repository:

- the fixture's approved ignored path and hard exclusion are pinned to the immutable Lift Off baseline rather than mutable `.gitignore` state;
- cloud checkpoints and returning-local capture preserve real tracked ignored files while hard-removing the baseline-declared exclusion;
- returning local state becomes immutable private commit `L` without moving the user's branch, any Git ref, the real index, or working-tree state during capture; its original `HEAD`, refs, reflog commits, and reachable objects are also imported and pinned under immutable session refs;
- `B -> L` and `B -> C` are compared conservatively, with same-path divergence, type changes, file/directory topology, and case or Unicode collisions routed to `NEEDS_REVIEW` before the original folder is changed;
- clean results are merged in a Lift-private worktree and applied through a durable, canonical journal that atomically moves originals into private recovery, revalidates those bytes before verification, rejects tampered authority, resumes a proven interruption, or rolls back to `L` without overwriting detected concurrent user work;
- the baseline, cloud and returning-local Git histories, final cloud state, local return, merge result, proposed conflict result when available, and Git-backed Land receipt remain under immutable Lift-private refs;
- the receipt payload itself is retained and revalidated from private Git, not only from a local JSON sidecar, while the canonical acknowledgement is persisted separately in the local and guest journals.

On 2026-09-02, run `p0-20260901083520-4fee` exercised this clean path against the live founder fixture. The first attempt stopped safely at controller phase `FINAL_CHECKPOINT_DURABLE` when a `/run` parent-directory mode check failed. After the permission fix, the same operation resumed the same immutable `C` rather than recapturing cloud state. It produced `APPLIED` merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, Git-backed receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`; the guest reached `ACKNOWLEDGED`, the controller lease returned to `LOCAL_PRIMARY`, and compute stopped afterward.

### Live deliberate-conflict acceptance

Fresh disposable run `p0-20260902183748-a7b1` exercised the other terminal Land outcome against real EC2/EBS/S3 and the Mac. Exact local and cloud edits to the same tracked `REMOTE_TEST.md` were pairwise distinct from baseline. Land froze the cloud writer, sealed and independently restore-tested `0002-land-final` as commit `722adcffd8ebba70fb222cfbb1f749b0f5e479bc`, tree `3aa8260a33ec8e8c50b8f277aa2118fd8b88770b`, and imported the exact versioned recovery objects before returning `NEEDS_REVIEW`.

The controller and guest remained `LANDING`; the guest stopped at `FINAL_CHECKPOINT_RECORDED`; no acknowledgement, receipt, apply journal, local cutover, lease return, or compute cleanup existed. The original local working tree, full included-content manifest, `HEAD`, branch, index, refs, reflog, and status remained exact. The Lift-private conflict worktree retained stages 1/2/3 as the exact baseline, local, and cloud bytes, and strict private-ledger `git fsck` reported no corruption. The generic runner was inactive, the user manager was masked with linger disabled, and its exact activation gate rejected a restart while the conflict was pending. EC2 remained running and Systems Manager online for recovery. Repeating the identical Land command returned `changed: false` and left controller state, events, refs, operation evidence, local bytes, final checkpoint, and S3 version identities unchanged. The current retry path also revalidates the live AWS binding, exact guest final checkpoint and writer fence, and all local conflict artifacts before returning a cached result; corruption or fence loss fails closed without reconstructing missing evidence.

An independent read-only audit passed the same invariants, including exact S3 object-version checks, bundle/ref completeness, EBS attachment, guest state, cloud bytes, and absence of a local cutover. This is enough to accept the generated-fixture Land vertical slice as implemented: both clean application and safe conflict preservation have crossed the live boundary. It is not a working customer `Land Workspace`, H6, arbitrary-repository, private-alpha, or launch acceptance. Conflict-resolution UX, automatic offline-helper continuation, repeat runs, and additional interruption phases remain open.

## What the founder run actually proves

| Area | Observed evidence | Honest conclusion |
| --- | --- | --- |
| Direct phone transport | ChatGPT on the founder's phone issued tasks directly to the Ubuntu EC2 Codex Remote environment | The experimental provider path can work without a desktop relay |
| Laptop independence | A fresh unpredictable challenge preceded the reported Mac shutdown; the exact proof appeared in the cloud workspace before the later Mac boot timestamp | Strongly corroborated founder evidence, not cryptographic device attestation |
| Runtime durability | EC2 stop/start changed the guest boot ID while the exact EBS workspace and provider environment survived | Structural recovery passed once |
| Provider reconstruction | Native project/root was reconstructed and read back; a new phone task used the exact folder after restart | Semantic provider recovery passed once for the folder-bound path |
| Approval usability | A request, resolution, exact canary, exact proof, and completed turn were observed and independently verified | The official founder-controlled client completed the guarded workflow once; selected-decision attribution remains unavailable |
| Recovery durability | Four checkpoint bundle/manifest pairs restored from exact S3 object versions with all required hashes and identities | The captured cloud revisions are independently recoverable |
| Safe-to-close | A fresh live status evaluation found every implemented gate true and more than one hour before managed auto-stop | The harness could truthfully tell the founder to close the Mac for that short validity window |
| Clean fixture Land | One frozen `C` survived a fail-closed interruption, restored from exact S3 versions, applied locally, was acknowledged on both sides, returned the lease, and stopped compute | The controlled clean EC2-to-Mac fixture transaction is resumable and recoverable in this run |
| Conflicted fixture Land | A fresh same-file divergence sealed and restored exact `C`, preserved the untouched local workspace and exact private `B/L/C` stages, retained `LANDING`, fenced restart, omitted acknowledgement and cleanup, and was byte-stable on retry | The generated-fixture conflict path fails safe across the live boundary and is idempotent in this run |

The evidence does **not** prove official provider support, repeatability across users or releases, network recovery, credential revocation, production isolation, arbitrary repository capture, automatic offline-helper continuation, conflict-resolution usability, product usability, willingness to pay, or retention.

## Safe-to-close contract learned from the spike

`safeToClose` is a derived, expiring verdict, not a durable boolean and not a synonym for “the process is running.” The Phase 0 verdict is valid for 30 seconds and must be freshly recomputed.

The passing chain requires all of the following:

1. the approved baseline exists and the exact workspace volume is durable;
2. the live CloudFormation resources and AWS identity match the persisted run;
3. the workspace is mounted at the canonical physical path;
4. the provider-neutral runner is active, fresh, identity-matched, healthy, and ready;
5. the Codex daemon and managed versions match the reviewed runtime;
6. Remote is connected and the required controller prerequisite exists;
7. the exact native server project and root read back correctly;
8. controller project visibility is never inferred from those server-side facts;
9. one fresh post-baseline phone task proves the claimed folder/project binding and runtime root;
10. the approval observer and historical verifier agree on the same complete turn;
11. challenge, proof, policy guard, evidence, and checkpoint identities match;
12. the following checkpoint has nonempty exact object-version IDs and passes a clean restore test;
13. the managed auto-stop timer has at least one hour remaining;
14. no remaining step depends on the laptop.

Any missing, stale, malformed, or contradictory fact blocks the promise.

## Security and reliability lessons

### Implemented in the founder harness

- Deployed actions fail closed unless local state matches the exact live stack, outputs, physical resources, safe stack status, AMI identity, account, non-root principal, and immutable STS user ID.
- AWS subprocesses inherit a sanitized environment. Credential, profile, region, endpoint, CA-bundle, metadata-endpoint, and Botocore configuration overrides are removed; configured endpoint URLs are explicitly ignored; and the selected profile and region are passed as explicit CLI arguments.
- Local control files use private directories, no-follow opens, ownership and link-count checks, size limits, atomic replacement, and file/directory `fsync`.
- Physical proof paths are walked without following symbolic links and must be regular, correctly owned, and size bounded.
- The capture harness refuses any workspace without the exact generated disposable-fixture marker before creating a ledger. Its one ignored-file inclusion must match the marker-declared path exactly.
- The approval observer runs as a hardened root-owned transient service from checksum-verified root-owned files, uses only the local Unix socket, and cannot answer provider requests.
- Provider connector state stays outside the project and current ordinary checkpoints. The complete live Land lifecycle must preserve that exclusion.

### Implemented locally but not in the founder harness

- A real-workspace candidate can be generated without transferring content and can be invalidated by a fresh rescan when workspace or Git identity changes.
- Every candidate path must receive an exact scoped decision; hard-excluded or unsupported state cannot be approved, and excluded metadata does not enter the portable policy.
- The initial approved entry set is separate from immutable return rules. In trusted local classification, supplied new ordinary paths can be selected for return, while supplied new ignored or sensitive paths require review and supplied prohibited or unsupported paths block.
- The portable effective-policy decoder rejects unknown or missing fields, invalid enums and entries, normalization collisions, and invalid bindings or hashes.

These controls are local foundation evidence only. Candidate self-hashes prove internal integrity, not scanner provenance or path-set completeness. They do not authorize an upload and are not yet enforced by generic B, guest reconstruction, checkpoints, Land, or receipts.

### Still blocking external alpha

- The Codex provider daemon, reusable provider credentials, and arbitrary workspace workload still share the `lift` Unix identity. A compromised workspace can potentially reach writable provider state. They need a separate provider-service identity or equivalently narrow credential broker.
- The disposable image bootstrap downloads the AWS CLI archive and Codex installer without verifying a reviewed installer digest or signature before root execution. Use a signed, content-addressed image or verify published signatures and pinned digests.
- Installed plugin metadata may affect model context even when no plugin, hook, MCP tool, or script provenance appears in the verified turn. High-assurance use needs an isolated plugin-disabled proof environment or content-addressed pinned bundles.
- Provider-supported decision-bearing audit evidence or a trusted transport boundary is required for strict approval attribution.
- Network interruption/recovery, reauthentication, disconnect/revoke, delete, cost-failure behavior, and repeated stop/start runs remain untested.
- Production transfer must provide explicit manifest review and must never infer permission to upload ignored or sensitive files from discovery alone.

## Current implementation boundary

The repository contains a feasibility harness, not a customer product.

Implemented:

- generated fixture capture and cloud reconstruction;
- real EC2/EBS/S3 lifecycle and identity binding;
- provider-blind supervision;
- experimental Codex connection recipe;
- direct provider-native phone proof;
- stop/start recovery;
- immutable cloud checkpoint and exact restore;
- fail-closed safe-to-close evidence;
- baseline-pinned fixture inclusion and exclusion policy across Lift Off and checkpoints;
- fixture-only local `B/L/C` reconciliation, isolated merge, transactional clean apply, safe rollback, structured conflict preservation, immutable local session refs, and a Git-backed receipt.
- one clean live founder-fixture Land transaction through writer freeze, exact final-checkpoint restore/import, local acknowledgement, lease return, and compute stop.
- one deliberate live founder-fixture conflict through writer freeze, exact final-checkpoint restore/import, untouched-local preservation, isolated `B/L/C` stages, retained `LANDING`, writer fencing, and idempotent retry.
- local-only real-workspace discovery, per-path approval, strict effective-policy serialization, trusted in-process return classification, and plan revalidation, with 77 focused passing tests.

Not implemented:

- signed desktop helper;
- dashboard, Connections tab, or Workspaces tab;
- one-click provider login and pairing;
- policy-bound generic `B` capture, upload, guest reconstruction, checkpoints, and Land for an arbitrary reviewed real workspace;
- customer-facing real-workspace review and approval UI;
- secrets broker and separate provider-service identity;
- normal product error recovery and revocation controls;
- automatic offline-helper continuation, conflict-resolution UI, repeated clean/conflict runs, and additional interruption phases;
- design-partner onboarding, billing, analytics, or production operations.

## Next highest-value slice: bind the reviewed policy to generic B and reconstruction

The local candidate -> approval -> effective-policy -> return-plan foundation exists. The next build should carry that policy through the smallest generic baseline `B` and reconstruction path beside the unchanged fixture adapter. It must transfer only the approved initial entries, bind every generic artifact to the policy, and avoid importing arbitrary user Git history. Reliability evidence should continue with fresh clean, conflict, and interruption fixture runs.

### Thin vertical scope

1. Add a generic capture entry point beside the marker-only fixture path; validate one freshly approved `EffectivePolicyV1` and copy only its exact `initialTransferEntries`.
2. Construct a policy-bound synthetic root `B` with a private index and without fetching or importing user refs, reflogs, `HEAD` ancestry, or other historical objects.
3. Add mutually exclusive generic session and manifest schemas carrying the complete policy and `policySha256`; fixture schema and `fixturePolicy` remain unchanged.
4. Reconstruct only the policy-selected B tree and validate the policy, manifest, commit trailer, root, and entry identities before publishing guest state.
5. Prove locally or in an isolated guest test that one noncritical real workspace reconstructs exactly, no excluded byte or arbitrary historical object transfers, and the user's branch, refs, real index, and working tree remain unchanged.
6. Then wire fresh rule-based classification into cloud checkpoints and Land so a safe cloud-created file is not lost merely because it was absent from the initial allowlist.
7. In parallel, repeat clean/conflicted fixture runs, exercise interruption boundaries, and implement offline-helper continuation without conflating that evidence with real-workspace support.

### Local acceptance tests now passing

- unchanged local fixture receives the exact cloud delta;
- local and cloud edits to different files combine correctly;
- same-file edits preserve both versions and do not alter the original folder;
- delete-versus-modify and file-versus-directory changes become explicit conflicts;
- a crash during local application deterministically completes or restores;
- no path escapes, symlink traversal, case collision, or ignored-file expansion occurs;
- all baseline, checkpoint, merge, conflict, and receipt objects remain restorable after clean completion.

Additional passing coverage includes tampered-journal rejection, replacement interruption and resume, rollback without clobbering a racing local file, file/symlink and file/directory review, case-colliding directory prefixes, `.git`-targeting symlink rejection, hard exclusion after `.gitignore` mutation, force-added tracked ignored files, deterministic receipt recovery, and idempotence after later local edits.

### Live observations still pending

- a second clean run repeats the result from a fresh session;
- a second deliberate live conflict repeats the same preservation, no-acknowledgement, no-lease-return, and no-cleanup result;
- interruption retries at additional phases retain the exact recovery identities;
- a Land requested while the laptop/helper is offline continues automatically after reconnect;
- one explicitly reviewed noncritical real workspace completes the local -> cloud -> phone -> local loop;
- the supported journey completes without founder terminal intervention.

The marker-only live capture guard remains in force until policy-bound generic B, reconstruction, checkpoint, and Land integration is implemented and inspected. The local policy module alone is not authorization to send a real workspace through the fixture command.

## Product and architecture truths to preserve

- The durable product object is a project workspace, independent of one agent, provider conversation, device, participant, or compute instance.
- Consumer/prosumer first; one user and one workspace remain the implementation and validation beachhead.
- Replace laptop dependence and prove repeated mobile-launched workspace use before expanding toward team collaboration.
- Preserve the provider application as the command, approval, and notification surface.
- Where provider capability permits it, mobile readiness includes launching a new task into the exact workspace after the laptop is offline.
- Keep the workspace and runner provider-neutral while isolating provider setup in reviewed recipes.
- Allow local, GitHub, and empty workspace origins without making GitHub a prerequisite.
- Support multiple agent tasks eventually through explicit shared, isolated, and read-only modes; do not require every task to use a Git worktree and do not present unrestricted shared writes as safe.
- Treat controlled internet, browser, and computer use as product-north-star capabilities with separate security gates.
- Treat Lift-hosted runtimes and supported provider-owned cloud agent computers as future replaceable execution locations attached to one durable project identity; external agent-computer attachment is not implemented today.
- Selectively transplant approved state; never clone a home directory or silently upload secrets and ignored files.
- Use a single-writer ownership lease rather than unrestricted live bidirectional sync.
- Keep Git underneath for ancestry and merge, but keep Lift history private and never push or open a pull request without explicit authorization.
- Preserve every session's history through clean Land; clean reconciliation is not a deletion event.
- Make infrastructure invisible in the supported journey without hiding security, transfer, cost, or recovery truth.

These product-direction decisions are documented in [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md) and D-033 through D-041 in [`DECISIONS.md`](DECISIONS.md). They do not alter the current implementation evidence or the immediate explicit-manifest slice.

## Operational snapshot

At the final 2026-09-02 verification, founder fixture run `p0-20260901083520-4fee` had four immutable restore-tested checkpoints, including exact `0004-land-final`; local reconciliation was `APPLIED`; the receipt and acknowledgement were retained; the guest was `ACKNOWLEDGED`; the controller lease was `LOCAL_PRIMARY`; and the exact bound compute instance was stopped after acknowledgement.

Fresh conflict run `p0-20260902183748-a7b1` separately ended at the intentional recovery state: restore-tested `0002-land-final`, `NEEDS_REVIEW`, controller and guest `LANDING`, untouched local state, exact private conflict stages, inactive fenced runner, no acknowledgement or cleanup, and compute retained with Systems Manager online. The exact same Land retry returned `changed: false`. This was also a point-in-time acceptance observation; it is not a reusable safe-to-close verdict or an instruction to leave compute running indefinitely.

A later live status recheck at `2026-09-02T20:12:25Z` found that conflict instance still running with Systems Manager online, while the runner remained inactive and the connection remained `LANDING`. Fresh readiness correctly returned `safeToClose: false`; its provider check reported that the Codex daemon version could not be verified. The preserved conflict is therefore a recovery hold, not an active provider-ready workspace.

Together these observations record completed clean and safely halted conflict fixture transactions, not current provider readiness; live readiness expires and must be re-read on a new Lift Off.

The founder harness is intentionally bound to one explicit non-root Lift AWS identity and profile. Commands must not fall back to a default profile, reuse unrelated AWS credentials, or trust stored account/resource identifiers without live verification. Do not place account IDs, credentials, pairing values, raw client records, or provider tokens in documentation or logs.

## Evidence and code map

- [Merged Phase 0 PR](https://github.com/natecl/lift/pull/3)
- [Merged current-state documentation PR](https://github.com/natecl/lift/pull/4)
- [`VALIDATION.md`](VALIDATION.md): hypothesis status and exact evidence interpretation
- [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md): full experiment narrative and protocol details
- [`EXPERIENCE.md`](EXPERIENCE.md): product-safe-to-close and Land contracts
- [`SECURITY.md`](SECURITY.md): threat model, implemented controls, and promotion gates
- [`STATE_SYNC.md`](STATE_SYNC.md): authoritative Land and session-ledger algorithm
- [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md): exact local policy schemas and staged generic integration contract
- [`ROADMAP.md`](ROADMAP.md): phase gates and immediate sequencing
- [`../spikes/ec2-laptop-off/spike.py`](../spikes/ec2-laptop-off/spike.py): local orchestrator and evidence controller
- [`../spikes/ec2-laptop-off/workspace.py`](../spikes/ec2-laptop-off/workspace.py): fixture capture boundary
- [`../spikes/ec2-laptop-off/workspace_policy.py`](../spikes/ec2-laptop-off/workspace_policy.py): local-only reviewed real-workspace policy foundation
- [`../spikes/ec2-laptop-off/tests/test_workspace_policy.py`](../spikes/ec2-laptop-off/tests/test_workspace_policy.py): focused policy tests
- [`../spikes/ec2-laptop-off/land.py`](../spikes/ec2-laptop-off/land.py): fixture-only local reconciliation and transactional apply core
- [`../spikes/ec2-laptop-off/live_land.py`](../spikes/ec2-laptop-off/live_land.py): durable controller-side live Land state machine
- [`../spikes/ec2-laptop-off/guest/landing.py`](../spikes/ec2-laptop-off/guest/landing.py): guest writer fence, final checkpoint, and acknowledgement protocol
- [`../spikes/ec2-laptop-off/guest/runner.py`](../spikes/ec2-laptop-off/guest/runner.py): provider-blind supervisor
- [`../spikes/ec2-laptop-off/guest/codex_project.py`](../spikes/ec2-laptop-off/guest/codex_project.py): experimental recipe-scoped provider preparation/readiness
- [`../spikes/ec2-laptop-off/guest/approval_observer.py`](../spikes/ec2-laptop-off/guest/approval_observer.py): passive live request/turn observer
- [`../spikes/ec2-laptop-off/guest/checkpoint.py`](../spikes/ec2-laptop-off/guest/checkpoint.py): immutable checkpoint construction
- [`../spikes/ec2-laptop-off/recipes/codex-headless.json`](../spikes/ec2-laptop-off/recipes/codex-headless.json): reviewed Codex workload recipe

## Updating this document

Update this file whenever a material evidence gate changes. Keep observed facts, guarded inference, and product claims separate. Detailed documents remain authoritative for their domains; this file should link to them and provide the coherent current picture rather than silently invent a second design.
