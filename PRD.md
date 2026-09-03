# Lift Product Requirements Document

Status: Draft for prototype and private alpha  
Owner: Nate  
Last updated: 2026-09-02

## 1. Summary

Lift gives every software project a persistent cloud workspace where developers and AI agents can work together from any device. The workspace is independent of any one laptop, agent provider, conversation, or compute instance.

The first release validates that larger product through one narrow promise:

> Start locally. Click Lift Off. Close the laptop. Keep building from the phone.

Lift is the infrastructure layer beneath Codex, Claude Code, Grok, Cursor, and other remote-capable agents. It manages workspace state, execution, runtime lifecycle, internet and browser capabilities, agent coordination, and recovery without replacing the agent or recreating its provider-owned phone and desktop clients.

A workspace may be created from an active local folder, a GitHub repository, or an empty environment. It may support one agent, multiple agents working in a shared directory, isolated agent tasks, and eventually multiple human collaborators. See [`docs/PRODUCT_NORTH_STAR.md`](docs/PRODUCT_NORTH_STAR.md).

### Current implementation state

The merged Phase 0 baseline proves the experimental Codex provider path once on a generated disposable workspace: real EC2/EBS, direct provider-native phone control, one stop/start recovery, guarded approval/proof evidence, three immutable restore-tested checkpoints, and a short-lived `safeToClose: true` verdict. On 2026-09-02, founder fixture run `p0-20260901083520-4fee` also passed one clean live Land transaction. Its exact versioned S3 bundle and manifest restored checkpoint `0004-land-final` at commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`. After a first attempt stopped safely at `FINAL_CHECKPOINT_DURABLE` on a `/run` parent-directory mode mismatch, the fixed retry reused that same `C`, produced `APPLIED` merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`; the guest reached `ACKNOWLEDGED`, the controller lease returned to `LOCAL_PRIMARY`, and compute stopped last.

A fresh disposable run, `p0-20260902183748-a7b1`, then passed the live deliberate-conflict path. Different local and cloud bytes for the same tracked file produced restore-tested checkpoint `0002-land-final` at commit `722adcffd8ebba70fb222cfbb1f749b0f5e479bc`, tree `3aa8260a33ec8e8c50b8f277aa2118fd8b88770b`, followed by `NEEDS_REVIEW` with both ownership records held at `LANDING`. The original local workspace and Git state were unchanged, the isolated private worktree retained exact baseline/local/cloud stages, no acknowledgement or compute cleanup occurred, the cloud writer remained fenced, and an immediate retry returned `changed: false` without mutating the recorded operation.

This accepts the generated-fixture Land core, not the customer product or H6. A separate local-only policy foundation now implements real-workspace discovery, exact scoped per-path approval, strict portable-policy decoding, and rule-based return classification; its focused suite passes 77 tests. It does **not** implement generic B, upload, EC2 reconstruction, checkpoint, Land, receipt, or customer review UI integration. The dashboard/helper, automatic offline-helper reconnection, conflict-resolution UI, and broader interruption and repetition evidence also remain pending. See [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) and [`docs/WORKSPACE_POLICY.md`](docs/WORKSPACE_POLICY.md).

## 2. Problem

Developers are becoming managers of agents, but their projects still live on fragile personal computers or inside provider-specific cloud sessions. Agent-heavy developers routinely keep laptops awake because their agents, files, credentials, tools, browsers, services, and running applications all live there. Existing alternatives each impose a compromise:

- Remote-control products still depend on the laptop remaining online.
- A DIY VPS requires SSH, tmux, networking, secret management, and maintenance.
- Fresh cloud-agent sessions lack local changes, project-specific tools, configuration, and accumulated context.
- General cloud development environments require setup and are designed around an IDE or enterprise platform rather than autonomous agents.
- Provider-specific cloud modes fragment work across Claude, Codex, and other agents.
- Multiple agents duplicate setup, collide in shared files, or produce disconnected changes with unclear ownership.
- Team members cannot easily enter the same functioning project environment or see what human and agent participants changed.

The user does not primarily need another place to clone a Git repository. They need the project to have a permanent, safe working environment that does not depend on one physical computer or one agent provider.

## 3. Product thesis

As agents perform more computer work, the laptop becomes a poor server. The durable unit will increasingly be a project-centric cloud workspace that is always available to its developers and agents and controlled from whatever device is convenient.

GitHub remains the source-history, permission, and review layer. Lift becomes the live environment where code is in motion: files, dependencies, services, browsers, agent tasks, collaborators, checkpoints, and activity. Provider labs may bundle cloud agents, but Lift remains useful only if the workspace survives changing agents, models, devices, conversations, team members, and eventually runtime providers.

