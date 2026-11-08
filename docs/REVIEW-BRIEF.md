# Gatekeeper adversarial review brief — A290 / t_5dbd0ce1

Repository: /home/cua/repos/hermes-gatekeeper. Review base b7f37b5. Local-only candidate.
Try to break the work against this acceptance list. Report concrete defects only,
with file/line and reproduction; no generic suggestions, edits, sends or live data.

## Goal and acceptance

- Deterministic hooks govern recognized pre_tool_call send_message and terminal imsg send/hermes send.
- Suppression is persistent and absolute at the gate; renewed consent/approval cannot lift it.
- Explicit per-recipient/channel consent required by default, with source/date metadata.
- Known recipient-local permitted window 08:00 inclusive–21:00 exclusive by default; owner region overrides/DST, unknown timezone approve, known outside block.
- Unanswered or pending outbound in a recipient/channel/thread holds for approval; minimum gap adds a hold even after replies. Reservations/logging atomic across concurrent calls; observer replays and inbound races cannot silently unlock.
- Exact owner-filled templates only; tool/model fill fields cannot create routine approval. Non-template wording approve.
- Every gated decision recorded with timestamp/channel/hash/rule/outcome, no raw body log; storage/evaluation failure blocks recognized sends without leaking exception text.
- Owner commands: all status/log/mutations local platform AND source=None, no remote/missing-context administration.
- Public normalized post_gateway_admission automatically suppresses observed STOP-family sender and DM target; ordinary DM replies are deduplicated and never grant consent.
- Runtime uses only public ctx/storage APIs, no private hermes_cli imports, core patches, network/subprocess/model calls.
- Manifest/catalog defaults and actual registrations align; README disclosures reflect exact boundaries, no compliance guarantee; Python 3.10+ tests strict warnings.

## Changed files

New root __init__.py; gatekeeper/{storage,suppression,consent,quiet_hours,double_text,history,wording,config,classify,service,commands,inbound}.py;
tests/test_*.py; examples/dry_run.py; plugin.yaml; CATALOG-ENTRY.yaml; README.md;
CHANGELOG.md; LICENSE; requirements-dev.txt; pytest.ini; docs/*.md; .gitignore.

## Tests

- .venv/bin/python -m pytest -q -W error --tb=short
- .venv/bin/python -m pytest -q -W error --tb=short --cov=gatekeeper --cov-report=term-missing
- .venv/bin/python -m examples.dry_run
- uv run --no-project --python 3.10 --with 'pytest>=8,<9' --with 'PyYAML>=6,<7' python -m pytest -q -W error --tb=short

Temporary SQLite and invented demo identities only. Dry-run synthetic host observations
are explicitly not delivery proof. No transport executes.

## Known host/release boundaries (do not mistake these for full enforcement)

send_message is not currently model-tool registered in supplied core; direct helper
sends and ordinary gateway replies do not traverse this hook. Arbitrary scripts/APIs,
obfuscated sends, alias/group-member resolution, later argument rewrites and host
approval policies/caches are not controlled. Checks are snapshots before approval,
not a final delivery seam. README/catalog state those limits prominently.

The admitted inbound hook omits rejected/control/approval/steering/slash traffic.
Manual owner optout/reply remains necessary for unseen events. No raw adapters.

Native Hermes validate/doctor and required codereview CLI are absent in this Space.
CATALOG-ENTRY owner URL and sha are intentional explicit placeholders for AXIOM.
hermes-ref is staged design-reference material; its removal was refused by the
unattended approval gate, so AXIOM must omit it before admission scan/publication.

## Supplemental review already performed (not native-profile approval)

Read-only delegate found three verified defects: shell glob/brace expansion changes
wording, global continuation removal changes single-quoted content, and expected
blocked uninspectable inputs latched service unhealthy. Added failing regressions,
then fixed all three in 3bed5d8: expansion-bearing/raw-newline recognized commands
now block conservatively, and expected blocked observations no longer poison health.
No further supplemental review is claimed. Native codereview remains required.
