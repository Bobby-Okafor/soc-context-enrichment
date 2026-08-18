"""Deterministic, ambiguity-preserving identity resolution."""

from __future__ import annotations

from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import EntityReference, ResolutionQuality, ResolvedEntity


class EntityResolver:
    def __init__(self, config: EnrichmentConfig) -> None:
        self.config = config

    def resolve(self, reference: EntityReference) -> ResolvedEntity:
        if reference.entity_type in {"user", "account", "ticket_requester", "ticket_target"}:
            return self._resolve_user(reference)
        if reference.entity_type in {"host", "asset"}:
            return self._resolve_host(reference)
        return self._unresolved(reference, "unsupported_entity_type")

    def resolve_user(self, value: str | None, source: str) -> ResolvedEntity:
        return self.resolve(EntityReference("user", value, source))

    def resolve_host(self, value: str | None, source: str) -> ResolvedEntity:
        return self.resolve(EntityReference("host", value, source))

    def _resolve_user(self, ref: EntityReference) -> ResolvedEntity:
        if ref.input_value is None or not ref.input_value.strip():
            return self._unresolved(ref, "missing")
        value = ref.input_value.strip().lower()
        aliases = self.config.user_aliases.get(value)
        if aliases:
            candidates = tuple(sorted(set(item.lower() for item in aliases)))
            if len(candidates) > 1:
                return ResolvedEntity(ref.entity_type, ref.input_value, None, candidates, "explicit_alias_map", ResolutionQuality.AMBIGUOUS, (ref.source_reference, "user_aliases"))
            quality = ResolutionQuality.EXACT if value == candidates[0] else ResolutionQuality.EXPLICIT_ALIAS
            method = "exact_identifier" if quality is ResolutionQuality.EXACT else "explicit_alias_map"
            return ResolvedEntity(ref.entity_type, ref.input_value, candidates[0], candidates, method, quality, (ref.source_reference, "user_aliases"))
        if "\\" in value:
            stripped = value.split("\\", 1)[1]
            aliases = self.config.user_aliases.get(stripped)
            if aliases and len(set(aliases)) == 1:
                canonical = tuple(aliases)[0].lower()
                return ResolvedEntity(ref.entity_type, ref.input_value, canonical, (canonical,), "domain_prefix_normalization", ResolutionQuality.NORMALIZED, (ref.source_reference, "domain_prefix_rule"))
        # Deterministic canonical transformation, not similarity matching.
        return ResolvedEntity(ref.entity_type, ref.input_value, value, (value,), "case_normalization", ResolutionQuality.NORMALIZED if value != ref.input_value else ResolutionQuality.EXACT, (ref.source_reference, "lowercase_rule"))

    def _resolve_host(self, ref: EntityReference) -> ResolvedEntity:
        if ref.input_value is None or not ref.input_value.strip():
            return self._unresolved(ref, "missing")
        original = ref.input_value.strip()
        value = original.lower().rstrip(".")
        method = "case_normalization"
        for suffix in self.config.host_dns_suffixes:
            if value.endswith(suffix.lower()):
                value = value[: -len(suffix)]
                method = "configured_dns_suffix_normalization"
                break
        quality = ResolutionQuality.EXACT if value == original else ResolutionQuality.NORMALIZED
        return ResolvedEntity(ref.entity_type, ref.input_value, value, (value,), method, quality, (ref.source_reference, "host_canonicalization_v1"))

    @staticmethod
    def _unresolved(ref: EntityReference, method: str) -> ResolvedEntity:
        return ResolvedEntity(ref.entity_type, ref.input_value, None, (), method, ResolutionQuality.UNRESOLVED, (ref.source_reference,))
