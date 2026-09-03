# Lift Documentation

This directory is the shared product knowledge base for humans and agents building Lift.

## Start here

For a complete introduction, read in this order:

1. [`../README.md`](../README.md) for the product in one page.
2. [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md) for the durable workspace vision, capability model, and wedge-to-platform sequence.
3. [`CURRENT_STATE.md`](CURRENT_STATE.md) for what exists, what passed, what failed, and what comes next.
4. [`../PRD.md`](../PRD.md) for requirements, boundaries, and acceptance criteria.
5. [`CONTEXT.md`](CONTEXT.md) for the product thesis and experience principles.
6. [`ICP.md`](ICP.md) for the exact first customer and anti-ICP.
7. [`EXPERIENCE.md`](EXPERIENCE.md) for workspace creation, mobile agent launch, Lift Off, and Land journeys.
8. [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md) for the reviewed real-workspace discovery, approval, and return-policy boundary.
9. [`DECISIONS.md`](DECISIONS.md) before changing product scope or architecture.
10. [`ROADMAP.md`](ROADMAP.md) for the current evidence gate and next milestone.

## Reading paths

### Founder and product

1. [`CONTEXT.md`](CONTEXT.md)
2. [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md)
3. [`ICP.md`](ICP.md)
4. [`../PRD.md`](../PRD.md)
5. [`EXPERIENCE.md`](EXPERIENCE.md)
6. [`RESEARCH.md`](RESEARCH.md)
7. [`VALIDATION.md`](VALIDATION.md)
8. [`ROADMAP.md`](ROADMAP.md)

### Engineering and security

1. [`ARCHITECTURE.md`](ARCHITECTURE.md)
2. [`RUNTIME_RESEARCH.md`](RUNTIME_RESEARCH.md)
3. [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md)
4. [`STATE_SYNC.md`](STATE_SYNC.md)
5. [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md)
6. [`COMPATIBILITY.md`](COMPATIBILITY.md)
7. [`SECURITY.md`](SECURITY.md)
8. [`RISK_REGISTER.md`](RISK_REGISTER.md)

### Validation and go-to-market

1. [`ICP.md`](ICP.md)
2. [`VALIDATION.md`](VALIDATION.md)
3. [`GTM.md`](GTM.md)
4. [`ECONOMICS.md`](ECONOMICS.md)
5. [`ANALYTICS.md`](ANALYTICS.md)

### Alpha and launch operations

1. [`ROADMAP.md`](ROADMAP.md)
2. [`LAUNCH.md`](LAUNCH.md)
3. [`OPERATIONS.md`](OPERATIONS.md)
4. [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md)
5. [`ANALYTICS.md`](ANALYTICS.md)

## Documents by purpose

### Understand the opportunity

- [`CURRENT_STATE.md`](CURRENT_STATE.md) is the canonical cross-functional snapshot of the repository implementation, observed evidence, milestone provenance, and remaining product boundary.
- [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md) defines the project-centric cloud workspace, mobile launch, multi-agent modes, browser and computer capabilities, GitHub relationship, defensibility, and validation sequence.
- [`CONTEXT.md`](CONTEXT.md) explains why Lift should exist and what “replace the laptop” means.
- [`ICP.md`](ICP.md) defines the beachhead customer, triggers, alternatives, anti-ICP, and qualification score.
- [`EXPERIENCE.md`](EXPERIENCE.md) defines the zero-terminal onboarding, one-button launch, safe-to-close, and Land contract.
- [`STATE_SYNC.md`](STATE_SYNC.md) defines the three-way state model, transactional return, and conflict behavior.
- [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md) defines the local candidate -> approval -> effective-policy -> return-plan foundation and the still-pending B/checkpoint/Land integration.
- [`RESEARCH.md`](RESEARCH.md) contains user evidence, category signals, competitors, and remaining validation gaps.
- [`RUNTIME_RESEARCH.md`](RUNTIME_RESEARCH.md) records the current infrastructure comparison and official Codex and Claude remote-control findings.
- [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md) records the versioned Codex Linux, phone, and EC2 feasibility evidence.

### Build the product

- [`../PRD.md`](../PRD.md) defines the target user, core journey, MVP, metrics, and non-goals.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) defines the selected prototype boundaries, state model, and handoff flows.
- [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md) defines the provider-blind workload runner, user-owned recipes, and Codex-first spike.
- [`STATE_SYNC.md`](STATE_SYNC.md) defines private Git snapshots, PR-like Land reconciliation, transactional apply, and recovery.
- [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md) records the exact local v1 policy schemas, initial-versus-return rule split, and generic Git-history boundary.
- [`COMPATIBILITY.md`](COMPATIBILITY.md) records what is verified, experimental, planned, relayed, or unsupported.
- [`SECURITY.md`](SECURITY.md) defines the threat model and minimum safeguards.
- [`RISK_REGISTER.md`](RISK_REGISTER.md) ranks product, provider, state, security, market, and company risks.

