"""Config loader for the kpi package.

The canonical config lives at ``src/kpi/config.yaml``. A user-supplied
dict of the same shape can be passed at runtime to override.
"""

from __future__ import annotations

import os

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")


def load_default_config() -> dict:
    """Read ``src/kpi/config.yaml`` and return the parsed dict."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_config(user_config: dict | None) -> dict:
    """Return ``user_config`` if provided, otherwise the default config."""
    return user_config if user_config is not None else load_default_config()
