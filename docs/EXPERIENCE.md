# Product Experience

Last updated: 2026-09-02

## Product truth

Lift will not win because it provisions virtual machines. It wins when a software project has one persistent cloud workspace that its developers and agents can enter from any device without rebuilding it or keeping a laptop online.

The first recurring experience should be:

> Click Lift Off. Wait until Lift says it is safe. Close the laptop. Continue in the agent app already on your phone.

The north-star recurring experience should be:

> Open an agent app on your phone, select the Lift workspace, and launch useful work while every personal computer is offline.

No SSH, terminal, cloud account, region, instance type, volume, daemon, token, or remote-control command should appear in the normal journey.

The current repository is still a founder-operated feasibility harness rather than this product experience. It proves the provider path once and, on 2026-09-02, completed separate live clean and deliberate same-file conflict Land runs on generated disposable fixtures through real EC2/EBS/S3 and the Mac. The clean path restored and applied exact immutable `C`, acknowledged it, returned ownership to `LOCAL_PRIMARY`, and stopped EC2. The conflict path returned `NEEDS_REVIEW`, preserved exact `B/L/C` plus the untouched local workspace, kept ownership `LANDING`, fenced cloud writers, and made no acknowledgement or cleanup; repeating Land was a no-op. There is still no dashboard, signed helper, reviewable arbitrary real-workspace manifest, one-click connection flow, automatic offline-helper wake, or conflict-resolution UI. See [`CURRENT_STATE.md`](CURRENT_STATE.md) for the exact implementation boundary.

## What provider-neutral means for the product

Provider-neutral does not mean every provider works without integration work. Authentication, native mobile registration, session resume, and readiness are different for each provider.

Provider-neutral means:

- the Lift workspace is not owned by any agent provider;
- the user can connect more than one supported provider;
- switching providers does not move or recreate the workspace;
- the underlying remote workload runner is identical for every provider;
- provider differences are isolated in reviewed connection recipes;
- users interact with one consistent Lift connection and launch experience;
- provider chat, approvals, models, transcripts, and mobile transport remain provider-owned.

It also means the workspace can host multiple heterogeneous agents over time. The workspace's files, services, checkpoints, browser capabilities, policies, and activity history cannot belong to a single provider conversation.

The technical complexity may vary underneath. The product surface must not.

## First-time journey

### 1. Create a Lift account

The user signs in to Lift and sees one primary next step:

> Connect the agent you already use

### 2. Connections tab

The Connections tab shows supported providers as simple cards:

```text
Connections

Codex        Not connected       [Connect]
Claude Code  Not connected       [Connect]
Other agent  Bring your own       [Configure]
```

Each card communicates only user-relevant facts:

- connected account or workspace;
- connection health;
- whether direct phone continuation is supported;
- whether the provider needs attention;
- disconnect or reconnect action.

Do not expose commands, environment variables, credential paths, or daemon state.

### 3. Connect provider

The user selects `Connect Codex` or another provider. Lift opens the provider-owned authentication flow in a browser window or secure device flow.

The ideal interaction is:

1. Click Connect.
2. Sign in on the provider's domain.
3. Approve the connection.
4. Return to Lift and see Connected.

Lift must never ask the user to paste a session cookie or find a token in a terminal. Where a provider lacks a supported third-party OAuth flow, Lift can orchestrate the provider's own CLI login inside the cloud workspace and present the browser step through the dashboard. The control plane stores connection metadata; reusable credentials remain encrypted and isolated from project files.

The connection is established once and reused until the provider requires reauthentication.

### 4. Create or select workspace

The user sees three creation choices:

```text
Create workspace

From this computer   Lift an active local folder
From GitHub          Start from a repository
Empty workspace      Start from a template or blank environment
```

Every choice creates the same class of durable Lift workspace. GitHub can be connected later and is not required for a local or empty workspace.

### 5. Select local workspace

The user chooses a folder through the desktop application or CLI bootstrap. Lift explains the transfer in product language:

> Lift will move this project's code, uncommitted changes, instructions, and development setup. Secrets and unrelated files stay on this computer unless you approve them.

The manifest remains inspectable, but the primary action is clear.

### GitHub-created and empty workspaces

A GitHub-created workspace asks the user to select a repository and, where applicable, a branch or default environment template. Lift then prepares the runtime and opens the same workspace page used by a locally lifted project.

