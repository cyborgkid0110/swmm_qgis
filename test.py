"""
Validate a SWMM .inp file using the pyswmm engine.

Runs the simulation and parses the generated .rpt report file to display
all errors, warnings, and continuity statistics.

Prerequisites:
    conda run -n qgis-env pip install pyswmm

Usage:
    conda run -n qgis-env python test.py
    conda run -n qgis-env python test.py path/to/model.inp
"""

import os
import sys

REPO_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_INP = os.path.join(REPO_DIR, "result", "swmm_output", "hanoi_sewer_sample.inp")


def run_simulation(inp_file):
    """Run SWMM simulation via pyswmm. Returns path to .rpt report file."""
    from pyswmm import Simulation

    print(f"Running: {inp_file}")
    with Simulation(inp_file) as sim:
        sim.execute()
    rpt_file = inp_file.replace(".inp", ".rpt")
    print(f"Done.  Report: {rpt_file}")
    return rpt_file


def parse_report(rpt_file):
    """Read .rpt file and print errors, warnings, and continuity stats."""
    if not os.path.exists(rpt_file):
        print(f"Report file not found: {rpt_file}")
        return

    errors = []
    warnings = []
    continuity = []
    status_lines = []

    with open(rpt_file, encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("ERROR"):
                errors.append(stripped)
            elif stripped.startswith("WARNING"):
                warnings.append(stripped)
            elif "Continuity Error" in stripped:
                continuity.append(stripped)
            elif stripped.startswith("Analysis") or stripped.startswith("Simulation"):
                status_lines.append(stripped)

    # Summary
    print("\n" + "=" * 60)
    print("SWMM Report Summary")
    print("=" * 60)

    print(f"\n--- Status ({len(status_lines)}) ---")
    for s in status_lines:
        print(f"  {s}")

    print(f"\n--- Errors ({len(errors)}) ---")
    if errors:
        for e in errors:
            print(f"  {e}")
    else:
        print("  (none)")

    print(f"\n--- Warnings ({len(warnings)}) ---")
    if warnings:
        for w in warnings:
            print(f"  {w}")
    else:
        print("  (none)")

    print(f"\n--- Continuity ---")
    if continuity:
        for c in continuity:
            print(f"  {c}")
    else:
        print("  (not found)")

    print("=" * 60)
    if not errors:
        print("RESULT: OK - no errors")
    else:
        print(f"RESULT: FAILED - {len(errors)} error(s)")
    print("=" * 60)


def main():
    inp_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INP

    if not os.path.exists(inp_file):
        print(f"ERROR: Input file not found: {inp_file}")
        print("Run 'conda run -n qgis-env python src/conversion.py' first.")
        sys.exit(1)

    try:
        rpt_file = run_simulation(inp_file)
    except ImportError:
        print("ERROR: pyswmm not installed.")
        print("Install with: conda run -n qgis-env pip install pyswmm")
        sys.exit(1)

    parse_report(rpt_file)


if __name__ == "__main__":
    main()
