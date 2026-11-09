from dataclasses import fields
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_catalog_match_runtime_registration(monkeypatch, tmp_path):
    from test_registration import load, Context
    from gatekeeper.config import Settings
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    catalog = yaml.safe_load((ROOT / "CATALOG-ENTRY.yaml").read_text())
    ctx = Context()
    load(monkeypatch, tmp_path).register(ctx)
    assert manifest["name"] == catalog["name"] == "hermes-gatekeeper"
    assert catalog["title"] == "Gatekeeper"
    assert manifest["version"] == catalog["version"] == "0.1.0"
    assert manifest["requires_hermes"] == catalog["requires_hermes"] == ">=0.22.5"
    assert set(manifest["provides_hooks"]) == set(ctx.hooks) == set(catalog["capabilities"]["provides_hooks"])
    assert manifest["provides_tools"] == catalog["capabilities"]["provides_tools"] == []
    schema = manifest["config_schema"]
    assert set(schema) == {f.name for f in fields(Settings)}
    assert Settings.parse({k: v["default"] for k, v in schema.items()}) == Settings()
    assert catalog["sha"] == "TBD"
    assert manifest["license"] == "MIT"


def test_readme_disclosure_and_catalog_install_first():
    readme = (ROOT / "README.md").read_text()
    assert "hermes plugins install hermes-gatekeeper" in readme
    assert "not legal advice and not a compliance guarantee" in readme
    assert "not legal advice and not a compliance guarantee" in (ROOT / "CATALOG-ENTRY.yaml").read_text()
    assert "post_gateway_admission" in readme
    assert "not currently registered" in readme
    assert "0.1.0" in (ROOT / "CHANGELOG.md").read_text()
    assert "Percy Keith Stewart" in (ROOT / "LICENSE").read_text()


def test_python_310_syntax_and_runtime_no_transport_imports():
    import ast
    paths = [ROOT / "__init__.py", *sorted((ROOT / "gatekeeper").glob("*.py"))]
    forbidden = {"subprocess", "socket", "urllib", "requests", "httpx", "http", "hermes_cli"}
    for path in paths:
        tree = ast.parse(path.read_text(), feature_version=(3, 10))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(name.split(".")[0] in forbidden for name in names), (path.name, names)


def test_public_files_carry_no_internal_references():
    banned = ("AXIOM", "scaffold", "hermes-ref", "BUILD-PLAN", "REVIEW-BRIEF", "OWNER-TBD", "Standing")
    for path in [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "CATALOG-ENTRY.yaml",
                 *(ROOT / "docs").glob("*.md"), *(ROOT / "gatekeeper").glob("*.py")]:
        text = path.read_text()
        if path.name == "README.md":
            # The README's "Works with" section names the sibling plugins on purpose.
            text = text.split("## Works with")[0]
        assert not [word for word in banned if word in text], path.name
    catalog = (ROOT / "CATALOG-ENTRY.yaml").read_text()
    assert "repo: https://github.com/percyhendrux123-prog/hermes-gatekeeper\n" in catalog


def test_catalog_and_readme_state_the_real_send_path():
    readme = (ROOT / "README.md").read_text()
    catalog = (ROOT / "CATALOG-ENTRY.yaml").read_text()
    for text in (readme, catalog):
        assert "terminal" in text and "execute_code" in text
    assert "not currently registered" in readme and "no model-callable send_message" in catalog
    assert "connectors__" in readme and "cronjob_manage" in readme


def test_docs_state_the_unrecognized_send_tool_behavior_and_its_limits():
    readme = (ROOT / "README.md").read_text()
    catalog = (ROOT / "CATALOG-ENTRY.yaml").read_text()
    host = (ROOT / "docs" / "HOST-CONTRACTS.md").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    for name in ("escalate_unrecognized_sends", "extra_send_tool_patterns", "allow_tools"):
        assert name in readme and name in changelog
    assert "unrecognized send tool <name>; owner approval required" in readme
    assert "cannot check consent/STOP/quiet hours" in readme and "cannot check consent/STOP/quiet hours" in host
    assert "unrecognized_send_tool" in readme and "unrecognized_send_tool" in changelog
    for text in (readme, host):
        assert "--yolo" in text and "approvals.mode" in text
    assert "python -c" in readme and "computer-use" in readme
    assert "owner approval" in catalog and "browser" in catalog.lower() and "subprocess" in catalog
    assert "connectors__" in catalog and "cronjob_manage" in catalog


def test_readme_vocabulary_matches_the_code_tables():
    from gatekeeper import escalate
    readme = (ROOT / "README.md").read_text()
    for token in sorted(escalate.SEND_TOKENS | escalate.NOUN_TOKENS | escalate.READ_TOKENS | {"draft"}):
        assert f"`{token}`" in readme, token
    for verb in sorted(escalate.CREATE_VERBS):
        assert verb in readme, verb
    for site in sorted(escalate.POST_OBJECTS):
        assert site in readme, site
