# Validation and Design-Partner Playbook

Last updated: 2026-09-02

## Objective

Prove that Lift changes repeated behavior before building the broad cloud-computer vision.

The evidence hierarchy is:

```text
observed behavior -> real repository handoff -> repeated handoff -> payment -> retention
```

Compliments, waitlist signups, and “I would use this” statements are weak evidence unless they lead to the next behavior.

## Critical hypotheses

| ID | Hypothesis | Cheapest credible test | Pass signal | Failure response |
| --- | --- | --- | --- | --- |
| H1 | The ICP encounters laptop-blocked agent work at least weekly. | Ten workflow interviews with recent examples. | At least six show a real event in the last 14 days. | Narrow the trigger or change the ICP. |
| H2 | Active local-state transplant matters more than starting cloud-first. | Concierge comparison on a dirty repository. | At least five of eight prefer Lift Off over reconstructing cloud-first. | Reconsider continuity as the wedge. |
| H3 | Codex can continue directly from phone while the laptop is off. | Real Ubuntu EC2 pairing and reconnection spike. | Start, bind one canonical post-baseline challenge to a fresh task in the exact registered project/root, complete its native approval round trip, create and restore-test the challenge-bound checkpoint, disconnect, restart, and recover without a desktop relay. | Do not market Codex laptop-off; validate Claude first or change the first provider. |
| H4 | Supported setup can avoid terminals and copied tokens. | Connections prototype with provider-owned auth. | Eight of ten complete it without help. | Reduce provider scope or redesign the connection path. |
| H5 | Users trust Lift with a real noncritical repository. | Manifest review plus explicit transfer. | Five design partners complete a real upload. | Improve security model, transparency, or target less sensitive work. |
| H6 | Land makes return feel safe. | Deliberate clean and conflicted return tests. | All clean merges succeed; every conflict preserves both sides; users understand the outcome. | Stop expansion and fix state safety. |
| H7 | The full loop repeats. | Two-week design-partner cohort. | At least three of ten users complete three or more handoffs. | Investigate frequency, wake time, mobile value, and onboarding. |
| H8 | The outcome supports payment. | Ask for a deposit after a successful handoff. | At least two of ten pay or place a meaningful deposit. | Test pricing and value before more infrastructure work. |

Evidence recorded on 2026-08-31: the local Ubuntu precursor paired ChatGPT mobile directly to headless Linux, changed one file in the selected persistent workspace, created a durable Git checkpoint, and cleanly fast-forwarded the disposable original.

Evidence recorded on 2026-09-01: the same experimental direct path was repeated on a real Ubuntu EC2 workspace backed by encrypted EBS. ChatGPT on the founder's phone controlled the intended cloud workspace. The founder reported shutting down the Mac after a fresh unpredictable challenge was armed; the exact nonce, source, and cloud `cwd` appeared in the EBS workspace afterward, and later Mac reboot timestamps strongly corroborated the sequence. This is strong founder dogfood evidence, not cryptographic device attestation or an independently observed release test.

The EC2 run produced immutable Lift-private Git checkpoints `0001`, `0002`, and the post-restart phone checkpoint `0003`. Their checksummed bundles and manifests were stored as versioned private S3 objects and restored by exact version into fresh repositories with commit, tree, history-ref, and evidence-file verification. This materially de-risks durable cloud checkpointing, but it does not pass H6 because clean and conflicted Land back into the real local workspace remain untested.

The current capture harness intentionally accepts only its generated disposable fixture and refuses an unmarked workspace before creating the private ledger. It includes the fixture's known untracked file and one marker-declared ignored path to exercise state preservation. This is not the production manifest-review flow and is not evidence that a real user's untracked or ignored files can be uploaded safely without explicit selection.

A subsequent EC2 stop/start changed the guest boot ID while preserving the exact encrypted workspace volume, checkpoint `0002`'s commit and bundle, both proof files, a healthy automatically restarted provider-neutral systemd runner, and the exact Codex Remote environment ID. This passes structural compute-restart recovery once.

The first mobile attempts after that restart revealed that process health was an insufficient readiness signal: Codex had no native project registered and routed tasks into projectless paths outside Lift's writable root. A version-pinned connector now uses the live Codex App Server API to register and read back the exact EBS workspace and configure only that root. Registration no longer depends on transient Remote or controller presence; the separate readiness command requires connected Remote state plus a paired controller. At `2026-09-01T19:28:58Z`, read-only live verification observed runner `active: true`, `healthy: true`, and `ready: true`; Codex CLI/App Server `0.152.0`; Remote `connected`; one registered controller; native project `01a05e65-3e1a-7e81-bc34-9bbc868b6155`; and exact root `/home/lift/workspaces/lift-ec2-spike`. Projectless home paths remained outside the writable service boundary.

