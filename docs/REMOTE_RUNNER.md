# Provider-Neutral Remote Workloads

Last updated: 2026-09-02

## Decision

Lift should not implement a Codex adapter, Claude adapter, or universal agent protocol.

Lift should implement one provider-blind remote workload runner. A reviewed connection recipe installs and starts a long-lived command inside the Lift workspace. If that command implements native remote control, the provider connects it to the provider's existing mobile or web client. Supported recipes are presented through Lift's Connections tab rather than exposed as terminal configuration.

The current repository implementation and the boundary between merged code, active development, passed founder evidence, and target product behavior are summarized in [`CURRENT_STATE.md`](CURRENT_STATE.md).

```text
Lift workspace and generic process supervisor
                    |
          user-owned remote command
                    |
         provider-owned relay protocol
                    |
        provider's existing mobile client
```

This preserves both goals:

- Lift remains technically neutral and does not contain provider protocol code.
- The user keeps the provider's native mobile remote experience when that provider offers one.

## The hard technical boundary

There is no common remote-control protocol currently shared by Codex, Claude Code, and every other coding agent. Lift cannot make an arbitrary agent appear inside Codex's or Claude's mobile application.

Lift can remain neutral because it does not need to speak those protocols. It only starts the provider's own remote-capable command and keeps its filesystem and process available. Authentication, pairing, chat, approvals, notifications, transcripts, and mobile transport remain end to end between the user and the provider.

Neutrality is an internal architecture property, not an excuse to expose setup. Lift's connection manager may know how to initiate a provider-owned browser login, check documented readiness, and recover the command. It does not terminate or reimplement the provider's remote conversation protocol.

An agent without a native phone or web remote mode can still run on Lift, but the user must control it through an interface that agent supports, such as SSH, a generic terminal client, or its own web application. Lift will not manufacture a native mobile connection that the provider does not expose.

## What Lift owns

- workspace discovery and the state manifest;
- local-to-cloud transfer and safe return;
- persistent compute and storage;
- reviewed recipe execution;
- Connections-tab orchestration and reusable connection state;
- generic PTY and process supervision;
- start, stop, restart, health, logs, and exit status at the process level;
- approved persistent directories;
- snapshots and recovery;
- isolation, resource limits, and network policy.

## What the user and provider own

- selection of the agent executable and version;
- credential issuance and provider-side authentication decisions;
- the provider-specific remote protocol and pairing exchange;
- the native mobile, web, or desktop interface;
- conversation and approval semantics;
- provider session identifiers and transcripts;
- model selection, inference, and subscription entitlement;
- whether the provider supports direct headless remote control at all.

## One generic runner contract

The runner deals only with processes and files. It does not expose methods such as `pairCodex`, `resumeClaude`, or `getProviderSession`.

Conceptual interface:

```ts
type RemoteWorkload = {
  id: string;
  install?: ProcessSpec;
  auth?: ProcessSpec;
  run: ProcessSpec;
  prepare?: ProcessSpec;
  readiness?: JsonProcessSpec;
  workingDirectory: string;
  persistentPaths: string[];
  secretRefs: string[];
  networkPolicy: NetworkPolicy;
  restartPolicy: "never" | "on-failure" | "always";
};

type RemoteWorkloadRunner = {
  prepare(workload: RemoteWorkload): Promise<void>;
  start(workload: RemoteWorkload): Promise<ProcessHandle>;
  attach(handle: ProcessHandle): Promise<PtyStream>;
  status(handle: ProcessHandle): Promise<ProcessStatus>;
  stop(handle: ProcessHandle): Promise<void>;
};
```

### Multiple agent tasks

The contract remains provider-blind when Lift runs several agents. One agent task creates one workload instance and process handle; the workspace task manager, not the runner, decides how those instances relate to files and to one another.

