"""Tests for the Claude Code Gatekeeper plugin (stdlib unittest).

Nothing here sends a message. Tool calls are plain dictionaries shaped like Claude Code's hook
events, evaluated by the adapter or by the real hook script run as a subprocess. Recipients are
invented. Temp dirs live under the Hermes scratch directory, resolved with realpath.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PLUGIN = os.path.join(HERE, "..", "gatekeeper")
PLUGIN = os.path.realpath(PLUGIN)
ENGINE = os.path.join(PLUGIN, "engine")
HOOK = os.path.join(PLUGIN, "hooks", "gatekeeper_hook.py")
ADMIN = os.path.join(PLUGIN, "scripts", "gatekeeper_admin.py")
SCRATCH = os.path.realpath(os.path.expanduser("~/.hermes/cache/scratch"))
if not os.path.isdir(SCRATCH):
    SCRATCH = os.path.realpath(tempfile.gettempdir())

sys.path.insert(0, ENGINE)
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
import claude_adapter as adapter  # noqa: E402
import gatekeeper_admin as admin  # noqa: E402

CANARY = "CANARY-5b1d9e"
PHONE = "+1-555-0100"
TOOL = "mcp__fake__send_sms"
SEND_TOOLS = [{"tool": "mcp__fake__send_sms", "channel": "sms", "recipient": "to", "message": "body"}]
TEMPLATE = "Demo notice for ${topic}."
DAY = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)    # 09:00 in America/Chicago
NIGHT = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)   # 00:00 in America/Chicago


def policy(**settings):
    base = {"templates": [TEMPLATE]}
    base.update(settings)
    return {"settings": base, "send_tools": SEND_TOOLS}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(dir=SCRATCH, prefix="gk-claude-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.env = {"GATEKEEPER_DIR": self.dir}
        self.n = 0

    def write_policy(self, data):
        with open(os.path.join(self.dir, "policy.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def owner(self, *argv):
        return admin.run(list(argv), self.env)

    def consent(self, phone=PHONE, channel="sms", zone="America/Chicago", topic="TEST"):
        self.owner("consent", phone, channel, "synthetic-form", "2026-01-01", zone)
        self.owner("variables", phone, channel, json.dumps({"topic": topic}))

    def event(self, kind="PreToolUse", tool=TOOL, tool_input=None, call=None):
        self.n += 1
        if tool_input is None:
            tool_input = {"to": PHONE, "body": "Demo notice for TEST."}
        return {"session_id": "s1", "hook_event_name": kind, "tool_name": tool,
                "tool_input": tool_input, "tool_use_id": call or "toolu_%d" % self.n}

    def pre(self, now=DAY, **kw):
        return adapter.pre_tool_use(self.event(**kw), self.dir, now=now)

    def post(self, event, now=DAY):
        event = dict(event, hook_event_name="PostToolUse")
        return adapter.post_tool_use(event, self.dir, now=now)

    @staticmethod
    def decision(output):
        return None if output is None else output["hookSpecificOutput"]["permissionDecision"]

    @staticmethod
    def reason(output):
        return output["hookSpecificOutput"]["permissionDecisionReason"]


class TestEngineCopy(unittest.TestCase):
    def test_engine_is_identical_to_the_hermes_package(self):
        source = os.path.join(REPO, "gatekeeper")
        copy = os.path.join(ENGINE, "gatekeeper")
        names = sorted(n for n in os.listdir(source) if n.endswith(".py"))
        self.assertEqual(names, sorted(n for n in os.listdir(copy) if n.endswith(".py")))
        for name in names:
            with open(os.path.join(source, name), "rb") as a, open(os.path.join(copy, name), "rb") as b:
                self.assertEqual(hashlib.sha256(a.read()).hexdigest(), hashlib.sha256(b.read()).hexdigest(), name)

    def test_no_network_or_subprocess_in_new_code(self):
        for path in (os.path.join(ENGINE, "claude_adapter.py"), HOOK):
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for word in ("socket", "urllib", "http.client", "requests", "subprocess", "os.system", "os.popen"):
                self.assertNotIn(word, text, (path, word))


class TestPolicyFile(Base):
    def test_missing_policy_means_defaults(self):
        self.assertFalse(adapter.load_policy(self.dir).error)

    def test_valid_policy_loads_send_tools(self):
        self.write_policy(policy())
        loaded = adapter.load_policy(self.dir)
        self.assertFalse(loaded.error)
        self.assertEqual([t.tool for t in loaded.send_tools], [TOOL])
        self.assertIn("1", self.owner("check-policy"))

    def test_invalid_policies_are_errors(self):
        bad = [
            {"unknown": 1},
            {"settings": {"nope": 1}},
            {"settings": {"start": "25:00"}},
            {"settings": {"require_consent": "yes"}},
            {"send_tools": [{"tool": "send_sms", "channel": "sms", "recipient": "to", "message": "body"}]},
            {"send_tools": [{"tool": TOOL, "channel": "SMS", "recipient": "to", "message": "body"}]},
            {"send_tools": [{"tool": TOOL, "channel": "sms", "recipient": "to", "message": "to"}]},
            {"send_tools": [{"tool": TOOL, "channel": "sms", "recipient": "to", "message": "body", "thread": "t"}]},
            {"send_tools": [{"tool": TOOL, "channel": "sms", "recipient": "to", "message": "body", "extra": 1}]},
            {"send_tools": "x"},
        ]
        for data in bad:
            with self.subTest(data=data):
                self.write_policy(data)
                self.assertTrue(adapter.load_policy(self.dir).error)
                self.assertIn("invalid", self.owner("check-policy"))

    def test_unparseable_policy_is_an_error(self):
        with open(os.path.join(self.dir, "policy.json"), "w") as handle:
            handle.write("{not json")
        self.assertTrue(adapter.load_policy(self.dir).error)

    def test_symlinked_policy_is_refused(self):
        real = os.path.join(self.dir, "elsewhere.json")
        with open(real, "w") as handle:
            json.dump(policy(), handle)
        os.symlink(real, os.path.join(self.dir, "policy.json"))
        self.assertTrue(adapter.load_policy(self.dir).error)

    def test_invalid_policy_blocks_a_configured_send_and_keeps_escalating(self):
        self.write_policy({"settings": {"start": "99:99"}, "send_tools": SEND_TOOLS})
        self.consent()
        # send_tools could not be read, so the tool is just a send-looking MCP name: held, not parsed.
        self.assertEqual(self.decision(self.pre()), "ask")
        output = self.pre(tool="mcp__x__send_email", tool_input={"to": "recipient-1"})
        self.assertEqual(self.decision(output), "ask")
        # a literal imsg send is a recognized send and is blocked while the policy is invalid
        out = self.pre(tool="Bash", tool_input={"command": "imsg send --service sms --to +15550100 --text 'Demo notice for TEST.'"})
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("gate_unavailable", self.reason(out))


class TestConfiguredMcpSend(Base):
    def setUp(self):
        super().setUp()
        self.write_policy(policy())

    def test_no_consent_is_denied(self):
        output = self.pre()
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("no_consent", self.reason(output))

    def test_routine_send_with_every_check_passing_has_no_veto(self):
        self.consent()
        self.assertIsNone(self.pre())

    def test_opt_out_is_absolute_and_survives_new_consent(self):
        self.consent()
        self.owner("optout", PHONE)
        self.assertIn("suppressed", self.reason(self.pre()))
        self.consent()
        output = self.pre()
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("suppressed", self.reason(output))

    def test_opt_out_matches_case_variants(self):
        self.owner("optout", "Demo-User-1")
        self.write_policy({"settings": {"templates": ["Hi."]},
                           "send_tools": [{"tool": "mcp__fake__send_mail", "channel": "chat", "recipient": "to", "message": "body"}]})
        self.owner("consent", "demo-user-1", "chat", "form", "2026-01-01", "unknown")
        output = self.pre(tool="mcp__fake__send_mail", tool_input={"to": "demo-user-1", "body": "Hi."})
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("suppressed", self.reason(output))

    def test_quiet_hours_are_denied_in_the_recipients_local_time(self):
        self.consent()
        output = self.pre(now=NIGHT)
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("quiet_hours", self.reason(output))

    def test_region_window_overrides_the_default_window(self):
        self.write_policy(policy(region_windows={"TEST": ["10:00", "20:00"]}))
        self.owner("consent", PHONE, "sms", "synthetic-form", "2026-01-01", "America/Chicago", "TEST")
        self.owner("variables", PHONE, "sms", json.dumps({"topic": "TEST"}))
        self.assertIn("quiet_hours", self.reason(self.pre(now=DAY)))  # 09:00 local, window opens at 10:00

    def test_unknown_timezone_is_held_not_guessed(self):
        self.consent(zone="unknown")
        output = self.pre()
        self.assertEqual(self.decision(output), "ask")
        self.assertIn("unknown_timezone", self.reason(output))

    def test_unapproved_wording_is_held(self):
        self.consent()
        output = self.pre(tool_input={"to": PHONE, "body": "Demo notice for TEST!"})
        self.assertEqual(self.decision(output), "ask")
        self.assertIn("unapproved_wording", self.reason(output))

    def test_no_templates_means_every_message_is_held(self):
        self.write_policy({"settings": {}, "send_tools": SEND_TOOLS})
        self.consent()
        self.assertEqual(self.decision(self.pre()), "ask")

    def test_unanswered_thread_is_held_until_the_owner_records_a_reply(self):
        self.consent()
        first = self.event()
        self.assertIsNone(adapter.pre_tool_use(first, self.dir, now=DAY))
        self.post(first)
        output = self.pre()
        self.assertEqual(self.decision(output), "ask")
        self.assertIn("unanswered", self.reason(output))
        self.owner("reply", PHONE, "sms")
        self.assertIsNone(self.pre())

    def test_a_send_that_never_reported_back_still_counts_as_pending(self):
        self.consent()
        self.assertIsNone(self.pre())  # reserved before dispatch, no PostToolUse follows
        self.assertIn("unanswered", self.reason(self.pre()))

    def test_minimum_gap_holds_even_after_a_reply(self):
        self.write_policy(policy(min_gap_seconds=3600))
        self.consent()
        first = self.event()
        self.assertIsNone(adapter.pre_tool_use(first, self.dir, now=DAY))
        self.post(first)
        self.owner("reply", PHONE, "sms")
        output = self.pre()
        self.assertEqual(self.decision(output), "ask")
        self.assertIn("minimum_gap", self.reason(output))

    def test_revoked_consent_is_denied(self):
        self.consent()
        self.owner("revoke", PHONE, "sms")
        self.assertIn("no_consent", self.reason(self.pre()))

    def test_require_consent_false_skips_only_the_consent_check(self):
        self.write_policy(policy(require_consent=False))
        self.owner("variables", PHONE, "sms", json.dumps({"topic": "TEST"}))
        self.assertEqual(self.decision(self.pre()), "ask")  # still no timezone and no variables record
        self.owner("optout", PHONE)
        self.assertEqual(self.decision(self.pre()), "deny")

    def test_uninspectable_configured_calls_are_denied(self):
        self.consent()
        for tool_input in ({"to": PHONE, "body": "Demo notice for TEST.", "media_url": "x"},
                           {"to": PHONE, "body": 5}, {"to": 5, "body": "x"}, {"body": "x"}, "text"):
            with self.subTest(tool_input=tool_input):
                output = self.pre(tool_input=tool_input)
                self.assertEqual(self.decision(output), "deny")
                self.assertIn("uninspectable", self.reason(output))

    def test_ignored_fields_are_allowed_when_listed(self):
        entry = dict(SEND_TOOLS[0], ignore=["subject"])
        self.write_policy({"settings": {"templates": [TEMPLATE]}, "send_tools": [entry]})
        self.consent()
        self.assertIsNone(self.pre(tool_input={"to": PHONE, "body": "Demo notice for TEST.", "subject": "x"}))

    def test_thread_field_for_thread_channels(self):
        entry = {"tool": "mcp__fake__send_tg", "channel": "telegram", "recipient": "chat", "message": "text", "thread": "topic"}
        self.write_policy({"settings": {"templates": ["Hi."]}, "send_tools": [entry]})
        self.owner("consent", "12345", "telegram", "form", "2026-01-01", "unknown")
        out = self.pre(tool="mcp__fake__send_tg", tool_input={"chat": "12345", "text": "Hi.", "topic": 42})
        self.assertEqual(self.decision(out), "ask")  # unknown timezone, parsed fine
        self.assertIn("unknown_timezone", self.reason(out))

    def test_pattern_matches_several_tools(self):
        entry = dict(SEND_TOOLS[0], tool="mcp__fake__send_*")
        self.write_policy({"settings": {"templates": [TEMPLATE]}, "send_tools": [entry]})
        self.consent()
        self.assertIsNone(self.pre(tool="mcp__fake__send_sms"))

    def test_decisions_log_hashes_not_text(self):
        self.consent()
        self.pre(tool_input={"to": PHONE, "body": CANARY})
        with open(os.path.join(self.dir, "data.db"), "rb") as handle:
            blob = handle.read()
        self.assertNotIn(CANARY.encode(), blob)
        self.assertNotIn(b"5550100", blob)
        log = self.owner("log", "5")
        self.assertNotIn(CANARY, log)
        self.assertIn("unapproved_wording", log)

    def test_reasons_never_echo_message_text(self):
        self.consent()
        self.assertNotIn(CANARY, self.reason(self.pre(tool_input={"to": PHONE, "body": CANARY})))

    def test_database_and_directory_permissions(self):
        self.consent()
        self.pre()
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, "data.db")).st_mode), 0o600)


class TestBash(Base):
    SEND = "imsg send --service sms --to +15550100 --text 'Demo notice for TEST.'"

    def setUp(self):
        super().setUp()
        self.write_policy(policy())

    def test_ordinary_commands_are_left_alone(self):
        for command in ("date", "echo hello", "ls -la", "git status", "imsg chats --limit 3"):
            with self.subTest(command=command):
                self.assertIsNone(self.pre(tool="Bash", tool_input={"command": command}))

    def test_literal_imsg_send_is_checked_like_any_other_send(self):
        output = self.pre(tool="Bash", tool_input={"command": self.SEND})
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("no_consent", self.reason(output))
        self.consent(phone="+15550100")
        self.assertIsNone(self.pre(tool="Bash", tool_input={"command": self.SEND}))

    def test_wrapped_or_compound_sends_are_denied_not_guessed(self):
        for command in ("echo hi && " + self.SEND, "sh -c \"" + self.SEND + "\"", "imsg send --to +15550100 --text hi",
                        "imsg send --service sms --to $NUMBER --text hi"):
            with self.subTest(command=command):
                output = self.pre(tool="Bash", tool_input={"command": command})
                self.assertEqual(self.decision(output), "deny")
                self.assertIn("uninspectable", self.reason(output))

    def test_bash_send_that_exits_zero_moves_to_sent(self):
        self.consent(phone="+15550100")
        first = self.event(tool="Bash", tool_input={"command": self.SEND})
        self.assertIsNone(adapter.pre_tool_use(first, self.dir, now=DAY))
        self.post(first)
        self.assertIn("unanswered", self.reason(self.pre(tool="Bash", tool_input={"command": self.SEND})))


class TestUnconfiguredMcpTools(Base):
    def test_send_looking_names_are_held_without_a_policy_check(self):
        for name in ("mcp__acme__send_email", "mcp__acme__reply_to_thread", "mcp__x__create_post", "mcp__srv__sendSMS"):
            with self.subTest(name=name):
                output = self.pre(tool=name, tool_input={"to": "someone", "text": CANARY})
                self.assertEqual(self.decision(output), "ask")
                self.assertIn("cannot check consent/STOP/quiet hours", self.reason(output))
                self.assertNotIn(CANARY, self.reason(output))

    def test_read_only_and_unrelated_names_pass_through(self):
        for name in ("mcp__github__list_issues", "mcp__gmail__list_messages", "mcp__gmail__draft_email", "mcp__fs__read_file"):
            with self.subTest(name=name):
                self.assertIsNone(self.pre(tool=name, tool_input={"q": "x"}))

    def test_allow_tools_and_extra_patterns(self):
        self.write_policy({"settings": {"allow_tools": ["mcp__acme__send_email"], "extra_send_tool_patterns": ["mcp__acme__*push*"]}})
        self.assertIsNone(self.pre(tool="mcp__acme__send_email", tool_input={}))
        self.assertEqual(self.decision(self.pre(tool="mcp__acme__web_push", tool_input={})), "ask")

    def test_escalation_can_be_switched_off(self):
        self.write_policy({"settings": {"escalate_unrecognized_sends": False}})
        self.assertIsNone(self.pre(tool="mcp__acme__send_email", tool_input={}))

    def test_built_in_tools_are_not_touched(self):
        for tool in ("Read", "Glob", "Grep", "WebFetch", "SendMessage", "Agent"):
            self.assertIsNone(self.pre(tool=tool, tool_input={"x": 1}))


class TestOwnerOnlyRecords(Base):
    def test_agent_cannot_write_the_records(self):
        for tool, tool_input in (("Write", {"file_path": os.path.join(self.dir, "policy.json"), "content": "{}"}),
                                 ("Edit", {"file_path": os.path.join(self.dir, "data.db")}),
                                 ("NotebookEdit", {"notebook_path": os.path.join(self.dir, "x.ipynb")})):
            with self.subTest(tool=tool):
                self.assertEqual(self.decision(self.pre(tool=tool, tool_input=tool_input)), "deny")

    def test_writes_elsewhere_are_not_touched(self):
        self.assertIsNone(self.pre(tool="Write", tool_input={"file_path": os.path.join(SCRATCH, "x.txt"), "content": "x"}))

    def test_agent_cannot_run_the_admin_tool_or_touch_the_directory(self):
        for command in ("python3 /somewhere/scripts/gatekeeper_admin.py optout +15550100",
                        "rm -rf " + self.dir, "sqlite3 " + os.path.join(self.dir, "data.db") + " .tables",
                        "cat ~/.claude/gatekeeper/policy.json"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(self.pre(tool="Bash", tool_input={"command": command})), "deny")

    def test_symlink_into_the_directory_is_resolved(self):
        link = os.path.join(SCRATCH, "gk-link-%d" % os.getpid())
        os.symlink(self.dir, link)
        self.addCleanup(os.unlink, link)
        self.assertEqual(self.decision(self.pre(tool="Write", tool_input={"file_path": os.path.join(link, "policy.json")})), "deny")


class TestLatch(Base):
    def test_latch_blocks_recognized_sends_until_the_owner_repairs(self):
        self.write_policy(policy())
        self.consent()
        self.assertIsNone(self.pre())
        adapter._latch(self.dir)
        output = self.pre()
        self.assertEqual(self.decision(output), "deny")
        self.assertIn("gate_unavailable", self.reason(output))
        self.assertIn("latch cleared", self.owner("repair"))
        self.owner("reply", PHONE, "sms")
        self.assertIsNone(self.pre())

    def test_status_reports_counts(self):
        self.consent()
        self.assertIn("contacts: 1", self.owner())


class TestHookProcess(Base):
    """The real script, fed Claude Code's JSON on stdin."""

    def run_hook(self, payload, raw=None):
        env = dict(os.environ, GATEKEEPER_DIR=self.dir, HOME=self.dir)
        data = raw if raw is not None else json.dumps(payload).encode("utf-8")
        return subprocess.run([sys.executable, HOOK], input=data, capture_output=True, env=env, timeout=30)

    def test_deny_output_shape(self):
        self.write_policy(policy())
        done = self.run_hook(self.event(tool_input={"to": PHONE, "body": CANARY}))
        self.assertEqual(done.returncode, 0)
        out = json.loads(done.stdout)
        self.assertEqual(set(out), {"hookSpecificOutput"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertNotIn(CANARY.encode(), done.stdout + done.stderr)

    def test_ask_output_shape(self):
        done = self.run_hook(self.event(tool="mcp__acme__send_email", tool_input={"to": "recipient-1"}))
        out = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual((done.returncode, out["permissionDecision"]), (0, "ask"))
        self.assertNotIn("Hermes", out["permissionDecisionReason"])

    def test_non_send_calls_print_nothing(self):
        for payload in (self.event(tool="Bash", tool_input={"command": "date"}),
                        self.event(tool="Read", tool_input={"file_path": "x"}),
                        self.event(kind="PostToolUse", tool="Bash", tool_input={"command": "date"}),
                        {"hook_event_name": "SessionStart"}):
            done = self.run_hook(payload)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b"", b""))

    def test_garbage_input_exits_quietly(self):
        for raw in (b"", b"not json", b"[]", b"null"):
            done = self.run_hook(None, raw=raw)
            self.assertEqual((done.returncode, done.stdout), (0, b""))

    def test_a_clean_run_leaves_no_files_for_non_sends(self):
        self.run_hook(self.event(tool="Bash", tool_input={"command": "date"}))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data.db")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "policy.json")))

    def test_main_swallows_adapter_errors_into_a_deny_for_pre_events(self):
        out = io.StringIO()
        broken = {"GATEKEEPER_DIR": os.path.join(self.dir, "policy.json", "nested")}
        with open(os.path.join(self.dir, "policy.json"), "w") as handle:
            handle.write("{}")
        code = adapter.main(io.StringIO(json.dumps(self.event(tool="Bash", tool_input={"command": "imsg send --service sms --to +15550100 --text hi"}))), out, broken)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")


