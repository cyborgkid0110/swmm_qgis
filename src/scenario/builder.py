"""ScenarioBuilder — produce modified ``.inp`` files from a decision vector.

Responsibilities:
  * Load the base SWMM model and the sedimentation CSV that defines the N
    monitoring points.
  * Compute ``v_max`` (current sediment volume per monitored conduit) for use
    as the upper bound of the decision variable.
  * Apply one-time rainfall and discharge overrides.
  * For any maintenance-volume vector ``x ∈ [0, v_max]^N``, write a modified
    ``.inp`` with updated ``[XSECTIONS]`` that reflects remaining sediment
    after maintenance.

ScenarioBuilder is independent of ScenarioExtractor.
"""

import copy
import csv
import os
import tempfile
from collections import OrderedDict

import torch

from .utils.geometry import circular_segment_area, invert_circular_segment_volume
from .utils.parser import (
    format_xsection_line,
    parse_conduits,
    parse_inp,
    parse_xsection_conduit_names,
    parse_xsections,
    write_inp,
)


class ScenarioBuilder:
    """Construct scenario ``.inp`` files for any decision vector."""

    def __init__(
        self,
        base_inp_path: str,
        sedimentation_csv: str,
        rainfall_csv: str | None = None,
        discharge_csv: str | None = None,
        output_dir: str | None = None,
    ):
        if not os.path.isfile(base_inp_path):
            raise FileNotFoundError(f"Base .inp not found: {base_inp_path}")
        if not os.path.isfile(sedimentation_csv):
            raise FileNotFoundError(f"Sedimentation CSV not found: {sedimentation_csv}")

        self._output_dir = output_dir or tempfile.mkdtemp(prefix="scenario_")
        os.makedirs(self._output_dir, exist_ok=True)

        self._base_sections = parse_inp(base_inp_path)

        self._conduit_names, self._filled_depths = self._load_sedimentation_csv(
            sedimentation_csv
        )

        xs_names = parse_xsection_conduit_names(self._base_sections)
        missing = [c for c in self._conduit_names if c not in xs_names]
        if missing:
            print(f"Warning: conduits not found in [XSECTIONS]: {missing}")

        self._conduit_props = parse_conduits(self._base_sections)
        self._xsection_props = parse_xsections(self._base_sections)

        self._v_max = self._compute_v_max()

        if rainfall_csv:
            self._apply_rainfall(self._base_sections, rainfall_csv)
        if discharge_csv:
            self._apply_discharge(self._base_sections, discharge_csv)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def N(self) -> int:
        return len(self._conduit_names)

    @property
    def conduit_names(self) -> list[str]:
        return list(self._conduit_names)

    @property
    def filled_depths(self) -> dict[str, float]:
        return dict(self._filled_depths)

    @property
    def base_sections(self) -> OrderedDict:
        return self._base_sections

    @property
    def output_dir(self) -> str:
        return self._output_dir

    @property
    def v_max(self) -> torch.Tensor:
        return self._v_max.clone()

    @property
    def v_max_sum(self) -> float:
        return float(self._v_max.sum().item())

    # ------------------------------------------------------------------
    # Scenario construction
    # ------------------------------------------------------------------

    def build_scenario(self, x: torch.Tensor, scenario_id: int = 0) -> str:
        """Build a single scenario ``.inp`` from maintenance-volume vector ``x``."""
        if x.shape != (self.N,):
            raise ValueError(f"Expected x of shape ({self.N},), got {x.shape}")

        sections = copy.deepcopy(self._base_sections)
        self._apply_sedimentation(sections, x)

        out_path = os.path.join(self._output_dir, f"scenario_{scenario_id:04d}.inp")
        write_inp(sections, out_path)
        return out_path

    def build_scenarios(self, X: torch.Tensor) -> list[str]:
        """Build scenarios for a batch of maintenance-volume vectors."""
        if X.dim() != 2 or X.shape[1] != self.N:
            raise ValueError(
                f"Expected X of shape (n_samples, {self.N}), got {X.shape}"
            )
        return [self.build_scenario(X[i], scenario_id=i) for i in range(X.shape[0])]

    # ------------------------------------------------------------------
    # Sedimentation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sedimentation_csv(
        csv_path: str,
    ) -> tuple[list[str], dict[str, float]]:
        """Load ``conduit,filled_depth`` rows; preserve CSV order for indexing."""
        conduit_names: list[str] = []
        filled_depths: dict[str, float] = {}
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["conduit"].strip()
                depth = float(row["filled_depth"].strip())
                conduit_names.append(name)
                filled_depths[name] = depth
        if not conduit_names:
            raise ValueError(f"Sedimentation CSV is empty: {csv_path}")
        return conduit_names, filled_depths

    def _compute_v_max(self) -> torch.Tensor:
        """Per-monitoring-point maximum maintenance volume (m^3)."""
        v: list[float] = []
        for name in self._conduit_names:
            h = self._filled_depths[name]
            length = self._conduit_props.get(name, {}).get("length", 0.0)
            diameter = self._xsection_props.get(name, {}).get("geom1", 0.0)
            if length <= 0.0 or diameter <= 0.0:
                raise ValueError(
                    f"Conduit {name!r} missing geometry (length={length}, "
                    f"diameter={diameter}) — cannot compute V_max"
                )
            r = diameter / 2.0
            h_eff = min(max(h, 0.0), diameter)
            v.append(circular_segment_area(h_eff, r) * length)
        return torch.tensor(v, dtype=torch.double)

    def _apply_sedimentation(
        self, sections: OrderedDict, x: torch.Tensor
    ) -> None:
        """Rewrite ``[XSECTIONS]`` in-place for maintenance vector ``x``.

        Three branches per monitoring conduit:
          * ``x_i <= 0``                 -> keep original filled depth
          * ``v_max_i - x_i <= 0``       -> revert to ``CIRCULAR`` (fully clean)
          * otherwise                     -> ``FILLED_CIRCULAR`` with Geom2 = h'
                                             inverted from the remaining volume
        """
        if "XSECTIONS" not in sections:
            raise ValueError("No [XSECTIONS] section in .inp file")

        lookup: dict[str, tuple[int, float, float]] = {}
        for i, name in enumerate(self._conduit_names):
            lookup[name] = (
                i,
                self._filled_depths[name],
                float(self._v_max[i].item()),
            )

        new_lines: list[str] = []
        for line in sections["XSECTIONS"]:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                new_lines.append(line)
                continue

            tokens = stripped.split()
            conduit_name = tokens[0]

            if conduit_name in lookup:
                idx, filled_depth, v_max_i = lookup[conduit_name]
                xi = max(0.0, min(float(x[idx].item()), v_max_i))
                v_remaining = v_max_i - xi

                props = self._conduit_props.get(conduit_name, {})
                xs_props = self._xsection_props.get(conduit_name, {})
                length = props.get("length", 0.0)
                diameter = xs_props.get("geom1", 0.0)

                while len(tokens) < 7:
                    tokens.append("0")

                if xi <= 0.0 or length <= 0.0 or diameter <= 0.0:
                    tokens[1] = "FILLED_CIRCULAR"
                    tokens[3] = f"{filled_depth:.6f}"
                elif v_remaining <= 0.0:
                    tokens[1] = "CIRCULAR"
                    tokens[3] = "0"
                else:
                    h_prime = invert_circular_segment_volume(
                        v_remaining, diameter / 2.0, length, diameter
                    )
                    tokens[1] = "FILLED_CIRCULAR"
                    tokens[3] = f"{h_prime:.6f}"

                line = format_xsection_line(tokens)

            new_lines.append(line)

        sections["XSECTIONS"] = new_lines

    # ------------------------------------------------------------------
    # Rainfall (optional)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_rainfall(sections: OrderedDict, csv_path: str) -> None:
        """Replace ``[RAINGAGES]`` and ``[TIMESERIES]`` from a rainfall CSV.

        Columns: ``Name, Format, Interval, SCF, DataSource, SeriesName,
        Date, Time, Value``.
        """
        gages: list[dict] = []
        timeseries: list[dict] = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gages.append(row)
                timeseries.append(row)

        if not gages:
            return

        seen: set[str] = set()
        gage_lines = [
            ";;Name           Format    Interval SCF      Source    \n",
            ";;-------------- --------- ------ ------ ----------\n",
        ]
        for row in gages:
            name = row.get("Name", "").strip()
            if name and name not in seen:
                seen.add(name)
                fmt = row.get("Format", "INTENSITY").strip()
                interval = row.get("Interval", "1:00").strip()
                scf = row.get("SCF", "1.0").strip()
                source = row.get("DataSource", "TIMESERIES").strip()
                series = row.get("SeriesName", name).strip()
                gage_lines.append(
                    f"{name:<17}{fmt:<10}{interval:<7}{scf:<9}{source:<14}{series}\n"
                )
        gage_lines.append("\n")
        sections["RAINGAGES"] = gage_lines

        ts_lines = [
            ";;Name           Date       Time       Value     \n",
            ";;-------------- ---------- ---------- ----------\n",
        ]
        for row in timeseries:
            name = row.get("SeriesName", row.get("Name", "")).strip()
            date = row.get("Date", "").strip()
            time = row.get("Time", "").strip()
            value = row.get("Value", "").strip()
            if name and time and value:
                if date:
                    ts_lines.append(f"{name:<17}{date:<11}{time:<11}{value}\n")
                else:
                    ts_lines.append(f"{name:<17}{time:<11}{value}\n")
        ts_lines.append("\n")
        sections["TIMESERIES"] = ts_lines

    # ------------------------------------------------------------------
    # Discharge (optional)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_discharge(sections: OrderedDict, csv_path: str) -> None:
        """Add/replace the ``[INFLOWS]`` section from a discharge CSV.

        Columns: ``Node, Constituent, TimeSeries, Type, Mfactor, Sfactor,
        Baseline, Pattern``.
        """
        rows: list[dict] = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return

        lines = [
            ";;Node           Constituent      Time Series      Type     "
            "Mfactor  Sfactor  Baseline Pattern\n",
            ";;-------------- ---------------- ---------------- -------- "
            "-------- -------- -------- --------\n",
        ]
        for row in rows:
            node = row.get("Node", "").strip()
            constituent = row.get("Constituent", "FLOW").strip()
            ts = row.get("TimeSeries", "").strip()
            typ = row.get("Type", "FLOW").strip()
            mfactor = row.get("Mfactor", "1.0").strip()
            sfactor = row.get("Sfactor", "1.0").strip()
            baseline = row.get("Baseline", "0").strip()
            pattern = row.get("Pattern", "").strip()
            if node and ts:
                lines.append(
                    f"{node:<17}{constituent:<17}{ts:<17}{typ:<9}"
                    f"{mfactor:<9}{sfactor:<9}{baseline:<9}{pattern}\n"
                )
        lines.append("\n")
        sections["INFLOWS"] = lines
