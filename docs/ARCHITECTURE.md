# Architecture Direction

This document defines the selected prototype direction. The first runtime is Ubuntu EC2 with EBS. One provider-blind workload runner executes any reviewed user command; Codex remote control is the first recipe used to validate it.

## Architecture goals

- Complete the local-to-cloud-to-phone loop quickly.
- Preserve user work under failures and concurrent edits.
- Keep each cloud workspace isolated.
- Support more than one agent without coupling the platform to agent internals.
- Make transferred state explicit and reviewable.
- Permit a future BYO AWS mode without requiring it for the first demo.
- Preserve each agent provider's existing mobile and desktop workflow rather than building a Lift interaction layer.
- Make the supported journey one button after first-time provider connection, with no terminal or infrastructure vocabulary.

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
- Workspaces tab with one dominant `Lift Off` action;
- plain-language progress;
- transfer review and exceptions;
- compute status and cost visibility without infrastructure terminology;
- final `Ready. You can close this laptop.` state;
- stop, wake, Land, sync status, snapshot, and delete controls.

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

The control plane should not receive raw workspace secrets when a brokered alternative is available.

### 4. Workspace runtime

An isolated Linux machine or microVM that contains:

- a persistent encrypted project volume;
- the chosen coding-agent CLIs;
- a small Lift runtime daemon;
- terminal and process supervision;
- development preview routing;
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
- supervising one arbitrary executable with explicit arguments and working directory;
- attaching a raw PTY internally so the connection manager can present provider-owned browser login and pairing through the dashboard;
- persisting only approved provider-state paths;
- reporting generic process health, exit status, and restart state;
- stopping the process cleanly;
- generating a provider-neutral continuation package when a process cannot resume.

The runner does not identify, parse, or speak Codex, Claude, or another provider's remote protocol. Codex is the first recipe. Claude Code can be another recipe without a new runner implementation. See [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md).

Lift does not parse pairing output or proxy the agent conversation, approvals, or notifications. Those remain end to end between the provider process and the user's existing provider application.

A user can select an executable, pinned version, arguments, approved persistent directories, network policy, and restart policy without waiting for a Lift integration. Lift or a provider may distribute reviewed recipe presets, but presets are data rather than provider-specific protocol code. Raw PTY attachment is an advanced diagnostic tool, not part of first-class provider setup.

### 7. Connection manager and recipes

The connection manager turns provider differences into one product lifecycle:

```text
DISCONNECTED -> CONNECTING -> CONNECTED -> STARTING_REMOTE -> REMOTE_READY
                         \-> NEEDS_REAUTH                    \-> DEGRADED or ERROR
```

It is responsible for:

- rendering one Connect action from a reviewed provider recipe;
- opening provider-owned browser or device authentication;
- storing only encrypted reusable credential state and nonsecret connection metadata;
- starting the provider-owned native remote command through the generic runner;
- checking process health and provider registration when an official signal exists;
- recovering, reconnecting, or requesting reauthentication;
- exposing optional provider deep links or unmodified session URLs;
- refusing to claim phone readiness when it cannot verify it.

The connection recipe contains provider-specific data and, only when unavoidable, a small sandboxed connector implementation. It does not change workspace, state, or runtime code. See [`EXPERIENCE.md`](EXPERIENCE.md) and [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md).

### 8. Runtime-provider driver

The runtime-provider driver isolates infrastructure-specific behavior:

- create, start, stop, and delete workspace compute;
- attach persistent storage;
- execute bootstrap and health commands;
- upload and download state;
- snapshot and restore;
- report lifecycle and cost-relevant status.

EC2 and EBS are the first implementation. Daytona, Fly Machines, or another runtime should be adoptable without changing remote workload recipes.

### 9. Preview gateway

Deferred from the first slice. When added, it provides authenticated access to development ports without public port exposure. Each URL should be short-lived or protected by the user's Lift session.

### 10. Secret broker

Stores encrypted secret values or references and injects them only into authorized workspace processes. It should support revocation, rotation, access logging, and per-workspace scoping.

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
10. Connection manager verifies provider-owned remote readiness where supported.
11. Dashboard displays safe to close only after durable state, process health, and required provider readiness checks pass.

## Return sequence

Lift uses an explicit ownership state machine for the first slice:

```text
LOCAL_PRIMARY -> LIFTING -> CLOUD_PRIMARY -> LANDING -> LOCAL_PRIMARY
```

1. Cloud state engine checkpoints changed files into versioned manifests while the workspace is lifted.
2. The user chooses `Land Workspace`; Lift pauses or stops workspace writers and creates a final durable cloud checkpoint.
3. If the laptop is offline, the workspace remains `LANDING` and the checkpoint remains recoverable until the helper returns.
4. Desktop helper reconnects and obtains the handoff baseline, current local manifest, and final cloud manifest.
5. The helper downloads the cloud delta outside the project, verifies hashes, and rechecks the local precondition immediately before applying it.
6. If local state still matches the handoff baseline, the helper applies the delta transactionally with a recovery journal and per-file atomic replacement.
7. Lift captures local return state as a private synthetic commit and performs a three-way merge with the final cloud commit in an isolated worktree. A clean result is applied transactionally; conflicts remain recoverable in that worktree or a sibling copy.
8. Only after the helper acknowledges the applied revision does Lift write an immutable Land receipt, return the ownership lease to local, and display `Your latest changes are back on this Mac.`
9. Compute may stop before the laptop reconnects, but `LANDING` is not complete until local acknowledgement or the user explicitly chooses to keep the workspace cloud-only.
10. The session ledger remains reachable and restorable after clean and conflicted merges; only temporary staging and unreferenced transfer data enter routine cleanup.

Never implement return as a blind directory mirror.

## Prototype stack hypothesis

This is the selected speed-oriented prototype:

- TypeScript for the Lift CLI and orchestration code where practical.
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
- approved persistent paths and secret references;
- network and restart policy;
- provider-owned authentication presentation and readiness checks for a first-class connection.

Provider transcripts, sessions, pairing codes, account state, and remote protocols remain opaque. When provider-native resume is unavailable, use a generated continuation package and state the limitation honestly.

The first Codex recipe is tested in two provider-owned modes:

1. A headless Linux remote-control and pairing spike using the current experimental CLI commands. This is the desired laptop-off path but is not a supported product promise until proven.
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
- Clean reconciliation never deletes the retained session checkpoint chain or merge history.