class TestPackaging(unittest.TestCase):
    def load(self, *parts):
        with open(os.path.join(PLUGIN, *parts), encoding="utf-8") as handle:
            return json.load(handle)

    def test_manifest(self):
        manifest = self.load(".claude-plugin", "plugin.json")
        self.assertEqual(manifest["name"], "axiom-gatekeeper")
        self.assertEqual(manifest["displayName"], "Gatekeeper")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["author"], {"name": "Deploy Axiom"})
        self.assertEqual(manifest["license"], "MIT")
        self.assertTrue(os.path.isfile(os.path.join(PLUGIN, ".claude-plugin", "icon.png")))

    def test_hooks_use_exec_form_and_fail_closed_on_pre_tool_use(self):
        hooks = self.load("hooks", "hooks.json")["hooks"]
        pre = hooks["PreToolUse"][0]
        self.assertEqual(pre["hooks"][0]["onFailure"], "block")
        self.assertEqual(pre["hooks"][0]["command"], "python3")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/gatekeeper_hook.py", pre["hooks"][0]["args"])
        self.assertNotIn("onFailure", hooks["PostToolUse"][0]["hooks"][0])
        self.assertEqual(set(hooks), {"PreToolUse", "PostToolUse"})

    def test_marketplace(self):
        with open(os.path.join(REPO, ".claude-plugin", "marketplace.json"), encoding="utf-8") as handle:
            market = json.load(handle)
        self.assertEqual(market["name"], "deploy-axiom-gatekeeper")
        self.assertEqual(market["plugins"][0]["name"], "axiom-gatekeeper")
        self.assertTrue(os.path.isdir(os.path.join(REPO, market["plugins"][0]["source"])))


if __name__ == "__main__":
    unittest.main()
