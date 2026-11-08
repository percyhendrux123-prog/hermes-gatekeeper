# Changelog

## 0.1.0

- Deterministic absolute suppression (case-insensitive), per-channel consent and recipient-local quiet-hour rules.
- Native Hermes approval directives for unknown timezone, unanswered/pending threads, minimum gaps and non-template wording.
- Exact templates filled only from local-owner variables; no model-filled approval shortcut.
- Hashed local decision log and atomic conservative thread reservations, with replay/order regressions.
- Bounded inspection of literal `hermes send` (including `-p/--profile`) and `imsg send` terminal commands, any hook-visible `send_message`, and deferred batches.
- Public normalized inbound STOP/DM reply observation and local-owner administration commands (accepted from gateway-owned local sessions, refused from messaging platforms).
- Escalate-on-unrecognized-send-tool: a tool call Gatekeeper cannot parse whose name matches a conservative send vocabulary (`connectors__<app>__<tool>`, `mcp__<server>__<tool>` and `mcp_<server>_<tool>`, plain names) returns a native `approve` directive stating that consent, STOP and quiet hours cannot be checked; `cronjob_manage`/`cronjob` create/update/run with a delivery target does the same. Read-only, delete and draft-only names stay allowed. Each escalation is written to the hashed decision log as rule `unrecognized_send_tool`.
- New settings `escalate_unrecognized_sends` (default true), `extra_send_tool_patterns` and `allow_tools` (both default empty).
- Explicit scope, storage, approval-policy and inbound-visibility disclosures. No transport, network, subprocess or model calls.
