# Current State

Last verified: 2026-09-02

Phase 0 implementation/evidence baseline: merge commit `b61bb9b42e3a36809d7947c1055e524da55954b5`
Product phase: Phase 0 provider-path feasibility passed once; the complete round trip is not yet complete

This is the canonical short-to-medium-term memory for Lift. It answers four questions: what exists, what was actually observed, what was learned, and what should be built next. Detailed protocol evidence remains in [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md).

## Executive snapshot

- Lift is infrastructure for existing coding agents, not a coding agent, phone chat, IDE, or GitHub replacement.
- The first wedge is one active Mac coding workspace moved to one persistent Linux cloud workspace, controlled from the provider application the user already has.
- The Codex-first provider path has passed once on a real Ubuntu EC2 instance with encrypted EBS: direct phone control, strongly corroborated laptop-off work, EC2 stop/start recovery, exact post-restart folder binding, a guarded approval/proof turn, an immutable following checkpoint, exact-version S3 restore, and a fresh `safeToClose: true` evaluation.
- The spike code and evidence were merged through [PR #3](https://github.com/natecl/lift/pull/3). Local verification at the merged revision has 125 passing unit tests plus passing Ruff, Python compilation, CloudFormation validation, whitespace, and secret/account-identifier scans. GitHub had no hosted status checks configured for that PR.
- The validated capture path is deliberately restricted to a generated disposable fixture. It is not yet safe or usable for arbitrary real user workspaces because the production manifest-review flow does not exist.
- There is no product dashboard or signed desktop helper yet. Authentication, pairing, and proof still required founder-operated terminal steps.
- `Land Workspace` is designed but not implemented end to end. Clean return, local divergence, same-file conflict, crash-safe application, and durable local acknowledgement remain the highest-value missing product slice.
- Codex direct Remote remains experimental and founder-only. One passing run is evidence of feasibility, not provider support, repeatability, external-alpha safety, or market demand.

## What is now implemented

### Phase 0 runtime harness

The merged spike under [`spikes/ec2-laptop-off/`](../spikes/ec2-laptop-off/) can:

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

### Durable checkpoint chain

The founder run retains three immutable Lift-private checkpoints:

| Ordinal | Label | Purpose | Restore result |
| --- | --- | --- | --- |
| `0001` | `phone-proof` | First direct phone workspace proof | Exact versioned bundle and manifest restored successfully |
| `0002` | `laptop-off-proof` | Challenge/proof created while the laptop-off sequence was being tested | Exact versioned bundle and manifest restored successfully and survived EC2 stop/start |
| `0003` | `post-restart-phone-proof` | Fresh phone binding, guarded approval, and proof after restart | Commit `674bd2722b961caf1e91db98f582330b6b4a54b5`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, and 12 files restored exactly |

Checkpoint history is additive. A later safe merge must never erase the baseline, cloud checkpoint chain, final cloud state, returning-local state, merge result, or Land receipt. Lift-private Git history remains outside the user's repository history unless the user explicitly authorizes a separate sanitized publication.

## What the founder run actually proves

| Area | Observed evidence | Honest conclusion |
| --- | --- | --- |
| Direct phone transport | ChatGPT on the founder's phone issued tasks directly to the Ubuntu EC2 Codex Remote environment | The experimental provider path can work without a desktop relay |
| Laptop independence | A fresh unpredictable challenge preceded the reported Mac shutdown; the exact proof appeared in the cloud workspace before the later Mac boot timestamp | Strongly corroborated founder evidence, not cryptographic device attestation |
| Runtime durability | EC2 stop/start changed the guest boot ID while the exact EBS workspace and provider environment survived | Structural recovery passed once |
| Provider reconstruction | Native project/root was reconstructed and read back; a new phone task used the exact folder after restart | Semantic provider recovery passed once for the folder-bound path |
| Approval usability | A request, resolution, exact canary, exact proof, and completed turn were observed and independently verified | The official founder-controlled client completed the guarded workflow once; selected-decision attribution remains unavailable |
| Recovery durability | Three exact S3 object versions restored into fresh Git repositories with all required hashes and identities | The captured cloud revisions are independently recoverable |
| Safe-to-close | A fresh live status evaluation found every implemented gate true and more than one hour before managed auto-stop | The harness could truthfully tell the founder to close the Mac for that short validity window |

The evidence does **not** prove official provider support, repeatability across users or releases, network recovery, credential revocation, production isolation, arbitrary repository capture, complete Land, product usability, willingness to pay, or retention.

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
- Provider connector state stays outside the project and current ordinary checkpoints. The future Land implementation must preserve that exclusion.

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
- fail-closed safe-to-close evidence.

Not implemented:

- signed desktop helper;
- dashboard, Connections tab, or Workspaces tab;
- one-click provider login and pairing;
- arbitrary real-workspace discovery and reviewable transfer manifest;
- secrets broker and separate provider-service identity;
- normal product error recovery and revocation controls;
- final cloud freeze and Land checkpoint;
- local baseline comparison, private three-way merge, transactional application, acknowledgement, and conflict UI;
- design-partner onboarding, billing, analytics, or production operations.

## Next highest-value slice: Land

The next build should complete the missing half of the promise on the disposable fixture before adding dashboard polish or a second provider.

### Thin vertical scope

1. Refuse new cloud writers and move the ownership lease from `CLOUD_PRIMARY` to `LANDING`.
2. Gracefully stop the provider and any declared workspace-writing processes.
3. Perform a complete final cloud scan and create immutable checkpoint `C`.
4. Persist and restore-test `C` independently of running compute.
5. Capture the unchanged or intentionally diverged local fixture as private synthetic commit `L` without touching its branch, refs, index, or working tree.
6. Compare `B -> L` and `B -> C` and merge in an isolated Lift-private worktree.
7. For an unchanged or nonoverlapping local workspace, stage and transactionally apply the verified result with a durable recovery journal and pre-apply copy.
8. For same-path, delete/modify, type, symlink, binary, or case conflicts, leave the original local workspace untouched and preserve local, cloud, and proposed merge results.
9. Verify the final local manifest before acknowledgement.
10. Write an immutable Land receipt, return the ownership lease to `LOCAL_PRIMARY`, and retain the complete session ledger even for a clean merge.
11. Make retries idempotent across interruption before freeze, after final checkpoint, during download, during local apply, and after acknowledgement.

### First acceptance tests

- unchanged local fixture receives the exact cloud delta;
- local and cloud edits to different files combine correctly;
- same-file edits preserve both versions and do not alter the original folder;
- delete-versus-modify and file-versus-directory changes become explicit conflicts;
- a crash during local application deterministically completes or restores;
- a Land requested while the laptop/helper is offline completes after reconnect;
- no path escapes, symlink traversal, case collision, or ignored-file expansion occurs;
- all baseline, checkpoint, merge, conflict, and receipt objects remain restorable after clean completion.

Once fixture Land passes, replace the marker-only capture boundary with the smallest explicit real-workspace manifest-review flow and repeat the entire local -> cloud -> phone -> local loop on a noncritical real repository.

## Product and architecture truths to preserve

- Consumer/prosumer first; one user and one workspace.
- Replace laptop dependence before expanding toward team source hosting.
- Preserve the provider application as the command, approval, and notification surface.
- Keep the workspace and runner provider-neutral while isolating provider setup in reviewed recipes.
- Selectively transplant approved state; never clone a home directory or silently upload secrets and ignored files.
- Use a single-writer ownership lease rather than unrestricted live bidirectional sync.
- Keep Git underneath for ancestry and merge, but keep Lift history private and never push or open a pull request without explicit authorization.
- Preserve every session's history through clean Land; clean reconciliation is not a deletion event.
- Make infrastructure invisible in the supported journey without hiding security, transfer, cost, or recovery truth.

## Operational snapshot

At the final 2026-09-02 verification, the scoped founder environment reported:

- EC2 `running` and Systems Manager `Online`;
- the generic runner active, fresh, healthy, and semantically ready;
- Codex Remote connected with one registered controller;
- the exact server project and workspace root registered;
- three restore-tested checkpoints in the immutable chain;
- the ownership lease still `CLOUD_PRIMARY` because complete Land has not run;
- local, persisted, and live safe-to-close gates true;
- more than one hour remaining before the managed auto-stop deadline.

This was a point-in-time observation. Runtime state, Remote connectivity, credentials, and the 30-second safe-to-close verdict expire and must be re-read before any later action.

The founder harness is intentionally bound to one explicit non-root Lift AWS identity and profile. Commands must not fall back to a default profile, reuse unrelated AWS credentials, or trust stored account/resource identifiers without live verification. Do not place account IDs, credentials, pairing values, raw client records, or provider tokens in documentation or logs.

## Evidence and code map

- [Merged Phase 0 PR](https://github.com/natecl/lift/pull/3)
- [`VALIDATION.md`](VALIDATION.md): hypothesis status and exact evidence interpretation
- [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md): full experiment narrative and protocol details
- [`EXPERIENCE.md`](EXPERIENCE.md): product-safe-to-close and Land contracts
- [`SECURITY.md`](SECURITY.md): threat model, implemented controls, and promotion gates
- [`STATE_SYNC.md`](STATE_SYNC.md): authoritative Land and session-ledger algorithm
- [`ROADMAP.md`](ROADMAP.md): phase gates and immediate sequencing
- [`../spikes/ec2-laptop-off/spike.py`](../spikes/ec2-laptop-off/spike.py): local orchestrator and evidence controller
- [`../spikes/ec2-laptop-off/workspace.py`](../spikes/ec2-laptop-off/workspace.py): fixture capture boundary
- [`../spikes/ec2-laptop-off/guest/runner.py`](../spikes/ec2-laptop-off/guest/runner.py): provider-blind supervisor
- [`../spikes/ec2-laptop-off/guest/codex_project.py`](../spikes/ec2-laptop-off/guest/codex_project.py): experimental recipe-scoped provider preparation/readiness
- [`../spikes/ec2-laptop-off/guest/approval_observer.py`](../spikes/ec2-laptop-off/guest/approval_observer.py): passive live request/turn observer
- [`../spikes/ec2-laptop-off/guest/checkpoint.py`](../spikes/ec2-laptop-off/guest/checkpoint.py): immutable checkpoint construction
- [`../spikes/ec2-laptop-off/recipes/codex-headless.json`](../spikes/ec2-laptop-off/recipes/codex-headless.json): reviewed Codex workload recipe

## Updating this document

Update this file whenever a material evidence gate changes. Keep observed facts, guarded inference, and product claims separate. Detailed documents remain authoritative for their domains; this file should link to them and provide the coherent current picture rather than silently invent a second design.
