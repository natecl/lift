# Codex Headless Remote Feasibility Spike

Date: 2026-08-31
Last updated: 2026-09-02

Status: single-run founder feasibility pass, not launch-ready. Direct ChatGPT phone control works against both the local Ubuntu precursor and a real Ubuntu EC2 workspace on encrypted EBS. The founder's laptop-off run is strongly corroborated by a fresh challenge/proof exchange and Mac reboot timestamps, but it is not cryptographic device attestation. One EC2 stop/start recovered the exact workspace, earlier checkpoints and proof files, the provider-neutral runner, and the same Codex Remote environment. After server-side native-project reconstruction, a brand-new phone task bound to the exact EBS folder, completed a live observed approval-and-proof turn, and produced checkpoint `0003`, which passed exact-version S3 restore verification. Fresh live evaluation reported every safe-to-close gate true. On 2026-09-02 separate generated disposable fixtures completed clean and deliberate same-file conflict Land runs across real EC2/EBS/S3 and the Mac. The clean path restored, imported, applied, acknowledged, returned the lease, and stopped compute. The conflict path preserved exact `B/L/C` and untouched local state, stopped at `NEEDS_REVIEW`/`LANDING`, retained the writer fence and compute, and repeated idempotently. Network recovery, revocation, automatic offline-helper wake, conflict-resolution UX, arbitrary real-workspace capture, customer UI/helper, repeated users and runs, provider-service isolation, and production-support policy remain pending.

For the cross-functional current snapshot and next slice, see [`../CURRENT_STATE.md`](../CURRENT_STATE.md). This document remains the detailed experiment record.

The local-to-cloud capture in this harness is deliberately fixture-only: it rejects any workspace without the exact generated disposable marker before creating its private ledger. A production manifest-review and explicit untracked/ignored-file selection flow is not implemented by this spike.

The disposable bootstrap also downloads the official AWS CLI archive and Codex installer without pinning the installer bytes to reviewed signatures or digests. Resulting versions and runtime files are checked, but alpha reuse requires a signed/content-addressed image or cryptographic verification before root execution.

## Question

Can an unmodified Codex installation run on persistent headless Ubuntu, connect outbound to OpenAI Remote, pair with the user's existing ChatGPT phone experience, and keep working without an awake Mac or Windows relay?

This is the first technical gate for Lift's Codex-first laptop-off promise. Process health alone does not answer it; the spike passes only after a real task travels from the phone to the Ubuntu workspace and reconnects after process and VM restarts.

## Documented support boundary

OpenAI's published Remote documentation currently describes the phone controlling a connected computer. The published remote-connections setup begins in the ChatGPT desktop application on an awake Mac or Windows computer, and an SSH project still routes through that desktop host. It does not document direct CLI-to-phone pairing as a supported production integration.

The current Linux CLI exposes a separate remote-control daemon and manual pairing command. Those commands are usable experimental evidence, not a stable third-party contract.

Official references:

