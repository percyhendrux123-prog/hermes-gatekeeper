"""Claude Code adapter for the Gatekeeper policy engine.

The policy engine in ``engine/gatekeeper/`` is a byte-for-byte copy of the Hermes plugin's
package (a test keeps the two identical). This file is the only new logic: it turns a Claude
Code ``PreToolUse`` / ``PostToolUse`` event into the call shape the engine already understands,
and turns the engine's answer back into a Claude Code decision.

Mapping of the engine's two outcomes:

* ``block``   -> ``permissionDecision: "deny"``  (the call does not run; Claude reads the reason)
* ``approve`` -> ``permissionDecision: "ask"``   (the call is held for the owner's yes or no;
                 in a run with nobody to ask, Claude Code denies it)
* ``pass``    -> no output; Gatekeeper has no veto and Claude Code's normal permission flow applies.

Nothing here sends a message, opens a network connection or starts a process.
"""
from dataclasses import fields
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
import os
import re
import sqlite3
import stat
import sys

from gatekeeper.classify import Uninspectable
from gatekeeper.config import Settings
from gatekeeper.consent import channel_id
from gatekeeper.service import Gatekeeper
from gatekeeper.storage import Ledger

POLICY_FILE = "policy.json"
DB_FILE = "data.db"
UNHEALTHY_FILE = "unhealthy"
THREAD_CHANNELS = frozenset({"telegram", "discord", "slack"})
_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_BASH_TOOLS = frozenset({"Bash"})
_FILE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "MultiEdit"})
RECORD_MARKERS = ("gatekeeper_admin", ".claude/gatekeeper")


# --------------------------------------------------------------------------- locations

def data_dir(environ=None):
    """The owner's Gatekeeper directory: GATEKEEPER_DIR, else <Claude config dir>/gatekeeper."""
    env = os.environ if environ is None else environ
    explicit = env.get("GATEKEEPER_DIR")
    if explicit:
        return os.path.realpath(os.path.expanduser(explicit))
    base = env.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.realpath(os.path.join(os.path.expanduser(base), "gatekeeper"))


def prepare(directory):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)


def connect_for(directory):
    def connect():
        prepare(directory)
        path = os.path.join(directory, DB_FILE)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("invalid database file")
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        return sqlite3.connect(path, timeout=10)
    return connect


# --------------------------------------------------------------------------- policy

class SendTool:
    """How one configured MCP send tool maps onto a recipient and a message."""

    KEYS = {"tool", "channel", "recipient", "message", "thread", "ignore"}

    def __init__(self, tool, channel, recipient, message, thread=None, ignore=()):
        self.tool, self.channel, self.recipient = tool, channel, recipient
        self.message, self.thread, self.ignore = message, thread, tuple(ignore)

    @classmethod
    def parse(cls, entry):
        if not isinstance(entry, dict) or set(entry) - cls.KEYS or not {"tool", "channel", "recipient", "message"} <= set(entry):
            raise ValueError("invalid send tool")
        tool = entry["tool"]
        if (not isinstance(tool, str) or not tool.startswith("mcp__") or len(tool) > 128
                or any(c.isspace() for c in tool)):
            raise ValueError("send tool names must be mcp__ tool names or patterns")
        channel = channel_id(entry["channel"])
        names = [entry["recipient"], entry["message"]] + ([entry["thread"]] if entry.get("thread") else [])
        ignore = entry.get("ignore", [])
        if not isinstance(ignore, list) or len(ignore) > 32:
            raise ValueError("invalid ignore list")
        for name in names + ignore:
            if not isinstance(name, str) or not _FIELD.fullmatch(name):
                raise ValueError("invalid field name")
        if len(set(names + ignore)) != len(names + ignore):
            raise ValueError("field names must be distinct")
        if entry.get("thread") and channel not in THREAD_CHANNELS:
            raise ValueError("thread is only supported for telegram, discord and slack")
        return cls(tool, channel, entry["recipient"], entry["message"], entry.get("thread") or None, ignore)

    def matches(self, tool_name):
        return fnmatchcase(tool_name, self.tool)

    def to_args(self, tool_input):
        """Engine ``send_message`` arguments, or ValueError when the call cannot be inspected."""
        if not isinstance(tool_input, dict):
            raise ValueError("invalid input")
        allowed = {self.recipient, self.message, *self.ignore} | ({self.thread} if self.thread else set())
        if set(tool_input) - allowed:
            raise ValueError("unsupported send options")
        recipient, message = tool_input.get(self.recipient), tool_input.get(self.message)
        if not isinstance(recipient, str) or not isinstance(message, str):
            raise ValueError("recipient and literal message required")
        target = self.channel + ":" + recipient
        if self.thread and tool_input.get(self.thread) not in (None, ""):
            thread = tool_input[self.thread]
            if not isinstance(thread, (str, int)) or isinstance(thread, bool):
                raise ValueError("invalid thread")
            target += ":" + str(thread)
        return {"target": target, "message": message}


class Policy:
    def __init__(self, settings=None, send_tools=(), error=False):
        self.settings = settings or Settings()
        self.send_tools = tuple(send_tools)
        self.error = error


