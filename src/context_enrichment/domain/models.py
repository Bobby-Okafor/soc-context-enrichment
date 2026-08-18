"""Canonical domain contracts for architecture baseline v1.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StringEnum(str, Enum):
    pass


class TimestampQuality(StringEnum):
    VALID = "VALID"
    AMBIGUOUS_TIMEZONE = "AMBIGUOUS_TIMEZONE"
    MALFORMED = "MALFORMED"
    MISSING = "MISSING"


class ResolutionQuality(StringEnum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    EXPLICIT_ALIAS = "EXPLICIT_ALIAS"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ProviderStatus(StringEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class DiagnosticSeverity(StringEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RelationshipState(StringEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class EvidencePolarity(StringEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class ConfidenceLevel(StringEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class EnrichmentStatus(StringEnum):
    RELATED_CONTEXT_FOUND = "RELATED_CONTEXT_FOUND"
    AMBIGUOUS_CONTEXT = "AMBIGUOUS_CONTEXT"
    CONTRADICTORY_CONTEXT = "CONTRADICTORY_CONTEXT"
    NO_RELIABLE_CONTEXT_FOUND = "NO_RELIABLE_CONTEXT_FOUND"
    PARTIAL_ENRICHMENT = "PARTIAL_ENRICHMENT"
    ENRICHMENT_FAILED = "ENRICHMENT_FAILED"


class ValidationOutcome(StringEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TimestampValue:
    raw_timestamp: str | None
    normalized_timestamp: datetime | None
    timestamp_quality: TimestampQuality


@dataclass(frozen=True)
class Provenance:
    source_provider: str
    source_record_id: str
    source_schema_version: str
    retrieved_at: datetime
    transformation_chain: tuple[str, ...]


@dataclass(frozen=True)
class RawAlert:
    alert_id: str
    schema_version: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class CanonicalAlert:
    alert_id: str
    schema_version: str
    timestamp: TimestampValue
    user: str | None
    host: str | None
    action: str | None
    alert_type: str | None
    raw_values: dict[str, Any]
    diagnostics: tuple[str, ...] = ()
    transformation_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawProviderRecord:
    source_provider: str
    source_record_id: str
    source_schema_version: str
    retrieved_at: datetime
    raw_values: dict[str, Any]


@dataclass(frozen=True)
class CanonicalContextRecord:
    source_provider: str
    source_record_id: str
    source_schema_version: str
    record_type: str
    timestamp: TimestampValue
    user: str | None
    host: str | None
    action: str | None
    record_state: str
    raw_values: dict[str, Any]
    provenance: Provenance
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityReference:
    entity_type: str
    input_value: str | None
    source_reference: str


@dataclass(frozen=True)
class ResolvedEntity:
    entity_type: str
    input_value: str | None
    canonical_value: str | None
    candidate_values: tuple[str, ...]
    resolution_method: str
    resolution_quality: ResolutionQuality
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class ProviderQuery:
    query_id: str
    alert_id: str
    provider_id: str
    canonical_user: str | None
    canonical_host: str | None
    action: str | None
    alert_timestamp: datetime | None


@dataclass(frozen=True)
class ProviderDiagnostic:
    provider_id: str
    code: str
    message: str
    severity: DiagnosticSeverity
    record_id: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    status: ProviderStatus
    records: tuple[RawProviderRecord, ...]
    diagnostics: tuple[ProviderDiagnostic, ...]


@dataclass(frozen=True)
class CandidateContext:
    record: CanonicalContextRecord
    resolved_entities: tuple[ResolvedEntity, ...]
    selection_reasons: tuple[str, ...]
    entity_specificity: int
    temporal_distance_seconds: int | None


@dataclass(frozen=True)
class CorrelationFeature:
    feature_id: str
    feature_type: str
    value: str
    explanation: str
    alert_value: Any = None
    context_value: Any = None


@dataclass(frozen=True)
class CorrelationResult:
    correlation_id: str
    alert_reference: str
    context_record_reference: str
    source_provider: str
    relationship_state: RelationshipState
    features: tuple[CorrelationFeature, ...]
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    polarity: EvidencePolarity
    claim_type: str
    alert_reference: str
    context_record_reference: str
    source_provider: str
    source_record_id: str
    observed_values: dict[str, Any]
    canonical_values: dict[str, Any]
    correlation_feature_reference: str
    timestamp: datetime | None
    provenance: Provenance


@dataclass(frozen=True)
class EvidenceSet:
    supporting: tuple[EvidenceItem, ...]
    contradicting: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class ConfidenceAssessment:
    level: ConfidenceLevel
    rationale: tuple[str, ...]
    degradation_factors: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentPacket:
    packet_id: str
    schema_version: str
    alert: CanonicalAlert
    execution_status: EnrichmentStatus
    related_context: tuple[CanonicalContextRecord, ...]
    correlation_results: tuple[CorrelationResult, ...]
    evidence_set: EvidenceSet
    confidence: ConfidenceAssessment
    contradictions: tuple[str, ...]
    missing_information: tuple[str, ...]
    provider_diagnostics: tuple[ProviderDiagnostic, ...]
    recommended_review_areas: tuple[str, ...]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ValidationExpectation:
    execution_status: str
    confidence: str | None = None
    related_record_ids: tuple[str, ...] = ()
    candidate_record_ids: tuple[str, ...] = ()
    forbidden_related_record_ids: tuple[str, ...] = ()
    diagnostic_codes: tuple[str, ...] = ()
    minimum_contradictions: int = 0
    deterministic_runs: int = 1


@dataclass(frozen=True)
class ValidationScenario:
    scenario_id: str
    name: str
    alert: dict[str, Any]
    provider_records: dict[str, list[dict[str, Any]]]
    provider_status: dict[str, str]
    expectation: ValidationExpectation
    metric_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    scenario_id: str
    name: str
    outcome: ValidationOutcome
    expected: dict[str, Any]
    actual: dict[str, Any]
    diagnostics: tuple[str, ...]
    false_association: bool = False
    missed_associations: int = 0


@dataclass(frozen=True)
class ValidationReport:
    run_id: str
    schema_version: str
    scenario_count: int
    pass_count: int
    fail_count: int
    error_count: int
    false_association_count: int
    missed_association_count: int
    scenario_results: tuple[ValidationResult, ...]
    diagnostics: tuple[str, ...]
    determinism_result: str
    metrics: dict[str, Any] = field(default_factory=dict)
