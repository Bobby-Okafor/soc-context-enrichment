"""Explicit deterministic correlation feature evaluation and classification."""

from __future__ import annotations

from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import (
    CandidateContext,
    CanonicalAlert,
    CorrelationFeature,
    CorrelationResult,
    RelationshipState,
    ResolutionQuality,
    ResolvedEntity,
)
from context_enrichment.domain.serialization import stable_id


class CorrelationEngine:
    def __init__(self, config: EnrichmentConfig) -> None:
        self.config = config

    def correlate(
        self,
        alert: CanonicalAlert,
        alert_entities: tuple[ResolvedEntity, ...],
        candidate: CandidateContext,
    ) -> CorrelationResult:
        alert_map = {item.entity_type: item for item in alert_entities}
        context_map = {item.entity_type: item for item in candidate.resolved_entities}
        values = {
            "USER_MATCH": self._user_match(alert_map.get("user"), context_map.get("user")),
            "HOST_MATCH": self._host_match(alert_map.get("host"), context_map.get("host")),
            "ACTION_COMPATIBILITY": self._action(alert.action, candidate.record.action),
            "TEMPORAL_RELATIONSHIP": self._temporal(candidate.temporal_distance_seconds),
            "RECORD_STATE": self._record_state(candidate.record.record_state),
        }
        features = tuple(
            CorrelationFeature(
                feature_id=stable_id("feature", alert.alert_id, candidate.record.source_provider, candidate.record.source_record_id, kind, value),
                feature_type=kind,
                value=value,
                explanation=self._explain(kind, value),
                alert_value=self._alert_value(kind, alert, alert_map),
                context_value=self._context_value(kind, candidate, context_map),
            )
            for kind, value in values.items()
        )
        relationship = self._classify(candidate.record.record_type, values)
        explanations = tuple(feature.explanation for feature in features) + (f"RELATIONSHIP:{relationship.value}",)
        return CorrelationResult(
            correlation_id=stable_id("correlation", alert.alert_id, candidate.record.source_provider, candidate.record.source_record_id, relationship.value),
            alert_reference=alert.alert_id,
            context_record_reference=candidate.record.source_record_id,
            source_provider=candidate.record.source_provider,
            relationship_state=relationship,
            features=features,
            explanation=explanations,
        )

    @staticmethod
    def _user_match(alert: ResolvedEntity | None, context: ResolvedEntity | None) -> str:
        if not alert or not context or not alert.input_value or not context.input_value:
            return "UNAVAILABLE"
        if ResolutionQuality.AMBIGUOUS in {alert.resolution_quality, context.resolution_quality}:
            return "AMBIGUOUS"
        if not alert.canonical_value or not context.canonical_value:
            return "UNAVAILABLE"
        if alert.canonical_value != context.canonical_value:
            return "MISMATCH"
        if ResolutionQuality.EXPLICIT_ALIAS in {alert.resolution_quality, context.resolution_quality}:
            return "EXPLICIT_ALIAS"
        return "EXACT_CANONICAL"

    @staticmethod
    def _host_match(alert: ResolvedEntity | None, context: ResolvedEntity | None) -> str:
        if not alert or not context or not alert.input_value or not context.input_value:
            return "UNAVAILABLE"
        if ResolutionQuality.AMBIGUOUS in {alert.resolution_quality, context.resolution_quality}:
            return "AMBIGUOUS"
        if not alert.canonical_value or not context.canonical_value:
            return "UNAVAILABLE"
        if alert.canonical_value != context.canonical_value:
            return "MISMATCH"
        if ResolutionQuality.NORMALIZED in {alert.resolution_quality, context.resolution_quality}:
            return "NORMALIZED_EQUIVALENT"
        return "EXACT_CANONICAL"

    def _action(self, alert_action: str | None, context_action: str | None) -> str:
        if not alert_action or not context_action:
            return "UNKNOWN"
        if alert_action == context_action:
            return "EXACT"
        if context_action in self.config.compatible_actions.get(alert_action, ()):
            return "COMPATIBLE"
        if context_action in self.config.contradictory_actions.get(alert_action, ()):
            return "CONTRADICTORY"
        return "UNRELATED"

    def _temporal(self, seconds: int | None) -> str:
        if seconds is None:
            return "UNKNOWN"
        if seconds <= self.config.strong_window_minutes * 60:
            return "WITHIN_STRONG_WINDOW"
        if seconds <= self.config.allowed_window_minutes * 60:
            return "WITHIN_ALLOWED_WINDOW"
        return "STALE"

    @staticmethod
    def _record_state(value: str) -> str:
        normalized = value.upper()
        return normalized if normalized in {"APPROVED", "ACTIVE", "COMPLETED", "PENDING", "REJECTED", "CANCELLED"} else "UNKNOWN"

    @staticmethod
    def _classify(record_type: str, values: dict[str, str]) -> RelationshipState:
        if values["ACTION_COMPATIBILITY"] == "CONTRADICTORY" or values["RECORD_STATE"] in {"REJECTED", "CANCELLED"}:
            return RelationshipState.CONTRADICTED
        if values["USER_MATCH"] in {"MISMATCH", "AMBIGUOUS"}:
            return RelationshipState.NOT_SUPPORTED
        if values["HOST_MATCH"] == "MISMATCH":
            return RelationshipState.NOT_SUPPORTED
        if values["ACTION_COMPATIBILITY"] == "UNRELATED" or values["TEMPORAL_RELATIONSHIP"] == "STALE":
            return RelationshipState.NOT_SUPPORTED
        user_supported = values["USER_MATCH"] in {"EXACT_CANONICAL", "EXPLICIT_ALIAS"}
        host_supported = values["HOST_MATCH"] in {"EXACT_CANONICAL", "NORMALIZED_EQUIVALENT", "UNAVAILABLE"}
        action_supported = values["ACTION_COMPATIBILITY"] in {"EXACT", "COMPATIBLE"}
        time_supported = values["TEMPORAL_RELATIONSHIP"] in {"WITHIN_STRONG_WINDOW", "WITHIN_ALLOWED_WINDOW"}
        if user_supported and host_supported and action_supported and time_supported:
            if record_type in {"historical_case", "asset_context"} or values["RECORD_STATE"] in {"PENDING", "UNKNOWN"}:
                return RelationshipState.PARTIALLY_SUPPORTED
            return RelationshipState.SUPPORTED
        if user_supported and action_supported and values["TEMPORAL_RELATIONSHIP"] == "UNKNOWN":
            return RelationshipState.PARTIALLY_SUPPORTED
        return RelationshipState.NOT_SUPPORTED

    @staticmethod
    def _explain(kind: str, value: str) -> str:
        return f"{kind}:{value}"

    @staticmethod
    def _alert_value(kind: str, alert: CanonicalAlert, entities: dict[str, ResolvedEntity]) -> object:
        if kind == "USER_MATCH":
            return entities.get("user").canonical_value if entities.get("user") else None
        if kind == "HOST_MATCH":
            return entities.get("host").canonical_value if entities.get("host") else None
        if kind == "ACTION_COMPATIBILITY":
            return alert.action
        if kind == "TEMPORAL_RELATIONSHIP":
            return alert.timestamp.normalized_timestamp
        return None

    @staticmethod
    def _context_value(kind: str, candidate: CandidateContext, entities: dict[str, ResolvedEntity]) -> object:
        if kind == "USER_MATCH":
            return entities.get("user").canonical_value if entities.get("user") else None
        if kind == "HOST_MATCH":
            return entities.get("host").canonical_value if entities.get("host") else None
        if kind == "ACTION_COMPATIBILITY":
            return candidate.record.action
        if kind == "TEMPORAL_RELATIONSHIP":
            return candidate.record.timestamp.normalized_timestamp
        return candidate.record.record_state
