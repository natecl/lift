# Provider-Neutral Remote Workloads

Last updated: 2026-08-31

## Decision

Lift should not implement a Codex adapter, Claude adapter, or universal agent protocol.

Lift should implement one provider-blind remote workload runner. A reviewed connection recipe installs and starts a long-lived command inside the Lift workspace. If that command implements native remote control, the provider connects it to the provider's existing mobile or web client. Supported recipes are presented through Lift's Connections tab rather than exposed as terminal configuration.

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

## Codex as the first recipe

Codex is the first real workload used to validate the runner, not a special integration in the Lift core.

The current local `codex-cli 0.146.0`, inspected on 2026-08-31, exposes candidate experimental commands:

```text
codex app-server daemon bootstrap --remote-control
codex remote-control start
codex remote-control pair
```

A Codex recipe can install the CLI and declare the daemon start command. In the finished product, the Connections tab must present the provider-owned login and any supported pairing flow without asking the user to open a terminal. Lift does not collect OpenAI passwords or interpret Remote conversation messages.

Desired flow:

```text
ChatGPT mobile
    -> OpenAI-owned Remote relay
    -> Codex-owned daemon on Ubuntu EC2
    -> Lift-owned persistent workspace
```

This path remains experimental until verified on a real Ubuntu EC2 host and phone. The official OpenAI documentation currently describes phone Remote through an awake Mac or Windows desktop host. It separately documents the desktop app starting Codex App Server on an SSH host.

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
7. Start work from the phone against the Lift workspace.
8. Disconnect the provisioning laptop.
9. Restart the supervised process and test provider reconnection.
10. Replace the internal PTY steps with a Connections-tab flow before calling Codex first-class support.
11. Stop and start EC2, confirm EBS state, and restart the recipe semantically.

The spike succeeds only if the provider-owned connection survives without an awake desktop relay. If it does not, Lift remains provider-neutral, but Codex cannot yet deliver the full phone-with-laptop-off experience through its supported surface.

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

## Final product statement

Lift runs any user-chosen remote-capable agent command on a persistent cloud workspace. When that agent offers native mobile remote control, the user keeps using it exactly as the provider designed it.
