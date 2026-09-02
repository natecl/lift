# Product North Star

Last updated: 2026-09-02

## Product definition

Lift gives every software project a persistent cloud workspace where developers and AI agents can work together from any device.

The workspace is the durable product object. Laptops, phones, people, agent providers, conversations, and compute instances are replaceable ways to enter or operate it.

The category statement is:

> The cloud workspace for developers and AI agents.

The first indispensable experience remains:

> Start locally. Click Lift Off. Close the laptop. Continue Codex from the phone.

The long-term north-star experience is:

> Open an agent application on a phone, launch one or more agents into the team's Lift workspace, and let useful work continue in the complete project environment without any personal computer online.

## Current proof boundary

This document defines the destination, not current product support. As of 2026-09-02, founder-operated generated fixtures have crossed the full technical lifecycle on real EC2/EBS/S3: Lift Off into a provider-visible cloud workspace, direct phone-controlled work and durable checkpoints, then Land back to the Mac. One clean Land applied and acknowledged the exact cloud result before returning ownership and stopping compute; a separate same-file conflict preserved exact baseline, local, and cloud states, kept ownership in `LANDING`, fenced cloud writers, and repeated idempotently without overwriting either side.

That evidence validates the core ownership, durability, and recovery model behind the north star. It does not yet provide arbitrary real-workspace capture, a customer dashboard or signed helper, automatic offline-helper continuation, conflict-resolution UX, repeatability, production isolation, or launch readiness. The immediate product boundary is the explicit real-workspace manifest/review flow. [`CURRENT_STATE.md`](CURRENT_STATE.md) remains authoritative for implementation and evidence status.

## Problem

Developers are becoming managers of agents, but their projects still live on fragile personal computers or inside provider-specific, disposable cloud sessions.

This creates several connected problems:

- a local agent stops or becomes unreachable when the laptop sleeps;
- a fresh cloud agent does not have the active workspace's dirty files, dependencies, services, instructions, or approved local state;
- launching a new task from a phone often still depends on a desktop relay or a provider-owned environment;
- using multiple agents creates collisions, duplicated setup, fragmented context, and unclear authorship;
- teammates cannot reliably enter the same functioning environment or understand what agents changed;
- browser sessions, development services, credentials, and runtime state are reconstructed differently for every agent provider;
- returning from the cloud can overwrite or strand useful work.

The durable customer job is:

> Give my project a permanent, safe place where I and my agents can work from anywhere, without keeping a laptop online or rebuilding the environment.

## Product model

```text
Lift workspace
├── project files and repositories
├── dependencies, tools, and running services
├── internet, terminal, browser, and computer capabilities
├── scoped secrets and browser identities
├── checkpoints, recovery, and activity history
├── human participants
└── agent tasks
    ├── Codex
    ├── Claude
    ├── Grok
    ├── Cursor
    └── user-chosen remote-capable runners
```

The ecosystem roles are:

| Layer | Responsibility |
| --- | --- |
| GitHub | Source history, repository distribution, permissions, review, and pull requests |
| Lift | The live workspace, runtime, state, participants, agent execution, coordination, browser access, and recovery |
| Agent providers | Intelligence, conversations, models, approvals, and provider-native phone or desktop clients |
| User devices | Optional command and observation surfaces; never required infrastructure after readiness |

The strategic shorthand is:

> GitHub hosts code at rest. Lift hosts code in motion.

Lift should complement GitHub before attempting to replace any GitHub responsibility. GitHub is an important creation source and integration surface, but it is not a prerequisite for a Lift workspace.

## Workspace creation and location

Every creation path produces the same durable workspace identity.

### From this computer

Select an existing local folder, review the state manifest, and Lift Off. This path can preserve tracked, dirty, staged, untracked, and explicitly approved ignored files plus reconstructable environment state that a GitHub clone cannot contain.

### From GitHub

Select a repository, create the cloud environment, connect agents, and optionally invite collaborators. This is the cleanest default for cloud-native projects and teams.

### Empty or templated

Create a new cloud workspace without an existing repository, then initialize it through an agent, terminal, or reviewed template.

A workspace may begin locally or in the cloud. A local workspace can run local agents before Lift Off; after Lift Off, the cloud workspace becomes the primary durable execution location. A cloud-native workspace can later be cloned or Landed locally without losing its Lift identity or history.

## Laptop independence and mobile launch

