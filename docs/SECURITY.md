# Security Baseline

Last updated: 2026-09-02

Lift will execute powerful autonomous tools against source code and credentials on remote infrastructure. Security is part of the initial product definition.

## Current security posture

The Phase 0 harness has strong founder-fixture controls: exact live AWS/resource identity binding, private no-follow local state, a baseline-pinned disposable capture policy, narrow physical workspace paths, a provider-blind unprivileged runner, root-owned passive approval observation, challenge-bound evidence, immutable checkpoint objects, exact restore tests, Git invocations isolated from ambient configuration and repo-local hooks, and a fixture Land transaction with an EBS-resident writer fence, exact-version quarantine import, canonical journal authority, preserved originals, rollback, conservative conflict handling, pinned returning-local history, exact acknowledgement, and Git-backed receipts. The provider path and separate clean and deliberate-conflict live founder-fixture Land transactions have passed once each.

A separate local-only real-workspace policy foundation now passes 77 focused tests. It covers discovery and classification of one supported physical Git worktree, exact scoped per-path decisions, omission of excluded metadata from the portable effective policy, strict policy decoding, and separation of initial-transfer entries from rule-based return classification. Return classification is trusted local/in-process logic over a caller-supplied candidate; the candidate self-hash does not authenticate scanner provenance or path-set completeness. The module performs no upload and is not wired into generic B, EC2 reconstruction, checkpoints, Land, or receipts.

It is not safe for external alpha use. The provider daemon and reusable credentials still share the `lift` Unix identity with the untrusted workspace workload; installer bytes are not signature/digest verified before root execution; policy-bound real-workspace transfer and the customer review/conflict-resolution experiences do not exist; approval decision/responder attribution is unavailable; and network recovery, revoke, repetition, broader interruption coverage, and automatic offline-helper continuation remain untested. See [`CURRENT_STATE.md`](CURRENT_STATE.md) for the coherent current boundary.

## Security objectives

- Compromise of one workspace does not expose another workspace or the control plane.
- An agent can access only the project, tools, network destinations, and credentials it requires.
- Users can see and revoke access.
- Secrets do not appear in images, snapshots, logs, manifests, or source-control changes.
- Local and cloud work remain recoverable after compromise or operator error.
- No file leaves the local computer merely because Lift discovered it.
- Every command and observed workspace mutation can be attributed to an authenticated human or agent task at the strongest level the runtime supports.
- Shared-mode agent collisions are visible and recoverable rather than silently accepted.
- Browser identity, provider identity, project files, and team membership remain separate security domains.

## Primary threats

### Malicious repository content

Instructions in source files, issues, dependencies, tool configuration, or generated output can manipulate an agent into reading secrets, changing policy, or exfiltrating data.

### Overpowered credentials

A general GitHub token, AWS key, browser profile, or personal SSH key can turn a compromised project into a compromise of the user's broader digital life.

### Cross-tenant escape

A container or runtime vulnerability could expose another user's memory, filesystem, credentials, or network identity.

### Unsafe state transfer

Automatic discovery could upload private ignored files, `.env` files, credentials, customer data, or unrelated home-directory content.

### Sync corruption

Concurrent local and cloud edits or implementation bugs could destroy or overwrite work.

### Concurrent agent corruption

Two agents writing in one shared working directory can race, overwrite files, invalidate each other's assumptions, or leave services and dependencies in a contradictory state.

### Browser and computer compromise

An agent with an authenticated browser, visual computer control, broad network access, or a shared login can escape the intended project purpose, expose credentials, or perform consequential actions in external systems.

### Cross-participant privilege confusion

A teammate or agent can inherit workspace, secret, browser, or GitHub authority intended for another participant if membership and task capabilities are not explicit and independently revocable.

### Untrusted external execution provider

A provider-owned agent computer can retain an overbroad project copy, misstate isolation or provenance, keep task credentials after revocation, or return untrusted changes while appearing to be a first-class Lift participant. Lift cannot treat a provider's task mode, deletion claim, activity stream, or filesystem as authoritative merely because an integration exists.