An empty workspace begins from a reviewed base image or template and may connect GitHub later. Neither path claims to include local dirty state that was never transferred.

## Recurring local handoff journey

The workspace card has one dominant button:

> Lift Off

When pressed, Lift performs the complete sequence without asking the user to operate infrastructure:

1. Inspect current project changes.
2. Apply previously approved transfer rules.
3. Wake or create the persistent cloud workspace.
4. Transfer changed state.
5. Reconstruct missing tools and dependencies.
6. Start the selected provider's native remote workload.
7. Run idempotent provider preparation, such as registering the exact native project, without requiring a phone or controller to be online.
8. Freshly verify runner health and provider semantic prerequisites, including the exact server-side native project ID, root, Remote connection, and controller prerequisite where supported; report controller-side project visibility separately and never infer it from those facts.
9. If controller-side visibility cannot be observed, explicitly perform the provider's one-time `Add new folder` selection for the exact workspace, then confirm a fresh post-baseline task in the provider's existing phone application is bound to that exact folder and `cwd`. Keep its controller `projectId` and the separately registered server project as distinct facts.
10. Complete a one-time native approval round trip when the supported workflow will require approvals.
11. Create and restore-test a durable checkpoint containing the verified phone and approval evidence.
12. Revalidate the live runner and native provider state, then display the final safe state for only a short stated validity window.

The default progress presentation uses plain language:

```text
Preparing your workspace
Moving your latest changes
Starting Codex
Connecting your phone

Ready. You can close this laptop.
Open Codex on your phone to continue.
```

Do not say “EC2 provisioning,” “mounting EBS,” “starting systemd,” “opening an SSH tunnel,” or “registering the App Server.”

## The safe-to-close contract

Lift must never show “You can close this laptop” merely because file upload finished.

The state requires, in this order where later evidence depends on earlier evidence:

- the approved handoff baseline durably persisted in the cloud;
- the workspace volume mounted and healthy;
- a fresh live check showing the selected remote workload running and healthy;
- credentials present and not known to be expired;
- a fresh live check of the provider's native remote registration and controller prerequisite when supported;
- the provider's exact native project ID and root read back when project selection is part of the workflow;
- controller-side project visibility reported as verified only when directly observed, otherwise explicitly `unknown` until a fresh correctly bound task proves the path;
- a fresh post-baseline task's actual working directory and project binding verified for the claimed compatibility level;
- a completed native approval round trip when approvals are required for ordinary work;
- a durable, restore-tested checkpoint created after the task-binding and approval evidence;
- no required step still depends on the laptop;
- the local client no longer needed for control-plane progress.

If Lift can verify only process health and not provider registration, the UI must say so and must not promise phone continuation. Server-side project registration must likewise not be presented as proof that the controller's project picker can see that project. Paired-controller presence alone is also insufficient because it proves neither project visibility nor current reachability or approval delivery. A cached historical `safeToClose` value is never current truth: the dashboard must recompute it from fresh runner and native-provider observations and expire the displayed result if it is not refreshed. The Phase 0 harness currently emits a 30-second validity window. A connection recipe qualifies for the one-click experience only after its full readiness check is proven.

## Continue on the phone

Lift does not provide the coding conversation. The user opens the provider application they already know.

Where supported, Lift may provide:

- `Open Codex` or `Open Claude` deep link;
- provider-owned session URL;
- provider-owned QR code;
- a workspace name chosen to match the Lift project;
- an instruction such as “Open ChatGPT, select Remote, then choose Acme.”

These are handoff affordances, not a Lift chat layer.

Phone continuation is not complete if the user can only observe or continue the process launched before Lift Off. A first-class provider connection should also allow the user to create a completely new task from the provider's phone application, bind it to the exact Lift workspace, and begin work while the laptop is offline.

The target flow is:

1. Open the provider application on the phone.
2. Select its remote-workspace surface.
3. Select the named Lift workspace.
4. Launch a new task.
5. Lift wakes compute if necessary.
6. Lift verifies the task's actual workspace binding and declared capabilities.
7. The provider application continues to own prompts, approvals, and notifications.

Lift may expose mobile workspace management for health, agents, task modes, permissions, cost, snapshots, stop, and recovery. It should not require a second chat surface when the provider application already supplies one.

