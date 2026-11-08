# Gatekeeper

**A deterministic gate for recognized outbound messaging calls in Hermes.**
The agent drafts; Gatekeeper evaluates the owner's policy before dispatch. Hermes—not
this plugin—performs any permitted send and owns the approval interface.

**Gatekeeper enforces rules the owner configures; not legal advice and not a compliance guarantee.**

**Read "What it gates—and what it does not" before relying on it.** In a stock Hermes
agent turn the model has no `send_message` tool, so the call this plugin practically
sees is a literal `hermes send …` / `imsg send …` run through the `terminal` tool.
Connector, MCP, cron-delivery, browser and script-based sends are not inspected.

Version 0.1.0. Checked against Hermes v0.23.0 with the real plugin loader, hook
dispatcher and agent loop (scripted local model, stub send executables, invented
contacts); it has not been run against live messaging platforms.

## Install

```sh
hermes plugins install hermes-gatekeeper
hermes plugins enable hermes-gatekeeper
```

Installing by catalog name gets the reviewed, pinned revision, not an unreviewed branch.
Requires Hermes >=0.22.5, Python >=3.10 and Linux or macOS with timezone data.
There are no third-party runtime dependencies or API keys. Restart/reload Hermes
after changing settings; the policy is loaded at registration.

## What it gates—and what it does not

Gatekeeper registers `pre_tool_call`, `post_tool_call`, `post_gateway_admission`
and the local-owner `/gatekeeper` command. It registers no model tools, middleware,
transport, background job or core override.

* **What a live agent turn actually reaches.** The model-callable tool that can
  send is `terminal`: Gatekeeper inspects literal `hermes send` and `imsg send`
  commands there (including calls to `terminal` made from inside `execute_code`
  scripts, which Hermes also routes through the hooks). Hermes's `send_message` is
  **not currently registered** as a model-callable tool (see `toolsets.py` and the
  note at the top of `tools/send_message_tool.py` in Hermes). Gatekeeper still
  evaluates a `send_message`
  call if one ever traverses `pre_tool_call` (for example from another plugin), using
  `{"target":"platform:recipient[:thread]","message":"literal text"}`; `action=list`
  is read-only and unsupported actions/options are blocked, not guessed. Gatekeeper
  does not register or resurrect that tool.
* **Not reached at all:** the `cronjob_manage` tool (scheduled delivery), hosted
  connector tools (`connectors__<app>__…`, e.g. a Gmail or Slack send), MCP-server
  tools, platform tools such as Discord or A2A, browser/computer-use driving of a
  messaging app, and a script that sends from inside `execute_code` or `python -c`
  (it is not seen as a send). Direct helper use by the CLI, cron, notifier or
  adapters is not a tool-hook call. Ordinary gateway replies and streaming are not
  gated.
* Recognized `terminal` commands are `hermes send` and `imsg send`, including
  explicit executable paths, `hermes -p NAME send` / `--profile NAME`, and
  `hermes-agent`. Simple, single-line literal forms can be evaluated:

  ```text
  hermes send --to sms:+1-555-0100 'Demo notice.'
  imsg send --service sms --to +1-555-0100 --text 'Demo notice.'
  ```

  These are syntax examples, not commands the plugin runs. For `hermes send` only
  `--to`/`-t` and one literal message are understood; `--file`, `--subject`,
  `--mention`, `--json`, `-q`, `--to=…`, stdin bodies and any other global option
  before `send` are blocked as uninspectable. `imsg` needs explicit
  `sms` or `imessage` service; auto-service, chat-id lookup, file/stdin bodies,
  subject/attachment flags, wrappers (`env`, `sh -c`, `python -m hermes_cli.main`),
  pipelines and compound commands are blocked.
  Expansion-bearing characters (`$`, backticks, `*?[]{}~`) and raw newlines/continuations
  are conservatively blocked **even when quoted**, rather than approximating shell
  expansion. `hermes send --list` remains read-only. Mentioning a recognized send
  inside another command can also overblock.
* Deferred `tool_call` / `multi_tool_use.parallel` batches are recursively checked;
  the strictest decision wins. Malformed/oversized/deep batches block. Leaves are
  checked again; the outer batch does not create duplicate send reservations.
  Only `send_message` and `terminal` leaves are recognized: a `connectors__…` leaf in
  such a batch is not inspected.
* This is **not an egress firewall or an OS sandbox**. `curl`, `osascript`, custom
  scripts, encoded/dynamically constructed sends, renamed tools, direct Python
  calls and arbitrary connector tools are out of scope. Other hooks/middleware
  can rewrite arguments later; Gatekeeper cannot guarantee the final delivered
  payload in that composition. Local code/config/database edits can defeat it, and
  sessions started with `--safe-mode`/`--ignore-user-config` load no plugin hooks.

