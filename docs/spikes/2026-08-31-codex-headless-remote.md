# Codex Headless Remote Feasibility Spike

Date: 2026-08-31

Status: partial pass. A real ChatGPT iPhone task paired directly to a headless Linux Codex App Server, edited the intended persistent workspace, completed provider-owned approvals, and returned through a clean Git fast-forward. EC2, a truly laptop-off run, network interruption, guest restart, revocation, and production-support policy remain pending.

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

Still required, in order:

1. interrupt and restore network access;
2. restart the Linux guest while preserving the provider home and workspace volumes;
3. repeat on Ubuntu EC2 with workspace and approved provider state on encrypted EBS;
4. stop and start EC2, restart the recipe semantically, and issue another phone task;
5. repeat without iPhone Mirroring or any awake desktop to prove the literal laptop-off claim;
6. revoke the mobile connection and confirm the server can no longer be controlled.

The Docker precursor also exposed a sandbox prerequisite. Bundled `bubblewrap` could not create an unprivileged user namespace, so read, edit, and verification commands retried through provider-owned escalation prompts. The production Ubuntu image must preflight Codex's sandbox prerequisites and kernel user-namespace support; otherwise a trivial edit produces avoidable approvals and weaker isolation.

The product may promise filesystem and session continuity only for the state it can durably reconstruct. It must not promise suspended RAM or invisible provider behavior.

## AWS isolation for the EC2 pass

A new local AWS CLI profile named `lift-spike` was created with region `us-east-1` and JSON output. It currently contains no credentials. Every existing company or organization account and profile is out of scope and must never be used for this spike.

Once the user has an eligible personal AWS account, bind `lift-spike` with `aws login --profile lift-spike`. AWS's console-login flow supplies short-lived credentials and avoids storing a long-lived access key. Verify the caller identity before provisioning, without recording the account number in this repository.

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
- Direct ChatGPT-mobile-to-headless-Linux execution is technically viable on the tested experimental CLI surface. The remaining uncertainty is production support and lifecycle reliability, not whether a phone task can reach Linux at all.
- The cloud working copy must be a real directory within the provider-browsable persistent home. Symlink indirection to an external mount failed in the tested picker.
- The default `Chat` workspace is dangerous for this product because it silently creates an empty projectless directory. Lift must verify the provider-reported `cwd` and block safe-to-close until it matches the lifted workspace.
- Sandbox readiness is part of the product experience. Missing user-namespace support turned one tiny edit into three approval prompts.
- Git checkpoint plus clean fast-forward returned the exact phone-authored commit while retaining session history, which supports the existing Git-backed Land decision.
- Lift must pin and continuously retest compatible provider versions because this surface is not yet established in the published production workflow.
- Launch copy must continue to distinguish observed behavior from officially documented support.
- Do not launch Codex direct-to-headless-Linux as a laptop-off promise until EC2, network, guest restart, literal laptop-off, revocation, and provider-policy tests pass. The local direct-phone execution gate itself is now passed.

## Exit record

Current local-precursor record:

- phone app and version: ChatGPT on iPhone 16 Pro; exact app build not surfaced during the mirrored test
- account/feature eligibility: Remote available; visible Add Connection/manual-code UI absent; provider pairing URL accepted; Linux server appeared as a separate Remote connection
- first phone task result: failed safely in the default empty `Chat` directory; no files changed
- corrected phone task result: passed in `/home/lift/Workspace`; exactly `REMOTE_TEST.md` changed
- approval behavior: three one-time provider prompts for inspection, edit, and verification; permanent approval was not granted; extra prompts were caused by unavailable `bubblewrap` user namespaces
- Git/session result: cloud commit `dd27755`; disposable original cleanly fast-forwarded from `7f14712`; both histories retained
- laptop-off result: pending; the data path was direct phone-to-Linux, but iPhone Mirroring kept the Mac awake for test operation
- daemon restart result: partial pass; persistent auth/home reused after App Server restart and version update, but a fresh pairing/unlock flow was exercised
- network interruption result:
- EC2 stop/start result:
- provider-state persistence result: Linux auth, sessions, and workspace survived initiating-shell exit and App Server restart on the isolated named home volume; EC2/EBS not tested
- revocation result:
- final verdict: local direct pairing, task execution, approval, Git checkpoint, and clean return pass; experimental surface remains version- and client-dependent
- product decision and fallback: proceed to the isolated EC2 lifecycle spike, but do not claim laptop-off support until the remaining promotion tests pass