Laptop independence remains a non-negotiable capability, not merely an acquisition message.

`Safe to close` means the workspace is durable, the selected provider is genuinely ready, and no remaining control or execution dependency requires the laptop. It must also mean that, where the provider supports it, the user can launch a completely new agent task from the provider's phone application after the laptop is offline. Continuing only an already-running process is insufficient for the complete promise.

The target Codex flow is:

1. Create or Lift Off a workspace once.
2. Lift registers and verifies the workspace with Codex Remote.
3. Close or power off the laptop.
4. Open Codex on the phone and select Remote.
5. Select the Lift workspace and launch a new task.
6. Lift wakes compute when necessary and binds the task to the correct project root, environment, permissions, and capabilities.
7. Start additional tasks from the phone without a laptop relay.

Provider-native applications remain the preferred conversation, notification, and approval surfaces. Lift owns workspace creation, health, participants, agent launch routing where supported, activity, stop controls, permissions, cost, snapshots, and recovery. Lift does not need to build a proprietary coding agent or a replacement mobile IDE.

## Solo, multi-agent, and multiplayer use

The product expands along one coherent workspace model:

1. One developer with one agent.
2. One developer with multiple agents.
3. Multiple developers and agents sharing a project workspace.

The beachhead remains the agent-heavy solo developer because one buyer can adopt quickly and the laptop-off problem is already observable. Multi-agent operation is a core product capability after the first complete handoff loop. Human team collaboration follows the same task, identity, permission, provenance, and recovery primitives after solo repeat use is proven.

### Agent execution modes

Isolation is configurable per task or workspace policy rather than permanently attached to an agent.

| Mode | Behavior | Best for |
| --- | --- | --- |
| Shared | Agents write in the same working directory and immediately see one another's changes | Coordinated work on different parts of one active task |
| Isolated | A task receives a Git worktree, branch, or copy-on-write environment for later integration | Independent implementations, risky changes, and large refactors |
| Read-only | An agent can inspect, test, and review without modifying files | Review, planning, security analysis, and debugging |

Shared mode must be simple enough for users who never want to think about Git. Because arbitrary shell commands make complete collision prevention difficult, shared mode promises strong visibility and recovery: a pre-run checkpoint, agent-attributed command and file activity, overlapping-write detection, pause and stop controls, preserved prior versions, and an append-only change journal. Isolated mode provides the stronger noninterference guarantee.

For team workspaces, owners may restrict which modes, secrets, browsers, networks, and integration actions each human or agent can use.

## Internet, browser, and computer capabilities

A useful agent workspace must support more than files and a terminal. The long-term workspace capability set includes:

- outbound internet access with visible policy and optional destination restrictions;
- GitHub, package registries, external APIs, and development services;
- headless Chromium and Playwright-style automation;
- visible Chrome or Chromium through a virtual display;
- visual computer use for applications without a suitable API;
- authenticated development previews and protected forwarded ports;
- user takeover for login, passkeys, two-factor authentication, CAPTCHA, or consequential confirmation;
- persistent project-scoped browser identities when explicitly enabled;
- separate browser contexts or screens for concurrent agents.

This is an agent-compatible project computer, not a clone of the user's personal laptop. Lift must never silently copy the user's everyday browser profile, cookie database, password manager, keychain, or unrelated home-directory state. Browser credentials and provider credentials remain encrypted, revocable, excluded from project Git and ordinary Land output, and inaccessible to unrelated agents.

Delivery should proceed from terminal and bounded network access, to headless browser testing, to visible browser observation, to secure takeover and persistent authentication, and finally to broader computer use. Browser and computer capabilities are part of the product north star even when they are excluded from the first handoff alpha.

## GitHub relationship

GitHub is the collaboration backbone, not a required origin and not an immediate replacement target.

| GitHub concept | Lift workspace concept |
| --- | --- |
| Repository | Persistent cloud workspace |
| Collaborator | Human or agent participant |
| Clone | Create or restore a workspace |
| Fork | Duplicate a functioning workspace |
| Commit | Durable code or workspace checkpoint |
| Branch | Optional isolated task environment |
| Pull request | Proposed integration or external review |
| Actions | Agents, routines, and scheduled work |
| Repository activity | Human and agent workspace activity |

Lift-private checkpoints may include approved active state that must never be pushed to GitHub. Any GitHub publication requires explicit authorization and a sanitized-content review. Over time, Lift may become the primary interface for active development while GitHub remains the canonical source and review backend.