### Public development services

A preview server, database console, or debugging port could be exposed to the internet without authentication.

### Resource abuse

An agent can create runaway processes, consume compute, make excessive network calls, or provision paid external resources.

### Control-plane compromise

An attacker who controls Lift authentication or orchestration could reach persistent workspaces and their secrets.

## Required controls for private alpha

### Isolation

- Use a dedicated VM or strong microVM boundary per active workspace.
- Do not rely on an application-level permission prompt as the isolation boundary.
- Run workspace services as an unprivileged user.
- Prevent workspace access to cloud instance metadata.
- Separate control-plane credentials from workspace credentials.

### File transfer

- Present a manifest before the first transfer.
- Apply default-deny rules to files outside the selected workspace.
- Treat `.env`, credential files, key files, databases, and ignored files as sensitive.
- Require explicit approval for sensitive or ignored files.
- Encrypt payloads in transit and at rest.
- Maintain content hashes and versioned recovery snapshots.

The live Phase 0 capture code is intentionally narrower than these product requirements. It refuses any workspace without the exact generated disposable-fixture marker before creating a private ledger and accepts only the one ignored path declared by that marker. This guard must not be relaxed for real repositories.

The new local policy foundation establishes, but does not yet integrate, the production boundary:

- discovery is read-only and produces a self-hashed local `CandidateManifestV1`; it does not grant transfer permission;
- canonical paths are classified across Git state and security state, while hard-excluded or unsupported entries expose no portable content hash, size, target, or bytes;
- regular files are opened without following links, bounded, hashed, and scanned across their full byte stream through file descriptors with before/after identity checks; physical Git blob identity is compared directly to the copied index without invoking `git diff`; hard links are unsupported;
- Git runs through a validated root-owned absolute system executable with a minimal environment derived from the operating-system account rather than ambient `PATH`, `HOME`, loader variables, or Git selectors;
- configured standard `core.excludesFile` sources and the implicit default or validated custom-XDG global ignore are discovered through the trusted Git binary, opened without link traversal, owner/link/size checked, copied privately, hashed into workspace identity, and applied explicitly while all later Git commands isolate the original external files; each live source path is then reopened through an anchored no-follow component walk and must retain the exact inode, metadata, and content digest;
- unsafe or nonreconstructable symlink dependency chains, nested Git repositories including bare repositories, gitlinks, partial/promisor repositories, alternate object storage, unsupported Git states, normalization collisions, root replacement, mount-table inspection failure, identifiable nested mounts, identifiable network filesystems, and configured external Git filters fail closed;
- a workspace equal to the account home or nested beneath account-private components such as `.ssh`, `.aws`, `.docker`, `.kube`, `.codex`, password stores, or keychains is rejected before scanning;
- ignored and sensitive paths, including force-added ignored paths, default to exclusion and require an explicit include action; private keys, credential stores, browser cookies, keychain databases, and other hard exclusions cannot be overridden;
- the approval binds every discovered path exactly once to the candidate plus run, workspace, and helper identity;
- only approved initial entries enter the portable `EffectivePolicyV1`; strict decoding rejects schema expansion or invalid bindings;
- a separate return ruleset allows new ordinary files, requires review for new ignored or sensitive files, and blocks prohibited, unsupported, or unknown-tombstone state;
- return-plan validation reclassifies the caller-supplied candidate instead of trusting the plan's self-hash alone; it does not authenticate the candidate or prove physical completeness.

Content classification is a defense-in-depth heuristic, not a complete secret detector. The UI must still tell the user exactly what will move. Before any portable cloud checkpoint or Land use, Lift needs an authenticated scanner-produced complete physical snapshot bound to the exact effective policy hash, approval scope (`runId`, `workspaceId`, and `helperVersion`), intended role, and scanner/classifier version. Capture must then bind copied bytes to that authenticated snapshot and recheck it around tree construction. A self-hashed `CandidateManifestV1` supplied across a trust boundary is insufficient because omitted paths can be rehashed consistently. The current return classifier does not itself scan a filesystem. Mount-type detection is limited to mount state the host can identify. No real-project upload is authorized until generic B/reconstruction/checkpoint/Land integration is implemented and independently reviewed. See [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md).

