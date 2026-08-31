# Lift

Close your laptop. Your agents keep building.

Lift is a persistent personal cloud computer for coding agents. Its first product is one-command workspace teleportation: begin in a real local project, run `lift`, close the laptop, and continue the same work from a phone or another computer using Claude Code, Codex, or another CLI agent.

Lift provides the computer, state, access, and safety boundaries. It does not build another coding agent.

## Status

Product definition and private-alpha planning. No implementation has been selected yet.

## The first magical loop

1. Work locally in a project with an agent and uncommitted changes.
2. Run `lift up`.
3. Lift creates an isolated cloud workspace containing the selected project state, toolchain, agent configuration, and approved secrets.
4. Close the laptop.
5. Continue, approve actions, inspect changes, and open the running preview from a phone.
6. Return to the local computer without losing or overwriting work.

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
- a remote-desktop product;
- a complete clone of a laptop;
- a GitHub replacement;
- an enterprise developer-platform product.

## Documentation

- [PRD.md](PRD.md) - product requirements and acceptance criteria
- [docs/CONTEXT.md](docs/CONTEXT.md) - product thesis, principles, and terminology
- [docs/RESEARCH.md](docs/RESEARCH.md) - user evidence and competitive landscape
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - proposed system boundaries and state model
- [docs/SECURITY.md](docs/SECURITY.md) - threat model and minimum controls
- [docs/LAUNCH.md](docs/LAUNCH.md) - weekend prototype and private-alpha plan
- [docs/DECISIONS.md](docs/DECISIONS.md) - decisions already made and unresolved questions

## Current product sentence

Lift teleports your active coding workspace to a persistent cloud computer so any coding agent can keep working after you close your laptop.