Coding is the first wedge because:

- agents already operate effectively through files and terminals;
- developers tolerate early infrastructure products;
- long-running tasks make laptop dependence visible;
- project state is narrower than an entire personal computer;
- success can be demonstrated immediately.

## 4. Target user

The complete beachhead profile, anti-ICP, qualification score, triggers, alternatives, and evidence status are maintained in [`docs/ICP.md`](docs/ICP.md).

### Primary persona

An agent-native solo builder or highly autonomous product engineer who uses coding agents daily, often has long-running or parallel tasks, and wants the project to remain available after leaving the desk.

### Qualification signals

- Uses a CLI coding agent at least four days per week.
- Has tried tmux, SSH, Tailscale, a VPS, remote desktop, Codespaces, or a mobile agent interface.
- Often has meaningful uncommitted or ignored local files.
- Has recently left a laptop awake for a coding agent or postponed an agent task to avoid doing so.
- Wants to launch new agent tasks from a phone while the laptop is offline.
- Uses more than one coding agent, or expects to as parallel agent work becomes normal.
- Is willing to trust a cloud workspace if permissions and transferred state are visible.

### Not the initial user

- A large company purchasing standardized developer environments.
- A team that needs compliance, RBAC, or fleet governance first.
- A nontechnical consumer who expects every desktop application to migrate.
- A developer looking for a new AI model or autonomous software engineer.

### First adjacent persona

A small AI-native startup team that wants one persistent, functioning project workspace for developers and heterogeneous agents without operating its own developer-platform stack. This segment follows solo repeat use rather than expanding the first alpha into enterprise administration.

## 5. Jobs to be done

### Core job

Give my project a permanent, safe workspace where I and my agents can work from anywhere without keeping a laptop online or rebuilding the environment.

### First validated job

When an agent is working in my local project and I need to leave, move the work somewhere persistent so it can continue, let me launch or continue agent tasks from my phone, and safely bring the result back.

### Supporting jobs

- Tell me what the agent is doing and when it needs me.
- Let me launch a new agent into the correct workspace from my phone while the laptop is offline.
- Let me approve, redirect, stop, or resume it from my phone.
- Keep my agent's existing chat, approval, and notification workflow unchanged.
- Let several agents share the current workspace when collaboration is useful or use isolated task environments when safety matters more.
- Attribute commands and file changes to the human or agent that produced them.
- Let a small team enter the same functioning workspace without sharing a personal computer or provider account.
- Give agents controlled internet, browser, and computer capabilities required to finish real work.
- Preserve all code changes and make returning to the laptop safe.
- Reflect cloud changes back into my local workspace automatically when my laptop returns.
- Let me use my preferred coding-agent subscription or API credentials.
- Shut down idle compute without losing the workspace.

## 6. User promise and positioning

### Primary message

The cloud workspace for developers and AI agents.

### Hero experience

Close your laptop. Launch your agents from anywhere.

### Functional description

Lift gives every software project a persistent cloud workspace where developers and AI agents can work together from any device. Start from a local folder, GitHub, or an empty environment; then launch agents from a phone or laptop without keeping personal compute online.

### Category distinction

- Not a cloud IDE: the agent is the primary interface.
- Not remote desktop: the laptop can be off.
- Not an agent: users bring Claude Code, Codex, or another supported agent.
- Not merely a VM: Lift owns durable project state, participants, capabilities, coordination, provenance, and recovery.
- Not Git hosting: GitHub remains the repository and review backbone while Lift owns the live workspace.

## 7. Core user journey

### Create workspace

The user chooses one of three equivalent creation paths:

1. `From this computer`: select an active local folder, review its manifest, and Lift Off.
2. `From GitHub`: select a repository and create a persistent cloud-native workspace.
3. `Empty workspace`: start from a reviewed template or blank environment.

Every path produces the same durable workspace identity and can connect GitHub or additional agent providers later.

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
3. User can launch a completely new agent task into the Lift workspace, not only continue a process started before the laptop closed.
4. User speaks or types instructions, handles approvals, and receives notifications through that provider.
5. Lift wakes stopped compute where supported and verifies that each task is bound to the intended project root and capabilities.
6. Lift remains responsible for workspace health, persistence, task mode, activity, stop controls, and explicit lifecycle commands.

### Multi-agent work

1. User starts additional agent tasks from a phone, laptop, or provider client.
2. Each task uses the workspace default or an explicit mode: shared, isolated, or read-only.
3. Shared tasks see one working directory immediately; Lift checkpoints before the run, attributes activity, detects overlapping writes, and preserves recoverable prior versions.
4. Isolated tasks use a worktree, branch, or copy-on-write environment and return a reviewable integration result.
5. Read-only tasks can inspect, test, and review without modifying files.
6. The user can see, pause, stop, and review every active task without understanding infrastructure.