def load_policy(directory):
    """Read ``policy.json``. A missing file means defaults; an unreadable or invalid one means
    recognized sends stay blocked (the engine's own fail-closed rule)."""
    path = os.path.join(directory, POLICY_FILE)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return Policy()
    except OSError:
        return Policy(error=True)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return Policy(error=True)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = None
            data = json.load(handle)
        if not isinstance(data, dict) or set(data) - {"settings", "send_tools"}:
            raise ValueError("unknown policy keys")
        raw = data.get("settings", {})
        known = {f.name for f in fields(Settings)}
        if not isinstance(raw, dict) or set(raw) - known:
            raise ValueError("unknown settings")
        settings = Settings.parse(raw)
        tools = data.get("send_tools", [])
        if not isinstance(tools, list) or len(tools) > 128:
            raise ValueError("invalid send tools")
        return Policy(settings, [SendTool.parse(entry) for entry in tools])
    except Exception:
        return Policy(error=True)
    finally:
        if descriptor is not None:
            os.close(descriptor)


# --------------------------------------------------------------------------- decisions

def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _ask(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                   "permissionDecisionReason": reason}}


def _from_directive(directive):
    if not directive:
        return None
    message = directive.get("message", "Gatekeeper: held.").replace(" through Hermes", "")
    return _deny(message) if directive.get("action") == "block" else _ask(message)


def touches_records(tool, tool_input, directory):
    """Best-effort: stop the agent from editing or running the owner's records and admin tool.

    The owner changes consent, opt-outs and policy from their own terminal. This is a name and path
    check on the tools the hook sees, not a sandbox.
    """
    if not isinstance(tool_input, dict):
        return False
    root = os.path.realpath(directory)
    if tool in _FILE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(path, str):
            real = os.path.realpath(os.path.expanduser(path))
            return real == root or real.startswith(root + os.sep)
        return False
    if tool in _BASH_TOOLS:
        command = tool_input.get("command")
        if isinstance(command, str):
            return any(marker in command for marker in (root, directory) + RECORD_MARKERS)
    return False


def _service(directory, policy, now):
    service = Gatekeeper(policy.settings, Ledger(connect_for(directory)), now=lambda: now,
                         config_error=policy.error)
    if os.path.lexists(os.path.join(directory, UNHEALTHY_FILE)):
        service.unhealthy.set()
    return service


def _engine_call(tool, tool_input, policy):
    """(engine tool name, engine args) for a Claude Code tool call, or None when it is not ours."""
    if tool in _BASH_TOOLS:
        return "terminal", {"command": tool_input.get("command") if isinstance(tool_input, dict) else None}
    if tool.startswith("mcp__"):
        for send_tool in policy.send_tools:
            if send_tool.matches(tool):
                return "send_message", send_tool
        return tool, tool_input
    return None


def pre_tool_use(event, directory, now=None):
    """Hook output (a dict) for a PreToolUse event, or None to leave the call alone."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool, str):
        return None
    if touches_records(tool, tool_input, directory):
        return _deny("Gatekeeper: its records, policy and admin tool are owner-only. "
                     "The owner changes them from their own terminal, not through the agent.")
    policy = load_policy(directory)
    mapped = _engine_call(tool, tool_input, policy)
    if mapped is None:
        return None
    now = now or datetime.now(timezone.utc)
    service = _service(directory, policy, now)
    name, args = mapped
    context = {"session_id": event.get("session_id", ""), "tool_call_id": event.get("tool_use_id", "")}
    if isinstance(args, SendTool):
        try:
            args = args.to_args(tool_input)
        except Exception:
            return _from_directive(service.error("uninspectable", tool, tool_input))
    return _from_directive(service.before(name, args, **context))


def post_tool_use(event, directory, now=None):
    """Record a completed send (the engine's ``sent`` state). Failures leave the hold in place."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool, str):
        return
    policy = load_policy(directory)
    mapped = _engine_call(tool, tool_input, policy)
    if mapped is None or mapped[0] not in {"terminal", "send_message"}:
        return
    name, args = mapped
    now = now or datetime.now(timezone.utc)
    service = _service(directory, policy, now)
    context = {"session_id": event.get("session_id", ""), "tool_call_id": event.get("tool_use_id", "")}
    try:
        if isinstance(args, SendTool):
            args = args.to_args(tool_input)
        result = json.dumps({"exit_code": 0} if name == "terminal" else {"success": True})
        service.after(name, args, result=result, status="ok", **context)
    except Exception:
        service.unhealthy.set()
    if service.unhealthy.is_set():
        _latch(directory)


def _latch(directory):
    """Keep the engine's 'observation failed, stay blocked' latch across hook processes."""
    try:
        prepare(directory)
        descriptor = os.open(os.path.join(directory, UNHEALTHY_FILE), os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
    except OSError:
        pass


def clear_latch(directory):
    try:
        os.unlink(os.path.join(directory, UNHEALTHY_FILE))
        return True
    except FileNotFoundError:
        return False


def main(stdin=None, stdout=None, environ=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        event = json.loads(stdin.read())
        if not isinstance(event, dict):
            return 0
    except Exception:
        return 0  # cannot tell what the call was; Claude Code carries on
    directory = data_dir(environ)
    kind = event.get("hook_event_name")
    try:
        if kind == "PreToolUse":
            output = pre_tool_use(event, directory)
            if output:
                stdout.write(json.dumps(output))
        elif kind == "PostToolUse":
            post_tool_use(event, directory)
    except Exception:
        if kind == "PreToolUse":
            stdout.write(json.dumps(_deny("Gatekeeper: could not evaluate this call. Blocked.")))
    return 0
