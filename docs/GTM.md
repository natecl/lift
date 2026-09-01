# Go-to-Market and Positioning

Last updated: 2026-08-31

## Go-to-market objective

Find agent-heavy solo builders at the exact moment their laptop is blocking ongoing work, get them through one real handoff, and convert the completed outcome into repeated usage and payment.

Lift should not launch as a broad “cloud computer for everyone.” The initial category entry is:

> Workspace handoff for coding agents.

## Positioning statement

For agent-native solo builders who need to leave while a coding agent is working locally, Lift moves the exact active workspace into a persistent cloud computer and lets them continue through the provider application already on their phone. Unlike VPSs, cloud IDEs, and generic remote access, Lift carries dirty local state into the cloud and safely merges the result back.

## Message hierarchy

### Primary promise

> Close your laptop. Your agent keeps building.

### Mechanism

> Click Lift Off. Lift moves the exact project into the cloud and connects the coding agent you already use.

### Trust proof

> When you Land, Lift merges the cloud changes back like a private pull request and never overwrites local work.

### Boundary

> Lift is the computer underneath your agent, not another agent or mobile chat app.

## Wedge and vision

Lead with the narrow wedge:

- one active coding project;
- one click from local to cloud;
- existing agent application on the phone;
- safe return to the same local folder.

Reveal the larger vision only after the wedge is understood:

> Your laptop becomes one optional interface to an always-available personal computer in the cloud.

Starting with the vision alone risks sounding like remote desktop, a generic VPS, or science fiction.

## Landing-page structure

### Hero

Headline:

> Close your laptop. Your agent keeps building.

Subhead:

> Lift moves your exact local coding workspace into a persistent cloud computer, connects the agent you already use, and safely brings every change back.

Primary action:

> Lift my first workspace

Secondary action:

> Watch the 45-second handoff

### Proof strip

- Dirty files included.
- No VPS or SSH setup.
- Continue in your existing agent app.
- Git-backed safe return.
- Stop and delete anytime.

### How it works

1. Connect Codex or another supported provider.
2. Choose a project and click Lift Off.
3. Wait for “You can close this laptop.”
4. Continue from the provider app on your phone.
5. Land the workspace and get the changes back locally.

### Before and after

Before:

- laptop awake;
- sleep disabled;
- tmux, VPS, tunnels, and copied state;
- uncertainty about returning changes.

After:

- one persistent workspace;
- existing provider interface;
- laptop fully off when supported;
- verified PR-like return.

### Trust section

Explain:

- what Lift transfers and excludes;
- encryption and isolation;
- provider credential ownership;
- no automatic remote pushes;
- how clean and conflicted Land operations behave;
- export, stop, revoke, and delete controls.

### Honest compatibility

List each provider and platform as:

```text
Supported and verified
Experimental
Requires desktop relay
Not yet supported
```

Never hide a laptop dependency behind “remote capable.”

### Final action

> Stop keeping your laptop awake.

## Canonical demo

The strongest distribution asset is a continuous, minimally edited video:

1. show a recognizable local project with an uncommitted change;
2. click Lift Off;
3. show the plain-language progress and verified safe-to-close message;
4. physically close or power off the laptop;
5. direct one visible product change from the existing provider phone app;
6. choose Land;
7. reopen the laptop;
8. show the cloud change in the original folder;
9. optionally show a deliberate conflict preserved safely.

The emotional proof is the lid closing and the same project returning—not an infrastructure dashboard.

## Waitlist qualification

Collect only fields that improve selection:

- name and email;
- primary coding agent;
- local operating system;
- how often they leave a laptop awake for agents;
- current workaround;
- whether they have a real noncritical repository to test;
- expected phone application;
- willingness to join a guided session;
- willingness to place a deposit if it works.

Score prospects using [`ICP.md`](ICP.md). Do not optimize for a large unqualified waitlist.

## Founder-led acquisition

### Direct outreach

Target people who have publicly described:

- coding from a phone;
- running Claude Code or Codex on a VPS;
- tmux or Tailscale agent setups;
- leaving a laptop awake for agents;
- dissatisfaction with cloud environment setup;
- long-running or overnight coding-agent work.

Example message:

