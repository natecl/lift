# Lift Product Requirements Document

Status: Draft for prototype and private alpha  
Owner: Nate  
Last updated: 2026-08-31

## 1. Summary

Lift lets a person move an active coding workspace from a laptop to a persistent cloud computer and continue controlling it through the coding-agent application they already use.

The first release focuses on one narrow promise:

> Start locally. Click Lift Off. Close the laptop. Keep building from the phone.

Lift is the infrastructure layer beneath Codex, Claude Code, and other CLI agents. It manages workspace state, execution, runtime lifecycle, and generic process supervision without replacing the agent, speaking its remote protocol, or recreating its phone and desktop clients.

## 2. Problem

Agent-heavy developers routinely keep laptops awake because their agent, files, credentials, tools, and running application all live there. Existing alternatives each impose a compromise:

- Remote-control products still depend on the laptop remaining online.
- A DIY VPS requires SSH, tmux, networking, secret management, and maintenance.
- Fresh cloud-agent sessions lack local changes, project-specific tools, configuration, and accumulated context.
- General cloud development environments require setup and are designed around an IDE or enterprise platform rather than autonomous agents.
- Provider-specific cloud modes fragment work across Claude, Codex, and other agents.

The user does not primarily need another place to clone a Git repository. They need the active working state they already created to stop depending on one physical computer.

## 3. Product thesis

As agents perform more computer work, the laptop becomes a poor server. The durable personal computer will increasingly be a cloud workspace that is always available to agents and controlled from whatever device is convenient.

Coding is the first wedge because:

- agents already operate effectively through files and terminals;
- developers tolerate early infrastructure products;
- long-running tasks make laptop dependence visible;
- project state is narrower than an entire personal computer;
- success can be demonstrated immediately.

## 4. Target user

The complete beachhead profile, anti-ICP, qualification score, triggers, alternatives, and evidence status are maintained in [`docs/ICP.md`](docs/ICP.md).

### Primary persona

An agent-native solo builder who uses Claude Code or Codex daily, often has long-running tasks, and wants to leave their desk without interrupting work.

### Qualification signals

- Uses a CLI coding agent at least four days per week.
- Has tried tmux, SSH, Tailscale, a VPS, remote desktop, Codespaces, or a mobile agent interface.
- Often has meaningful uncommitted or ignored local files.
- Has recently left a laptop awake for a coding agent or postponed an agent task to avoid doing so.
- Is willing to trust a cloud workspace if permissions and transferred state are visible.

### Not the initial user

- A large company purchasing standardized developer environments.
- A team that needs compliance, RBAC, or fleet governance first.
- A nontechnical consumer who expects every desktop application to migrate.
- A developer looking for a new AI model or autonomous software engineer.

## 5. Jobs to be done

### Core job

When an agent is working in my local project and I need to leave, move the work somewhere persistent so it can continue and I can control it from my phone without reconstructing the environment.

### Supporting jobs

- Tell me what the agent is doing and when it needs me.
- Let me approve, redirect, stop, or resume it from my phone.
- Keep my agent's existing chat, approval, and notification workflow unchanged.
- Preserve all code changes and make returning to the laptop safe.
- Reflect cloud changes back into my local workspace automatically when my laptop returns.
- Let me use my preferred coding-agent subscription or API credentials.
- Shut down idle compute without losing the workspace.

## 6. User promise and positioning

### Primary message

Close your laptop. Your agents keep building.

### Functional description

Lift teleports your active coding workspace to a persistent cloud computer so any coding agent can keep working after you close your laptop.

### Category distinction

- Not a cloud IDE: the agent is the primary interface.
- Not remote desktop: the laptop can be off.
- Not an agent: users bring Claude Code, Codex, or another supported agent.
- Not merely a VM: Lift reconstructs and safely reconciles active workspace state.

## 7. Core user journey

### First-time setup

1. User installs the Lift desktop helper and signs in.
2. User opens the Connections tab.
3. User clicks `Connect Codex` or another supported provider.
4. Lift opens the provider-owned browser authentication flow and verifies the connection.
5. User selects a local project folder.
6. Lift discovers repository state, relevant configuration, toolchain, and potentially required secrets.
7. Lift presents a plain-language state manifest and exclusions.
8. User approves what may be transferred or reconstructed.

### Handoff

1. User clicks `Lift Off`.
2. Lift captures a consistent workspace revision without altering the local project.
3. Lift provisions or wakes an isolated cloud workspace.
4. Lift uploads approved state and reconstructs the toolchain.
5. Lift starts the user's reviewed remote-workload recipe through a provider-blind process supervisor.
6. The connection manager uses the provider recipe to reuse the connected account, start native remote control, and verify provider readiness where supported.
7. Lift displays `Ready. You can close this laptop.` only when no remaining dependency requires it.
8. The user closes the laptop.

