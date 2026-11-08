# Changelog

## 0.1.0

- Deterministic absolute suppression (case-insensitive), per-channel consent and recipient-local quiet-hour rules.
- Native Hermes approval directives for unknown timezone, unanswered/pending threads, minimum gaps and non-template wording.
- Exact templates filled only from local-owner variables; no model-filled approval shortcut.
- Hashed local decision log and atomic conservative thread reservations, with replay/order regressions.
- Bounded inspection of literal `hermes send` (including `-p/--profile`) and `imsg send` terminal commands, any hook-visible `send_message`, and deferred batches.
- Public normalized inbound STOP/DM reply observation and local-owner administration commands (accepted from gateway-owned local sessions, refused from messaging platforms).
- Explicit scope, storage, approval-policy and inbound-visibility disclosures. No transport, network, subprocess or model calls.