- In **shared** mode, several workload instances use the same working directory. No Git worktree is required. Lift adds a pre-run checkpoint, task identity, observable command and file attribution, overlap detection, pause and stop controls, and preserved recovery versions.
- In **isolated** mode, each instance receives a worktree, branch, overlay, or copy-on-write root and later produces an explicit integration result.
- In **read-only** mode, the runtime enforces nonmutation rather than trusting an instruction in the prompt.

The runner never treats an agent as a permanent owner of a worktree. Execution mode is selected per task or workspace policy, and all workload instances remain subordinate to the cloud workspace ownership lease and Land writer fence.

Provider conversation traffic remains opaque. For a first-class connection, the connection recipe presents provider-owned browser or device authentication through the dashboard and consumes only explicitly declared nonsecret readiness signals. `lift attach` can expose the raw PTY for development or unsupported custom recipes, but it is not part of the supported consumer journey.

## User-controlled recipe

Conceptual manifest:

```yaml
version: 1
id: my-remote-agent
install:
  executable: npm
  arguments: [install, --global, my-agent-cli@1.2.3]
auth:
  executable: my-agent
  arguments: [auth, login]
run:
  executable: my-agent
  arguments: [remote]
prepare:
  executable: provider-connector
  arguments: [register, --workspace, /workspace]
readiness:
  executable: provider-connector
  arguments: [status, --workspace, /workspace]
  assertions:
    ready: true
    workspace: /workspace
workingDirectory: /workspace
persistentPaths:
  - /home/lift/.config/my-agent
secretRefs: []
networkPolicy:
  outbound: provider-default
restartPolicy: on-failure
```

The actual schema should represent executables and arguments separately, reject paths outside approved workspace and home-state roots, and never interpolate an unreviewed shell string.

Before first execution, Lift displays:

- installation source and pinned version;
- executable and arguments;
- requested persistent paths;
- requested secret references;
- outbound network policy;
- restart behavior;
- whether the recipe requests an interactive authentication step.

Lift signs and curates recipes for first-class Connections. A provider can publish one, or an advanced user can approve a custom recipe. Curating a recipe does not make Lift a remote-protocol adapter because the runner behavior remains identical.

For first-class providers, the recipe also declares a uniform connection lifecycle:

- how Lift opens provider-owned authentication without a terminal;
- which encrypted paths preserve reusable login state;
- how the native remote command starts;
- what nonsecret signal establishes remote readiness;
- how reauthentication and process recovery work;
- whether a provider-owned deep link or session URL may be shown.

`run` establishes the long-lived workload. An optional idempotent `prepare` step runs after that process is reachable and reconstructs durable provider-owned semantic state, such as registering the exact native project through a documented or inspected provider API. Preparation must not require transient Remote connectivity or a paired controller. An optional `readiness` step emits normalized JSON and performs those live checks in addition to verifying workspace identity. The supervisor treats these signals differently:

- failed liveness increments the process failure threshold and may restart the workload;
- failed readiness keeps the process running, reports `ready: false`, and blocks `safe to close`;
- neither step may broaden writable paths or silently copy credentials;
- connectors must use provider-owned APIs and must never patch a provider database directly.

## Codex as the first recipe

Codex is the first real workload used to validate the runner, not a special integration in the Lift core.

The historical local `codex-cli 0.146.0`, inspected on 2026-08-31, exposed candidate experimental commands:

```text
codex app-server daemon bootstrap --remote-control
codex remote-control start
codex remote-control pair
```

A Codex recipe can install the CLI and declare the daemon start command. The managed runtime used for the final passing run pins Codex CLI and App Server `0.152.1`; original guest-bootstrap metadata still records the earlier CLI `0.152.0`, so live managed identity—not the historical bootstrap field—is authoritative. The recipe-scoped connector uses the live Unix-domain App Server control socket. Its preparation command idempotently registers the exact Lift workspace as a native Codex project and configures trust for only that path without requiring Remote or a controller; its separate readiness command reads that project back and requires connected Remote state plus paired-controller presence. The connector's nonsecret workspace-binding and create-idempotency record lives outside the project tree at `/home/lift/.codex/lift/<workspace-id>/codex-project.json`, with `0700` parent directories and a `0600` file. Its `project/*`, `config/value/write`, and Remote status/client calls come from the experimental version-pinned App Server schema, not a stable documented production contract. The connector validates that schema and all relevant versions before writing provider state, has no public listener or direct-SQLite fallback, and does not interpret Remote conversation messages.

