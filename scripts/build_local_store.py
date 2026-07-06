"""CLI entry point that wraps `rett_repurposing.store.build.build()`.

This is the only process that should write to the DuckDB file (DuckDB is
single-writer; the backend opens read-only).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rett_repurposing.config import get_settings
from rett_repurposing.logging import configure_logging
from rett_repurposing.store.build import build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opentargets-dir",
        type=Path,
        default=Path("data/raw/opentargets"),
        help="Directory containing OT raw JSON files. Default: data/raw/opentargets/",
    )
    parser.add_argument(
        "--chembl-dir",
        type=Path,
        default=Path("data/raw/chembl"),
        help="Directory containing ChEMBL raw JSON files. Default: data/raw/chembl/",
    )
    parser.add_argument(
        "--signature-dir",
        type=Path,
        default=Path("data/raw/signature"),
        help="Directory with the Phase 2 disease signature. Default: data/raw/signature/",
    )
    parser.add_argument(
        "--lincs-dir",
        type=Path,
        default=Path("data/raw/lincs"),
        help="Directory with the Phase 2 LINCS reversers. Default: data/raw/lincs/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output DuckDB path. Default: settings.duckdb_path.",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    duckdb_path = args.output or get_settings().duckdb_path
    build(
        args.opentargets_dir,
        args.chembl_dir,
        Path(duckdb_path),
        signature_dir=args.signature_dir,
        lincs_dir=args.lincs_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
