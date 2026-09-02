# Product and Architecture Decisions

Last updated: 2026-09-02

This log records decisions already made so future work does not reopen them accidentally. Change a decision when evidence warrants it, and record why.

## Accepted decisions

### D-001: Consumer and prosumer first

Decision: Build initially for an individual agent-heavy builder, not an enterprise platform team.

Reason: The motivating behavior is personal laptop independence. Enterprise requirements would obscure the core experience.

### D-002: Replace laptop dependence before replacing GitHub

Decision: The first buyer and workflow are personal, but the product object is a persistent project workspace—not a collaborative source-hosting platform or a disposable personal VM.

Reason: Laptop independence produces the stronger emotional promise and matches the founder's interest.

### D-003: Infrastructure for agents, not another agent

Decision: Support existing coding agents and do not create a proprietary coding agent.

Reason: Users already have preferred agents, subscriptions, and workflows. Lift should remain useful as providers change.

### D-004: State continuity is the wedge

Decision: Differentiate through the local-to-cloud handoff rather than generic persistent compute or mobile access.

Reason: Direct competitors already provide cloud environments, phone interfaces, and several preinstalled agents.

### D-005: Selective transplant, not whole-laptop cloning

Decision: Transfer and reconstruct only the state required for the selected workspace.

Reason: Whole-device cloning is unsafe, slow, cross-platform fragile, and inconsistent with a weekend prototype.

### D-006: Semantic continuity is acceptable

Decision: Processes may restart in the cloud if the same project, goal, agent context, and visible work continue.

Reason: Transparent process migration would greatly increase complexity without being required for the user outcome.

### D-007: Phone as command surface

Decision: Prioritize direction, approval, status, changes, and previews over a full mobile code editor.

Reason: The user wants to avoid opening a laptop, not manually reproduce desktop coding on a small screen.

### D-008: Git remains underneath the initial product

Decision: Use Git concepts for versioning and reconciliation without requiring all active state to be committed or pushed.

Reason: Replacing GitHub or inventing a new distributed version-control system is unnecessary for the wedge.

### D-009: Browser-profile migration is out of MVP

Decision: Do not copy arbitrary authenticated browser state in the initial release.

Reason: Browser cookies radically expand security risk. Isolated project browser identities can be explored later.

### D-010: AWS is an acceptable initial infrastructure target

Decision: A Lift-hosted AWS prototype may use a simple VM per workspace. BYO AWS can follow.

Reason: The founder is open to AWS, and validating continuity matters more than early infrastructure density.

### D-011: Provider applications remain the interaction surface

Decision: Do not build a Lift mobile chat, approval, notification, or coding interface. Users continue through the Codex, Claude, or other provider clients they already use.

Reason: Preserving the workflow is central to the product, and recreating provider interfaces would distract from state continuity.

### D-012: EC2 and EBS are the first runtime

Decision: Use one x86_64 Ubuntu EC2 instance and a separate encrypted gp3 EBS workspace volume for the first slice.

Reason: A full Linux VM provides the fewest constraints for PTYs, arbitrary tools, authentication, background daemons, SSH, and durable state. It is the fastest way to test continuity even if a managed runtime is adopted later.

### D-013: Codex first recipe, provider-blind core

Decision: Validate Codex first because it is the founder's available provider. Run it as a reviewed recipe through the same generic workload supervisor used for any executable. Do not add Codex conversation, approval-transport, or Remote-relay protocol code to Lift; isolate any provider setup and readiness calls in the reviewed connection recipe.

Reason: The first recipe should match the founder's real workflow without coupling process supervision, compute, state transfer, or reconciliation to OpenAI-specific behavior.

### D-014: Codex laptop-off support is gated by a spike

Decision: The real EC2 pairing, laptop-off, stop/start, fresh phone-task, guarded approval/proof, following checkpoint, restore test, one clean live fixture Land, and one deliberate live fixture conflict have now passed once. Keep direct ChatGPT-mobile-to-Ubuntu Codex control classified as Experimental until network recovery, revocation, repeated independent runs, provider-policy review, provider-service credential isolation, explicit real-workspace review, and repeated conflict plus broader interruption evidence pass. Keep the documented ChatGPT Desktop-to-SSH path as a fallback, but do not call that fallback laptop-independent.

