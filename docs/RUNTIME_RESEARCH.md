# Runtime and Remote-Control Research

Last updated: 2026-09-02

## Executive decision

Build the first Lift slice on one single-tenant Ubuntu EC2 virtual machine with an encrypted gp3 EBS volume. Use one provider-blind workload runner and validate it with a user-owned Codex remote-control recipe.

This decision optimizes for the fastest credible test of Lift's core promise:

> Move a real, dirty local workspace to a persistent cloud computer and continue controlling the user's existing agent without asking the user to adopt a new interface.

The first implementation is not a commitment to EC2 as the permanent production runtime. It deliberately chooses a complete Linux machine while the product risk is continuity and provider compatibility rather than machine density.

The current runtime evidence, failure sequence, security boundary, accepted generated-fixture Land lifecycle, and next real-workspace manifest slice are summarized in [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Product-boundary finding

Lift should not build a mobile chat application, terminal application, approval interface, notification system, or coding agent.

The agent provider already owns those interaction surfaces. Lift should own:

- discovery and review of local workspace state;
- transfer of committed, uncommitted, and selected untracked state;
- provisioning and waking the cloud workspace;
- reconstruction of the toolchain;
- installation and lifecycle of supported agent hosts;
- a generic process supervisor that runs the user's provider-owned remote command without speaking its protocol;
- durable storage, snapshots, stop, delete, and recovery;
- safe cloud-to-local return.

This keeps the user's workflow unchanged. The user continues working in Codex, Claude, or another supported provider application while Lift changes where the files and execution live.

## Provider-owned remote compatibility

### Codex

The stable, documented Codex remote path is:

```text
ChatGPT mobile
    -> ChatGPT desktop app on an awake Mac or Windows host
    -> SSH connection
    -> Codex App Server and workspace on the Lift Linux host
```

The ChatGPT desktop app can connect to projects on an SSH host. It starts the remote Codex App Server over SSH, and file and shell operations happen on the SSH host. However, the documented phone setup still pairs the phone with an awake Mac or Windows desktop host. Mobile setup cannot currently be initiated from the Codex CLI or IDE extension according to the official guide.

Implication: the stable path proves that Codex can work against a Lift workspace, but it does not prove the full laptop-off promise because a desktop relay remains online.

The locally installed `codex-cli 0.146.0`, inspected on 2026-08-31, also exposes experimental commands for a remote-control daemon and manual pairing:

- `codex remote-control start`
- `codex remote-control pair`
- `codex app-server daemon bootstrap --remote-control`
- `codex app-server daemon enable-remote-control`

These commands create a plausible direct Linux-host-to-phone path, but the official product documentation does not yet establish it as a supported production workflow. The App Server WebSocket transport is explicitly experimental and unsupported for production. A founder feasibility spike has now exercised the path on real Ubuntu EC2; that observed behavior does not authorize Lift to advertise headless Codex mobile support until lifecycle and provider-policy gates pass.

The local feature listing and command availability are not a sufficient compatibility guarantee. CLI behavior can lead public documentation, be gated by account rollout, or change without a stable third-party contract. The spike must record the exact CLI, desktop, and mobile versions and distinguish observed behavior from documented support.

Official references:

- [Codex Remote](https://learn.chatgpt.com/docs/remote)
- [Codex remote connections](https://learn.chatgpt.com/docs/remote-connections)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)

### Claude Code

Claude Code Remote Control can connect the Claude web or mobile client directly to a Claude Code process running on a machine. The remote process retains access to that machine's filesystem, tools, MCP servers, and project configuration. It communicates through outbound HTTPS rather than an inbound public listener.

The practical Lift path is:

```text
Claude mobile or claude.ai/code
    -> Anthropic relay
    -> Claude Code Remote Control on the Lift Linux host
    -> persistent Lift workspace
```

Important constraints:

- the remote process must remain running;
- a full Claude subscription login is required;
- API-key authentication and inference-only setup tokens cannot establish Remote Control;
- the cloud host must retain the user's approved login state;
- extended network loss can end the remote-control process.

This makes Claude the cleaner documented laptop-off integration, even though Codex remains the chosen first implementation because it is the founder's available provider.

Official references:

- [Claude Code Remote Control](https://code.claude.com/docs/en/remote-control)
- [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web)

## Runtime-platform comparison

| Platform | Persistence model | Host flexibility | Agent-client fit | Decision |
| --- | --- | --- | --- | --- |
| AWS EC2 + EBS | EBS files survive stop and start; RAM and processes do not | Full Ubuntu VM, root, PTYs, Docker, arbitrary daemons | Works with Codex over SSH; suitable for testing headless pairing; suitable for Claude Remote Control | Use for the first slice |
| Daytona VM sandboxes | Persistent files plus VM pause, resume, and snapshots | Strong PTY, SSH, preview, policy, and BYOC capabilities | No native agent-mobile bridge, but can host provider processes | Evaluate as the managed production runtime |
| Fly Machines + volumes | Machine lifecycle plus persistent local volumes | Full machine behavior and useful API | Can host provider processes; lifecycle and recovery remain Lift's responsibility | Credible lean alternative |
| Cloudflare Sandbox/Containers | Local filesystem and processes are lost on sleep or replacement; persistence requires external backup and restore | Strong short-lived containers, terminals, and edge routing | No provider-native advantage | Use for control-plane or ephemeral work, not authoritative workspace state |
| ECS/Fargate/EKS | Task storage is ephemeral unless external persistent storage is mounted | Good for scheduled or stateless containers; awkward as a personal computer | No provider-native advantage | Do not use for the first workspace runtime |
| Modal Sandbox | Short default and maximum lifetimes; longer work requires snapshots | Strong bounded compute API | Better for finite agent jobs | Do not use as the living workspace |
| E2B | Pause and resume can preserve filesystem and process state, subject to plan and duration constraints | Strong sandbox and terminal API | No provider-native advantage | Re-evaluate if managed sandbox speed becomes important |
| GitHub Codespaces | Workspace files persist, but environments idle-stop and remain GitHub-centric | Mature development environments | Does not own the local dirty-state transplant or provider mobile bridge | Substitute, not preferred substrate |
| Coder/devcontainers | Good workspace control plane and packaging | Strong enterprise and IDE integration | Does not itself supply the provider mobile bridge | Potential later control-plane component |
| Firecracker/microVMs | Can provide strong isolation and snapshots when fully engineered | Maximum control with major scheduler, storage, network, and recovery work | Neutral | Consider only after scale justifies owning infrastructure |

## Why EC2 first

EC2 with EBS gives the prototype the properties of a real computer:

- an ordinary Linux filesystem and home directory;
- root access and arbitrary toolchains;
- PTYs and long-running background processes;
- Docker and browser automation when needed;
- a durable block device that survives stopping the compute;
- simple snapshot and recovery primitives;
- few provider-specific restrictions on authentication flows.

Recommended prototype shape:

- one Ubuntu x86_64 VM per user or workspace;
- `t3.medium` or an equivalent 2-vCPU, 4-GiB instance for compatibility;
- one separate encrypted 30-50 GiB gp3 data volume for workspace and approved agent state;
- encrypted snapshots before risky lifecycle operations;
- no public application listeners;
- AWS Systems Manager for administration without inbound ports;
- restricted SSH through a mesh network or carefully scoped path only when Codex Desktop requires it;
- `systemd` user services for provider daemons and declared development processes;
- cloud-init or an immutable base image for repeatable bootstrap.

Stopping an EC2 instance removes compute charges but does not preserve RAM or running processes. Attached EBS state remains billable and persistent. Lift should promise semantic continuity after a stop, not memory-level process continuation.

### Phase 0 runtime evidence recorded on 2026-09-01 and completed on 2026-09-02

- A real single-tenant Ubuntu EC2 instance ran Codex Remote against the intended workspace on a separate encrypted EBS volume.
- ChatGPT on the founder's phone paired directly with that environment and controlled the correct cloud `cwd`; the data path did not require ChatGPT Desktop as a relay.
- A fresh unpredictable challenge was armed immediately before the founder reported shutting down the Mac. The exact nonce, source, and cloud `cwd` were then written into the EBS workspace from the phone, and later Mac reboot timestamps strongly corroborated the order of events. This is human-attested founder evidence, not cryptographic attestation that the Mac was powered off.
- Immutable Lift-private Git checkpoints `0001` and `0002` were created against the exact encrypted EBS workspace. Checksummed bundles and manifests were stored as versioned private S3 objects, downloaded by exact version, and restored into fresh repositories with commit, tree, history-ref, and evidence-file verification.
- One EC2 stop/start changed the guest boot ID while the exact encrypted workspace EBS volume reattached. Checkpoint `0002`'s commit and bundle and both proof files recovered, the provider-neutral systemd runner automatically started healthy, and the exact Codex Remote environment ID was preserved. After server-side native-project reconstruction, a fresh post-baseline phone task passed exact folder/runtime binding, guarded approval observation, proof, following checkpoint `0003`, exact-version restore, and fresh safe-to-close evaluation. Separate provider-service identity and credential isolation are pre-alpha gates.
- The restart exposed that daemon liveness and Remote environment persistence do not reconstruct provider semantic state. With no native project registered, new tasks used projectless paths outside Lift's write boundary. The recipe-scoped connector now prepares and reads back the exact server project/root, while readiness separately checks Remote and controller prerequisites.
- Server project registration did not make that project visible in the phone picker. The passing task used the provider's `Add new folder` path, had the exact canonical `cwd`, and retained `projectId: null`; this is folder continuity, not controller project assignment.
- The final passing runtime used the managed Codex CLI and App Server `0.152.1`; the guest-bootstrap metadata still records the originally installed CLI `0.152.0`.
- The approval observer and historical verifier agreed on the request, resolution, two exact command lifecycles, and completed turn. The provider protocol still omits selected decision and responder identity, so the approval claim remains a guarded founder-only inference.
- The runtime remains unsuitable for external alpha until provider credentials are isolated from the workspace Unix identity and the mutable AWS CLI/Codex installer downloads are replaced with signed or content-addressed inputs.
- One live generated-fixture Land returned cleanly from EC2/EBS through exact versioned S3 recovery to the Mac: exact `C` was imported and applied, both sides acknowledged it, ownership returned to local, and compute stopped afterward.
- A separate fresh generated-fixture Land deliberately conflicted on one file and stopped at `NEEDS_REVIEW`/`LANDING` with exact `B/L/C`, untouched local state, a fenced runner, no acknowledgement or cleanup, and an idempotent no-op retry.

Official references:

- [EC2 stop and start behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html)
- [EBS persistence](https://docs.aws.amazon.com/ebs/latest/userguide/EBSFeatures.html)
- [AWS Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [ECS storage options](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html)

## Why Cloudflare is not the workspace disk

Cloudflare Sandbox and Containers are useful for isolated execution, terminals, preview routing, and edge control-plane work. Their local disk and running process state are not currently the correct source of truth for a living personal workspace. A sleeping or replaced container can lose that local state, and durable behavior requires copying state to an external store and restoring it later.

That reconstruction model can support replaceable compute and is compatible with Lift's north star when external persistence, identity, and recovery are engineered correctly. It is not the fastest first authoritative workspace substrate: Lift would need to build and prove the durable filesystem, checkpoint, restore, writer-fencing, and failure semantics outside the container before testing the user experience, while EC2 plus EBS already supplies the required block-storage boundary.

Possible later Cloudflare roles:

- Lift API and authentication edge;
- workspace metadata and lifecycle requests;
- authenticated preview routing;
- short-lived helper jobs;
- R2-backed recovery objects.

References:

- [Cloudflare Sandbox lifecycle](https://developers.cloudflare.com/sandbox/concepts/sandboxes/)
- [Cloudflare Sandbox backup and restore](https://developers.cloudflare.com/sandbox/guides/backup-restore/)

## Production evolution

Do not rewrite the prototype around a production runtime before users repeat the handoff. Instead, place EC2 behind a runtime-provider interface with operations such as:

```text
createWorkspace
startWorkspace
stopWorkspace
deleteWorkspace
exec
upload
download
snapshot
status
```

After the core experience works, compare:

1. Daytona VM sandboxes on BYOC AWS for managed lifecycle, snapshots, PTYs, SSH, and isolation.
2. Fly Machines for a lower-level machine API with persistent volumes.
3. Continuing on EC2 with a stronger control plane if simplicity and economics remain acceptable.
4. Owned Firecracker infrastructure only after utilization and margin justify the operational burden.

References:

- [Daytona persistence](https://www.daytona.io/docs/en/persistence/)
- [Daytona PTY](https://www.daytona.io/docs/en/pty/)
- [Fly per-user development environments](https://fly.io/docs/blueprints/per-user-dev-environments/)
- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes)
- [E2B persistence](https://docs.e2b.dev/sandbox/persistence)
- [GitHub Codespaces lifecycle](https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle)

## Prototype security constraints

The runtime decision does not authorize copying the user's computer indiscriminately.

- Never copy `.env`, SSH private keys, browser cookies, keychains, or agent tokens automatically.
- Keep the persistent workspace volume separate from reconstructable caches and scratch space.
- Encrypt EBS volumes and snapshots.
- Store provider login state only after explicit user authorization and keep it outside the project tree.
- Prevent workspace access to cloud metadata and control-plane credentials.
- Do not expose Codex App Server or any raw workspace port to a public network.
- Snapshot before stop, provider handoff, or destructive reconciliation.
- Record workspace, instance, volume, manifest, and provider-session identifiers without logging credentials.
- Treat authentication as user-owned and verify provider terms before automating sign-in.

## Last-30-days architecture pass

A focused run on 2026-08-31 collected 45 items across GitHub, Hacker News, Reddit, and X. Reddit became partial after 17 items because of an HTTP 429 response. The community material supports a distinction between durable machines for multi-day work and ephemeral schedulers for bounded jobs, but vendor documentation is the source of truth for platform capabilities.

Run totals:

- Reddit: 17 threads, 1,591 upvotes, 657 comments;
- X: 20 posts, 51,409 likes, 5,852 reposts;
- Hacker News: 6 stories, 148 points, 55 comments;
- GitHub: 2 items, 263,979 stars, 30,175 comments.

Representative comments:

> “I really don’t understand the value proposition of all these agent core computer resources vs just hosting in lambda, ECS, etc. It feels like AWS cannibalizing themselves.” - `r/aws`, 11 upvotes

> “I use fargate + airflow as my agent orchestration and it works great.” - `r/aws`, 4 upvotes

Raw artifact:

`~/Documents/Last30Days/persistent-cloud-workspaces-for-coding-agents-with-phone-access-and-local-to-cloud-handoff-raw-v3-2026-08-31.md`

## Confidence and unknowns

High confidence:

- a normal VM is the fastest first substrate;
- EBS provides the persistence the first slice needs;
- Lift should not recreate provider mobile interfaces;
- provider remote compatibility must remain outside Lift's generic workload runner;
- Cloudflare's current local disk model is not the authoritative workspace filesystem.
- the tested experimental Codex CLI can pair ChatGPT mobile directly to headless Linux, including one real Ubuntu EC2 workspace, and execute against a selected persistent working copy;
- provider-visible working copies should be real directories beneath the persistent remote user home, not symlinks to an external mount.
- exact-version object recovery plus Lift-private Git refs can preserve a cloud checkpoint chain independently of the live working directory.
- one EC2 stop/start can reconstruct the exact EBS-backed workspace and automatically restart the provider-neutral runner while preserving the Codex Remote environment identity.

Requires a spike:

- whether the observed Codex headless pairing and task flow repeats reliably across users, provider releases, and independent laptop-off runs;
- whether the provider permits and sustains the required cloud-host authentication flow;
- which Codex session metadata can be preserved without depending on unsupported internals;
- whether the once-passed fresh post-stop/start phone path repeats reliably and reconnects correctly after network interruption;
- which Ubuntu kernel and `bubblewrap` settings eliminate avoidable sandbox escalation prompts without weakening isolation;
- the smallest safe SSH or mesh-network path needed for the stable desktop-relay fallback.

Requires user validation:

- whether local dirty-state transplant is valuable enough to pay for;
- whether a desktop-relay fallback is acceptable while direct Codex pairing matures;
- whether users prefer Lift-hosted compute or BYO cloud;
- whether stopping compute between sessions feels sufficiently continuous.