### Provider-native continuation

1. User opens the existing Codex, Claude, or other supported provider application.
2. The Lift-hosted session already appears under the same provider account without terminal setup.
3. User speaks or types instructions, handles approvals, and receives notifications through that provider.
4. Lift remains responsible only for workspace health, persistence, and explicit lifecycle commands.

### Return

1. At the end of the cloud session, the user selects `Land Workspace`.
2. Lift stops cloud writers, creates a final durable checkpoint, and waits if the laptop is still offline.
3. The Lift desktop helper reconnects and compares local and cloud revisions against the handoff baseline.
4. If only the cloud changed, Lift stages, verifies, and automatically applies the cloud delta.
5. If both changed without overlap, Lift safely assembles the nonconflicting result.
6. If changes overlap, Lift preserves both sides in a recoverable branch, worktree, or sibling copy and explains the options.
7. Only after local acknowledgement does Lift return workspace ownership to the laptop and optionally stop compute.

## 8. MVP requirements

### P0: required for the private-alpha promise

- Lift dashboard with Workspaces and Connections tabs.
- Provider-owned browser authentication initiated from a single Connect button.
- Encrypted reusable connection state that is isolated from project files.
- A no-terminal happy path after installing the Lift desktop helper.
- One-button `Lift Off` for an already-connected provider and approved workspace.
- Plain-language progress ending in an evidence-backed `safe to close` state.
- Support for a local Git repository, including tracked and uncommitted files.
- Reviewable include and exclude manifest before the first upload.
- Persistent isolated Linux workspace with durable storage.
- Codex installed using the user's existing entitlement and authenticated through an explicit user-owned flow.
- One provider-blind remote workload runner for any reviewed executable and arguments.
- A connection-recipe schema declaring provider-owned authentication, installation, remote command, readiness, persistent paths, secrets, network policy, recovery, and restart policy.
- A Codex connection recipe that keeps OpenAI protocol traffic and credentials provider-owned.
- A Codex headless remote-control feasibility spike on Ubuntu EC2.
- A documented Codex Desktop-to-SSH fallback for development and diagnostics.
- One supervised active agent session per workspace.
- Dashboard status, stop, snapshot, reconnect, revoke, and delete controls, with CLI equivalents for diagnostics.
- Safe cloud-to-local reconciliation.
- One-button `Land Workspace` with automatic verified return application when the local helper reconnects and the local workspace has not diverged.
- An explicit single-writer ownership state machine across local, lifting, cloud, landing, and local states.
- Conflict-safe preservation when local and cloud edits overlap.
- Versioned hash manifests, staged local application, and recovery journals as defined in `docs/STATE_SYNC.md`.
- Lift-private synthetic Git commits and isolated three-way merge worktrees for PR-like reconciliation without modifying the user's branch or index.
- A durable per-session ledger retaining every baseline, cloud checkpoint, final merge result, and local acknowledgement even after a clean Land.
- Explicit stop, delete, and emergency credential-revocation controls.
- Basic compute budget and idle-stop protection.

### P1: after the handoff loop works

- Multiple simultaneous agent sessions.
- Additional first-class connection recipes, including Claude Code Remote Control.
- Advanced user and community recipes that may expose manual setup when one-click support is impossible.
- Automatic runtime and dependency detection.
- Reusable personal toolchain profiles.
- Additional CLI agents.
- Authenticated development previews.
- Multiple preview ports.
- Scheduled or event-triggered work.
- BYO AWS account.
- Optional sanitized GitHub branch and pull-request return mode.

### P2: future platform

- Shared company workspaces.
- Project-level collaboration and handoffs between people.
- Browser automation with isolated, scoped identity.
- Documents and other non-code workspace types.
- A cloud-native file system spanning projects.
- Organization policy, audit, and governance.

## 9. Explicit non-goals for MVP

- Byte-for-byte operating-system or live-process migration.
- Full macOS application compatibility.
- Uploading the user's home directory.
- Migrating arbitrary browser cookies or logged-in browser profiles.
- Replacing GitHub or Git.
- Hosting models or selling inference.
- Building an IDE or full remote desktop.
- Building a Lift mobile chat, approval, or notification application.
- Making unsupported providers appear inside another provider's mobile application.
- Production deployment automation.
- Multi-user collaboration.
- Supporting every language or agent.

## 10. State-transplant model

Lift should discover more than it transfers. The user approves the boundary.

### Included candidates

- Git repository contents and metadata needed for safe reconciliation.
- Tracked and uncommitted changes.
- Explicitly selected ignored files.
- Agent instruction files such as `AGENTS.md` and `CLAUDE.md`.
- Supported agent session or continuation metadata where portable.
- Lift session metadata, goal, version fingerprints, readiness evidence, checkpoint chain, merge result, and Land receipt.
- Runtime and package-manager versions.
- Dependency manifests and lockfiles.
- Approved dotfile fragments or Lift-specific shell configuration.
- Development commands and preview-port declarations.
- Task goal, current status, and a generated continuation summary.