Reason: Single-run feasibility answers whether the path can work, not whether OpenAI supports the topology or Lift can operate it safely and reliably for users. Official OpenAI documentation still establishes mobile pairing through an awake Mac or Windows desktop host, while the direct Linux commands remain experimental.

### D-015: Agent neutrality is one user-controlled remote workload runner

Decision: Allow a user to choose an executable, version, installation command, authentication command, run command, approved persistent state directories, network policy, and restart policy through one generic recipe. Lift may curate presets and narrow lifecycle connectors, but will not implement provider-specific conversation or remote-transport adapters.

Reason: Lift can supervise provider-owned remote commands without knowing their protocols. Mobile pairing and session semantics remain end to end between the user and provider and must not be faked or normalized.

### D-016: User experience is the product

Decision: The supported recurring journey is `Connect once -> select workspace -> click Lift Off -> wait for safe to close -> continue in the provider app`. Do not require a terminal, SSH, copied token, cloud console, or provider command.

Reason: Compute and remote processes are commodities. Lift's value is removing the setup and uncertainty that currently keep the laptop in the loop.

### D-017: Connections tab above the provider-blind runner

Decision: Add a Connections tab and generic connection manager driven by reviewed provider recipes. Each recipe may declare provider-owned authentication, native remote startup, readiness, encrypted state, and recovery. Keep workspace and runner code provider-neutral.

Reason: Zero-terminal onboarding and reliable one-click launch require knowledge of each provider's supported authentication and readiness behavior, but that knowledge can remain isolated from the durable workspace core.

### D-018: Safe to close is a verified product state

Decision: Display `Ready. You can close this laptop.` only after approved state is durable, the cloud workspace is healthy, the native remote workload is running, required provider readiness checks pass, and no remaining step depends on the laptop.

Reason: A false readiness claim destroys the central trust promise. File upload or process health alone is not sufficient evidence of mobile continuation.

### D-019: One-button, conflict-safe return handoff

Decision: Use an explicit workspace ownership lease: local before Lift Off, cloud while lifted, and local again only after Land completes. `Land Workspace` freezes a final cloud revision; when the desktop helper is available, Lift automatically stages, verifies, and applies it if local state has not diverged. When both sides changed, preserve both versions and route through a recoverable merge rather than overwriting either side.

Reason: Lift Off must be a round trip, but invisible bidirectional mirroring creates unacceptable data-loss risk. A handoff baseline, explicit ownership, and one-button return preserve simplicity and trust.

### D-020: Git-backed reconciliation, GitHub optional

Decision: Represent the Lift Off baseline, cloud checkpoints, and returning local state as commits in a Lift-private Git repository. Perform the Land three-way merge in an isolated worktree. On a clean merge, transactionally apply the result to the user's working tree without moving their branch or rewriting their index. Never push Lift refs or open a GitHub pull request without explicit authorization.

Reason: Git already provides proven ancestry, diff, rename detection, and three-way merge semantics. Keeping the merge repository private preserves uncommitted workspace continuity and enables a PR-like experience without requiring a GitHub remote or exposing approved ignored files.

### D-021: Every handoff has a durable session ledger

Decision: Retain the baseline, complete checkpoint chain, final cloud state, returning-local state, merge result, and Land receipt after every session, including clean merges. Store them under an immutable Lift-private session namespace until the user explicitly deletes the session, workspace, or account. Routine cleanup may remove staging and unreachable duplicates but never retained session history.

Reason: A safe merge is not the end of useful state. Persistent session history provides restore points, auditability, cross-session continuity, incident recovery, and a product-level timeline without polluting the user's repository history.

### D-022: Provider-visible workspaces are real directories on persistent storage

Decision: Place each provider-visible cloud working copy at a real path beneath the remote user's supported persistent workspace root, such as `/home/lift/workspaces/<workspace-id>`. Do not depend on a symbolic link from that root to a separately mounted working tree. Verify the provider-reported `cwd` before declaring safe-to-close.

