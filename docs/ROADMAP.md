# Zero-to-Launch Roadmap

Last updated: 2026-09-02

## Roadmap principle

Lift advances by evidence gates, not by accumulating infrastructure.

```text
prove provider path
        -> prove exact workspace transplant
        -> prove phone continuation
        -> prove safe Land
        -> prove repeated behavior
        -> prove persistent reuse and repeat mobile launch
        -> prove payment
        -> prove multi-agent coordination
        -> prove small-team collaboration
        -> scale access
```

Do not enter the next phase because the calendar says so. Enter when the current phase's exit criteria are true.

The canonical implementation and evidence snapshot is [`CURRENT_STATE.md`](CURRENT_STATE.md).

The long-term destination is the project-centric cloud workspace defined in [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md). This roadmap intentionally reaches it through the smallest complete solo handoff rather than treating the entire platform as one release.

## North-star capability path

The product sequence after the complete handoff is:

1. retain and reuse the same cloud workspace across days;
2. repeatedly launch completely new provider-native agent tasks after stopped-compute wake from a phone while the laptop is offline, without another local transfer;
3. create equivalent workspaces from GitHub and empty templates;
4. run multiple agent tasks, beginning with shared mode plus attribution and recovery;
5. add isolated and read-only execution modes;
6. add headless browser testing, visible browser observation, secure takeover, and project-scoped browser identity in risk-gated steps;
7. prove provider neutrality with a second agent;
8. prove one supported provider-owned cloud computer can participate as a replaceable execution location without owning the project;
9. add team-lite workspace membership and GitHub-derived access;
10. deepen collaboration, permissions, and governance only when observed use requires them.

The limited shared-mode experiment in Phase 3 intentionally precedes broad cloud-origin and isolation support so design partners can expose coordination failures early. It does not promote multi-agent operation to a supported platform capability before the Phase 4 gates.

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

### Current evidence

The founder EC2 spike now passes the provider-path portion once: direct phone control, strongly corroborated laptop-off execution, EC2 stop/start recovery, exact post-restart folder binding, guarded native approval observation, versioned checkpointing, exact S3 restore, and a fresh `safeToClose: true` evaluation. On 2026-09-02, generated fixtures also passed both live Land outcomes once: the clean run completed the EBS writer fence, immutable final `C`, exact-version restore/import, local application, durable two-sided acknowledgement, ownership return, and post-ack compute stop; a separate fresh same-file conflict run restored its exact final `C`, returned `NEEDS_REVIEW`, preserved the untouched local workspace and exact private `B/L/C` stages, retained `LANDING`, fenced cloud writers, omitted acknowledgement and cleanup, and was byte-stable on retry. The full local suite passes. Phase 0 remains narrow: explicit real-workspace manifest review, conflict-resolution UX, additional interruption runs, automatic offline-helper continuation, repeated clean/conflict evidence, and the zero-terminal journey remain open. Provider-service identity isolation, network recovery, revocation, provider-policy review, and repetition remain separate pre-alpha or compatibility-promotion gates.

| Phase 0 gate | Current state |
| --- | --- |
| Direct provider-native phone path | Passed once on the founder's existing phone client; still Experimental |
| Laptop-off evidence | Strongly corroborated once; not cryptographic device attestation |
| EC2/EBS stop/start recovery | Passed once |
| Post-restart exact folder and runtime binding | Passed once with `projectId: null`; controller project visibility remains unknown |
| Guarded approval/proof turn | Passed once; selected decision and responder identity remain unavailable |
| Immutable checkpoint and exact restore | The first run's four checkpoints passed exact-version restore through `0004-land-final`; the fresh conflict run's exact `0002-land-final` also passed restore |
| Phase 0 private capture and return merge | One clean and one deliberate-conflict live founder-fixture transaction passed; repeat, conflict-resolution, offline-helper, and broader interruption evidence remain pending |
| Real-workspace capture and complete product Land | Phase 1 target; not implemented |
| No-terminal customer journey | Phase 1 target; not implemented |
| Provider-service and credential isolation | Pre-alpha blocker; not implemented |
| Network recovery, revoke, provider-policy review, repetition | Compatibility/promotion gates; not yet tested |

### Immediate next evidence gate

