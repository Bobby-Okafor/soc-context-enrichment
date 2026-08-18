"""Bounded deterministic analyst-assistant executor."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from context_enrichment.application.service import EnrichmentService
from context_enrichment.assistant.contracts import (
    AssistantAction,
    AssistantAuthorityViolation,
    AssistantCompletionState,
    AssistantRequest,
    AssistantResponse,
    AssistantToolCall,
    AssistantTrace,
)
from context_enrichment.assistant.model_adapter import DisabledModelAdapter, ModelAdapter
from context_enrichment.assistant.policy import DeterministicAssistantPolicy
from context_enrichment.assistant.tools import AssistantTools
from context_enrichment.domain.models import EnrichmentPacket, RelationshipState
from context_enrichment.domain.serialization import canonical_json, stable_id


ACTION_TO_TOOL = {
    AssistantAction.CALL_ENRICHMENT_SERVICE: "enrich_alert",
    AssistantAction.INSPECT_RELATIONSHIP: "get_relationship",
    AssistantAction.INSPECT_SUPPORTING_EVIDENCE: "get_supporting_evidence",
    AssistantAction.INSPECT_CONTRADICTING_EVIDENCE: "get_contradicting_evidence",
    AssistantAction.INSPECT_MISSING_INFORMATION: "get_missing_information",
    AssistantAction.INSPECT_CONFIDENCE: "get_confidence_factors",
    AssistantAction.INSPECT_PROVIDER_DIAGNOSTICS: "get_provider_diagnostics",
    AssistantAction.INSPECT_REVIEW_AREAS: "get_recommended_review_areas",
}


class AnalystAssistant:
    """Execute a finite request plan without acquiring factual authority."""

    def __init__(
        self,
        enrichment_service: EnrichmentService,
        *,
        policy: DeterministicAssistantPolicy | None = None,
        model_adapter: ModelAdapter | None = None,
    ) -> None:
        self._tools = AssistantTools(enrichment_service)
        self._policy = policy or DeterministicAssistantPolicy()
        self._model_adapter = model_adapter or DisabledModelAdapter()

    def execute(self, request: AssistantRequest) -> AssistantResponse:
        plan = self._policy.plan(request)
        packet = request.packet
        views: dict[str, Any] = {}
        actions: list[AssistantAction] = []
        calls: list[AssistantToolCall] = []
        evidence_ids: list[str] = []

        for action in plan:
            actions.append(action)
            if action is AssistantAction.BUILD_RESPONSE:
                continue
            if not self._policy.permits(request.intent, action, packet_supplied=request.packet is not None):
                raise AssistantAuthorityViolation(f"policy rejected action {action.value}")
            tool_name = ACTION_TO_TOOL[action]
            if action is AssistantAction.CALL_ENRICHMENT_SERVICE:
                if request.alert_envelope is None:
                    raise AssistantAuthorityViolation("service call requires the request alert envelope")
                packet = self._tools.enrich_alert(request.alert_envelope)
                result: Any = packet
                output_refs = (packet.packet_id,)
            else:
                if packet is None:
                    raise AssistantAuthorityViolation("packet inspection attempted without an accepted packet")
                result = getattr(self._tools, tool_name)(packet)
                views[tool_name] = result
                output_refs = self._output_references(tool_name, result, packet)
            call_evidence = self._evidence_references(result)
            evidence_ids.extend(call_evidence)
            calls.append(AssistantToolCall(
                sequence=len(calls) + 1,
                action=action,
                tool_name=tool_name,
                input_reference=request.request_id if action is AssistantAction.CALL_ENRICHMENT_SERVICE else packet.packet_id,
                output_references=output_refs,
                evidence_ids=call_evidence,
                status="COMPLETED",
            ))

        if packet is None:
            raise AssistantAuthorityViolation("assistant plan completed without an accepted packet")
        authoritative_packet_hash = canonical_json(packet, indent=None)
        consulted = tuple(dict.fromkeys(evidence_ids))
        trace = AssistantTrace(
            requested_intent=request.intent,
            deterministic_plan=plan,
            actions_executed=tuple(actions),
            tool_calls=tuple(calls),
            packet_reference=packet.packet_id,
            evidence_ids_consulted=consulted,
            completion_state=AssistantCompletionState.COMPLETED,
            diagnostics=(),
        )
        response = self._build_response(request, packet, views, trace)
        if self._model_adapter.enabled:
            detached_context = json.loads(canonical_json(response, indent=None))
            narrative = self._model_adapter.generate_narrative(detached_context)
            if not isinstance(narrative, str) or not narrative.strip():
                raise AssistantAuthorityViolation("enabled ModelAdapter returned no narrative")
            response = replace(response, narrative=narrative.strip(), model_adapter_status="ENABLED_PRESENTATION_ONLY")
        if canonical_json(packet, indent=None) != authoritative_packet_hash:
            raise AssistantAuthorityViolation("assistant execution mutated the accepted packet")
        return response

    @staticmethod
    def _build_response(request, packet, views, trace) -> AssistantResponse:
        relationships = tuple(views.get("get_relationship", ()))
        supporting = tuple(views.get("get_supporting_evidence", ()))
        contradicting = tuple(views.get("get_contradicting_evidence", ()))
        missing = tuple(views.get("get_missing_information", ()))
        confidence = views.get("get_confidence_factors")
        diagnostics = tuple(views.get("get_provider_diagnostics", ()))
        review = tuple(views.get("get_recommended_review_areas", ()))
        contradictions = packet.contradictions if "get_contradicting_evidence" in views else ()
        narrative = _render_narrative(
            packet,
            relationships,
            supporting,
            contradicting,
            contradictions,
            missing,
            confidence,
            diagnostics,
            review,
            relationship_inspected="get_relationship" in views,
        )
        identity = (
            request.request_id,
            packet.packet_id,
            request.intent.value,
            trace,
            relationships,
            supporting,
            contradicting,
            contradictions,
            missing,
            confidence,
            diagnostics,
            review,
        )
        return AssistantResponse(
            response_id=stable_id("assistant-response", identity),
            request_id=request.request_id,
            intent=request.intent,
            packet_id=packet.packet_id,
            execution_status=packet.execution_status.value,
            relationship_results=relationships,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            contradictions=contradictions,
            missing_information=missing,
            confidence=confidence,
            provider_diagnostics=diagnostics,
            recommended_review_areas=review,
            narrative=narrative,
            trace=trace,
            model_adapter_status="DISABLED_NO_MODEL",
            diagnostics=(),
        )

    @staticmethod
    def _evidence_references(result: Any) -> tuple[str, ...]:
        if isinstance(result, tuple):
            return tuple(item.evidence_id for item in result if hasattr(item, "evidence_id"))
        return ()

    @staticmethod
    def _output_references(tool_name: str, result: Any, packet: EnrichmentPacket) -> tuple[str, ...]:
        if tool_name == "get_relationship":
            return (f"execution_status:{packet.execution_status.value}",) + tuple(
                f"{item.correlation_id}:{item.relationship_state.value}" for item in result
            )
        if tool_name in {"get_supporting_evidence", "get_contradicting_evidence"}:
            return tuple(item.evidence_id for item in result)
        if tool_name == "get_confidence_factors":
            return (f"confidence:{result.level.value}",)
        if tool_name == "get_provider_diagnostics":
            return tuple(f"{item.provider_id}:{item.code}" for item in result)
        return tuple(f"{tool_name}:{index + 1}" for index, _ in enumerate(result))


def _render_narrative(
    packet,
    relationships,
    supporting,
    contradicting,
    contradictions,
    missing,
    confidence,
    diagnostics,
    review,
    *,
    relationship_inspected,
) -> str:
    lines = [f"Accepted enrichment status: {packet.execution_status.value}."]
    if relationship_inspected:
        if relationships:
            lines.append("Core relationship results:")
            for item in relationships:
                eligible = supporting if item.relationship_state in {RelationshipState.SUPPORTED, RelationshipState.PARTIALLY_SUPPORTED} else contradicting if item.relationship_state is RelationshipState.CONTRADICTED else ()
                citations = tuple(evidence.evidence_id for evidence in eligible if evidence.context_record_reference == item.context_record_reference and evidence.source_provider == item.source_provider)
                if citations:
                    suffix = f" Evidence: {', '.join(citations)}."
                elif item.relationship_state is RelationshipState.NOT_SUPPORTED:
                    observations = tuple(evidence.evidence_id for evidence in supporting if evidence.context_record_reference == item.context_record_reference and evidence.source_provider == item.source_provider)
                    suffix = f" Consulted observation IDs (not relationship support): {', '.join(observations)}." if observations else " No evidence item establishes relationship support."
                else:
                    suffix = " No consulted evidence item supports a stronger claim."
                lines.append(f"- {item.source_provider}/{item.context_record_reference}: {item.relationship_state.value}.{suffix}")
        else:
            lines.append("The accepted packet contains no correlation result that safely establishes related context.")
    if supporting:
        state_by_record = {(item.source_provider, item.context_record_reference): item.relationship_state.value for item in packet.correlation_results}
        accepted_states = {RelationshipState.SUPPORTED.value, RelationshipState.PARTIALLY_SUPPORTED.value}
        relationship_support = tuple(item for item in supporting if state_by_record.get((item.source_provider, item.source_record_id)) in accepted_states)
        nonrelationship_observations = tuple(item for item in supporting if item not in relationship_support)
        if relationship_support:
            lines.append("Supporting relationship evidence:")
            lines.extend(f"- [{item.evidence_id}] {item.claim_type}={item.canonical_values.get('feature_value')} from {item.source_provider}/{item.source_record_id}." for item in relationship_support)
        if nonrelationship_observations:
            ids = ", ".join(item.evidence_id for item in nonrelationship_observations)
            lines.append(f"Feature observations attached to NOT_SUPPORTED records remain non-authoritative for relationship support: {ids}.")
    if contradicting or contradictions:
        lines.append("Contradictions remain explicit:")
        lines.extend(f"- [{item.evidence_id}] {item.claim_type}={item.canonical_values.get('feature_value')} from {item.source_provider}/{item.source_record_id}." for item in contradicting)
        if not contradicting:
            lines.extend(f"- {item}." for item in contradictions)
    if missing:
        lines.append("Missing or unavailable information:")
        lines.extend(f"- {item}." for item in missing)
    if confidence is not None:
        lines.append(f"Relationship confidence: {confidence.level.value}.")
        lines.extend(f"- {item}." for item in confidence.rationale)
        lines.extend(f"- Degradation: {item}." for item in confidence.degradation_factors)
    if diagnostics:
        lines.append("Provider diagnostics:")
        for item in diagnostics:
            lines.append(f"- {item.provider_id}/{item.code}: {item.message}.")
        if any(item.severity.value == "ERROR" or "UNAVAILABLE" in item.code or "FAIL" in item.code for item in diagnostics):
            lines.append("A provider evidence path was unavailable; this does not establish that no context exists.")
    if review:
        lines.append("Deterministic review areas (not response actions):")
        lines.extend(f"- {item}." for item in review)
    lines.append("This response preserves the packet's uncertainty and does not perform alert disposition.")
    return "\n".join(lines)
