from __future__ import annotations

import json
import logging

from conftest import scenario_packet
from context_enrichment.domain.serialization import canonical_json
from context_enrichment.output.renderer import render_packet


def test_full_e2e_path_exercises_all_frozen_stages(caplog) -> None:
    caplog.set_level(logging.INFO, logger="context_enrichment")
    scenario, packet = scenario_packet("V01")
    events = [json.loads(record.message)["event"] for record in caplog.records]
    for required in (
        "enrichment_started", "alert_normalized", "entity_resolution_completed",
        "provider_queried", "candidate_count", "correlation_completed",
        "evidence_created", "confidence_assessed", "packet_assembled",
    ):
        assert required in events
    assert scenario.scenario_id == "V01"
    assert packet.schema_version == "enrichment_packet_v1"
    assert packet.provenance["provider_count"] == 5
    assert packet.provenance["rejected_candidate_record_ids"] == ("ASSET-V01", "TKT-V01-UNRELATED")
    assert packet.provenance["pipeline_stages"][0] == "INTAKE_VALIDATED"
    assert packet.provenance["pipeline_stages"][-1] == "PACKET_ASSEMBLED"
    assert len(packet.provenance["provider_results"]) == 5
    assert {item["status"] for item in packet.provenance["provider_results"]} == {"SUCCESS"}
    assert {item["entity_type"] for item in packet.provenance["alert_resolved_entities"]} == {"user", "host"}
    assert all(item["selection_reasons"] for item in packet.provenance["selected_candidates"])
    assert {item["reason"] for item in packet.provenance["rejected_candidates"]} == {"EXPLICIT_USER_MISMATCH"}
    assert packet.related_context and packet.correlation_results and packet.evidence_set.supporting


def test_renderer_is_deterministic_and_non_dispositive() -> None:
    _, packet = scenario_packet("V01")
    first = render_packet(packet)
    second = render_packet(packet)
    assert first == second
    assert "analyst judgment remains authoritative" in first
    assert "Execution status: RELATED_CONTEXT_FOUND" in first
    assert "Executed pipeline stages:" in first
    assert "Provider query results:" in first
    assert "REJECTED TKT-V01-UNRELATED: EXPLICIT_USER_MISMATCH" in first
    assert "Correlation results:" in first
    assert "Supporting evidence: 18" in first
    assert "Source provenance:" in first
    assert "malicious" not in first.lower()


def test_authoritative_packet_serialization_replays_identically() -> None:
    _, first = scenario_packet("V20")
    _, second = scenario_packet("V20")
    assert canonical_json(first, indent=None) == canonical_json(second, indent=None)
    assert first.packet_id == second.packet_id


def test_partial_provider_availability_is_not_no_context() -> None:
    _, packet = scenario_packet("V16")
    assert packet.execution_status.value == "PARTIAL_ENRICHMENT"
    assert packet.related_context
    assert any(item.code == "PROVIDER_UNAVAILABLE" for item in packet.provider_diagnostics)


def test_successful_empty_providers_mean_no_reliable_context() -> None:
    _, packet = scenario_packet("V15")
    assert packet.execution_status.value == "NO_RELIABLE_CONTEXT_FOUND"
    assert packet.execution_status.value != "ENRICHMENT_FAILED"
    assert packet.provider_diagnostics == ()
