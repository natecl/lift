# Lift Documentation

This directory is the shared product knowledge base for humans and agents building Lift.

## Start here

For a complete introduction, read in this order:

1. [`../README.md`](../README.md) for the product in one page.
2. [`../PRD.md`](../PRD.md) for requirements, boundaries, and acceptance criteria.
3. [`CONTEXT.md`](CONTEXT.md) for the product thesis and experience principles.
4. [`ICP.md`](ICP.md) for the exact first customer and anti-ICP.
5. [`EXPERIENCE.md`](EXPERIENCE.md) for the Connections, Lift Off, and Land user journey.
6. [`DECISIONS.md`](DECISIONS.md) before changing product scope or architecture.
7. [`ROADMAP.md`](ROADMAP.md) for the current evidence gate and next milestone.

## Reading paths

### Founder and product

1. [`CONTEXT.md`](CONTEXT.md)
2. [`ICP.md`](ICP.md)
3. [`../PRD.md`](../PRD.md)
4. [`EXPERIENCE.md`](EXPERIENCE.md)
5. [`RESEARCH.md`](RESEARCH.md)
6. [`VALIDATION.md`](VALIDATION.md)
7. [`ROADMAP.md`](ROADMAP.md)

### Engineering and security

1. [`ARCHITECTURE.md`](ARCHITECTURE.md)
2. [`RUNTIME_RESEARCH.md`](RUNTIME_RESEARCH.md)
3. [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md)
4. [`STATE_SYNC.md`](STATE_SYNC.md)
5. [`COMPATIBILITY.md`](COMPATIBILITY.md)
6. [`SECURITY.md`](SECURITY.md)
7. [`RISK_REGISTER.md`](RISK_REGISTER.md)

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

- [`CONTEXT.md`](CONTEXT.md) explains why Lift should exist and what “replace the laptop” means.
- [`ICP.md`](ICP.md) defines the beachhead customer, triggers, alternatives, anti-ICP, and qualification score.
- [`EXPERIENCE.md`](EXPERIENCE.md) defines the zero-terminal onboarding, one-button launch, safe-to-close, and Land contract.
- [`STATE_SYNC.md`](STATE_SYNC.md) defines the three-way state model, transactional return, and conflict behavior.
- [`RESEARCH.md`](RESEARCH.md) contains user evidence, category signals, competitors, and remaining validation gaps.
- [`RUNTIME_RESEARCH.md`](RUNTIME_RESEARCH.md) records the current infrastructure comparison and official Codex and Claude remote-control findings.
- [`spikes/2026-08-31-codex-headless-remote.md`](spikes/2026-08-31-codex-headless-remote.md) records the versioned Codex Linux, phone, and EC2 feasibility evidence.

### Build the product

- [`../PRD.md`](../PRD.md) defines the target user, core journey, MVP, metrics, and non-goals.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) defines the selected prototype boundaries, state model, and handoff flows.
- [`REMOTE_RUNNER.md`](REMOTE_RUNNER.md) defines the provider-blind workload runner, user-owned recipes, and Codex-first spike.
- [`STATE_SYNC.md`](STATE_SYNC.md) defines private Git snapshots, PR-like Land reconciliation, transactional apply, and recovery.
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

Lift teleports your active coding workspace to a persistent cloud computer so any coding agent can keep working after you close your laptop.

## Current narrow wedge

One user lifts one active coding project from macOS into an isolated persistent Linux workspace, continues Codex through an existing OpenAI interface, and safely reconciles the result back to the laptop. Direct phone-to-Linux Codex control is the first feasibility gate, not an already-proven promise.

## Current phase

Phase 0: prove the Codex headless phone path and the private Git capture/merge path before treating the laptop-off promise as a supported product. See [`ROADMAP.md`](ROADMAP.md).

## Knowledge-base maintenance

- New evidence updates [`RESEARCH.md`](RESEARCH.md) or [`VALIDATION.md`](VALIDATION.md).
- A changed product choice updates [`DECISIONS.md`](DECISIONS.md), [`../PRD.md`](../PRD.md), and any affected experience or architecture document.
- A changed supported surface updates [`COMPATIBILITY.md`](COMPATIBILITY.md), launch copy, and the checklist.
- A new risk gets an owner and trigger in [`RISK_REGISTER.md`](RISK_REGISTER.md).
- A reliability or security incident updates the relevant runbook and launch gate.
- Prices remain hypotheses until recorded behavior supports them.
- No document may turn an experimental provider capability into a product promise.
