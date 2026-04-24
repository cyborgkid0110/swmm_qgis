"""Low-level syntactic parsers and writer for SWMM ``.inp`` files.

Functions here are unaware of scenario semantics — they only convert between
text on disk and dict/list structures. Higher-level semantics (building
scenarios, extracting sediment state) live in ``scenario.builder`` and
``scenario.extractor``.
"""

import re
from collections import OrderedDict


def parse_inp(inp_path: str) -> OrderedDict:
    """Parse an ``.inp`` file into ``OrderedDict[section_name, list[str]]``.

    Lines before the first section header are stored under ``'_PREAMBLE'``.
    Section names are stored without brackets (e.g. ``'XSECTIONS'``).
    Each line retains its original text (including newline).
    """
    sections: OrderedDict = OrderedDict()
    current = "_PREAMBLE"
    sections[current] = []

    with open(inp_path, "r", encoding="utf-8") as f:
        for line in f:
            # SWMM allows mixed-case section headers (e.g. [Polygons] in files
            # written by QGIS' export). Normalize to uppercase so downstream
            # consumers can look sections up by a single canonical name.
            m = re.match(r"^\[([A-Za-z_]+)\]", line.strip())
            if m:
                current = m.group(1).upper()
                sections[current] = []
            else:
                sections[current].append(line)

    return sections


def write_inp(sections: OrderedDict, output_path: str) -> None:
    """Write a section dict back to an ``.inp`` file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for section_name, lines in sections.items():
            if section_name != "_PREAMBLE":
                f.write(f"[{section_name}]\n")
            for line in lines:
                f.write(line)


def parse_conduits(sections: OrderedDict) -> dict:
    """Parse ``[CONDUITS]`` for length, roughness, and node connectivity.

    Returns ``{conduit_name: {from_node, to_node, length, roughness,
    in_offset, out_offset}}``.
    """
    props: dict = {}
    for line in sections.get("CONDUITS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 5:
            continue
        name = tokens[0]
        props[name] = {
            "from_node": tokens[1],
            "to_node": tokens[2],
            "length": float(tokens[3]),
            "roughness": float(tokens[4]),
            "in_offset": float(tokens[5]) if len(tokens) > 5 and tokens[5] != "*" else 0.0,
            "out_offset": float(tokens[6]) if len(tokens) > 6 and tokens[6] != "*" else 0.0,
        }
    return props


def parse_xsections(sections: OrderedDict) -> dict:
    """Parse ``[XSECTIONS]`` for shape and geometry.

    Returns ``{link_name: {shape, geom1, geom2, geom3, geom4, barrels}}``.
    """
    props: dict = {}
    for line in sections.get("XSECTIONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        name = tokens[0]
        props[name] = {
            "shape": tokens[1],
            "geom1": float(tokens[2]) if len(tokens) > 2 else 0.0,
            "geom2": float(tokens[3]) if len(tokens) > 3 else 0.0,
            "geom3": float(tokens[4]) if len(tokens) > 4 else 0.0,
            "geom4": float(tokens[5]) if len(tokens) > 5 else 0.0,
            "barrels": int(float(tokens[6])) if len(tokens) > 6 else 1,
        }
    return props


def parse_xsection_conduit_names(sections: OrderedDict) -> set[str]:
    """Return the set of conduit names that have an ``[XSECTIONS]`` entry."""
    names: set[str] = set()
    for line in sections.get("XSECTIONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        names.add(stripped.split()[0])
    return names


def format_xsection_line(tokens: list[str]) -> str:
    """Format XSECTIONS tokens into an aligned ``.inp`` line."""
    # Widths: Name(17) Shape(17) Geom1(17) Geom2(11) Geom3(11) Geom4(11) Barrels(11)
    parts: list[str] = []
    widths = [17, 17, 17, 11, 11, 11, 11]
    for i, token in enumerate(tokens):
        if i < len(widths):
            parts.append(f"{token:<{widths[i]}}")
        else:
            parts.append(token)
    return "".join(parts).rstrip() + "\n"


def parse_node_elevations(sections: OrderedDict) -> dict:
    """Parse ``[JUNCTIONS]`` and ``[OUTFALLS]`` for invert elevations.

    Returns ``{node_name: elevation}``.
    """
    elevations: dict = {}
    for line in sections.get("JUNCTIONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) >= 2:
            elevations[tokens[0]] = float(tokens[1])
    for line in sections.get("OUTFALLS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) >= 2:
            elevations[tokens[0]] = float(tokens[1])
    return elevations
