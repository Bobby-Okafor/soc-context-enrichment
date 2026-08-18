"""Explicit validated configuration for the deterministic prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_PROVIDERS = (
    "mock_ticket_provider",
    "mock_change_provider",
    "mock_historical_case_provider",
    "mock_identity_provider",
    "mock_asset_provider",
)


@dataclass(frozen=True)
class EnrichmentConfig:
    strong_window_minutes: int = 30
    allowed_window_minutes: int = 1440
    enabled_providers: tuple[str, ...] = DEFAULT_PROVIDERS
    fixture_root: Path = Path("fixtures")
    user_aliases: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "domain\\jsmith": ("jsmith",),
        "john.smith": ("jsmith",),
        "jsmith": ("jsmith",),
        "john.smith2": ("john.smith2",),
        "asmith": ("asmith",),
    })
    host_dns_suffixes: tuple[str, ...] = (".example.local",)
    compatible_actions: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "privileged_password_change": ("password_reset", "administrative_password_change", "identity_password_change"),
        "account_unlock": ("account_unlock", "identity_account_unlock"),
        "mfa_reset": ("mfa_reset", "identity_mfa_reset"),
        "service_restart": ("service_restart",),
        "server_configuration_change": ("server_configuration_change",),
    })
    contradictory_actions: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "privileged_password_change": ("account_disable", "password_change_denied", "identity_password_change_denied"),
        "account_unlock": ("account_lock", "account_disable"),
        "mfa_reset": ("mfa_reset_denied",),
    })
    alert_schema_versions: tuple[str, ...] = ("alert_schema_v1",)
    context_schema_versions: tuple[str, ...] = (
        "ticket_schema_v1", "ticket_schema_v2", "change_schema_v1",
        "case_schema_v1", "identity_schema_v1", "asset_schema_v1",
    )

    def __post_init__(self) -> None:
        if self.strong_window_minutes <= 0:
            raise ValueError("strong_window_minutes must be positive")
        if self.allowed_window_minutes <= self.strong_window_minutes:
            raise ValueError("allowed_window_minutes must exceed strong_window_minutes")
        unknown = set(self.enabled_providers) - set(DEFAULT_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown providers: {sorted(unknown)}")
        root = self.fixture_root.resolve()
        if ".." in self.fixture_root.parts:
            raise ValueError("fixture_root must not contain parent traversal")
        object.__setattr__(self, "fixture_root", root)
