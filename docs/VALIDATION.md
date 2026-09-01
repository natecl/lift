# Validation and Design-Partner Playbook

Last updated: 2026-08-31

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
| H3 | Codex can continue directly from phone while the laptop is off. | Real Ubuntu EC2 pairing and reconnection spike. | Start, redirect, approve, disconnect, restart, and recover without a desktop relay. | Do not market Codex laptop-off; validate Claude first or change the first provider. |
| H4 | Supported setup can avoid terminals and copied tokens. | Connections prototype with provider-owned auth. | Eight of ten complete it without help. | Reduce provider scope or redesign the connection path. |
| H5 | Users trust Lift with a real noncritical repository. | Manifest review plus explicit transfer. | Five design partners complete a real upload. | Improve security model, transparency, or target less sensitive work. |
| H6 | Land makes return feel safe. | Deliberate clean and conflicted return tests. | All clean merges succeed; every conflict preserves both sides; users understand the outcome. | Stop expansion and fix state safety. |
| H7 | The full loop repeats. | Two-week design-partner cohort. | At least three of ten users complete three or more handoffs. | Investigate frequency, wake time, mobile value, and onboarding. |
| H8 | The outcome supports payment. | Ask for a deposit after a successful handoff. | At least two of ten pay or place a meaningful deposit. | Test pricing and value before more infrastructure work. |

Local precursor evidence recorded on 2026-08-31: ChatGPT mobile paired directly to headless Linux, changed one file in the selected persistent workspace, created a durable Git checkpoint, and cleanly fast-forwarded the disposable original. This de-risks H3 and H6 but does not pass either hypothesis: the run used iPhone Mirroring on an awake Mac, did not use EC2, and did not test dirty state, conflict return, network interruption, guest restart, or revocation.

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
