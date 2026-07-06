"""Build the Rett disease signature from the GEO counts matrix.

Reads ``data/raw/geo/counts.tsv``, runs the KO-vs-WT differential-expression
pass, maps the top mouse genes to human orthologs, and writes the up/down human
gene signature to ``data/raw/signature/rett_signature.json``. This is the query
consumed by ``scripts/fetch_lincs.py``. Network-free (uses the committed
ortholog table). Idempotent.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from rett_repurposing.config import get_settings
from rett_repurposing.logging import configure_logging
from rett_repurposing.signature import (
    compute_disease_signature,
    load_ortholog_map,
    map_signature_to_human,
)
from rett_repurposing.signature.differential_expression import (
    DEFAULT_TOP_N,
    parse_counts_matrix,
)

log = structlog.get_logger("scripts.build_signature")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/geo/counts.tsv"),
        help="GEO counts TSV. Default: data/raw/geo/counts.tsv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/signature"),
        help="Output directory for rett_signature.json. Default: data/raw/signature/",
    )
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    return parser.parse_args()


def run(input_path: Path, output_dir: Path, top_n: int) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found — run fetch_geo.py first")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()

    matrix = parse_counts_matrix(input_path.read_text())
    signature = compute_disease_signature(matrix, top_n=top_n)
    ortholog_map = load_ortholog_map()
    up_human = map_signature_to_human(signature.up_genes, ortholog_map)
    down_human = map_signature_to_human(signature.down_genes, ortholog_map)

    output_path = output_dir / "rett_signature.json"
    output_path.write_text(
        json.dumps(
            {
                "__meta__": {
                    "built_at": datetime.now(tz=UTC).isoformat(),
                    "source": settings.geo_series_accession,
                    "n_ko": signature.n_ko,
                    "n_wt": signature.n_wt,
                    "top_n": top_n,
                },
                "up_genes": up_human,
                "down_genes": down_human,
                "up_genes_mouse": signature.up_genes,
                "down_genes_mouse": signature.down_genes,
                "stats": signature.stats,
            },
            indent=2,
        )
    )
    log.info(
        "signature.build.done",
        output_path=str(output_path),
        up=len(up_human),
        down=len(down_human),
    )


def main() -> int:
    configure_logging()
    args = parse_args()
    run(args.input, args.output, args.top_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
