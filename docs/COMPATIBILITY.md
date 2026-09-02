# Compatibility and Support Matrix

Last updated: 2026-09-02

## Status vocabulary

- **Verified**: passes the full release test on named versions.
- **Alpha**: supported for invited users with known limitations.
- **Experimental**: available only for feasibility testing; not a product promise.
- **Relay required**: works only while another named device remains awake.
- **Planned**: in scope later but not available.
- **Unsupported**: detected and blocked or explicitly excluded.

Never label a component Verified based only on installation or process health. Provider continuation requires the real client path; state support requires Lift Off and Land.

## Current product claim

Lift is in a Codex-first feasibility and private-alpha planning phase. Direct phone control and one full EC2 stop/start recovery have passed as founder evidence, with a laptop-off sequence strongly corroborated but not cryptographically attested. The post-restart run included exact folder/runtime binding, guarded approval observation, proof, following checkpoint, exact-version restore, and a fresh safe-to-close evaluation. Separate provider-service identity and credential isolation are pre-alpha gates; network recovery, revocation, repetition, provider-policy review, and complete Land remain pending, so no public laptop-off compatibility claim is final.

The current implementation is fixture-only and has no complete Land or customer UI. See [`CURRENT_STATE.md`](CURRENT_STATE.md) before interpreting a first-slice target as present support.

## Provider matrix

| Provider path | Runtime | Existing user interface | Status | Current limitation |
| --- | --- | --- | --- | --- |
| Codex direct headless Remote | Ubuntu x86_64 EC2 | ChatGPT/Codex phone experience | Experimental | The local precursor and one real EC2 run pass provider-URL pairing and direct phone task execution against a real workspace under `/home/lift`. The EC2 run's laptop-off sequence is strongly corroborated by a fresh challenge/proof exchange and Mac reboot timestamps, but it is human-attested rather than cryptographically device-attested. Three immutable private-Git checkpoints were restored from exact checksummed, versioned S3 objects. One EC2 stop/start recovered the exact EBS volume, earlier checkpoints and proof files, runner, and Remote environment; after server-side project/root repair, a fresh phone task passed exact folder/runtime binding, guarded approval observation, proof, following checkpoint, restore, and safe-to-close evaluation once. Separate provider-service identity and credential isolation, network recovery, revocation, provider-policy review, repeated runs, and complete Land remain pending. |
| Codex Desktop to SSH | Ubuntu x86_64 EC2 plus Mac/Windows desktop | ChatGPT Desktop and paired phone | Relay required | Documented phone flow still depends on the awake desktop host; this cannot support the laptop-off claim. |
| Claude Code Remote Control | Ubuntu x86_64 EC2 | Claude web/mobile | Planned validation recipe | Cleaner documented headless remote path, but account eligibility, EC2 behavior, and reconnect must be tested. |
| Custom remote-capable CLI | Ubuntu x86_64 EC2 | Provider-owned client | Planned advanced mode | No first-class badge until auth, readiness, recovery, and policy pass. |
| CLI without provider-native remote client | Ubuntu x86_64 EC2 | SSH/terminal or its own web UI | Advanced/unsupported for core promise | Lift will not create a replacement mobile interface. |

Every release records:

- provider CLI version;
- connection recipe version;
- account type and eligibility;
- desktop and phone app versions when relevant;
- authentication mode;
- readiness evidence;
- reconnect results after network, process, and VM restart.

## Local operating systems

| Local system | Status | Notes |
| --- | --- | --- |
| macOS on Apple silicon | Initial alpha target | Helper signing, permissions, filesystem casing, sleep/wake, and update behavior must pass. |
| macOS on Intel | Planned validation | Do not assume binary compatibility without testing. |
| Windows | Planned | Path, permission, symlink, case, helper distribution, and Git behavior require separate work. |
| Desktop Linux | Planned | Technically close to the runtime but not part of the consumer-first alpha. |
| iOS/Android as Lift control surfaces | Not required | The provider's existing phone application owns the coding conversation. Lift may expose a responsive lifecycle dashboard, not a chat app. |

## Cloud runtime

