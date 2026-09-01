# Zero-to-Launch Roadmap

Last updated: 2026-08-31

## Roadmap principle

Lift advances by evidence gates, not by accumulating infrastructure.

```text
prove provider path
        -> prove exact workspace transplant
        -> prove phone continuation
        -> prove safe Land
        -> prove repeated behavior
        -> prove payment
        -> scale access
```

Do not enter the next phase because the calendar says so. Enter when the current phase's exit criteria are true.

## Phase 0: Feasibility gates

### Objective

Remove the two technical unknowns capable of invalidating the first promise.

### Build and test

- provision one Ubuntu EC2 workspace with encrypted EBS;
- install and authenticate the exact Codex version used by the founder;
- test direct headless phone pairing, laptop disconnect, daemon reconnect, and VM restart;
- separately validate the documented desktop-to-SSH path without calling it laptop-independent;
- capture a dirty local repository into a Lift-private synthetic baseline commit;
- produce cloud and returning-local commits and perform an isolated three-way merge;
- verify that the user's branch, refs, real index, and working tree remain untouched during capture;
- test clean and deliberate conflict returns.

### Exit criteria

- one provider path truthfully supports the claimed phone continuation, or the product explicitly changes its first provider/claim;
- Git-backed capture and merge work with tracked, dirty, staged, untracked, and approved ignored files;
- no silent overwrite in the conflict test;
- selected runtime survives stop and wake with durable files.

### Do not build yet

- production control plane;
- multi-provider UI;
- teams;
- preview gateway;
- billing;
- arbitrary runtime abstraction beyond the thin interface required by the spike.

## Phase 1: Founder-only vertical slice

Target: the first two-to-four-day “holy shit” moment.

### Objective

The founder completes one real loop without using a terminal during the product journey.

### Scope

- signed local helper or minimal trusted local application;
- Lift account and one connected Codex account;
- one project picker and plain-language transfer review;
- one `Lift Off` button;
- one preprovisioned or automatically provisioned EC2 workspace;
- exact dirty-state transfer;
- generic runner plus Codex connection recipe;
- verified safe-to-close state;
- provider-owned phone continuation;
- one `Land Workspace` button;
- private Git three-way merge and automatic clean return;
- visible conflict preservation;
- stop, delete, and emergency revoke.

### Exit criteria

- a real project goes local -> cloud -> phone -> local;
- laptop is fully off during useful agent work;
- Land returns the exact expected content;
- no terminal, SSH command, cloud console, or copied token appears after installation;
- the complete demo can be shown in under three minutes excluding agent generation and cold provisioning.

## Phase 2: Founder dogfood

### Objective

Make Lift reliable enough that the founder chooses it over leaving the laptop open.

### Scope

- seven consecutive days on one real project;
- retryable and idempotent lifecycle operations;
- runtime wake and idle stop;
- connection recovery and reauthentication;
- versioned cloud checkpoints;
- crash-safe local application journal;
- compute and transfer timing instrumentation;
- error states written in user language;
- recovery runbook for every expected failure.

### Exit criteria

- at least five successful real handoffs;
- at least three occur because the laptop genuinely needed to close;
- clean Land succeeds every time;
- all intentional conflicts preserve both sides;
- no unrecoverable workspace or credential incident;
- founder can explain every status without infrastructure vocabulary.

## Phase 3: Design-partner alpha

### Objective

Prove that people other than the founder can reach the same moment.

### Scope

- five high-fit design partners, then a second wave of five;
- guided onboarding and visible support channel;
- account, helper, provider, workspace, and deletion lifecycle;
- per-user isolation and scoped credentials;
- basic cost caps and idle stop;
- transfer and reconciliation audit events;
- analytics funnel in [`ANALYTICS.md`](ANALYTICS.md);
- privacy notice, alpha agreement, and explicit product limitations;
- founder-operated incident and support playbooks.

### Exit criteria

