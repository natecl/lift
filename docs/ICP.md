# Ideal Customer Profile

Last updated: 2026-09-02

## Beachhead customer

Lift's first customer is an agent-native solo builder who starts real product work locally, uses Codex or another coding agent almost every day, and wants the project and its agents to remain available after the laptop closes.

This is narrower than “developers who use AI.” The initial user already feels the availability problem and has enough active local state that “just clone it into a cloud IDE” is not an acceptable answer.

## Primary ICP

### Identity

- solo founder, indie hacker, technical creator, or highly autonomous product engineer;
- buyer, user, and administrator are the same person;
- building a personal product, early startup, or noncritical side project;
- comfortable trusting a coding agent with substantial implementation work;
- uses macOS locally and a Git repository for the first release;
- already pays for Codex, Claude, or a comparable agent subscription;
- can adopt a new tool without company procurement or security review.

### Observable behavior

- uses a CLI coding agent at least four days per week;
- leaves a laptop awake for long agent tasks, overnight work, or remote access;
- switches between laptop and phone during the day;
- wants to launch completely new agent tasks from the phone while the laptop is offline;
- uses more than one coding agent or regularly considers parallelizing work across agents;
- often has uncommitted, untracked, or locally configured project state;
- has tried or seriously considered a VPS, Codespaces, tmux, Tailscale, remote desktop, or a provider cloud agent;
- values speed and continuity more than infrastructure customization;
- will test Lift on a real but noncritical repository.

### Trigger moment

The highest-intent moment is not “I need cloud development.” It is:

> My agent is working in the exact project on my laptop, but I need to leave now.

A second high-intent moment is:

> I am away from my laptop and want to start useful work in the real project now.

Common triggers include:

- leaving for class, a commute, a meeting, the gym, or errands;
- wanting an agent to continue overnight;
- avoiding battery drain, heat, or unreliable sleep settings;
- needing to redirect or approve work from a phone;
- traveling without wanting the project tied to one physical device;
- realizing that a fresh cloud environment lacks the dirty state and setup already working locally.

## Core jobs to be done

### Functional job

Give the project a permanent cloud workspace, move the exact active local state into it when necessary, launch or continue agents from any device, and safely bring the result back when desired.

### Emotional job

Feel certain that the laptop can close without losing momentum, context, or work.

### Social job

Operate like an unusually fast, always-on builder without becoming a part-time infrastructure engineer.

## Pain hierarchy

1. The laptop must remain awake and connected.
2. A fresh cloud workspace is not the same as the active local workspace.
3. Rebuilding tools, dirty files, instructions, and configuration is tedious and unreliable.
4. VPS and remote-access setups expose infrastructure details and maintenance.
5. Returning cloud changes to a dirty local workspace feels risky.
6. Existing products often replace the user's agent interface or assume work starts cloud-first.
7. Multiple agents duplicate setup, collide in shared files, or return disconnected changes with unclear authorship.
8. Provider-owned cloud environments tie project state to one agent ecosystem.

## Desired outcome

The primary customer should be able to say:

- “I clicked Lift Off and it told me when I could close the laptop.”
- “The project was already in Codex on my phone.”
- “I launched a new Codex task from my phone after the laptop was off.”
- “I could use several agents without rebuilding the project for each one.”
- “I never opened a terminal or cloud console.”
- “When I landed it, every change was back on my Mac.”
- “It handled the merge like a pull request and did not touch my local edits.”

## Existing alternatives

- leave the laptop open with sleep disabled;
- remote into the laptop;
- run an agent in tmux on a personal VPS;
- start cloud-first in Codespaces or a provider cloud agent;
- push partial work to GitHub and reconstruct the environment elsewhere;
- carry the laptop and postpone the task.

Lift must beat these on completed handoff time, trust, and cognitive load—not merely on feature count.

## Qualification scorecard

Give one point for each true statement:

1. Uses a coding agent four or more days per week.
2. Has left a laptop awake for an agent in the last month.
3. Uses the agent from a phone or wants to.
4. Regularly works with uncommitted or untracked project state.
5. Has tried or considered remote compute or remote access.
6. Can test on a real noncritical Git repository this week.
7. Can purchase a prosumer subscription personally.
8. Says laptop independence is more valuable than a new agent or IDE.
9. Uses multiple agents or has a concrete task they would parallelize.

Interpretation:

- `8-9`: ideal design partner;
- `6-7`: strong alpha prospect;
- `3-5`: interview, but do not optimize the first release around them;
- `0-2`: outside the beachhead.

## Anti-ICP for the first release

Do not optimize the private alpha for:

- enterprise platform teams or procurement-led buyers;
- regulated production repositories requiring formal vendor review;
- users who primarily need a browser IDE or remote desktop;
- users whose work depends on macOS-only GUI applications;
- large teams requiring shared workspaces, governance, procurement, or enterprise controls before a pilot;
- users who work cloud-first and have no local handoff pain;
- users who do not use a provider with a viable remote phone or web client;
- repositories dominated by huge binary assets, nested repositories, or unsupported submodule layouts;
- people unwilling to let any source code or approved state leave the laptop.

Saying no to these users protects the first experience. They may become later segments.

## Adjacent future segments

