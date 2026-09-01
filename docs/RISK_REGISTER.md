# Product and Company Risk Register

Last updated: 2026-08-31

## Scoring

- Likelihood: `1` rare to `5` expected.
- Impact: `1` minor to `5` existential or severe user harm.
- Exposure: likelihood multiplied by impact.

Scores are current hypotheses. Owners update evidence, mitigation, and trigger status at least weekly during alpha.

## Active risks

| ID | Risk | L | I | Exposure | Current mitigation | Trigger or leading indicator | Owner |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| R-001 | Direct Codex phone-to-Linux control is unavailable, unstable, or unsupported. | 4 | 5 | 20 | Run the EC2 feasibility gate; label desktop relay honestly; be ready to validate Claude first. | Pairing fails, phone cannot reconnect, or provider policy rejects the topology. |  |
| R-002 | Provider authentication cannot be embedded in a zero-terminal Connections flow. | 3 | 5 | 15 | Use provider-owned browser/device flow, connection recipes, and explicit eligibility gates. | Users must paste tokens, open a terminal, or copy opaque credential state. |  |
| R-003 | Provider changes an experimental CLI, remote protocol, or eligibility rule. | 4 | 4 | 16 | Pin versions, test compatibility, keep provider code isolated in recipes, and publish status. | Readiness failures increase after a version or provider rollout. |  |
| R-004 | Lift corrupts or silently overwrites workspace state. | 2 | 5 | 10 | Ownership lease, signed manifests, private Git three-way merge, recovery journal, no cleanup before ack. | Hash mismatch, unexplained local change, failed crash recovery, or missing cloud revision. |  |
| R-005 | Unsaved editor buffers overwrite returned files after Land. | 3 | 4 | 12 | Detect known editors where practical, warn before return, recheck disk state, preserve recovery revision. | User reports editor reopening or saving an older buffer after successful Land. |  |
| R-006 | Secrets enter workspace snapshots, Git objects, logs, analytics, or support output. | 3 | 5 | 15 | Default exclusions, explicit ignored-file approval, vault isolation, redaction tests, secret scans. | Secret scanner hit or provider credential path appears in a manifest/object set. |  |
| R-007 | Workspace isolation failure exposes another user's data or credentials. | 2 | 5 | 10 | One VM per workspace initially, metadata blocking, least privilege, cross-user tests. | Unexpected cross-workspace network or storage access. |  |
| R-008 | Users do not trust source code on Lift-hosted infrastructure. | 4 | 4 | 16 | Transparent manifest, encryption, revoke/delete/export, noncritical design-partner repositories, future BYO AWS. | Qualified users abandon at transfer approval. |  |
| R-009 | Wake, environment reconstruction, or transfer is too slow for the trigger moment. | 4 | 4 | 16 | Persistent volume, warm path, content-addressed delta, timing instrumentation, prebuilt image. | Median safe-to-close exceeds target or users leave before completion. |  |
| R-010 | Compute and support cost exceed a consumer price. | 3 | 4 | 12 | Idle stop, hard caps, usage attribution, one workspace, measured packaging, support-time tracking. | Negative contribution margin or high support minutes after activation. |  |
| R-011 | Users prefer cloud-first agents and do not value local transplant. | 3 | 5 | 15 | Concierge comparison and H2 validation gate before scaling build. | Users choose Codespaces/provider cloud even after seeing Lift Off. |  |
| R-012 | The trigger is impressive but too infrequent for retention. | 4 | 5 | 20 | Recruit high-frequency ICP, measure recent events, require repeated handoffs before paid beta. | Fewer than three of ten users repeat three times. |  |
| R-013 | Users like Lift but will not pay beyond their agent subscription. | 3 | 4 | 12 | Request deposit immediately after success; test subscription plus usage; measure workaround spend. | Zero deposits after successful real loops. |  |
| R-014 | First-party Codex or Claude products absorb persistence and handoff. | 4 | 4 | 16 | Own cross-provider workspace state, local dirty-state transplant, and safe return; monitor bundling. | Provider ships equivalent local-to-cloud-to-local flow. |  |
| R-015 | Existing competitors already satisfy the ICP with a simpler workflow. | 3 | 4 | 12 | Test against CloudCLI, iCode, Codespaces, and DIY setup using real tasks. | Design partners prefer an existing option after direct comparison. |  |
| R-016 | Git-backed reconciliation fails on real repository shapes. | 3 | 4 | 12 | Narrow compatibility, private refs/index, test matrix, block submodules/nested repos initially. | High unsupported rate or merge differs from manifest result. |  |
| R-017 | Automatic return surprises an active editor or local process. | 3 | 4 | 12 | Explicit Land, cloud freeze, local precondition recheck, visible ownership state, recovery journal. | Files change while a local tool is actively writing. |  |
| R-018 | A compromised repository exfiltrates credentials or attacks the control plane. | 3 | 5 | 15 | Per-workspace isolation, scoped secret broker, restricted egress, metadata blocking, approval boundaries. | Unexpected secret access or outbound destination. |  |
| R-019 | Product name creates trademark, search, domain, or package conflict. | 3 | 3 | 9 | Treat Lift as working name; run formal checks before public launch. | Counsel/search reveals conflict or acquisition is impractical. |  |
| R-020 | Alpha incident response is too slow or lacks recovery evidence. | 3 | 5 | 15 | Severity model, stop-all control, versioned recovery, staffed launch, rehearsed runbooks. | Incident occurs without a known durable revision or accountable owner. |  |

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
