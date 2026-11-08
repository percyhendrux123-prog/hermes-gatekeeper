"""Gatekeeper: deterministic policy hooks; no transport, model or subprocess."""
from dataclasses import fields
import logging
import os
import sqlite3
import stat

logger = logging.getLogger("hermes-gatekeeper")


def connect():
    # Public profile-aware helper owns home selection. Never reconstruct it from
    # os.environ['HERMES_HOME'] or read any core config/credential file ourselves.
    from plugins.plugin_storage import plugin_data_dir
    directory = plugin_data_dir("hermes-gatekeeper")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / "data.db"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("invalid database file")
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return sqlite3.connect(path, timeout=10)


def register(ctx):
    from .gatekeeper.config import Settings
    from .gatekeeper.service import Gatekeeper
    from .gatekeeper.storage import Ledger

    defaults = Settings()
    config_error = False
    try:
        settings = Settings.parse({f.name: ctx.get_config(f.name, default=getattr(defaults, f.name))
                                   for f in fields(Settings)})
    except Exception:
        logger.warning("Gatekeeper policy settings are invalid; recognized sends stay blocked.")
        settings, config_error = defaults, True
    service = Gatekeeper(settings, Ledger(connect), config_error=config_error)
    # No storage I/O at registration: its failure must not disable the gate.
    ctx.register_hook("pre_tool_call", service.before)
    ctx.register_hook("post_tool_call", service.after)
    ctx.register_hook("post_gateway_admission", service.inbound)
    ctx.register_command("gatekeeper", service.command,
                         description="Local-owner outbound policy status, decisions and recipient records.",
                         args_hint="[log | optout | consent | revoke | reply | variables]")