1. Small AI-native startup teams sharing persistent project workspaces among developers and agents.
2. Agent-heavy freelancers moving among several client workspaces.
3. Nontechnical founders directing cloud coding agents from a phone.
4. Researchers and students running long-lived computational or browser tasks.
5. Operators using agents for product, support, and browser workflows beyond code.

Do not broaden the first alpha into team administration until the primary ICP repeats the coding handoff and pays. The workspace and task model should nevertheless preserve a clean path to team participation.

## Purchase hypothesis

The buyer pays for one or more of these outcomes:

- freedom to close the laptop;
- time saved maintaining remote infrastructure;
- fewer interrupted agent sessions;
- reliable continuity of dirty project state;
- confidence that cloud changes will return safely.
- the ability to launch new work from a phone while every laptop is offline;
- one persistent environment shared across several agent providers;
- safe, understandable parallel agent work.

The strongest willingness-to-pay evidence is not positive interview feedback. It is a real repository handoff followed by a deposit, paid month, or continued paid usage.

## Objections and product implications

| Objection | Product implication |
| --- | --- |
| “I do not trust you with my source code.” | Inspectable manifest, encryption, isolation, deletion controls, and clear data handling must be visible before upload. |
| “I can already use a VPS.” | Lift must complete the dirty-workspace round trip faster and with less setup than the user's workaround. |
| “Why not start in Codespaces?” | Demonstrate active local-state transplant and provider-neutral continuation, not generic cloud development. |
| “Why not use Grok Bot or my provider's cloud agent?” | Demonstrate a project-centric workspace that survives provider changes, supports heterogeneous agents, and connects local and GitHub origins without belonging to one bot account. |
| “Will multiple agents overwrite one another?” | Offer shared, isolated, and read-only modes; checkpoint before shared work, attribute activity, detect overlap, and preserve recoverable versions. |
| “Will it overwrite my work?” | Show the Git-backed baseline, clean-merge result, and preserved conflict worktree in plain language. |
| “Do I need another agent subscription?” | Reuse the user's provider account where officially supported; price Lift for infrastructure and continuity. |
| “Does my laptop really turn off?” | Never claim this until the selected provider's direct headless phone path is verified. |
| “Will I return to a mess of commits?” | Keep Lift history private and return changes to the working tree by default without moving the user's branch or index. |

## Recruitment screener

Ask prospects:

1. Which coding agent did you use most in the last seven days?
2. Show the last task that continued for more than 15 minutes.
3. What did you do when you needed to leave the computer?
4. How often is your working tree dirty while the agent is working?
5. Have you set up a VPS, remote desktop, tmux, Tailscale, or Codespaces for this?
6. Which phone application would you expect to continue from?
7. What repository could you safely test this on this week?
8. If it works, can you put down a deposit or pay for the first month?
9. Which two agent tasks would you run at the same time if the environment and collision risk were handled?

Recruit from demonstrated behavior, not enthusiasm for an abstract “cloud laptop.”

## Evidence status

### Observed

- the founder personally uses agents as the primary coding interface;
- laptop availability and goal continuity are real workflow constraints;
- recent community discussions show people assembling VPS, tmux, Tailscale, remote-control, and phone workflows;
- several products already market persistent cloud agent environments and mobile access;
- in one founder-only Phase 0 run, ChatGPT on the phone directly controlled the intended Ubuntu EC2 workspace before and after an EC2 stop/start, and three immutable cloud checkpoints were restored from exact versioned S3 objects;
- that run's laptop shutdown is strongly corroborated by a fresh challenge/proof exchange and Mac reboot timestamps, but is human-attested rather than cryptographically device-attested.
- the founder still needed terminal-operated authentication, pairing, exact folder selection, recovery, and evidence steps, confirming that the zero-terminal experience is a separate product problem rather than a consequence of provisioning the VM.
- separate generated-fixture runs crossed the live Land boundary once each: the clean path restored, applied, acknowledged, returned ownership, and stopped compute; the deliberate same-file conflict preserved exact `B/L/C`, left the local workspace untouched, retained `LANDING`, fenced cloud writers, and changed nothing on retry.

### Supported inference

- local-to-cloud-to-local continuity is a more defensible wedge than generic persistent compute;
- a project-centric workspace that survives provider changes may be more defensible than an account-centric cloud computer;
- solo agent-heavy builders can adopt faster than enterprise teams;
- verified clean application and safe conflict preservation can support a trustworthy return experience, although fixture mechanics are not evidence that users understand or trust the product UX.

### Unproven

- the pain occurs frequently enough for retention;
- the once-passed Codex Remote stop/start path repeats reliably across users, independent runs, provider versions, reauthentication, and network interruption;
- users trust Lift with real active state;
- users understand and successfully resolve a preserved Land conflict without Git or infrastructure expertise;
- users repeatedly launch new agent tasks from mobile rather than treating phone control as a demo;
- solo developers need multiple agents often enough for coordination to drive retention;
- small teams will share a functioning workspace and accept its permission model;
- browser and computer capabilities unlock retained workflows without creating unacceptable credential risk;
- the zero-terminal experience can survive provider authentication constraints;
- the primary ICP will pay enough to cover compute and support.

These unproven claims drive the validation plan in [`VALIDATION.md`](VALIDATION.md).
