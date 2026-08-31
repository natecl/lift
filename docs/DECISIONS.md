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

## Pending decisions

### P-001: Hosted versus BYO cloud first

Default hypothesis: Lift-hosted infrastructure for the fastest consumer setup.

Evidence needed: trust objections, compute economics, and willingness to connect an AWS account.

### P-002: Official session resume versus continuation package

Default hypothesis: use official resume paths when stable and a generated continuation package otherwise.

Evidence needed: supported behavior and portability of Claude Code and Codex session state.

### P-003: State transfer implementation

Options include content-addressed encrypted objects, an rsync-like protocol, Git bundle plus file delta, or a combination.

Decision criteria: correctness, speed on dirty repositories, explainability, and recovery.

### P-004: Local edits after handoff

Default hypothesis: warn that the workspace is lifted, detect divergence, and reconcile through a temporary worktree rather than locking local files.

Evidence needed: actual user behavior while a workspace is active in the cloud.

### P-005: Product name

`Lift` is a working name. Trademark, domain, package-name, and search-competition checks remain required before a public brand launch.

