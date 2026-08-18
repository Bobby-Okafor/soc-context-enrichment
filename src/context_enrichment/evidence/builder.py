"""Provenance-bearing evidence construction from correlation observations."""

from __future__ import annotations

from context_enrichment.domain.models import (
    CandidateContext,
    CorrelationResult,
    EvidenceItem,
    EvidencePolarity,
    EvidenceSet,
)
from context_enrichment.domain.serialization import stable_id


SUPPORTING_VALUES = {
    "USER_MATCH": {"EXACT_CANONICAL", "EXPLICIT_ALIAS"},
    "HOST_MATCH": {"EXACT_CANONICAL", "NORMALIZED_EQUIVALENT"},
    "ACTION_COMPATIBILITY": {"EXACT", "COMPATIBLE"},
    "TEMPORAL_RELATIONSHIP": {"WITHIN_STRONG_WINDOW", "WITHIN_ALLOWED_WINDOW"},
    "RECORD_STATE": {"APPROVED", "ACTIVE", "COMPLETED"},
}

CONTRADICTING_VALUES = {
    "USER_MATCH": {"MISMATCH"},
    "HOST_MATCH": {"MISMATCH"},
    "ACTION_COMPATIBILITY": {"CONTRADICTORY"},
    "RECORD_STATE": {"REJECTED", "CANCELLED"},
}


class EvidenceBuilder:
    def build(
        self,
        pairs: tuple[tuple[CandidateContext, CorrelationResult], ...],
    ) -> EvidenceSet:
        supporting: list[EvidenceItem] = []
        contradicting: list[EvidenceItem] = []
        for candidate, result in pairs:
            for feature in result.features:
                polarity = None
                if feature.value in SUPPORTING_VALUES.get(feature.feature_type, set()):
                    polarity = EvidencePolarity.SUPPORTING
                elif feature.value in CONTRADICTING_VALUES.get(feature.feature_type, set()):
                    polarity = EvidencePolarity.CONTRADICTING
                if polarity is None:
                    continue
                item = EvidenceItem(
                    evidence_id=stable_id("evidence", result.alert_reference, candidate.record.source_provider, candidate.record.source_record_id, feature.feature_id, polarity.value),
                    polarity=polarity,
                    claim_type=feature.feature_type,
                    alert_reference=result.alert_reference,
                    context_record_reference=candidate.record.source_record_id,
                    source_provider=candidate.record.source_provider,
                    source_record_id=candidate.record.source_record_id,
                    observed_values={"alert": feature.alert_value, "context": feature.context_value},
                    canonical_values={"feature_value": feature.value},
                    correlation_feature_reference=feature.feature_id,
                    timestamp=candidate.record.timestamp.normalized_timestamp,
                    provenance=candidate.record.provenance,
                )
                (supporting if polarity is EvidencePolarity.SUPPORTING else contradicting).append(item)
        key = lambda item: (item.source_provider, item.source_record_id, item.claim_type, item.polarity.value, item.evidence_id)
        return EvidenceSet(tuple(sorted({item.evidence_id: item for item in supporting}.values(), key=key)), tuple(sorted({item.evidence_id: item for item in contradicting}.values(), key=key)))