## Multi-agent experience

A workspace may run one or more agent tasks. Starting another task asks only for the goal, agent, and an optional execution-mode override. Infrastructure choices remain hidden.

```text
Start agent

Agent       Codex
Workspace   Acme
Mode        Work together

[Start]
```

The user-facing modes are:

- `Work together`: use the shared working directory and see current uncommitted changes immediately;
- `Work independently`: use an isolated worktree, branch, or copy-on-write environment and return a reviewable result;
- `Review only`: inspect and test without permission to modify files.

Shared mode does not pretend concurrent arbitrary shell writes are perfectly safe. Before the run, Lift creates a recoverable checkpoint. During the run, it attributes commands and observed file changes to each agent, shows current file activity, detects overlap, allows immediate pause or stop, and retains overwritten versions when a collision occurs.

The workspace page should answer:

- which humans and agents are present;
- what each task is trying to accomplish;
- whether each task is shared, isolated, or read-only;
- which files and services each task is touching;
- whether any task is blocked, waiting for approval, or colliding;
- what changed and what can be restored;
- which results are ready for review or GitHub publication.

## Internet, browser, and computer experience

The workspace capability panel should make powerful access visible without forcing infrastructure knowledge:

```text
Capabilities

Internet       Allowed with workspace policy
Terminal       Allowed
Browser        Project profile
Computer use   Ask for consequential actions
Previews       Two protected services
```

The capability sequence is terminal and bounded outbound internet, headless Chromium for tests and automation, visible browser observation, secure user takeover, persistent project-scoped browser identity, and broader computer use.

When login, passkey, two-factor authentication, CAPTCHA, or human confirmation is required, the agent requests a short-lived takeover. The user sees the exact workspace and browser context, completes the human-only step, and returns control. Lift never imports the user's everyday browser cookie database or presents a project browser profile as a separate agent security boundary unless isolation is actually enforced.

Concurrent agents receive separate browser contexts or screens by default even when they share the code working directory. Sharing an authenticated browser identity must be an explicit workspace policy.

## Team workspace experience

After solo repeat use is proven, a workspace owner can invite a teammate or derive access from a connected GitHub repository. The first team experience remains intentionally small:

- owner, member, and viewer roles;
- explicit workspace membership;
- per-human and per-agent task identity;
- scoped secrets and browser capabilities;
- shared, isolated, and read-only task policies;
- activity provenance and stop controls;
- GitHub review and publication.

Lift should not require enterprise SSO, complex organization hierarchy, or a collaborative code editor to validate small-team demand.

## Return to the laptop

Lift Off must be a round trip. The cloud workspace cannot become a second disconnected copy that the user later has to reconcile manually.

At Lift Off, Lift records a handoff baseline covering tracked, uncommitted, untracked, and explicitly approved ignored files. It also transfers the workspace's ownership lease from local to cloud. While the workspace is lifted, the cloud copy is the primary writer and Lift checkpoints changed cloud state into new durable manifest revisions.

At the end of the session, the user chooses one plain-language action:

> Land Workspace

Lift pauses workspace writers, creates a final checkpoint, and waits for the desktop helper if the laptop is still offline. The user never needs to commit, push, pull, copy a patch, or run a sync command.

When the desktop helper comes back online:

1. It downloads the exact final cloud revision outside the project, verifies it, and imports its recovery refs into Lift-private state.
2. It captures the current local workspace as private revision `L` without moving the user's branch, refs, or index.
3. It compares baseline `B`, local `L`, and cloud `C`, then performs the return merge in an isolated worktree.
4. If the result is clean—including independent edits on different paths—it rechecks the local precondition and applies the verified result transactionally.
5. If changes overlap or another platform hazard exists, it leaves the original workspace untouched, preserves every side, and asks the user which result to keep.
6. It never silently overwrites either side and returns ownership to the laptop only after the exact applied cloud revision is acknowledged locally and by the cloud record.

The successful default message is:

> Your latest changes are back on this Mac.

The exceptional message is:

> We found edits on both computers. Nothing was overwritten.

If the laptop is opened while the workspace is still cloud-primary, Lift shows `This workspace is still lifted` and one `Bring changes back` action, which starts the same Land flow. It does not silently create a live bidirectional workspace.

