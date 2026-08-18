"""Explicit finite intent-to-action policy for the AnalystAssistant."""

from context_enrichment.assistant.contracts import AssistantAction, AssistantIntent, AssistantRequest


COMPREHENSIVE_INSPECTION = (
    AssistantAction.INSPECT_RELATIONSHIP,
    AssistantAction.INSPECT_SUPPORTING_EVIDENCE,
    AssistantAction.INSPECT_CONTRADICTING_EVIDENCE,
    AssistantAction.INSPECT_MISSING_INFORMATION,
    AssistantAction.INSPECT_CONFIDENCE,
    AssistantAction.INSPECT_PROVIDER_DIAGNOSTICS,
    AssistantAction.INSPECT_REVIEW_AREAS,
)

INTENT_POLICY = {
    AssistantIntent.ENRICH_ALERT: (AssistantAction.CALL_ENRICHMENT_SERVICE, *COMPREHENSIVE_INSPECTION, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.EXPLAIN_RELATIONSHIP: (AssistantAction.INSPECT_RELATIONSHIP, AssistantAction.INSPECT_SUPPORTING_EVIDENCE, AssistantAction.INSPECT_CONTRADICTING_EVIDENCE, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.LIST_SUPPORTING_EVIDENCE: (AssistantAction.INSPECT_SUPPORTING_EVIDENCE, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.LIST_CONTRADICTIONS: (AssistantAction.INSPECT_CONTRADICTING_EVIDENCE, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.LIST_MISSING_INFORMATION: (AssistantAction.INSPECT_MISSING_INFORMATION, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.EXPLAIN_CONFIDENCE: (AssistantAction.INSPECT_CONFIDENCE, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.LIST_PROVIDER_DIAGNOSTICS: (AssistantAction.INSPECT_PROVIDER_DIAGNOSTICS, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.SUGGEST_REVIEW_AREAS: (AssistantAction.INSPECT_REVIEW_AREAS, AssistantAction.BUILD_RESPONSE),
    AssistantIntent.SUMMARIZE_ENRICHMENT: (*COMPREHENSIVE_INSPECTION, AssistantAction.BUILD_RESPONSE),
}


class DeterministicAssistantPolicy:
    def plan(self, request: AssistantRequest) -> tuple[AssistantAction, ...]:
        plan = INTENT_POLICY[request.intent]
        if request.packet is None and request.intent is not AssistantIntent.ENRICH_ALERT:
            return (AssistantAction.CALL_ENRICHMENT_SERVICE, *plan)
        return plan

    def permits(self, intent: AssistantIntent, action: AssistantAction, *, packet_supplied: bool) -> bool:
        plan = INTENT_POLICY[intent]
        if not packet_supplied and intent is not AssistantIntent.ENRICH_ALERT:
            plan = (AssistantAction.CALL_ENRICHMENT_SERVICE, *plan)
        return action in plan
