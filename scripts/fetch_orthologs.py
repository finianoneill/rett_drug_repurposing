"""Build the committed mouse → human ortholog table from MGI.

Downloads the MGI mouse/human homology report and writes a two-column
``mouse_symbol<TAB>human_symbol`` TSV. Rows in the report are grouped by
``DB Class Key``; within a class we pair each mouse symbol with the (first)
human symbol. Re-run to refresh; the output is committed so signature building
and tests stay offline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import structlog

from rett_repurposing.logging import configure_logging

log = structlog.get_logger("scripts.fetch_orthologs")

MGI_URL = "https://www.informatics.jax.org/downloads/reports/HOM_MouseHumanSequence.rpt"
MOUSE_TAXON = "10090"
HUMAN_TAXON = "9606"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/rett_repurposing/signature/reference/mouse_human_orthologs.tsv"),
        help="Destination TSV path.",
    )
    return parser.parse_args()


def build_map(report_text: str) -> dict[str, str]:
    """Parse the MGI report into a mouse_symbol -> human_symbol map."""
    lines = report_text.splitlines()
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}
    key_i = col["DB Class Key"]
    taxon_i = col["NCBI Taxon ID"]
    symbol_i = col["Symbol"]

    mouse_by_class: dict[str, list[str]] = {}
    human_by_class: dict[str, list[str]] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= symbol_i:
            continue
        cls = parts[key_i]
        taxon = parts[taxon_i]
        symbol = parts[symbol_i].strip()
        if not symbol:
            continue
        if taxon == MOUSE_TAXON:
            mouse_by_class.setdefault(cls, []).append(symbol)
        elif taxon == HUMAN_TAXON:
            human_by_class.setdefault(cls, []).append(symbol)

    mapping: dict[str, str] = {}
    for cls, mouse_syms in mouse_by_class.items():
        humans = human_by_class.get(cls)
        if not humans:
            continue
        for m in mouse_syms:
            mapping.setdefault(m, humans[0])
    return mapping


def main() -> int:
    configure_logging()
    args = parse_args()
    log.info("orthologs.fetch", url=MGI_URL)
    response = httpx.get(MGI_URL, timeout=120.0, follow_redirects=True)
    response.raise_for_status()
    mapping = build_map(response.text)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# mouse_symbol\thuman_symbol",
        "# source: MGI HOM_MouseHumanSequence.rpt",
    ]
    lines.extend(f"{m}\t{h}" for m, h in sorted(mapping.items()))
    args.output.write_text("\n".join(lines) + "\n")
    log.info("orthologs.done", pairs=len(mapping), output=str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
