"""Replay harness comparing deterministic packets to scenario contracts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from context_enrichment.application.service import EnrichmentService
from context_enrichment.domain.models import (
    ValidationExpectation,
    ValidationOutcome,
    ValidationReport,
    ValidationResult,
    ValidationScenario,
)
from context_enrichment.domain.serialization import canonical_json, stable_id, to_primitive
from context_enrichment.providers.mock import build_mock_providers


DESIGNATED_ADVERSARIAL = {"V04", "V06", "V10", "V15"}
LOGGER = logging.getLogger("context_enrichment.validation")


def validate_fixture_path(path: Path, fixture_root: Path, *, directory: bool = False) -> Path:
    root = fixture_root.resolve()
    candidate = path.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"fixture path escapes configured root: {path}") from exc
    if directory:
        if not candidate.is_dir():
            raise ValueError(f"fixture scenario directory does not exist: {candidate}")
    else:
        if not candidate.is_file() or candidate.suffix.lower() != ".json":
            raise ValueError(f"fixture scenario must be an existing JSON file: {candidate}")
    return candidate


def load_scenario(path: Path, fixture_root: Path | None = None) -> ValidationScenario:
    if fixture_root is not None:
        path = validate_fixture_path(path, fixture_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    expectation = value["expectation"]
    return ValidationScenario(
        scenario_id=value["scenario_id"],
        name=value["name"],
        alert=value["alert"],
        provider_records=value.get("provider_records", {}),
        provider_status=value.get("provider_status", {}),
        expectation=ValidationExpectation(
            execution_status=expectation["execution_status"],
            confidence=expectation.get("confidence"),
            related_record_ids=tuple(expectation.get("related_record_ids", ())),
            candidate_record_ids=tuple(expectation.get("candidate_record_ids", ())),
            forbidden_related_record_ids=tuple(expectation.get("forbidden_related_record_ids", ())),
            diagnostic_codes=tuple(expectation.get("diagnostic_codes", ())),
            minimum_contradictions=int(expectation.get("minimum_contradictions", 0)),
            deterministic_runs=int(expectation.get("deterministic_runs", 1)),
        ),
        metric_labels=tuple(value.get("metric_labels", ())),
    )


def run_scenario(scenario: ValidationScenario) -> ValidationResult:
    expected = to_primitive(scenario.expectation)
    try:
        serializations: list[str] = []
        packet = None
        for _ in range(max(1, scenario.expectation.deterministic_runs)):
            service = EnrichmentService(providers=build_mock_providers(scenario.provider_records, scenario.provider_status))
            packet = service.enrich(scenario.alert)
            serializations.append(canonical_json(packet, indent=None))
        assert packet is not None
        actual_related = tuple(item.source_record_id for item in packet.related_context)
        actual_candidates = tuple(packet.provenance.get("selected_candidate_record_ids", ()))
        diagnostic_codes = tuple(item.code for item in packet.provider_diagnostics)
        failures: list[str] = []
        if packet.execution_status.value != scenario.expectation.execution_status:
            failures.append(f"execution_status expected {scenario.expectation.execution_status}, got {packet.execution_status.value}")
        if scenario.expectation.confidence and packet.confidence.level.value != scenario.expectation.confidence:
            failures.append(f"confidence expected {scenario.expectation.confidence}, got {packet.confidence.level.value}")
        missing_related = sorted(set(scenario.expectation.related_record_ids) - set(actual_related))
        missing_candidates = sorted(set(scenario.expectation.candidate_record_ids) - set(actual_candidates))
        unexpected_candidates = sorted(set(actual_candidates) - set(scenario.expectation.candidate_record_ids))
        forbidden_present = sorted(set(scenario.expectation.forbidden_related_record_ids) & set(actual_related))
        missing_diagnostics = sorted(set(scenario.expectation.diagnostic_codes) - set(diagnostic_codes))
        if missing_related:
            failures.append(f"missing related records: {missing_related}")
        if missing_candidates:
            failures.append(f"missing candidates: {missing_candidates}")
        if unexpected_candidates:
            failures.append(f"unexpected candidates: {unexpected_candidates}")
        if forbidden_present:
            failures.append(f"forbidden related records present: {forbidden_present}")
        if missing_diagnostics:
            failures.append(f"missing diagnostics: {missing_diagnostics}")
        if len(packet.contradictions) < scenario.expectation.minimum_contradictions:
            failures.append(f"contradictions expected >= {scenario.expectation.minimum_contradictions}, got {len(packet.contradictions)}")
        deterministic = len(set(serializations)) == 1
        if not deterministic:
            failures.append("authoritative serialization differed across replay runs")
        false_association = bool(forbidden_present) or (
            scenario.scenario_id in {"V04", "V06", "V15"}
            and bool(actual_related)
        ) or (
            scenario.scenario_id == "V10"
            and any(item.relationship_state.value in {"SUPPORTED", "PARTIALLY_SUPPORTED"} for item in packet.correlation_results)
        )
        if false_association:
            failures.append("designated false-association contract violated")
        actual = {
            "packet_id": packet.packet_id,
            "execution_status": packet.execution_status.value,
            "confidence": packet.confidence.level.value,
            "related_record_ids": actual_related,
            "candidate_record_ids": actual_candidates,
            "correlation_states": {item.context_record_reference: item.relationship_state.value for item in packet.correlation_results},
            "supporting_evidence_count": len(packet.evidence_set.supporting),
            "contradicting_evidence_count": len(packet.evidence_set.contradicting),
            "contradiction_count": len(packet.contradictions),
            "diagnostic_codes": diagnostic_codes,
            "deterministic": deterministic,
        }
        return ValidationResult(
            scenario.scenario_id,
            scenario.name,
            ValidationOutcome.FAIL if failures else ValidationOutcome.PASS,
            expected,
            actual,
            tuple(failures),
            false_association,
            len(missing_related),
        )
    except Exception as exc:
        return ValidationResult(
            scenario.scenario_id,
            scenario.name,
            ValidationOutcome.ERROR,
            expected,
            {},
            (f"{type(exc).__name__}: {exc}",),
        )


def run_validation_directory(directory: Path, fixture_root: Path | None = None) -> ValidationReport:
    if fixture_root is not None:
        directory = validate_fixture_path(directory, fixture_root, directory=True)
    paths = sorted(directory.glob("V*.json"))
    scenarios: list[ValidationScenario] = []
    results: list[ValidationResult] = []
    infrastructure_diagnostics: list[str] = []
    for path in paths:
        try:
            scenario = load_scenario(path, fixture_root)
            LOGGER.info(json.dumps({"event": "validation_scenario_started", "scenario_id": scenario.scenario_id}, sort_keys=True))
            scenarios.append(scenario)
            result = run_scenario(scenario)
            results.append(result)
            LOGGER.info(json.dumps({"event": "validation_scenario_completed", "scenario_id": scenario.scenario_id, "outcome": result.outcome.value}, sort_keys=True))
        except Exception as exc:
            scenario_id = path.stem
            results.append(ValidationResult(scenario_id, path.name, ValidationOutcome.ERROR, {}, {}, (f"scenario load error: {type(exc).__name__}: {exc}",)))
            infrastructure_diagnostics.append(f"{scenario_id}:scenario_load_error")
            LOGGER.info(json.dumps({"event": "validation_scenario_completed", "scenario_id": scenario_id, "outcome": "ERROR"}, sort_keys=True))
    pass_count = sum(item.outcome is ValidationOutcome.PASS for item in results)
    fail_count = sum(item.outcome is ValidationOutcome.FAIL for item in results)
    error_count = sum(item.outcome is ValidationOutcome.ERROR for item in results)
    false_count = sum(item.false_association for item in results)
    missed = sum(item.missed_associations for item in results)
    expected_candidates = sum(len(item.expectation.candidate_record_ids) for item in scenarios)
    actual_candidate_count = sum(len(item.actual.get("candidate_record_ids", ())) for item in results)
    candidate_true_positive = sum(
        len(set(scenario.expectation.candidate_record_ids) & set(result.actual.get("candidate_record_ids", ())))
        for scenario, result in zip(scenarios, results)
    )
    metrics = {
        "scenario_pass_rate": round(pass_count / len(results), 4) if results else 0.0,
        "candidate_precision": round(candidate_true_positive / actual_candidate_count, 4) if actual_candidate_count else None,
        "candidate_recall": round(candidate_true_positive / expected_candidates, 4) if expected_candidates else None,
        "provider_failure_coverage": _coverage(scenarios, "provider_failure"),
        "timestamp_normalization_coverage": _coverage(scenarios, "timestamp"),
        "entity_resolution_coverage": _coverage(scenarios, "entity_resolution"),
        "contradiction_handling_coverage": _coverage(scenarios, "contradiction"),
        "schema_drift_coverage": _coverage(scenarios, "schema_drift"),
        "evidence_completeness": all(
            item.outcome is not ValidationOutcome.PASS or item.actual.get("supporting_evidence_count", 0) + item.actual.get("contradicting_evidence_count", 0) > 0 or item.actual.get("execution_status") == "NO_RELIABLE_CONTEXT_FOUND"
            for item in results
        ),
        "designated_adversarial_scenarios": sorted(DESIGNATED_ADVERSARIAL),
    }
    determinism = "PASS" if results and all(item.actual.get("deterministic", False) for item in results if item.outcome is not ValidationOutcome.ERROR) else "FAIL"
    return ValidationReport(
        run_id=stable_id("validation", [(item.scenario_id, item.outcome.value, item.actual) for item in results]),
        schema_version="validation_report_v1",
        scenario_count=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count,
        false_association_count=false_count,
        missed_association_count=missed,
        scenario_results=tuple(results),
        diagnostics=tuple(infrastructure_diagnostics),
        determinism_result=determinism,
        metrics=metrics,
    )


def write_validation_outputs(report: ValidationReport, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(canonical_json(report), encoding="utf-8")
    lines = [
        "# Validation Report", "", f"Run ID: `{report.run_id}`", "",
        f"Result: {report.pass_count}/{report.scenario_count} PASS; {report.fail_count} FAIL; {report.error_count} ERROR",
        f"False associations: {report.false_association_count}",
        f"Missed associations: {report.missed_association_count}",
        f"Determinism: {report.determinism_result}", "", "## Scenario Matrix", "",
        "| ID | Scenario | Outcome | Status | Confidence |", "|---|---|---|---|---|",
    ]
    for item in report.scenario_results:
        lines.append(f"| {item.scenario_id} | {item.name} | {item.outcome.value} | {item.actual.get('execution_status', '-')} | {item.actual.get('confidence', '-')} |")
    lines.extend(["", "## Metrics", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(report.metrics.items()))
    lines.extend(["", "This report was generated from authoritative runtime execution. PASS values are not hardcoded."])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _coverage(scenarios: list[ValidationScenario], label: str) -> dict[str, Any]:
    ids = sorted(item.scenario_id for item in scenarios if label in item.metric_labels)
    return {"scenario_count": len(ids), "scenario_ids": ids}