Reason: The ChatGPT Remote folder picker accepted a real clone at `/home/lift/Workspace` but refused a symlink from that path to `/workspace`. Its default `Chat` choice created an empty projectless directory, causing the first phone task to fail safely outside the intended repository. A canonical real path and explicit `cwd` check remove both failure modes.

### D-023: Provider-specific setup is recipe-scoped, and readiness is not liveness

Decision: Keep the workload supervisor provider-blind while allowing a reviewed, version-pinned recipe to declare separate `prepare` and `readiness` commands. A provider connector may use the provider-owned control API to register the exact persistent workspace and configure only that root. This idempotent preparation must not depend on transient Remote connectivity or controller presence; the non-mutating readiness command checks those conditions and returns normalized nonsecret evidence. Server-side project registration and controller-side project visibility are separate facts: when the controller's saved-folder registry cannot be observed, readiness must report visibility as `unknown` and unverified rather than infer it from project registration or paired-controller presence. The founder flow may then explicitly request the one-time provider-native `Add new folder` selection for the exact workspace, but production one-click compatibility remains unproven until that setup is supported or eliminated. The connector must not mutate provider databases directly. Process liveness may trigger restart; a readiness failure must block `safe to close` without creating a restart loop. Safe-to-close additionally requires a fresh live runner/native-provider check, a fresh post-baseline phone-task binding, a native approval round trip, and a durable checkpoint created afterward.

Reason: After the first EC2 stop/start, the Codex daemon was healthy and retained its Remote environment, but its native project registry was empty. New mobile tasks therefore opened projectless workspaces outside Lift's writable root. Missing approval controls were also observed, but their exact cause is not yet proven. Registering and reading back the exact workspace through the version-pinned Codex App Server project API reconstructs server-side semantic state while preserving one generic supervisor and a narrow filesystem boundary. The phone picker subsequently showed only `Chat` and `Add new folder`, demonstrating that App Server project registration does not itself prove controller-side visibility. Treating either daemon health or server registration as complete phone readiness produced a false positive.

### D-024: Provider connector records stay outside the project; service identity isolation is a pre-alpha gate

Decision: Store the Codex connector's nonsecret workspace binding and create-idempotency record at `/home/lift/.codex/lift/<workspace-id>/codex-project.json`, not inside the provider-visible project. Before inviting external alpha users, separate the provider service and reusable credentials from the untrusted workspace workload with a distinct Unix identity or an equivalently narrow credential broker.

Reason: Keeping connector state outside the workspace prevents it from entering project checkpoints, Land output, or normal Git history. File placement and mode bits alone do not isolate credentials while the provider daemon and arbitrary workspace process share the same operating-system identity.

### D-025: Phone readiness evidence is bound to one canonical challenge

Decision: Represent each native-phone proof and approval attempt as one exact, versioned challenge whose canonical JSON has a SHA-256 identity. Bind the fresh-thread evidence, proof bytes, approval item, durable checkpoint, and final safe-to-close evidence to that identity. A normal re-arm removes any post-restart alias; post-restart verification requires its alias to equal the active challenge exactly. The proof source selects one fixed relative path and checkpoint label, and the verifier rejects extra fields, alternate paths, stale aliases, unsupported approval policies, network-enabled approvals, and mismatched project or runtime roots.

Reason: Independent booleans can be assembled from different attempts, and a stale post-restart challenge can otherwise authorize a newer transition. One canonical identity makes replay, cross-challenge mixing, wrong-source checkpointing, and permissive approval fallback fail closed.

### D-026: Runtime actions bind local state to live CloudFormation resources

Decision: Before operating on a deployed workspace, validate the persisted run, AWS identity, stack identity, outputs, and canonical paths, then re-read the live CloudFormation stack. Bind the operator to the exact account, principal ARN, and immutable STS user ID so recreating a same-named IAM user cannot inherit authority. Require the exact stored stack ID and name, a completed safe status, the expected immutable parameters, byte-for-byte matching outputs, and exact physical bindings for the EC2 instance, EBS volume, and S3 transfer bucket. Revalidate the selected Ubuntu AMI against Canonical ownership, availability, and architecture rather than trusting a cached ID. Run AWS subprocesses with a sanitized inherited environment that removes ambient credential, profile, region, endpoint, CA, Botocore, and metadata-endpoint overrides and explicitly ignores configured endpoint URLs; pass the selected profile and region as explicit CLI arguments.

