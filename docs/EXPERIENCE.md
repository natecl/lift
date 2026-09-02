# Product Experience

Last updated: 2026-09-01

## Product truth

Lift will not win because it provisions virtual machines. It wins when cloud infrastructure becomes invisible enough that keeping an agent on a laptop feels unnecessarily primitive.

The recurring experience should be:

> Click Lift Off. Wait until Lift says it is safe. Close the laptop. Continue in the agent app already on your phone.

No SSH, terminal, cloud account, region, instance type, volume, daemon, token, or remote-control command should appear in the normal journey.

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

### 4. Select local workspace

The user chooses a folder through the desktop application or CLI bootstrap. Lift explains the transfer in product language:

> Lift will move this project's code, uncommitted changes, instructions, and development setup. Secrets and unrelated files stay on this computer unless you approve them.

The manifest remains inspectable, but the primary action is clear.

## Recurring one-button journey

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
9. If controller-side visibility cannot be observed, explicitly perform the provider's one-time `Add new folder` selection for the exact workspace, then confirm a fresh post-baseline task in the provider's existing phone application is bound to that project and workspace.
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

## Return to the laptop

Lift Off must be a round trip. The cloud workspace cannot become a second disconnected copy that the user later has to reconcile manually.

At Lift Off, Lift records a handoff baseline covering tracked, uncommitted, untracked, and explicitly approved ignored files. It also transfers the workspace's ownership lease from local to cloud. While the workspace is lifted, the cloud copy is the primary writer and Lift checkpoints changed cloud state into new durable manifest revisions.

At the end of the session, the user chooses one plain-language action:

> Land Workspace

Lift pauses workspace writers, creates a final checkpoint, and waits for the desktop helper if the laptop is still offline. The user never needs to commit, push, pull, copy a patch, or run a sync command.

When the desktop helper comes back online:

1. It compares local and cloud state against the handoff baseline.
2. If the local workspace is unchanged, it downloads the cloud delta outside the project, verifies hashes, rechecks the local precondition, and applies the delta transactionally.
3. If both sides changed different files, it applies nonconflicting changes and stages the divergent result for review.
4. If both sides changed the same content, it creates a recoverable branch, worktree, or sibling copy and asks the user which version to keep.
5. It never silently overwrites either side.
6. It returns workspace ownership to the laptop only after the local helper acknowledges the applied cloud revision.

The successful default message is:

> Your latest changes are back on this Mac.

The exceptional message is:

> We found edits on both computers. Nothing was overwritten.

If the laptop is opened while the workspace is still cloud-primary, Lift shows `This workspace is still lifted` and one `Bring changes back` action, which starts the same Land flow. It does not silently create a live bidirectional workspace.

The first implementation deliberately avoids background bidirectional mirroring while the cloud agent is still writing. A later continuous-sync mode may prefetch revisions, but it must preserve the same ownership, divergence, and recovery guarantees.

The exact manifest, Land, transactional-apply, and conflict rules are defined in [`STATE_SYNC.md`](STATE_SYNC.md).

## Always available, not literally one immortal process

The durable promise is the workspace, not an eternal operating-system process or one permanent provider conversation.

Lift should make interruptions invisible when possible:

- restart a provider process after failure;
- reconnect or register a replacement native remote session;
- wake stopped compute without losing files;
- preserve a provider-neutral continuation package;
- request reauthentication only when the provider requires it;
- bring the user back to the same project and current work.

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

The first post-restart phone attempts then exposed a second failure: the daemon was live but its native project registry was empty, so new tasks used synthetic projectless paths; older tasks also entered an approval loop with no usable approval control. The server-side remedy is now deployed and live-readback verifies the exact native project/root, connected Remote state, and one registered controller. The phone project picker nevertheless showed only `Chat` and `Add new folder`, so controller-side visibility remains unknown and Lift must preserve the explicit folder-binding model instead of claiming that `lift` is listed or assigned. The repaired path has now passed end to end once: exact fresh-task folder binding, post-restart proof, guarded native approval round trip, restore-tested following checkpoint, and fresh safe-to-close evaluation. Codex still must not receive the `Direct phone continuation` badge for alpha until provider-service identity and credential isolation, network recovery, revocation, repeated laptop-off runs, full Land, and provider-policy review pass their separate gates.

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
- recovery success after process or workspace restart;
- automatic cloud-to-local reconciliation success rate;
- local divergence and conflict rate;
- support requests mentioning SSH, terminals, credentials, or cloud infrastructure;
- repeated Lift Off usage per user per week.

The north-star qualitative reaction is:

> I clicked one button, closed my laptop, and everything was already on my phone.
