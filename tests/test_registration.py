from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]


class Context:
    def __init__(self, config=None):
        self.config = config or {}
        self.hooks = {}
        self.commands = {}
    def get_config(self, key, default=None):
        return self.config.get(key, default)
    def register_hook(self, name, callback):
        self.hooks[name] = callback
    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler


def load(monkeypatch, tmp_path):
    storage = types.ModuleType("plugins.plugin_storage")
    storage.plugin_data_dir = lambda name: tmp_path / "canonical-home" / name
    plugins = types.ModuleType("plugins")
    monkeypatch.setitem(sys.modules, "plugins", plugins)
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", storage)
    spec = importlib.util.spec_from_file_location("hermes_plugin_gatekeeper_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_public_registration_and_owner_command_real_sqlite(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "wrong-raw-env-home"))
    ctx = Context()
    module.register(ctx)
    assert set(ctx.hooks) == {"pre_tool_call", "post_tool_call", "post_gateway_admission"}
    assert set(ctx.commands) == {"gatekeeper"}
    command = ctx.commands["gatekeeper"]
    assert "consent recorded" in command("consent +1-555-0100 sms synthetic-form 2026-01-01 UTC", platform="local", source=None)
    result = ctx.hooks["pre_tool_call"](tool_name="send_message", args={"target": "sms:+1-555-0100", "message": "demo"})
    assert result["action"] in {"approve", "block"}  # runtime local clock; no templates auto-approved
    path = tmp_path / "canonical-home" / "hermes-gatekeeper" / "data.db"
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert not (tmp_path / "wrong-raw-env-home").exists()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("select count(*) from decisions").fetchone()[0] == 1


def test_invalid_config_does_not_disable_protection_hooks(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path)
    ctx = Context({"require_consent": "false"})
    module.register(ctx)
    result = ctx.hooks["pre_tool_call"](tool_name="send_message", args={"target": "sms:+1-555-0100", "message": "demo"})
    assert result["action"] == "block"
    assert "gate_unavailable" in result["message"]


def test_unavailable_public_storage_does_not_disable_hook_registration(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path)
    def refused(name):
        raise OSError("synthetic private path")
    sys.modules["plugins.plugin_storage"].plugin_data_dir = refused
    ctx = Context()
    module.register(ctx)
    assert ctx.hooks["pre_tool_call"](tool_name="send_message", args={"target": "sms:+1-555-0100", "message": "demo"})["action"] == "block"


def test_config_accessor_error_is_not_fail_open(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path)
    ctx = Context()
    def failed(*args, **kwargs):
        raise RuntimeError("synthetic config failure")
    ctx.get_config = failed
    module.register(ctx)
    assert ctx.hooks["pre_tool_call"](tool_name="send_message", args={"target": "sms:+1-555-0100", "message": "demo"})["action"] == "block"