A nonempty paired-client result proves only that a controller is registered. It does not prove that the phone is currently reachable, that the client is recent, or that an approval request can complete. Those remain separate end-to-end gates. In the finished product, the Connections tab must present the provider-owned login and any supported pairing flow without asking the user to open a terminal.

Desired flow:

```text
ChatGPT mobile
    -> OpenAI-owned Remote relay
    -> Codex-owned daemon on Ubuntu EC2
    -> Lift-owned persistent workspace
```

This path remains experimental. One founder-only Phase 0 run now verifies direct phone execution against a real Ubuntu EC2 workspace and strongly corroborates a laptop-off sequence through a fresh challenge/proof exchange and Mac reboot timestamps. That evidence is human-attested rather than cryptographically device-attested. A subsequent EC2 stop/start changed the guest boot ID while preserving the exact EBS workspace, earlier checkpoints and proof files, and exact Codex Remote environment ID. It also exposed a false-positive readiness bug: the daemon was live but no native Codex project was registered, so new mobile tasks fell into projectless paths outside the service's narrow write boundary. The version-pinned connector now registers and reads back the exact project, and the generic runner distinguishes `healthy` from semantic `ready`. After that repair, one fresh post-baseline phone task passed exact folder/runtime binding, guarded approval observation, proof, following checkpoint, exact-version restore, and fresh safe-to-close evaluation.

The same generated fixture subsequently completed one live clean Land round trip on 2026-09-02. Once the guest entered `LANDING`, the provider-blind runner remained fenced from restarting; immutable `0004-land-final` was restored and imported by exact S3 object version on the Mac, reconciliation returned `APPLIED`, the guest accepted the exact acknowledgement, the lease became `LOCAL_PRIMARY`, and EC2 stopped. An initial `/run` record-directory permission failure was safely resumed from the same already durable final checkpoint and then fixed and tested.

Fresh generated-fixture run `p0-20260902183748-a7b1` then passed the deliberate same-file conflict path. Land froze the provider workload, sealed and restore-tested immutable `0002-land-final`, returned `NEEDS_REVIEW`, kept both controller and guest ownership at `LANDING`, left the original local fixture untouched, retained independently recoverable local and cloud sides, kept the runner fenced, and retained compute. Retrying Land reused the exact conflict evidence and reported `changed: false`. This is founder-only fixture evidence, not H6 or private-alpha acceptance. Separate provider-service identity and credential isolation, production isolation, network recovery, revocation, broader repetition and interruption coverage, arbitrary real-workspace capture, automatic offline-helper wake, conflict-resolution UI, the customer UI/helper, the no-terminal journey, and provider-policy gates remain open. The official OpenAI documentation currently describes phone Remote through an awake Mac or Windows desktop host and separately documents the desktop app starting Codex App Server on an SSH host.

The stable fallback is:

```text
ChatGPT mobile
    -> ChatGPT desktop on awake Mac or Windows
    -> SSH
    -> Codex on the Lift workspace
```

That fallback proves the neutral workspace and Codex execution, but not the laptop-off promise.

Official references:

