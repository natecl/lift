# Alpha Operations and Support

Last updated: 2026-08-31

## Operating principle

During alpha, Lift is a high-trust infrastructure product. Fast growth is less important than knowing where every workspace revision is, which process can write it, and how a user gets their work back.

## Supported alpha envelope

Publish and enforce a compatibility envelope:

- macOS local helper versions;
- Git versions and supported repository layouts;
- Ubuntu runtime image version;
- supported architecture;
- provider, CLI, desktop, and phone application versions;
- supported authentication mode;
- maximum repository and individual-file size;
- behavior for Git LFS, submodules, nested repositories, symbolic links, and ignored files;
- supported AWS region and runtime shape;
- known limitations and required fallbacks.

Unsupported does not mean “probably works.” It means Lift detects the condition before upload and explains the next step.

## Design-partner onboarding

### Before the session

- confirm the user matches the ICP;
- choose a real noncritical repository;
- confirm a supported provider account and phone application;
- explain that direct Codex phone continuation remains gated until the headless path is proven;
- identify sensitive files and expected exclusions;
- set a conservative compute cap;
- establish the support channel and emergency stop path;
- ensure the user knows how to access the original local folder.

### During the session

1. connect the provider through its owned flow;
2. select and inspect the repository;
3. review transfer boundaries in plain language;
4. click Lift Off;
5. verify safe-to-close evidence;
6. require the laptop to close;
7. complete one useful provider-native change;
8. choose Land;
9. verify the local result and original Git state;
10. show stop, revoke, export, and delete controls;
11. request payment or a deposit after success.

### After the session

- send the exact compatibility and support summary;
- record every manual intervention;
- schedule the 24-hour and seven-day follow-ups;
- verify unexpected compute has stopped;
- classify product feedback by hypothesis, not feature request count.

## User-visible workspace states

Support and product should use the same vocabulary:

```text
On this Mac
Preparing to Lift
Lifted - working in the cloud
Needs connection
Safe to close
Bringing changes back
Back on this Mac
Needs review - both copies were edited
Stopped - files preserved
Deletion scheduled
```

Never tell a user a workspace is “fine” without identifying the current ownership state, durable revision, provider connection state, and compute state.

## Support intake

Collect:

- user and opaque workspace ID;
- helper, runtime image, provider, and recipe versions;
- current desired and observed state;
- last acknowledged local and cloud revision IDs;
- safe error class and attempt ID;
- whether the user has made new local edits;
- whether the provider process is still writing;
- whether credentials, sensitive data, or production systems may be involved.

Do not request source archives, full logs, terminal histories, screenshots containing secrets, or provider tokens as the first diagnostic step.

## Severity model

### Severity 1: stop and contain

Examples:

- suspected data loss or silent overwrite;
- cross-user workspace access;
- provider or infrastructure credential exposure;
- false safe-to-close confirmation that strands active work;
- unauthorized remote branch push or external action;
- unrecoverable deletion;
- active compromise.

Response:

1. stop affected workspace writers and prevent destructive cleanup;
2. preserve manifests, journals, audit events, and encrypted recovery revisions;
3. revoke exposed grants where safe;
4. notify the affected user promptly with known facts and a safe next action;
5. block the affected release or capability;
6. investigate with least-privilege access;
7. document impact, timeline, root cause, recovery, and prevention before re-enabling.

### Severity 2: major workflow failure

Examples:

- workspace cannot wake;
- provider connection cannot recover;
- Lift Off repeatedly fails after state is safely captured;
- Land is waiting despite an available helper;
- compute continues beyond the user's stop request;
- repeated conflict false positives.

Respond during the active support window, protect state first, offer a verified export or recovery path, and prevent additional charges caused by the fault.

### Severity 3: degraded or confusing behavior

Examples:

- slow cold start;
- unclear error copy;
- optional metadata or analytics missing;
- unsupported repository detected late;
- nonblocking dashboard inconsistency.

Record, prioritize by impact on the full loop, and do not disguise it as success.

## Common recovery playbooks

### Provider needs reauthentication

- keep the workspace and final revision durable;
- stop claiming remote readiness;
- show `Reconnect <provider>`;
- open only the provider-owned auth flow;
- never ask for a copied cookie or token;
- resume the same desired state after connection health is verified.

