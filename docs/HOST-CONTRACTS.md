# Public host contracts and verification

Gatekeeper uses only public Hermes plugin interfaces:

- `ctx.get_config`, `ctx.register_hook`, `ctx.register_command` — see the plugin
  developer guide (`website/docs/developer-guide/plugins/index.md` in
  [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)).
- `plugins.plugin_storage.plugin_data_dir` for active-profile storage
  (`<hermes home>/plugin-data/hermes-gatekeeper/`). Home selection stays inside
  Hermes's storage helper; the plugin never reads `HERMES_HOME`, config or credential
  files, and imports nothing from `hermes_cli`.
- `pre_tool_call` directives: `{"action":"block","message":…}` vetoes; `{"action":
  "approve","message":…,"rule_key":…}` asks the host's human-approval gate. `block`
  outranks `approve`. Keywords received: `tool_name`, `args`, `task_id`, `session_id`,
  `tool_call_id`, …
- `post_tool_call` observer keywords `tool_name`, `args`, `result`, `status`,
  `tool_call_id` (status `blocked`/`cancelled` release a reservation).
- `post_gateway_admission` keywords `session_key`, `platform`, `source` (the
  normalized `SessionSource.to_dict()` snapshot), `message_id`, `text`; returning
  `{"action":"handled"}` consumes the message. It runs after authorization, control,
  approval, steering and slash-command lanes, so it is not universal inbound
  visibility. It is fail-open on the host side.
- Slash-command calling-session keywords `platform` and `source`. A local session's
  command runs in the gateway and receives `platform="local"` with a `SessionSource`
  whose platform is local; the classic in-process path passes `source=None`.

## What a live agent turn reaches

Hermes registers no model-callable `send_message` tool: `toolsets.py` states there is
deliberately none and `tools/send_message_tool.py` notes it is imported by cron, the
`hermes send` CLI, the kanban notifier and the opt-in MCP server. Imports of its
helpers are not `pre_tool_call` calls. The tool call Gatekeeper actually sees when an
agent sends is `terminal` running `hermes send …` / `imsg send …`, including
`terminal()` called from an `execute_code` script (Hermes dispatches those inner calls
through `handle_function_call`, which fires `pre_tool_call`). The following are not
parsed: `cronjob_manage` delivery, `connectors__<app>__<tool>` connector tools,
`mcp__<server>__<tool>` MCP tools (`mcp_<server>_<tool>` in older spelling), platform
tools (Discord, A2A, …), UI automation, and a send made from inside a script
(`subprocess` in `python -c` or `execute_code`).

Connector and MCP tool calls do fire `pre_tool_call` under those prefixed names
(`tools/connectors/gateway/names.py`, `tools/mcp_tool_schema.py` in the Hermes source),
and so does each entry of a batched `tool_call`, which Hermes dispatches through
`handle_function_call` with its own call ID. Gatekeeper therefore sees the *name* and
arguments of such a call but has no parser for its recipient, so it cannot check
suppression, consent or quiet hours. Instead, when `escalate_unrecognized_sends` is on,
a name matching the send vocabulary (see README) gets an `approve` directive with the
reason `Gatekeeper: unrecognized send tool <name>; owner approval required. Gatekeeper
cannot check consent/STOP/quiet hours for this tool.`, and a `cronjob_manage`/`cronjob`
create/update/run carrying a non-`local` `deliver`/`target`/`failure_deliver` gets the
same. `approve` is a request to the host's approval gate: it is auto-approved under
`--yolo`, `approvals.mode: off` and `hermes -z`, where this escalation protects nothing.

Host behaviors that bound the guarantee: a `pre_tool_call` callback that raises or
times out is turned into a `block` directive by the host's dispatcher, and
Gatekeeper's callback also converts every internal error into its own `block`
directive. If the host's dispatcher itself throws while collecting results, the
call proceeds (`tool_executor._pre_tool_block`). Sessions started with
`--safe-mode`/`--ignore-user-config` do not run plugin hooks at all. An `approve`
directive is auto-approved under `--yolo`, `approvals.mode: off` and
`hermes -z`/`--oneshot` (the host sets `HERMES_YOLO_MODE=1`); with no human or
approval bridge present it fails closed.

## Verification performed

Unit tests (`pytest`) call the registered callbacks with synthetic public contexts and
a real temporary SQLite database. They do not install Hermes. The unrecognized-send-tool
escalation (names, cron arguments, settings, decision log) is covered only at this level;
it has not been exercised through a running Hermes host's dispatcher.

Host checks were run against Hermes v0.23.0 (`2bd378ed1b`) in an isolated, throw-away
`HERMES_HOME` with no messaging credentials: the plugin installed from a `file://`
clone and enabled with `hermes plugins install/enable`; settings via
`plugins.entries.hermes-gatekeeper.settings`; records created through the real
`/gatekeeper` command handler; a scripted local model server emitting `terminal` /
`execute_code` tool calls into the real agent loop and hook dispatcher; and stub
`hermes`/`imsg` executables that only log their arguments. Observed:

| Attempt | Result |
|---|---|
| `hermes send` to a suppressed recipient (also via `imsg send`, `hermes -p NAME send`, and `terminal()` inside `execute_code`) | blocked, stub not run |
| send to a recipient without consent | blocked (`no_consent`) |
| consented recipient, local time outside 08:00–21:00 | blocked (`quiet_hours`) |
| consented recipient in window, exact approved template | allowed, stub ran once |
| immediate second send / unapproved wording | `approve` requested; not run without a human, run when the host auto-approves (YOLO) |
| suppressed recipient under YOLO | still blocked |
| `/gatekeeper` from a local session with a local `SessionSource`; from a Telegram source | accepted; refused |
| Casing variant of an opted-out address | still suppressed |

`hermes plugins validate .` and `hermes plugins doctor .` pass on the repository.
The `requires_hermes` floor (`>=0.22.5`) is based on the documentation at that tag
(which documents `post_gateway_admission`); the plugin has not been executed on that
release.

Catalog entry fields follow the plugin-catalog entry schema; `sha` is filled in when
the reviewed commit is pinned.
