# Public host contracts and provenance

Gatekeeper uses these public interfaces only:

- `ctx.get_config`, `ctx.register_hook`, `ctx.register_command` from the [plugin developer guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).
- `plugins.plugin_storage.plugin_data_dir` for active-profile storage. Home selection stays inside Hermes's public storage helper; no raw HERMES_HOME reconstruction or private config imports.
- `pre_tool_call` block/approve directives and `post_tool_call` status/result/correlation from the [hook reference](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).
- `post_gateway_admission`: normalized authorized profile-scoped source snapshot/text; silently consume STOP with `{"action":"handled"}`, never adapter calls. This is after control, approval, steering and slash-command lanes and is not universal inbound visibility.
- Slash-command calling-session `platform` and `source` keywords; the local-owner test follows the supplied Standing example. Unknown/remote context cannot administer or read this plugin's records.

The staged scaffold b7f37b5 supplied developer/catalog docs, observer-hooks.md,
send_message_tool.py and Standing examples under hermes-ref/. Those are design
references, not Gatekeeper's runtime or copied core dependencies. Removal from
this candidate's release tree was requested but the unattended approval gate
refused the git-rm action; AXIOM must remove/omit hermes-ref before native
admission scanning. The originals remain available at the scaffold commit.

The supplied send_message_tool.py:28-30 explicitly says send_message is not
model-tool registered; CLI/cron/notifier imports of its helpers are NOT evidence
of pre_tool_call coverage. target/message shapes follow that reference. The
current public CLI reference documents `hermes send --to <target> <message>`.

The current public hook page was re-read for inbound visibility. A direct public
fetch of the v0.22.5 hook reference confirmed post_gateway_admission is documented
at that tag. This supports the declared floor; it is not execution on that release.
https://raw.githubusercontent.com/NousResearch/hermes-agent/v0.22.5/website/docs/user-guide/features/hooks.md

Native host validate/doctor, approval policy behavior, real dispatcher ordering
and plugin composition remain operator checks. Unit tests invoke registered
callbacks through synthetic public contexts and real temporary SQLite; they do
not pretend to install Hermes or execute a real message send.

Catalog draft fields follow the canonical plugin-catalog README entry schema.
The named example-catalog-entry.yaml was not present in the scaffold; repository
owner and exact SHA remain explicit operator placeholders, never guessed.