### Secrets

- Never bake secrets into machine images.
- Store secrets in a dedicated encrypted service.
- Scope each secret to a workspace and purpose.
- Prefer short-lived tokens and GitHub App credentials over personal access tokens.
- Inject secrets into specific processes rather than writing them to general project files.
- Redact secrets from logs and terminal event storage.
- Provide one-action revocation through the Connections tab and explain when provider-side revocation is also required.

### Network

- Default to restricted outbound network access.
- Make broad internet access a visible workspace permission.
- Support destination allowlists as soon as practical.
- Block private control-plane and cloud metadata addresses.
- Authenticate every preview and use TLS.
- Do not expose raw workspace ports publicly.

### Agent actions

- Require confirmation for destructive filesystem operations, secret access, production changes, external messages, deployments, purchases, and new cloud resources.
- Keep an append-only action and approval history.
- Give the user an immediate stop button that terminates agent processes and revokes active secret grants.
- Separate “agent completed the task” from “changes were merged or deployed.”

### Multi-agent execution

- Assign every agent task a stable identity, authenticated initiator, declared goal, execution mode, capability grants, and lifecycle record.
- Support shared, isolated, and read-only modes as explicit policies rather than inferred behavior.
- Before shared-mode writes, create a recoverable checkpoint and start an append-only task-attributed command and file-activity journal.
- Detect overlapping observed writes and surface them immediately; do not claim arbitrary shell writes can always be prevented.
- Preserve prior file versions and provide per-task pause and stop controls.
- Treat Git worktrees and copy-on-write environments as stronger isolation options, not mandatory collaboration semantics.
- Do not treat separate agent conversations, names, browser screens, or prompts as security boundaries.
- Scope secrets, browser identities, network grants, and external actions independently from filesystem-sharing mode.

### Browser and computer use

- Use a dedicated project-scoped browser profile; never import the user's everyday cookie database or full authenticated personal profile.
- Encrypt persistent browser state separately from project files and exclude it from Git, ordinary checkpoints, Land output, analytics, logs, and support bundles unless a purpose-built encrypted recovery path explicitly includes it.
- Use a separate browser context or screen per concurrent agent by default.
- Require explicit policy before agents share an authenticated browser identity.
- Route login, passkey, two-factor, CAPTCHA, and other human-only steps through a short-lived authenticated takeover bound to the exact workspace and browser context.
- Make consequential send, publish, purchase, delete, permission, production, and legal actions require approval even when the browser session is already authenticated.
- Restrict downloads, uploads, clipboard transfer, local file bridging, and browser-to-control-plane network paths.
- Keep browser automation and visible computer-control services off unauthenticated public networks.
- Record nonsecret action provenance sufficient for incident reconstruction without recording passwords, tokens, personal messages, or unrestricted screenshots.

### Team workspace access

- Require explicit workspace membership and authenticated human identity.
- Start with a small owner, member, and viewer model; deny access when repository and Lift permissions disagree until the conflict is resolved.
- Prefer short-lived GitHub App credentials and derive repository access from the connected installation where appropriate.
- Keep workspace membership, provider accounts, secrets, browser profiles, and task identities separately revocable.
- Never make one person's provider or browser login implicitly available to every teammate.
- Record invitation, membership, role, secret-grant, task-launch, approval, publication, and removal events.

### Lift authentication

- Use short-lived web and desktop-helper sessions.
- Protect account recovery and workspace deletion.
- Bind device sessions and allow remote sign-out.
- Rate-limit sensitive endpoints.
- Record security-relevant control-plane events.

### Provider-owned remote authentication

