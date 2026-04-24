"""Shared config loader for BO-SWMM.

The canonical config file lives at ``src/boswmm/config.yaml``. The
structure is documented in that file; top-level sections include
``optimization`` (mode + BO hyperparameters), ``constraints``
(maintenance budget), and ``kpi`` (paths to the FROI config + data).

A user-supplied ``config`` dict (same shape) can override at runtime.
"""

import os
import yaml

here = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(here, "config.yaml")


def load_default_config() -> dict:
    """Read the ``config.yaml`` and return the parsed dict."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_config(user_config: dict | None) -> dict:
    """Return ``user_config`` if provided, otherwise the default config."""
    return user_config if user_config is not None else load_default_config()
