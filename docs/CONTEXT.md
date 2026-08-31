# Product Context

## Origin

Lift began with a simple desire: if a cloud computer could run a product and school workflows continuously, the laptop could become an optional command surface rather than the place where work must live.

The motivating analogy is Wispr Flow. Dictation existed for years, but poor accuracy and poor product design kept typing as the default. Wispr Flow took an existing primitive, made it work unusually well, and changed behavior. Lift should apply the same product instinct to remote and cloud computing.

Cloud development environments, VPSs, SSH, remote desktop, browser IDEs, and cloud coding agents already exist. The opportunity is to make handoff so complete and easy that keeping an agent on a laptop begins to feel primitive.

## Long-term vision

The laptop becomes one optional interface to a persistent personal cloud computer. Files, agents, browsers, tasks, and ongoing work remain available regardless of which physical device is open.

The long-term vision can expand from a personal computer to a shared company computer, but the consumer experience comes first.

## Initial wedge

One active coding workspace moves from a local laptop to an always-available cloud environment. Existing agents can operate there, and the user can control them from a phone.

The wedge is intentionally smaller than the vision:

- one person;
- one project;
- Linux cloud runtime;
- Claude Code and Codex;
- files, terminal, agent state, and one web preview;
- phone control rather than phone-based manual coding.

## Core insight

The hard and valuable part is not provisioning compute. It is continuity.

People already know how to clone a repository into a VM. What they do not want to reconstruct is everything implicit around it: dirty files, ignored configuration, runtime versions, local tools, instructions, task state, credentials, ports, and the mental certainty that the cloud workspace is truly the same work.

Lift should own the transition between environments.

## Product principles

### 1. Continue, do not restart

Every experience should feel like continuing existing work rather than configuring a new computer.

### 2. The agent is the interface

The phone should emphasize the goal, current work, decisions, changes, preview, and approvals. A cramped code editor is secondary.

### 3. Bring your agent

The user's chosen agent is not a temporary integration. Agent neutrality is part of the value proposition.

### 4. Magic must be inspectable

Lift can automate discovery, but the user must be able to see what moves, what remains local, what the agent can access, and what compute is running.

### 5. Preserve work before convenience

No handoff is successful if it risks overwriting local or cloud changes.

### 6. Consumer infrastructure should not feel like infrastructure

Avoid exposing containers, regions, SSH keys, Terraform, networking, or instance families during the core journey.

### 7. Start narrow enough to become excellent

Do not dilute the handoff by prematurely building collaboration, a full cloud desktop, or a general file system.

## What “replace the laptop” means

It does not mean virtualizing every macOS application. It means removing the laptop as the availability bottleneck for valuable work.

For the first release, success is more modest: the user no longer keeps a laptop awake for a coding agent.

## Product personality

Lift should feel fast, calm, reliable, and slightly magical. It should use plain language and make infrastructure disappear without hiding important risk.

Useful emotional moments:

- “It found everything this project needs.”
- “I can actually close the lid now.”
- “The preview is already on my phone.”
- “It knew exactly where I left off.”
- “I can see and revoke every permission.”

Avoid:

- a dashboard full of servers and infrastructure terminology;
- a generic chat wrapper;
- a toy mobile code editor;
- claims that imply every laptop application is supported;
- autonomous behavior without visible goals, status, or stop controls.