Reason: Locally persisted identifiers are routing hints, not authority. A stale, edited, cross-account, or partially replaced state file must not redirect lifecycle commands, proof collection, or checkpoint writes to unrelated infrastructure.

### D-027: Phase 0 approval confirmation combines live observation and independent history, but remains an inference

Decision: Do not treat a completed `commandExecution` item as standalone approval proof. Before the Codex founder prompt, start a challenge-specific passive observer as a hardened root-owned transient systemd service from checksum-verified, root-owned runtime files. Require it to initialize, prove an empty post-baseline scan, and write a root-owned private readiness record before arming is exposed to the user. The observer never answers an App Server request and must remain present through the exact approval request, matching resolution, successful canary, successful proof command, and completed full turn. Bind its root-owned evidence to the challenge, policy guard, baseline, environment, native project, `cwd`, thread, turn, request, both item identities, both command hashes, and event order.

Separately, keep the historical verifier independent: it must re-read the completed new task and require one turn, exact `on-request` policy, `user` reviewer, network-disabled sandbox, and exactly the environment-cleared HTTPS canary followed by the independently reconstructed proof command, both agent-originated with null plugin/script provenance and no unreviewed tool or mutation items. Capture a SHA-256 guard over active config, rules, hooks, the complete bounded `plugin/list` response, and managed requirements before arming and require it unchanged during verification. Installed plugins may remain enabled, but every effective hook and every plugin/MCP execution or plugin/script command provenance remains disallowed in the proof turn. This binds the observed plugin environment; it does not prove plugin-free model context or immutable remote plugin content. High-assurance promotion requires isolated plugin-disabled execution or content-addressed pinned bundles. Both evidence paths must agree and bind into the checkpoint and safe-to-close chain. Observer schema v8 and the independent historical verifier agreed on one live EC2 phone task on 2026-09-02, closing H3's single-run feasibility gate without changing the guarded-inference limitation.

Reason: A later `thread/read` loses the request and resolution events. A subscribed second App Server client can observe `item/commandExecution/requestApproval`, `serverRequest/resolved`, both exact command lifecycles, and `turn/completed`, which is stronger than completed history and prevents stopping verification after only the canary. The public protocol still does not reveal the decision payload or responder connection identity, however, so even the combined result supports only `request observed -> request resolved -> exact command succeeded`, not “this phone user tapped Approve.” Root-owned observation protects the evidence from the workspace, but the provider daemon and workload still share the `lift` identity; provider-service identity separation remains a pre-alpha gate, and provider-supported audit evidence is required for production-grade decision attribution.

### D-028: Codex mobile Add Folder is a folder binding, not a project assignment

Decision: Model the tested Codex mobile `Add new folder` path as `folder-bound-project-unassigned`. Keep the App Server-registered Lift project as a separate readiness fact; do not claim the mobile task is project-bound when its provider record has `projectId: null`. A phone proof must be the only post-baseline task for the exact canonical `cwd`, retain `projectId: null` across list, read, and resume, and return the exact runtime root from `thread/resume`. Its two completed commands must have source `unifiedExecStartup` and decode to exactly `[/bin/bash, -lc, EXPECTED_INNER]`; Lift hashes and compares the inner commands, rejects any shell or argument variation, and still requires the independent approval observer, unchanged approval guard, empty active rules, exact item order, and no additional tool or mutation.

Reason: The live mobile task created after `Add new folder` used the intended EBS-backed `cwd` but no experimental project assignment. Treating the registered server project ID as the task's project ID caused a false rejection. Treating `cwd` alone as sufficient would be too permissive, so the compatibility path is explicit, versioned, and fail-closed around the complete observed task and command envelope.

### D-029: Complete Land before dashboard polish or a second provider

Decision: Complete the conflict-safe Land path on the generated disposable fixture before dashboard polish or a second provider: freeze cloud writers, create and restore-test the final cloud checkpoint, capture returning local state privately, merge in an isolated Lift worktree, transactionally apply a clean result or preserve every conflicting side, acknowledge locally, return the ownership lease, and retain the complete session ledger. The control path is implemented and unit-tested; one clean live EC2 execution and one separate deliberate live conflict passed on 2026-09-02. That is enough to accept the generated-fixture Land vertical slice. The next product boundary is D-030's explicit real-workspace manifest review, while conflict-resolution, additional interruption, offline-helper, and repeat evidence continue.

