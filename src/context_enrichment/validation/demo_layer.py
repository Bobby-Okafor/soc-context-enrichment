"""Generated validation and conformance evidence for the demo-layer extension."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Callable

from context_enrichment.assistant.contracts import AssistantIntent
from context_enrichment.assistant.policy import INTENT_POLICY
from context_enrichment.assistant.tools import AssistantTools
from context_enrichment.cli.demo import render_demo, render_demo_json, run_demo
from context_enrichment.domain.models import RelationshipState
from context_enrichment.domain.serialization import stable_id


REQUIRED_PUBLIC_DOCS = (
    "ARCHITECTURE.md",
    "TRUST_BOUNDARIES.md",
    "VALIDATION.md",
    "DEMO_GUIDE.md",
    "PROVIDER_INTEGRATION.md",
    "PRODUCTIONIZATION.md",
)


def build_demo_layer_report(repository: Path, fixture_root: Path) -> dict[str, Any]:
    repository = repository.resolve()
    fixture_root = fixture_root.resolve()
    checks: list[dict[str, Any]] = []

    def check(check_id: str, description: str, operation: Callable[[], tuple[bool, str]]) -> None:
        try:
            passed, evidence = operation()
            checks.append({"check_id": check_id, "description": description, "outcome": "PASS" if passed else "FAIL", "evidence": evidence})
        except Exception as exc:
            checks.append({"check_id": check_id, "description": description, "outcome": "ERROR", "evidence": f"{type(exc).__name__}: {exc}"})

    results = {key: run_demo(key, fixture_root=fixture_root) for key in ("primary", "false-join", "provider-failure")}
    repeats = {key: run_demo(key, fixture_root=fixture_root) for key in results}

    check("DLV-01", "Primary demo establishes accepted supported context", lambda: (
        results["primary"].packet.execution_status.value == "RELATED_CONTEXT_FOUND"
        and results["primary"].response.execution_status == "RELATED_CONTEXT_FOUND"
        and bool(results["primary"].response.supporting_evidence),
        f"packet={results['primary'].packet.packet_id}; evidence={len(results['primary'].response.supporting_evidence)}",
    ))
    check("DLV-02", "False-join demo creates no relationship narrative", lambda: (
        results["false-join"].packet.execution_status.value == "NO_RELIABLE_CONTEXT_FOUND"
        and not results["false-join"].response.relationship_results
        and not results["false-join"].response.supporting_evidence
        and "TKT-V04-SIMILAR" not in results["false-join"].response.narrative,
        "V04 rejected similar identity; no assistant relationship/evidence output",
    ))
    check("DLV-03", "Provider failure remains explicit partial availability", lambda: (
        results["provider-failure"].packet.execution_status.value == "PARTIAL_ENRICHMENT"
        and any(item.code == "PROVIDER_UNAVAILABLE" for item in results["provider-failure"].response.provider_diagnostics)
        and "does not establish that no context exists" in results["provider-failure"].response.narrative,
        "V16 PARTIAL_ENRICHMENT with PROVIDER_UNAVAILABLE and unavailable-path narrative",
    ))
    check("DLV-04", "All demo outputs replay deterministically", lambda: (
        all(render_demo_json(results[key]) == render_demo_json(repeats[key]) and render_demo(results[key]) == render_demo(repeats[key]) for key in results),
        "primary, false-join, and provider-failure structured and terminal outputs repeated identically",
    ))
    check("DLV-05", "All nine intents map to finite plans", lambda: (
        set(INTENT_POLICY) == set(AssistantIntent) and all(plan and plan[-1].value == "BUILD_RESPONSE" and len(plan) == len(set(plan)) for plan in INTENT_POLICY.values()),
        f"intent_count={len(INTENT_POLICY)}",
    ))
    check("DLV-06", "Controlled tool surface is exact", lambda: (
        {name for name in dir(AssistantTools) if not name.startswith("_")} == {
            "enrich_alert", "get_relationship", "get_supporting_evidence", "get_contradicting_evidence",
            "get_missing_information", "get_confidence_factors", "get_provider_diagnostics", "get_recommended_review_areas",
        },
        "eight declared tools; no dynamic/general tool",
    ))
    check("DLV-07", "Assistant traces all comprehensive tool calls", lambda: (
        len(results["primary"].response.trace.tool_calls) == 8
        and tuple(call.sequence for call in results["primary"].response.trace.tool_calls) == tuple(range(1, 9))
        and results["primary"].response.trace.actions_executed == results["primary"].response.trace.deterministic_plan,
        f"tool_calls={len(results['primary'].response.trace.tool_calls)}; completion={results['primary'].response.trace.completion_state.value}",
    ))
    check("DLV-08", "Supported relationship claims cite evidence", lambda: (
        all(
            any(item.evidence_id in results["primary"].response.narrative for item in results["primary"].response.supporting_evidence if item.source_provider == relationship.source_provider and item.context_record_reference == relationship.context_record_reference)
            for relationship in results["primary"].response.relationship_results
            if relationship.relationship_state in {RelationshipState.SUPPORTED, RelationshipState.PARTIALLY_SUPPORTED}
        ),
        f"consulted_evidence={len(results['primary'].response.trace.evidence_ids_consulted)}",
    ))
    check("DLV-09", "Not-supported records are not narrated as supported", lambda: (
        "NOT_SUPPORTED. Evidence:" not in results["primary"].response.narrative,
        "NOT_SUPPORTED results carry no supporting relationship citation",
    ))
    check("DLV-10", "Default model path is disabled", lambda: (
        all(item.response.model_adapter_status == "DISABLED_NO_MODEL" for item in results.values()),
        "all three scenarios use DISABLED_NO_MODEL",
    ))
    check("DLV-11", "Core packages do not depend on assistant", lambda: _core_has_no_assistant_import(repository))
    check("DLV-12", "Assistant does not import providers or core domain algorithms", lambda: _assistant_import_boundary(repository))
    check("DLV-13", "Public architecture, validation, demo, integration, and production documents exist", lambda: (
        all((repository / "docs" / name).is_file() for name in REQUIRED_PUBLIC_DOCS),
        f"public_docs={sum((repository / 'docs' / name).is_file() for name in REQUIRED_PUBLIC_DOCS)}",
    ))

    pass_count = sum(item["outcome"] == "PASS" for item in checks)
    fail_count = sum(item["outcome"] == "FAIL" for item in checks)
    error_count = sum(item["outcome"] == "ERROR" for item in checks)
    scenario_results = {
        key: {
            "scenario_id": item.scenario_id,
            "packet_id": item.packet.packet_id,
            "response_id": item.response.response_id,
            "execution_status": item.response.execution_status,
            "confidence": item.packet.confidence.level.value,
            "tool_call_count": len(item.response.trace.tool_calls),
            "model_adapter_status": item.response.model_adapter_status,
        }
        for key, item in results.items()
    }
    identity = stable_id("demo-layer-validation", checks, scenario_results)
    return {
        "schema_version": "demo_layer_validation_v1",
        "run_id": identity,
        "check_count": len(checks),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": error_count,
        "passed": fail_count == 0 and error_count == 0,
        "checks": checks,
        "scenario_results": scenario_results,
        "determinism_result": "PASS" if checks[3]["outcome"] == "PASS" else checks[3]["outcome"],
        "false_association_count": 0 if checks[1]["outcome"] == "PASS" else 1,
        "boundary": "Synthetic engineering reference only; analyst judgment remains authoritative.",
    }


def _core_has_no_assistant_import(repository: Path) -> tuple[bool, str]:
    package = repository / "src" / "context_enrichment"
    offenders = []
    for path in package.rglob("*.py"):
        subsystem = path.relative_to(package).parts[0]
        if subsystem in {"assistant", "cli", "validation"}:
            continue
        if "context_enrichment.assistant" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(repository).as_posix())
    return not offenders, "offenders=" + (", ".join(offenders) if offenders else "none")


def _assistant_import_boundary(repository: Path) -> tuple[bool, str]:
    forbidden = (
        "context_enrichment.providers",
        "context_enrichment.normalization",
        "context_enrichment.entity_resolution",
        "context_enrichment.candidate_selection",
        "context_enrichment.correlation",
        "context_enrichment.evidence",
        "context_enrichment.confidence",
        "context_enrichment.validation",
        "context_enrichment.cli",
    )
    offenders = []
    for path in (repository / "src" / "context_enrichment" / "assistant").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                values.append(node.module)
            elif isinstance(node, ast.Import):
                values.extend(alias.name for alias in node.names)
        for value in values:
            if value.startswith(forbidden):
                offenders.append(f"{path.name}:{value}")
    return not offenders, "offenders=" + (", ".join(offenders) if offenders else "none")


def write_demo_layer_report(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Demonstration Layer Validation",
        "",
        f"Run: `{report['run_id']}`",
        f"Result: `{'PASS' if report['passed'] else 'FAIL'}`",
        f"Checks: {report['pass_count']}/{report['check_count']} PASS; failures={report['fail_count']}; errors={report['error_count']}",
        f"False associations: {report['false_association_count']}",
        f"Determinism: `{report['determinism_result']}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {item['check_id']} `{item['outcome']}` — {item['description']}. Evidence: {item['evidence']}" for item in report["checks"])
    lines.extend(["", "## Demo Scenarios", ""])
    lines.extend(f"- {key}: status={item['execution_status']}; confidence={item['confidence']}; tools={item['tool_call_count']}; model={item['model_adapter_status']}" for key, item in report["scenario_results"].items())
    lines.extend(["", report["boundary"], ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
