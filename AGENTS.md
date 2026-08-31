# Agent Context for Lift

This file is the operating context for coding agents working in this repository.

## Read first

Before proposing or implementing substantial work, read:

1. `README.md`
2. `PRD.md`
3. `docs/CONTEXT.md`
4. `docs/DECISIONS.md`
5. `docs/SECURITY.md` for anything involving execution, credentials, networking, syncing, or browser state

## Mission

Make a user's active coding workspace independent of their laptop. The first valuable experience is a safe local-to-cloud handoff that lets an existing coding agent continue while the laptop is closed.

## Non-negotiable product constraints

- Lift is infrastructure for existing agents. Do not build a proprietary coding agent.
- Preserve the user's workflow. Claude Code and Codex are the initial integrations.
- Optimize for a solo consumer or prosumer before teams or enterprise administrators.
- The MVP handles one workspace and one user.
- Build selective state transplant, not whole-device cloning.
- Do not copy a home directory, password manager, keychain, SSH private keys, or browser cookie database.
- Never silently upload secrets or ignored files. Discovery and transfer are different operations.
- Prefer an explicit, understandable state manifest over hidden magic.
- Treat the cloud workspace as untrusted execution with a narrow blast radius.
- A phone interface is for directing, approving, inspecting, and previewing work. It is not a miniature desktop IDE.

## The experience to protect

The demo should fit in one sentence: run `lift up`, close the laptop, and watch the same agent continue from the phone.

If an implementation choice makes that loop slower, more confusing, or require infrastructure knowledge, it needs a strong reason.

## Terminology

- **Workspace**: a project and the state required to work on it.
- **Local workspace**: the source project currently on a user's computer.
- **Lift workspace**: its persistent, isolated cloud continuation.
- **State manifest**: the reviewable declaration of what Lift will reconstruct or transfer.
- **Selective transplant**: copying required project state while excluding unrelated device state.
- **Handoff**: changing where work is controlled without losing meaningful context.
- **Semantic continuity**: the same project and task can continue even if operating-system processes restart.

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
- Keep credentials out of images, logs, snapshots, and agent-readable files whenever possible.
- Document material product or architecture decisions in `docs/DECISIONS.md`.
- Keep the PRD accurate when scope changes.
- Prefer a thin vertical implementation of the complete handoff over disconnected infrastructure components.