Reason: The provider path has passed its single-run feasibility gate, while the product promise is still only half a loop. Completing clean return and deliberate conflict preservation removes the largest remaining work-preservation risk and tests the product's differentiated value more directly than adding UI polish, another provider, or broader infrastructure.

### D-030: Phase 0 capture remains fixture-only until explicit manifest review exists

Decision: The current capture harness must refuse any workspace that lacks the exact generated disposable-fixture marker before it creates a private ledger. It may include only the fixture's known untracked content and the one ignored path declared by that marker. Do not relax this guard to test a real repository. Replace it with a separately reviewed production discovery and explicit include/exclude manifest flow.

Reason: Discovery is not permission to transfer. The spike's fixed fixture proves mechanics without creating a path that could silently upload secrets, arbitrary ignored files, or a user's real workspace before the product has a reviewable transfer boundary.

### D-031: Land is one product action backed by a resumable transaction

Decision: Present Land as one user action—`Bring changes back`—with three meaningful user states: returning safely, waiting for the original computer, or needs review with nothing overwritten. Internally, implement it as explicit durable phases for cloud freeze, final checkpoint, exact import, local capture, reconciliation, transactional apply, acknowledgement, and lease return. Decompose and test those phases independently, but do not expose infrastructure steps or require the user to orchestrate them.

Reason: Small independently recoverable transitions make data safety and retries tractable, while exposing those transitions as setup work would destroy the product's core promise. Engineering decomposition is a reasoning and reliability technique, not a constraint on the optimal architecture or a burden shifted to the user.

### D-032: The EBS Land record is the cloud write authority and `C` is immutable

Decision: Persist the cloud-side ownership record on the encrypted workspace volume and write `FREEZE_REQUESTED` before stopping the provider-neutral workload. The generic runner must hold the same lifecycle lock and prove `CLOUD_PRIMARY` from that record immediately before activation. After the record enters `LANDING`, retries may only advance the same monotonic operation through `CLOUD_FROZEN`, one exact `land-final` checkpoint, local acknowledgement, and `ACKNOWLEDGED`; they may not create another final cloud state or restart a workspace writer.

Bind the one final `C` to its complete checkpoint and Git-history ref maps, hashes, exact S3 object keys and version IDs, and successful independent restore test. Download those exact object versions outside the project, verify them in a private quarantine, and publish only absent-or-identical allowlisted refs into the local ledger. Return the lease to `LOCAL_PRIMARY` only after a clean local result and receipt produce a canonical acknowledgement for that exact `C`. A conflict remains `LANDING` with both sides preserved and no acknowledgement. Stop compute only after acknowledgement; cleanup failure may remain pending without revoking the completed local return.

Reason: Controller state can be interrupted and compute can reboot. An EBS-resident write fence prevents a stale controller or systemd restart from creating a second writer, while one immutable recovery identity prevents retries from silently recapturing a different cloud tree. Exact-version quarantine and acknowledgement bind the state that was restored locally to the state that remains recoverable in the cloud. Cleanup belongs last because cost recovery must never be allowed to weaken work recovery.

Evidence: On 2026-09-02, live founder fixture run `p0-20260901083520-4fee` sealed `0004-land-final` at commit `4bba13ff328a41dba0c898023e0d26cf3c31249c`, tree `df3bcde602bd34463dc70ffeb549bc4ae242d9ee`, and restored its exact versioned S3 bundle and manifest. The first attempt stopped safely at `FINAL_CHECKPOINT_DURABLE` on a `/run` parent-directory mode mismatch. After the permission fix, the same operation reused the same `C`, produced `APPLIED` merge `444b397a5ced2a0ba7d7b6e3b888f7a694523d9e`, receipt `da72f1ab6e81572dfc58501f1437af9835d1de1d`, and acknowledgement `d2e97376dadaa3e0aadd3af3c5c9545c28c9ec246b7deccfb382110b91e02bbc`; the guest reached `ACKNOWLEDGED`, ownership became `LOCAL_PRIMARY`, and compute stopped.

