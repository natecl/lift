# Prototype and Launch Plan

Last updated: 2026-09-02

This document is the tactical first build and alpha plan. Phase gates are defined in [`ROADMAP.md`](ROADMAP.md); final release readiness is defined in [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md).

## Current execution status

- Day 1's direct provider path, one EC2/EBS stop/start, fresh exact-folder phone task, guarded approval/proof, and following restore-tested checkpoint have passed once as founder-only evidence.
- Day 2 is not complete: capture is restricted to a generated fixture, and there is no signed helper, dashboard, reviewable real-workspace manifest, or zero-terminal flow.
- Day 3's underlying runtime driver, provider-blind runner, Codex recipe, and fail-closed safe-to-close evidence exist in the harness; the one-button product surface does not.
- Day 4's generated-fixture core has passed separate live clean and deliberate same-file conflict runs. The clean path completed exact-version restore/import, local application and acknowledgement, lease return, and compute stop. The conflict path preserved exact `B/L/C` plus untouched local state, stopped at `NEEDS_REVIEW`/`LANDING`, kept the writer fenced, and repeated idempotently. Conflict-resolution UX, offline-helper continuation, and arbitrary real-workspace return remain unproven.

The next highest-value product slice is an explicit, reviewable real-workspace manifest so the proven fixture lifecycle can safely expand beyond generated test data. In parallel, repeat clean and conflict Land from fresh sessions and exercise additional interruption and offline-helper recovery cases. See [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Launch recommendation

Launch a landing page immediately. Treat one real project completing the full local-to-cloud-to-phone-to-local loop as necessary private-alpha evidence, not a sufficient release gate. Private alpha also requires the applicable security and operations blockers—especially provider-service and credential isolation, signed or content-addressed bootstrap, revoke/delete/recovery controls, and the relevant items in [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md)—to pass.

Do not publicly launch Lift as a general cloud laptop. The first launch should make one narrow claim and demonstrate it live.

## Weekend prototype

### Day 1: Prove the Codex connection

- Manually provision one x86_64 Ubuntu EC2 instance with an encrypted EBS data volume.
- Install and authenticate the current Codex CLI through an explicit user-owned flow.
- Bootstrap the experimental durable remote-control daemon.
- Generate a pairing code and attempt to pair ChatGPT mobile directly with the Linux host.
- Start a task, approve an action, disconnect the laptop, restart the daemon, and record behavior.
- Configure the documented ChatGPT Desktop-to-SSH path as a fallback and diagnostic control.

End-of-day gate: either direct headless Codex control works with the laptop disconnected, or Lift records precisely which unsupported dependency blocks the promise. Do not build around assumed pairing behavior.

### Day 2: Lift a real repository

- Implement the internal inspect primitive and the first reviewed state manifest.
- Add the minimal signed desktop helper for folder selection, local manifest generation, and transfer.
- Add a minimal dashboard with Workspaces and a Codex connection card that presents the provider-owned login established in the Day 1 spike.
- Discover Git status, untracked files, runtimes, package manager, and development command.
- Transfer an approved dirty workspace to the existing EC2 and EBS runtime.
- Verify that local files are not modified and cloud files match the manifest hashes.

End-of-day proof: without a terminal, an uncommitted local project appears correctly on the persistent cloud machine and Codex can read it.

### Day 3: Turn the spike into the first vertical slice

- Implement the runtime-provider boundary for create, start, stop, exec, upload, snapshot, and status.
- Implement the provider-blind remote workload runner.
- Express Codex installation and daemon startup entirely as a reviewed recipe.
- Supervise the Codex daemon under `systemd` and feed readiness into the generic connection state machine.
- Wire one `Lift Off` button to workspace transfer, runtime wake, native remote startup, readiness verification, and the safe-to-close state.
- Generate a provider-neutral continuation package for semantic restart.

End-of-day proof: one `Lift Off` click moves the workspace, starts the currently Experimental Codex connection recipe, reaches a verified safe-to-close state, and Codex changes cloud files.

### Day 4: Make state safe and recoverable

- Harden transfer review and secret exclusions.
- Add idle stop and compute visibility.
- Implement the local/cloud ownership state machine, versioned checkpoints, `Land Workspace`, and automatic verified application when the local helper reconnects.
- Capture baseline, cloud, and returning local state as commits in a Lift-private bare repository without changing the user's branch or index.
- Perform the three-way Land merge in an isolated worktree and route conflicts to that recoverable worktree or a sibling copy instead of overwriting.
- Add failure recovery and a demo workspace.
- Verify that stopping compute preserves EBS state and that restart provides semantic continuity.

End-of-day proof: the founder can disconnect, return, and see cloud changes reflected locally without a terminal, data loss, or a Lift-built phone interface.

## Deliberate prototype shortcuts

- Support TypeScript projects first.
- Support macOS local machines and Linux cloud workspaces first.
- Use one AWS region.
- Use one VM per workspace.
- Allow only one active agent session.
- Validate Codex first; add providers as recipes through the same runner.
- Let the provider own conversation, approvals, voice, and notifications.
- Require a conventional package-manager lockfile and development command.
- Use a generated continuation package if official agent-session resume is unavailable.
- Keep alpha access invite-only.

Do not shortcut isolation, secret handling, work preservation, or the distinction between observed process health and provider-owned connection state.

## Demo script

1. Open a familiar local project and make an uncommitted edit.
2. Connect Codex through Lift's provider-owned browser flow.
3. Select the project, review the concise state manifest, and click `Lift Off`.
4. Wait for `Ready. You can close this laptop.`
5. If direct headless pairing passed, close the laptop completely and continue from ChatGPT mobile.
6. Ask Codex for a visible refinement and inspect the changed files through Codex.
7. Choose `Land Workspace` while the laptop remains offline.
8. Reopen the laptop and show the verified cloud result appearing automatically in the local workspace.
9. Optionally wake the workspace again to demonstrate durable files and semantic restart.

The demo should take less than three minutes excluding provisioning and agent generation time. Direct pairing has a single founder feasibility pass, but public laptop-independent demo copy still waits for the compatibility promotion gates. If the desktop-to-SSH fallback is shown, do not describe it as laptop-independent.

## Landing-page outline

### Hero

Close your laptop. Your agents keep building.

Start locally with Codex. Lift your active workspace into a persistent cloud computer and continue through Codex without rebuilding your environment.

### Proof

- Your uncommitted work comes with you.
- Your existing agent and workflow stay intact.
- You keep using your existing agent interface.
- Your laptop can be completely off when the selected provider supports direct headless remote control.
- You can see and revoke every permission.

### Contrast

No VPS setup. No SSH juggling. No fresh cloud environment. No new coding agent. No new mobile chat app.

### Call to action

Lift my first workspace.

## Alpha cohort

Recruit 10 to 15 agent-heavy solo builders. Prefer people who already use remote-control or VPS workarounds.

For each user:

1. Observe their current workflow.
2. Have them lift a real noncritical project.
3. Require them to leave the laptop closed.
4. Give them a concrete task to redirect from the phone.
5. Observe return reconciliation.
6. Ask for payment or a deposit only after success.

## Go or no-go criteria

Continue toward a paid beta when:

- at least 50 percent of invited users successfully lift a workspace;
- at least 30 percent repeat the workflow on another day;
- at least two users pay or place a deposit;
- setup assistance falls with each cohort;
- users cite handoff or laptop independence, not merely novelty;
- no serious security or data-loss event occurs.

Reconsider the wedge when users consistently prefer starting cloud-first, only want remote control of their laptop, or will not trust project state to Lift.

## Early distribution

- Short video showing the lid closing while the agent continues.
- Posts in Claude Code, Codex, and agent-builder communities.
- Direct outreach to people publicly describing VPS and phone workflows.
- Open-source the local manifest inspector if it improves trust and distribution.
- Avoid a broad Product Hunt launch until real repeat usage exists.
