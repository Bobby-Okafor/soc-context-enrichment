"""Optional presentation-only model boundary; no model is required or enabled."""

from typing import Any, Mapping, Protocol


class ModelAdapter(Protocol):
    @property
    def enabled(self) -> bool: ...

    def generate_narrative(self, context: Mapping[str, Any]) -> str: ...


class DisabledModelAdapter:
    enabled = False

    def generate_narrative(self, context: Mapping[str, Any]) -> str:
        raise RuntimeError("ModelAdapter is disabled")
