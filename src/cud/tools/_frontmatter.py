"""YAML frontmatter parser shared by skills and tasks."""

from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into a (metadata, body) pair.

    If the text starts with a YAML frontmatter block delimited by ``---``,
    the block is parsed and returned as a dict.  Otherwise an empty dict
    is returned and *body* equals the full text.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, text[match.end():]


def render_frontmatter(metadata: dict[str, Any], body: str) -> str:
    """Combine *metadata* and *body* into a YAML-frontmatter markdown string.

    If *metadata* is empty the frontmatter block is omitted and only the body
    is returned.
    """
    if not metadata:
        return body
    header = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{header}\n---\n{body}"
