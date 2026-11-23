"""Name-based escalation for send-looking tools Gatekeeper cannot parse.

Gatekeeper fully understands only ``send_message`` and literal ``hermes send`` /
``imsg send`` terminal commands. A connector, MCP or plain tool whose *name* looks
like a send is not parsed, so no consent, STOP or quiet-hours check is possible; the
owner is asked instead. This is a bounded vocabulary over tool names, not a
classifier of what a tool really does: a differently named sender is not seen
(``extra_send_tool_patterns`` lets the owner widen it, ``allow_tools`` narrows it).
"""
from fnmatch import fnmatchcase
import re

# Tools Gatekeeper already evaluates (or blocks as uninspectable) elsewhere.
KNOWN_TOOLS = frozenset({"send_message", "terminal", "tool_call", "parallel"})
_PREFIXES = frozenset({"connectors", "mcp"})
_CRON_TOOLS = frozenset({"cronjob_manage", "cronjob"})
_CRON_ACTIONS = frozenset({"create", "update", "edit", "run", "run_now", "trigger"})
_CRON_TARGET_KEYS = ("deliver", "target", "failure_deliver")

# Vocabulary (whole tokens of the tool name, lower-cased; camelCase and any
# non-alphanumeric run split words).
SEND_TOKENS = frozenset({"send", "resend", "reply", "tweet", "publish"})
NOUN_TOKENS = frozenset({"sms", "mms", "dm"})  # a messaging noun alone is a send tool
CREATE_VERBS = frozenset({"create", "new", "add", "make", "write", "submit", "compose", "schedule"})
POST_OBJECTS = frozenset({"message", "msg", "tweet", "status", "update", "comment", "reply", "text",
                          "dm", "toot", "thread", "story", "to"})
MESSAGE_TOKENS = frozenset({"message", "messages", "msg"})
MAIL_TOKENS = frozenset({"email", "mail"})
NOT_A_SEND_AFTER = frozenset({"template", "templates", "draft", "drafts", "filter", "filters", "label",
                              "labels", "rule", "rules", "folder", "folders", "history", "count"})
READ_TOKENS = frozenset({"list", "get", "search", "read", "fetch", "find", "count", "query", "lookup",
                         "view", "show", "describe", "retrieve", "download", "export", "check",
                         "history", "inspect", "summarize", "validate", "delete", "remove", "cancel",
                         "archive", "mark", "trash", "discard"})
SOCIAL_TOKENS = frozenset({"x", "twitter", "instagram", "facebook", "linkedin", "tiktok", "youtube",
                           "reddit", "mastodon", "bluesky", "threads", "pinterest", "tumblr", "social"})
NOTIFY_TARGET_NOUNS = frozenset({"user", "users", "person", "people", "channel", "channels", "team", "owner",
                                 "contact", "customer", "client", "chat", "room", "member", "human", "phone",
                                 "slack", "discord", "telegram", "whatsapp", "sms", "email", "mail"})
TARGET_KEYS = frozenset({"to", "recipient", "recipients", "target", "targets", "channel", "channel_id",
                         "chat_id", "user", "user_id", "username", "phone", "phone_number", "number",
                         "email", "address", "thread", "thread_id", "room", "destination", "deliver", "handle"})
BODY_KEYS = frozenset({"message", "text", "body", "content"})
BARE_MAIL_NAMES = frozenset({"email", "mail"})
BARE_MESSAGE_NAMES = frozenset({"message", "messages", "chat", "text"})
SEND_ACTIONS = frozenset({"send", "post", "create", "reply", "publish", "compose"})

