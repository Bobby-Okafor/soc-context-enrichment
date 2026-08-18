"""Deterministic eligibility selection, ordering, and duplicate control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from context_enrichment.domain.models import CandidateContext, CanonicalAlert, CanonicalContextRecord, ResolutionQuality, ResolvedEntity


@dataclass(frozen=True)
class SelectionResult:
    candidates: tuple[CandidateContext, ...]
    diagnostics: tuple[str, ...]
    rejected_record_ids: tuple[str, ...]
    rejected_reasons: tuple[tuple[str, str], ...]


class CandidateSelector:
    def select(
        self,
        alert: CanonicalAlert,
        alert_entities: tuple[ResolvedEntity, ...],
        records: tuple[tuple[CanonicalContextRecord, tuple[ResolvedEntity, ...]], ...],
    ) -> SelectionResult:
        alert_map = {item.entity_type: item for item in alert_entities}
        seen: set[tuple[str, str]] = set()
        candidates: list[CandidateContext] = []
        diagnostics: list[str] = []
        rejected: list[str] = []
        rejected_reasons: list[tuple[str, str]] = []
        for record, entities in sorted(records, key=lambda item: (item[0].source_provider, item[0].source_record_id)):
            key = (record.source_provider, record.source_record_id)
            if key in seen:
                diagnostics.append(f"DUPLICATE_RECORD_SUPPRESSED:{record.source_provider}:{record.source_record_id}")
                continue
            seen.add(key)
            context_map = {item.entity_type: item for item in entities}
            user_equal = _equal(alert_map.get("user"), context_map.get("user"))
            host_equal = _equal(alert_map.get("host"), context_map.get("host"))
            user_explicit_mismatch = _explicit_mismatch(alert_map.get("user"), context_map.get("user"))
            host_explicit_mismatch = _explicit_mismatch(alert_map.get("host"), context_map.get("host"))
            reasons: list[str] = []
            if user_equal:
                reasons.append("CANONICAL_USER_EQUALITY")
                if _alias_used(alert_map.get("user"), context_map.get("user")):
                    reasons.append("EXPLICIT_USER_ALIAS")
            if host_equal:
                reasons.append("CANONICAL_HOST_EQUALITY")
            if alert.action and record.action and (alert.action == record.action):
                reasons.append("EXACT_ACTION_TOKEN")
            if record.record_type in {"historical_case", "asset_context"} and (user_equal or host_equal):
                reasons.append("CONTEXT_RECORD_TYPE_ELIGIBLE")
            # Host alone can never overcome a known user mismatch.
            eligible = user_equal or (host_equal and not user_explicit_mismatch and context_map.get("user", None) is None)
            if not eligible or (host_equal and user_explicit_mismatch):
                rejected.append(record.source_record_id)
                rejected_reasons.append((record.source_record_id, "EXPLICIT_USER_MISMATCH" if user_explicit_mismatch else "NO_SAFE_ENTITY_JOIN"))
                continue
            # User equality allows correlation to explicitly reject a host mismatch.
            if host_explicit_mismatch:
                reasons.append("HOST_MISMATCH_REQUIRES_EVALUATION")
            distance = _distance(alert.timestamp.normalized_timestamp, record.timestamp.normalized_timestamp)
            if distance is not None:
                reasons.append("TIMESTAMP_AVAILABLE")
            specificity = 0 if user_equal and host_equal else 1 if user_equal else 2
            candidates.append(CandidateContext(record, entities, tuple(sorted(set(reasons))), specificity, distance))
        candidates.sort(key=lambda item: (
            item.entity_specificity,
            item.temporal_distance_seconds if item.temporal_distance_seconds is not None else 2**63 - 1,
            item.record.source_provider,
            item.record.source_record_id,
        ))
        return SelectionResult(tuple(candidates), tuple(sorted(diagnostics)), tuple(sorted(rejected)), tuple(sorted(rejected_reasons)))


def _equal(left: ResolvedEntity | None, right: ResolvedEntity | None) -> bool:
    return bool(left and right and left.canonical_value and right.canonical_value and left.canonical_value == right.canonical_value and left.resolution_quality is not ResolutionQuality.AMBIGUOUS and right.resolution_quality is not ResolutionQuality.AMBIGUOUS)


def _explicit_mismatch(left: ResolvedEntity | None, right: ResolvedEntity | None) -> bool:
    return bool(left and right and left.canonical_value and right.canonical_value and left.canonical_value != right.canonical_value)


def _alias_used(left: ResolvedEntity | None, right: ResolvedEntity | None) -> bool:
    return bool(left and right and ResolutionQuality.EXPLICIT_ALIAS in {left.resolution_quality, right.resolution_quality})


def _distance(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    return int(abs((left - right).total_seconds()))