## Initial ICP

The first customer is an agent-native solo builder or highly autonomous product engineer who:

- uses coding agents most working days;
- has kept a laptop awake or postponed work because an agent depended on it;
- wants to launch or direct agents from a phone;
- has a meaningful active local workspace or repeatedly reconstructs cloud environments;
- uses more than one agent, or expects to;
- values continuity and reliability more than infrastructure customization;
- can adopt and pay without enterprise procurement.

The strongest adjacent segment is a small AI-native startup team that wants a shared project computer for its developers and agents without operating a developer-platform stack.

The product is less urgent for developers who use short agent tasks, are satisfied with one provider's bundled cloud environment, have trivial repository setup, never need mobile access, or require enterprise governance before experimentation.

## Wedge and destination

The first wedge remains deliberately narrow:

> Lift one real local project, close the laptop, launch or continue Codex from the phone, and safely Land every change.

The wedge proves the hardest trust and continuity primitives: selective state transplant, durable runtime, provider-native mobile readiness, verified laptop independence, checkpoints, and conflict-safe return.

The destination is broader:

> A permanent, project-centric cloud workspace where developers and heterogeneous agents work together through real terminals, browsers, services, applications, and GitHub workflows.

Lift Off becomes one high-value way to create or update that workspace, not the entire product. Creating from GitHub or an empty template reaches the same product object.

## Defensibility and competitive thesis

Persistent VMs, browser access, phone control, snapshots, and even multiple agents are category capabilities, not durable moats. Grok Bot is a strong market signal that major providers expect demand for always-on agents with a shared cloud computer, browser, files, and mobile control; its existence does not by itself validate demand for Lift. First-party labs can continue bundling cloud agents.

Lift is defensible only if it owns the horizontal, project-centric layer that no individual agent provider naturally owns:

- the workspace survives changing agents, models, conversations, devices, team members, and eventually runtime providers;
- Codex, Claude, Grok, Cursor, and user-chosen runners can participate without recreating the project;
- shared and isolated tasks have explicit coordination, provenance, collision handling, and recovery;
- project environment, services, secrets, browser identities, and policies accumulate independently of an agent subscription;
- GitHub permissions, branches, reviews, and pull requests connect naturally without becoming a prerequisite;
- local-to-cloud-to-local movement remains safe for projects that did not start cloud-first;
- a team can understand which human or agent changed what and can revoke access without destroying the workspace.

The sharp distinction is:

> Grok Bot gives a user a computer for its Bots. Lift gives a software project a workspace for its humans and agents.

If Lift can be recreated inside a provider's cloud computer with a directory and a few scripts, it is packaging. If it reliably provides provider-neutral execution, shared-work visibility, task isolation, permissions, browser identity, GitHub integration, recovery, and team access, recreating it becomes a platform project.

### If every agent has its own cloud computer

Assume the strongest competitive future: Codex, Claude, Grok, and every serious agent include persistent cloud compute, browser and computer use, background execution, mobile launch, snapshots, and multiple concurrent agents. In that world, “a cloud computer for your agent” is bundled infrastructure and cannot sustain Lift.

Lift survives only if the provider computer is a replaceable **worker** and the Lift workspace remains the durable **project home**. The project—not the provider account or agent VM—owns its identity, canonical state, environment contract, services, participants, policies, secrets, browser identities, task ledger, provenance, checkpoints, and recovery history.

Lift should support two execution relationships:

| Relationship | Responsibility |
| --- | --- |
| Lift-hosted agent | Lift supplies the workspace runtime; the provider supplies the agent, conversation, and intelligence |
| Provider-hosted agent computer | The provider supplies execution; its computer receives a scoped workspace view or attaches through a supported interface, then returns changes, activity, and results to the Lift project |

This leads to a long-term product promise:

> Bring your own agent—and, when supported, bring its computer too.

Provider-hosted execution must not be faked. It requires a supported provider API or transport, short-lived task identity, explicit capability negotiation, a scoped state view, attributable changes, and checkpointed reconciliation. If a provider exposes only GitHub pull requests, Lift can integrate those results but cannot claim that the agent joined a live shared workspace. If a provider refuses external workspace attachment and state export entirely, it remains a closed substitute rather than a Lift participant.

