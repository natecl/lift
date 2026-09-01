# Lift

Close your laptop. Your agents keep building.

Lift is a persistent personal cloud computer for coding agents. Its first product is one-button workspace teleportation: begin in a real local project, click `Lift Off`, move the workspace to the cloud, and continue through the Codex, Claude, or other agent interface you already use.

Lift provides the computer, state, access, and safety boundaries. It does not build another coding agent.

## Status

Codex-first technical spike and private-alpha planning. The first runtime is one Ubuntu EC2 VM with an encrypted EBS workspace volume. Lift uses one provider-blind workload runner; Codex is merely the first user-owned recipe executed by it.

## The first magical loop

1. Connect Codex, Claude Code, or another supported provider once in Lift's Connections tab.
2. Work locally in a project with an agent and uncommitted changes.
3. Click `Lift Off`.
4. Lift moves the workspace, starts the provider's native remote connection, and verifies readiness.
5. When Lift says it is safe, close the laptop and continue in the provider's existing phone application.
6. At the end of the cloud session, choose `Land Workspace`; when the laptop returns, Lift verifies and reflects the cloud changes back into the local workspace without losing or overwriting work.

Continuity is semantic, not byte-for-byte process migration. Lift may restart an agent or development process from preserved state when moving between machines.

## Initial user

A solo founder or agent-heavy developer who:

- regularly runs Claude Code, Codex, or similar CLI agents;
- leaves a laptop open while agents work;
- switches between a laptop and phone;
- has accumulated local configuration that makes fresh cloud environments annoying;
- wants cloud persistence without maintaining a VPS, tmux, Tailscale, Docker, or Terraform.

## Product boundary

Lift initially moves one coding workspace. It is not:

- a new foundation model or coding agent;
- a browser-based IDE;
- a mobile chat or remote-control application;
- a remote-desktop product;
- a complete clone of a laptop;
- a GitHub replacement;
- an enterprise developer-platform product.

## Documentation

- [docs/README.md](docs/README.md) - documentation map and recommended reading paths
- [PRD.md](PRD.md) - product requirements and acceptance criteria
- [docs/CONTEXT.md](docs/CONTEXT.md) - product thesis, principles, and terminology
- [docs/ICP.md](docs/ICP.md) - first customer, trigger, anti-ICP, and qualification score
- [docs/EXPERIENCE.md](docs/EXPERIENCE.md) - Connections tab, one-button Lift Off journey, safe-to-close, and Land experience
- [docs/STATE_SYNC.md](docs/STATE_SYNC.md) - ownership handoff, return-sync algorithm, recovery, and conflict behavior
- [docs/RESEARCH.md](docs/RESEARCH.md) - user evidence and competitive landscape
- [docs/RUNTIME_RESEARCH.md](docs/RUNTIME_RESEARCH.md) - runtime comparison, Codex and Claude remote-control findings, and infrastructure decision
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - selected prototype boundaries and state model
- [docs/REMOTE_RUNNER.md](docs/REMOTE_RUNNER.md) - provider-blind workload runner, user-owned recipes, and Codex-first validation
- [docs/SECURITY.md](docs/SECURITY.md) - threat model and minimum controls
- [docs/VALIDATION.md](docs/VALIDATION.md) - hypothesis tests, design partners, and evidence gates
- [docs/ROADMAP.md](docs/ROADMAP.md) - phased plan from feasibility through public launch
- [docs/GTM.md](docs/GTM.md) - positioning, landing page, acquisition, and launch sequence
- [docs/ECONOMICS.md](docs/ECONOMICS.md) - pricing, packaging, costs, and billing hypotheses
- [docs/ANALYTICS.md](docs/ANALYTICS.md) - activation, events, funnels, retention, and privacy rules
- [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) - verified, experimental, planned, and unsupported surfaces
- [docs/OPERATIONS.md](docs/OPERATIONS.md) - alpha onboarding, support, incidents, recovery, and release operations
- [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) - ranked technical, product, market, and company risks
- [docs/LAUNCH.md](docs/LAUNCH.md) - weekend prototype and private-alpha plan
- [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md) - private-alpha and public-launch readiness gates
- [docs/DECISIONS.md](docs/DECISIONS.md) - decisions already made and unresolved questions

## Current product sentence

Lift teleports your active coding workspace to a persistent cloud computer so any coding agent can keep working after you close your laptop.

The first feasibility target is Codex because it is the founder's current provider. Direct phone-to-Linux Codex control remains an experimental capability that must pass a real EC2 pairing spike; the documented fallback uses ChatGPT Desktop as an SSH relay and therefore does not yet satisfy the laptop-off promise.
