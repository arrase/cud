"""Cud package."""

from __future__ import annotations

import warnings
from importlib.metadata import version

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

# Note: Remove this warning filter once the internal checkpointer serializers
# (specifically JsonPlusSerializer) are updated to explicitly pass `allowed_objects`.
# Currently, it triggers a LangChainPendingDeprecationWarning on import/instantiation.
# This will likely be resolved in a future update to the `langgraph` or
# `langgraph-checkpoint-sqlite` packages, or when `langchain-core` removes the warning.
warnings.filterwarnings(
    "ignore",
    category=LangChainPendingDeprecationWarning,
    message=".*allowed_objects.*",
)

__all__ = ["__version__"]

__version__ = version("cud")

