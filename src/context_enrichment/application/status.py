"""Execution state derivation kept outside confidence."""

from __future__ import annotations

from collections import Counter

from context_enrichment.domain.models import CorrelationResult, EnrichmentStatus, ProviderDiagnostic, RelationshipState


def determine_execution_status(
    results: tuple[CorrelationResult, ...],
    diagnostics: tuple[ProviderDiagnostic, ...],
) -> EnrichmentStatus:
    provider_failed = any(item.code in {"PROVIDER_UNAVAILABLE", "PROVIDER_PARTIAL", "INTERNAL_PROVIDER_EXCEPTION"} for item in diagnostics)
    supported = [item for item in results if item.relationship_state in {RelationshipState.SUPPORTED, RelationshipState.PARTIALLY_SUPPORTED}]
    contradicted = [item for item in results if item.relationship_state is RelationshipState.CONTRADICTED]
    if contradicted:
        return EnrichmentStatus.CONTRADICTORY_CONTEXT
    if supported:
        operational = [item for item in supported if item.source_provider in {"mock_ticket_provider", "mock_change_provider"}]
        grouped = Counter((item.source_provider, _feature(item, "USER_MATCH"), _feature(item, "HOST_MATCH"), _feature(item, "ACTION_COMPATIBILITY"), _feature(item, "TEMPORAL_RELATIONSHIP")) for item in operational)
        if any(count > 1 for count in grouped.values()):
            return EnrichmentStatus.AMBIGUOUS_CONTEXT
        if provider_failed:
            return EnrichmentStatus.PARTIAL_ENRICHMENT
        return EnrichmentStatus.RELATED_CONTEXT_FOUND
    if provider_failed:
        return EnrichmentStatus.ENRICHMENT_FAILED
    return EnrichmentStatus.NO_RELIABLE_CONTEXT_FOUND


def _feature(result: CorrelationResult, kind: str) -> str:
    return next((feature.value for feature in result.features if feature.feature_type == kind), "UNAVAILABLE")
