# Product Context

Last updated: 2026-09-02

## Origin

Lift began with a simple desire: if a cloud computer could run a product and school workflows continuously, the laptop could become an optional command surface rather than the place where work must live.

The motivating analogy is Wispr Flow. Dictation existed for years, but poor accuracy and poor product design kept typing as the default. Wispr Flow took an existing primitive, made it work unusually well, and changed behavior. Lift should apply the same product instinct to remote and cloud computing.

Cloud development environments, VPSs, SSH, remote desktop, browser IDEs, and cloud coding agents already exist. The opportunity is to make handoff so complete and easy that keeping an agent on a laptop begins to feel primitive.

## Long-term vision

Every software project can have a persistent cloud workspace where developers and AI agents work together from any device. The workspace, not a laptop, provider conversation, agent, or compute instance, is the durable product object.

The laptop becomes one optional interface. A developer can open Codex or another provider application on a phone, launch a new agent into the workspace, and continue useful work while every personal computer is offline. One developer may use one or several agents; later, multiple developers and heterogeneous agents can share the same project workspace.

GitHub remains the source-history and review backbone. Lift owns the live project environment: files, dependencies, services, internet and browser capabilities, participants, tasks, checkpoints, and recovery. The full product model is defined in [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md).

## Where the product stands now

The provider half of the first promise has passed once in a founder-only feasibility harness. A generated disposable workspace ran on Ubuntu EC2 with encrypted EBS, accepted a direct task from the founder's existing phone application, survived one EC2 stop/start, produced a guarded approval/proof turn, and entered a third immutable checkpoint that restored exactly from versioned S3 objects. A fresh live evaluation then found every implemented safe-to-close gate true for its 30-second validity window.

