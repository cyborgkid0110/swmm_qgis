"""Step 1 — InputqEHVISWMM: load base .inp, apply scenario mods, build per-sample .inp files."""

import copy
import csv
import os
import re
import tempfile
from collections import OrderedDict

import torch


class InputqEHVISWMM:
    """Load a base SWMM .inp model, configure sedimentation monitoring points,
    and produce modified .inp files for any binary decision vector x.

    Decision variable x in {0,1}^N:
        x[i] = 1  ->  conduit i is maintained (sediment cleared, stays CIRCULAR)
        x[i] = 0  ->  conduit i is NOT maintained (FILLED_CIRCULAR with filled_depth)
    """

    def __init__(
        self,
        base_inp_path: str,
        sedimentation_csv: str,
        rainfall_csv: str | None = None,
        discharge_csv: str | None = None,
        output_dir: str | None = None,
    ):
        """
        Args:
            base_inp_path: Path to the base SWMM .inp file.
            sedimentation_csv: CSV with columns [conduit, filled_depth].
            rainfall_csv: Optional CSV to replace [RAINGAGES] + [TIMESERIES].
            discharge_csv: Optional CSV to add/replace [INFLOWS].
            output_dir: Directory for modified .inp files. Defaults to a temp dir.
        """
        if not os.path.isfile(base_inp_path):
            raise FileNotFoundError(f"Base .inp not found: {base_inp_path}")
        if not os.path.isfile(sedimentation_csv):
            raise FileNotFoundError(f"Sedimentation CSV not found: {sedimentation_csv}")

        self._output_dir = output_dir or tempfile.mkdtemp(prefix="qehvi_swmm_")
        os.makedirs(self._output_dir, exist_ok=True)

        # Parse base .inp
        self._base_sections = self._parse_inp(base_inp_path)

        # Load sedimentation config
        self._conduit_names, self._filled_depths = self._load_sedimentation(
            sedimentation_csv
        )

        # Validate that sedimentation conduits exist in [XSECTIONS]
        xs_conduits = self._get_xsection_conduit_names(self._base_sections)
        missing = [c for c in self._conduit_names if c not in xs_conduits]
        if missing:
            print(f"Warning: conduits not found in [XSECTIONS]: {missing}")

        # Apply one-time scenario modifications
        if rainfall_csv:
            self._apply_rainfall(self._base_sections, rainfall_csv)
        if discharge_csv:
            self._apply_discharge(self._base_sections, discharge_csv)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def N(self) -> int:
        """Number of sedimentation monitoring points (dimension of x)."""
        return len(self._conduit_names)

    @property
    def conduit_names(self) -> list[str]:
        """Ordered conduit names — index i maps to x[i]."""
        return list(self._conduit_names)

    @property
    def output_dir(self) -> str:
        return self._output_dir

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def build_scenario(self, x: torch.Tensor, scenario_id: int = 0) -> str:
        """Build a single modified .inp from binary vector x.

        Args:
            x: Binary tensor of shape (N,).
            scenario_id: Integer used in the output filename.

        Returns:
            Path to the generated .inp file.
        """
        if x.shape != (self.N,):
            raise ValueError(f"Expected x of shape ({self.N},), got {x.shape}")

        sections = copy.deepcopy(self._base_sections)
        self._apply_sedimentation(sections, x)

        out_path = os.path.join(self._output_dir, f"scenario_{scenario_id:04d}.inp")
        self._write_inp(sections, out_path)
        return out_path

    def build_scenarios(self, X: torch.Tensor) -> list[str]:
        """Build modified .inp files for a batch of binary vectors.

        Args:
            X: Binary tensor of shape (n_samples, N).

        Returns:
            List of paths to generated .inp files.
        """
        if X.dim() != 2 or X.shape[1] != self.N:
            raise ValueError(
                f"Expected X of shape (n_samples, {self.N}), got {X.shape}"
            )
        return [self.build_scenario(X[i], scenario_id=i) for i in range(X.shape[0])]

    # ------------------------------------------------------------------
    # .inp parsing / writing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_inp(inp_path: str) -> OrderedDict:
        """Parse .inp file into OrderedDict[section_name, list[str]].

        Lines before the first section header go under key '_PREAMBLE'.
        Section names are stored WITHOUT brackets (e.g. 'XSECTIONS').
        Each line retains its original text (including newline).
        """
        sections = OrderedDict()
        current = "_PREAMBLE"
        sections[current] = []

        with open(inp_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\[([A-Z_]+)\]", line.strip())
                if m:
                    current = m.group(1)
                    sections[current] = []
                else:
                    sections[current].append(line)

        return sections

    @staticmethod
    def _write_inp(sections: OrderedDict, output_path: str) -> None:
        """Write section dict back to .inp file."""
        with open(output_path, "w", encoding="utf-8") as f:
            for section_name, lines in sections.items():
                if section_name != "_PREAMBLE":
                    f.write(f"[{section_name}]\n")
                for line in lines:
                    f.write(line)

    # ------------------------------------------------------------------
    # Sedimentation
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sedimentation(csv_path: str) -> tuple[list[str], dict[str, float]]:
        """Load sedimentation CSV with columns [conduit, filled_depth].

        Returns:
            (conduit_names, filled_depths) where conduit_names is the ordered
            list and filled_depths maps conduit name -> depth value.
        """
        conduit_names = []
        filled_depths = {}
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

    def _apply_sedimentation(
        self, sections: OrderedDict, x: torch.Tensor
    ) -> None:
        """Modify [XSECTIONS] in-place based on binary vector x.

        x[i]=0 (not maintained): CIRCULAR -> FILLED_CIRCULAR, Geom2 = filled_depth
        x[i]=1 (maintained):     keep original line (CIRCULAR)
        """
        if "XSECTIONS" not in sections:
            raise ValueError("No [XSECTIONS] section in .inp file")

        # Build lookup: conduit_name -> (index_in_x, filled_depth)
        lookup = {}
        for i, name in enumerate(self._conduit_names):
            lookup[name] = (i, self._filled_depths[name])

        new_lines = []
        for line in sections["XSECTIONS"]:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                new_lines.append(line)
                continue

            tokens = stripped.split()
            conduit_name = tokens[0]

            if conduit_name in lookup:
                idx, depth = lookup[conduit_name]
                if int(x[idx].item()) == 0:
                    # Not maintained -> apply sedimentation
                    tokens[1] = "FILLED_CIRCULAR"
                    # Ensure Geom2 position exists
                    while len(tokens) < 7:
                        tokens.append("0")
                    tokens[3] = str(depth)
                    line = self._format_xsection_line(tokens)

            new_lines.append(line)

        sections["XSECTIONS"] = new_lines

    @staticmethod
    def _format_xsection_line(tokens: list[str]) -> str:
        """Format XSECTIONS tokens into aligned .inp line."""
        # Widths: Name(17) Shape(17) Geom1(17) Geom2(11) Geom3(11) Geom4(11) Barrels(11)
        parts = []
        widths = [17, 17, 17, 11, 11, 11, 11]
        for i, token in enumerate(tokens):
            if i < len(widths):
                parts.append(f"{token:<{widths[i]}}")
            else:
                parts.append(token)
        return "".join(parts).rstrip() + "\n"

    @staticmethod
    def _get_xsection_conduit_names(sections: OrderedDict) -> set[str]:
        """Extract conduit names from [XSECTIONS] section."""
        names = set()
        for line in sections.get("XSECTIONS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            names.add(stripped.split()[0])
        return names

    # ------------------------------------------------------------------
    # Rainfall (optional)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_rainfall(sections: OrderedDict, csv_path: str) -> None:
        """Replace [RAINGAGES] and [TIMESERIES] sections from rainfall CSV.

        CSV columns: Name, Format, Interval, SCF, DataSource, SeriesName,
                     Date, Time, Value
        Raingages rows define the gage; timeseries rows define the rainfall data.
        """
        gages = []
        timeseries = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gages.append(row)
                timeseries.append(row)

        if not gages:
            return

        # Build unique raingages
        seen = set()
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

        # Build timeseries
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
                    ts_lines.append(
                        f"{name:<17}{date:<11}{time:<11}{value}\n"
                    )
                else:
                    ts_lines.append(f"{name:<17}{time:<11}{value}\n")
        ts_lines.append("\n")
        sections["TIMESERIES"] = ts_lines

    # ------------------------------------------------------------------
    # Discharge (optional)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_discharge(sections: OrderedDict, csv_path: str) -> None:
        """Add/replace [INFLOWS] section from discharge CSV.

        CSV columns: Node, Constituent, TimeSeries, Type, Mfactor, Sfactor,
                     Baseline, Pattern
        """
        rows = []
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
