# Product and Architecture Decisions

This log records decisions already made so future work does not reopen them accidentally. Change a decision when evidence warrants it, and record why.

## Accepted decisions

### D-001: Consumer and prosumer first

Decision: Build initially for an individual agent-heavy builder, not an enterprise platform team.

Reason: The motivating behavior is personal laptop independence. Enterprise requirements would obscure the core experience.

### D-002: Replace laptop dependence before replacing GitHub

Decision: The first product is a persistent personal workspace, not a collaborative source-hosting platform.

Reason: Laptop independence produces the stronger emotional promise and matches the founder's interest.

### D-003: Infrastructure for agents, not another agent

Decision: Support existing coding agents and do not create a proprietary coding agent.

Reason: Users already have preferred agents, subscriptions, and workflows. Lift should remain useful as providers change.

### D-004: State continuity is the wedge

Decision: Differentiate through the local-to-cloud handoff rather than generic persistent compute or mobile access.

Reason: Direct competitors already provide cloud environments, phone interfaces, and several preinstalled agents.

### D-005: Selective transplant, not whole-laptop cloning

Decision: Transfer and reconstruct only the state required for the selected workspace.

Reason: Whole-device cloning is unsafe, slow, cross-platform fragile, and inconsistent with a weekend prototype.

### D-006: Semantic continuity is acceptable

Decision: Processes may restart in the cloud if the same project, goal, agent context, and visible work continue.

Reason: Transparent process migration would greatly increase complexity without being required for the user outcome.

### D-007: Phone as command surface

Decision: Prioritize direction, approval, status, changes, and previews over a full mobile code editor.

Reason: The user wants to avoid opening a laptop, not manually reproduce desktop coding on a small screen.

### D-008: Git remains underneath the initial product

Decision: Use Git concepts for versioning and reconciliation without requiring all active state to be committed or pushed.

Reason: Replacing GitHub or inventing a new distributed version-control system is unnecessary for the wedge.

### D-009: Browser-profile migration is out of MVP

Decision: Do not copy arbitrary authenticated browser state in the initial release.

Reason: Browser cookies radically expand security risk. Isolated project browser identities can be explored later.

### D-010: AWS is an acceptable initial infrastructure target

Decision: A Lift-hosted AWS prototype may use a simple VM per workspace. BYO AWS can follow.

Reason: The founder is open to AWS, and validating continuity matters more than early infrastructure density.

### D-011: Provider applications remain the interaction surface

Decision: Do not build a Lift mobile chat, approval, notification, or coding interface. Users continue through the Codex, Claude, or other provider clients they already use.

Reason: Preserving the workflow is central to the product, and recreating provider interfaces would distract from state continuity.

### D-012: EC2 and EBS are the first runtime

Decision: Use one x86_64 Ubuntu EC2 instance and a separate encrypted gp3 EBS workspace volume for the first slice.

Reason: A full Linux VM provides the fewest constraints for PTYs, arbitrary tools, authentication, background daemons, SSH, and durable state. It is the fastest way to test continuity even if a managed runtime is adopted later.

### D-013: Codex first recipe, provider-blind core

Decision: Validate Codex first because it is the founder's available provider. Run it as a reviewed recipe through the same generic workload supervisor used for any executable. Do not add Codex protocol code to Lift.

Reason: The first recipe should match the founder's real workflow without coupling process supervision, compute, state transfer, or reconciliation to OpenAI-specific behavior.

### D-014: Codex laptop-off support is gated by a spike

Decision: Treat direct ChatGPT-mobile-to-Ubuntu Codex control as experimental until a real EC2 pairing and reconnection test passes. Keep the documented ChatGPT Desktop-to-SSH path as a fallback, but do not call that fallback laptop-independent.

Reason: Official OpenAI documentation currently establishes mobile pairing through an awake Mac or Windows desktop host. Current CLI commands suggest a headless path, but the supported production behavior is not yet documented.

### D-015: Agent neutrality is one user-controlled remote workload runner

Decision: Allow a user to choose an executable, version, installation command, authentication command, run command, approved persistent state directories, network policy, and restart policy through one generic recipe. Lift may curate presets as data but will not implement provider-specific remote adapters.

Reason: Lift can supervise provider-owned remote commands without knowing their protocols. Mobile pairing and session semantics remain end to end between the user and provider and must not be faked or normalized.

### D-016: User experience is the product

Decision: The supported recurring journey is `Connect once -> select workspace -> click Lift Off -> wait for safe to close -> continue in the provider app`. Do not require a terminal, SSH, copied token, cloud console, or provider command.

Reason: Compute and remote processes are commodities. Lift's value is removing the setup and uncertainty that currently keep the laptop in the loop.

### D-017: Connections tab above the provider-blind runner

Decision: Add a Connections tab and generic connection manager driven by reviewed provider recipes. Each recipe may declare provider-owned authentication, native remote startup, readiness, encrypted state, and recovery. Keep workspace and runner code provider-neutral.

Reason: Zero-terminal onboarding and reliable one-click launch require knowledge of each provider's supported authentication and readiness behavior, but that knowledge can remain isolated from the durable workspace core.

### D-018: Safe to close is a verified product state

Decision: Display `Ready. You can close this laptop.` only after approved state is durable, the cloud workspace is healthy, the native remote workload is running, required provider readiness checks pass, and no remaining step depends on the laptop.

Reason: A false readiness claim destroys the central trust promise. File upload or process health alone is not sufficient evidence of mobile continuation.

