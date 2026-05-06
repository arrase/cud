"""Module entrypoint for `python -m cud.gateway.run <agent>`."""

from __future__ import annotations

import argparse
import asyncio

from .discord_adapter import DiscordGateway


def run_gateway(agent: str, verbose: bool = False) -> None:
    gateway = DiscordGateway(agent, verbose=verbose)
    asyncio.run(gateway.run())

