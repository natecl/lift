# Architecture Direction

This document proposes system boundaries for the prototype. It is not a final stack decision.

## Architecture goals

- Complete the local-to-cloud-to-phone loop quickly.
- Preserve user work under failures and concurrent edits.
- Keep each cloud workspace isolated.
- Support more than one agent without coupling the platform to agent internals.
- Make transferred state explicit and reviewable.
- Permit a future BYO AWS mode without requiring it for the first demo.

## System components

### 1. Lift CLI

Runs on the local computer and is responsible for:

- authentication;
- workspace discovery;
- state-manifest generation;
- user approval;
- consistent snapshot creation;
- encrypted upload and download;
- status and stop commands;
- conflict-safe reconciliation.

The CLI must never modify the project merely to inspect it.

### 2. Control plane

Responsible for:

- users and sessions;
- workspace lifecycle;
- desired state and status;
- provisioning jobs;
- encrypted secret references;
- event and audit history;
- compute budgets and idle timers;
- mobile API and notifications.

The control plane should not receive raw workspace secrets when a brokered alternative is available.

### 3. Workspace runtime

An isolated Linux machine or microVM that contains:

- a persistent encrypted project volume;
- the chosen coding-agent CLIs;
- a small Lift runtime daemon;
- terminal and process supervision;
- development preview routing;
- telemetry limited to operational events;
- no cross-workspace filesystem access.

For a weekend prototype, one small AWS EC2 instance per active workspace plus an EBS volume is acceptable. Container density and Firecracker-style microVM orchestration can wait until usage proves the need.

### 4. State engine

Responsible for:

- content-addressed file transfer;
- include and exclude rules;
- a versioned manifest;
- detection of local and cloud divergence;
- safe application of changes;
- recovery snapshots.

The state engine should distinguish files, reconstructable environment, secrets, and process declarations.

### 5. Mobile web application

The initial PWA should expose:

- workspace health and cost status;
- current agent and task;
- conversation or continuation interface;
- attention requests and approvals;
- recent commands and changed files;
- running preview;
- stop, lock, and revoke actions.

Avoid building a complete source editor in v0.

### 6. Preview gateway

Provides authenticated access to development ports without public port exposure. Each URL should be short-lived or protected by the user's Lift session.

### 7. Secret broker

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

1. CLI inspects the project and produces manifest version N.
2. User approves additions or exclusions.
3. CLI snapshots files against a known Git base and hashes all payloads.
4. Control plane provisions or wakes the workspace.
5. State engine sends only missing encrypted objects.
6. Workspace runtime reconstructs the environment.
7. Secret broker grants scoped runtime access.
8. Runtime starts the agent and declared development command.
9. Health checks pass and the preview gateway becomes available.
10. Control plane marks the workspace ready and notifies the phone.

## Return sequence

1. CLI obtains the last common manifest and current cloud manifest.
2. CLI checks whether the local workspace has diverged.
3. Nonconflicting cloud changes apply to a temporary worktree or staging directory first.
4. Conflicts create a recoverable branch or patch set.
5. User confirms application to the local workspace.
6. Cloud state remains recoverable until confirmation.

Never implement return as a blind directory mirror.

## Prototype stack hypothesis

This is a speed-oriented hypothesis, not a commitment:

- TypeScript for CLI, API, runtime daemon, and PWA where practical.
- Next.js or a small equivalent web application for control and mobile UI.
- Postgres for control-plane metadata.
- AWS EC2 for isolated prototype workspaces.
- EBS for persistent workspace volumes.
- S3 for encrypted, versioned transfer objects and recovery snapshots.
- AWS Secrets Manager or an equivalently scoped service for prototype secrets.
- WebSockets or server-sent events for terminal and agent updates.
- Cloudflare Tunnel, an authenticated reverse proxy, or an AWS-native gateway for previews.

### Why not optimize infrastructure yet

The largest early technical risk is environment continuity, not machine density. A less elegant isolated VM that proves the experience is preferable to a sophisticated orchestration layer without a magical handoff.

## Agent adapters

Use a narrow adapter interface rather than baking agent-specific assumptions into the workspace runtime.

An adapter may provide:

- installation and authentication checks;
- start and resume commands;
- structured status events where officially supported;
- transcript or session-location discovery;
- capability declarations;
- stop behavior.

Unsupported agent internals should not become hard platform dependencies. When true resume is unavailable, use a generated continuation package and state the limitation honestly.

## Reliability invariants

- Every upload has a manifest and content hashes.
- Every destructive transition has a recoverable prior revision.
- Workspace creation is idempotent.
- Stopping compute does not delete persistent state.
- Deleting a workspace requires an explicit separate action.
- Local reconciliation never silently overwrites divergent changes.
- Agent failure does not corrupt the last known-good workspace manifest.

