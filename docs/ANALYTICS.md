# Analytics and Learning System

Last updated: 2026-09-02

## Measurement principle

Measure the completed behavior Lift exists to create. Do not substitute page views, prompts, runtime hours, or waitlist size for successful laptop-independent handoffs.

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

If provider telemetry cannot prove phone activity, use the strongest available provider readiness signal plus an explicit lightweight user confirmation. Never infer “laptop closed” merely from a disconnected socket.

The founder Phase 0 run is technical feasibility evidence, not an activation event: it used a generated fixture, manual terminal steps, and no complete Land. No user is activated until the full acknowledged loop above passes. See [`CURRENT_STATE.md`](CURRENT_STATE.md).

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
| `manifest_reviewed` | workspace_id, included counts, excluded counts, exceptions | Transfer boundary is approved. |
| `liftoff_started` | workspace_id, provider, warm_or_cold | One-button handoff begins. |
| `liftoff_stage_completed` | workspace_id, stage, elapsed_ms | Diagnoses where time is spent. |
| `safe_to_close_reached` | workspace_id, provider, elapsed_ms, readiness evidence class | Laptop independence is claimed. |
| `safe_to_close_failed` | workspace_id, safe error class, stage | Claim was withheld. |
| `local_helper_offline` | workspace_id | Supporting signal, not proof of lid closure. |
| `provider_continuation_confirmed` | workspace_id, evidence class | Existing provider client reached the Lift session. |
| `cloud_checkpoint_created` | workspace_id, revision, changed counts | Durable work exists. |
| `land_started` | workspace_id, initiated surface | Return begins. |
| `land_checkpoint_created` | workspace_id, revision, elapsed_ms | Final cloud state is durable. |
| `land_merge_completed` | workspace_id, clean_or_conflicted, changed counts | Private three-way merge finished. |
| `land_local_applied` | workspace_id, elapsed_ms | Verified result reached the local folder. |
| `land_acknowledged` | workspace_id, revision | Ownership returned to local. |
| `session_ledger_sealed` | workspace_id, opaque session_id, checkpoint_count, clean_or_conflicted | Restorable history was retained after Land. |
| `land_needs_review` | workspace_id, conflict classes and counts | Both copies were preserved. |
| `workspace_stopped` | workspace_id, reason | Compute stopped without deleting state. |
| `workspace_deleted` | workspace_id, retention outcome | User requested deletion. |
| `deposit_paid` | user_id, offer version | Behavioral willingness-to-pay evidence. |
| `subscription_started` | user_id, package version | Paid conversion. |

For `safe_to_close_reached` and `provider_continuation_confirmed`, record nonsecret enumerated evidence classes rather than a generic success boolean. The current experimental classes distinguish server project registration from `folder-bound-project-unassigned`, a guarded approval inference from a provider-attributed decision, and a restore-tested following checkpoint from a merely created checkpoint. Also record the verdict validity interval. Never emit an analytics property that implies a specific approval decision, responder identity, controller project assignment, or cryptographic laptop-off attestation when the underlying protocol did not provide it.

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

End the review with one product decision and one validation action for the next week.
