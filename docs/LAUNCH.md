# Prototype and Launch Plan

## Launch recommendation

Launch a landing page immediately and a private alpha when one real project can complete the full local-to-cloud-to-phone-to-local loop.

Do not publicly launch Lift as a general cloud laptop. The first launch should make one narrow claim and demonstrate it live.

## Weekend prototype

### Day 1: Lift a real repository

- Implement local authentication and `lift inspect`.
- Discover Git status, untracked files, runtimes, package manager, and development command.
- Produce an include and exclude manifest.
- Provision one isolated cloud VM and persistent volume.
- Transfer an approved workspace snapshot.

End-of-day proof: an uncommitted local project appears correctly on a cloud machine.

### Day 2: Run existing agents

- Install Claude Code and Codex in the workspace image.
- Implement one adapter end to end.
- Start or continue a task using an explicit goal and generated handoff summary.
- Supervise the agent and one development process.
- Stream structured status and terminal output.

End-of-day proof: the agent changes code after the local computer disconnects.

### Day 3: Control it from a phone

- Build a minimal responsive PWA.
- Show goal, status, recent output, changed files, and attention requests.
- Allow typed or spoken redirection.
- Add stop and approve controls.
- Route one authenticated development preview.

End-of-day proof: close the laptop, request a change from a phone, and see it in the preview.

### Day 4: Make it trustworthy

- Add clear transfer review and secret exclusions.
- Add idle stop and compute visibility.
- Implement a safe export or `lift pull` path.
- Add failure recovery and a demo workspace.
- Instrument the activation funnel.

End-of-day proof: another person can complete the loop without infrastructure help.

## Deliberate prototype shortcuts

- Support TypeScript projects first.
- Support macOS local machines and Linux cloud workspaces first.
- Use one AWS region.
- Use one VM per workspace.
- Allow only one active agent session.
- Require a conventional package-manager lockfile and development command.
- Use a generated continuation package if official agent-session resume is unavailable.
- Keep alpha access invite-only.

Do not shortcut isolation, secret handling, work preservation, or authenticated previews.

## Demo script

1. Open a familiar local application and make an uncommitted edit.
2. Ask Claude Code or Codex to implement a visible feature.
3. While it is working, run `lift up`.
4. Show the concise state manifest and approve it.
5. Close the laptop lid.
6. Open Lift on a phone and show that the task continues.
7. Speak a refinement into the phone.
8. Open the protected preview and see the refinement.
9. Show the changed-file summary and stop the workspace.
10. Reopen the laptop and safely retrieve the result.

The demo should take less than three minutes excluding agent generation time.

## Landing-page outline

### Hero

Close your laptop. Your agents keep building.

Start locally with Claude Code or Codex. Lift your active workspace into a persistent cloud computer and continue from your phone.

### Proof

- Your uncommitted work comes with you.
- Your existing agent and workflow stay intact.
- Your preview opens on your phone.
- Your laptop can be completely off.
- You can see and revoke every permission.

### Contrast

No VPS setup. No SSH juggling. No fresh cloud environment. No new coding agent.

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

