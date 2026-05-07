"""Module entrypoint for `python -m cud.gateway.run <agent>`."""

from __future__ import annotations

import asyncio
import logging

from .discord_adapter import DiscordGateway

log = logging.getLogger(__name__)


def run_gateway(agent: str, verbose: bool = False) -> None:
    gateway = DiscordGateway(agent, verbose=verbose)
    try:
        asyncio.run(gateway.run())
    except KeyboardInterrupt:
        log.info("Shutting down gateway for '%s'", agent)
    finally:
        asyncio.run(gateway.aclose_sessions())
