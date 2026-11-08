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


_PROGRAMS = {"imsg", "hermes", "hermes-agent", "hermes_cli", "hermes_cli.main"}
_PROFILE_FLAGS = {"-p", "--profile"}


def _locate_send(tokens):
    """Return (program index, send index) of the first recognized send, else None.

    Hermes accepts global options before a subcommand (``hermes -p NAME send``).
    ``-p/--profile`` selects only credentials and is understood; any other global
    option has unknown arity, so a ``send`` after it is refused rather than guessed.
    """
    for i, token in enumerate(tokens):
        program = PurePosixPath(token).name
        if program not in _PROGRAMS:
            continue
        if program == "imsg":
            if tokens[i + 1:i + 2] == ["send"]:
                return i, i + 1
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            if tokens[j] in _PROFILE_FLAGS:
                j += 2
            elif tokens[j].startswith("--profile="):
                j += 1
            elif "send" in tokens[j + 1:]:
                raise ValueError("unsupported global option before send")
            else:
                break
        if j < len(tokens) and tokens[j] == "send":
            return i, j
    return None


def terminal(args):
    command = args.get("command")
    if not isinstance(command, str):
        raise ValueError("invalid terminal input")
    normalized = command.replace("\\\n", "")
    stripped = normalized.replace("'", "").replace('"', "")
    raw_match = re.search(r"\b(?:imsg|hermes)\s+send\b", stripped)
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        if raw_match or re.search(r"\b(?:imsg|hermes(?:-agent)?|hermes_cli(?:\.main)?)\b.*\bsend\b", stripped, re.S):
            raise ValueError("invalid recognized command")
        return []
    located = _locate_send(tokens)
    if located is None and not raw_match:
        return []
    lex = shlex.shlex(normalized, posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    syntax = list(lex)
    if any(token and set(token) <= set(";&|()<>") for token in syntax) or any(c in command for c in "$`\n\r*?[]{}~"):
        raise ValueError("complex or expansion-bearing recognized shell command")
    if located is None or located[0] != 0 or len(tokens) <= located[1] + 1:
        raise ValueError("wrapped send")
    program = PurePosixPath(tokens[0]).name
    rest = tokens[located[1] + 1:]
    if program != "imsg" and rest[0] in {"--list", "-l"} and len(rest) in {1, 2}:
        return []
    options, positional = {}, []
    values = iter(rest)
    allowed = {"--to", "--text", "--service"} if program == "imsg" else {"--to", "-t"}
    for token in values:
        if token.startswith("-"):
            if token not in allowed:
                raise ValueError("unsupported send option")
            name = "--to" if token == "-t" else token
            if name in options:
                raise ValueError("duplicate option")
            options[name] = next(values)  # missing values fail closed
        else:
            positional.append(token)
    if program != "imsg":
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