Fresh disposable run `p0-20260902183748-a7b1` then sealed and restored `0002-land-final` at commit `722adcffd8ebba70fb222cfbb1f749b0f5e479bc`, tree `3aa8260a33ec8e8c50b8f277aa2118fd8b88770b`, after exact same-file local/cloud divergence. It returned `NEEDS_REVIEW`; both ownership records stayed `LANDING`; the original local workspace and Git state were exact; private stages preserved baseline, local, and cloud; no apply journal, receipt, acknowledgement, lease return, or cleanup was produced; the runner fence rejected activation; and a repeated Land returned `changed: false` without changing state, events, refs, operation evidence, or either side. This accepts the generated-fixture Land core, not offline-helper, arbitrary-workspace, conflict-resolution UI, H6, or launch evidence.

### D-033: The project-centric cloud workspace is the product north star

Decision: Define Lift as the persistent cloud workspace where developers and user-chosen AI agents work together from any device. Treat the workspace as the durable product object, independent of any laptop, phone, provider conversation, agent, team member, or compute instance.

Reason: Laptop-independent handoff is a compelling first use, but provider labs can bundle cloud agents and user-scoped cloud computers. A project-centric workspace can remain valuable across providers, participants, and devices and can accumulate environment, service, policy, provenance, and recovery state that no single agent conversation owns.

Scope: This expands the product north star without changing the current implementation or Phase 0 evidence boundary. The authoritative product model is [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md).

### D-034: Lift Off remains the first indispensable workflow, not the entire product boundary

Decision: Preserve the complete local-to-cloud-to-phone-to-local handoff and `safe to close` contract. Treat Lift Off as one way to create or update a durable workspace alongside GitHub-created and empty cloud-native workspaces.

Reason: Active local state remains a differentiated, painful entry problem and proves Lift's most important continuity and recovery primitives. Requiring every future workspace to originate locally would unnecessarily limit cloud-native projects and teams.

### D-035: Mobile readiness includes launching new agent tasks

Decision: Where a provider supports it, first-class laptop-independent compatibility requires the user to launch a completely new task from the provider's phone application into the correct Lift workspace after the laptop is offline. Continuing only a process started before Lift Off is an incomplete capability.

Reason: The workspace, not the laptop relay or one immortal process, must remain the durable execution destination. Mobile initiation turns phone access from monitoring into a genuine command surface.

### D-036: Multi-agent operation is a core capability with user-configurable execution modes

Decision: Support multiple agent tasks in one workspace. Let the user or workspace policy choose shared, isolated, or read-only execution per task. Do not require every agent to use a Git worktree.

Reason: Many users want agents to see and build on the same uncommitted state immediately. Mandatory isolation would make ordinary collaboration feel like branch management. Other tasks require stronger noninterference, so isolated worktrees or copy-on-write environments remain available rather than universal.

Shared-mode safety: Create a recoverable pre-run checkpoint, attribute commands and observed file changes, detect overlapping writes, provide pause and stop controls, retain prior versions, and keep an append-only change journal. Do not claim arbitrary shell writes can always be prevented or silently resolve collisions.

### D-037: Internet, browser, and computer use are workspace capabilities

Decision: Treat controlled outbound internet, headless Chromium, visible browser observation, secure user takeover, persistent project-scoped browser identity, and visual computer use as required product-north-star capabilities. Stage them after the first safe coding handoff rather than treating them as a separate general-computer product.

Reason: Agents cannot complete many development, testing, authentication, research, and operational tasks through files and a terminal alone. These capabilities increase the workspace's usefulness while remaining project-scoped.

Security boundary: Do not migrate a personal browser cookie database, password manager, keychain, or full personal profile. Keep browser identities encrypted, revocable, scoped, excluded from project Git and ordinary Land output, and isolated across workspaces and unrelated agents.

### D-038: GitHub is the source and review backbone, not a workspace prerequisite

Decision: Allow workspace creation from an active local folder, GitHub, or an empty reviewed template. Use GitHub for repository distribution, identity, permissions, branches, pull requests, and explicit sanitized publication without requiring a GitHub repository to use Lift.

