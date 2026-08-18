"""Immutable contracts for the bounded deterministic AnalystAssistant."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from context_enrichment.domain.models import ConfidenceAssessment, CorrelationResult, EnrichmentPacket, EvidenceItem, ProviderDiagnostic
from context_enrichment.domain.serialization import stable_id


class AssistantContractError(ValueError):
    """Raised when an assistant request violates the frozen contract."""


class AssistantAuthorityViolation(RuntimeError):
    """Raised when downstream execution attempts to change packet authority."""


class AssistantIntent(str, Enum):
    ENRICH_ALERT = "ENRICH_ALERT"
    EXPLAIN_RELATIONSHIP = "EXPLAIN_RELATIONSHIP"
    LIST_SUPPORTING_EVIDENCE = "LIST_SUPPORTING_EVIDENCE"
    LIST_CONTRADICTIONS = "LIST_CONTRADICTIONS"
    LIST_MISSING_INFORMATION = "LIST_MISSING_INFORMATION"
    EXPLAIN_CONFIDENCE = "EXPLAIN_CONFIDENCE"
    LIST_PROVIDER_DIAGNOSTICS = "LIST_PROVIDER_DIAGNOSTICS"
    SUGGEST_REVIEW_AREAS = "SUGGEST_REVIEW_AREAS"
    SUMMARIZE_ENRICHMENT = "SUMMARIZE_ENRICHMENT"


class AssistantAction(str, Enum):
    CALL_ENRICHMENT_SERVICE = "CALL_ENRICHMENT_SERVICE"
    INSPECT_RELATIONSHIP = "INSPECT_RELATIONSHIP"
    INSPECT_SUPPORTING_EVIDENCE = "INSPECT_SUPPORTING_EVIDENCE"
    INSPECT_CONTRADICTING_EVIDENCE = "INSPECT_CONTRADICTING_EVIDENCE"
    INSPECT_MISSING_INFORMATION = "INSPECT_MISSING_INFORMATION"
    INSPECT_CONFIDENCE = "INSPECT_CONFIDENCE"
    INSPECT_PROVIDER_DIAGNOSTICS = "INSPECT_PROVIDER_DIAGNOSTICS"
    INSPECT_REVIEW_AREAS = "INSPECT_REVIEW_AREAS"
    BUILD_RESPONSE = "BUILD_RESPONSE"


class AssistantCompletionState(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AssistantDiagnostic:
    code: str
    message: str
    severity: str = "INFO"


@dataclass(frozen=True)
class AssistantRequest:
    request_id: str
    intent: AssistantIntent
    alert_envelope: dict[str, Any] | None = None
    packet: EnrichmentPacket | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise AssistantContractError("request_id must not be empty")
        if not isinstance(self.intent, AssistantIntent):
            raise AssistantContractError("intent must be an AssistantIntent")
        if self.alert_envelope is not None and self.packet is not None:
            raise AssistantContractError("request must provide an alert envelope or packet, not both")
        if self.alert_envelope is None and self.packet is None:
            raise AssistantContractError("request requires an alert envelope or accepted packet")
        if self.intent is AssistantIntent.ENRICH_ALERT and self.alert_envelope is None:
            raise AssistantContractError("ENRICH_ALERT requires an alert envelope")

    @classmethod
    def for_alert(cls, intent: AssistantIntent, alert_envelope: dict[str, Any]) -> "AssistantRequest":
        return cls(stable_id("assistant-request", intent.value, alert_envelope), intent, alert_envelope=alert_envelope)

    @classmethod
    def for_packet(cls, intent: AssistantIntent, packet: EnrichmentPacket) -> "AssistantRequest":
        if intent is AssistantIntent.ENRICH_ALERT:
            raise AssistantContractError("ENRICH_ALERT cannot use an existing packet")
        return cls(stable_id("assistant-request", intent.value, packet.packet_id), intent, packet=packet)


@dataclass(frozen=True)
class AssistantToolCall:
    sequence: int
    action: AssistantAction
    tool_name: str
    input_reference: str
    output_references: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class AssistantTrace:
    requested_intent: AssistantIntent
    deterministic_plan: tuple[AssistantAction, ...]
    actions_executed: tuple[AssistantAction, ...]
    tool_calls: tuple[AssistantToolCall, ...]
    packet_reference: str
    evidence_ids_consulted: tuple[str, ...]
    completion_state: AssistantCompletionState
    diagnostics: tuple[AssistantDiagnostic, ...]


@dataclass(frozen=True)
class AssistantResponse:
    response_id: str
    request_id: str
    intent: AssistantIntent
    packet_id: str
    execution_status: str
    relationship_results: tuple[CorrelationResult, ...]
    supporting_evidence: tuple[EvidenceItem, ...]
    contradicting_evidence: tuple[EvidenceItem, ...]
    contradictions: tuple[str, ...]
    missing_information: tuple[str, ...]
    confidence: ConfidenceAssessment | None
    provider_diagnostics: tuple[ProviderDiagnostic, ...]
    recommended_review_areas: tuple[str, ...]
    narrative: str
    trace: AssistantTrace
    model_adapter_status: str
    diagnostics: tuple[AssistantDiagnostic, ...]