The strongest users in this future are developers and teams using several agents, long-lived environments, shared services or data, project-scoped browsers and secrets, and cross-provider permissions or recovery. A solo developer who uses one provider and needs only that provider's bundled computer is unlikely to need Lift.

The existential test is explicit: if one provider or GitHub delivers a persistent team-owned project workspace with excellent local-state import, outside-agent participation, shared and isolated execution, project browsers and secrets, permissions, provenance, and recovery, Lift may not have a durable standalone role. The strategy therefore depends on owning cross-provider project continuity, not merely supplying compute.

## Product invariants

- The workspace is independent of any one agent, provider conversation, user device, or compute instance.
- Lift-hosted runtimes and supported provider-owned agent computers are replaceable execution participants, never the canonical owner of the project.
- A supported workspace remains usable when every personal laptop is offline.
- Users can launch new remote agent tasks from provider-native mobile applications where the provider permits it.
- Lift remains infrastructure for user-chosen agents and does not become a proprietary coding agent.
- Local folders, GitHub repositories, and empty or templated starts are equally valid workspace origins.
- Shared agent writing is supported with visibility and recovery; isolation is available when stronger guarantees are needed.
- Browser and computer use are project-scoped, permissioned, revocable, and separate from personal device identity.
- Every important state transition is idempotent or recoverable.
- No local, cloud, human, or agent change is silently overwritten.
- Secrets never enter ordinary project history, screenshots, snapshots, or logs merely because an agent can use them.
- GitHub integration is explicit and sanitized; Lift does not silently push private workspace state.
- Infrastructure complexity stays out of the normal product journey.

## Capability sequence

The north star does not require building the whole platform before validating the wedge.

1. Complete the safe real local-to-cloud-to-phone-to-local loop.
2. Make the resulting workspace persistent and launchable repeatedly without a new local transfer.
3. Allow a new provider-native phone task to wake and enter the workspace while the laptop is offline.
4. Add GitHub-created and empty workspaces.
5. Add multiple agent tasks, starting with shared mode plus attribution and recovery.
6. Add optional isolated and read-only task modes.
7. Add headless browser testing, then visible browser observation and secure takeover.
8. Add a second provider to prove agent neutrality in practice.
9. Prove that one supported provider-owned cloud computer can participate without becoming the workspace system of record.
10. Add team-lite invitations and GitHub-derived access for small AI-native teams.
11. Add deeper permissions, scoped browser identities, collaboration, and governance only as observed use requires them.

## Validation

The north-star story is not market proof. Validate increasingly expensive behavior:

1. A user lifts a real project and intentionally closes the laptop.
2. The user launches a useful new agent task from the phone while the laptop remains offline.
3. The user leaves the workspace in the cloud and returns on multiple days.
4. The user launches multiple agent tasks because parallelism is valuable, not because the feature is novel.
5. The user chooses shared or isolated execution and understands the outcome.
6. A user pays for the second month rather than returning to a laptop, VPS, or provider workspace.
7. A small team invites another developer and repeatedly uses the same workspace.

The product is solving a must-have problem when users deliberately leave laptops closed, launch new phone tasks, keep workspaces alive across days, run multiple agents, invite teammates, and pay for the resulting continuity. If users complete only the demo and return to local or provider-owned environments, the broader platform remains a cool capability rather than a retained product.

## North-star metrics

The beachhead activation event remains one acknowledged closed-laptop loop. Long-term product health should also measure:

- weekly active cloud workspaces with at least one useful completed agent task;
- new remote agent tasks launched while the originating laptop is offline;
- mobile-launched agent tasks per active workspace;
- workspaces used on multiple days without reconstruction;
- workspaces with two or more active agent tasks;
- shared-mode overlap warnings and successful recoveries;
- isolated-task integrations and review outcomes;
- GitHub-connected workspace activity and accepted pull requests;
- collaborator invitations, joins, and retained team workspaces;
- provider mix per retained workspace;
- compute and support cost per retained workspace;
- data-loss, credential, cross-workspace, and false-readiness incidents, with a target of zero.

## Scope discipline

The north star does not authorize premature breadth. Before solo repeat use and payment, Lift should not build a proprietary agent, Git hosting, a browser IDE, a full remote desktop product, enterprise SSO, complex organization hierarchy, unrestricted simultaneous writes without recovery, or broad personal-computer cloning.

The rule is:

> Architect for the project workspace and multiplayer future; validate it through the smallest complete solo workflow.