Build the smallest explicit real-workspace manifest/review flow while continuing adversarial fixture evidence:

1. separate discovery from permission and show a versioned candidate manifest before any real-workspace upload;
2. require explicit inclusion of ignored or sensitive files and hard-exclude credentials, unrelated paths, and unapproved content;
3. bind the approved manifest to baseline `B` and the later checkpoint/Land ledger, preserving the user's branch, refs, real index, and working tree;
4. run the reviewed flow on one noncritical real repository only after the transfer boundary is inspectable;
5. repeat clean and conflicted live fixture round trips from additional fresh sessions, requiring every conflict to stay fenced in `LANDING` with both sides preserved and no acknowledgement or cleanup;
6. interrupt fresh fixture runs at the durable phase boundaries and verify stable `C`, receipt, acknowledgement, and lease identities on retry;
7. separately implement and test a Land request made while the original helper is offline and automatic continuation on reconnect.

### Evidence recorded on 2026-09-01

- A real Ubuntu EC2 instance ran the provider-blind workload recipe against a real workspace on a separate encrypted EBS volume.
- ChatGPT on the founder's phone paired directly with the EC2-hosted Codex Remote environment and controlled the intended workspace without a desktop relay in the data path.
- A fresh laptop-off challenge was issued immediately before the founder shut down the Mac; the exact nonce, source, and cloud `cwd` were then written from the phone, and later Mac reboot timestamps strongly corroborated the shutdown. This is human-attested founder evidence, not cryptographic proof of device power state, so the public laptop-off promotion gate remains open.
- Immutable Lift-private Git checkpoints `0001` and `0002` were created on the exact encrypted EBS workspace. Checksummed bundles and manifests were stored as versioned private S3 objects, downloaded by exact version, and restored into fresh repositories with commit, tree, history-ref, and evidence verification.
- One EC2 stop/start changed the guest boot ID while the exact encrypted EBS volume reattached. Checkpoint `0002`'s commit and bundle and both proof files recovered, the provider-neutral systemd runner auto-started healthy, and the exact Codex Remote environment ID was preserved.
- Server-side native-project reconstruction after that restart passed. At the end of 2026-09-01, end-to-end recovery still required a fresh post-baseline phone task, approval/proof evidence, and a following restore-tested checkpoint.

### Evidence recorded on 2026-09-02

- A brand-new phone task in the existing EC2 folder connection retained the exact canonical `cwd`, null project assignment, and correct runtime roots.
- The root-owned passive observer and independent historical verifier agreed on the exact approval canary, resolution lifecycle, proof command, successful completions, and unchanged policy guard. The selected decision remains a guarded official-client inference because the public protocol omits it.
- Immutable checkpoint `0003-post-restart-phone-proof` was uploaded as checksummed, versioned private S3 objects and restored into a fresh repository with exact commit, tree, file-count, manifest, and evidence verification.
- Fresh live status reported EC2 running, Systems Manager online, the generic runner active/healthy/ready, Codex Remote connected, all handoff gates true, and `safeToClose: true`.
- Founder fixture run `p0-20260901083520-4fee` sealed `0004-land-final` at commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`; the exact versioned S3 bundle and manifest restored successfully.
- The first Land attempt stopped safely at controller phase `FINAL_CHECKPOINT_DURABLE` on a `/run` parent-directory mode mismatch. After the permission fix, the same operation reused the same `C` and completed with `APPLIED` merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`.
- The guest reached `ACKNOWLEDGED`, the controller lease returned to `LOCAL_PRIMARY`, and compute stopped only after acknowledgement.
- Fresh disposable run `p0-20260902183748-a7b1` exercised a deliberate both-modified conflict. Exact restore-tested `0002-land-final` was imported; Land returned `NEEDS_REVIEW`; controller and guest stayed `LANDING`; the original local content and Git state stayed exact; private stages preserved `B/L/C`; no acknowledgement or cleanup occurred; the cloud writer remained fenced; and a repeated Land returned `changed: false` without mutating its evidence.
- Separate provider-service identity and credential isolation are pre-alpha gates. Explicit real-workspace review, network interruption, revocation, repeated laptop-off and clean/conflict runs, broader interruption coverage, conflict-resolution UX, automatic offline-helper continuation, and the complete no-terminal journey remain pending.

