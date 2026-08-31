# Security Baseline

Lift will execute powerful autonomous tools against source code and credentials on remote infrastructure. Security is part of the initial product definition.

## Security objectives

- Compromise of one workspace does not expose another workspace or the control plane.
- An agent can access only the project, tools, network destinations, and credentials it requires.
- Users can see and revoke access.
- Secrets do not appear in images, snapshots, logs, manifests, or source-control changes.
- Local and cloud work remain recoverable after compromise or operator error.
- No file leaves the local computer merely because Lift discovered it.

## Primary threats

### Malicious repository content

Instructions in source files, issues, dependencies, tool configuration, or generated output can manipulate an agent into reading secrets, changing policy, or exfiltrating data.

### Overpowered credentials

A general GitHub token, AWS key, browser profile, or personal SSH key can turn a compromised project into a compromise of the user's broader digital life.

### Cross-tenant escape

A container or runtime vulnerability could expose another user's memory, filesystem, credentials, or network identity.

### Unsafe state transfer

Automatic discovery could upload private ignored files, `.env` files, credentials, customer data, or unrelated home-directory content.

### Sync corruption

Concurrent local and cloud edits or implementation bugs could destroy or overwrite work.

### Public development services

A preview server, database console, or debugging port could be exposed to the internet without authentication.

### Resource abuse

An agent can create runaway processes, consume compute, make excessive network calls, or provision paid external resources.

### Control-plane compromise

An attacker who controls Lift authentication or orchestration could reach persistent workspaces and their secrets.

## Required controls for private alpha

### Isolation

- Use a dedicated VM or strong microVM boundary per active workspace.
- Do not rely on an application-level permission prompt as the isolation boundary.
- Run workspace services as an unprivileged user.
- Prevent workspace access to cloud instance metadata.
- Separate control-plane credentials from workspace credentials.

### File transfer

- Present a manifest before the first transfer.
- Apply default-deny rules to files outside the selected workspace.
- Treat `.env`, credential files, key files, databases, and ignored files as sensitive.
- Require explicit approval for sensitive or ignored files.
- Encrypt payloads in transit and at rest.
- Maintain content hashes and versioned recovery snapshots.

### Secrets

- Never bake secrets into machine images.
- Store secrets in a dedicated encrypted service.
- Scope each secret to a workspace and purpose.
- Prefer short-lived tokens and GitHub App credentials over personal access tokens.
- Inject secrets into specific processes rather than writing them to general project files.
- Redact secrets from logs and terminal event storage.
- Provide one-action revocation from mobile and web.

### Network

- Default to restricted outbound network access.
- Make broad internet access a visible workspace permission.
- Support destination allowlists as soon as practical.
- Block private control-plane and cloud metadata addresses.
- Authenticate every preview and use TLS.
- Do not expose raw workspace ports publicly.

### Agent actions

- Require confirmation for destructive filesystem operations, secret access, production changes, external messages, deployments, purchases, and new cloud resources.
- Keep an append-only action and approval history.
- Give the user an immediate stop button that terminates agent processes and revokes active secret grants.
- Separate “agent completed the task” from “changes were merged or deployed.”

### Authentication

- Use short-lived web and CLI sessions.
- Protect account recovery and workspace deletion.
- Bind device sessions and allow remote sign-out.
- Rate-limit sensitive endpoints.
- Record security-relevant control-plane events.

### Cost controls

- Idle-stop workspaces.
- Set per-workspace runtime and spend limits.
- Notify before a meaningful budget threshold.
- Prevent workspace credentials from provisioning arbitrary infrastructure by default.

## Prohibited MVP behavior

- Copying an entire home directory.
- Uploading browser cookies or a full authenticated browser profile.
- Copying password-manager data or an operating-system keychain.
- Copying SSH private keys.
- Sharing one filesystem or runtime among different users.
- Giving a workspace administrator-level control-plane credentials.
- Logging full environment variables.
- Opening unauthenticated preview URLs.
- Silently resolving sync conflicts by overwriting one side.

## Browser automation

Authenticated cloud browser use is strategically important but excluded from the first coding-workspace alpha.

When added, it should use a separate browser identity or user-mediated authorization rather than migrating the user's everyday cookie database. Browser state should be isolated per project, visibly scoped, revocable, and inaccessible to unrelated agents.

## Incident readiness

Before inviting external alpha users, Lift needs:

- a way to lock an account and stop all workspaces;
- workspace credential revocation;
- recoverable state snapshots;
- sufficient audit events to reconstruct access;
- a documented contact and response process;
- a clear statement of what is and is not encrypted and logged.

## Security review triggers

Perform a dedicated review before:

- introducing multi-tenant container density;
- adding browser state or browser automation;
- enabling arbitrary MCP servers;
- supporting production credentials;
- allowing inbound webhooks to trigger agents;
- adding team sharing;
- storing agent transcripts long term;
- moving from private alpha to public paid access.