### D-019: One-button, conflict-safe return handoff

Decision: Use an explicit workspace ownership lease: local before Lift Off, cloud while lifted, and local again only after Land completes. `Land Workspace` freezes a final cloud revision; when the desktop helper is available, Lift automatically stages, verifies, and applies it if local state has not diverged. When both sides changed, preserve both versions and route through a recoverable merge rather than overwriting either side.

Reason: Lift Off must be a round trip, but invisible bidirectional mirroring creates unacceptable data-loss risk. A handoff baseline, explicit ownership, and one-button return preserve simplicity and trust.

### D-020: Git-backed reconciliation, GitHub optional

Decision: Represent the Lift Off baseline, cloud checkpoints, and returning local state as commits in a Lift-private Git repository. Perform the Land three-way merge in an isolated worktree. On a clean merge, transactionally apply the result to the user's working tree without moving their branch or rewriting their index. Never push Lift refs or open a GitHub pull request without explicit authorization.

Reason: Git already provides proven ancestry, diff, rename detection, and three-way merge semantics. Keeping the merge repository private preserves uncommitted workspace continuity and enables a PR-like experience without requiring a GitHub remote or exposing approved ignored files.

### D-021: Every handoff has a durable session ledger

Decision: Retain the baseline, complete checkpoint chain, final cloud state, returning-local state, merge result, and Land receipt after every session, including clean merges. Store them under an immutable Lift-private session namespace until the user explicitly deletes the session, workspace, or account. Routine cleanup may remove staging and unreachable duplicates but never retained session history.

Reason: A safe merge is not the end of useful state. Persistent session history provides restore points, auditability, cross-session continuity, incident recovery, and a product-level timeline without polluting the user's repository history.

### D-022: Provider-visible workspaces are real directories on persistent storage

Decision: Place each provider-visible cloud working copy at a real path beneath the remote user's supported persistent workspace root, such as `/home/lift/workspaces/<workspace-id>`. Do not depend on a symbolic link from that root to a separately mounted working tree. Verify the provider-reported `cwd` before declaring safe-to-close.

Reason: The ChatGPT Remote folder picker accepted a real clone at `/home/lift/Workspace` but refused a symlink from that path to `/workspace`. Its default `Chat` choice created an empty projectless directory, causing the first phone task to fail safely outside the intended repository. A canonical real path and explicit `cwd` check remove both failure modes.

## Pending decisions

### P-001: Hosted versus BYO cloud first

Default hypothesis: Lift-hosted infrastructure for the fastest consumer setup.

Evidence needed: trust objections, compute economics, and willingness to connect an AWS account.

### P-002: Codex headless remote-control viability

Updated hypothesis: the current experimental CLI daemon and provider pairing URL can connect ChatGPT mobile directly to a persistent Linux workspace. A local Ubuntu precursor now passes pairing, phone task execution, one-time approvals, Git checkpoint, and clean return.

Evidence still needed: real Ubuntu EC2 repetition, network interruption, literal laptop disconnection, guest and EC2 stop/start recovery, revocation, compatible sandbox configuration, and provider-policy review.

### P-003: State transfer implementation

Options include content-addressed encrypted objects, an rsync-like protocol, Git bundle plus file delta, or a combination.

Decision criteria: correctness, speed on dirty repositories, explainability, and recovery.

### P-004: Local edits after handoff

Default hypothesis: show that the workspace is cloud-primary, detect any local divergence, and reconcile through a temporary worktree rather than silently overwriting or hard-locking local files.

Evidence needed: actual user behavior while a workspace is active in the cloud.

### P-005: Product name

`Lift` is a working name. Trademark, domain, package-name, and search-competition checks remain required before a public brand launch.

### P-006: Production runtime after EC2

Default hypothesis: evaluate Daytona VM sandboxes on BYOC AWS after the EC2 prototype proves repeat usage.

Evidence needed: utilization, wake latency, snapshot reliability, vendor risk, unit economics, and the operational cost of remaining directly on EC2.

### P-007: Remote workload recipe format

Default hypothesis: use a declarative, versioned recipe with executable and arguments represented separately, explicit persistent paths, requested secret references, network policy, restart behavior, and optional interactive authentication.

Evidence needed: Codex remote control, Claude Code Remote Control, and one unrelated CLI workload all running through the identical process supervisor without provider-specific branches.

### P-008: Provider connection credential placement

Default hypothesis: keep reusable provider credentials in a dedicated encrypted per-user vault or approved encrypted workspace state; store only nonsecret status and identifiers in the control plane.

Evidence needed: officially supported authentication behavior for each provider, reauthentication frequency, revocation behavior, snapshot-exclusion guarantees, and provider terms.

### P-009: Dashboard and desktop-helper boundary

Default hypothesis: a small signed desktop helper handles local discovery and transfer while a web dashboard owns Connections, Workspaces, Lift Off, status, and lifecycle controls.

Evidence needed: browser folder-access limitations, background transfer behavior, auto-update requirements, and the minimum native surface needed to make the journey feel like one application.

### P-010: Optional GitHub return mode

Default hypothesis: the personal default remains local Land. Later, an explicitly connected GitHub account may publish a sanitized session branch and pull request for users who want remote review or repository-policy enforcement.

Evidence needed: user demand, permission scope, behavior for forks and protected branches, CI cost, and a reliable guarantee that ignored or workspace-only content can never enter the remote branch.