| Component | Initial target | Status |
| --- | --- | --- |
| Distribution | Ubuntu LTS, exact image pinned per release | Canonical AMI identity is live-verified in Phase 0; AWS CLI and Codex installer bytes are still mutable and unverified before root execution |
| Architecture | x86_64 | Selected for first slice |
| Compute | One EC2 VM per workspace | One full Phase 0 stop/start phone recovery passed; provider-service and credential isolation remain pre-alpha gates |
| Storage | Separate encrypted gp3 EBS volume | Exact volume and checkpoint `0002` recovered across one stop/start; checkpoint `0003` then restored from exact versioned objects |
| Administration | AWS Systems Manager; restricted SSH only for required diagnostics | Selected direction |
| Process supervision | `systemd` user services | Provider-neutral runner auto-started healthy after one stop/start |
| Region | One region | Phase 0 exercised in `us-east-1`; product-region decision remains pending |
| Managed production runtime | Daytona VM sandboxes or another candidate | Evaluation only after validation |

## Repository support

| Repository feature | First-slice status | Required behavior |
| --- | --- | --- |
| Standard Git worktree | Target | Full Lift Off and Land. |
| Dirty tracked files | Target | Captured without changing real index. |
| Staged plus unstaged state | Target | Content captured; real local index preserved on return. |
| Untracked files | Target | Included after manifest review. |
| Ignored files | Explicit opt-in only | Never included or remotely pushed by default. |
| File create/delete/rename | Target | Three-way return and manifest verification. |
| Executable bit | Target | Preserve supported mode. |
| Symbolic links | Target with validation | Never follow outside the workspace during capture/apply. |
| Case-only rename/collision | Detect before return | Must not corrupt case-insensitive macOS paths. |
| Binary files | Target within size cap | No automatic content merge; hash and preserve conflicts. |
| Git LFS | Planned | Pointer and object availability require explicit tests. |
| Submodules | Deferred | Block or require a separate approved workspace per module. |
| Nested Git repositories | Deferred | Detect and block before transfer. |
| Multiple worktrees | Deferred | Private mirror must not confuse linked Git directories. |
| Sparse checkout | Deferred | Requires explicit index and path-policy tests. |
| Non-Git folder | Future | Manifest transfer can work, but PR-like merge depends on a separate strategy. |
| Huge monorepository | Future | Limits depend on measured scan, transfer, storage, and merge performance. |

The alpha must publish numeric repository and individual-file size caps after measurement.

## Project/toolchain support

| Project class | Status | Notes |
| --- | --- | --- |
| TypeScript/Node project with lockfile | First target | One conventional install and development command. |
| Other CLI-native Linux projects | Planned | Add only after environment reconstruction tests. |
| Docker-dependent project | Planned validation | Requires runtime resource and security limits. |
| macOS-only GUI project | Unsupported | Does not fit the Linux coding-workspace wedge. |
| Production infrastructure repository | Discouraged in alpha | Credential and blast-radius requirements exceed the first trust boundary. |
| Large media/game repository | Unsupported initially | Binary and transfer profile is outside the wedge. |

## Feature support

| Capability | Current / first-slice state | Later |
| --- | --- | --- |
| One workspace, one user | Founder harness only | Teams and sharing |
| One active provider process | Implemented in founder harness | Multiple simultaneous agents |
| Exact local dirty-state transplant | Generated fixture only; real manifest flow not implemented | Multiple devices |
| Provider-native phone continuation | Experimental single-run pass | More recipes |
| Git-backed Land | Designed; complete clean/conflict return not implemented | Optional sanitized GitHub PR |
| Authenticated preview | No | Planned after handoff loop |
| Browser profile migration | No | Isolated project browser identity only |
| Whole-laptop clone | No | Explicit non-goal |
| Process-memory migration | No | Semantic restart only |

## Promotion test

Move an item from Experimental or Planned to Alpha/Verified only after recording:

1. exact versions and environment;
2. fresh install and authentication;
3. first Lift Off;
4. laptop-off or explicitly labeled relay behavior;
5. network interruption;
6. provider process restart;
7. compute stop and wake;
8. cloud checkpoint and Land;
9. clean and conflict return;
10. revoke and delete;
11. known limitations and rollback.

Compatibility is release data, not marketing copy.
