# Product and Company Risk Register

Last updated: 2026-09-02

## Scoring

- Likelihood: `1` rare to `5` expected.
- Impact: `1` minor to `5` existential or severe user harm.
- Exposure: likelihood multiplied by impact.

Scores are current hypotheses. Owners update evidence, mitigation, and trigger status at least weekly during alpha.

## Active risks

| ID | Risk | L | I | Exposure | Current mitigation | Trigger or leading indicator | Owner |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| R-001 | Direct Codex phone-to-Linux control is unstable, changes, or remains unsupported despite one founder pass. | 4 | 5 | 20 | Keep status Experimental, pin and record versions, repeat the full compatibility gate, label desktop relay honestly, and be ready to validate Claude first. | Pairing or recovery regresses, another user cannot repeat the run, or provider policy rejects the topology. | Nate |
| R-002 | Provider authentication cannot be embedded in a zero-terminal Connections flow. | 3 | 5 | 15 | Use provider-owned browser/device flow, connection recipes, and explicit eligibility gates. | Users must paste tokens, open a terminal, or copy opaque credential state. | Nate |
| R-003 | Provider changes an experimental CLI, remote protocol, or eligibility rule. | 4 | 4 | 16 | Pin versions, test compatibility, keep provider code isolated in recipes, and publish status. | Readiness failures increase after a version or provider rollout. | Nate |
| R-004 | Lift corrupts or silently overwrites workspace state. | 2 | 5 | 10 | Ownership lease, signed manifests, private Git three-way merge, recovery journal, no cleanup before ack. | Hash mismatch, unexplained local change, failed crash recovery, or missing cloud revision. | Nate |
| R-005 | Unsaved editor buffers overwrite returned files after Land. | 3 | 4 | 12 | Detect known editors where practical, warn before return, recheck disk state, preserve recovery revision. | User reports editor reopening or saving an older buffer after successful Land. | Nate |
| R-006 | Secrets enter workspace snapshots, Git objects, logs, analytics, or support output. | 3 | 5 | 15 | Default exclusions, explicit ignored-file approval, vault isolation, redaction tests, secret scans. | Secret scanner hit or provider credential path appears in a manifest/object set. | Nate |
| R-007 | Workspace isolation failure exposes another user's data or credentials. | 2 | 5 | 10 | One VM per workspace initially, metadata blocking, least privilege, cross-user tests. | Unexpected cross-workspace network or storage access. | Nate |
| R-008 | Users do not trust source code on Lift-hosted infrastructure. | 4 | 4 | 16 | Transparent manifest, encryption, revoke/delete/export, noncritical design-partner repositories, future BYO AWS. | Qualified users abandon at transfer approval. | Nate |
| R-009 | Wake, environment reconstruction, or transfer is too slow for the trigger moment. | 4 | 4 | 16 | Persistent volume, warm path, content-addressed delta, timing instrumentation, prebuilt image. | Median safe-to-close exceeds target or users leave before completion. | Nate |
| R-010 | Compute and support cost exceed a consumer price. | 3 | 4 | 12 | Idle stop, hard caps, usage attribution, one workspace, measured packaging, support-time tracking. | Negative contribution margin or high support minutes after activation. | Nate |
| R-011 | Users prefer cloud-first agents and do not value local transplant. | 3 | 5 | 15 | Concierge comparison and H2 validation gate before scaling build. | Users choose Codespaces/provider cloud even after seeing Lift Off. | Nate |
| R-012 | The trigger is impressive but too infrequent for retention. | 4 | 5 | 20 | Recruit high-frequency ICP, measure recent events, require repeated handoffs before paid beta. | Fewer than three of ten users repeat three times. | Nate |
| R-013 | Users like Lift but will not pay beyond their agent subscription. | 3 | 4 | 12 | Request deposit immediately after success; test subscription plus usage; measure workaround spend. | Zero deposits after successful real loops. | Nate |
| R-014 | First-party Codex or Claude products absorb persistence and handoff. | 4 | 4 | 16 | Own cross-provider workspace state, local dirty-state transplant, and safe return; monitor bundling. | Provider ships equivalent local-to-cloud-to-local flow. | Nate |
| R-015 | Existing competitors already satisfy the ICP with a simpler workflow. | 3 | 4 | 12 | Test against CloudCLI, iCode, Codespaces, and DIY setup using real tasks. | Design partners prefer an existing option after direct comparison. | Nate |
| R-016 | Git-backed reconciliation fails on real repository shapes. | 3 | 4 | 12 | Narrow compatibility, private refs/index, test matrix, block submodules/nested repos initially. | High unsupported rate or merge differs from manifest result. | Nate |
| R-017 | Automatic return surprises an active editor or local process. | 3 | 4 | 12 | Explicit Land, cloud freeze, local precondition recheck, visible ownership state, recovery journal. | Files change while a local tool is actively writing. | Nate |
| R-018 | A compromised repository exfiltrates credentials or attacks the control plane. | 3 | 5 | Per-workspace isolation, scoped secret broker, restricted egress, metadata blocking, approval boundaries. | Unexpected secret access or outbound destination. | Nate |
| R-019 | Product name creates trademark, search, domain, or package conflict. | 3 | 3 | 9 | Treat Lift as working name; run formal checks before public launch. | Counsel/search reveals conflict or acquisition is impractical. | Nate |
| R-020 | Alpha incident response is too slow or lacks recovery evidence. | 3 | 5 | Severity model, stop-all control, versioned recovery, staffed launch, rehearsed runbooks. | Incident occurs without a known durable revision or accountable owner. | Nate |
| R-021 | Process liveness or server project registration is mistaken for real phone readiness. | 3 | 5 | 15 | Separate liveness, semantic readiness, controller visibility, fresh folder/task binding, guarded approval, following checkpoint, and expiring safe-to-close evidence. | A healthy daemon routes a task to the wrong folder, the picker cannot expose the workspace, or approval controls are unusable. | Nate |
| R-022 | Provider credentials and policy state are reachable from a compromised workspace because both share the `lift` Unix identity. | 4 | 5 | 20 | Block external alpha until the provider service/credential owner has a separate identity or narrow broker with encrypted credentials unreadable to workspace code. | Workspace code can read, write, race, or replace provider credential, policy, or connection state. | Nate |
| R-023 | Approval evidence is overclaimed or influenced by unbound provider/plugin state. | 3 | 5 | 15 | Keep the claim a guarded inference, require passive observation plus independent history and an unchanged plugin/config guard, and seek provider decision-bearing audit evidence or trusted transport. | Decision/responder attribution is required, plugin content changes invisibly, or a repeated canary shows session-scoped acceptance. | Nate |
| R-024 | Mutable installer bytes execute as root during workspace bootstrap. | 3 | 5 | 15 | Replace downloads with a signed content-addressed image or verify published signatures and reviewed digests before execution. | Upstream installer content changes without a Lift release or reproducible digest. | Nate |
| R-025 | Fixture capture is generalized before a safe real-workspace manifest exists. | 3 | 5 | 15 | Retain the exact disposable marker gate; build explicit discovery, exclusions, and ignored/sensitive-file approval before any real-project transfer. | An unmarked repository reaches ledger creation or an ignored/sensitive path is included without explicit selection. | Nate |
| R-026 | Cached AWS identifiers or ambient endpoint/configuration state redirect runtime actions. | 2 | 5 | 10 | Bind account, ARN, immutable STS user ID, live stack/resources/AMI, and canonical paths; scrub credential/profile/region/endpoint/CA/Botocore/metadata overrides. | Same-name IAM recreation, output/resource drift, unexpected endpoint, or cross-account operation is accepted. | Nate |

## Risk treatment rules

- Exposure `15-25`: block public launch or assign an immediate validation/mitigation action.
- Exposure `8-14`: keep an active owner, leading indicator, and scheduled test.
- Exposure `1-7`: monitor and revisit when scope changes.
- Any risk involving data loss, cross-user access, credential exposure, or false safe-to-close is a hard launch blocker regardless of numeric score.

## Weekly risk review

For the highest five exposures:

1. What new evidence changed likelihood or impact?
2. Did a leading indicator fire?
3. Is the mitigation implemented and tested or merely planned?
4. What is the next risk-reducing action?
5. Does this risk change the product claim, compatibility, phase gate, or launch decision?

Record accepted risk and scope limitations in [`DECISIONS.md`](DECISIONS.md). Move incident-derived controls into [`SECURITY.md`](SECURITY.md), [`OPERATIONS.md`](OPERATIONS.md), or [`LAUNCH_CHECKLIST.md`](LAUNCH_CHECKLIST.md) rather than leaving them only here.
