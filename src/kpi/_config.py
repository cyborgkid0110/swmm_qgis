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


def resolve_config(config: dict | str | None = None) -> dict:
    """Resolve a config from a dict, a YAML file path, or ``None`` (default).

    Args:
        config: A parsed config dict, a path to a YAML file, or ``None``
            to load the package default.
    """
    if config is None:
        return load_default_config()
    if isinstance(config, str):
        with open(config, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return config
