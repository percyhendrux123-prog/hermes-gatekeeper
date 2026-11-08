# Gatekeeper local verification and operator handoff

STATUS: blocked / unshipped. No push, PR, install, live data change or message send.

## Implemented

All requested rule modules, public hook/owner-command wiring, local hashed SQLite
log, normalized inbound STOP/DM observation, conservative terminal/native/batch
classification, manifest, catalog draft, README, CHANGELOG 0.1.0 and MIT license.
The exact public-hook scope is narrower than universal outbound enforcement;
see README and HOST-CONTRACTS before accepting a release claim.

## Real execution

- Python 3.10.21: `uv run --no-project --python 3.10 --with 'pytest>=8,<9' --with 'PyYAML>=6,<7' python -m pytest -q -W error --tb=short` — exit 0, **163 passed in 0.15s**. Full stdout: TEST-OUTPUT-3.10.txt.
- Python 3.12.3: same command with `--python 3.12` — exit 0, **163 passed in 0.20s**. Full stdout: TEST-OUTPUT-3.12.txt.
- Python 3.14.7: `.venv/bin/python -m pytest -q -W error --tb=short --cov=gatekeeper --cov-report=term-missing` — exit 0, **163 passed in 0.16s**, **97% statement coverage** for gatekeeper modules (476 statements, 12 unexecuted). Full stdout: TEST-OUTPUT-3.14.txt. This does not include native-host coverage.
- `.venv/bin/python -m examples.dry_run` — exit 0. Real gate/SQLite decisions: no consent block; approved routine pass; unanswered approve; observed reply permits next routine; changed wording approve; STOP block. Seven decisions including inbound STOP, zero transports. Public delivery observations are explicitly synthetic. Full stdout: DRY-RUN-OUTPUT.txt.
- `git diff --check` and `.venv/bin/python -m compileall -q __init__.py gatekeeper examples tests` — exit 0.
- Tests also parse production code with the Python 3.10 grammar and assert no transport/private-hermes_cli imports in the runtime tree. Registration tests use synthetic public contexts; they are not native PluginManager/doctor runs.

## Adversarial review

Supplemental read-only delegated source review found three concrete defects:

1. Shell glob expansion could change approved wording after shlex inspection.
2. Removing continuations globally changed single-quoted message content.
3. An expected uninspectable blocked observation unnecessarily latched the service unhealthy.

All three reproduced as failing tests, then fixed in **3bed5d8**. Expansion-bearing
and raw-newline recognized commands now block even when quoted; expected blocked
observations no longer poison health. Regression suite passes across all three
interpreters. Earlier self-tests also fixed observer replay and pending/reply/send
ordering races in 36df52e and b31f37a.

This supplemental review is **not native codereview-profile approval**. Required
attempt: `hermes -p codereview chat --query-file /home/cua/repos/hermes-gatekeeper/docs/REVIEW-BRIEF.md -Q`.
Actual result: **exit 127, `bash: line 8: hermes: command not found`**. No Hermes
installation, credentials or live profile config were introduced to work around it.

## Remaining operator gates

1. Export committed `main` from /home/cua/repos/hermes-gatekeeper through the approved Space flow before the RAM-backed Space stops.
2. Run required codereview on the host using REVIEW-BRIEF.md; fix real findings and re-run tests. Run native `hermes plugins validate . --install-deps` and `hermes plugins doctor . --ci` against the exact candidate. No native pass is claimed here.
3. Remove/omit staged hermes-ref before release/admission scanning. The attempted `git rm -r hermes-ref` was denied by the unattended approval gate; it did not execute, and no alternate deletion route was used. The references include unrelated copied core/example imports, not runtime dependencies. Keep them in scaffold history, not the release payload.
4. Confirm the explicitly disclosed partial boundary is acceptable: send_message is not core model-tool registered; direct helpers, ordinary gateway replies, arbitrary APIs/scripts, later argument rewrites, host approval policy/cache and changes made while a call waits for approval remain outside this gate's guarantee. An all-outbound guarantee requires a host-owned final delivery seam.
5. Choose/create the public repository, replace OWNER-TBD and `sha: TBD` in CATALOG-ENTRY.yaml with the verified URL/full pin, and obtain Percy/default-operator publication approval. No URL was invented.
6. Standing proof attempt **standing:33** was **unavailable**, not a mismatch or pass: the public hook-doc HTTP target was not owner-allowlisted/reachable under its scope. No passing proof for task completion was obtained. Owner-allowlist a relevant reachable proof or run the appropriate host-side task verification before closing.

## Rollback

Safe pre-build commit: **b7f37b5**. Nothing was installed or deployed. Reverting source
or disabling the plugin does not automatically remove persistent optouts; preserve
the profile-local data directory. A failed or absent plugin is not a network firewall.
