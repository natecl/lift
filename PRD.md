# Lift Product Requirements Document

Status: Draft for prototype and private alpha  
Owner: Nate  
Last updated: 2026-08-31

## 1. Summary

Lift lets a person move an active coding workspace from a laptop to a persistent cloud computer and continue controlling existing coding agents from a phone or another computer.

The first release focuses on one narrow promise:

> Start locally. Run one command. Close the laptop. Keep building from the phone.

Lift is the infrastructure layer beneath Claude Code, Codex, and other CLI agents. It manages workspace state, execution, access, previews, notifications, and safety without replacing the agent itself.

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

### Primary persona

An agent-native solo builder who uses Claude Code or Codex daily, often has long-running tasks, and wants to leave their desk without interrupting work.

### Qualification signals

- Uses a CLI coding agent at least four days per week.
- Has tried tmux, SSH, Tailscale, a VPS, remote desktop, Codespaces, or a mobile agent interface.
- Often has meaningful uncommitted or ignored local files.
- Runs a local development server and wants to inspect the preview remotely.
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
- Let me open the application preview it created.
- Preserve all code changes and make returning to the laptop safe.
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

1. User installs the Lift CLI.
2. User signs in through the browser.
3. User runs `lift inspect` inside a project.
4. Lift discovers repository state, relevant configuration, toolchain, and potentially required secrets.
5. Lift presents a state manifest and exclusions.
6. User approves what may be transferred or reconstructed.

### Handoff

1. User runs `lift up`.
2. Lift captures a consistent workspace revision without altering the local project.
3. Lift provisions or wakes an isolated cloud workspace.
4. Lift uploads approved state and reconstructs the toolchain.
5. Lift starts the selected agent and development processes.
6. Lift verifies health and returns a phone URL or deep link.
7. The user closes the laptop.

### Mobile continuation

1. User sees agent status, current task, recent actions, changed files, and requests for approval.
2. User can speak or type a new instruction.
3. User can approve or deny a sensitive action.
4. User can open a protected preview URL.
5. User receives a notification when the agent is done, blocked, or needs approval.

### Return

1. User runs `lift pull` or opens Lift on the laptop.
2. Lift compares local and cloud revisions.
3. If only the cloud changed, Lift applies the changes safely.
4. If both changed, Lift creates a conflict-safe branch or worktree and explains the options.
5. The cloud workspace may stop while its encrypted volume persists.

## 8. MVP requirements

### P0: required for the private-alpha promise

- CLI authentication and one-command workspace creation.
- Support for a local Git repository, including tracked and uncommitted files.
- Reviewable include and exclude manifest before the first upload.
- Persistent isolated Linux workspace with durable storage.
- Claude Code and Codex installed or installable using the user's existing entitlement.
- One active agent session per workspace.
- Mobile web interface for status, conversation, approvals, terminal output, and stop.
- Secure preview URL for one detected development port.
- Push notification or equivalent when attention is required.
- Safe cloud-to-local reconciliation.
- Explicit stop, delete, and emergency credential-revocation controls.
- Basic compute budget and idle-stop protection.

### P1: after the handoff loop works

- Multiple simultaneous agent sessions.
- Voice input optimized for directing agents.
- Automatic runtime and dependency detection.
- Reusable personal toolchain profiles.
- Additional CLI agents.
- Multiple preview ports.
- Scheduled or event-triggered work.
- BYO AWS account.

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
2. Run one command and review what will move.
3. Reach a healthy cloud workspace in under two minutes on a warm path or five minutes on a cold path.
4. Close the laptop completely.
5. Continue the coding-agent conversation from a phone.
6. Open the application preview from the phone.
7. Ask the agent for a change and see it reflected in the preview.
8. Return to the laptop and recover the cloud changes without losing local work.

## 12. Success metrics

### Private-alpha gate

- 10 users install Lift.
- 5 users successfully lift a real workspace.
- 3 users perform a handoff on multiple days.
- 2 users pay or place a deposit.
- At least one user reports intentionally leaving their laptop closed because Lift exists.

### Product metrics

- Workspace-lift success rate.
- Time from command to healthy cloud workspace.
- Percentage of lifted workspaces continued from mobile.
- Successful cloud-to-local reconciliation rate.
- Number of handoffs per active user per week.
- Agent attention requests resolved from mobile.
- Compute cost per active workspace hour.
- Security or data-loss incidents, with a target of zero.

### Guardrail metrics

- Unexpected files uploaded.
- Secrets detected in logs, images, or snapshots.
- Sync conflicts that require manual recovery.
- Workspaces left running unintentionally.
- Users abandoning during environment reconstruction.

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
- Mobile interaction is too limited to replace opening the laptop.
- Compute costs make a consumer price unattractive.
- “Replace the laptop” creates expectations far beyond the coding wedge.

## 15. Open questions

- Which exact state can be resumed for Claude Code and Codex without depending on unsupported internals?
- Is the first command `lift`, `lift up`, or an always-running local daemon?
- Should v0 use Lift-hosted infrastructure or the user's AWS account?
- Does the first version support local-to-cloud return syncing or require Git as the return path?
- How should local edits made after lifting be handled?
- What is the smallest useful mobile interface beyond agent chat and approvals?
- Can an encrypted workspace remain stopped while still waking quickly enough?

