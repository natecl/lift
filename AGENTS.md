# Agent Context for Lift

This file is the operating context for coding agents working in this repository.

## Read first

Before proposing or implementing substantial work, read:

1. `README.md`
2. `docs/CURRENT_STATE.md`
3. `PRD.md`
4. `docs/CONTEXT.md`
5. `docs/ICP.md`
6. `docs/EXPERIENCE.md`
7. `docs/DECISIONS.md`
8. `docs/ROADMAP.md`
9. `docs/SECURITY.md` for anything involving execution, credentials, networking, syncing, or browser state

Before changing launch scope, pricing, analytics, support, or positioning, also read the corresponding document linked from `docs/README.md`.

## Mission

Make a user's active coding workspace independent of their laptop. The first valuable experience is a safe local-to-cloud handoff that lets an existing coding agent continue while the laptop is closed.

## Non-negotiable product constraints

- Lift is infrastructure for existing agents. Do not build a proprietary coding agent.
- Preserve the user's workflow. Codex is the first validation recipe, but the runner must accept any user-chosen remote-capable command.
- Optimize for a solo consumer or prosumer before teams or enterprise administrators.
- The MVP handles one workspace and one user.
- Build selective state transplant, not whole-device cloning.
- Do not copy a home directory, password manager, keychain, SSH private keys, or browser cookie database.
- Never silently upload secrets or ignored files. Discovery and transfer are different operations.
- Prefer an explicit, understandable state manifest over hidden magic.
- Treat the cloud workspace as untrusted execution with a narrow blast radius.
- Do not build a Lift mobile chat or IDE. The user's existing Codex, Claude, or other provider application remains the command surface.
- The supported happy path must not require a terminal, SSH, cloud console, copied token, or provider command.
- Never show “safe to close” until workspace durability and native provider remote readiness are actually verified.
- Treat a lifted workspace as single-writer by default: local before Lift Off, cloud while lifted, and local again only after Land completes.
- After `Land Workspace`, sync cloud changes back automatically when the helper reconnects and the local workspace has not diverged; otherwise preserve both sides and require an explicit resolution.

## The experience to protect

The demo should fit in one sentence: click `Lift Off`, wait for “safe to close,” close the laptop, and continue the same agent from its existing phone application.

If an implementation choice makes that loop slower, more confusing, or require infrastructure knowledge, it needs a strong reason.

## Terminology

- **Workspace**: a project and the state required to work on it.
- **Local workspace**: the source project currently on a user's computer.
- **Lift workspace**: its persistent, isolated cloud continuation.
- **State manifest**: the reviewable declaration of what Lift will reconstruct or transfer.
- **Selective transplant**: copying required project state while excluding unrelated device state.
- **Handoff**: changing where work is controlled without losing meaningful context.
- **Semantic continuity**: the same project and task can continue even if operating-system processes restart.
- **Runtime provider**: the infrastructure that supplies compute and persistent storage, initially EC2 and EBS.
- **Remote workload runner**: Lift's provider-blind process and PTY supervisor.
- **Remote workload recipe**: a reviewed, user-owned declaration of what to install and run, which paths persist, and which resources it requests.
- **Connection recipe**: the provider-specific declarative setup, authentication, launch, readiness, and recovery metadata used by Lift's generic connection manager.
- **Safe to close**: a verified state in which cloud state is durable, the native remote workload is ready, and no remaining dependency requires the laptop.
- **Handoff baseline**: the common manifest revision used to compare later local and cloud changes safely.
- **Workspace ownership lease**: the explicit state declaring whether the local or cloud workspace is currently allowed to be the primary writer.
- **Land**: finish or pause cloud work, checkpoint it, return the ownership lease, reconcile it to the local workspace when available, and optionally stop compute.

## Decision order

When requirements conflict, prioritize:

1. User security and recoverability
2. Preservation of user work
3. Time to the handoff moment
4. Consumer simplicity
5. Agent neutrality
6. Infrastructure efficiency
7. Breadth of features

## Engineering habits

- Make every state transition idempotent or recoverable.
- Use content hashes and explicit versions for synced state.
- Never overwrite local changes without showing the conflict and creating a recoverable copy.
- Use Lift-private Git objects, refs, indexes, and worktrees for reconciliation; never move the user's branch, rewrite their index, push a remote branch, or open a pull request without explicit authorization.
- Keep credentials out of images, logs, snapshots, and agent-readable files whenever possible.
- Document material product or architecture decisions in `docs/DECISIONS.md`.
- Keep the PRD accurate when scope changes.
- Prefer a thin vertical implementation of the complete handoff over disconnected infrastructure components.