Use stable recipient/chat IDs, not directory/display names or implicit home channels.
`#channel` aliases are refused. Telegram/Discord/Slack thread suffixes are separated;
other platform address strings (including Matrix server names) remain intact.
Phone-format spaces/parentheses/hyphens after `+` normalize for record matching.
Consent and thread history match identities as exact, case-sensitive strings;
suppression matches case-insensitively, so a case variant of an opted-out address
is still suppressed. There is no address-book,
account, alias or group-membership lookup. Suppressing a person's user ID does not
prove every alternate DM chat/group/address for them is suppressed; record each
known identity. `require_consent: true` blocks unrecorded alternate addresses.

## Decision rules

| Rule | Result |
|---|---|
| Suppressed recipient | **block**, always; approval or new consent cannot override |
| Missing consent for this channel | **block** by default |
| Outside known recipient-local permitted hours | **block** |
| Unknown/missing/invalid recipient timezone | **approve**; never infer location |
| Pending or unanswered outbound in this thread | **approve**, however old |
| Configured minimum gap not elapsed, even after a reply | **approve** |
| Not an exact owner-filled approved template | **approve** |
| Every applicable rule passes | no Gatekeeper veto; other Hermes guards still apply |
| Invalid settings, unreadable/corrupt storage, log failure or evaluation error | **block** recognized sends |

`block` outranks `approve`. The default permitted window is **08:00 inclusive to
21:00 exclusive**, in the stored IANA timezone, with DST handled by `zoneinfo`.
Overnight windows are supported; equal endpoints are invalid. Region/state
windows are **owner-supplied**, not a built-in jurisdiction or legal database.

An `approve` directive requests Hermes's native approval gate. It is not an
independent observation of a fresh human answer: host approval modes (including
smart/YOLO/off), unattended behavior and cached scopes remain host-owned. With no
human or approval bridge present (for example a plain scripted turn) the host fails
closed and the send does not run. But `hermes -z`/`--oneshot`, `--yolo` and
`approvals.mode: off` auto-approve, so in those modes every `approve` rule above is
a no-op and only the `block` rules (suppression, consent, quiet hours, errors)
still stop a send. Gatekeeper
never auto-answers a prompt or disables a guard. Its rule key binds the current
arguments/session/call, but it does not override host approval policy. Policy is
checked at the hook boundary, not rechecked after a delayed approval; a suppression
or policy change while a call is waiting does not retroactively cancel that call.
Use a host configuration requiring human review; do not rely on this as universal
or immutable outbound authorization.

## Owner setup and commands

Every `/gatekeeper` command, including status/log, requires a local session: the
host-supplied `platform` is `cli`, `tui`, `desktop` or `local` and `source` is either
`None` or a source whose platform is `local` (Hermes runs slash commands of local
sessions in the gateway and passes such a source). Messaging platforms, remote
sources and missing context are refused. This trusts the local
OS/session owner; it is not a second authentication factor. These commands are
not agent-callable tools. All examples below are invented demo data.

```text
/gatekeeper
/gatekeeper log 10
/gatekeeper optout +1-555-0100
/gatekeeper consent +1-555-0101 sms synthetic-form 2026-01-01 America/Chicago TEST
/gatekeeper consent demo@example.com email synthetic-form 2026-01-01 unknown
/gatekeeper revoke +1-555-0101 sms
/gatekeeper variables +1-555-0101 sms '{"topic":"TEST"}'
/gatekeeper reply +1-555-0101 sms
/gatekeeper reply 15550101 telegram 42
```

Consent stores recipient hash, channel, source, date, timezone and optional region.
`unknown` explicitly records no timezone. `revoke` retains location/variable metadata
but removes consent. New consent never removes suppression. V1 deliberately has
**no unsuppress command and no approval override** for an optout.

`reply` is the owner's attestation that a reply was actually observed in that
recipient/channel/thread. It also settles that thread's uncertain pending sends;
use it only after independently checking them. It grants no consent and lifts no
suppression. Log output shows timestamps, channel, shortened recipient hash,
rule and outcome, never message text or exception details.

### Settings

