# Gatekeeper 0.1.0 build contract

Scope: A290 / t_5dbd0ce1. Local-only build from scaffold b7f37b5, no live data, sends, push or PR.
AGENTS.md, CLAUDE.md and prior docs plans are absent at the scaffold.

1. Persistent suppression + privacy-preserving decisions, then channel consent.
2. Recipient-local quiet hours, unanswered-thread/minimum-gap holds, exact owner-filled templates.
3. Conservative send classifier and public pre/post hooks; owner-only slash commands.
4. Public normalized inbound observation, failure paths and concurrent decisions.
5. Catalog/manifest/docs alignment, full pytest -W error, adversarial review and host handoff.

Each module is test-first and committed after its narrow suite passes. No runtime dependencies beyond stdlib and public Hermes storage APIs. Store recipient/thread hashes and message SHA-256, never raw message bodies. Consent sources/dates, timezone/region and owner template variables are stored and disclosed.

Public API boundary: send_message is not currently model-tool registered in supplied core source; direct CLI/cron/notifier helper use and ordinary gateway replies are not universally intercepted. Only calls traversing the plugin hooks are governed. Terminal v1 recognizes imsg send and hermes send; complex recognized shell invocations are blocked, not guessed. Arbitrary scripts/API calls are not an egress firewall.

Use documented post_gateway_admission for automatic STOP and DM reply observation. It excludes rejected, control, paused/queued, running-session steering, slash and pending-approval traffic. No private inbound adapter access. Manual optout/reply commands cover unseen events. No consent inferred from a reply.

A pass means Gatekeeper does not veto; Hermes still sends and owns approvals. An approve directive is not proof of a fresh human answer. Host approval mode/cache and later argument rewrites remain host boundaries, explicitly disclosed. Block outranks approve; suppression is never overridden by approval.

Safe rollback: b7f37b5. Native validate/doctor and codereview CLI are unavailable in this Space at start; AXIOM must provide a runner or run those checks on export before publication.
