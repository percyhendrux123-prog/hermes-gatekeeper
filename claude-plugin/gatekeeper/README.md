# Gatekeeper for Claude Code

I want my rules checked before an agent texts anyone.

Gatekeeper is a Claude Code plugin. Before a messaging tool call runs, it checks the recipient against rules you set: STOP and opt-outs, recorded consent, quiet hours, no double-texting, and approved wording. If a check fails it denies the call. If it can't tell, it holds the call for your yes or no. It never sends anything itself.

It is the Claude Code counterpart of [Gatekeeper for Hermes Agent](https://github.com/percyhendrux123-prog/hermes-gatekeeper). The policy engine is the same code, copied byte for byte into this plugin (a test fails if the two drift apart). What is new is the adapter that reads Claude Code's tool calls, and the way you tell it which tools are send tools.

**Gatekeeper enforces rules you configure. It is not legal advice and not a compliance guarantee.** Read "What it sees, and what it doesn't" before relying on it.

## What it decides

| Rule | Result in Claude Code |
|---|---|
| Suppressed recipient (opted out) | **deny**, always. Consent or approval cannot override it |
| No recorded consent for this channel | **deny** |
| Outside the recipient's local permitted hours (default 08:00 to 21:00) | **deny** |
| Recipient has no known timezone | **hold** (asks you); it never guesses a location |
| An earlier message in this thread is unanswered | **hold** |
| Minimum gap since the last message not elapsed | **hold** |
| Message is not an exact, owner-filled approved template | **hold** |
| A tool that looks like a send but isn't configured here | **hold**, and says consent, STOP and quiet hours were not checked |
| Every rule passes | no veto; Claude Code's own permission flow still applies |
| Bad `policy.json`, unreadable records, or an evaluation error | **deny** recognized sends |

"Deny" means the call does not run and Claude reads the reason. "Hold" means the hook asks for a permission decision, so Claude Code shows you the prompt. In a run with nobody to ask, such as `claude -p`, Claude Code denies a held call.

A reason never contains message text or the recipient. Records store hashes, not raw recipients or bodies.

## Install

```
claude plugin marketplace add percyhendrux123-prog/hermes-gatekeeper
claude plugin install axiom-gatekeeper@deploy-axiom-gatekeeper
```

To try it for one session without installing:

```
claude --plugin-dir ./claude-plugin/gatekeeper
```

## Before you install

- **Runs:** two `python3` command hooks (`PreToolUse` and `PostToolUse`) on `Bash`, `Write`, `Edit`, `NotebookEdit`, `MultiEdit` and MCP tools. Python 3.9 or later, standard library only.
- **Files it writes:** `~/.claude/gatekeeper/data.db` (decision log, consent, opt-outs, thread history). Directory 0700, file 0600. Set `GATEKEEPER_DIR` to use another directory. If `CLAUDE_CONFIG_DIR` is set, the default is `$CLAUDE_CONFIG_DIR/gatekeeper`.
- **Files it reads:** `policy.json` in that directory (yours), and the hook event Claude Code sends on stdin. Nothing else.
- **Network, subprocesses, model calls, telemetry, stored credentials:** none. A test checks the new code for them.
- **If the hook itself fails:** the `PreToolUse` hook is set to block on failure, so a missing `python3` or a crash blocks `Bash`, file-edit and MCP tool calls until it is fixed. That is deliberate: a gate that silently stops working is worse than one that is loud. (This is the hooks reference's `onFailure: "block"`; I did not trigger it on purpose.) The `PostToolUse` hook fails open, which only means a missed "sent" record (the engine then keeps the thread held).
- **Platform:** macOS and Linux. Not Windows.

## Tell it which tools send

A Claude Code send is a tool call, so Gatekeeper needs to know which tools those are. Put this in `~/.claude/gatekeeper/policy.json`. Every name below is invented.

```json
{
  "settings": {
    "require_consent": true,
    "start": "08:00",
    "end": "21:00",
    "region_windows": { "TEST": ["09:00", "20:00"] },
    "min_gap_seconds": 0,
    "templates": ["Demo notice for ${topic}."],
    "escalate_unrecognized_sends": true,
    "extra_send_tool_patterns": ["mcp__acme__*push*"],
    "allow_tools": []
  },
  "send_tools": [
    { "tool": "mcp__acme__send_sms", "channel": "sms", "recipient": "to", "message": "body" }
  ]
}
```

- `send_tools` lists MCP tools Gatekeeper should parse fully. `tool` is an exact name or a `*`/`?` pattern and must start with `mcp__`. `channel` is the label consent is recorded under. `recipient` and `message` name the fields in the tool's input. Optional `thread` names a thread field (Telegram, Discord and Slack channels only) and optional `ignore` lists fields it may carry without being checked. Any other field makes the call uninspectable, and an uninspectable call is denied, not guessed at.
- `settings` has the same keys and meaning as the Hermes plugin's settings (see that README). Template variables come only from your own recipient records, never from tool arguments.
- A missing `policy.json` means the defaults: consent required, no templates (so every message is held), no configured send tools.
- An invalid file blocks recognized sends until you fix it. `check-policy` below tells you whether it parses.

Three kinds of call are recognized:

1. **A configured MCP send tool.** Checked in full: STOP, consent, quiet hours, threading, wording.
2. **A literal `imsg send` or `hermes send` command in `Bash`.** Checked in full. Only simple single-line literal forms are understood: `imsg send --service sms --to +15550100 --text 'Demo notice.'`. Wrappers, pipelines, compound commands, variables, globs and anything else that expands are denied rather than guessed at. The same parser as the Hermes plugin, so it can also over-block a command that merely mentions a send.
3. **Any other MCP tool whose name looks like a send** (`mcp__x__send_email`, `mcp__y__reply_to_thread`, `mcp__z__create_post`). Held for your approval, not checked. Gatekeeper does not parse these, so it cannot see the recipient. Read-style names (`list_messages`, `draft_email`, `search_*`) pass. The vocabulary is the Hermes plugin's, applied to the tool name only.

## You record consent, opt-outs and replies from your own terminal

Consent, opt-outs and settings are yours, not the agent's. The admin tool is a script you run in your own shell. Find it under the plugin's install folder, or in a clone of this repo:

```
python3 claude-plugin/gatekeeper/scripts/gatekeeper_admin.py <command>
```

```
log 10
optout +1-555-0100
consent +1-555-0101 sms synthetic-form 2026-01-01 America/Chicago TEST
consent demo-user-1 chat synthetic-form 2026-01-01 unknown
revoke +1-555-0101 sms
variables +1-555-0101 sms '{"topic":"TEST"}'
reply +1-555-0101 sms
check-policy
repair
```

These are the Hermes `/gatekeeper` commands with the same behavior: `optout` is permanent in v1 (no unsuppress, no override); `consent` never removes a suppression; `reply` is your word that a reply was actually seen, and it also settles that thread's pending holds; `unknown` records no timezone. `check-policy` validates `policy.json`. `repair` clears the stay-blocked latch after you have repaired the records.

To stop the agent doing the same thing, the hook denies any `Write`, `Edit` or `NotebookEdit` into the Gatekeeper directory and any `Bash` command that names that directory or the admin script. That is a path and name check on the tools the hook sees, not a sandbox. Inside a session, you can still run the admin tool yourself with Claude Code's `!` shell prefix.

## What it sees, and what it doesn't

Claude Code runs the hook on every `Bash`, file-edit and MCP tool call, and Gatekeeper only acts on the three kinds above.

**Not seen at all**

- A script that sends from inside `python -c`, a Node file, `curl`, `osascript` or any other subprocess.
- Browser or computer-use driving of a messaging app.
- Built-in tools and any non-MCP tool. (`SendMessage` between agents in a team is not a message to a person and is left alone.)
- `PowerShell` commands.
- A tool whose name doesn't match the vocabulary and isn't in `send_tools`. Add a pattern to `extra_send_tool_patterns` or list it.
- Messages sent from outside Claude Code.

## Known gaps

Where Claude Code can't do what the Hermes plugin does, or where I haven't checked.

- **No inbound STOP.** Claude Code has no hook for messages arriving from your customers. The Hermes plugin sees inbound STOP and replies through its gateway. Here you record an opt-out with `optout` and an observed reply with `reply`. A STOP you never record is not known to Gatekeeper.
- **Declining a held call leaves the thread held.** Claude Code fires no event when you answer a permission prompt "no", so the held send stays counted as pending. Later sends to that thread are held until you run `reply`. The Hermes plugin gets an explicit cancelled outcome and releases it. A call that runs but fails (`PostToolUseFailure`) is also kept pending on purpose, because a failed send may have partly gone out.
- **A hold is a permission prompt, and Claude Code decides how it looks.** I checked headless runs only: held calls were denied, including under `--permission-mode bypassPermissions`. I did not check the interactive prompt, auto mode, or what a settings `allow` rule does alongside a held call. When several hooks disagree, Claude Code's rule is deny over ask over allow.
- **Records protection is best effort.** A determined agent with a tool the hook doesn't see could still reach the directory. Local code and file edits can always defeat a local gate.
- **Subagents.** I did not test whether subagent tool calls reach the hook.
- **Time.** Quiet hours are tested with an injected clock, not in a live run at night.
- **Not an egress firewall or sandbox.** Same as the Hermes plugin.
- **No parity claim.** The engine's 439 Hermes tests pass in the repo, and the engine files here are identical to that code. The Claude Code side is covered by the new tests listed below and one headless run, nothing more.
- **Not on the plugin directory.** The plugin has command hooks and scripts, so it installs from GitHub.

## Try it with no install

```
python3 -m unittest discover -s claude-plugin/tests
```

The tests feed sample hook events to the adapter and to the real hook script, check the decisions, check that no message text or raw recipient reaches output or storage, and check that the engine copy matches the Hermes package. They use a temporary directory and a stand-in tool name; they never send a message and never touch `~/.claude`.

## Undo

```
claude plugin uninstall axiom-gatekeeper
claude plugin marketplace remove deploy-axiom-gatekeeper
```

Delete `~/.claude/gatekeeper/` if you no longer want the records. Opt-outs live there, so deleting it removes them too.

## How it was made

I designed it, set the rules for what it may do and refuse, and tested it on my own system. AI agents wrote the code under my spec and review. I read Python; I don't claim to write it by hand.

Percy Keith, Deploy Axiom. MIT license.
