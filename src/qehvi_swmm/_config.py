"""Shared config loader for qEHVI-SWMM.

The canonical config file lives at the ``src/qehvi_swmm/config.yaml`` and
uses three top-level sections:

    kpi:
      f1: {alpha, beta}
      f2: {zeta, gamma, delta}
      f3: {mu, nu}
    bo:
      n_init, max_iter, batch_size, num_restarts, raw_samples, mc_samples,
      patience, seed, ref_point_offset
    constraints:
      maintenance_budget

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
