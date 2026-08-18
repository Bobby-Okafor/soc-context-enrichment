"""Schema and UTC normalization with retained raw values and diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import (
    CanonicalAlert,
    CanonicalContextRecord,
    Provenance,
    RawAlert,
    RawProviderRecord,
    TimestampQuality,
    TimestampValue,
)


class NormalizationError(ValueError):
    pass


def normalize_timestamp(raw: Any) -> TimestampValue:
    if raw is None or raw == "":
        return TimestampValue(None if raw is None else str(raw), None, TimestampQuality.MISSING)
    if not isinstance(raw, str):
        return TimestampValue(str(raw), None, TimestampQuality.MALFORMED)
    text = raw.strip()
    try:
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return TimestampValue(raw, None, TimestampQuality.MALFORMED)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return TimestampValue(raw, None, TimestampQuality.AMBIGUOUS_TIMEZONE)
    return TimestampValue(raw, parsed.astimezone(timezone.utc), TimestampQuality.VALID)


class AlertNormalizer:
    def __init__(self, config: EnrichmentConfig) -> None:
        self.config = config

    def normalize(self, raw: RawAlert) -> CanonicalAlert:
        if raw.schema_version not in self.config.alert_schema_versions:
            raise NormalizationError(f"SCHEMA_INCOMPATIBILITY: unsupported alert schema {raw.schema_version}")
        timestamp = normalize_timestamp(raw.payload.get("observed_at"))
        diagnostics: list[str] = []
        if timestamp.timestamp_quality is not TimestampQuality.VALID:
            diagnostics.append(f"ALERT_TIMESTAMP_{timestamp.timestamp_quality.value}")
        return CanonicalAlert(
            alert_id=raw.alert_id,
            schema_version="canonical_alert_v1",
            timestamp=timestamp,
            user=_clean(raw.payload.get("user")),
            host=_clean(raw.payload.get("host")),
            action=_canonical_token(raw.payload.get("action")),
            alert_type=_canonical_token(raw.payload.get("alert_type")),
            raw_values=dict(raw.payload),
            diagnostics=tuple(diagnostics),
            transformation_chain=(raw.schema_version, "alert_normalizer_v1", "canonical_alert_v1"),
        )


SCHEMA_MAPPINGS: dict[str, dict[str, str]] = {
    "ticket_schema_v1": {
        "record_type": "record_type", "timestamp": "created", "user": "requester",
        "host": "target_host", "action": "request_type", "state": "status",
    },
    "ticket_schema_v2": {
        "record_type": "kind", "timestamp": "opened_at", "user": "requested_for",
        "host": "configuration_item", "action": "operation", "state": "workflow_state",
    },
    "change_schema_v1": {
        "record_type": "record_type", "timestamp": "scheduled_at", "user": "actor",
        "host": "asset", "action": "change_type", "state": "approval_state",
    },
    "case_schema_v1": {
        "record_type": "record_type", "timestamp": "closed_at", "user": "subject_user",
        "host": "subject_host", "action": "activity", "state": "case_state",
    },
    "identity_schema_v1": {
        "record_type": "record_type", "timestamp": "event_time", "user": "account",
        "host": "device", "action": "operation", "state": "result",
    },
    "asset_schema_v1": {
        "record_type": "record_type", "timestamp": "updated_at", "user": "owner",
        "host": "hostname", "action": "context_action", "state": "lifecycle_state",
    },
}


DEFAULT_RECORD_TYPES = {
    "ticket_schema_v1": "ticket", "ticket_schema_v2": "ticket",
    "change_schema_v1": "change", "case_schema_v1": "historical_case",
    "identity_schema_v1": "identity_activity", "asset_schema_v1": "asset_context",
}


class ContextNormalizer:
    def __init__(self, config: EnrichmentConfig) -> None:
        self.config = config

    def normalize(self, raw: RawProviderRecord) -> CanonicalContextRecord:
        mapping = SCHEMA_MAPPINGS.get(raw.source_schema_version)
        if mapping is None or raw.source_schema_version not in self.config.context_schema_versions:
            raise NormalizationError(
                f"SCHEMA_INCOMPATIBILITY: {raw.source_provider}/{raw.source_record_id} schema {raw.source_schema_version}"
            )
        values = raw.raw_values
        timestamp = normalize_timestamp(values.get(mapping["timestamp"]))
        diagnostics: list[str] = []
        if timestamp.timestamp_quality is not TimestampQuality.VALID:
            diagnostics.append(f"CONTEXT_TIMESTAMP_{timestamp.timestamp_quality.value}")
        record_type = _canonical_token(values.get(mapping["record_type"])) or DEFAULT_RECORD_TYPES[raw.source_schema_version]
        user = _clean(values.get(mapping["user"]))
        action = _canonical_token(values.get(mapping["action"]))
        if not record_type or not action:
            raise NormalizationError(
                f"NORMALIZATION_FAILURE: {raw.source_provider}/{raw.source_record_id} missing record_type/action"
            )
        if user is None:
            diagnostics.append("CONTEXT_USER_MISSING")
        host = _clean(values.get(mapping["host"]))
        if host is None:
            diagnostics.append("CONTEXT_HOST_MISSING")
        state = (_canonical_token(values.get(mapping["state"])) or "unknown").upper()
        provenance = Provenance(
            source_provider=raw.source_provider,
            source_record_id=raw.source_record_id,
            source_schema_version=raw.source_schema_version,
            retrieved_at=raw.retrieved_at,
            transformation_chain=(raw.source_schema_version, "context_normalizer_v1", "canonical_context_v1"),
        )
        return CanonicalContextRecord(
            source_provider=raw.source_provider,
            source_record_id=raw.source_record_id,
            source_schema_version=raw.source_schema_version,
            record_type=record_type,
            timestamp=timestamp,
            user=user,
            host=host,
            action=action,
            record_state=state,
            raw_values=dict(values),
            provenance=provenance,
            diagnostics=tuple(diagnostics),
        )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_token(value: Any) -> str | None:
    cleaned = _clean(value)
    return cleaned.lower().replace(" ", "_").replace("-", "_") if cleaned else None
