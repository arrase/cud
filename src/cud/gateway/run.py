"""Module entrypoint for `python -m cud.gateway.run <agent>`."""

from __future__ import annotations

import argparse
import asyncio

from .discord_adapter import DiscordGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    gateway = DiscordGateway(args.agent, verbose=args.verbose)
    asyncio.run(gateway.run())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

