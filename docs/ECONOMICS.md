# Pricing and Unit Economics

Last updated: 2026-08-31

## Economic principle

Users pay for continuity and laptop independence, not for an EC2 instance resale.

The pricing model should:

- make the fixed product value visible;
- recover variable compute and storage costs;
- prevent surprise bills;
- reward stopping idle compute without making the product feel fragile;
- remain simple enough for a consumer to understand before Lift Off.

All prices in this document are hypotheses to test, not launch commitments.

## Value metric

The best product value metric is a persistent personal workspace with successful handoffs. Raw tokens belong to the agent provider and should not be resold by Lift.

Possible billable dimensions are:

- active workspace subscription;
- cloud compute time;
- persistent storage above an included amount;
- future premium capabilities such as multiple simultaneous workspaces or browser automation.
- retained session-history storage above an included allowance, if measured usage eventually requires it.

Do not charge per prompt, model token, file, merge, or Land operation.

## Initial package hypotheses

### Design-partner deposit

Ask for a `$20-$50` deposit immediately after the first successful full handoff. It may apply to the first paid month. The amount should be meaningful enough to test commitment but not optimized for revenue.

### Paid-beta option A: subscription plus usage

- `$29-$49` monthly continuity subscription;
- one persistent workspace and included storage;
- compute passed through with a visible markup or simple hourly rate;
- hard monthly spend cap chosen by the user.

This is economically safer while real usage is unknown.

### Paid-beta option B: simple included allowance

- `$49-$79` monthly;
- one persistent workspace;
- an included active-compute allowance sized from alpha data;
- clear overage price or automatic stop at the allowance;
- persistent storage retained while compute is stopped.

This may feel simpler after usage variance is understood.

### Avoid initially

- unlimited compute;
- annual contracts before retention is known;
- a free hosted tier that attracts low-intent infrastructure usage;
- multiple confusing machine-size choices;
- hiding compute overages behind credits.

## Cost model

Track cost per workspace and user from the first external alpha.

Define:

```text
monthly_runtime_cost = active_instance_hours * effective_instance_hour_rate
monthly_storage_cost = average_persistent_GB * effective_storage_GB_month_rate
monthly_snapshot_cost = retained_snapshot_GB * snapshot_GB_month_rate
monthly_transfer_cost = billable_egress_GB * egress_GB_rate
monthly_platform_cost = allocated control-plane + observability + secret-store cost
monthly_support_cost = support_hours * internal_support_hour_cost

workspace_COGS = runtime + storage + snapshots + transfer + platform allocation + support
gross_margin = (revenue - workspace_COGS) / revenue
```

Do not hardcode public cloud list prices into product decisions. Record the effective billed rates, region, discounts, and actual measured usage.

## Cost attribution events

For each workspace, record:

- runtime provider and region;
- machine shape;
- start and stop timestamps;
- active and idle-running hours;
- persistent volume average and peak size;
- snapshot count, size, and retention age;
- transfer in and out;
- recovery storage;
- retained session-ledger storage by workspace and session;
- control-plane jobs;
- support incidents and minutes;
- user-selected cap and cap-triggered stops.

Cost telemetry must not include source code, prompts, filenames, or secrets.

## Default compute policy

- stop compute after a visible idle threshold;
- preserve the encrypted workspace volume;
- warn before stopping when a provider session is active and the provider exposes that signal;
- snapshot before risky stop or infrastructure replacement;
- allow a user-selected monthly hard cap;
- make wake time and stopped-state behavior explicit;
- never delete durable state merely because a spend cap is reached.

The product should feel always available even when compute is not always billing.

## Margin targets

Use targets as decision heuristics:

- private alpha: learn the true cost; margin is secondary but must be measured;
- paid beta: positive contribution margin before founder labor;
- repeatable paid product: path to at least `60-70%` gross margin after routine support;
- any user with persistently negative contribution margin should trigger packaging, caps, or workload-shape review.

High support time can dominate EC2 cost. Track it as COGS even when the founder is providing it personally.

## Pricing experiments

Run sequentially rather than showing every user a different complex package.

1. After a successful handoff, ask for a deposit without offering a survey-only alternative.
2. Offer the subscription-plus-usage package to the first paid cohort.
3. Observe active hours, stopped hours, storage, support, and price objections for four weeks.
4. Test an included-allowance package against the measured distribution.
5. Raise or simplify pricing before expanding acquisition if support and compute erase contribution margin.

Capture the exact objection:

- total price too high;
- unpredictable usage;
- already pays the provider;
- not used frequently enough;
- does not trust hosted infrastructure;
- current workaround is good enough.

## Willingness-to-pay questions

Ask only after the participant completes the loop:

1. If Lift disappeared tomorrow, what would you do instead?
2. How often would you have used this in the last month?
3. What do you currently pay for the workaround?
4. Which part would you pay to avoid?
5. Will you put down `$X` now for continued access?

The final question produces the useful evidence.

## Billing experience requirements

Before paid beta, users must be able to:

- see the base price and usage policy before starting;
- see current active compute and estimated monthly usage;
- choose a hard cap;
- stop compute immediately;
- understand that storage remains billable while stopped, if applicable;
- download or Land work before cancellation;
- cancel without contacting support;
- delete the workspace and understand retention timing;
- obtain receipts and billing history;
- receive a clear failed-payment and grace-period explanation.

## Cancellation and retention

Cancellation must not strand source code.

Recommended flow:

1. offer Land to the known local folder;
2. offer an encrypted export or repository-safe archive;
3. stop compute;
4. state the recovery retention window;
5. allow immediate permanent deletion as a separate explicit action;
6. revoke provider and infrastructure credentials according to policy.

## Unit-economics review template

Review monthly:

| Measure | Actual | Target | Action |
| --- | ---: | ---: | --- |
| Revenue per paying user |  |  |  |
| Active compute hours |  |  |  |
| Idle-running hours |  |  |  |
| Storage GB-month |  |  |  |
| Infrastructure COGS |  |  |  |
| Support minutes |  |  |  |
| Total COGS |  |  |  |
| Contribution margin |  | Positive |  |
| Gross margin |  | Path to 60-70% |  |
| Paid 28-day retention |  |  |  |

Do not scale paid acquisition until repeat usage and contribution margin are both visible.