- at least 5 of 10 invited users complete the loop;
- at least 3 repeat it on three occasions;
- at least 2 pay or place a deposit;
- second-wave users require less assistance than the first;
- zero data-loss, cross-user, credential-exposure, or false-safe-to-close incidents.

## Phase 4: Private paid beta

### Objective

Turn the successful concierge loop into a supportable paid product.

### Scope

- self-serve invite acceptance and onboarding;
- reliable helper installation and updates;
- hosted runtime provisioning and lifecycle automation;
- billing, included usage, caps, and cancellation;
- encrypted recovery retention and user-controlled deletion;
- service health, alerting, and support response targets;
- polished connection recovery;
- onboarding education for workspace ownership and Land;
- a second provider recipe only after Codex reliability is established or if Codex cannot support the promise;
- documented provider and runtime version compatibility.

### Exit criteria

- at least 20 paying users or another deliberately chosen sample large enough to observe repeat behavior;
- target activation and repeat rates in [`ANALYTICS.md`](ANALYTICS.md) are met for four weeks;
- support burden is manageable by the current team;
- gross-margin trajectory is viable under [`ECONOMICS.md`](ECONOMICS.md);
- security, privacy, deletion, and provider-policy launch gates pass;
- no unresolved severity-one incident.

## Phase 5: Public launch candidate

### Objective

Make one truthful, narrow promise to a wider audience.

### Required product scope

- supported macOS and repository constraints are explicit;
- at least one provider has a proven laptop-off flow;
- first-time connection and Lift Off are self-serve;
- safe-to-close is evidence-backed;
- Land is clean, understandable, and recoverable;
- users can see cost, stop compute, revoke providers, export, and delete;
- runtime and provider outages degrade honestly;
- support and incident channels are staffed for launch traffic.

### Exit criteria

All applicable items in [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md) are complete and the founder can run the canonical demo live against production.

## Phase 6: Expansion after launch

Rank by observed demand rather than vision appeal:

1. reliability and wake-speed improvements;
2. second first-class provider connection;
3. more local operating systems and repository shapes;
4. authenticated previews;
5. optional sanitized GitHub pull-request return mode;
6. multiple simultaneous agents;
7. reusable environment profiles;
8. BYO AWS;
9. shared company workspaces;
10. browser and non-code workloads.

## Workstream ownership

Every milestone should have one directly responsible person, a verification artifact, and a rollback path.

| Workstream | Definition of done |
| --- | --- |
| Product experience | A target user completes the journey without explanation. |
| Provider connection | Authentication, native remote startup, readiness, recovery, and revocation are verified. |
| State continuity | Every included byte has a manifest revision and every return is recoverable. |
| Runtime | Create, wake, stop, snapshot, restore, and delete are idempotent and observable. |
| Security | Isolation, secret boundaries, audit events, and emergency controls pass documented tests. |
| Growth | A repeatable path reaches qualified users and produces real product attempts. |
| Business | Price, compute policy, billing, cancellation, and support costs are measurable. |

## Prioritization rule

When choosing the next task, use this order:

1. eliminate a blocker to the complete loop;
2. prevent data or credential loss;
3. remove a manual step from the supported journey;
4. reduce time to safe-to-close or Land acknowledgement;
5. improve recovery and explanation;
6. improve activation measurement;
7. add breadth only after repeat usage.

## Scope firewall

Until private-alpha retention is proven, do not build:

- a Lift coding agent;
- a Lift phone chat or IDE;
- a general cloud desktop;
- multi-user collaboration;
- GitHub replacement;
- production deployment automation;
- arbitrary browser-profile migration;
- a sophisticated multi-tenant scheduler;
- provider-specific protocol proxies;
- features whose success cannot be observed in the canonical handoff.

## Weekly operating review

At least weekly, record:

- current phase and unmet exit criteria;
- successful and failed full loops;
- the largest source of manual assistance;
- time to safe-to-close and Land acknowledgement;
- repeated usage by user;
- payment commitments;
- security, reliability, and cost incidents;
- the one hypothesis the next build or interview will test.

Do not let a backlog substitute for a decision about the current gate.
