"""Module entrypoint for `python -m cud.gateway.run <agent>`."""

from __future__ import annotations

import asyncio
import logging

from .discord_adapter import DiscordGateway

_log = logging.getLogger(__name__)


def run_gateway(agent: str, verbose: bool = False) -> None:
    gateway = DiscordGateway(agent, verbose=verbose)
    try:
        asyncio.run(_run_and_cleanup(gateway))
    except KeyboardInterrupt:
        _log.info("Shutting down gateway for '%s'", agent)


async def _run_and_cleanup(gateway: DiscordGateway) -> None:
    try:
        await gateway.run()
    finally:
        await gateway.aclose_sessions()
