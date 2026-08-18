"""Canonical deterministic serialization helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        utc = value.astimezone(timezone.utc)
        return utc.isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    if isinstance(value, set):
        return [to_primitive(item) for item in sorted(value, key=str)]
    return value


def canonical_json(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(to_primitive(value), indent=indent, sort_keys=True, separators=(",", ": ") if indent else (",", ":"), ensure_ascii=False) + ("\n" if indent else "")


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    material = canonical_json(parts, indent=None).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:length]}"
