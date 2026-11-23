#!/usr/bin/env python3
"""Owner-only Gatekeeper administration. Run it from your own terminal, not through Claude.

Same commands as the Hermes plugin's /gatekeeper command, plus two for this version:

  gatekeeper_admin.py                       status
  gatekeeper_admin.py log [1-50]
  gatekeeper_admin.py optout <recipient>
  gatekeeper_admin.py consent <recipient> <channel> <source> <YYYY-MM-DD> <timezone|unknown> [region]
  gatekeeper_admin.py revoke <recipient> <channel>
  gatekeeper_admin.py reply <recipient> <channel> [thread]
  gatekeeper_admin.py variables <recipient> <channel> '<JSON object>'
  gatekeeper_admin.py check-policy          validate policy.json
  gatekeeper_admin.py repair                clear the 'stay blocked' latch after you have repaired records
"""
import os
import shlex
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "engine"))

import claude_adapter as adapter  # noqa: E402
from gatekeeper.commands import command  # noqa: E402
from gatekeeper.service import Gatekeeper  # noqa: E402
from gatekeeper.storage import Ledger  # noqa: E402


def run(argv, environ=None):
    directory = adapter.data_dir(environ)
    policy = adapter.load_policy(directory)
    if argv[:1] == ["check-policy"]:
        if policy.error:
            return "Gatekeeper: policy.json is invalid. Recognized sends stay blocked until it is fixed."
        return ("Gatekeeper: policy.json is valid (or absent, which means defaults). "
                f"Configured send tools: {len(policy.send_tools)}.")
    if argv[:1] == ["repair"]:
        cleared = adapter.clear_latch(directory)
        return "Gatekeeper: latch cleared." if cleared else "Gatekeeper: no latch was set."
    service = Gatekeeper(policy.settings, Ledger(adapter.connect_for(directory)), config_error=policy.error)
    if os.path.lexists(os.path.join(directory, adapter.UNHEALTHY_FILE)):
        service.unhealthy.set()
    return command(service, shlex.join(argv), platform="cli")


if __name__ == "__main__":
    print(run(sys.argv[1:]))
