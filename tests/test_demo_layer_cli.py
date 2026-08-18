from __future__ import annotations

import json

import pytest

from context_enrichment.cli.demo import render_demo, render_demo_json, run_demo
from context_enrichment.cli.main import main


@pytest.mark.parametrize(
    ("scenario", "status"),
    [
        ("primary", "RELATED_CONTEXT_FOUND"),
        ("false-join", "NO_RELIABLE_CONTEXT_FOUND"),
        ("provider-failure", "PARTIAL_ENRICHMENT"),
    ],
)
def test_demo_scenarios_are_readable_and_authoritative(repo_root, scenario: str, status: str) -> None:
    result = run_demo(scenario, fixture_root=repo_root / "fixtures")
    rendered = render_demo(result)
    assert result.packet.execution_status.value == status
    assert result.response.execution_status == status
    for heading in (
        "ALERT",
        "CONTEXT DISCOVERY",
        "ENTITY RESOLUTION",
        "CORRELATION",
        "EVIDENCE",
        "CONFIDENCE",
        "ASSISTANT WORKFLOW",
        "ANALYST RESPONSE",
        "SAFETY / LIMITATIONS",
    ):
        assert f"\n{heading}\n" in rendered
    assert "analyst judgment remains authoritative" in rendered


def test_demo_json_and_terminal_output_are_deterministic(repo_root) -> None:
    first = run_demo("primary", fixture_root=repo_root / "fixtures")
    second = run_demo("primary", fixture_root=repo_root / "fixtures")
    assert render_demo(first) == render_demo(second)
    assert render_demo_json(first) == render_demo_json(second)
    parsed = json.loads(render_demo_json(first))
    assert parsed["assistant_response"]["trace"]["completion_state"] == "COMPLETED"


def test_false_join_demo_does_not_narrativize_rejected_record(repo_root) -> None:
    result = run_demo("false-join", fixture_root=repo_root / "fixtures")
    assert "REJECTED TKT-V04-SIMILAR" in render_demo(result)
    assert "TKT-V04-SIMILAR" not in result.response.narrative
    assert result.response.supporting_evidence == ()


def test_provider_failure_demo_explains_degraded_path(repo_root) -> None:
    result = run_demo("provider-failure", fixture_root=repo_root / "fixtures")
    assert "mock_change_provider: FAILED" in render_demo(result)
    assert "provider evidence path was unavailable" in result.response.narrative.lower()
    assert "does not establish that no context exists" in result.response.narrative


def test_one_command_cli_default_and_alternates(repo_root, capsys) -> None:
    fixture_root = str(repo_root / "fixtures")
    assert main(["demo", "--fixture-root", fixture_root]) == 0
    assert "Scenario: primary" in capsys.readouterr().out
    assert main(["demo", "--scenario", "false-join", "--fixture-root", fixture_root]) == 0
    assert "NO_RELIABLE_CONTEXT_FOUND" in capsys.readouterr().out
    assert main(["demo", "--scenario", "provider-failure", "--fixture-root", fixture_root, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["assistant_response"]["execution_status"] == "PARTIAL_ENRICHMENT"