Reason: GitHub is the strongest collaboration backbone for cloud-native and team workspaces, while a GitHub clone omits dirty, untracked, approved ignored, environment, service, browser, and task state. Lift should complement GitHub before replacing any Git hosting responsibility.

### D-039: Provider-native applications remain preferred agent surfaces while Lift owns workspace control

Decision: Preserve provider applications as the preferred surfaces for agent conversation, notifications, approvals, and mobile task launch. Lift may provide workspace and task management from mobile or web, including health, participants, modes, permissions, activity, cost, snapshots, stop, and recovery, without building a proprietary coding agent or requiring a replacement chat.

Reason: Users should keep familiar provider workflows while Lift owns the provider-neutral workspace layer. Cross-provider workspace management is distinct from recreating provider conversation products.

### D-040: Solo first, multiplayer architecture, team expansion after repeat use

Decision: Continue validating the first product with one agent-heavy developer and one workspace. Architect workspace identity, membership, task modes, provenance, secrets, browser contexts, and recovery so multiple agents and later human collaborators fit the same model. Add team-lite collaboration only after solo repeat use and payment are observed.

Reason: Multi-agent and team work are central to the platform thesis, but enterprise administration would obscure the first behavioral test. The product can preserve the larger architecture without making teams a Phase 0 requirement.

### D-041: Provider-owned agent computers are replaceable workspace participants

Decision: Design the durable Lift workspace so an agent may execute either inside a Lift-hosted runtime or, where a supported integration exists, on its provider's own cloud computer. In the latter case, the provider computer receives a scoped task view or attachment and returns attributable changes and results; it never becomes the canonical owner of the project.

Reason: Cloud compute, persistence, browsers, mobile launch, and concurrent agents are rapidly becoming bundled agent capabilities. Lift cannot depend on reselling those capabilities. Its durable role is the project-centric state, environment, permissions, participants, provenance, coordination, and recovery layer shared across providers.

Boundary: Do not claim a provider-hosted agent has joined a live Lift workspace unless the integration can authenticate the task, bind the correct project state, enforce the declared mode and grants, report sufficient provenance, and reconcile safely. A GitHub branch or pull request is an external result, not proof of live shared-workspace participation.

Failure condition: If one provider or GitHub supplies a superior persistent team-owned project workspace with local-state import, outside-agent participation, shared and isolated execution, permissions, project browser and secret state, provenance, and recovery, Lift's standalone differentiation may disappear.

## Pending decisions

### P-001: Hosted versus BYO cloud first

Default hypothesis: Lift-hosted infrastructure for the fastest consumer setup.

Evidence needed: trust objections, compute economics, and willingness to connect an AWS account.

### P-002: Codex direct Remote promotion

Updated hypothesis: the current experimental CLI daemon and provider pairing URL can connect ChatGPT mobile directly to a persistent Linux workspace. A real Ubuntu EC2 run now passes direct pairing and phone task execution against the exact EBS-backed workspace. A fresh challenge issued before the founder shut down the Mac was satisfied from the phone, and later Mac reboot timestamps strongly corroborate that the computer was off; this remains human-attested evidence, not cryptographic device attestation.

State evidence from the same run includes immutable Lift-private Git checkpoints `0001` and `0002` bound to the exact encrypted EBS volume. Their bundles and manifests were uploaded as checksummed, versioned private S3 objects and restored from the exact versions into fresh repositories with commit, tree, history-ref, and evidence-file verification.

A subsequent EC2 stop/start changed the guest boot ID. The exact encrypted workspace volume reattached; checkpoint `0002`'s commit and bundle and both proof files recovered; the provider-neutral systemd runner automatically started healthy; and the exact Codex Remote environment ID was preserved. Live server-side verification read back the repaired native project and exact workspace root. On 2026-09-02, a brand-new phone task then bound to the exact folder with `projectId: null`, completed the controlled approval and proof turn, and entered immutable checkpoint `0003`, which restored successfully from exact versioned S3 objects. Fresh live evaluation reported every safe-to-close gate true. Generated fixtures later completed the separate clean and deliberate-conflict live Land evidence recorded under D-032.

