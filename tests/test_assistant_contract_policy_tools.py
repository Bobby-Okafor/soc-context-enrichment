from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import scenario_packet
from context_enrichment.application.service import EnrichmentService
from context_enrichment.assistant.contracts import (
    AssistantAction,
    AssistantContractError,
    AssistantIntent,
    AssistantRequest,
)
from context_enrichment.assistant.policy import INTENT_POLICY, DeterministicAssistantPolicy
from context_enrichment.assistant.tools import AssistantTools
from context_enrichment.domain.models import EnrichmentStatus


def test_assistant_request_validation() -> None:
    _, packet = scenario_packet("V01")
    with pytest.raises(AssistantContractError, match="must not be empty"):
        AssistantRequest("", AssistantIntent.SUMMARIZE_ENRICHMENT, packet=packet)
    with pytest.raises(AssistantContractError, match="requires"):
        AssistantRequest("request", AssistantIntent.SUMMARIZE_ENRICHMENT)
    with pytest.raises(AssistantContractError, match="not both"):
        AssistantRequest("request", AssistantIntent.SUMMARIZE_ENRICHMENT, alert_envelope={}, packet=packet)
    with pytest.raises(AssistantContractError, match="requires an alert"):
        AssistantRequest("request", AssistantIntent.ENRICH_ALERT, packet=packet)


def test_all_nine_intents_have_finite_inspectable_plans() -> None:
    assert set(INTENT_POLICY) == set(AssistantIntent)
    assert len(INTENT_POLICY) == 9
    for intent, plan in INTENT_POLICY.items():
        assert plan
        assert plan[-1] is AssistantAction.BUILD_RESPONSE
        assert len(plan) == len(set(plan))
        assert all(isinstance(action, AssistantAction) for action in plan)
        if intent is not AssistantIntent.ENRICH_ALERT:
            assert AssistantAction.CALL_ENRICHMENT_SERVICE not in plan


def test_policy_prepends_authoritative_enrichment_only_when_packet_is_absent() -> None:
    scenario, packet = scenario_packet("V01")
    policy = DeterministicAssistantPolicy()
    from_alert = AssistantRequest.for_alert(AssistantIntent.EXPLAIN_CONFIDENCE, scenario.alert)
    from_packet = AssistantRequest.for_packet(AssistantIntent.EXPLAIN_CONFIDENCE, packet)
    assert policy.plan(from_alert)[0] is AssistantAction.CALL_ENRICHMENT_SERVICE
    assert policy.plan(from_packet) == (
        AssistantAction.INSPECT_CONFIDENCE,
        AssistantAction.BUILD_RESPONSE,
    )
    assert policy.permits(AssistantIntent.EXPLAIN_CONFIDENCE, AssistantAction.INSPECT_CONFIDENCE, packet_supplied=True)
    assert not policy.permits(AssistantIntent.EXPLAIN_CONFIDENCE, AssistantAction.INSPECT_RELATIONSHIP, packet_supplied=True)


def test_controlled_tool_surface_is_exact_and_packet_only_after_enrichment() -> None:
    public = {name for name in dir(AssistantTools) if not name.startswith("_")}
    assert public == {
        "enrich_alert",
        "get_relationship",
        "get_supporting_evidence",
        "get_contradicting_evidence",
        "get_missing_information",
        "get_confidence_factors",
        "get_provider_diagnostics",
        "get_recommended_review_areas",
    }
    _, packet = scenario_packet("V01")
    tools = AssistantTools(EnrichmentService())
    assert tools.get_relationship(packet) is packet.correlation_results
    assert tools.get_supporting_evidence(packet) is packet.evidence_set.supporting
    assert tools.get_contradicting_evidence(packet) is packet.evidence_set.contradicting
    assert tools.get_confidence_factors(packet) is packet.confidence


@pytest.mark.parametrize(
    ("scenario_id", "expected_status"),
    [
        ("V01", "RELATED_CONTEXT_FOUND"),
        ("V13", "AMBIGUOUS_CONTEXT"),
        ("V10", "CONTRADICTORY_CONTEXT"),
        ("V15", "NO_RELIABLE_CONTEXT_FOUND"),
        ("V16", "PARTIAL_ENRICHMENT"),
    ],
)
def test_existing_packets_cover_five_execution_states(scenario_id: str, expected_status: str) -> None:
    _, packet = scenario_packet(scenario_id)
    assert packet.execution_status.value == expected_status


def test_failed_state_remains_observable_to_packet_inspection() -> None:
    _, packet = scenario_packet("V15")
    failed = replace(packet, execution_status=EnrichmentStatus.ENRICHMENT_FAILED)
    tools = AssistantTools(EnrichmentService())
    assert failed.execution_status.value == "ENRICHMENT_FAILED"
    assert tools.get_relationship(failed) == failed.correlation_results