### Exit criteria

- one provider path truthfully supports the claimed phone continuation, or the product explicitly changes its first provider/claim;
- Git-backed capture and merge work with tracked, dirty, staged, untracked, and approved ignored files;
- no silent overwrite in the conflict test;
- selected runtime survives stop and wake with durable files.
- the complete disposable-fixture Land transaction passes both clean and conflicted outcomes on live EC2 without changing `C` across a retry. Each passed once on 2026-09-02; repetition and broader interruption evidence remain open.

### Do not build yet

- production control plane;
- multi-provider UI;
- teams;
- preview gateway;
- billing;
- arbitrary runtime abstraction beyond the thin interface required by the spike.

These are sequencing constraints for Phase 0, not rejections of the product north star.

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
- separate provider-service identity and credential isolation from untrusted workspace execution;
- stop, delete, and emergency revoke.

### Exit criteria

- a real project goes local -> cloud -> phone -> local;
- laptop is fully off during useful agent work;
- Land returns the exact expected content;
- no terminal, SSH command, cloud console, or copied token appears after installation;
- the complete demo can be shown in under three minutes excluding agent generation and cold provisioning.
- after the laptop is off, the founder can launch a completely new Codex task from the phone into the exact Lift workspace without a desktop relay.

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
- persistent reuse of the same cloud workspace across several days;
- mobile launch of new agent tasks after stop and wake;
- measurement of which tasks the founder would have postponed or run locally without Lift.

### Exit criteria

- at least five successful real handoffs;
- at least three occur because the laptop genuinely needed to close;
- clean Land succeeds every time;
- all intentional conflicts preserve both sides;
- no unrecoverable workspace or credential incident;
- founder can explain every status without infrastructure vocabulary.
- at least three useful agent tasks begin from the phone while the laptop is offline;
- the workspace is reused across several days without a full environment reconstruction.

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
- a limited multi-agent experiment for qualified users, beginning with shared mode plus a pre-run checkpoint, attribution, overlap detection, and recovery;
- a manual H14 comparison with users who already use at least two provider-owned cloud-agent environments, without building the external agent-computer gateway;

### Exit criteria

- at least 5 of 10 invited users complete the loop;
- at least 3 repeat it on three occasions;
- at least 2 pay or place a deposit;
- second-wave users require less assistance than the first;
- zero data-loss, cross-user, credential-exposure, or false-safe-to-close incidents.
- at least three users launch a new useful task from mobile while their laptop is offline;
- multi-agent participants use parallelism for a real task rather than only exploring the feature.
- H14 is measured with at least five qualified cross-provider users; if fewer than three repeatedly prefer one durable project across providers for coordination, environment, permission, provenance, or recovery reasons, revise or reject the standalone workspace thesis before private beta.

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
- GitHub-created workspace beta for users who prefer cloud-first setup;
- optional isolated and read-only agent-task modes after shared-mode behavior is observed;
- headless browser testing behind explicit workspace network policy;

### Exit criteria

- at least 20 paying users or another deliberately chosen sample large enough to observe repeat behavior;
- at least one retained user renews into a second paid month rather than returning to a laptop, VPS, or provider-owned workspace;
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
- at least one provider can launch a completely new, correctly bound task from its native phone application while the originating laptop is offline, including wake from stopped compute when applicable;
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

1. reliability, mobile-launch latency, and wake-speed improvements;
2. broaden the earlier GitHub-created workspace beta and add equivalent empty/template creation;
3. generalize the earlier shared-mode experiment into supported simultaneous-agent shared, isolated, and read-only modes;
4. second first-class provider connection;
5. broaden the earlier headless-browser beta into supported testing and authenticated previews;
6. visible browser observation, secure takeover, and project-scoped browser identity;
7. more local operating systems and repository shapes;
8. optional sanitized GitHub pull-request publication;
9. supported provider-owned agent-computer attachment and result ingestion;
10. team-lite workspace membership and GitHub-derived access;
11. reusable environment profiles, BYO cloud, and deeper collaboration controls.

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

Maintain schemas and boundaries that can support multiple agent tasks, browser contexts, workspace membership, and GitHub-created origins later. Scope discipline forbids premature implementation, not forward-compatible architecture.

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
