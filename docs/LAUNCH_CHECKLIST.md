# Launch Readiness Checklist

Last updated: 2026-08-31

## How to use this checklist

Assign an owner and evidence link for every applicable item. `Done` means verified against the release candidate, not implemented once in development.

Public launch requires every hard no-go condition to be false. Private alpha may defer explicitly labeled scale items, but it may not defer work preservation, isolation, credential safety, deletion, or truthful product claims.

## Hard no-go conditions

Do not launch until every statement below has been verified and checked:

- [ ] The advertised provider's direct phone continuation is proven with the laptop fully off.
- [ ] Safe-to-close cannot appear without verified workspace durability and provider readiness.
- [ ] Clean Land cannot lose, overwrite, or misplace included workspace content under the tested envelope.
- [ ] A conflict cannot overwrite either local or cloud state.
- [ ] Final cloud revisions cannot be deleted before acknowledgement or recovery retention.
- [ ] Provider credentials cannot enter project files, logs, ordinary snapshots, or analytics through tested paths.
- [ ] Cross-user isolation tests prevent access to another user's runtime, storage, credentials, and metadata.
- [ ] Emergency stop, provider revoke, workspace export/Land, and deletion are available and tested.
- [ ] Provider terms and authentication constraints permit the advertised integration and claim.
- [ ] A staffed incident path exists for data loss and credential exposure.

## Product and experience

- [ ] Primary ICP and anti-ICP are documented and reflected in onboarding.
- [ ] One supported journey reads `Connect -> Lift Off -> safe to close -> provider app -> Land`.
- [ ] Normal setup requires no terminal, SSH, cloud console, copied token, or provider command.
- [ ] Unsupported operating systems, providers, repository layouts, and file types are detected early.
- [ ] Transfer review explains included, excluded, sensitive, ignored, and reconstructed state.
- [ ] Progress uses plain language and provides actionable recovery.
- [ ] Stop, wake, Land, revoke, export, and delete are findable.
- [ ] Product does not contain a redundant Lift agent chat or mobile IDE.
- [ ] Accessibility, keyboard navigation, focus states, errors, and loading states have been tested.
- [ ] First-run and returning-user journeys have been tested separately.
- [ ] Canonical demo works from a clean account against production.

## Provider connection

- [ ] Supported provider and account eligibility are explicit.
- [ ] Authentication occurs through an official provider-owned flow.
- [ ] Lift never collects the provider password.
- [ ] Reusable credentials are encrypted and isolated from project content.
- [ ] Native remote startup is supervised and restartable.
- [ ] Readiness distinguishes process health from provider registration.
- [ ] Reauthentication, revoke, disconnect, and account switch are tested.
- [ ] Laptop-off continuation, network interruption, provider process restart, and VM restart are tested.
- [ ] Version compatibility and known limitations are published.
- [ ] Fallbacks are labeled accurately and do not imply laptop independence.

## Local helper

- [ ] Installer identity, signing, distribution, and update mechanism are ready.
- [ ] Helper permissions are minimal and explained.
- [ ] Folder selection cannot escape the approved workspace.
- [ ] Helper does not mutate the project during inspection.
- [ ] Helper restart and OS restart recover desired state.
- [ ] Offline, captive-network, proxy, and interrupted-transfer behavior are tested.
- [ ] Update rollback and compatibility policy exist.
- [ ] Uninstall preserves or safely Lands active workspaces and removes local secrets as documented.

## Workspace state and Land

- [ ] Manifest schema is versioned and signed or otherwise authenticated.
- [ ] Tracked, staged, unstaged, untracked, and approved ignored content are tested.
- [ ] Exclusions prevent unrelated home-directory and secret transfer.
- [ ] Lift-private Git capture does not move user branches, refs, or real index.
- [ ] Cloud checkpoints include dirty final state.
- [ ] Ownership state machine is durable and idempotent.
- [ ] Clean three-way merge and transactional apply are verified.
- [ ] Same-file, delete-modify, type, binary, symlink, and case-collision conflicts preserve both sides.
- [ ] Crash during application recovers through the journal.
- [ ] Land requested while the laptop is offline completes when it reconnects.
- [ ] Missing or moved local folder requires explicit destination selection.
- [ ] No Lift ref or ignored content is pushed to GitHub automatically.
- [ ] Baseline, checkpoint chain, clean or conflicted merge result, and Land receipt remain restorable after local acknowledgement.
- [ ] Session-ledger deletion requires an authenticated explicit user action and is tested end to end.
- [ ] Recovery retention and cleanup jobs are tested.

## Runtime and infrastructure

- [ ] Create, start, stop, snapshot, restore, status, and delete are idempotent.
- [ ] Workspace uses a dedicated isolation boundary appropriate for alpha.
- [ ] Persistent volume and snapshots are encrypted.
- [ ] Cloud metadata and control-plane networks are inaccessible from workspace code.
- [ ] No unauthenticated provider daemon or workspace port is public.
- [ ] Administrative access uses individual least-privilege identities and audit logs.
- [ ] Base image, bootstrap, and recipe versions are reproducible.
- [ ] Idle stop and monthly hard caps are tested.
- [ ] Duplicate or failed provisioning does not create unbounded cost.
- [ ] Region outage and unrecoverable-instance procedures are documented.
- [ ] Backup restore has been performed, not merely configured.

## Security and privacy

