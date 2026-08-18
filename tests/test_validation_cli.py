from __future__ import annotations

import ast
import json
import logging
import tempfile
from pathlib import Path

from conftest import SCENARIOS
from context_enrichment.cli.main import main
from context_enrichment.validation.harness import run_validation_directory, validate_fixture_path


def test_v01_v20_authoritative_validation_gate() -> None:
    report = run_validation_directory(SCENARIOS)
    assert report.scenario_count == 20
    assert report.pass_count == 20
    assert report.fail_count == 0
    assert report.error_count == 0
    assert report.false_association_count == 0
    assert report.missed_association_count == 0
    assert report.determinism_result == "PASS"
    assert report.metrics["candidate_precision"] == 1.0
    assert report.metrics["candidate_recall"] == 1.0
    assert report.metrics["evidence_completeness"] is True


def test_validation_observability_and_fixture_containment(repo_root: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="context_enrichment.validation")
    report = run_validation_directory(SCENARIOS, repo_root / "fixtures")
    events = [json.loads(record.message)["event"] for record in caplog.records]
    assert report.pass_count == 20
    assert events.count("validation_scenario_started") == 20
    assert events.count("validation_scenario_completed") == 20
    with __import__("pytest").raises(ValueError, match="escapes configured root"):
        validate_fixture_path(repo_root / "README.md", repo_root / "fixtures")


def test_cli_enrich_render_and_validate(repo_root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="cli-test-", dir=repo_root / "validation") as temporary:
        test_path = Path(temporary)
        packet = test_path / "packet.json"
        rendered = test_path / "packet.txt"
        report = test_path / "report.json"
        markdown = test_path / "report.md"
        assert main(["enrich", str(SCENARIOS / "V01.json"), "--output", str(packet)]) == 0
        assert main(["render", str(packet), "--output", str(rendered)]) == 0
        assert main(["validate", "--scenarios", str(SCENARIOS), "--output", str(report), "--markdown", str(markdown)]) == 0
        value = json.loads(report.read_text(encoding="utf-8"))
        assert value["pass_count"] == 20
        assert "analyst judgment remains authoritative" in rendered.read_text(encoding="utf-8")
        assert markdown.is_file()


def test_no_paid_or_external_runtime_dependencies(repo_root: Path) -> None:
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "dependencies = []" in pyproject
    for path in (repo_root / "src" / "context_enrichment").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.lower())
            elif isinstance(node, ast.Import):
                imported.extend(alias.name.lower() for alias in node.names)
        assert not any(name.startswith(("engineering_automation", "control_plane")) for name in imported)
        assert "subprocess" not in imported


def test_no_real_identifiers_or_enterprise_connectors(repo_root: Path) -> None:
    scoped = [repo_root / "src", repo_root / "fixtures"]
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for root in scoped
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json", ".md"}
    )
    fragments = (
        ("chri", "stos"),
        ("service", "now"),
        ("ji", "ra"),
        ("senti", "nel"),
        ("spl", "unk"),
        ("en", "tra"),
        ("ok", "ta"),
    )
    for forbidden in ("".join(parts) for parts in fragments):
        assert forbidden not in text
