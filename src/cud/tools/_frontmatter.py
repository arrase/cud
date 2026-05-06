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
    match = _FRONTMATTER_RE.search(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, text[match.end():]
