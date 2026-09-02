# Analytics and Learning System

Last updated: 2026-09-02

## Measurement principle

Measure the completed behavior Lift exists to create. Do not substitute page views, prompts, runtime hours, agent count, or waitlist size for successful laptop-independent work and retained workspace use.

## North-star event

The north-star unit is an:

> Acknowledged closed-laptop loop

It occurs when one workspace:

1. reaches verified safe-to-close;
2. is continued through the provider application while the local helper is offline;
3. produces a cloud change;
4. Lands successfully; and
5. receives local acknowledgement without lost work.

Track weekly acknowledged closed-laptop loops and the number of users completing at least one.

This remains the beachhead activation event. After persistent workspace use ships, the long-term north-star unit becomes a `weekly useful workspace`: one durable workspace that completes at least one user-accepted agent task during the week without environment reconstruction. Segment it by local, GitHub, or empty origin; mobile or desktop launch; provider mix; agent count; and human participant count without collecting repository identity or task contents.

If provider telemetry cannot prove phone activity, use the strongest available provider readiness signal plus an explicit lightweight user confirmation. Never infer “laptop closed” merely from a disconnected socket.

The 2026-09-02 founder Phase 0 runs are technical feasibility evidence, not activation events. The first completed a clean acknowledged round trip on the generated disposable fixture through real EC2/EBS/S3 and the Mac: exact `0004-land-final` was restored and imported, reconciliation returned `APPLIED`, the guest stored the exact acknowledgement, ownership returned to `LOCAL_PRIMARY`, and EC2 stopped. Fresh generated-fixture run `p0-20260902183748-a7b1` then passed a deliberate same-file conflict: restore-tested `0002-land-final` remained durable, reconciliation returned `NEEDS_REVIEW`, ownership remained `LANDING`, the original local fixture was untouched, both local and cloud sides remained recoverable, the runner stayed fenced, compute was retained, and retry returned the same result with `changed: false`. Both runs still used founder-operated terminal steps and did not exercise an arbitrary real workspace, customer UI/helper, automatic offline-helper wake, or conflict-resolution UI. H6 and private-alpha activation remain unaccepted; broader repetition and interruption coverage, production isolation, network recovery, revocation, and the no-terminal journey remain gates. No customer is activated until the full product loop above passes. See [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Activation definition

A user is activated only after the first acknowledged closed-laptop loop.

Intermediate milestones are diagnostics:

```text
account created
provider connected
workspace selected
manifest approved
Lift Off started
safe-to-close reached
provider continuation confirmed
cloud change checkpointed
Land started
local revision acknowledged
activated
```

## Core event taxonomy

| Event | Required properties | Meaning |
| --- | --- | --- |
| `account_created` | anonymous acquisition source | Lift account exists. |
| `provider_connect_started` | provider, recipe version | User starts provider-owned auth. |
| `provider_connect_completed` | provider, elapsed_ms, result | Reusable connection is ready. |
| `provider_connect_failed` | provider, safe error class, stage | Connection needs recovery. |
| `workspace_selected` | workspace_id, repository class, local OS | Local folder is approved for inspection. |
| `workspace_created` | workspace_id, origin class, runtime class | A durable workspace exists from local, GitHub, or empty/template origin. |
| `manifest_reviewed` | workspace_id, included counts, excluded counts, exceptions | Transfer boundary is approved. |
| `liftoff_started` | workspace_id, provider, warm_or_cold | One-button handoff begins. |
| `liftoff_stage_completed` | workspace_id, stage, elapsed_ms | Diagnoses where time is spent. |
| `safe_to_close_reached` | workspace_id, provider, elapsed_ms, readiness evidence class | Laptop independence is claimed. |
| `safe_to_close_failed` | workspace_id, safe error class, stage | Claim was withheld. |
| `local_helper_offline` | workspace_id | Supporting signal, not proof of lid closure. |
| `provider_continuation_confirmed` | workspace_id, evidence class | Existing provider client reached the Lift session. |
| `agent_launch_requested` | workspace_id, provider, launch surface, execution mode, initiator class | A human or agent asks to begin a new task. |
| `agent_launch_bound` | workspace_id, provider, launch surface, execution mode, binding evidence class, elapsed_ms | A new task is verified in the intended workspace. |
| `agent_task_completed` | workspace_id, provider, execution mode, result class, accepted | An agent finishes with a reviewable result. |
| `agent_task_stopped` | workspace_id, provider, reason class | A user, policy, or runtime stops an agent task. |
| `shared_write_overlap_detected` | workspace_id, opaque task IDs, overlap class | Shared-mode tasks touched overlapping state. |
| `shared_write_recovered` | workspace_id, recovery class, result | A collision or overwrite was preserved or restored. |
| `browser_session_started` | workspace_id, mode, authenticated, agent count | A scoped headless or visible browser capability begins. |
| `browser_takeover_completed` | workspace_id, result class, elapsed_ms | A user completes a human-only browser step without recording its contents. |
| `collaborator_invited` | workspace_id, role | A team experiment begins. |
| `collaborator_joined` | workspace_id, role, auth source class | An invited participant enters the workspace. |
| `cloud_checkpoint_created` | workspace_id, revision, changed counts | Durable work exists. |
| `land_started` | workspace_id, initiated surface | Return begins. |
| `land_checkpoint_created` | workspace_id, revision, elapsed_ms | Final cloud state is durable. |
| `land_merge_completed` | workspace_id, clean_or_conflicted, changed counts | Private three-way merge finished. |
| `land_local_applied` | workspace_id, elapsed_ms | Verified result reached the local folder. |
| `land_acknowledged` | workspace_id, revision | Ownership returned to local. |
| `session_ledger_sealed` | workspace_id, opaque session_id, checkpoint_count, final outcome class | Restorable history was retained after acknowledged clean Land, explicit conflict resolution, or another explicit session finish. |
| `land_needs_review` | workspace_id, conflict classes and counts | Both copies were preserved and this Land operation remains unresolved. |
| `workspace_stopped` | workspace_id, reason | Compute stopped without deleting state. |
| `workspace_deleted` | workspace_id, retention outcome | User requested deletion. |
| `deposit_paid` | user_id, offer version | Behavioral willingness-to-pay evidence. |
| `subscription_started` | user_id, package version | Paid conversion. |
| `subscription_renewed` | user_id, package version, renewal ordinal | A user paid for a subsequent month. |

For `safe_to_close_reached` and `provider_continuation_confirmed`, record nonsecret enumerated evidence classes rather than a generic success boolean. The current experimental classes distinguish server project registration from `folder-bound-project-unassigned`, a guarded approval inference from a provider-attributed decision, and a restore-tested following checkpoint from a merely created checkpoint. Also record the verdict validity interval. Never emit an analytics property that implies a specific approval decision, responder identity, controller project assignment, or cryptographic laptop-off attestation when the underlying protocol did not provide it.

Do not emit `session_ledger_sealed` merely because a conflict is safely preserved. An unresolved `NEEDS_REVIEW` operation emits `land_needs_review` and keeps its recovery evidence open; sealing occurs only after an explicit resolution or finish policy reaches a real terminal outcome.

## Privacy rules

Analytics must never collect:

- source code or file contents;
- prompts or agent transcripts;
- raw filenames or absolute local paths;
- environment-variable values;
- tokens, cookies, pairing secrets, or credentials;
- terminal output;
- Git diffs;
- provider conversation identifiers unless explicitly required, minimized, and documented.

Use opaque workspace IDs, enumerated error classes, aggregate file counts, byte counts, elapsed time, and capability flags.

Operational logs with sensitive diagnostic data require a separate access and retention policy; they are not product analytics.

## Primary funnels

### Connection funnel

```text
Connect clicked -> provider auth completed -> reusable connection healthy
```

### Lift Off funnel

```text
workspace selected -> manifest approved -> Lift Off -> safe-to-close
```

### Magic-moment funnel

```text
safe-to-close -> provider continuation -> cloud change -> Land acknowledged
```

### Persistent workspace funnel

```text
workspace created -> new task launched -> useful result accepted -> workspace reused on another day
```

### Multi-agent funnel

```text
first task running -> second task launched -> overlap handled -> useful result accepted
```

### Team-lite funnel

```text
workspace retained -> collaborator invited -> collaborator joined -> shared useful task completed
```

### Commercial funnel

```text
qualified lead -> real test -> activated -> repeated -> deposit -> paid -> retained
```

Segment every funnel by provider, recipe version, runtime image, helper version, warm/cold runtime, acquisition source, and cohort. Do not segment by data that exposes repository identity.

## Product metrics

### Activation and use

- invitation-to-provider-connection rate;
- connection-to-first-Lift-Off rate;
- Lift-Off-to-safe-to-close rate;
- safe-to-close-to-acknowledged-Land rate;
- median and p95 time to safe-to-close;
- median and p95 Land acknowledgement time while the helper is online;
- percentage of loops requiring terminal or founder intervention;
- percentage of users who confirm the laptop was actually closed;
- handoffs per activated user per week.
- new mobile-launched tasks while the originating laptop is offline;
- weekly useful workspaces;
- multi-day workspace reuse without reconstruction;
- useful agent tasks per retained workspace;
- workspaces with two or more agents;
- workspaces used by two or more agent providers or execution locations;
- shared, isolated, and read-only mode selection and completion;
- collaborator invitation, join, and retained team-workspace rates;

### Retention

- second handoff within seven days;
- users with three handoffs in 14 days;
- weekly retained activated users;
- 28-day paid retention;
- reactivation after an idle week;
- reason for nonrepeat usage.

### Continuity quality

- clean Land rate;
- intentional and unintentional conflict rate;
- conflict-review completion rate;
- local acknowledgement failures;
- cloud revisions waiting for a local helper;
- retries by state transition;
- recovery-journal activations;
- false safe-to-close incidents;
- data-loss or silent-overwrite incidents.
- unattributed workspace mutations;
- shared-mode overlap detection and recovery outcomes;
- cross-agent browser or secret exposure incidents;

### Business

- successful-loop-to-deposit conversion;
- activated-to-paid conversion;
- revenue and COGS per active user;
- support minutes per activated user;
- retained-user acquisition source;
- referral rate.

## Initial decision thresholds

For the first 10 invited users:

- at least 5 complete the full loop;
- at least 3 repeat three times;
- at least 2 pay or deposit;
- zero data-loss, credential, cross-user, or false-safe-to-close incidents;
- median manual assistance declines from wave one to wave two.

These are stage gates, not statistically stable benchmarks.

## Reliability indicators

Track each lifecycle transition as a durable operation with:

- attempt ID;
- desired state;
- previous state;
- start and completion time;
- retry count;
- idempotency key;
- safe error class;
- resulting revision or runtime identifier.

The product dashboard and operational dashboard should derive status from the same state machine. Avoid a marketing-facing success state that is not backed by runtime evidence.

## User feedback prompts

Ask at moments where memory is fresh:

### After safe-to-close

> Do you believe you can close the laptop now? If not, what still feels dependent on it?

### After first Land

> Would you otherwise have kept the laptop open for this task?

### After conflict recovery

> Was it clear that neither copy was overwritten?

### After seven days without reuse

> Did you lack the need, avoid Lift, or use another workaround?

### After the first new mobile launch

> What would you have done if this workspace had not been available from your phone?

### After the first multi-agent task

> Why did you run these tasks together, and did shared or isolated work match what you expected?

### After a collaborator joins

> Did sharing the functioning workspace remove setup or coordination work that GitHub alone did not?

Store structured answers and concise notes without source-code or transcript content.

## Experiment record

Every material product experiment should include:

```text
Name:
Hypothesis:
Primary metric:
Guardrail metric:
Target segment:
Variant or intervention:
Start and stop criteria:
Result:
Decision:
```

Do not run growth experiments that increase activation while weakening security, recoverability, or truthfulness of safe-to-close.

## Weekly dashboard

Review:

1. qualified users invited;
2. full loops attempted and acknowledged;
3. users repeating;
4. paid commitments;
5. time by Lift Off and Land stage;
6. manual interventions;
7. conflicts and recoveries;
8. security or reliability incidents;
9. compute and support cost;
10. top observed reason for abandonment.
11. weekly useful workspaces and multi-day reuse;
12. new mobile launches and correctly bound starts;
13. multi-agent overlap and recovery;
14. team invitations and repeated shared use when enabled.

End the review with one product decision and one validation action for the next week.
