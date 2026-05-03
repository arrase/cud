"""Provider registry for gateway adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cud.gateway.discord_adapter import DiscordGateway


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    name: str
    implemented: bool
    adapter: type[Any] | None = None


PROVIDERS: dict[str, ProviderSpec] = {
    "discord": ProviderSpec("discord", True, DiscordGateway),
    "telegram": ProviderSpec("telegram", False, None),
    "slack": ProviderSpec("slack", False, None),
}


def provider_spec(name: str) -> ProviderSpec:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown gateway provider: {name}") from exc