On 2026-09-02, the repaired post-restart path passed H3 once as founder dogfood. A brand-new phone task in the existing `ip-10-67-0-26` connection bound to the exact EBS workspace with `projectId: null`, completed the exact two-command challenge, emitted the observed approval lifecycle, and produced the exact proof bytes. The following immutable checkpoint `0003-post-restart-phone-proof` (`674bd2722b961caf1e91db98f582330b6b4a54b5`) was stored as checksummed, versioned private S3 objects and restored into a fresh repository with exact commit, tree, file-count, manifest, and evidence verification. Fresh live status then reported the EC2 instance running, Systems Manager online, the provider-neutral runner active/healthy/ready, Codex Remote connected with one paired client, all readiness gates true, and `safeToClose: true`.

This closes the single-run technical feasibility question in H3; it does not make the path launch-ready. The public protocol reports that the approval request resolved but does not expose the selected decision or responder identity, so the one-time approval result remains a guarded inference scoped to the official founder-controlled client. Separate provider-service identity and credential isolation are pre-alpha security gates; network interruption, revocation, provider-policy compatibility, repeated independent laptop-off runs, and complete conflict-safe Land remain promotion gates. Do not turn this founder-only evidence into a public compatibility claim.

Implementation hardening completed after that observation now makes the remaining H3 attempt one fail-closed evidence chain. An exact schema-v3 challenge is canonically hashed; the active challenge, fresh-thread proof, guarded approval inference, checkpoint, and safe-to-close evidence must share that digest. The implementation rejects stale post-restart aliases, reused or multi-turn tasks, source/path/label substitutions, mismatched proof bytes, any approval policy except exact `on-request`, network-enabled approval evidence, non-user review, active exec-policy rules, effective or managed hooks, hook discovery errors, opaque active config layers, config/rules/hooks/plugin-state guard drift, non-agent or plugin-script provenance, plugin or MCP tool items, unreviewed tool items, and either command deviating from its independently reconstructed digest. Installed plugins may remain enabled, but their bounded complete `plugin/list` response is hashed before and after the attempt. This is evidence of a fixed observed plugin environment and no observed plugin execution, not proof that plugin skill metadata was absent from model context or that a remote bundle was content-immutable. It also rejects project, `cwd`, runtime-root, environment, or native-project mismatches.

The approval path now has a passive live-event observer in addition to the independent historical verifier. The controller launches the observer as a hardened root-owned transient systemd service from checksum-verified root-owned files. After App Server initialization, it must find no fresh post-baseline task before atomically writing its root-owned private readiness record; the phone prompt is blocked until the controller validates that record. It then stays through the exact request, matching `serverRequest/resolved`, successful canary, successful proof command, and `turn/completed`, binding the full two-command turn to the challenge, guard, baseline, environment, project, `cwd`, request, thread, turn, item identities, command hashes, and event order. The historical verifier separately re-reads the completed one-turn task and enforces the exact two commands, policy, reviewer, sandbox, provenance, and absence of unreviewed items; neither verifier substitutes for the other.

The checkpoint records both the selected evidence challenge and the underlying phone challenge, requires nonempty version IDs, restores the exact required evidence bytes from versioned recovery objects, validates restore hashes, commit, tree, file count, and timestamp, and rechecks at least one hour of live auto-stop time before reporting ready. Local state and events use private no-follow, ownership-checked, size-bounded, atomic and durable file operations. Unit coverage exercises observer readiness and full-turn event order, root-owned service and evidence binding, controller mutation rejection, post-restart source preservation, stale-alias rejection, exact physical proof-path walking, command-smuggling and provenance rejection, config/rules/hooks/plugin-state guard rejection, approval-policy rejection, restore/version/timer failures, local control-file link attacks, and tampered digest/evidence failure. The full 125-test spike suite passes locally. Observer schema v8 was deployed as an immutable runtime bundle and exercised by the successful live phone task. The observer accepted the source-authentic nested decision schema `execpolicy_amendment`, then recorded the request, matching resolution, both successful command lifecycles, and successful turn completion; the independent historical verifier agreed before checkpointing. The provider still does not expose the decision payload or responder identity to the observer, so the result remains a guarded founder-only inference rather than proof that a particular phone user tapped Approve. Separate provider-service identity and credential isolation remain pre-alpha gates because the current provider daemon and workload share the `lift` Unix identity. A high-assurance plugin boundary also remains a promotion gate because public Codex documentation does not establish that `plugin/list` binds immutable plugin contents.

The harness also now treats persisted AWS identifiers as claims to verify against the live control plane. Before deployed-runtime operations, it requires the stored AWS account and `lift-admin` principal, run-derived stack name and exact stack ID, canonical paths and typed outputs, then re-reads CloudFormation. The live stack must be in a completed safe state with the expected parameters and identical outputs, while its `WorkspaceInstance`, `WorkspaceVolume`, and `TransferBucket` resources must have the expected types, physical IDs, and completed statuses. The selected Ubuntu AMI is revalidated as an available x86_64 image owned by Canonical. Unit coverage exercises wrong stack IDs, output drift, parameter drift, and resource mismatches. These controls prevent the test harness from silently acting on a stale or substituted environment; the next live run must still demonstrate them against the authenticated Lift AWS account.