### Reconstructed rather than copied

- Dependencies and build artifacts.
- Language runtimes and system packages.
- Development processes.
- Agent processes.
- Terminal sessions.

### Excluded by default

- Password-manager databases and operating-system keychains.
- SSH private keys.
- Browser cookie stores and full browser profiles.
- Cloud credentials found in arbitrary files.
- Unrelated home-directory files.
- Node modules, caches, virtual environments, and large build output.
- Files outside the selected workspace.

## 11. Functional acceptance test

The prototype succeeds when a new alpha user can:

1. Start with a functioning local TypeScript project containing an uncommitted change.
2. Click Connect Codex and complete only a provider-owned browser login.
3. Select the project and review a plain-language transfer summary without opening a terminal.
4. Click Lift Off once.
5. Reach `Ready. You can close this laptop.` in under two minutes on a warm path or five minutes on a cold path.
6. Close the laptop completely and find the workspace in the existing ChatGPT mobile experience without additional setup.
7. Ask Codex for a change and verify that the Lift workspace changes while the local project remains untouched.
8. Select `Land Workspace`, reopen the laptop, and see the cloud changes automatically reflected in the local workspace without losing local work.

The stable Desktop-to-SSH flow is sufficient to validate workspace transplant and Codex execution, but it is not sufficient to claim the laptop-off mobile promise. That promise requires the headless pairing test to pass.

## 12. Success metrics

### Private-alpha gate

- 10 users install Lift.
- 5 users successfully lift a real workspace.
- 3 users perform a handoff on multiple days.
- 2 users pay or place a deposit.
- At least one user reports intentionally leaving their laptop closed because Lift exists.

### Product metrics

- Workspace-lift success rate.
- Time from Lift Off click to safe-to-close.
- Percentage of Lift Off runs requiring any terminal or manual intervention, with a target of zero for supported providers.
- Percentage of lifted workspaces continued through an existing provider client.
- Successful cloud-to-local reconciliation rate.
- Percentage of Land operations applied automatically after the single Land action.
- Number of handoffs per active user per week.
- Provider remote connections established successfully.
- Native provider sessions visible from mobile after Lift Off.
- Provider reauthentication rate and completion time.
- Compute cost per active workspace hour.
- Security or data-loss incidents, with a target of zero.

### Guardrail metrics

- Unexpected files uploaded.
- Secrets detected in logs, images, or snapshots.
- Sync conflicts that require manual recovery.
- Cloud revisions not acknowledged by any local helper.
- Workspaces left running unintentionally.
- Users abandoning during environment reconstruction.
- False safe-to-close confirmations.

## 13. Business model hypotheses

Do not optimize pricing before repeat usage is proven.

Potential initial models:

- Monthly subscription plus metered compute.
- Higher fixed monthly price with an included compute allowance.
- Free local CLI with paid hosted workspaces.
- Later, BYO AWS for advanced users with a smaller control-plane fee.

The private alpha should test willingness to pay against the completed handoff, not a survey description.

## 14. Major risks

- CloudCLI or first-party agent vendors absorb the local handoff use case.
- Agent session formats are proprietary or not safely portable.
- Environment discovery works on demos but fails on real projects.
- Uploading state and restoring dependencies makes handoff too slow.
- Secrets or authenticated state create unacceptable exposure.
- Bidirectional sync causes lost work or confusing conflicts.
- Return application surprises an open editor, unsaved buffer, or development process.
- Mobile interaction is too limited to replace opening the laptop.
- Codex's supported phone path continues to require an awake Mac or Windows desktop relay.
- Experimental Codex headless pairing changes or is unavailable to third-party infrastructure.
- Provider account authentication cannot be legally or technically embedded into Lift's no-terminal Connections flow.
- A provider process appears healthy while its native mobile registration has failed.
- Compute costs make a consumer price unattractive.
- “Replace the laptop” creates expectations far beyond the coding wedge.

## 15. Open questions

- Does current Codex headless remote-control pairing work reliably from Ubuntu EC2 to ChatGPT mobile?
- Which exact Codex state can be resumed without depending on unsupported internals?
- What is the smallest desktop helper required for one-button local discovery and transfer?
- Should v0 use Lift-hosted infrastructure or the user's AWS account?
- Can the helper reliably detect or warn about unsaved editor buffers before applying a Land revision?
- Should reopening a lifted workspace offer one-click Land or automatically Land only when no cloud writer is active?
- Is the connection-recipe schema expressive enough for Codex, Claude Code, and a genuinely unrelated CLI agent without coupling the workspace core to provider code?
- Can an encrypted workspace remain stopped while still waking quickly enough?