### Cloud-native continuation

1. A GitHub-created or empty workspace remains the project's durable cloud home.
2. The user launches new agent tasks on later days without reconstructing the environment or performing another local transfer.
3. The workspace retains approved services, tools, state, policies, checkpoints, and provider connections across compute stop and wake.
4. The user may later clone, export, publish through GitHub, or Land the workspace locally.

### Return

1. At the end of the cloud session, the user selects `Land Workspace`.
2. Lift stops cloud writers, creates a final durable checkpoint, and waits if the laptop is still offline.
3. The Lift desktop helper reconnects and compares local and cloud revisions against the handoff baseline.
4. If only the cloud changed, Lift stages, verifies, and automatically applies the cloud delta.
5. If both changed without overlap, Lift safely assembles the nonconflicting result.
6. If changes overlap, Lift preserves both sides in a recoverable branch, worktree, or sibling copy and explains the options.
7. Only after durable local acknowledgement and the matching guest acknowledgement does Lift return workspace ownership to the laptop and optionally stop compute.

## 8. MVP requirements

### Product-north-star requirements

These requirements define the product even when delivery is staged behind the first handoff proof:

- A durable workspace identity independent of its creation source, agent provider, conversation, user device, and compute instance.
- Replaceable execution locations: agents may run in a Lift-hosted runtime or, through a supported scoped integration, on a provider-owned cloud computer without moving canonical project ownership out of Lift.
- Workspace creation from an approved local folder, GitHub, or an empty reviewed template.
- Provider-native mobile launch of new agent tasks while the laptop is offline where provider capability permits it.
- Multiple agent tasks with configurable shared, isolated, and read-only execution modes.
- Pre-run checkpoints, per-agent activity attribution, overlap detection, pause and stop controls, and recovery for shared writes.
- Controlled outbound internet, headless browser automation, visible browser observation, secure user takeover, and project-scoped persistent browser identity.
- GitHub-native authentication, repository import, explicit sanitized publication, branches, pull requests, and permission mapping without making GitHub mandatory.
- Human collaboration built on explicit workspace membership, task identity, scoped secrets, and auditability.
- A workspace control surface for health, agents, capabilities, permissions, cost, snapshots, recovery, and deletion; provider clients remain the preferred agent conversation surfaces.

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

- Persistent reuse of the same cloud workspace across days without a new local transfer.
- Repeatable provider-native launch of completely new agent tasks after stopped-compute wake, using the same persistent workspace without another local transfer.
- Multiple simultaneous agent sessions, beginning with shared mode plus attribution, overlap detection, and recovery.
- Optional isolated and read-only task modes.
- GitHub-created and empty workspaces.
- Additional first-class connection recipes, including Claude Code Remote Control.
- Advanced user and community recipes that may expose manual setup when one-click support is impossible.
- Automatic runtime and dependency detection.
- Reusable personal toolchain profiles.
- Additional CLI agents.
- Headless Chromium and Playwright-style browser testing.
- Authenticated development previews.
- Multiple preview ports.
- Scheduled or event-triggered work.
- BYO AWS account.
- Optional sanitized GitHub branch and pull-request return mode.

### P2: future platform

- Visible Chrome or Chromium with visual computer use and secure user takeover.
- Persistent project-scoped browser identities and separate contexts for concurrent agents.
- Team-lite shared workspaces with GitHub-derived access.
- Project-level collaboration, human and agent presence, and handoffs.
- Workspace-level permissions, scoped secrets, activity provenance, and integration policy.
- Project-linked non-code artifacts needed to build and operate software, only after the coding-workspace use case retains.
- A cross-workspace catalog and control plane that preserves project isolation rather than creating one shared filesystem across projects.
- Organization policy, audit, and governance.
- Supported attachment of provider-owned agent computers through short-lived task identity, scoped state and capabilities, attributable result ingestion, and checkpointed reconciliation.

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
7. Launch a new Codex task from the phone into the correct Lift workspace, not only continue a pre-existing process.
8. Ask Codex for a change and verify that the Lift workspace changes while the local project remains untouched.
9. Select `Land Workspace`, reopen the laptop, and see the cloud changes automatically reflected in the local workspace without losing local work.

### North-star platform test

After the handoff acceptance test repeats and supports payment, the platform direction succeeds when a user can:

