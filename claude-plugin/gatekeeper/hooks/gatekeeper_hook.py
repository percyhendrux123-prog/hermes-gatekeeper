#!/usr/bin/env python3
"""Claude Code hook entry point for Gatekeeper (PreToolUse and PostToolUse).

Reads one hook event on stdin and, for a PreToolUse event on a send, prints a permission decision.
Everything else exits 0 with no output. The logic lives in engine/claude_adapter.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "engine"))

from claude_adapter import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
