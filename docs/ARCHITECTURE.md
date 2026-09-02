# Architecture Direction

Last updated: 2026-09-02

This document defines the selected prototype direction. The first runtime is Ubuntu EC2 with EBS. One provider-blind workload runner executes any reviewed user command; Codex remote control is the first recipe used to validate it.

The product north star is broader than the implemented prototype: one durable project workspace can host multiple human and agent participants, accept new mobile-launched tasks while laptops are offline, provide controlled internet/browser/computer capabilities, and originate from a local folder, GitHub, or an empty template. See [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md).

## Current implementation cut line

The Phase 0 Python harness implements the EC2/EBS/S3 runtime driver, generated-fixture reconstruction, provider-blind runner, experimental Codex recipe/connector, stop/start recovery, challenge-bound readiness evidence, immutable restore-tested cloud checkpoints, and the fixture-only distributed Land transaction. On 2026-09-02, a clean transaction completed against the founder's live disposable environment: it froze writers on the real EC2/EBS workspace, sealed immutable checkpoint `0004-land-final` as `C`, restored and imported its exact versioned S3 objects on the Mac, reconciled with outcome `APPLIED`, persisted the exact acknowledgement on the guest, returned the lease to `LOCAL_PRIMARY`, and stopped EC2. An initial record-directory permission failure under `/run` occurred only after `C` was durable; retry safely reused that same `C`, and the permission repair was tested before successful completion. Fresh generated-fixture run `p0-20260902183748-a7b1` then exercised deliberate same-file divergence: Land sealed and restore-tested immutable `0002-land-final`, returned `NEEDS_REVIEW`, held ownership at `LANDING`, left the original local fixture untouched, retained independently recoverable local and cloud sides, kept the runner fenced, retained compute, and returned `changed: false` on retry.

