from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import scenario_packet
from context_enrichment.application.service import EnrichmentService
from context_enrichment.assistant.contracts import AssistantIntent, AssistantRequest
from context_enrichment.assistant.service import AnalystAssistant
from context_enrichment.domain.models import EnrichmentStatus, RelationshipState
from context_enrichment.domain.serialization import canonical_json


def response_for(scenario_id: str, intent: AssistantIntent = AssistantIntent.SUMMARIZE_ENRICHMENT):
    _, packet = scenario_packet(scenario_id)
    return packet, AnalystAssistant(EnrichmentService()).execute(AssistantRequest.for_packet(intent, packet))


def test_comprehensive_trace_is_complete_stable_and_evidence_referenced() -> None:
    packet, first = response_for("V01")
    _, second = response_for("V01")
    assert canonical_json(first, indent=None) == canonical_json(second, indent=None)
    assert first.trace.packet_reference == packet.packet_id
    assert first.trace.actions_executed == first.trace.deterministic_plan
    assert tuple(call.sequence for call in first.trace.tool_calls) == tuple(range(1, 8))
    assert tuple(call.tool_name for call in first.trace.tool_calls) == (
        "get_relationship",
        "get_supporting_evidence",
        "get_contradicting_evidence",
        "get_missing_information",
        "get_confidence_factors",
        "get_provider_diagnostics",
        "get_recommended_review_areas",
    )
    expected_ids = tuple(item.evidence_id for item in (*packet.evidence_set.supporting, *packet.evidence_set.contradicting))
    assert first.trace.evidence_ids_consulted == expected_ids


def test_assistant_does_not_mutate_packet_confidence_evidence_or_relationships() -> None:
    _, packet = scenario_packet("V19")
    before = canonical_json(packet, indent=None)
    response = AnalystAssistant(EnrichmentService()).execute(AssistantRequest.for_packet(AssistantIntent.SUMMARIZE_ENRICHMENT, packet))
    assert canonical_json(packet, indent=None) == before
    assert response.confidence is packet.confidence
    assert response.supporting_evidence == packet.evidence_set.supporting
    assert response.contradicting_evidence == packet.evidence_set.contradicting
    assert response.relationship_results == packet.correlation_results


def test_not_supported_and_contradicted_results_are_never_narrated_as_support() -> None:
    _, primary = response_for("V01")
    assert "NOT_SUPPORTED. Evidence:" not in primary.narrative
    assert "NOT_SUPPORTED. Consulted observation IDs (not relationship support):" in primary.narrative
    assert all(item.evidence_id in primary.narrative for item in primary.supporting_evidence)
    _, contradicted = response_for("V10")
    assert any(item.relationship_state is RelationshipState.CONTRADICTED for item in contradicted.relationship_results)
    assert "CONTRADICTED. Evidence:" in contradicted.narrative
    assert "relationship=CONTRADICTED" not in contradicted.narrative or "Supporting feature observations" in contradicted.narrative


def test_relationship_claims_preserve_evidence_ids() -> None:
    _, response = response_for("V01", AssistantIntent.EXPLAIN_RELATIONSHIP)
    supported = [item for item in response.relationship_results if item.relationship_state is RelationshipState.SUPPORTED]
    assert supported
    for result in supported:
        matching = [item.evidence_id for item in response.supporting_evidence if item.source_provider == result.source_provider and item.context_record_reference == result.context_record_reference]
        assert matching
        assert all(evidence_id in response.narrative for evidence_id in matching)


def test_false_join_is_not_converted_into_plausible_context() -> None:
    _, response = response_for("V04")
    assert response.execution_status == "NO_RELIABLE_CONTEXT_FOUND"
    assert response.relationship_results == ()
    assert response.supporting_evidence == ()
    assert "no correlation result that safely establishes related context" in response.narrative
    assert "TKT-V04-SIMILAR" not in response.narrative


def test_provider_failure_remains_unavailable_not_absent() -> None:
    _, response = response_for("V16")
    assert response.execution_status == "PARTIAL_ENRICHMENT"
    assert any(item.code == "PROVIDER_UNAVAILABLE" for item in response.provider_diagnostics)
    assert "evidence path was unavailable" in response.narrative
    assert "does not establish that no context exists" in response.narrative


def test_ambiguity_and_all_six_execution_states_are_preserved() -> None:
    for scenario_id in ("V01", "V13", "V10", "V15", "V16"):
        packet, response = response_for(scenario_id)
        assert response.execution_status == packet.execution_status.value
    _, packet = scenario_packet("V15")
    failed = replace(packet, execution_status=EnrichmentStatus.ENRICHMENT_FAILED)
    response = AnalystAssistant(EnrichmentService()).execute(AssistantRequest.for_packet(AssistantIntent.SUMMARIZE_ENRICHMENT, failed))
    assert response.execution_status == "ENRICHMENT_FAILED"
    ambiguous_packet, ambiguous = response_for("V13")
    assert ambiguous.execution_status == "AMBIGUOUS_CONTEXT"
    assert ambiguous.relationship_results == ambiguous_packet.correlation_results


class MutatingPresentationAdapter:
    enabled = True

    def generate_narrative(self, context):
        context["execution_status"] = "ENRICHMENT_FAILED"
        context["supporting_evidence"] = []
        return "Presentation-only test narrative"


def test_model_adapter_is_disabled_by_default_and_enabled_adapter_cannot_mutate_facts() -> None:
    _, packet = scenario_packet("V01")
    baseline = AnalystAssistant(EnrichmentService()).execute(AssistantRequest.for_packet(AssistantIntent.SUMMARIZE_ENRICHMENT, packet))
    assert baseline.model_adapter_status == "DISABLED_NO_MODEL"
    before = canonical_json(packet, indent=None)
    adapted = AnalystAssistant(EnrichmentService(), model_adapter=MutatingPresentationAdapter()).execute(AssistantRequest.for_packet(AssistantIntent.SUMMARIZE_ENRICHMENT, packet))
    assert adapted.model_adapter_status == "ENABLED_PRESENTATION_ONLY"
    assert adapted.narrative == "Presentation-only test narrative"
    assert adapted.execution_status == packet.execution_status.value
    assert adapted.supporting_evidence == packet.evidence_set.supporting
    assert canonical_json(packet, indent=None) == before


@pytest.mark.parametrize(
    "intent",
    [
        AssistantIntent.EXPLAIN_RELATIONSHIP,
        AssistantIntent.LIST_SUPPORTING_EVIDENCE,
        AssistantIntent.LIST_CONTRADICTIONS,
        AssistantIntent.LIST_MISSING_INFORMATION,
        AssistantIntent.EXPLAIN_CONFIDENCE,
        AssistantIntent.LIST_PROVIDER_DIAGNOSTICS,
        AssistantIntent.SUGGEST_REVIEW_AREAS,
        AssistantIntent.SUMMARIZE_ENRICHMENT,
    ],
)
def test_every_packet_intent_executes_without_general_chat_behavior(intent: AssistantIntent) -> None:
    _, packet = scenario_packet("V19")
    response = AnalystAssistant(EnrichmentService()).execute(AssistantRequest.for_packet(intent, packet))
    assert response.intent is intent
    assert response.trace.completion_state.value == "COMPLETED"
    assert response.trace.deterministic_plan[-1].value == "BUILD_RESPONSE"