- [ ] Threat model in `SECURITY.md` has been reviewed against the release candidate.
- [ ] Cross-user isolation test passes.
- [ ] Secret scanning covers logs, manifests, snapshots, analytics, and support output.
- [ ] Provider, cloud, and control-plane credentials are scoped and rotatable.
- [ ] Emergency account lock and stop-all-workspaces controls are tested.
- [ ] Operator access is least privilege, time-bounded where possible, and audited.
- [ ] Dependency and image vulnerability review is current.
- [ ] Abuse, runaway process, egress, and resource-limit controls exist.
- [ ] Security contact and incident process are published.
- [ ] Privacy notice accurately describes collected data, purpose, subprocessors, retention, and user controls.
- [ ] Terms accurately describe beta limitations, user responsibility, acceptable use, and service availability.
- [ ] Account deletion, workspace deletion, provider revocation, and backup expiration are tested end to end.
- [ ] Any required legal or privacy counsel review is complete.

## Reliability and observability

- [ ] Every lifecycle operation has an attempt ID, desired state, retry count, and safe error class.
- [ ] Alerts cover provisioning, provider readiness, final checkpoint, Land acknowledgement, deletion, and cost anomalies.
- [ ] Product state and operational state derive from the same source of truth.
- [ ] Logs are redacted and have access and retention policies.
- [ ] Dashboards show workspaces stuck in Lifting, Landing, stopping, or deletion.
- [ ] Synthetic full-loop test runs on the release candidate.
- [ ] Recovery runbooks in `OPERATIONS.md` have been exercised.
- [ ] Status communication path is ready for provider or runtime outages.

## Analytics and learning

- [ ] North-star and activation definitions match `ANALYTICS.md`.
- [ ] Critical events fire once with correct idempotency and safe properties.
- [ ] No code, paths, prompts, diffs, credentials, or transcripts enter analytics.
- [ ] Connection, Lift Off, magic-moment, Land, retention, and paid funnels are visible.
- [ ] Acquisition source persists through activation.
- [ ] Manual assistance and support minutes are recorded.
- [ ] User feedback prompts are ready after safe-to-close and Land.
- [ ] Experiment and evidence log owner is assigned.

## Billing and economics

- [ ] Price and included usage are understandable before purchase.
- [ ] Compute, storage, cap, stopped-state, and overage behavior are explicit.
- [ ] Usage attribution is accurate by workspace.
- [ ] User can set a hard cap and stop compute immediately.
- [ ] Failed payment does not destroy or strand work.
- [ ] Cancellation, Land/export, recovery retention, refund, and deletion flows are ready.
- [ ] Receipts, taxes, and required business information are configured.
- [ ] Infrastructure and support COGS are measured.
- [ ] Paid-beta package has a path to positive contribution margin.

## Support and operations

- [ ] Supported envelope and known limitations are published.
- [ ] Support hours, contact, and severity definitions are visible.
- [ ] On-call owner for launch traffic is assigned.
- [ ] Severity-one stop, preserve, revoke, notify, and investigate flow has been rehearsed.
- [ ] Support can identify ownership state and durable revisions without requesting source code.
- [ ] User-facing recovery messages and internal runbooks agree.
- [ ] Refund or credit policy for Lift-caused compute cost exists.
- [ ] Provider and runtime compatibility owners are assigned.

## Go-to-market assets

- [ ] Landing page reflects the current supported claim.
- [ ] Compatibility matrix is accurate.
- [ ] Continuous canonical demo is recorded against the release candidate.
- [ ] Screenshots and copy do not expose user content or secrets.
- [ ] Waitlist form qualifies the ICP.
- [ ] Founder outreach list is behavior-based, not generic developer leads.
- [ ] Design-partner results have explicit permission before publication.
- [ ] Objection responses and comparison copy are accurate.
- [ ] Pricing page, privacy notice, terms, support, and status links are live.
- [ ] Product name, domain, package names, and material trademark risk have been checked.

## Private-alpha launch day

- [ ] Admit users in a small wave with a named owner for each session.
- [ ] Verify runtime capacity and cost caps.
- [ ] Watch every first Lift Off and Land with consent.
- [ ] Ask for a deposit only after successful outcome.
- [ ] Review all manual interventions the same day.
- [ ] Stop expansion immediately on any hard no-go incident.

## Public launch day

- [ ] Freeze nonessential releases.
- [ ] Verify production, billing, support, analytics, and status surfaces.
- [ ] Run the full canonical loop immediately before announcement.
- [ ] Publish the demo, narrow promise, compatibility, pricing, and limitations together.
- [ ] Staff support and infrastructure monitoring.
- [ ] Track qualified activation and successful Land, not traffic alone.
- [ ] Maintain a public incident update when material functionality is impaired.

## First 72 hours after launch

- [ ] Review every failed provider connection, Lift Off, safe-to-close, and Land.
- [ ] Contact high-fit users who abandon before activation.
- [ ] Inspect compute leakage and cap behavior.
- [ ] Verify no cloud revision is stranded or prematurely cleaned.
- [ ] Review analytics privacy and event volume.
- [ ] Publish known issues quickly.
- [ ] Fix trust and full-loop blockers before growth optimizations.
- [ ] Decide whether to continue, throttle invites, or pause using the documented gates.

## Signoff

| Area | Owner | Evidence | Status |
| --- | --- | --- | --- |
| Product |  |  |  |
| Provider connection |  |  |  |
| State continuity |  |  |  |
| Runtime |  |  |  |
| Security/privacy |  |  |  |
| Reliability |  |  |  |
| Billing/economics |  |  |  |
| Analytics |  |  |  |
| Support/operations |  |  |  |
| GTM |  |  |  |

The launch decision is documented in [`DECISIONS.md`](DECISIONS.md) with any accepted limitations and their owners.