The first implementation deliberately avoids background bidirectional mirroring while the cloud agent is still writing. A later continuous-sync mode may prefetch revisions, but it must preserve the same ownership, divergence, and recovery guarantees.

The exact manifest, Land, transactional-apply, and conflict rules are defined in [`STATE_SYNC.md`](STATE_SYNC.md).

The founder fixtures have now exercised both return outcomes once across the live infrastructure boundary. The clean transaction resumed from its already durable `0004-land-final`, completed `APPLIED`, acknowledged the same `C`, returned the lease to `LOCAL_PRIMARY`, and stopped compute. A fresh deliberate-conflict transaction stopped at `NEEDS_REVIEW`, preserved exact local and cloud versions without modifying the original workspace, kept the lease `LANDING`, fenced the cloud runner, and repeated idempotently. This still does not prove the intended user experience: the runs were terminal-operated, the fixtures used fixed transfer policy, the helper did not wake automatically from an offline state, and no user-facing conflict resolution was completed.

## Always available, not literally one immortal process

The durable promise is the workspace, not an eternal operating-system process or one permanent provider conversation.

Lift should make interruptions invisible when possible:

- restart a provider process after failure;
- reconnect or register a replacement native remote session;
- wake stopped compute without losing files;
- preserve a provider-neutral continuation package;
- request reauthentication only when the provider requires it;
- bring the user back to the same project and current work.
- accept and route a new provider-native mobile task after compute wakes.

The user experience should feel permanent even when infrastructure and provider sessions restart underneath.

## Connections architecture

### Provider-blind runner

Executes reviewed commands, attaches PTYs, supervises processes, and persists approved paths. It contains no provider protocol logic.

### Connection recipe

Describes how a supported provider uses the generic runner and uniform connection state machine:

- installation executable and pinned version;
- provider-owned authentication mode;
- login command or browser authorization entrypoint;
- persistent credential and configuration paths;
- remote workload command;
- process health check;
- optional idempotent post-start preparation command;
- provider registration check from a reviewed supported or explicitly experimental/version-pinned signal;
- recovery and reauthentication behavior;
- optional provider-owned deep link or session URL extraction;
- declared mobile capabilities and limitations.

A connection recipe can be mostly declarative. If a provider requires custom behavior, a small sandboxed connector may implement the same contract. Provider code never enters the workspace, transfer, or reconciliation layers.

### Connection manager

Presents one consistent lifecycle to the product:

```text
DISCONNECTED
CONNECTING
CONNECTED
NEEDS_REAUTH
STARTING_REMOTE
REMOTE_RUNNING
REMOTE_READY
DEGRADED
ERROR
```

`REMOTE_RUNNING` means the provider process is live but semantic or end-to-end readiness is not yet proven. Missing or wrong native project/root, absent controller, stale authentication, or unknown required approval behavior moves the connection to `DEGRADED` without forcing a restart of an otherwise healthy process. Only `REMOTE_READY` qualifies for the “safe to close” message.

## Connection security model

- Authentication happens on the provider's domain or through the provider's supported device flow.
- Lift never collects provider passwords.
- Prefer OAuth with PKCE or device authorization when officially supported.
- Store reusable provider credentials in an encrypted per-user vault or approved workspace state, never in the project tree.
- Keep raw credentials out of logs, snapshots, analytics, support output, and connection metadata.
- The Connections tab can revoke Lift's stored state but must also explain when the user should revoke access at the provider.
- Reauthentication must be a visible provider-owned browser flow.
- Never claim an account-level integration that the provider does not officially permit.

## Provider eligibility for polished support

A provider can appear as a first-class one-click connection only when Lift has verified:

1. Supported installation on the Lift runtime.
2. A user-authorized authentication path that can be presented without a terminal.
3. A headless native remote-control process or equivalent.
4. A provider-owned phone or web client.
5. A reliable readiness or registration signal.
6. Recovery behavior after process and network interruption.
7. A supported credential storage and revocation model.
8. Provider terms compatible with the integration.

If any item is missing, the provider may be available as an advanced custom recipe but should not be marketed as one-click mobile continuation.

## Codex reality check

The official OpenAI documentation currently establishes:

- Codex CLI can be installed on Linux and signed in with ChatGPT or another available method;
- ChatGPT mobile Remote controls a connected Mac or Windows desktop host;
- ChatGPT Desktop can start Codex App Server on a remote SSH host;
- the documented phone flow still depends on an awake desktop host;
- direct App Server WebSocket exposure is experimental and not a production integration surface.

The current experimental CLI daemon and provider-owned pairing URL have now carried real phone tasks directly to a real Ubuntu EC2 workspace. A founder laptop-off run is strongly corroborated by a fresh challenge/proof exchange and Mac reboot timestamps, but it is human-attested rather than cryptographically device-attested. One EC2 stop/start changed the guest boot ID while preserving the exact encrypted workspace volume, earlier checkpoints and proof files, a healthy automatically restarted provider-neutral runner, and the exact Codex Remote environment ID. A following fresh phone task completed the live observed approval-and-proof turn, entered restore-tested checkpoint `0003`, and produced a fresh `safeToClose: true` evaluation.

In the tested mobile picker, `Add new folder` creates a controller task bound to the selected canonical folder while leaving the experimental App Server `projectId` unset. Lift must present that as folder continuity, not as project visibility: the separately registered server project may remain healthy while the mobile task is explicitly `project-unassigned`. The safe-to-close verifier requires the one fresh task's exact `cwd`, null project assignment, resume-time runtime root, exact two-command `/bin/bash -lc` envelope, unchanged approval guard, and passive approval lifecycle evidence before the folder binding is considered verified.

The manual `Add new folder` action is an observed feasibility workaround, not the target product journey. Before first-class support, Lift must either orchestrate a supported provider-owned equivalent from the Connections/Lift Off flow or state the one-time provider-app action clearly and verify the resulting folder binding without terminal setup.

The first post-restart phone attempts then exposed a second failure: the daemon was live but its native project registry was empty, so new tasks used synthetic projectless paths; older tasks also entered an approval loop with no usable approval control. The server-side remedy is now deployed and live-readback verifies the exact native project/root, connected Remote state, and one registered controller. The phone project picker nevertheless showed only `Chat` and `Add new folder`, so controller-side visibility remains unknown and Lift must preserve the explicit folder-binding model instead of claiming that `lift` is listed or assigned. The repaired path has now passed end to end once: exact fresh-task folder binding, post-restart proof, guarded native approval round trip, restore-tested following checkpoint, and fresh safe-to-close evaluation. Clean and deliberate-conflict generated-fixture Land outcomes have also passed once each, but Codex still must not receive the `Direct phone continuation` badge for alpha until provider-service identity and credential isolation, network recovery, revocation, repeated users and runs, conflict-resolution UX, the automatic no-terminal helper journey, and provider-policy review pass their separate gates.

Official references:

- [Codex CLI](https://learn.chatgpt.com/docs/codex/cli)
- [Codex Remote](https://learn.chatgpt.com/docs/remote)
- [Codex remote connections](https://learn.chatgpt.com/docs/remote-connections)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)

## Claude Code comparison

Claude Code documents a direct Remote Control process that connects to Claude's web and mobile applications through outbound HTTPS. It still requires an eligible full user login and has provider-specific session and reconnect behavior. This makes it a good second recipe for proving that the connection system remains neutral.

Reference:

- [Claude Code Remote Control](https://code.claude.com/docs/en/remote-control)

## Experience metrics

Measure whether complexity truly disappeared:

- time from Lift Off click to safe-to-close;
- percentage of launches requiring any user intervention;
- connection success and native mobile visibility rate;
- provider reauthentication frequency;
- percentage of users who actually close the laptop;
- percentage who continue from the provider's phone application;
- percentage who launch a completely new provider-native task while the laptop is offline;
- time from a mobile launch request to a correctly bound running task;
- workspaces reused across several days without reconstruction;
- workspaces with concurrent or sequential multi-agent use;
- shared-mode overlap warnings, recoveries, and abandoned runs;
- browser-task completion and takeover success without credential leakage;
- collaborator invitations, joins, and repeated team use;
- recovery success after process or workspace restart;
- automatic cloud-to-local reconciliation success rate;
- local divergence and conflict rate;
- support requests mentioning SSH, terminals, credentials, or cloud infrastructure;
- repeated Lift Off usage per user per week.

The north-star qualitative reaction is:

> I closed my laptop, started another agent from my phone, and it entered the same working project my team and other agents were already using.