Under `plugins.entries.hermes-gatekeeper.settings` (or the plugin's settings UI):

```yaml
require_consent: true
start: "08:00"
end: "21:00"
region_windows:
  TEST: ["09:00", "20:00"]
min_gap_seconds: 0
templates:
  - "Demo notice for ${topic}."
stop_keywords: [STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT]
```

Template variables come **only** from local-owner recipient records, never tool
arguments/model-provided fill values. `$topic` and `${topic}` are simple string
substitutions; `$$` means a literal dollar sign. No Python expressions, attribute
access or recursive substitution. Missing variables do not match. Case, whitespace
and punctuation must match exactly. With no templates (the default), every message
requires approval. `min_gap_seconds` defaults to 0 and adds an optional gap of up to
2,678,400 seconds; it never expires an unanswered-thread hold. Setting
`require_consent: false` disables only the consent check—not suppression, quiet
hours, threading or wording. It is an explicit reduction in protection.

## STOP and inbound visibility

The public `post_gateway_admission` hook supplies authorized, routed-profile,
normalized `platform/source/message_id/text` snapshots. Whole-text matching after
whitespace trimming is case-insensitive: `STOP` matches, `please stop later` does
not. No fuzzy, substring or language inference occurs.

On an observed STOP, Gatekeeper suppresses the sender ID and, for a DM, its chat
ID too. It consumes that admitted message silently, without sending confirmation.
A group STOP suppresses its sender, **not the entire group**. Ordinary observed
DM replies are recorded for that exact destination/thread; group replies do not
clear DM history. When message IDs are present, reply observations are deduplicated
so replaying an old inbound event cannot clear a newer outbound.

This is **not a raw all-inbound hook**: rejected, ignored, internal, paused/control,
pending-approval/clarify, running-session steering and idle slash-command traffic
may never reach it. Messages outside Hermes are invisible. Record unseen optouts
with `/gatekeeper optout` and unseen replies with `/gatekeeper reply`. A reply
never creates consent. If inbound storage/identity observation fails, the running
service latches further recognized sends blocked. Repair the records (including
any missed optout) and reload; a restart alone does not reconstruct missed events.

## Storage, failure behavior and disclosure

The public `plugins.plugin_storage.plugin_data_dir()` helper selects this plugin's
active-profile data directory; Gatekeeper does not reconstruct home from raw
`HERMES_HOME`, read credential/config files or import `hermes_cli` internals.
It creates `data.db` there with owner-only permissions (directory 0700, file 0600),
using SQLite transactions and explicitly closed connections. Permission/storage
errors fail closed. Linux/macOS only; no cross-profile/shared-ledger override.

Each gated decision records UTC epoch time, channel, SHA-256 recipient/thread IDs,
message SHA-256, stable rule and outcome. Uninspectable calls use an unresolved
identity and hash their input envelope. Inbound STOP decisions, consent source/date,
timezone/region, owner template variables, pending/sent/failed thread events and
inbound-event hashes are also stored. **No raw outbound/inbound message-body log
exists.** Identity columns store hashes, not raw recipient IDs. Source strings and template variables
are owner-entered plaintext and can contain sensitive content; approved templates
live in the owner's settings. Hashes are pseudonymous, not encryption or anonymity,
and short/repeated message text or addresses can be guessed. No retention pruning
is automatic; back up and retain the profile-local database according to your policy.

Send evaluation, logging and reservations share an immediate SQLite transaction,
so concurrent routine sends cannot both pass on an empty thread. A reservation
counts as ours before dispatch; it is not proof of delivery. Explicit host
`blocked`/`cancelled` outcomes with a matching tool-call ID release that reservation.
Confirmed success moves the outbound ordering boundary to observation time. Unknown,
partial, skipped, missing-ID or missing-observer results remain conservative pending
holds; an automatic inbound reply cannot unlock a still-pending send. After a true
observation failure, repair/reload is required. Normal expected rejections do not
poison service health. Decision outcomes are policy decisions, not delivery receipts
or proof that a human approved.

**No network calls, subprocesses, model calls, telemetry, credential reads, external
file scans or background jobs are made by the plugin itself.** It reads only its
settings via `ctx`, hook arguments/results/inbound snapshots in memory, and its own
persistent data. Error messages/log lines never echo tool arguments or exception
text. It cannot repair a host that fails to load/register the plugin, intercept
unseen execution paths, or guarantee an audit write when storage itself is broken;
recognized sends are blocked in the latter case.

## Contributor workflow (local checkout, not the catalog install path)

From a checkout of this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -W error --tb=short
.venv/bin/python -m examples.dry_run
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

Tests and the dry-run use invented data, temporary SQLite and synthetic public host
contexts; they never send messages. Behavior against a real Hermes host (plugin
loader, hook dispatcher, approval gate, local-session slash-command context) is
exercised separately with `hermes plugins validate`/`doctor` and the manual checks in
`docs/HOST-CONTRACTS.md`.
