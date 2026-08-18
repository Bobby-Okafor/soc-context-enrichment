"""Semantic relationship-trust assessment, separate from evidence construction."""

from __future__ import annotations

from context_enrichment.domain.models import (
    ConfidenceAssessment,
    ConfidenceLevel,
    CorrelationResult,
    EvidenceSet,
    ProviderDiagnostic,
    RelationshipState,
)


class ConfidenceAssessor:
    def assess(
        self,
        results: tuple[CorrelationResult, ...],
        evidence: EvidenceSet,
        provider_diagnostics: tuple[ProviderDiagnostic, ...],
        normalization_diagnostics: tuple[str, ...],
    ) -> ConfidenceAssessment:
        supported = [item for item in results if item.relationship_state in {RelationshipState.SUPPORTED, RelationshipState.PARTIALLY_SUPPORTED}]
        contradicted = [item for item in results if item.relationship_state is RelationshipState.CONTRADICTED]
        provider_degraded = any(item.code in {"PROVIDER_UNAVAILABLE", "PROVIDER_PARTIAL"} for item in provider_diagnostics)
        factors: list[str] = []
        if provider_degraded:
            factors.append("PARTIAL_PROVIDER_AVAILABILITY")
        factors.extend(sorted(set(normalization_diagnostics)))
        if contradicted or evidence.contradicting:
            factors.append("CONTRADICTORY_EVIDENCE")
        if not supported:
            level = ConfidenceLevel.LOW if contradicted else ConfidenceLevel.INSUFFICIENT_CONTEXT
            reason = "No safely supported relationship is available" if not contradicted else "Explicit contradiction prevents a trustworthy supported relationship"
            return ConfidenceAssessment(level, (reason,), tuple(sorted(set(factors))))
        features = [feature for result in supported for feature in result.features]
        values = {(item.feature_type, item.value) for item in features}
        if supported and all(result.relationship_state is RelationshipState.PARTIALLY_SUPPORTED for result in supported):
            factors.append("PARTIAL_RELATIONSHIP_SUPPORT")
        strong_supported = [item for item in supported if item.relationship_state is RelationshipState.SUPPORTED]
        if strong_supported and all(
            any(feature.feature_type == "USER_MATCH" and feature.value == "EXPLICIT_ALIAS" for feature in item.features)
            for item in strong_supported
        ):
            factors.append("EXPLICIT_ALIAS_RESOLUTION")
        if ("TEMPORAL_RELATIONSHIP", "WITHIN_ALLOWED_WINDOW") in values:
            factors.append("WEAKER_TEMPORAL_PROXIMITY")
        if ("TEMPORAL_RELATIONSHIP", "UNKNOWN") in values:
            factors.append("TIMESTAMP_UNAVAILABLE")
        if any(("RECORD_STATE", value) in values for value in {"PENDING", "UNKNOWN"}):
            factors.append("NON_FINAL_RECORD_STATE")
        factors = sorted(set(factors))
        if "CONTRADICTORY_EVIDENCE" in factors:
            level = ConfidenceLevel.LOW
        elif any(item in factors for item in {"PARTIAL_RELATIONSHIP_SUPPORT", "EXPLICIT_ALIAS_RESOLUTION", "WEAKER_TEMPORAL_PROXIMITY", "TIMESTAMP_UNAVAILABLE", "NON_FINAL_RECORD_STATE", "PARTIAL_PROVIDER_AVAILABILITY"}):
            level = ConfidenceLevel.MEDIUM
        else:
            has_strong = any(
                result.relationship_state is RelationshipState.SUPPORTED
                and {feature.value for feature in result.features if feature.feature_type == "USER_MATCH"} & {"EXACT_CANONICAL"}
                and {feature.value for feature in result.features if feature.feature_type == "HOST_MATCH"} & {"EXACT_CANONICAL", "NORMALIZED_EQUIVALENT"}
                and {feature.value for feature in result.features if feature.feature_type == "ACTION_COMPATIBILITY"} & {"EXACT", "COMPATIBLE"}
                and {feature.value for feature in result.features if feature.feature_type == "TEMPORAL_RELATIONSHIP"} & {"WITHIN_STRONG_WINDOW"}
                for result in supported
            )
            level = ConfidenceLevel.HIGH if has_strong else ConfidenceLevel.MEDIUM
        return ConfidenceAssessment(level, (f"Relationship trust assessed as {level.value} from deterministic support and degradation semantics",), tuple(factors))