1. Create the same class of durable workspace from a local folder, GitHub repository, or empty/template start, and later clone or Land it locally without changing its Lift identity or retained history.
2. Reuse it on several days without environment reconstruction.
3. Launch at least two agents from mobile or desktop surfaces, including two distinct provider families using the same retained workspace without reconstruction.
4. Let agents work in a shared directory with visible attribution and recoverable collision handling, or select isolation for independent work.
5. Give an agent controlled internet and browser access for an end-to-end task.
6. Invite a teammate through explicit project permissions.
7. Review and publish the result through GitHub without exposing workspace-only state.
8. Restore the workspace onto replacement compute without changing its workspace identity, retained history, or recovery chain; later repeat across a second supported runtime provider.

The stable Desktop-to-SSH flow is sufficient to validate workspace transplant and Codex execution, but it is not sufficient to claim the laptop-off mobile promise. A founder-only Ubuntu EC2 run has now demonstrated direct phone control and strongly corroborated a powered-off Mac through a fresh challenge/proof exchange and reboot timestamps. A subsequent EC2 stop/start preserved the exact encrypted EBS workspace, earlier checkpoints and proof files, the provider-neutral runner, and the exact Codex Remote environment. After server-side native-project reconstruction, a fresh post-baseline phone task passed exact folder/runtime binding with `projectId: null`, guarded approval observation, proof, following checkpoint, exact-version restore, and fresh safe-to-close evaluation once. Founder fixtures later passed both one resumable clean EC2-to-Mac Land transaction—including exact final-checkpoint restore, local application, two-sided acknowledgement, lease return, and post-ack compute stop—and one fresh deliberate-conflict transaction that preserved exact `B/L/C`, left local state untouched, retained `LANDING`, fenced cloud writers, and produced no acknowledgement or cleanup. This remains Phase 0 fixture evidence rather than a public compatibility or full product claim. The capture harness still accepts only its generated disposable fixture and is not evidence of safe arbitrary-project transfer. The local reviewed-policy foundation has no transfer or live-loop integration. Separate provider-service identity and credential isolation are pre-alpha gates; policy-bound real-workspace capture, network recovery, revocation, repeated clean/conflict runs and broader interruption coverage, automatic offline-helper continuation, and the zero-terminal product journey remain pending.

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
- New mobile agent tasks successfully launched while the originating laptop is offline.
- Weekly active cloud workspaces with a useful completed agent task.
- Workspaces reused on multiple days without reconstruction.
- Workspaces with two or more agent tasks.
- Shared-mode overlap warnings, recoveries, and unrecovered collisions.
- GitHub-created workspaces and accepted workspace-originated pull requests.
- Empty/template workspace creation and successful later clone or Land with identity and history preserved.
- Collaborator invitations, joins, and retained team workspaces.
- Provider mix and successful provider switches per retained workspace without reconstruction.
- Successful restore to replacement compute without workspace-identity or history loss.
- Second-month paid renewal.
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
- Unattributed or unrecoverable shared-agent writes.
- Browser credentials exposed across workspaces, agents, or snapshots.

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
- First-party providers bundle sufficiently capable persistent multi-agent computers and make a separate workspace product unnecessary.
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
- Shared-mode agents overwrite or destabilize one another's work faster than Lift can attribute and recover it.
- Browser and computer capabilities expose credentials or turn a project compromise into broader account compromise.
- The platform vision adds breadth before the solo workspace demonstrates repeat use and payment.

## 15. Open questions

- Does the once-passed post-stop/start Codex phone path remain repeatable across users, independent runs, network interruption, reauthentication, and provider releases?
- Which exact Codex state can be resumed without depending on unsupported internals?
- What is the smallest desktop helper required for one-button local discovery and transfer?
- Should v0 use Lift-hosted infrastructure or the user's AWS account?
- Can the helper reliably detect or warn about unsaved editor buffers before applying a Land revision?
- Should reopening a lifted workspace offer one-click Land or automatically Land only when no cloud writer is active?
- Is the connection-recipe schema expressive enough for Codex, Claude Code, and a genuinely unrelated CLI agent without coupling the workspace core to provider code?
- Can an encrypted workspace remain stopped while still waking quickly enough?
- What is the simplest provider-native mechanism for launching a new task from a phone into an existing Lift workspace after compute stop and wake?
- Should shared, isolated, or read-only execution be the default for the first multi-agent cohort?
- Which file-activity and checkpoint guarantees make shared-agent writing understandable and recoverable without pretending arbitrary shell writes can always be prevented?
- Which browser capability is required first: headless testing, visible observation, secure takeover, or persistent authentication?
- How much of GitHub identity and repository permission should Lift inherit before team invitations are enabled?
