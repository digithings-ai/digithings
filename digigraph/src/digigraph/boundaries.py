"""Shared runtime error boundaries for graph and HTTP handlers."""

from __future__ import annotations

import yaml

PROJECT_CONFIG_ERRORS = (OSError, yaml.YAMLError, AttributeError, TypeError, ValueError)

GRAPH_RUNTIME_ERRORS = (
    ValueError,
    KeyError,
    TypeError,
    RuntimeError,
    ImportError,
    OSError,
    AttributeError,
)

STREAM_SSE_ERRORS = (
    *GRAPH_RUNTIME_ERRORS,
    GeneratorExit,
)