- Treat Codex, Claude, and other provider sessions as user-owned credentials.
- Initiate authentication only through the provider's domain, supported browser flow, or supported device flow; never collect a provider password in Lift.
- Prefer OAuth with PKCE or device authorization when the provider officially supports it, and bind callbacks to the initiating Lift user and workspace.
- Require explicit user authorization for the cloud workspace; do not copy opaque laptop credential stores automatically.
- Store approved provider state outside the project tree in a dedicated encrypted per-user vault or approved encrypted workspace path.
- Exclude provider credential state from ordinary workspace snapshots, transfer manifests, support bundles, and agent-readable project paths.
- Never print pairing secrets, OAuth tokens, cookies, or complete provider state into logs or manifests.
- Allow the user to revoke or remove one provider without deleting the workspace.
- Do not automate account creation, bypass provider policy, or transform inference-only credentials into broader session credentials.
- Pin or record agent versions so provider behavior changes can be diagnosed.
- Never expose a provider daemon, including Codex App Server, directly on an unauthenticated public network.

For the Codex feasibility recipe, the service uses `ProtectHome=read-only`. Its only writable exceptions are the canonical workspace, `/home/lift/.codex`, and `/home/lift/.cache/codex`; never broaden this to `/home/lift`, `/home/lift/Documents/Codex`, `/`, or a glob. A provider fallback into a projectless directory must fail closed. The connector must resolve the canonical workspace real path, reject symbolic-link substitution, use only the local Unix-domain App Server socket, require the generated experimental schema and exact pinned versions, and use provider APIs rather than direct SQLite mutation. Its idempotent registration step must not require Remote connectivity or controller presence; those transient checks belong to non-mutating readiness.

Persist only normalized nonsecret readiness evidence. Do not log raw client lists, pairing payloads, tokens, or provider state. The prototype's nonsecret workspace binding and create-idempotency record lives outside the project tree at `/home/lift/.codex/lift/<workspace-id>/codex-project.json`; its parent directories are mode `0700` and the file is mode `0600`. It must remain outside user-facing Land output, workspace checkpoints, and normal project Git history. An exact trust entry is a workspace-selection prerequisite; it is not an approval bypass or proof that the provider's approval channel works.

Treat each phone readiness attempt as a single evidence transaction, not a collection of reusable flags. The challenge schema, environment and native-project IDs, canonical project and `cwd`, sorted pre-challenge thread baseline, independent proof and approval nonces, proof source, fixed proof path, and checkpoint label are canonicalized and SHA-256 identified. The phone-thread record, approval record, checkpoint record, and safe-to-close record must all carry that same challenge identity. Re-arming must invalidate the earlier proof and approval evidence; normal re-arming must remove a post-restart alias, and post-restart verification must reject an alias that is absent or not exactly equal to the active challenge.

Proof handling is source-specific and fail closed. `codex-phone` may write only `.lift/phone-proof.json`, `codex-phone-post-restart` only `.lift/post-restart-proof.json`, and the separate laptop-off attestation only `.lift/laptop-off-proof.json`; each maps to one fixed checkpoint label. Read proof bytes by walking from the already verified physical workspace directory with no-follow semantics, reject symbolic-link substitution and nonregular files, require the `lift` owner, and enforce the size limit before parsing. The expected proof SHA-256 must be recomputed from the active challenge rather than trusted from stored state.

The App Server's completed command item is not, by itself, proof of a user approval decision. Phase 0 therefore requires two separate checks. The historical verifier independently re-reads the completed task and requires one new post-baseline task, one turn, exact `on-request` policy, `user` reviewer, a network-disabled sandbox, and exactly two agent-originated commands in order: the environment-cleared HTTPS canary and the independently reconstructed proof command. Both commands must have null plugin and script provenance. Hook prompts, file changes, MCP or dynamic tools, additional commands, and other unreviewed turn items invalidate the attempt.