This is founder-only generated-fixture evidence, not H6 acceptance or a customer or public-compatibility result. The repository still does not implement the desktop helper, dashboard, product control plane, secret broker, arbitrary real-workspace manifest, automatic wake and continuation when the local helper is offline, or conflict-resolution UI. Broader repetition and interruption coverage, production workspace isolation, provider-service credential isolation, network recovery, revocation, and the no-terminal journey remain unproven. See [`STATE_SYNC.md`](STATE_SYNC.md) and [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Architecture goals

- Complete the local-to-cloud-to-phone loop quickly.
- Preserve user work under failures and concurrent edits.
- Keep each cloud workspace isolated.
- Support more than one agent without coupling the platform to agent internals.
- Make transferred state explicit and reviewable.
- Permit a future BYO AWS mode without requiring it for the first demo.
- Preserve each agent provider's existing mobile and desktop workflow rather than building a Lift interaction layer.
- Make the supported journey one button after first-time provider connection, with no terminal or infrastructure vocabulary.
- Give each workspace a stable identity independent of origin, agent provider, participant, and compute instance.
- Accept new provider-native mobile tasks after compute stop and wake without a laptop relay.
- Support multiple agent tasks using explicit shared, isolated, or read-only execution modes.
- Add project-scoped internet, browser, and computer capabilities without importing personal-device identity.
- Use GitHub as an optional source, permission, review, and publication layer without making it the workspace itself.
- Treat Lift-hosted runtimes and supported provider-owned cloud computers as replaceable execution locations attached to one durable project identity.

## North-star logical model

```text
Workspace
├── origins: local, GitHub, empty/template
├── canonical project state and services
├── capabilities: terminal, network, browser, computer, previews
├── identities: members, agents, tasks, credentials, browser contexts
├── history: checkpoints, activity, provenance, recovery
├── task modes: shared, isolated, read-only
└── execution locations
    ├── Lift-hosted workspace runtime
    └── supported provider-owned agent computer
```

The current one-user, one-workspace, one-runner harness is a deliberately narrow implementation of this model. Product-direction additions below are architectural requirements, not claims that the code already implements them.

## System components

### 1. Lift desktop helper

Runs on the local computer and is responsible for:

- authentication;
- workspace discovery;
- state-manifest generation;
- user approval;
- consistent snapshot creation;
- encrypted upload and download;
- initiating Lift Off from the dashboard;
- reporting progress until the laptop is no longer required;
- conflict-safe reconciliation.

The helper must never modify the project merely to inspect it. A CLI may expose the same primitives for development and diagnostics, but it is not the supported happy path.

### 2. Product dashboard

Provides the consumer-facing experience:

- Connections tab for provider account setup, health, reconnect, and revoke;
- Workspaces tab with creation from this computer, GitHub, or an empty template;
- one dominant `Lift Off` action for a selected local workspace;
- plain-language progress;
- transfer review and exceptions;
- compute status and cost visibility without infrastructure terminology;
- final `Ready. You can close this laptop.` state;
- stop, wake, Land, sync status, snapshot, and delete controls.
- agent-task launch, execution mode, activity, pause, stop, and recovery controls;
- workspace participants, capabilities, permissions, and GitHub connection status.

The dashboard does not host the agent conversation. After Lift Off, it hands the user to the provider's existing phone application.

### 3. Control plane

Responsible for:

- users and sessions;
- workspace lifecycle;
- desired state and status;
- provisioning jobs;
- encrypted secret references;
- event and audit history;
- compute budgets and idle timers;
- connection state, remote-workload process status, and signed recipe metadata.
- workspace origins and durable identity;
- workspace membership and task identities;
- agent execution modes, desired state, capability grants, and provenance;
- mobile launch routing and wake requests;
- GitHub installation, repository, permission, and explicit publication metadata.

The control plane should not receive raw workspace secrets when a brokered alternative is available.

### 4. Workspace runtime

An isolated Linux machine or microVM that contains:

- a persistent encrypted project volume;
- the chosen coding-agent CLIs;
- a small Lift runtime daemon;
- terminal and process supervision;
- development preview routing;
- bounded outbound internet access;
- headless Chromium, and later visible browser/computer sessions through isolated project-scoped contexts;
- telemetry limited to operational events;
- no cross-workspace filesystem access.

For a weekend prototype, one small AWS EC2 instance per active workspace plus an EBS volume is acceptable. Container density and Firecracker-style microVM orchestration can wait until usage proves the need.

### 5. State engine

Responsible for:

- content-addressed file transfer;
- include and exclude rules;
- a versioned manifest;
- Lift-private Git snapshots and refs that never mutate the user's branch or index;
- an append-only per-session ledger retaining baseline, checkpoints, merge result, and Land receipt even after a clean merge;
- isolated three-way merge worktrees for PR-like return reconciliation;
- detection of local and cloud divergence;
- safe application of changes;
- recovery snapshots.

The state engine should distinguish files, reconstructable environment, secrets, and process declarations. Its ownership and reconciliation contract is defined in [`STATE_SYNC.md`](STATE_SYNC.md).

### 6. Provider-blind remote workload runner

The runner is responsible for:

- validating and displaying a user-owned recipe;
- running approved installation and authentication commands;
- supervising one or more arbitrary executables with explicit arguments, task identities, working directories, and capability grants;
- running an optional idempotent post-start preparation command declared by the recipe;
- evaluating an optional non-mutating semantic-readiness command independently of process health;
- attaching a raw PTY internally so the connection manager can present provider-owned browser login and pairing through the dashboard;
- persisting only approved provider-state paths;
- reporting generic process health, exit status, and restart state;
- stopping the process cleanly;
- generating a provider-neutral continuation package when a process cannot resume.

The runner does not identify, parse, or speak Codex, Claude, or another provider's remote protocol. Codex is the first recipe. Claude Code can be another recipe without a new runner implementation. See [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md).

Lift does not parse pairing output or proxy the agent conversation, approvals, or notifications. Those remain end to end between the provider process and the user's existing provider application.

A user can select an executable, pinned version, arguments, approved persistent directories, network policy, and restart policy without waiting for a Lift integration. Lift or a provider may distribute reviewed recipe presets and narrow lifecycle connectors, but these never proxy the conversation or change the workspace, transfer, or Land layers. Raw PTY attachment is an advanced diagnostic tool, not part of first-class provider setup.

### 7. Agent task manager

Deferred from the Phase 0 harness. It creates and supervises agent-task records independently of provider conversations.

Each task declares:

- initiating human or agent;
- provider and reviewed workload recipe;
- goal and workspace;
- shared, isolated, or read-only execution mode;
- working directory or isolated environment identity;
- network, secret, browser, computer, and publication grants;
- lifecycle, resource budget, activity provenance, result, and recovery checkpoint.

Shared mode binds several task processes to the same working directory. The manager checkpoints before shared writes, records task-attributed process and observed file activity, detects overlapping writes, and exposes pause and stop controls. It must present visibility and recovery honestly rather than claim it can prevent every write performed by arbitrary shell commands.

Isolated mode creates a worktree, branch, overlay, or copy-on-write environment and produces an explicit integration result. Read-only mode enforces nonmutation at the runtime boundary rather than relying only on an agent instruction.

### 8. External agent-computer gateway

Deferred from the initial product. This gateway lets a supported provider-owned cloud computer participate in a Lift task without making that computer the canonical workspace owner.

An attachment negotiates:

- authenticated provider, agent, task, workspace, and execution-location identities;
- a short-lived scoped view of the approved project state;
- shared, isolated, or read-only semantics that the provider can actually enforce;
- permitted network, secret, browser, service, and publication capabilities;
- change, command, result, and status provenance available from the provider;
- checkpoint, conflict, cancellation, expiration, and reconciliation behavior.

The preferred path is a supported provider API or workspace-attachment protocol. Depending on provider capability, the external computer may mount a remote state service, materialize a content-addressed task view, or work in an isolated copy whose result Lift imports. Lift must never imply low-latency shared-directory semantics when the actual integration is asynchronous cloning and reconciliation.

If the only supported return channel is a Git branch or pull request, Lift records it as an external result and reconciles it through the project ledger. That is useful interoperability, but it is not the same as the agent joining the live workspace. Provider computers that expose no safe attachment or export boundary remain closed substitutes.

An external worker's result is not a second whole-workspace `Land`. Lift first records an attributable task checkpoint and reconciles it into the canonical Lift workspace while preserving the prior project revision. If the user later Lands the project to a local computer, the accepted canonical workspace revision becomes cloud revision `C` in the ordinary `B/L/C` transaction. The gateway may reuse content hashes, quarantine import, Lift-private Git, and conflict-preservation primitives, but neither the provider VM nor the current EBS-specific guest journal becomes the workspace system of record.

### 9. Connection manager and recipes

The connection manager turns provider differences into one product lifecycle:

```text
DISCONNECTED -> CONNECTING -> CONNECTED -> STARTING_REMOTE -> REMOTE_RUNNING -> REMOTE_READY
                         \-> NEEDS_REAUTH                    \-> DEGRADED or ERROR
```

It is responsible for:

- rendering one Connect action from a reviewed provider recipe;
- opening provider-owned browser or device authentication;
- storing only encrypted reusable credential state and nonsecret connection metadata;
- starting the provider-owned native remote command through the generic runner;
- checking three separate layers: process liveness, provider semantic readiness, and end-to-end phone/approval proof;
- keeping idempotent provider preparation independent of transient Remote or controller presence while readiness performs those live checks;
- using a reviewed supported signal or an explicitly experimental, version-pinned signal rather than treating process health as registration;
- recovering, reconnecting, or requesting reauthentication;
- exposing optional provider deep links or unmodified session URLs;
- refusing to claim phone readiness when it cannot verify it.
- accepting and verifying a newly launched provider-native mobile task after compute wake where the provider supports it.

The connection recipe contains provider-specific data and, only when unavoidable, a small sandboxed connector implementation. It does not change workspace, transfer, Land, or generic runtime code. A healthy workload with a missing or wrong native project, root, controller, or required approval proof is `DEGRADED`; it is not restarted solely for that condition and never qualifies as `REMOTE_READY`. The current Codex spike keeps its nonsecret connector record under `/home/lift/.codex/lift/<workspace-id>/`, outside the provider-visible project. Before external alpha, the provider service and reusable credentials must also be isolated from the untrusted workspace workload by a separate service identity or an equivalently narrow brokered boundary. See [`EXPERIENCE.md`](EXPERIENCE.md) and [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md).

### 10. Runtime-provider driver

The runtime-provider driver isolates infrastructure-specific behavior:

- create, start, stop, and delete workspace compute;
- attach persistent storage;
- execute bootstrap and health commands;
- upload and download state;
- snapshot and restore;
- report lifecycle and cost-relevant status.

EC2 and EBS are the first implementation. Daytona, Fly Machines, or another runtime should be adoptable without changing remote workload recipes.

### 11. Preview gateway

Deferred from the first slice. When added, it provides authenticated access to development ports without public port exposure. Each URL should be short-lived or protected by the user's Lift session.

### 12. Browser and computer capability service

Deferred from the first coding-workspace alpha. It provides headless browser automation, visible browser sessions, visual computer use, and short-lived user takeover without exposing the workspace runtime directly.

Browser profiles are project-scoped encrypted state, separate from project files and provider credentials. Concurrent agents receive separate contexts or screens by default. Sharing an authenticated browser identity is an explicit policy decision and never follows automatically from sharing a working directory.

### 13. Secret broker

Stores encrypted secret values or references and injects them only into authorized workspace processes. It should support revocation, rotation, access logging, and per-workspace scoping.

### 14. GitHub integration

Creates cloud-native workspaces from repositories, uses short-lived GitHub App credentials, reads repository permissions where appropriate, and publishes sanitized branches or pull requests only after explicit authorization. It never treats a repository clone as the complete workspace or pushes Lift-private checkpoint state.

### 15. Workspace membership and authorization

Deferred until solo repeat use. It begins with owner, member, and viewer roles plus per-task capability grants. Human membership, provider identities, browser identities, secrets, and agent tasks remain separately revocable.

## State model

### File state

- repository base revision;
- tracked files;
- uncommitted modifications;
- untracked files;
- explicitly selected ignored files;
- Lift metadata stored outside the user's repository when possible.

### Environment state

- operating-system family and architecture;
- language and package-manager versions;
- dependency lockfiles;
- system package declarations;
- approved shell fragments;
- agent instruction and configuration files.

### Task state

- selected agent;
- current goal;
- current status;
- supported session identifier or transcript reference;
- generated continuation summary;
- recent tool results needed for continuity.
- authenticated initiator and agent-task identity;
- shared, isolated, or read-only execution mode;
- capability grants and resource budget;
- observed command and file-activity provenance;
- collision, pause, stop, result, and integration state.

### Participant state

- workspace owner and members;
- connected provider accounts and agent recipes;
- per-participant roles and grants;
- GitHub installation and repository permission evidence;
- revocation and membership history.

### Browser state

- project-scoped profile identity;
- agent context or screen identity;
- encrypted persistence and recovery policy;
- authentication and takeover state;
- network, upload, download, clipboard, and external-action policy.

### Runtime state

Do not promise transparent process migration. Record restartable declarations:

- command;
- working directory;
- safe environment references;
- ports;
- health check;
- restart policy.

## Handoff sequence

1. User selects an already-connected provider and clicks Lift Off.
2. Desktop helper inspects the project and produces manifest version N.
3. User approves only new or changed transfer exceptions; established rules apply automatically.
4. Desktop helper snapshots files against a known Git base into a Lift-private Git repository, without changing the user's branch or index, and hashes all payloads.
5. Control plane provisions or wakes the workspace.
6. State engine sends only missing encrypted objects.
7. Workspace runtime reconstructs the environment.
8. Secret broker grants scoped runtime access.
9. Connection manager validates and starts the selected remote workload through the generic runner.
10. The recipe's idempotent preparation step reconstructs provider-owned semantic state, including the exact native project/root binding where required, without depending on transient Remote or controller presence.
11. Connection manager freshly verifies runner health and reads back native provider readiness, including Remote and controller prerequisites where supported.
12. A fresh post-baseline provider task confirms its actual project/root binding.
13. The user completes any required native approval round trip through the provider interface.
14. Lift creates and restore-tests a durable checkpoint containing the verified evidence.
15. Dashboard freshly revalidates runner and native provider state and displays safe to close only for a short stated validity window.

## Return sequence

Lift uses an explicit ownership state machine for the first slice:

```text
LOCAL_PRIMARY -> LIFTING -> CLOUD_PRIMARY -> LANDING
                                                |-- clean + acknowledged -> LOCAL_PRIMARY
                                                `-- conflict -> NEEDS_REVIEW
                                                    (lease remains LANDING)
```

1. Cloud state engine checkpoints changed files into versioned manifests while the workspace is lifted.
2. The user chooses `Land Workspace`; the controller persists `LANDING`, the EBS record declares freeze intent, and Lift stops and fences every declared cloud writer.
3. Lift captures exactly one immutable final cloud revision `C`, stores its bundle and manifest as exact versioned recovery objects, and independently restore-tests them.
4. If the laptop is offline, the workspace remains `LANDING`, writers remain fenced, and exact `C` remains recoverable until the helper returns.
5. The helper downloads those exact object versions outside the project, verifies them in quarantine, and imports only the allowlisted recovery refs into Lift-private state.
6. Lift captures the current local workspace as private synthetic revision `L` without moving the user's branch, refs, real index, or working tree.
7. Lift compares `B/L/C` and performs the three-way merge in an isolated worktree. A conflict stops at `NEEDS_REVIEW`, preserves all sides, keeps the lease `LANDING`, and creates no receipt, acknowledgement, or cleanup.
8. For a clean result, the helper rechecks affected paths, applies the verified merge transactionally through a durable recovery journal, and verifies the final local manifest.
9. Lift retains the immutable Land receipt and canonical local acknowledgement for exact `C`; the guest accepts only that matching acknowledgement. Only then does Lift return the lease to `LOCAL_PRIMARY` and display `Your latest changes are back on this Mac.`
10. In the implemented fixture transaction, compute stops only after exact local and guest acknowledgement and lease return. A future explicitly designed offline pause may stop compute earlier after `C` is independently durable, but it cannot complete Land or return ownership.
11. The session ledger remains reachable and restorable after clean and conflicted outcomes; only temporary staging and unreferenced transfer data enter routine cleanup.

Never implement return as a blind directory mirror.

## Prototype stack hypothesis

This is the selected speed-oriented product hypothesis. The current feasibility code is Python; the customer-facing implementation language remains a later choice:

- Python for the current Phase 0 harness; TypeScript remains a candidate for the product helper and control-plane orchestration where practical.
- A minimal desktop helper and dashboard for Connections, Workspaces, and Lift Off.
- A generic connection state machine driven by signed declarative recipes.
- One x86_64 Ubuntu EC2 instance per prototype workspace.
- One separate encrypted 30-50 GiB gp3 EBS workspace volume.
- AWS Systems Manager for no-ingress administration.
- Restricted SSH or a mesh-network path only where the documented Codex Desktop flow requires it.
- `systemd` user services for the Codex daemon and restartable development processes.
- A reviewed rsync-like transfer for the first real dirty workspace, with content hashes and recovery snapshots.
- S3 only when needed for encrypted transfer objects or independent recovery copies.
- No Lift mobile application, conversation proxy, preview gateway, or production control-plane database in the first feasibility slice.

### Why not optimize infrastructure yet

The largest early technical risk is environment continuity, not machine density. A less elegant isolated VM that proves the experience is preferable to a sophisticated orchestration layer without a magical handoff.

## Remote workload recipes

Use one generic process contract rather than baking agent-specific assumptions into the workspace runtime.

A recipe may declare:

- installation executable and arguments;
- an interactive authentication executable and arguments;
- long-running executable, arguments, and working directory;
- an optional idempotent post-start preparation executable and arguments;
- an optional non-mutating readiness executable with normalized assertions;
- approved persistent paths and secret references;
- network and restart policy;
- provider-owned authentication presentation and readiness checks for a first-class connection.

Provider transcripts, sessions, pairing codes, account state, and remote protocols remain opaque. When provider-native resume is unavailable, use a generated continuation package and state the limitation honestly.

The first Codex recipe is tested in two provider-owned modes:

1. A headless Linux remote-control and pairing spike using the current experimental CLI commands. The founder-only provider path and clean and deliberate-conflict fixture-round-trip paths have passed once, but this is not a supported product promise until broader recovery and interruption coverage, repetition, isolation, policy, explicit real-workspace review, conflict-resolution, offline-helper, and customer-experience promotion gates pass.
2. The documented ChatGPT Desktop-to-SSH path. This validates Codex against the Lift workspace but still requires an awake Mac or Windows relay.

Never expose Codex App Server directly on a public network. The official documentation recommends SSH, VPN, or mesh networking and labels the WebSocket transport experimental.

## Reliability invariants

- Every upload has a manifest and content hashes.
- Every destructive transition has a recoverable prior revision.
- Workspace creation is idempotent.
- Stopping compute does not delete persistent state.
- Deleting a workspace requires an explicit separate action.
- Local reconciliation never silently overwrites divergent changes.
- Agent failure does not corrupt the last known-good workspace manifest.
- No cloud revision is deleted before a local helper acknowledges it or another recovery copy exists.
- Automatic return sync never overwrites a locally divergent file silently.
- Local and cloud are never both treated as the unrestricted primary writer in the first slice.
- Every agent task has one explicit execution mode and identity.
- Shared-mode writes begin from a recoverable checkpoint and remain attributable at the strongest observable runtime level.
- An overlap or collision is never silently represented as a clean agent result.
- Isolated and read-only guarantees are enforced by runtime boundaries, not prompts alone.
- Browser identities never enter project Git or ordinary Land output and are never shared merely because agents share files.
- A newly launched mobile task never qualifies as ready until its actual workspace binding is verified.
- Clean reconciliation never deletes the retained session checkpoint chain or merge history.
- A resumed Land operation reuses the exact already durable final checkpoint rather than recapturing cloud state.
