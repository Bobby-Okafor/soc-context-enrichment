"""Generic provider query construction owned by the application layer."""

from __future__ import annotations

from context_enrichment.domain.models import CanonicalAlert, ProviderQuery, ResolvedEntity
from context_enrichment.domain.serialization import stable_id


def construct_provider_queries(
    alert: CanonicalAlert,
    resolved_entities: tuple[ResolvedEntity, ...],
    provider_ids: tuple[str, ...],
) -> tuple[ProviderQuery, ...]:
    by_type = {entity.entity_type: entity for entity in resolved_entities}
    user = by_type.get("user")
    host = by_type.get("host")
    queries = []
    for provider_id in sorted(provider_ids):
        queries.append(ProviderQuery(
            query_id=stable_id("query", alert.alert_id, provider_id, user.canonical_value if user else None, host.canonical_value if host else None, alert.action),
            alert_id=alert.alert_id,
            provider_id=provider_id,
            canonical_user=user.canonical_value if user else None,
            canonical_host=host.canonical_value if host else None,
            action=alert.action,
            alert_timestamp=alert.timestamp.normalized_timestamp,
        ))
    return tuple(queries)