Before the task is armed and again during verification, hash the complete active config-layer description and require every discoverable active `rules/` directory to be absent or empty. Query the effective `hooks/list`, `plugin/list`, and `configRequirements/read` views for the exact workspace; reject discovery or marketplace-load errors, every enabled hook regardless of source, nonempty managed-hook requirements, explicit inline hooks, file-backed `hooks.json`, and opaque active layers. Installed plugins may remain enabled so the proof does not destroy the user's normal Codex workflow, but Lift must validate a bounded `plugin/list` response, hash that complete response into the guard, require it unchanged, and reject plugin or MCP tool items plus plugin/script command provenance in the exact proof turn. Bind that guard digest and the named inference method into the challenge, phone-thread evidence, approval evidence, checkpoint, and safe-to-close chain. Any command or provenance variation, rule/config/hook/plugin-state change, non-human reviewer, different policy, or guard mismatch blocks the transition.

This is a guarded founder-spike claim, not proof of plugin-free model context. OpenAI documents that installed plugins can add skills, connectors, MCP tools, and hooks, and that installed skill metadata can enter a new task's context and trigger implicit skill loading. The public documentation does not guarantee that `plugin/list` binds every byte of remote plugin content, and remote marketplace sources may update. A high-assurance external-alpha verifier therefore needs an isolated plugin-disabled proof environment or content-addressed, pinned plugin bundles in addition to the existing no-hooks and no-plugin-execution checks. See the official [plugins](https://learn.chatgpt.com/docs/plugins), [skills](https://learn.chatgpt.com/docs/build-skills), [hooks](https://learn.chatgpt.com/docs/hooks), and [plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management) documentation.

Before showing the phone prompt, the controller starts a challenge-specific passive observer as a hardened root-owned transient systemd service from checksum-verified, root-owned runtime files. The observer uses only the local Unix-domain App Server socket, never answers a server request, and does not execute the mutable provider binary or a workspace-owned helper. After App Server initialization, it performs an empty post-baseline scan and writes a root-owned mode-`0600` ready record beneath a root-owned mode-`0700` directory; any already-fresh task blocks readiness. It then stays subscribed through the entire task and requires, in order, the exact `item/commandExecution/requestApproval`, matching `serverRequest/resolved`, successful canary completion, successful proof-command completion, and successful `turn/completed`. Its normalized root-owned evidence binds the challenge and guard hashes, baseline, environment, native project, `cwd`, thread, turn, request, both item identities, both command hashes, and event times. It does not store raw commands or provider secrets.

The controller accepts that evidence only from a successfully exited observer unit with exact private-file metadata and only when it agrees with the independently produced historical-verifier result. Neither evidence path substitutes for the other. Observer schema v8, service control, source-authentic approval-decision schema validation, and evidence binding are covered by local tests and passed one live founder phone task on the EC2 spike on 2026-09-02. This is single-run feasibility evidence, not a production trust boundary.

