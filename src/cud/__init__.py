"""Cud package."""

from __future__ import annotations

import warnings
from importlib.metadata import PackageNotFoundError, version

# TODO: Remove this warning filter once the internal checkpointer serializers
# (specifically JsonPlusSerializer) are updated to explicitly pass `allowed_objects`.
# Currently, it triggers a LangChainPendingDeprecationWarning on import/instantiation.
# This will likely be resolved in a future update to the `langgraph` or
# `langgraph-checkpoint-sqlite` packages, or when `langchain-core` removes the warning.
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        category=LangChainPendingDeprecationWarning,
        message=".*allowed_objects.*",
    )
except ImportError:
    pass

__all__ = ["__version__"]

try:
    __version__ = version("cud")
except PackageNotFoundError:
    __version__ = "dev"