- [Codex Remote](https://learn.chatgpt.com/docs/remote)
- [Codex remote connections](https://learn.chatgpt.com/docs/remote-connections)
- [Codex developer commands](https://learn.chatgpt.com/docs/developer-commands)
- [Codex App Server protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)

These references currently disagree at the product boundary. The stable Remote guide describes setup through an awake macOS or Windows desktop host, while the developer-command reference and App Server protocol expose experimental `remote-control` pairing primitives. Treat the CLI surface as experimental until OpenAI documents the client topology and platform support consistently.

## Precursor environment

The first pass uses a disposable local Linux container so provider feasibility can be tested before incurring EC2 cost.

| Property | Value |
| --- | --- |
| Host | Docker Desktop on macOS |
| Guest | Ubuntu 24.04, `linux/amd64` |
| Container | Disposable single-user precursor |
| Seed workspace | `/workspace`, initialized as a tiny Git repository |
| Provider-visible workspace | Real Git clone at `/home/lift/Workspace` on the persistent home volume |
| Persistent provider home | Named Docker volume mounted at `/home/lift` |
| Installation | Official `https://chatgpt.com/codex/install.sh` installer |
| Codex CLI | `0.151.0` for fresh auth and first pairing; `0.152.0` after daemon restart, x86_64 Linux |
| Authentication | User-approved OpenAI device authorization; no credential files copied from the Mac |

The container is not evidence for EC2/EBS lifecycle behavior. It isolates the narrower provider question and gives the exact EC2 runbook a known-good starting point.

## Observed results

### 1. Fresh Linux authentication — pass

`codex login --device-auth` completed successfully through the provider-owned authorization page. `codex login status` reports ChatGPT authentication.

No OpenAI password was entered into Lift, and no existing local Codex credential file was transferred. Reusable provider state is held in the isolated Linux home volume for the duration of the spike.

### 2. Headless daemon bootstrap — pass

`codex remote-control start --json` returned:

- daemon mode;
- connected status;
- PID-backed bootstrap;
- remote control enabled;
- CLI and App Server version `0.151.0`;
- a Unix control socket beneath `/home/lift/.codex`.

After the initiating shell exited, two managed Codex processes remained alive: the remote-control App Server and its PID update loop. The App Server command listens on a Unix socket and does not require an inbound public workspace listener.

### 3. Manual phone pairing artifact — pass at CLI boundary

`codex remote-control pair --json` generated both a short-lived manual code and a provider environment identifier. The transient code is deliberately excluded from this repository and from durable logs.

This proves the current CLI exposes a nonterminal pairing artifact that a Lift Connections flow could present. It does not prove the ChatGPT phone client accepts it or that OpenAI supports third-party automation around it. The App Server protocol labels the related pairing methods experimental.

### 4. Current iPhone controller pairing — pass through provider-owned URL

The live test used the user's unlocked iPhone 16 Pro through iPhone Mirroring. The ChatGPT Remote screen showed only the already paired Mac host, `Nathans-MacBook-Pro.local`. It did not show the connected Linux server name or environment.

The tested mobile UI was inspected through both relevant surfaces:

- Remote's host label and overflow menu exposed no Add Connection or manual-code action; the overflow menu contained organization controls only.
- The complete ChatGPT settings list exposed Personalization/Memory, Account/Subscription/Usage, Theme, General, Notifications, Voice, and Parental controls. It contained no Remote Control or Connections row on this account/build.

Multiple early short-lived Linux pairing codes expired unclaimed. This confirmed that the Linux App Server's `connected` status only describes its outbound relay; it does not prove a controller device has claimed it.

Inspection of the installed official desktop app bundle found that its QR component maps the opaque CLI `pairingCode` to:

`https://chatgpt.com/codex/pair?pairing_code=<short-lived-provider-payload>`

The payload is not a manual PIN and is deliberately not stored in this repository. Opening a fresh provider-owned URL on the same iPhone succeeded. The ChatGPT client displayed a second Remote connection for server `d2705d3c3337`; the Linux relay reported the environment claimed with one controller client.

The mobile app required its provider-owned local unlock/authentication gate before exposing the Remote environment. Lift did not receive the user's OpenAI password, pairing payload, or reusable provider token. The short-lived pairing artifact was removed after use.

The missing visible Add Connection UI is therefore a discovery/onboarding limitation, not a protocol failure. A Lift Connections experience can present the provider-owned pairing URL without reimplementing the provider protocol, but this remains an experimental surface. Current OpenAI repository reports show both successful community experiments and active failures around the same commands, including the documentation mismatch tracked in [openai/codex#35928](https://github.com/openai/codex/issues/35928).

### 5. Real phone-issued task and Git return — pass in the local precursor

The first phone task exposed an important workspace-selection failure. The mobile composer defaulted to `Chat`, which created an empty projectless directory beneath `/home/lift/Documents/Codex/...`. The agent correctly reported that `REMOTE_TEST.md` was absent and changed nothing.

The Remote folder picker could browse `/home/lift`, but it refused to follow a `/home/lift/Workspace -> /workspace` symbolic link. Replacing the symlink with a real Git clone at `/home/lift/Workspace` made the directory selectable. The product implication is concrete: the provider-visible working copy must physically live beneath the persistent remote user's supported workspace root. A convenience symlink to a workspace mounted elsewhere is not sufficient.

With `Workspace` selected, the iPhone issued:

`Replace the line in REMOTE_TEST.md with: Status: changed from the paired iPhone. Do not modify any other file.`

The resulting thread recorded `cwd=/home/lift/Workspace` and originator `codex_chatgpt_ios_remote`. The provider client requested one-time approval for repository inspection, the one-line edit, and final verification. The test chose `Approve`, never `Always approve`.

The agent changed exactly one tracked file:

```diff
-Status: waiting for a phone-issued Codex task.
+Status: changed from the paired iPhone.
```

The phone thread completed with: `Updated REMOTE_TEST.md as requested. No other files were modified.` Git diff and status independently confirmed the same scope.

The cloud working copy was checkpointed as commit `dd27755` (`Record paired iPhone workspace edit`). The clean return path fetched that commit into the disposable original `/workspace` repository and fast-forwarded it from `7f14712` to `dd27755`. Both repositories ended clean with identical history and file content. This validates the smallest Git-backed session-history and clean-Land mechanism; it is not yet a test of dirty local state or conflicts.

### 6. Reconnection and persistence — partial pass

The provider login and installation survived the initiating shell exit because `/home/lift` was persistent. The App Server process was stopped and relaunched, upgrading the active CLI/App Server from `0.151.0` to `0.152.0`; the same persistent provider home could reconnect and complete the successful phone task. The test did require reopening a fresh provider pairing URL and passing the provider-owned Remote unlock gate, so transparent controller reattachment is not yet proven.

At the end of the local precursor, the remaining tests were:

1. interrupt and restore network access;
2. restart the Linux guest while preserving the provider home and workspace volumes;
3. repeat on Ubuntu EC2 with workspace and approved provider state on encrypted EBS;
4. stop and start EC2, restart the recipe semantically, and issue another phone task;
5. repeat without iPhone Mirroring or any awake desktop to prove the literal laptop-off claim;
6. revoke the mobile connection and confirm the server can no longer be controlled.

The Docker precursor also exposed a sandbox prerequisite. Bundled `bubblewrap` could not create an unprivileged user namespace, so read, edit, and verification commands retried through provider-owned escalation prompts. The production Ubuntu image must preflight Codex's sandbox prerequisites and kernel user-namespace support; otherwise a trivial edit produces avoidable approvals and weaker isolation.

The product may promise filesystem and session continuity only for the state it can durably reconstruct. It must not promise suspended RAM or invisible provider behavior.

### 7. Real Ubuntu EC2 and direct phone control — pass at transport and workspace boundary

On 2026-09-01, the experimental path was repeated on a real x86_64 Ubuntu EC2 instance. The provider-visible working copy was a real directory beneath `/home/lift/workspaces` on a separate encrypted EBS workspace volume. The Codex Remote environment reported the exact intended cloud `cwd`, and ChatGPT on the founder's phone controlled that environment directly rather than routing through ChatGPT Desktop as an SSH relay.

This passes the narrower question of whether the current Codex Remote surface can carry a real phone task to the intended EC2 workspace. It does not establish provider support, repeatability, or end-to-end native phone recovery after a lifecycle event.

### 8. Laptop-off challenge — strongly corroborated founder evidence, not attestation

Immediately before the shutdown attempt, Lift armed a fresh unpredictable nonce tied to the provider environment, exact expected cloud `cwd`, and one proof path. The founder then reported shutting down the Mac completely, opened the already paired environment on the phone, and caused the exact challenge object to be written into the EBS-backed workspace. The observed file matched the required nonce, source, path, ownership, type, and content after the challenge issue time. Later Mac boot timestamps post-dated the challenge and proof sequence.

This combination strongly corroborates that the phone continued the EC2 workspace while the Mac was off. It is still a human-attested founder test: Lift did not have a hardware-rooted power-state signal, an independent observer, or cryptographic device attestation. Record it as meaningful Phase 0 evidence, not as a public `Verified` compatibility claim.

### 9. Immutable cloud checkpoints and exact restore — pass for four revisions

The run created four immutable Lift-private Git checkpoints: `0001` before the shutdown proof, `0002` after it, `0003-post-restart-phone-proof` after the successful post-restart phone and approval evidence, and `0004-land-final` as the single final cloud state for Land. The checkpoint process used Lift-private refs and indexes rather than moving the user's branch, refs, or index.

For all four revisions, Lift produced a Git bundle and manifest, computed checksums, and stored them as versioned private S3 objects. The verifier downloaded each exact object version into a clean location, checked the object checksums, restored the bundle into a fresh bare repository, and verified the expected commit, tree, retained history refs, and required evidence. Checkpoint `0003` is commit `674bd2722b961caf1e91db98f582330b6b4a54b5` with restored tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`. The final `0004-land-final` bundle and manifest were additionally imported through the Mac's private quarantine and used as exact `C` for the applied reconciliation. This proves recoverability of those captured revisions independently of the live working directory.

The subsequent stop/start test below proves structural recovery of the same EC2 workspace and Codex Remote environment for one run. It does not by itself prove native phone access after restart, the local Land transaction, or conflict behavior.

### 10. EC2 stop/start and end-to-end phone recovery — single-run pass

The EC2 instance was stopped and started rather than merely rebooted in place. The guest boot ID changed, demonstrating a new guest boot. After the instance returned through Systems Manager:

- the exact encrypted workspace EBS volume was reattached and mounted at the expected workspace path;
- checkpoint `0002`'s expected commit and bundle were present and verified;
- both the original phone proof and the laptop-off proof were recovered with the workspace;
- the provider-neutral systemd workload runner automatically started and reported healthy; and
- Codex Remote reported the exact same provider environment ID used before the stop.

This first passed structural EC2 stop/start recovery: durable state, checkpoint identity, generic supervision, and provider environment identity all survived while the guest process state was reconstructed. On 2026-09-02, the following fresh phone task then passed against the preserved environment and exact EBS folder, and its evidence entered restore-tested checkpoint `0003`. That closes the single-run end-to-end recovery question without establishing repeatability or official provider support.

### 11. Native project reconstruction and semantic readiness — single-run end-to-end pass

The first post-restart mobile attempts failed even though systemd and Codex Remote appeared healthy. A new task reported a workspace error. Older tasks repeatedly requested write approval outside the workspace, but no actionable approval control appeared. Inspection found that Codex had retained the Remote environment while its native project registry contained zero projects and zero project roots. Mobile consequently opened synthetic directories beneath `/home/lift/Documents/Codex/...`, which are intentionally read-only under Lift's service sandbox.

Lift now treats that state as not ready. The generic runner gained recipe-declared `prepare` and `readiness` process specifications. The currently pinned Codex `0.152.1` connector validates the experimental App Server schema and connects to the live provider-owned control socket. Its idempotent `prepare` command creates or reads the server-side native project named `lift`, binds it to `/home/lift/workspaces/lift-ec2-spike`, and configures trust for only that exact path without requiring transient Remote or controller presence. Its separate `readiness` command reads that project back and requires Remote to be connected with at least one paired controller. Because that API does not expose the controller's saved-folder picker, the connector now reports `serverProjectRegistered: true` while keeping `controllerProjectVisibility` explicitly `unknown` and unverified. The connector stores only a nonsecret workspace-binding and create-idempotency record at `/home/lift/.codex/lift/lift-ec2-spike/codex-project.json`, outside the workspace, and never mutates Codex's SQLite database.

Read-only verification at `2026-09-01T19:28:58Z` observed:

- systemd workload active with `healthy: true` and semantic `ready: true`;
- Codex CLI, managed binary, and App Server all pinned at `0.152.1`;
- Remote status `connected` with environment `env_e_6a96f94562d083289769bba32f8614d7` and one registered controller;
- native project `01a05e65-3e1a-7e81-bc34-9bbc868b6155` present and read back through App Server;
- exact project root and service working directory `/home/lift/workspaces/lift-ec2-spike` matching the EBS-backed workspace;
- exact workspace, Codex state, and Codex cache paths writable while projectless home paths remain read-only; and
- no direct mutation of Codex's state database.

Existing projectless mobile tasks are not repaired by assigning a project ID because their stored working directories and sandbox histories remain wrong. The tested recovery used the already saved exact folder connection and a brand-new post-baseline mobile task. App Server list/read/resume showed the exact canonical `cwd`, `projectId: null`, and exact runtime roots, so this is a verified folder binding rather than evidence that the separately registered server project became visible in the mobile picker. The controlled approval canary and proof command both completed in that task, the live and historical verifiers agreed, the following checkpoint restored successfully, and fresh runner/Remote evaluation reported `safeToClose: true`. Controller-side project visibility remains explicitly unknown, and separate provider-service identity and credential isolation remain pre-alpha security gates.

### Approval-event observer — deployed and live-proven once

Codex 0.152 lets a subscribed second App Server client see stronger evidence than completed thread history alone. It receives the same `item/commandExecution/requestApproval` request and request ID as the provider client; `thread/resume` can replay a still-pending request. It later receives `serverRequest/resolved`, `item/completed`, and `turn/completed`.

Lift now implements that second client as a passive observer. The controller starts one challenge-specific, root-owned transient systemd service from checksum-verified root-owned runtime files, with a private network namespace restricted to Unix sockets, read-only home access, and only a root-owned observation directory writable. The observer connects directly to the local Unix-domain App Server socket and never answers a server request. After initialization it first proves that no fresh post-baseline task exists, then atomically writes a root-owned mode-`0600` readiness record. Only after the controller validates that exact ready record may it show the phone prompt.

The observer does not stop when the canary completes. It stays through the complete two-command turn and requires the exact approval request, matching resolution, successful canary item, subsequent successful proof item, and successful `turn/completed`, with no extra command, tool, or mutation item. Its normalized evidence binds the challenge and guard hashes, thread baseline, environment, native project, `cwd`, request, thread, turn, both item identities, both command hashes, and event times. The controller accepts it only from a successfully exited observer unit and root-owned private evidence file. Raw commands, pairing data, and provider secrets are not persisted in the observer record.

This live path complements rather than replaces the historical verifier. The latter independently re-reads the completed task and enforces one new post-baseline task, one turn, exact command order and digests, exact `on-request`/`user` policy, network-disabled sandbox, agent provenance, null plugin/script provenance, and absence of plugin, MCP, or other unreviewed items. The controller separately proves no effective hook can run and binds the bounded complete `plugin/list` response before and after the attempt. Installed plugins may therefore remain enabled without being executed in the proof turn. The controller requires the live observation and historical result to agree before approval evidence can enter the checkpoint and safe-to-close chain.

The public protocol does **not** mirror the phone's response payload or retain the responder connection identity. The first client response resolves the shared request, and the passive observer sees only that it resolved. `availableDecisions` is a presentation hint rather than a server-enforced allowlist, so the observer cannot directly prove the selected enum either. Therefore the combined evidence proves `request observed -> request resolved -> exact command succeeded` with the trusted official founder-controlled client, not “this exact phone user tapped Approve.” This remains an explicitly guarded founder-spike inference. It also does not prove a plugin-free model context: installed skill metadata can influence a new task without a tool call, and public documentation does not guarantee that `plugin/list` binds immutable remote bundle content. A high-assurance path needs a decision-bearing provider audit event or trusted transport boundary, plus isolated plugin-disabled execution or content-addressed pinned bundles.

Observer schema v8 was deployed from immutable runtime bundle `4fa78e5437aff008e099bbd4c3be95720f19abb7c38f36ae7f0e8a007382bb0c` and exercised by the successful phone task. It validated the source-authentic `execpolicy_amendment` decision schema, request execution environment `local`, event ordering, matching resolution, both successful command lifecycles, and successful turn completion. The independent historical verifier agreed before checkpoint `0003` was allowed. Production-grade attribution still requires a provider audit event or another supported mechanism, and external alpha requires separating the provider daemon and credentials from the untrusted workload because both currently share the `lift` Unix identity. Undocumented trace logs and mutable local databases are not acceptable evidence. See the official [plugins](https://learn.chatgpt.com/docs/plugins), [skills](https://learn.chatgpt.com/docs/build-skills), [hooks](https://learn.chatgpt.com/docs/hooks), and [plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management) documentation.

### 12. Mobile folder task semantics — deployed and live-verified

The fresh task created from the phone after selecting `/home/lift/workspaces/lift-ec2-spike` had the exact intended `cwd` and `projectId: null`. Its one completed turn contained the two challenge commands in order; each completed command used source `unifiedExecStartup`, null plugin/script provenance, exit code zero, and a stored command that decoded exactly to `/bin/bash -lc INNER`, where `INNER` matched the independently reconstructed challenge command byte-for-byte. The active rules directories were empty after the founder selected one-time approval.

This is provider-authentic folder binding, not evidence that the separately registered App Server project became visible or assigned to the mobile task. The deployed compatibility path keeps those facts separate and requires exactly one post-baseline exact-folder task, null project assignment on list/read/resume, exact resume-time runtime roots, exact wrapper argv and inner hashes, exact item order, unchanged rule/hook/plugin guard, the passive request/resolution observer, and no extra tools or mutations. Older project-bound verifier evidence no longer satisfies the versioned safe-to-close methods. The 2026-09-02 task passed both evidence paths; following checkpoint `0003` restored successfully, and the subsequent fresh live evaluation reported `safeToClose: true`.

### 13. Live clean Land to the Mac — single-run fixture pass

On 2026-09-02 the founder invoked the fixture-only Land transaction against the same bound EC2 instance, encrypted EBS workspace, and versioned S3 bucket. The guest entered `LANDING`, froze the provider-neutral workload, and sealed exactly one next-ordinal final checkpoint, `0004-land-final`. Its exact S3 bundle and manifest versions restored successfully, then entered the Mac's private local ledger through quarantine as the immutable final-cloud commit `C`.

The local `B/L/C` reconciliation finished with outcome `APPLIED`. The acknowledgement matched that exact `C` and its recovery identities, the guest persisted the matching acknowledgement, the distributed lease returned to `LOCAL_PRIMARY`, and the exact EC2 instance stopped only after acknowledgement.

The first attempt exposed a controller-host packaging error: the configured record directory under `/run` was not writable. The failure occurred after final `C` was already durable. The EBS fence and journals preserved that recovery identity, so the corrected retry reused the same `0004-land-final` rather than recapturing a different cloud tree. The record-directory permission fix was covered by a regression test before the successful rerun.

This is one clean founder-operated pass on a generated disposable fixture. It is not evidence for arbitrary real repositories, a reviewable manifest, customer UI/helper, automatic wake of an offline helper, conflict-resolution UX, repeatability across users or runs, provider-service credential isolation, network recovery, revocation, official provider support, or launch readiness.

### 14. Live deliberate-conflict Land — single-run fixture pass

A fresh generated fixture, `p0-20260902183748-a7b1`, began from one shared baseline and then changed `REMOTE_TEST.md` differently on the Mac and cloud workspace. Plain `land` froze the cloud writer, sealed and independently restore-tested exact immutable `0002-land-final`, imported it through quarantine, captured the returning local revision, and classified both a content-level and Git merge conflict.

The controller returned `NEEDS_REVIEW` with the ownership lease still `LANDING`. The original local content, branch, index, refs, reflog, and full manifest remained byte-for-byte unchanged. The isolated conflict worktree retained stages 1, 2, and 3 for baseline `B`, local `L`, and cloud `C`; the private session refs and strict Git object verification remained valid. No apply journal, acknowledgement, ownership return, compute cleanup, or completion event was produced, and direct runner reactivation was rejected by the EBS-backed writer fence.

Repeating the same plain `land` command returned `changed: false` and preserved byte-identical controller state, events, refs, operation evidence, local conflict file, exact S3 recovery versions, and final checkpoint. An independent read-only audit agreed with every invariant. This accepts the generated-fixture conflict boundary; it does not provide the missing user-facing resolution flow or expand the claim to arbitrary workspaces or external alpha.

## AWS isolation for the EC2 pass

A dedicated local AWS CLI profile named `lift-spike` was bound to the founder's isolated personal spike account in `us-east-1`. Caller identity was verified before provisioning. Every existing company or organization account and profile remains out of scope and must never be used for this spike.

Use short-lived user-authorized credentials where possible, verify caller identity before every provisioning or lifecycle operation, and do not record the account number or credentials in this repository.

The EC2 pass should use tagged, isolated resources, encrypted storage, no public application listener, Systems Manager administration, a cost alert, and an explicit cleanup record.

### Personal Free Tier signup note

AWS's current signup and promotional rules are identity-based, not simply card-based:

- both Free and Paid plans require a valid payment method;
- phone ownership is confirmed through SMS or a voice call and a short PIN;
- AWS recommends a unique phone number per account and says a number already associated with another AWS account can cause verification problems;
- the current Free Tier is limited to new AWS customers, and the terms allow Free Tier credits for only one account;
- changing to a new credit card does not reset customer eligibility;
- a qualifying new customer receives USD 100 at signup and can earn up to another USD 100 through listed activities;
- the Free plan ends after six months or when its credits are exhausted, whichever happens first, while the credits themselves expire twelve months after account creation;
- joining AWS Organizations ends the Free Plan credit eligibility and upgrades the account to a paid plan.

Therefore this spike may use a new personal Free Plan account only if the founder is genuinely eligible under AWS's terms. If existing AWS access is solely an IAM role in someone else's company account, AWS must still make the eligibility determination during personal signup. Do not attempt to evade duplicate-account, phone, payment, or fraud checks.

Official reference:

- [AWS CLI login with console credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
- [AWS Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/)
- [AWS Free Tier terms](https://aws.amazon.com/free/terms/)
- [AWS phone verification troubleshooting](https://repost.aws/knowledge-center/phone-verify-no-call)

## Product implications so far

- The provider-blind workload runner remains technically plausible: it only needs to install, authenticate, start, health-check, and restart an opaque provider command.
- A zero-terminal Connections experience is technically plausible because the CLI produces a provider-owned short-lived artifact and the provider pairing URL successfully claimed the Linux environment from ChatGPT mobile.
- Direct ChatGPT-mobile-to-headless-Linux execution is technically viable on the tested experimental CLI surface, including a real Ubuntu EC2 workspace. The remaining uncertainty is production support, repeatability, and lifecycle reliability, not whether a phone task can reach Linux at all.
- The cloud working copy must be a real directory within the provider-browsable persistent home. Symlink indirection to an external mount failed in the tested picker.
- The default `Chat` workspace is dangerous for this product because it silently creates an empty projectless directory. Lift must verify the provider-reported `cwd` and block safe-to-close until it matches the lifted workspace.
- Process health and native-provider readiness are separate states. A live daemon with no exact native project is not ready, and readiness failure must block handoff without restarting an otherwise healthy provider process.
- Provider neutrality permits a reviewed recipe-scoped connector. The reusable runner remains generic while the connector uses the provider-owned, version-pinned API to reconstruct and verify semantic state.
- Sandbox readiness is part of the product experience. Missing user-namespace support turned one tiny edit into three approval prompts.
- The local precursor's Git checkpoint plus clean fast-forward returned the exact phone-authored commit, and the EC2 pass restored immutable checkpoint revisions from exact versioned S3 objects. Final `0004-land-final` completed one exact clean return to the Mac; a fresh run's `0002-land-final` then exercised the deliberate-conflict boundary while preserving both sides and fencing writers. Together they accept the generated-fixture Land core without proving arbitrary-workspace behavior or conflict-resolution UX.
- A changed guest boot ID plus exact EBS, checkpoint, proof-file, runner-health, and Remote-environment recovery demonstrates semantic restart continuity for one EC2 stop/start without claiming process-memory continuity.
- Lift must pin and continuously retest compatible provider versions because this surface is not yet established in the published production workflow.
- Launch copy must continue to distinguish observed behavior from officially documented support.
- Do not launch Codex direct-to-headless-Linux as a laptop-off promise until network recovery, repeated independent users and runs, revocation, automatic offline-helper recovery, conflict-resolution UX, provider-service isolation, and provider-policy tests pass. Direct phone execution, full EC2 stop/start recovery, and separate clean and deliberate-conflict fixture Land outcomes are now observed once; promotion remains gated.
- The current capture path must remain marker-gated to the generated disposable fixture. The next product slice is an explicit real-workspace manifest-review flow, followed by the customer helper and UI; additional clean/conflict repetitions and interruption tests remain evidence work.

## Exit record

Historical local-precursor record:

- phone app and version: ChatGPT on iPhone 16 Pro; exact app build not surfaced during the mirrored test
- account/feature eligibility: Remote available; visible Add Connection/manual-code UI absent; provider pairing URL accepted; Linux server appeared as a separate Remote connection
- first phone task result: failed safely in the default empty `Chat` directory; no files changed
- corrected phone task result: passed in `/home/lift/Workspace`; exactly `REMOTE_TEST.md` changed
- approval behavior: three one-time provider prompts for inspection, edit, and verification; permanent approval was not granted; extra prompts were caused by unavailable `bubblewrap` user namespaces
- Git/session result: cloud commit `dd27755`; disposable original cleanly fast-forwarded from `7f14712`; both histories retained
- laptop-off result: pending; the data path was direct phone-to-Linux, but iPhone Mirroring kept the Mac awake for test operation
- daemon restart result: partial pass; persistent auth/home reused after App Server restart and version update, but a fresh pairing/unlock flow was exercised
- network interruption result: not tested
- EC2 stop/start result: not applicable to the local container precursor
- provider-state persistence result: Linux auth, sessions, and workspace survived initiating-shell exit and App Server restart on the isolated named home volume; EC2/EBS not tested
- revocation result: not tested
- final verdict: local direct pairing, task execution, approval, Git checkpoint, and clean return pass; experimental surface remains version- and client-dependent
- product decision and fallback: proceed to the isolated EC2 lifecycle spike, but do not claim laptop-off support until the remaining promotion tests pass

Current real-EC2 record:

- runtime result: pass for provisioning and direct phone execution on a real Ubuntu EC2 workspace with separate encrypted EBS
- workspace targeting: pass; the provider-reported `cwd` matched the intended real workspace beneath `/home/lift/workspaces`
- laptop-off result: strongly corroborated founder evidence; fresh nonce proof and Mac reboot timestamps match the reported shutdown sequence, but no cryptographic device attestation was available
- cloud checkpoint result: pass for immutable Lift-private Git checkpoints `0001`, `0002`, post-restart phone checkpoint `0003`, and final checkpoint `0004-land-final` on the exact encrypted EBS volume
- off-volume recovery result: pass; checksummed bundle and manifest objects were fetched by exact S3 version and restored into fresh repositories with commit, tree, history-ref, and evidence verification; `0004-land-final` was also imported through private quarantine on the Mac
- EC2 stop/start result: structural pass; guest boot ID changed, exact encrypted EBS reattached, checkpoint `0002` commit and bundle and both proof files recovered, provider-neutral systemd runner auto-started healthy, and exact Codex Remote environment ID was preserved
- post-restart native phone result: pass once; a brand-new task bound to the exact EBS folder, completed the exact two-command proof, and entered restore-tested checkpoint `0003`
- post-restart server-side remediation: pass; pinned App Server connector registered and read back the exact native `lift` project, exact trust root, connected Remote state, and paired-controller presence while preserving the narrow write boundary; controller-side project visibility remains explicitly unknown because the phone picker showed only `Chat` and `Add new folder`
- approval observer result: deployed as schema v8 and live-proven once with root-owned service/readiness/evidence and agreeing independent historical verification; selected decision and responder identity remain guarded inference rather than directly exposed protocol evidence
- AWS binding hardening result: post-hardening live status passed exact account, non-root ARN, immutable STS user ID, live stack/resource/AMI binding, and ambient AWS endpoint/configuration scrubbing while still deriving a short-lived `safeToClose: true`
- clean Land result: pass once on the generated disposable fixture; exact `0004-land-final` returned through real EC2/EBS/S3 to the Mac, reconciliation reported `APPLIED`, the guest persisted the exact acknowledgement, ownership returned to `LOCAL_PRIMARY`, and EC2 stopped
- deliberate live conflict result: pass once on a fresh generated disposable fixture; exact restore-tested `0002-land-final` and all `B/L/C` versions were preserved, original local and Git state remained unchanged, the controller stopped at `NEEDS_REVIEW`/`LANDING`, the writer stayed fenced, no acknowledgement or cleanup ran, and an exact retry returned `changed: false`
- Land interruption result: pass for safe resume of the same durable `C`; an initial `/run` record-directory permission failure was fixed and regression-tested without creating a second final checkpoint
- network recovery result: pending
- revocation result: pending
- automatic offline-helper wake and user-facing conflict-resolution result: pending
- compatibility verdict: continue Phase 0; do not label the path Alpha or Verified and do not claim launch readiness
