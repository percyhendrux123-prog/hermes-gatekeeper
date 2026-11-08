"""A deliberately bounded classifier, not a shell parser or an egress firewall."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
import shlex

from .consent import channel_id
from .storage import canonical_recipient


class Uninspectable(ValueError):
    """A recognized send cannot safely be evaluated."""


@dataclass(frozen=True)
class Send:
    channel: str
    recipient: str
    thread: str
    message: str


def target_parts(target):
    if not isinstance(target, str) or ":" not in target:
        raise ValueError("explicit target required")
    channel, recipient = target.split(":", 1)
    channel = channel_id(channel)
    thread = ""
    if channel in {"telegram", "discord", "slack"} and ":" in recipient:
        recipient, thread = recipient.split(":", 1)
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", thread):
            raise ValueError("invalid thread")
    if recipient.startswith("#"):
        raise ValueError("use stable ids, not directory names")
    return channel, canonical_recipient(recipient), thread


def native(args):
    if args.get("action", "send") == "list":
        return []
    if set(args) - {"target", "message", "action"} or args.get("action", "send") != "send":
        raise ValueError("unsupported send options")
    message = args.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("literal message required")
    message.encode("utf-8")  # reject lone surrogates rather than approve different delivered text
    return [Send(*target_parts(args.get("target")), message)]


def terminal(args):
    command = args.get("command")
    if not isinstance(command, str):
        raise ValueError("invalid terminal input")
    normalized = command.replace("\\\n", "")
    raw_match = re.search(r"\b(?:imsg|hermes)\s+send\b", normalized.replace("'", "").replace('"', ""))
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        if raw_match:
            raise ValueError("invalid recognized command")
        return []
    found = raw_match or any(PurePosixPath(a).name in {"imsg", "hermes"} and b == "send"
                             for a, b in zip(tokens, tokens[1:]))
    if not found:
        return []
    lex = shlex.shlex(normalized, posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    syntax = list(lex)
    if any(token and set(token) <= set(";&|()<>") for token in syntax) or any(c in normalized for c in "$`\n\r"):
        raise ValueError("complex recognized shell command")
    if len(tokens) < 3 or PurePosixPath(tokens[0]).name not in {"imsg", "hermes"} or tokens[1] != "send":
        raise ValueError("wrapped send")
    program = PurePosixPath(tokens[0]).name
    if program == "hermes" and tokens[2] in {"--list", "-l"} and len(tokens) in {3, 4}:
        return []
    options, positional = {}, []
    rest = iter(tokens[2:])
    allowed = {"--to", "-t"} if program == "hermes" else {"--to", "--text", "--service"}
    for token in rest:
        if token.startswith("-"):
            if token not in allowed:
                raise ValueError("unsupported send option")
            name = "--to" if token == "-t" else token
            if name in options:
                raise ValueError("duplicate option")
            options[name] = next(rest)  # missing values fail closed
        else:
            positional.append(token)
    if program == "hermes":
        if len(positional) != 1:
            raise ValueError("literal message required")
        return native({"target": options["--to"], "message": positional[0]})
    if positional or options.get("--service") not in {"sms", "imessage"}:
        raise ValueError("explicit imsg service required")
    return native({"target": options["--service"] + ":" + options["--to"], "message": options["--text"]})


def classify(tool_name, args, _depth=0):
    name = tool_name.rsplit(".", 1)[-1] if isinstance(tool_name, str) else ""
    if name not in {"send_message", "terminal", "tool_call", "parallel"}:
        return []
    try:
        if not isinstance(args, dict) or _depth > 8:
            raise ValueError("invalid call")
        if name == "send_message":
            return native(args)
        if name == "terminal":
            return terminal(args)
        field, name_key, args_key = ("calls", "name", "arguments") if name == "tool_call" else ("tool_uses", "recipient_name", "parameters")
        calls = args[field]
        if not isinstance(calls, list) or len(calls) > 128:
            raise ValueError("invalid batch")
        sends = []
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get(name_key), str) or not isinstance(call.get(args_key), dict):
                raise ValueError("invalid entry")
            sends.extend(classify(call[name_key], call[args_key], _depth + 1))
        return sends
    except (ValueError, KeyError, StopIteration, TypeError, UnicodeError) as exc:
        raise Uninspectable("recognized send or batch cannot be inspected") from exc
