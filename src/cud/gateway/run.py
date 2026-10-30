"""Module entrypoint for `python -m cud.gateway.run <agent>`."""

from __future__ import annotations

import asyncio
import logging
import sys

from cud.gateway.discord_adapter import DiscordGateway

_log = logging.getLogger(__name__)
_EXPECTED_ARGV_LEN = 2


def run_gateway(agent: str, *, verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    gateway = DiscordGateway(agent, verbose=verbose)
    try:
        asyncio.run(gateway.run())
    except KeyboardInterrupt:
        _log.info("Shutting down gateway for '%s'", agent)


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != _EXPECTED_ARGV_LEN:
        raise SystemExit("usage: python -m cud.gateway.run <agent>")
    run_gateway(sys.argv[1])
