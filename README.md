# Lift

The cloud workspace for developers and AI agents.

Lift gives a software project a persistent cloud workspace where one developer, multiple agents, and eventually a team can work from any device without keeping a personal laptop online. A workspace may begin as an active local folder, a GitHub repository, or an empty cloud environment.

The first indispensable experience remains one-button workspace teleportation: begin in a real local project, click `Lift Off`, wait for verified readiness, close the laptop, and launch or continue Codex from the phone. Lift provides the live environment, state, agent execution, internet and future browser capabilities, coordination, and safety boundaries. It does not build another coding agent.

The long-term product and the disciplined path to it are defined in [docs/PRODUCT_NORTH_STAR.md](docs/PRODUCT_NORTH_STAR.md).

## Status

Codex-first Phase 0 spike and private-alpha planning. A generated disposable workspace on real Ubuntu EC2 now accepts direct Codex Remote tasks from ChatGPT on the founder's phone, and the first three immutable Lift-private Git checkpoints were restored from exact versioned S3 objects before the live Land run. The laptop-off run is strongly corroborated by a fresh challenge/proof exchange and Mac reboot timestamps, but it is human-attested rather than cryptographically device-attested. One EC2 stop/start preserved the exact encrypted EBS workspace, earlier checkpoints and proof files, and the Codex Remote environment ID. After repairing native-project reconstruction, a fresh phone task passed the exact folder, guarded approval, proof, following checkpoint, restore, and live safe-to-close gates once.

On 2026-09-02, the controlled clean Land path passed once against live founder fixture run `p0-20260901083520-4fee`. The cloud writer fence sealed checkpoint `0004-land-final` as commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`; its exact versioned S3 bundle and manifest restored successfully. The first controller attempt stopped safely at `FINAL_CHECKPOINT_DURABLE` on a `/run` parent-directory mode mismatch. After the permission fix, the retry reused the same `C`, applied local merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, retained receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and produced acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`. The guest reached `ACKNOWLEDGED`, ownership returned to `LOCAL_PRIMARY`, and compute stopped only afterward. The full local suite passes.

Later on 2026-09-02, fresh disposable run `p0-20260902183748-a7b1` passed the complementary live conflict path. Deliberate local and cloud edits to `REMOTE_TEST.md` produced restore-tested checkpoint `0002-land-final` at commit `722adcffd8ebba70fb222cfbb1f749b0f5e479bc`, tree `3aa8260a33ec8e8c50b8f277aa2118fd8b88770b`. Land returned `NEEDS_REVIEW`; both ownership records remained `LANDING`; the original local content, branch, index, refs, reflog, and status stayed unchanged; and the isolated private worktree retained the exact baseline, local, and cloud stages. No apply journal, receipt, acknowledgement, lease return, or compute cleanup was created. The cloud runner remained fenced, a direct activation gate was rejected, and a repeated Land returned `changed: false` without changing controller state, events, refs, operation evidence, or either side. This accepts the generated-fixture Land vertical slice—clean application plus safe conflict preservation—as implemented.

These are founder-operated fixture results, not product acceptance. A separate local-only reviewed real-workspace policy foundation now passes 77 focused tests for discovery, exact approval, strict portable-policy decoding, and rule-based return classification. It does not upload or reconstruct a real workspace and is not wired into generic B, checkpoints, Land, or receipts. Policy-bound generic capture/reconstruction, customer review UI, automatic offline-helper continuation, additional phase-interruption coverage, conflict-resolution UI, repeated clean and conflict runs, and the no-terminal journey remain unimplemented or unproven. Separate provider-service identity and credential isolation, network recovery, revocation, repeated users, and provider-policy review remain pre-alpha or promotion gates. The next highest-value implementation slice is policy-bound generic B and reconstruction beside the unchanged fixture adapter. Lift uses one provider-blind workload runner; Codex is merely the first user-owned recipe executed by it.

## The first magical loop

1. Connect Codex, Claude Code, or another supported provider once in Lift's Connections tab.
2. Work locally in a project with an agent and uncommitted changes.
3. Click `Lift Off`.
4. Lift moves the workspace, starts the provider's native remote connection, and verifies readiness.
5. When Lift says it is safe, close the laptop and launch or continue agent tasks in the provider's existing phone application.
6. At the end of the cloud session, choose `Land Workspace`; when the laptop returns, Lift verifies and reflects the cloud changes back into the local workspace without losing or overwriting work.

Continuity is semantic, not byte-for-byte process migration. Lift may restart an agent or development process from preserved state when moving between machines.

## Initial user

A solo founder or agent-heavy developer who:

- regularly runs Claude Code, Codex, or similar CLI agents;
- leaves a laptop open while agents work;
- switches between a laptop and phone;
- wants to launch new agent tasks from the phone while the laptop is offline;
- uses more than one agent, or expects to as parallel agent work becomes normal;
- has accumulated local configuration that makes fresh cloud environments annoying;
- wants cloud persistence without maintaining a VPS, tmux, Tailscale, Docker, or Terraform.

The strongest adjacent customer is a small AI-native startup team that wants one functioning project workspace for its developers and agents without operating an internal developer platform.

## Product boundary

Lift initially proves one coding workspace and one user. It is not:

- a new foundation model or coding agent;
- a browser-based IDE;
- a replacement mobile chat or coding application;
- a remote-desktop product;
- a complete clone of a laptop;
- a Git hosting replacement;
- an enterprise developer-platform product.

Multi-agent operation, browser and computer use, GitHub-created workspaces, and team participation are product-north-star capabilities. They remain staged behind the complete, safe solo handoff rather than being treated as unrelated products.

## Documentation

- [docs/README.md](docs/README.md) - documentation map and recommended reading paths
- [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) - canonical current implementation, evidence, lessons, limitations, and next slice
- [docs/PRODUCT_NORTH_STAR.md](docs/PRODUCT_NORTH_STAR.md) - long-term product definition, capabilities, ICP expansion, defensibility, and validation sequence
- [PRD.md](PRD.md) - product requirements and acceptance criteria
- [docs/CONTEXT.md](docs/CONTEXT.md) - product thesis, principles, and terminology
- [docs/ICP.md](docs/ICP.md) - first customer, trigger, anti-ICP, and qualification score
- [docs/EXPERIENCE.md](docs/EXPERIENCE.md) - Connections tab, one-button Lift Off journey, safe-to-close, and Land experience
- [docs/STATE_SYNC.md](docs/STATE_SYNC.md) - ownership handoff, return-sync algorithm, recovery, and conflict behavior
- [docs/WORKSPACE_POLICY.md](docs/WORKSPACE_POLICY.md) - exact local policy schemas, initial-versus-return boundary, and staged generic integration
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

Lift gives every software project a persistent cloud workspace where developers and AI agents can work together from any device.

The first product proof remains: Lift teleports an active local coding workspace to the cloud so the user can close the laptop and launch or continue Codex from the phone.

The first feasibility target is Codex because it is the founder's current provider. Direct phone-to-Linux control, one full EC2 stop/start recovery, one clean live fixture Land, and one deliberate live fixture conflict now pass as founder evidence. The capability remains experimental and founder-only until separate provider-service identity and credential isolation, network recovery, revocation, provider-policy review, repeated clean/conflict/interruption evidence, and an explicitly reviewed real-workspace loop pass. The documented fallback uses ChatGPT Desktop as an SSH relay and therefore does not satisfy the laptop-off promise.