> I saw your setup for keeping an agent running away from your laptop. I am building Lift: it moves the exact dirty local workspace into a persistent cloud machine, keeps your existing agent app, and merges everything back afterward. I am looking for five people willing to try it on a real noncritical project. If it does not remove the laptop from the loop, I do not want you to keep using it.

### Community participation

Share evidence and implementation lessons rather than generic promotion:

- why dirty workspaces make cloud handoff difficult;
- a real local-to-cloud-to-local demo;
- what Codex and Claude remote control actually support;
- the Git-backed Land design;
- transparent failures from the feasibility spike;
- measured time saved versus a VPS workflow.

Use the communities and voices already identified in [`RESEARCH.md`](RESEARCH.md), while following each community's promotion rules.

### Founder content

Create a small sequence:

1. “Why my laptop is still the bottleneck for coding agents.”
2. “I closed my laptop while Codex kept building.”
3. “The hard part was getting a dirty workspace back safely.”
4. “We use private Git commits so Lift returns work like a pull request.”
5. Design-partner result with concrete elapsed time and outcome.

One undeniable demo is more useful than daily abstract AI commentary.

## Launch sequence

### Stage 1: Problem and build in public

- recruit interviews from observed workaround users;
- publish the problem and technical constraints;
- collect a qualified waitlist;
- avoid claiming unsupported provider behavior.

### Stage 2: Design-partner proof

- onboard five users manually;
- publish anonymized outcomes and failures;
- collect deposits after successful Land;
- refine the demo and objections.

### Stage 3: Invite-only alpha

- admit users in small waves;
- keep a visible compatibility matrix;
- use referral invites from successful users;
- prioritize people with an immediate trigger event.

### Stage 4: Paid beta

- introduce the tested package from [`ECONOMICS.md`](ECONOMICS.md);
- convert existing successful users before buying distribution;
- publish a clear support and data policy;
- track cohort retention rather than total signups.

### Stage 5: Public launch

- launch only after [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md) passes;
- lead with the continuous demo;
- use founder communities, direct outreach, and relevant launch platforms;
- keep the claim narrow enough that every new user can verify it.

## Lifecycle communication

### After waitlist signup

Confirm the exact supported use case and ask for a real test repository.

### Before first Lift Off

Explain the transfer boundary, provider limitations, cost cap, and recovery behavior.

### Immediately after first Land

Show the result summary, ask whether the laptop would otherwise have stayed open, and request a deposit or paid conversion.

### After inactivity

Ask about the missing trigger or failure. Do not send generic “come back” emails before understanding why the behavior stopped.

### After repeated success

Ask for a referral to one person using a similar agent workflow and permission to tell the story.

## Objection handling

### “This is just a VPS.”

A VPS gives you a machine. Lift moves the exact active workspace, establishes the existing agent connection, tells you when the laptop can close, and safely Lands the result.

### “Why not Codespaces or a cloud agent?”

Those are strong when work starts in their environment. Lift's wedge is continuing the messy local workspace that already exists and keeping the agent provider interchangeable.

### “Why not Git push and pull?”

Git push omits uncommitted, untracked, approved ignored, environment, and task state. Lift uses Git underneath for reconciliation without requiring the user to clean up or publish intermediate work.

### “Can I trust the merge?”

Lift merges private baseline, cloud, and returning-local snapshots in an isolated worktree. It applies a clean result only after verification and preserves both copies on conflict.

### “Why pay if my agent provider adds this?”

Lift must earn payment through cross-provider workspace ownership and local continuity. If first-party providers fully solve those jobs, the wedge must change.

## Messaging constraints

Never claim:

- every agent works;
- every laptop application moves;
- a provider phone path is direct when it needs a relay;
- process memory migrates;
- conflicts always merge automatically;
- end-to-end encryption unless the actual architecture supports that precise term;
- GitHub integration before explicit permissions and sanitization exist.

Trustworthy limitations are part of the brand.

## GTM metrics

- qualified waitlist rate;
- interview-to-real-test conversion;
- invitation-to-first-Lift-Off conversion;
- first-Lift-Off-to-acknowledged-Land conversion;
- percentage who physically close the laptop;
- seven- and 28-day repeat handoff rate;
- successful-user-to-paid conversion;
- successful-user referral rate;
- acquisition source by retained user, not signup;
- support minutes per activated user.

The event definitions and dashboards live in [`ANALYTICS.md`](ANALYTICS.md).