# Human-readable summary, kept in sync with the tables above (README quotes it).
VOCABULARY = (
    "token send/resend/reply/tweet/publish; sms/mms/dm; text+message; post+"
    "(message|msg|tweet|status|update|comment|reply|text|dm|toot|thread|story|to) or "
    "(create|new|add|make|write|submit|compose|schedule)+post; "
    "(send|post|create|new|add|make|write|submit|compose|schedule)+(message|messages|msg); "
    "(compose|forward)+(email|mail|message); (create|post|add|reply)+comment on a social name; "
    "notify with a person/channel target; bare email/mail; bare message/chat/text with a send action "
    "or a target plus body; glued forms such as sendmail, sendEmail, createPost. "
    "Read, delete, cancel and draft-only leading verbs (list, get, search, read, fetch, find, count, "
    "query, lookup, view, show, describe, retrieve, download, export, check, history, inspect, "
    "summarize, validate, delete, remove, cancel, archive, mark, trash, discard, draft) keep a tool allowed."
)

_GLUED = re.compile(r"^(send|resend)(mail|email|message|messages|msg|sms|mms|text|tweet|dm|reply|notification|chat)$"
                    r"|^(post|create|new)(message|msg|tweet|status|post|comment)$")
_CAMEL = re.compile(r"([a-z0-9])([A-Z])")


def _tokens(segment):
    out = []
    for word in re.split(r"[^a-z0-9]+", _CAMEL.sub(r"\1_\2", segment).lower()):
        if not word:
            continue
        glued = _GLUED.match(word)
        out.extend(g for g in glued.groups() if g) if glued else out.append(word)
    return out


def _segments(name):
    """Tool-name segments worth reading: the tool part of ``connectors__app__tool`` /
    ``mcp__server__tool`` (the app/server name is not a verb), every segment of any
    other ``__``/``.``-delimited name, or the whole plain name."""
    parts = [p for p in re.split(r"__|\.", name) if p]
    if len(parts) > 1 and parts[0].lower() in _PREFIXES:
        return parts[2:] if len(parts) > 2 else parts[1:]
    return parts or [name]


def _vetoed(tokens, index, kind, *, sending):
    """A leading read/delete/draft verb keeps the tool allowed ('get_message', 'draft_reply').

    ``kind == 'noun'`` triggers (sms, dm, ...) are vetoed by a read verb anywhere
    ('list_sms', 'dm_search'). Verb triggers are vetoed only by a read verb *before* them
    with no 'and'/'then' between ('get_and_send' still escalates).
    """
    for i, token in enumerate(tokens):
        if token not in READ_TOKENS and not (token == "draft" and not sending):
            continue
        if kind == "noun":
            return True
        if i < index and not {"and", "then"} & set(tokens[i:index]):
            return True
    return False


def _first_hit(tokens, social):
    """Return (index, kind, sending) of the first send trigger, else None."""
    for i, token in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prev = tokens[i - 1] if i else ""
        after = tokens[i + 2] if i + 2 < len(tokens) else ""
        if token in {"send", "resend"}:
            return i, "verb", True
        if token in SEND_TOKENS:
            return i, "verb", False
        if token in NOUN_TOKENS:
            return i, "noun", False
        if token == "text" and nxt in MESSAGE_TOKENS:
            return i, "noun", False
        if token == "post" and (nxt in POST_OBJECTS or prev in CREATE_VERBS) and nxt not in NOT_A_SEND_AFTER:
            start = i - 1 if prev in CREATE_VERBS and nxt not in POST_OBJECTS else i
            return start, "verb", False
        if token in MESSAGE_TOKENS and prev in CREATE_VERBS | {"post"} and nxt not in NOT_A_SEND_AFTER:
            return i - 1, "verb", False
        if token in MESSAGE_TOKENS and nxt in {"create", "post", "new"} and after not in NOT_A_SEND_AFTER:
            return i, "verb", False
        if token in {"compose", "forward"} and set(tokens) & (MAIL_TOKENS | MESSAGE_TOKENS):
            return i, "verb", False
        if token == "comment" and social and (prev in CREATE_VERBS | {"post", "reply"} or nxt in {"create", "post"}):
            return (i - 1 if prev in CREATE_VERBS | {"post", "reply"} else i), "verb", False
    return None


