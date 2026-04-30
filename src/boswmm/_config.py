"""Shared config loader for BO-SWMM.

The canonical config file lives at ``src/boswmm/config.yaml``. The
structure is documented in that file; top-level sections include
``optimization`` (mode + BO hyperparameters), ``constraints``
(maintenance budget), and ``kpi`` (paths to the FROI config + data).

A user-supplied ``config`` dict (same shape) can override at runtime.
"""
from __future__ import annotations

import os
import yaml

here = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(here, "config.yaml")


def load_default_config() -> dict:
    """Read the ``config.yaml`` and return the parsed dict."""
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