- [Codex Remote](https://learn.chatgpt.com/docs/remote)
- [Codex remote connections](https://learn.chatgpt.com/docs/remote-connections)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)

## Codex recipe spike

1. Provision the generic Ubuntu EC2 and EBS workspace.
2. Apply a reviewed Codex recipe through the same runner used for any command.
3. First prove provider authentication manually through an internal PTY during the feasibility spike.
4. Start the provider's remote-control daemon.
5. Confirm the unmodified pairing output and determine whether it has a supported nonterminal presentation.
6. Pair ChatGPT mobile without Lift parsing the exchange.
7. Register and read back the exact native project through the pinned provider API without making registration depend on Remote or controller presence.
8. Require a fresh live runner and native-Remote readiness result.
9. Start a brand-new post-baseline phone task at the declared controller-binding level and verify its actual project ID, working directory, and runtime roots. The observed path is exact-folder binding with `projectId: null`, not controller assignment to the server project.
10. Complete a controlled approval request and response through the native provider UI.
11. Create and restore-test a durable checkpoint containing the phone and approval evidence, then revalidate live readiness before reporting safe-to-close.
12. Disconnect the provisioning laptop.
13. Restart the supervised process and test provider reconnection.
14. Replace the internal PTY steps with a Connections-tab flow before calling Codex first-class support.
15. Stop and start EC2, confirm EBS state, and restart the recipe semantically.
16. Reconstruct and read back the exact native provider project before declaring readiness.
17. Create a fresh mobile task bound to the exact Lift folder and write a post-restart proof inside the exact Lift workspace.

The direct transport, real-EC2 workspace, structural stop/start recovery, server-side project/readiness reconstruction, fresh exact-folder phone task, guarded approval/proof turn, following restore-tested checkpoint, and clean and deliberate-conflict disposable-fixture returns now pass once each. Promotion still requires network interruption and recovery, reauthentication and revocation, repeated independent users and runs, broader interruption coverage, provider-policy review, arbitrary real-workspace capture, automatic offline-helper wake, conflict-resolution UI, a zero-terminal customer path, and separate provider-service identity and credential isolation. Until then, Lift remains provider-neutral and Codex remains an experimental recipe rather than a supported phone-with-laptop-off surface.

## Claude as another recipe

The same runner could execute:

```text
claude remote-control
```

The process would connect through Anthropic's relay to Claude's existing web and mobile clients. Lift would supervise only the process and persist approved Claude-owned state. It would not contain Claude-specific transport code.

This example is important architecturally: adding Claude requires a recipe and compatibility test, not a new runner implementation.

Reference:

- [Claude Code Remote Control](https://code.claude.com/docs/en/remote-control)

## Universal continuity without universal sessions

Lift can preserve universal workspace continuity even though provider conversations are opaque.

Lift records a provider-neutral continuation package containing:

- the user's stated goal when explicitly supplied to Lift;
- workspace manifest revision;
- Git base, branch, and dirty-file summary;
- test and development-process status;
- recent Lift lifecycle events;
- user-approved notes needed to restart work.

The provider may separately preserve its own session. Lift should not scrape or copy proprietary session databases. If the provider process cannot resume, the user can give the continuation package to the same or a different agent.

## Security constraints

- Treat every recipe as untrusted executable code.
- Run it as the unprivileged workspace user.
- Require review before installation, authentication, or changed permissions.
- Keep provider credentials outside the project tree.
- Never log provider PTY output during authentication or pairing by default.
- Never parse or persist pairing codes unless a future explicit, reviewed feature requires it.
- Never surface a raw terminal in a first-class provider's normal Connect or Lift Off flow.
- Do not expose raw provider daemons publicly.
- Restrict persistent paths and secret references.
- Record recipe version and content hash for reproducibility.
- Let the user remove one recipe and its provider state without deleting the workspace.

## Non-goals

- a provider-specific code adapter in the Lift core;
- a universal chat or remote-control protocol;
- translating conversations between providers;
- making unsupported agents appear in another provider's mobile app;
- normalizing provider pairing, approvals, or sessions;
- copying opaque provider credentials from the laptop;
- automating account creation or bypassing provider policy.

## Runner boundary statement

At the runner layer, Lift can run any reviewed, user-chosen remote-capable agent command inside a persistent cloud workspace. When that agent offers native mobile remote control, the user keeps using it exactly as the provider designed it. The full product is the durable project workspace and its state, participants, capabilities, and recovery—not merely this command runner; see [`PRODUCT_NORTH_STAR.md`](PRODUCT_NORTH_STAR.md).