## Phase 1: Problem interviews

Recruit 10 to 15 people matching [`ICP.md`](ICP.md). Ask for screen-shared evidence and recent behavior.

### Interview script

1. Walk me through the last coding-agent task you started locally.
2. Show me what was in the working tree before the task began.
3. When did you next need to leave or close the laptop?
4. What happened to the task?
5. What workaround did you use, if any?
6. What would have been missing on a new cloud machine?
7. Which files or credentials would you refuse to transfer?
8. How did you get the result back into your normal workspace?
9. What has this problem cost in time, interruption, or abandoned tasks?
10. Show me any VPS, remote-control, or cloud-agent setup you already maintain.

Do not pitch Lift until the workflow is understood. Afterward, show only the one-sentence promise and ask what would prevent a real test.

### Capture template

```text
Participant:
ICP score:
Agent/provider:
Recent trigger:
Current workaround:
Local state that mattered:
Frequency:
Trust boundary:
Expected phone interface:
Return workflow:
Money/time already spent:
Real test repository:
Commitment made:
Unexpected evidence:
```

## Phase 2: Concierge handoff

Before polished automation, manually complete the loop with the founder and three to five design partners:

1. inspect a noncritical dirty repository together;
2. show exactly what moves;
3. transfer it to the prototype workspace;
4. establish the supported provider-native connection;
5. require the participant to close the laptop;
6. complete one useful phone-directed change;
7. Land through the Git-backed return flow;
8. inspect the local result and any conflicts together;
9. ask for a deposit immediately after success.

Record every moment requiring explanation or manual intervention. Each repeated explanation is a candidate product requirement.

## Phase 3: Founder dogfood

Use Lift as the default environment transition for one real project over seven days.

Required scenarios:

- clean working tree;
- dirty tracked file;
- staged plus unstaged changes;
- untracked and explicitly approved ignored file;
- laptop offline before Land;
- runtime stop and wake;
- provider reauthentication;
- cloud process crash;
- nonoverlapping local divergence;
- direct same-file conflict;
- failed network during local application.

Log whether Lift saved a real laptop opening, not merely whether the system ran.

## Phase 4: Design-partner cohort

Invite 10 users in two waves of five. The first wave gets white-glove onboarding; the second should receive less help.

### Required first session

- connect the provider;
- select a real repository;
- review the transfer boundary;
- reach safe-to-close;
- close the laptop completely;
- continue in the provider application;
- create a visible useful change;
- Land and verify the local result;
- choose whether to pay or deposit.

### Follow-up cadence

- immediately after first Land: outcome and trust interview;
- 24 hours: did they use it again or avoid it?;
- day 7: repeat usage, blockers, and willingness to pay;
- day 14: retention decision and cancellation reason.

## Commitment ladder

Move prospects through increasingly costly commitments:

1. agrees to an interview;
2. shows a real workflow;
3. installs the helper;
4. selects a real repository;
5. transfers actual state;
6. closes the laptop;
7. repeats without the founder present;
8. places a deposit or pays;
9. keeps using it after the novelty period;
10. refers another qualified user.

Optimize for progression, not the size of the top-of-funnel list.

## Alpha scorecard

Track per user:

| Measure | Target |
| --- | --- |
| Provider connection completed | Yes |
| First Lift Off completed | Yes |
| Terminal/manual setup needed | No |
| Safe-to-close was truthful | Yes |
| Laptop actually closed | Yes |
| Useful phone-directed change completed | Yes |
| Land acknowledged locally | Yes |
| Data loss or silent overwrite | No |
| Second handoff within seven days | Yes |
| Paid or deposited after success | Yes/No |

## Go, iterate, and stop rules

### Continue toward paid beta

- at least 5 of 10 invited users complete the full loop;
- at least 3 repeat it on three separate occasions;
- at least 2 pay or place a deposit;
- median assisted setup time declines across the cohort;
- no data-loss, credential, or false-safe-to-close incident occurs;
- users describe laptop independence or state continuity as the value.

### Iterate before expanding

- users succeed only with founder assistance;
- the loop works but wake or transfer time prevents repeated use;
- conflicts are safe but confusing;
- users value the product but reject the current price;
- one provider blocks the flow while another can support it.

### Stop or change the wedge

- qualified users rarely encounter the trigger;
- most prefer starting cloud-first;
- users will not transfer even noncritical repositories;
- the provider-native phone path cannot work without the laptop;
- repeated usage remains below three users after two focused cohorts;
- payment interest remains zero after successful real handoffs.

## Evidence log

For every material conclusion, add an entry to the relevant research or decision document:

```text
Date:
Hypothesis:
Test:
Participants/sample:
Observed behavior:
Result:
Confidence:
Decision changed:
Next test:
```

Separate observed evidence from inference. A strong anecdote can reveal a mechanism but cannot establish frequency by itself.
