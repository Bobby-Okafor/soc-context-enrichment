from __future__ import annotations

from datetime import datetime, timezone

import pytest

from context_enrichment.application.intake import IntakeValidationError, validate_intake_envelope
from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import EntityReference, RawProviderRecord, ResolutionQuality, TimestampQuality
from context_enrichment.domain.serialization import canonical_json, stable_id
from context_enrichment.entity_resolution.resolver import EntityResolver
from context_enrichment.normalization.normalizers import AlertNormalizer, ContextNormalizer, NormalizationError, normalize_timestamp


def test_stable_ids_and_serialization_are_deterministic() -> None:
    assert stable_id("x", {"b": 2, "a": 1}) == stable_id("x", {"a": 1, "b": 2})
    assert canonical_json({"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc)}) == '{\n  "timestamp": "2026-01-01T00:00:00Z"\n}\n'


@pytest.mark.parametrize("strong,allowed", [(0, 1440), (30, 30), (60, 30)])
def test_configuration_rejects_invalid_windows(strong: int, allowed: int) -> None:
    with pytest.raises(ValueError):
        EnrichmentConfig(strong_window_minutes=strong, allowed_window_minutes=allowed)


def test_configuration_rejects_unknown_provider_and_path_traversal() -> None:
    with pytest.raises(ValueError, match="unknown providers"):
        EnrichmentConfig(enabled_providers=("unapproved_provider",))
    with pytest.raises(ValueError, match="parent traversal"):
        EnrichmentConfig(fixture_root=__import__("pathlib").Path("fixtures/../outside"))


@pytest.mark.parametrize(
    "raw,quality,normalized",
    [
        ("2026-01-15T10:00:00Z", TimestampQuality.VALID, "2026-01-15T10:00:00+00:00"),
        ("2026-01-15T11:00:00+01:00", TimestampQuality.VALID, "2026-01-15T10:00:00+00:00"),
        ("2026-01-15 10:00:00", TimestampQuality.AMBIGUOUS_TIMEZONE, None),
        ("not-a-time", TimestampQuality.MALFORMED, None),
        (None, TimestampQuality.MISSING, None),
    ],
)
def test_timestamp_contract(raw, quality, normalized) -> None:
    result = normalize_timestamp(raw)
    assert result.timestamp_quality is quality
    assert result.normalized_timestamp.isoformat() == normalized if normalized else result.normalized_timestamp is None


def test_intake_and_alert_normalization_preserve_raw_values() -> None:
    raw = validate_intake_envelope({"alert_id": "a1", "schema_version": "alert_schema_v1", "payload": {"observed_at": "2026-01-15T10:00:00Z", "user": "UserA", "host": "HOST-A", "action": "Account Unlock", "extra": "preserved"}})
    alert = AlertNormalizer(EnrichmentConfig()).normalize(raw)
    assert alert.action == "account_unlock"
    assert alert.raw_values["extra"] == "preserved"
    assert alert.timestamp.timestamp_quality is TimestampQuality.VALID
    assert alert.transformation_chain == ("alert_schema_v1", "alert_normalizer_v1", "canonical_alert_v1")


def test_intake_rejects_missing_required_fields() -> None:
    with pytest.raises(IntakeValidationError, match="payload.action"):
        validate_intake_envelope({"alert_id": "a1", "schema_version": "alert_schema_v1", "payload": {"user": "u"}})


def test_context_schema_v2_and_extra_fields_are_controlled() -> None:
    raw = RawProviderRecord("mock_ticket_provider", "t1", "ticket_schema_v2", datetime(2026, 1, 15, tzinfo=timezone.utc), {"kind": "ticket", "opened_at": "2026-01-15T10:00:00Z", "requested_for": "jsmith", "configuration_item": "HOST.example.local", "operation": "account_unlock", "workflow_state": "pending", "extra": 42})
    record = ContextNormalizer(EnrichmentConfig()).normalize(raw)
    assert record.record_type == "ticket"
    assert record.action == "account_unlock"
    assert record.raw_values["extra"] == 42
    assert record.provenance.transformation_chain[-1] == "canonical_context_v1"


def test_context_schema_incompatibility_is_explicit() -> None:
    raw = RawProviderRecord("mock_ticket_provider", "bad", "ticket_schema_v99", datetime(2026, 1, 15, tzinfo=timezone.utc), {})
    with pytest.raises(NormalizationError, match="SCHEMA_INCOMPATIBILITY"):
        ContextNormalizer(EnrichmentConfig()).normalize(raw)


def test_context_missing_required_action_is_explicit() -> None:
    raw = RawProviderRecord("mock_ticket_provider", "missing-action", "ticket_schema_v1", datetime(2026, 1, 15, tzinfo=timezone.utc), {"record_type": "ticket", "created": "2026-01-15T10:00:00Z", "requester": "jsmith"})
    with pytest.raises(NormalizationError, match="NORMALIZATION_FAILURE"):
        ContextNormalizer(EnrichmentConfig()).normalize(raw)


def test_entity_resolution_alias_host_and_false_similarity() -> None:
    resolver = EntityResolver(EnrichmentConfig())
    alias = resolver.resolve_user("DOMAIN\\jsmith", "test")
    host = resolver.resolve_host("web-prd-01.example.local", "test")
    similar = resolver.resolve_user("john.smith2", "test")
    assert alias.canonical_value == "jsmith" and alias.resolution_quality is ResolutionQuality.EXPLICIT_ALIAS
    assert host.canonical_value == "web-prd-01" and host.resolution_quality is ResolutionQuality.NORMALIZED
    assert similar.canonical_value == "john.smith2" and similar.canonical_value != alias.canonical_value


def test_ambiguous_alias_is_preserved() -> None:
    config = EnrichmentConfig(user_aliases={"shared": ("user-a", "user-b")})
    resolved = EntityResolver(config).resolve(EntityReference("user", "shared", "test"))
    assert resolved.resolution_quality is ResolutionQuality.AMBIGUOUS
    assert resolved.canonical_value is None
    assert resolved.candidate_values == ("user-a", "user-b")
