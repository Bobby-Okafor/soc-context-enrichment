"""Alert intake envelope validation only."""

from __future__ import annotations

from typing import Any

from context_enrichment.domain.models import RawAlert


class IntakeValidationError(ValueError):
    pass


def validate_intake_envelope(value: dict[str, Any]) -> RawAlert:
    if not isinstance(value, dict):
        raise IntakeValidationError("INVALID_INPUT: alert envelope must be an object")
    alert_id = value.get("alert_id")
    schema_version = value.get("schema_version")
    payload = value.get("payload")
    if not isinstance(alert_id, str) or not alert_id.strip():
        raise IntakeValidationError("INVALID_INPUT: alert_id is required")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise IntakeValidationError("INVALID_INPUT: schema_version is required")
    if not isinstance(payload, dict):
        raise IntakeValidationError("INVALID_INPUT: payload must be an object")
    if not isinstance(payload.get("action"), str) or not payload["action"].strip():
        raise IntakeValidationError("INVALID_INPUT: payload.action is required")
    if not isinstance(payload.get("user"), str) or not payload["user"].strip():
        raise IntakeValidationError("INVALID_INPUT: payload.user is required")
    return RawAlert(alert_id=alert_id.strip(), schema_version=schema_version.strip(), payload=dict(payload))
