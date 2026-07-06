"""Mouse → human ortholog mapping for the disease signature.

The disease signature is derived from mouse (Mecp2-null) expression, but LINCS
L1000 signatures are human. We map mouse gene symbols to human symbols using a
committed two-column table derived once from the MGI mouse/human homology
report (``scripts/fetch_orthologs.py``).
"""

from __future__ import annotations

from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# Committed reference table (package-relative so it ships with the source).
ORTHOLOG_TABLE = Path(__file__).parent / "reference" / "mouse_human_orthologs.tsv"


def load_ortholog_map(path: Path | None = None) -> dict[str, str]:
    """Load a ``mouse_symbol -> human_symbol`` map from the reference TSV."""
    table = path or ORTHOLOG_TABLE
    if not table.exists():
        raise FileNotFoundError(
            f"ortholog table {table} not found — run scripts/fetch_orthologs.py"
        )
    mapping: dict[str, str] = {}
    for line in table.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] and parts[1]:
            mapping.setdefault(parts[0], parts[1])
    log.info("signature.orthologs_loaded", pairs=len(mapping))
    return mapping


def map_signature_to_human(
    mouse_symbols: list[str],
    ortholog_map: dict[str, str],
) -> list[str]:
    """Map mouse symbols to human, dropping unmapped genes and de-duplicating.

    Order is preserved (rank matters for the top-N signature); the first
    occurrence of each human symbol wins. Genes with no explicit ortholog fall
    back to the upper-cased symbol when that is itself a known human ortholog
    (many mouse/human symbols differ only in case, e.g. ``Bdnf`` → ``BDNF``).
    """
    human_symbols = set(ortholog_map.values())
    human: list[str] = []
    seen: set[str] = set()
    for sym in mouse_symbols:
        mapped = ortholog_map.get(sym)
        if mapped is None and sym.upper() in human_symbols:
            mapped = sym.upper()
        if mapped and mapped not in seen:
            seen.add(mapped)
            human.append(mapped)
    return human