### Validate and sell the product

- [`VALIDATION.md`](VALIDATION.md) defines hypotheses, interviews, concierge tests, commitment ladder, and go/no-go gates.
- [`GTM.md`](GTM.md) defines positioning, landing-page structure, founder-led acquisition, launch sequence, and objections.
- [`ECONOMICS.md`](ECONOMICS.md) defines pricing hypotheses, cost attribution, packaging tests, and billing requirements.
- [`ANALYTICS.md`](ANALYTICS.md) defines activation, the north-star loop, privacy-safe events, funnels, retention, and decision thresholds.

### Make and communicate decisions

- [`DECISIONS.md`](DECISIONS.md) records accepted and pending decisions.
- [`ROADMAP.md`](ROADMAP.md) defines evidence-gated phases from feasibility to public launch.
- [`LAUNCH.md`](LAUNCH.md) defines the weekend prototype, canonical demo, alpha cohort, and early distribution.
- [`OPERATIONS.md`](OPERATIONS.md) defines onboarding, support, incidents, recovery, releases, access, and data lifecycle.
- [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md) is the final private-alpha and public-launch readiness gate.

## Current product sentence

Lift gives every software project a persistent cloud workspace where developers and AI agents can work together from any device.

The first proof remains a local-to-cloud-to-phone-to-local loop in which the laptop can close and the user can launch or continue Codex from the provider's phone application.

## Current narrow wedge

One user lifts one active coding project from macOS into an isolated persistent Linux workspace, continues Codex through an existing OpenAI interface, and safely reconciles the result back to the laptop. Founder-only generated-fixture spikes have observed direct phone-to-Ubuntu-EC2 control, one full stop/start recovery with exact post-restart folder binding and guarded approval/proof evidence, and live clean and conflicted Land paths from EC2/EBS through exact versioned S3 recovery to the Mac. A separate local-only policy foundation now discovers and classifies a real Git worktree, binds explicit per-path approval, compiles a strict portable policy, and classifies caller-supplied return candidates for trusted in-process use without transferring bytes. It does not authenticate scanner provenance or candidate completeness and is not connected to fixture capture, EC2 reconstruction, checkpoints, or Land. Reviewable arbitrary-workspace transfer, a customer UI/helper, automatic offline-helper wake, conflict-resolution UI, separate provider-service identity and credential isolation, network recovery, revocation, broader repetition and interruption coverage, and the no-terminal journey remain pending.

## Current phase

Phase 0: the provider path, private-Git cloud checkpoints, one full EC2 stop/start phone recovery, one clean disposable-fixture round trip, and one fresh deliberate-conflict round trip are evidenced. The local real-workspace policy primitive is implemented and focused-tested, but no real project has crossed its transfer boundary. The immediate implementation boundary is policy-bound generic `B` capture and reconstruction beside the unchanged fixture adapter; the immediate product boundary still includes the customer helper and review UI. H6 remains open: conflict resolution, automatic offline-helper wake, broader repetition and interruption coverage, service-identity and credential isolation, production isolation, network recovery, revocation, the zero-terminal journey, and launch readiness remain gates. See [`CURRENT_STATE.md`](CURRENT_STATE.md), [`WORKSPACE_POLICY.md`](WORKSPACE_POLICY.md), and [`ROADMAP.md`](ROADMAP.md).

## Knowledge-base maintenance

- New evidence updates [`RESEARCH.md`](RESEARCH.md) or [`VALIDATION.md`](VALIDATION.md).
- Any change to the actual implementation/evidence boundary also updates [`CURRENT_STATE.md`](CURRENT_STATE.md).
- A changed product choice updates [`DECISIONS.md`](DECISIONS.md), [`../PRD.md`](../PRD.md), and any affected experience or architecture document.
- A changed supported surface updates [`COMPATIBILITY.md`](COMPATIBILITY.md), launch copy, and the checklist.
- A new risk gets an owner and trigger in [`RISK_REGISTER.md`](RISK_REGISTER.md).
- A reliability or security incident updates the relevant runbook and launch gate.
- Prices remain hypotheses until recorded behavior supports them.
- No document may turn an experimental provider capability into a product promise.
