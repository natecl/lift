# Security Baseline

Lift will execute powerful autonomous tools against source code and credentials on remote infrastructure. Security is part of the initial product definition.

## Security objectives

- Compromise of one workspace does not expose another workspace or the control plane.
- An agent can access only the project, tools, network destinations, and credentials it requires.
- Users can see and revoke access.
- Secrets do not appear in images, snapshots, logs, manifests, or source-control changes.
- Local and cloud work remain recoverable after compromise or operator error.
- No file leaves the local computer merely because Lift discovered it.

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

### Cloud runtime identity binding

Treat the local spike state as untrusted input. Before a deployed-runtime action, require its exact schema, revision, run and workspace IDs, named AWS profile and region, non-root `lift-admin` principal, canonical local and cloud paths, and identifiers with expected AWS formats. Re-read the live CloudFormation stack by the stored stack identity and proceed only when its exact stack ID and name, safe completed status, expected parameters, and outputs match the persisted record. Resolve the instance, workspace volume, and transfer bucket through `describe-stack-resources` and require their logical type, physical ID, and resource status to match as well. Any malformed, missing, duplicated, drifted, or cross-account binding must stop the operation before Systems Manager, EC2, EBS, or S3 is used.

The disposable Phase 0 image bootstrap still downloads the official AWS CLI archive and Codex installer without pinning their installer bytes to a reviewed digest or signature. The harness verifies the resulting runtime identity and versions, but that is not equivalent to supply-chain verification. Before any real-user or external-alpha reuse, replace these mutable downloads with a signed, content-addressed image or verify published signatures and pinned digests before root execution.

Keep the local control directory owned by the current user at mode `0700` and its state and event files at `0600`. Open them relative to a no-follow directory descriptor, require owned single-link regular files, cap their size, append events through the verified descriptor, and replace state only from an exclusive random temporary file followed by file and directory `fsync`. Tighten compatible owned legacy modes once; reject symbolic links, hard links, nonregular files, foreign ownership, and oversized data without reading or modifying their referents.

Do not trust a cached base-image identifier during provisioning. Re-read its metadata and require the exact image ID, Canonical owner, `available` state, and `x86_64` architecture. These checks reduce confused-deputy and stale-state risk; they do not replace least-privilege IAM, CloudFormation drift detection, or production control-plane authentication.

### Return sync and workspace ownership

- Record an immutable handoff baseline before transferring the ownership lease from local to cloud.
- Do not treat local and cloud as simultaneous unrestricted primary writers in the first slice.
- Freeze or stop cloud writers before producing the final Land checkpoint.
- Download return changes outside the project, verify manifest signatures and content hashes, then recheck local state immediately before application.
- Apply an unchanged-local delta with a recovery journal and per-file atomic replacement; retain a pre-apply recovery copy until acknowledgement.
- Validate path containment, symbolic links, file modes, case collisions, and platform-incompatible names before touching the local workspace.
- If local state diverged, preserve both sides in a branch, worktree, or sibling copy and require explicit resolution for overlaps.
- Do not delete the final cloud revision until a local helper acknowledges it or the user explicitly chooses another durable recovery destination.
- Store synthetic commits and Lift refs in an encrypted Lift-owned Git directory outside the user's project; do not write them into the user's refs or index.
- Treat private Git objects as sensitive workspace content because explicitly approved ignored files may exist in their trees.
- Never push a Lift ref, create a remote branch, or open a GitHub pull request without explicit authorization and a separate sanitized-content review.
- Keep retained session-ledger objects encrypted, scoped to one user and workspace, and inaccessible to provider processes unless required for an explicit restore.
- Delete retained session history only through an authenticated explicit user action and a documented deletion workflow; clean Land is not a deletion event.

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

Authenticated cloud browser use is strategically important but excluded from the first coding-workspace alpha.

When added, it should use a separate browser identity or user-mediated authorization rather than migrating the user's everyday cookie database. Browser state should be isolated per project, visibly scoped, revocable, and inaccessible to unrelated agents.

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
- storing agent transcripts long term;
- moving from private alpha to public paid access.