### Runtime will not start

- do not create a second authoritative workspace;
- inspect provider lifecycle state and last durable volume attachment;
- retry idempotently;
- attach a recovery clone only through an explicit restore operation;
- keep the user informed in product language;
- stop billing failed duplicate resources.

### Local helper is offline during Land

- complete the final cloud checkpoint;
- stop compute if requested;
- keep the workspace in `LANDING`;
- notify the user that files are safe and waiting for the Mac;
- apply automatically only after the original folder and local precondition are verified.

### Local workspace diverged

- do not touch overlapping paths;
- preserve local, cloud, and proposed merge revisions;
- show the PR-like file and conflict summary;
- offer the isolated worktree or sibling recovery folder;
- keep cloud revision cleanup paused until explicit resolution.

### Local application interrupted

- read the durable operation journal;
- verify current hashes;
- complete or restore deterministically;
- never rerun the whole delta blindly;
- acknowledge cloud only after final verification.

### Cost cap reached

- checkpoint state;
- stop compute;
- preserve storage according to the user's plan;
- explain the exact effect on provider sessions;
- never delete the workspace or block export because a cap was reached.

## Release management

- pin helper, runtime image, recipe, and provider CLI versions per session;
- test a compatibility matrix before promotion;
- roll out to founder, then one design partner, then a small percentage of alpha users;
- preserve the prior runtime image and recipe for rollback;
- never auto-upgrade a running session across a known incompatible provider change;
- record migrations of credential paths, manifest schema, private Git state, and volume format;
- require recovery tests before any state-format migration.

## Backups and restoration

- keep versioned cloud manifests and required content objects;
- snapshot the persistent volume before risky lifecycle changes;
- retain the final Land revision until local acknowledgement and retain the sealed session ledger afterward until explicit user deletion;
- test restoration into a separate isolated runtime;
- verify restored content by manifest, not by successful mount alone;
- document recovery retention separately from deletion retention;
- ensure backups containing private Git objects inherit the same sensitivity and encryption rules.

## Access and audit

- operators use individual identities and least privilege;
- production workspace access is exceptional, time-bounded, and logged;
- support tooling displays metadata before any content access;
- user consent is required for content-level investigation unless immediate security containment legally permits otherwise;
- control-plane, secret, runtime, and recovery access events are retained according to policy;
- no shared root credentials or permanent personal cloud keys.

## Data lifecycle

Document for every class:

| Data class | Location | Encryption | Retention | User control |
| --- | --- | --- | --- | --- |
| Account metadata | Control plane | Required | Account lifetime plus stated retention | Export/delete where applicable |
| Workspace manifests | Control plane/recovery store | Required | Retained per session until explicit deletion | View/export/delete |
| Workspace content | Encrypted volume/object store | Required | Active state plus retained session checkpoints until explicit deletion | Land/export/delete |
| Private Git objects and Land receipts | Encrypted Lift state | Required | Retained per session until explicit deletion | Restore/export/delete |
| Provider credentials | Dedicated vault/approved state | Required | Until revoke/disconnect | Disconnect/revoke |
| Operational logs | Restricted logging system | Required | Minimal documented period | Policy-dependent |
| Product analytics | Analytics system | Required | Minimal documented period | Account privacy controls |

Do not state a retention number publicly until the implementation and deletion job enforce it.

## Alpha support expectations

- publish support hours and an emergency security contact;
- identify who can stop all workspaces;
- acknowledge severity-one reports immediately during staffed periods;
- do not promise 24/7 coverage before it exists;
- provide status updates even when there is no resolution yet;
- refund or credit user-caused charges from a confirmed Lift fault;
- close every serious incident with a user-readable explanation.

## Weekly operations review

Review:

- workspaces by ownership and lifecycle state;
- cloud revisions waiting for local acknowledgement;
- failed and retried operations;
- provider reauthentication and compatibility failures;
- idle-running and cap-triggered compute;
- support volume and minutes per activated user;
- backup and restoration test results;
- security events and operator access;
- upcoming provider, helper, or runtime changes;
- documentation gaps revealed by support.

Operations exists to protect the product promise, not to normalize manual repair.