That is meaningful technical evidence, not a customer product. The current tree implements the fixture Land control path: an EBS-resident write fence, one immutable and restore-tested final cloud checkpoint, exact-version quarantine import, local `B/L/C` reconciliation, durable acknowledgement and lease return for a clean result, and preservation without acknowledgement for a conflict. On 2026-09-02, one live clean fixture transaction completed through post-ack compute stop, and a separate fresh fixture run completed the deliberate-conflict path through `NEEDS_REVIEW`. The conflict left both controller and guest ownership at `LANDING`, kept the local workspace and its Git state untouched, preserved exact baseline/local/cloud stages in the private worktree, fenced the cloud runner, retained compute for recovery, and returned `changed: false` on retry. This accepts the generated-fixture Land core, not H6 or the customer journey. The harness still requires founder-operated terminal steps, captures only an exact generated fixture, lacks conflict-resolution UI and automatic offline-helper continuation, and shares one Unix identity between provider state and the untrusted workload. The immediate product move is the explicit real-workspace manifest/review boundary while repeat and additional interruption evidence continue. The exact boundary is maintained in [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Initial wedge

One active coding workspace moves from a local laptop to an always-available cloud environment. Existing agents can operate there, and the user controls them through the provider interface they already use.

The wedge is intentionally smaller than the vision:

- one person;
- one project;
- Linux cloud runtime;
- Codex first, with Claude Code or any remote-capable agent running through the same provider-blind workload runner;
- files, terminal, approved agent state, and restartable processes;
- provider-owned phone control rather than a Lift mobile application.

The wedge is an entry path into the larger workspace product, not a permanent product boundary. The same durable workspace will later be creatable from GitHub or an empty template, launchable repeatedly without a new local transfer, and usable by multiple agents and eventually teammates.

## Core insight

The hard and valuable part is not provisioning compute. It is durable, project-centric continuity and coordination.

People already know how to clone a repository into a VM. What they do not want to reconstruct is everything implicit around it: dirty files, ignored configuration, runtime versions, local tools, instructions, task state, credentials, ports, and the mental certainty that the cloud workspace is truly the same work.

Lift should own the transition between environments and the functioning workspace that remains afterward. Provider labs can supply cloud agents; Lift supplies the agent-neutral project medium in which those agents and their users work.

## Product principles

### 1. Continue, do not restart

Every experience should feel like continuing existing work rather than configuring a new computer.

### 2. The existing agent is the interface

The user's Codex, Claude, or other provider application should remain the place for prompts, approvals, notifications, and conversation. Lift should not ask the user to adopt another chat surface.

### 3. Bring your agent

The user's chosen agent is not a temporary integration. Agent neutrality is part of the value proposition.

The workspace must survive changing agents, models, conversations, devices, and eventually runtime providers.

### 4. Magic must be inspectable

Lift can automate discovery, but the user must be able to see what moves, what remains local, what the agent can access, and what compute is running.

### 5. Preserve work before convenience

No handoff is successful if it risks overwriting local or cloud changes.

Lift uses an explicit ownership handoff instead of pretending two live directories are one. The laptop is primary before Lift Off, the cloud is primary while lifted, and the laptop becomes primary again only after a verified Land operation.

Within a cloud-primary workspace, several agents may operate using a user-selected execution mode. Shared mode prioritizes immediate collaboration and must provide attribution, overlap detection, checkpoints, and recovery. Isolated mode prioritizes noninterference through worktrees or copy-on-write environments. Read-only mode supports review without mutation.

### 6. Consumer infrastructure should not feel like infrastructure

Avoid exposing containers, regions, SSH keys, Terraform, networking, or instance families during the core journey.

The recurring action is one button. Provider login is connected once through a normal browser flow. A supported user should never need to open a terminal, copy a token, or understand how the remote process works.

### 7. The phone can start work

Laptop independence is incomplete if the phone can only observe a process started earlier. Where provider capabilities permit it, a ready Lift workspace must accept completely new provider-native agent tasks while the laptop is offline.

### 8. The workspace is more than a terminal

Agents eventually need controlled internet, headless browser automation, visible browser observation, secure human takeover, persistent project-scoped browser identity, and computer use. These capabilities belong to the project workspace and must never require copying a personal browser profile.

### 9. GitHub is a backbone, not a gate

A workspace may start from GitHub, an active local folder, or an empty environment. Use GitHub for repository identity, permissions, review, and publication without forcing uncommitted or workspace-only state into a remote repository.

### 10. Compute is replaceable; the project is durable

An agent may run inside Lift or, where a safe supported integration exists, on a provider-owned cloud computer. Either computer is an execution participant rather than the owner of the project. Lift's durable value is the provider-neutral workspace identity, state, environment, permissions, provenance, coordination, and recovery that remains when an execution location disappears or changes.

Do not claim a closed provider computer is participating in the live workspace when Lift can only ingest a later Git branch or pull request. Honest asynchronous interoperability is preferable to false shared-state semantics.

### 11. Start narrow enough to become excellent

Do not build the whole multiplayer platform before the complete solo handoff repeats and supports payment. Architect the workspace, identity, task, and state models for multiple agents and later teams while validating them through the smallest complete solo workflow.

## What “replace the laptop” means

It does not mean virtualizing every macOS application. It means removing the laptop as the availability bottleneck for valuable work.

For the first release, success is more modest: the user no longer keeps a laptop awake for a coding agent and can launch or continue a correctly bound provider-native task from the phone.

## Product personality

Lift should feel fast, calm, reliable, and slightly magical. It should use plain language and make infrastructure disappear without hiding important risk.

Useful emotional moments:

- “It found everything this project needs.”
- “I can actually close the lid now.”
- “The same project is already in Codex on my phone.”
- “I started another agent from my phone and it entered the right workspace.”
- “Both agents saw the work, and I could tell what each changed.”
- “My teammate joined the functioning project instead of rebuilding it.”
- “It knew exactly where I left off.”
- “Everything it changed is already back on my laptop.”
- “I can see and revoke every permission.”
- “It literally just said I could close my laptop.”

Avoid:

- a dashboard full of servers and infrastructure terminology;
- a generic chat wrapper;
- a toy mobile code editor;
- claims that imply every laptop application is supported;
- autonomous behavior without visible goals, status, or stop controls.