The public provider protocol still does not expose the decision payload or responder connection identity to the passive observer. Its `availableDecisions` field is a presentation hint rather than a server-enforced allowlist, so a nonconforming client could return another valid decision enum that the observer never sees. The combined evidence therefore supports only the guarded inference `request observed -> request resolved -> exact command succeeded` when using the trusted official founder-controlled client, not the claim that a particular phone or person tapped Approve. Strict attribution needs a provider-supported decision-bearing audit event or trusted transport boundary; a repeat-canary design that observes a second identical approval request can separately rule out session-scoped acceptance. Root ownership protects the observer process and its evidence from the unprivileged workspace, but it does not solve the separate fact that the Phase 0 provider daemon and workload share the `lift` Unix identity. Before an external alpha, isolate the provider service and policy state under a separate identity or equivalent broker and require a provider-supported audit signal for decision attribution. See the official [App Server approval protocol](https://developers.openai.com/codex/app-server/#approvals), [Codex rules documentation](https://developers.openai.com/codex/rules/), and [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks).

A checkpoint may become safe-to-close evidence only when it carries the active phone challenge, proof source, proof digest, checkpoint commit and tree, nonempty exact version IDs for both recovery objects, and a successful restore-test record whose hashes, Git identities, file count, and timestamp exactly match the latest checkpoint. Re-read the managed auto-stop timer live and require at least one hour remaining; a cached, negative, boolean, expired, or otherwise malformed value cannot authorize safe-to-close.

That provider-private path is necessary but not sufficient isolation. The Phase 0 workload and provider daemon still run under the same `lift` Unix identity, which can write the approved provider-state paths and potentially race provider policy or approval state. Before any external private alpha, Lift must run the provider service and credential owner under a separate Unix identity or an equivalently narrow brokered boundary, keep reusable credentials encrypted and unreadable by the untrusted workspace workload, and verify snapshot exclusion, revocation, and recovery behavior. This service-identity and credential-isolation gate remains independent of the now-passed single-run phone-task and guarded live approval evidence.

### Provider-owned execution computers

Before a provider-owned computer may participate in a Lift task:

- authenticate the provider, execution location, task, workspace, and requested mode with short-lived, independently revocable identity;
- expose only a reviewed task-scoped state manifest and the minimum required secrets or capabilities, never the whole workspace vault by default;
- advertise shared, isolated, or read-only behavior only when the provider interface can actually enforce and evidence that mode;
- document provider retention and deletion behavior, expire access independently, and never equate Lift revocation with verified provider-side deletion;
- treat returned files, activity, provenance, and completion claims as untrusted input, verify them in quarantine, and reconcile through a durable checkpoint without direct writes to canonical state;
- preserve the prior canonical project revision and route ambiguity, missing provenance, conflicting changes, or unverifiable deletion to review;
- keep provider-computer state and credentials out of ordinary Land output and make later local Land operate only on the accepted canonical Lift revision.

No external agent-computer gateway is implemented today. These are future enablement gates, not current controls or a reason to expand the Phase 1 build.

### Cloud runtime identity binding

Treat the local spike state as untrusted input. Before a deployed-runtime action, require its exact schema, revision, run and workspace IDs, named AWS profile and region, non-root `lift-admin` principal, canonical local and cloud paths, and identifiers with expected AWS formats. Bind the caller to the exact account, principal ARN, and immutable STS user ID so deleting and recreating a same-named IAM user cannot silently inherit authority. Re-read the live CloudFormation stack by the stored stack identity and proceed only when its exact stack ID and name, safe completed status, expected parameters, and outputs match the persisted record. Resolve the instance, workspace volume, and transfer bucket through `describe-stack-resources` and require their logical type, physical ID, and resource status to match as well. Any malformed, missing, duplicated, drifted, or cross-account binding must stop the operation before Systems Manager, EC2, EBS, or S3 is used.

Every AWS subprocess must receive a sanitized inherited environment. Remove ambient AWS access keys, session credentials, profile and region selectors, global and service-specific endpoint overrides, CA-bundle and Botocore configuration, and metadata-endpoint overrides; set `AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true`; and pass the explicitly selected Lift profile and region as CLI arguments rather than ambient environment state. This prevents shell state or local configuration from redirecting otherwise valid AWS calls to a different identity or endpoint.

The disposable Phase 0 image bootstrap still downloads the official AWS CLI archive and Codex installer without pinning their installer bytes to a reviewed digest or signature. The harness verifies the resulting runtime identity and versions, but that is not equivalent to supply-chain verification. Before any real-user or external-alpha reuse, replace these mutable downloads with a signed, content-addressed image or verify published signatures and pinned digests before root execution.

Keep the local control directory owned by the current user at mode `0700` and its state and event files at `0600`. Open them relative to a no-follow directory descriptor, require owned single-link regular files, cap their size, append events through the verified descriptor, and replace state only from an exclusive random temporary file followed by file and directory `fsync`. Tighten compatible owned legacy modes once; reject symbolic links, hard links, nonregular files, foreign ownership, and oversized data without reading or modifying their referents.

Do not trust a cached base-image identifier during provisioning. Re-read its metadata and require the exact image ID, Canonical owner, `available` state, and `x86_64` architecture. These checks reduce confused-deputy and stale-state risk; they do not replace least-privilege IAM, CloudFormation drift detection, or production control-plane authentication.

### Return sync and workspace ownership

- Record an immutable handoff baseline before transferring the ownership lease from local to cloud.
- Do not treat local and cloud as simultaneous unrestricted primary writers in the first slice.
- Freeze or stop cloud writers before producing the final Land checkpoint.
- Download return changes outside the project, verify manifest signatures and content hashes, then recheck local state immediately before application.
- Apply an unchanged-local delta with a recovery journal and per-file atomic cutover; move each original into private same-filesystem recovery before installing its replacement, then revalidate preserved bytes before verification and retain them until acknowledgement.
- Validate path containment, symbolic links, file modes, case collisions, and platform-incompatible names before touching the local workspace.
- If local state diverged, preserve both sides in a branch, worktree, or sibling copy and require explicit resolution for overlaps.
- Do not delete the final cloud revision until a local helper acknowledges it or the user explicitly chooses another durable recovery destination.
- Store synthetic commits and Lift refs in an encrypted Lift-owned Git directory outside the user's project; do not write them into the user's refs or index.
- Treat private Git objects as sensitive workspace content because explicitly approved ignored files may exist in their trees.
- Never push a Lift ref, create a remote branch, or open a GitHub pull request without explicit authorization and a separate sanitized-content review.
- Keep retained session-ledger objects encrypted, scoped to one user and workspace, and inaccessible to provider processes unless required for an explicit restore.
- Delete retained session history only through an authenticated explicit user action and a documented deletion workflow; clean Land is not a deletion event.

#### Implemented fixture Land boundary

The fixture lifecycle now enforces these rules in code and local tests:

- The root-owned guest record lives with the private ledger on the encrypted workspace volume and is bound to the exact run, workspace, baseline, and EBS volume identity. Its private directory and file metadata, canonical JSON, and monotonic phases are validated before use.
- Freeze writes `FREEZE_REQUESTED` before stopping the generic workload. The runner takes the same lifecycle lock and must prove `CLOUD_PRIMARY` immediately before systemd activation, so a retry or reboot cannot reopen a writer after `LANDING` begins.
- Final capture is permitted only after runner inactivity and the absence of another process using the declared workspace writer identity are verified. `--land-final` accepts no ordinary proof source and creates only the next immutable `land-final` checkpoint.
- The final bundle and manifest are verified on EBS, written to a versioned private S3 bucket, read back by exact `VersionId`, and independently restored before local import. Local import occurs outside the project in a mode-`0700` quarantine; it verifies file metadata, hashes, the manifest self-hash and exact tree, baseline and parentage, fixture policy, bundle prerequisites, and the complete allowlisted ref map before publishing absent-or-identical private refs.
- A local acknowledgement binds the exact S3 recovery versions, final cloud commit and tree, verified local manifest, merge result, and Git-backed Land receipt. The guest accepts that acknowledgement only for its already recorded final checkpoint. Only then may both records return ownership to `LOCAL_PRIMARY`.
- A reconciliation conflict produces no acknowledgement, leaves the EBS fence and controller lease in `LANDING`, and preserves the untouched local workspace, exact final cloud state, and isolated conflict worktree. The current harness has no conflict-resolution continuation UI.
- A cached conflict response is never trusted by itself: retry rebinds the live AWS identity and stack, probes the guest writer fence and exact final checkpoint, and validates the local result, merge record, lock, private refs, and conflict worktree without repairing absent evidence.
- Compute shutdown is attempted only after acknowledgement and lease return. A cleanup failure is retained as pending rather than weakening or repeating the completed local return.

Atomic pathname cutover plus final hash revalidation detects and recovers the tested local-write races, but it cannot eliminate a write through an already-open file descriptor after the final check. Production Land still requires desktop-helper writer quiescence or a filesystem snapshot boundary before this fixture mechanism can be promoted to arbitrary workspaces.

On 2026-09-02, founder fixture run `p0-20260901083520-4fee` exercised the clean path live. It froze one `C` at checkpoint `0004-land-final`, commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, and restored the exact versioned S3 bundle and manifest. The first attempt failed closed at controller phase `FINAL_CHECKPOINT_DURABLE` on a `/run` parent-directory mode mismatch. After the permission fix, the same operation reused the same `C`, applied merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, retained receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and bound acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`; the guest reached `ACKNOWLEDGED`, the lease returned to `LOCAL_PRIMARY`, and compute stopped last.

Fresh founder fixture run `p0-20260902183748-a7b1` separately exercised a deliberate same-file conflict live. The final `C` and its exact S3 versions passed independent restore, quarantine retained complete recovery refs, and the isolated merge retained all `B/L/C` stages. The controller stopped at `NEEDS_REVIEW` with the lease `LANDING`; the original local workspace and Git state remained exact, no acknowledgement or cleanup ran, and the cloud runner could not reactivate. Repeating Land returned `changed: false` with unchanged evidence.

This verifies one clean founder-fixture execution, one deliberate-conflict execution, one specific safe resume point, and one idempotent conflict retry. It does not verify automatic offline-helper operation, user-facing conflict resolution, every interruption phase, repeated independent runs, arbitrary real-workspace transfer, or external-alpha safety.

### User-controlled agent manifests

- Display the executable, arguments, installation source, persistent paths, requested secret references, network access, and restart policy before first run.
- Represent executables and arguments separately rather than interpolating an untrusted shell string in production.
- Restrict persistent paths to the isolated user's workspace and approved home-state locations.
- Run custom agents as the unprivileged workspace user.
- Treat a custom agent as untrusted code with the same isolation and egress restrictions as repository content.

### Cost controls

- Idle-stop workspaces.
- Set per-workspace runtime and spend limits.
- Notify before a meaningful budget threshold.
- Prevent workspace credentials from provisioning arbitrary infrastructure by default.

## Prohibited MVP behavior

- Copying an entire home directory.
- Uploading browser cookies or a full authenticated browser profile.
- Copying password-manager data or an operating-system keychain.
- Copying SSH private keys.
- Sharing one filesystem or runtime among different users.
- Giving a workspace administrator-level control-plane credentials.
- Logging full environment variables.
- Opening unauthenticated preview URLs.
- Silently resolving sync conflicts by overwriting one side.

## Browser automation

Internet, browser, and computer use are required product-north-star capabilities but remain excluded from the first coding-workspace alpha until their separate security gates pass.

Delivery should proceed from bounded outbound internet, to headless Chromium for development tests, to visible browser observation, to secure user takeover, persistent project-scoped authentication, and broader visual computer use. Each expansion requires threat-model review, credential-isolation tests, revocation, recovery, and cross-agent isolation evidence.

When added, browser use must use a separate project identity or user-mediated authorization rather than migrating the user's everyday cookie database. Browser state must be visibly scoped, revocable, inaccessible to unrelated workspaces, and unavailable to agents without an explicit grant.

## Incident readiness

Before inviting external alpha users, Lift needs:

- a way to lock an account and stop all workspaces;
- workspace credential revocation;
- recoverable state snapshots;
- sufficient audit events to reconstruct access;
- a documented contact and response process;
- a clear statement of what is and is not encrypted and logged.

## Security review triggers

Perform a dedicated review before:

- introducing multi-tenant container density;
- adding browser state or browser automation;
- enabling arbitrary MCP servers;
- supporting production credentials;
- allowing inbound webhooks to trigger agents;
- adding team sharing;
- enabling shared-mode simultaneous agent writers;
- deriving workspace membership or credentials from GitHub;
- storing agent transcripts long term;
- moving from private alpha to public paid access.