Evidence still needed: repeated independent laptop-off and Land runs, network interruption and recovery, revocation, compatible sandbox configuration, provider-policy review, provider-service identity isolation, explicit real-workspace manifest review, repeated live conflicts, broader interruption coverage, conflict-resolution UX, and automatic offline-helper continuation. The observed founder runs do not make Codex direct Remote launch-ready.

### P-003: State transfer implementation

Options include content-addressed encrypted objects, an rsync-like protocol, Git bundle plus file delta, or a combination.

Decision criteria: correctness, speed on dirty repositories, explainability, and recovery.

### P-004: Local edits after handoff

Default hypothesis: show that the workspace is cloud-primary, detect any local divergence, and reconcile through a temporary worktree rather than silently overwriting or hard-locking local files.

Evidence needed: actual user behavior while a workspace is active in the cloud.

### P-005: Product name

`Lift` is a working name. Trademark, domain, package-name, and search-competition checks remain required before a public brand launch.

### P-006: Production runtime after EC2

Default hypothesis: evaluate Daytona VM sandboxes on BYOC AWS after the EC2 prototype proves repeat usage.

Evidence needed: utilization, wake latency, snapshot reliability, vendor risk, unit economics, and the operational cost of remaining directly on EC2.

### P-007: Remote workload recipe format

Default hypothesis: use a declarative, versioned recipe with executable and arguments represented separately, explicit persistent paths, requested secret references, network policy, restart behavior, and optional interactive authentication.

Evidence needed: Codex remote control, Claude Code Remote Control, and one unrelated CLI workload all running through the identical process supervisor without provider-specific branches.

### P-008: Provider connection credential placement

Default hypothesis: keep reusable provider credentials in a dedicated encrypted per-user vault or approved encrypted workspace state; store only nonsecret status and identifiers in the control plane.

Evidence needed: officially supported authentication behavior for each provider, reauthentication frequency, revocation behavior, snapshot-exclusion guarantees, and provider terms.

### P-009: Dashboard and desktop-helper boundary

Default hypothesis: a small signed desktop helper handles local discovery and transfer while a web dashboard owns Connections, Workspaces, Lift Off, status, and lifecycle controls.

Evidence needed: browser folder-access limitations, background transfer behavior, auto-update requirements, and the minimum native surface needed to make the journey feel like one application.

### P-010: Optional GitHub return mode

Default hypothesis: the personal default remains local Land. Later, an explicitly connected GitHub account may publish a sanitized session branch and pull request for users who want remote review or repository-policy enforcement.

Evidence needed: user demand, permission scope, behavior for forks and protected branches, CI cost, and a reliable guarantee that ignored or workspace-only content can never enter the remote branch.

### P-011: Default multi-agent execution mode

Default hypothesis: shared mode for coordinated solo work, with an obvious per-task choice for isolated or read-only execution and a workspace policy that teams can tighten.

Evidence needed: actual overlap frequency, user understanding, recovery outcomes, and whether users prefer immediate shared state over review-before-integration.

### P-012: First browser capability

Default hypothesis: ship headless Chromium for development testing before visible browser observation, secure takeover, and persistent authenticated profiles.

Evidence needed: design-partner tasks blocked by browser absence, required login flows, credential boundaries, runtime cost, and support burden.

### P-013: GitHub-created workspace authorization

Default hypothesis: use a narrowly scoped GitHub App for repository selection, short-lived credentials, permission-derived team access, and explicit branch or pull-request publication.

Evidence needed: local-only adoption, GitHub organization approval friction, fork and protected-branch behavior, and the minimum permission set for useful team-lite workspaces.

### P-014: External agent-computer attachment contract

Default hypothesis: use supported provider APIs or a narrow authenticated workspace gateway to issue a short-lived task identity and scoped state view, negotiate enforceable capabilities, ingest attributable activity, and reconcile checkpointed results. Treat Git-only export as asynchronous integration rather than shared execution.

Evidence needed: which providers permit external workspace targets, filesystem attachment, task APIs, event/provenance export, scoped credentials, cancellation, and reliable result recovery; latency and conflict behavior when several execution locations participate; and whether customers actually use multiple provider computers on one project.