def _bare_tool(tokens, args):
    if len(tokens) != 1:
        return False
    if tokens[0] in BARE_MAIL_NAMES:
        return True
    if tokens[0] not in BARE_MESSAGE_NAMES:
        return False
    action = args.get("action")
    keys = {str(k).lower() for k, v in args.items() if v not in (None, "", [], {})}
    return (isinstance(action, str) and action.strip().lower() in SEND_ACTIONS) or (
        bool(keys & TARGET_KEYS) and bool(keys & BODY_KEYS))


def _notify(tokens, all_tokens, args):
    if "notify" not in tokens:
        return False
    keys = {str(k).lower() for k, v in args.items() if v not in (None, "", [], {})}
    if keys & TARGET_KEYS or set(all_tokens) & NOTIFY_TARGET_NOUNS:
        return not any(t in READ_TOKENS for t in tokens)
    return False


def _looks_like_send(name, args):
    parts = _segments(name)
    all_tokens = [t for part in re.split(r"__|\.", name) for t in _tokens(part)]
    social = bool(set(all_tokens) & SOCIAL_TOKENS)
    for part in parts:
        tokens = _tokens(part)
        if not tokens:
            continue
        if tokens[0] in _PREFIXES and len(tokens) > 1:  # legacy single-underscore mcp_<server>_<tool>
            tokens = tokens[1:]
        hit = _first_hit(tokens, social)
        if hit and not _vetoed(tokens, hit[0], hit[1], sending=hit[2]):
            return True
        if _bare_tool(tokens, args) or _notify(tokens, all_tokens, args):
            return True
    return False


def _matches_extra(name, patterns):
    lowered = name.lower()
    candidates = {lowered, *(part.lower() for part in _segments(name))}
    return any(fnmatchcase(c, pattern.lower()) for pattern in patterns for c in candidates)


def _cron_delivers(args):
    action = args.get("action")
    if action is None or (isinstance(action, str) and action.strip().lower() not in _CRON_ACTIONS):
        return False  # list/pause/remove/... or no action; a malformed non-text action still asks
    for key in _CRON_TARGET_KEYS:
        value = args.get(key)
        if isinstance(value, str):
            if any(p.strip().lower() not in {"", "local"} for p in value.split(",")):
                return True
        elif value not in (None, "", [], {}):
            return True
    return False


def unrecognized_send(tool_name, args, settings):
    """Return None, or a short label for why this tool call needs owner approval."""
    if not getattr(settings, "escalate_unrecognized_sends", True) or not isinstance(tool_name, str) or not tool_name:
        return None
    args = args if isinstance(args, dict) else {}
    if tool_name in settings.allow_tools:
        return None
    if tool_name.rsplit(".", 1)[-1] in KNOWN_TOOLS:
        return None
    if tool_name.rsplit(".", 1)[-1].lower() in _CRON_TOOLS:
        return "scheduled delivery" if _cron_delivers(args) else None
    if _matches_extra(tool_name, settings.extra_send_tool_patterns):
        return "matches extra_send_tool_patterns"
    if _looks_like_send(tool_name, args):
        return "send-looking name"
    return None


_SAFE_NAME = re.compile(r"[A-Za-z0-9_.\-]{1,64}")


def safe_name(tool_name):
    """A tool name fit for a prompt or the log; anything odd is shown truncated and masked."""
    if _SAFE_NAME.fullmatch(tool_name):
        return tool_name
    return re.sub(r"[^A-Za-z0-9_.\-]", "?", tool_name)[:64]


def reason(tool_name, label):
    name = safe_name(tool_name)
    suffix = f" ({label})" if label == "scheduled delivery" else ""
    return (f"Gatekeeper: unrecognized send tool {name}{suffix}; owner approval required. "
            "Gatekeeper cannot check consent/STOP/quiet hours for this tool.")
