"""Enrich drug records by fetching ChEMBL molecule details.

Reads ChEMBL IDs from `drug_candidates.json` (produced by fetch_opentargets.py)
and writes a single `molecules.json` blob containing all fetched molecule
records. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from rett_repurposing.fetchers.chembl import ChEMBLClient
from rett_repurposing.logging import configure_logging

log = structlog.get_logger("scripts.fetch_chembl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/opentargets/drug_candidates.json"),
        help="Path to Open Targets drug_candidates.json. Default: data/raw/opentargets/drug_candidates.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/chembl"),
        help="Output directory for molecules.json. Default: data/raw/chembl/",
    )
    return parser.parse_args()


def extract_chembl_ids(drug_candidates: dict[str, Any]) -> list[str]:
    """Pull every distinct ChEMBL ID out of an OT drug_candidates response."""
    ids: set[str] = set()
    rows = drug_candidates.get("disease", {}).get("drugAndClinicalCandidates", {}).get("rows", [])
    for row in rows:
        drug = row.get("drug")
        if drug is None:
            continue
        chembl_id = drug.get("id")
        if isinstance(chembl_id, str) and chembl_id.startswith("CHEMBL"):
            ids.add(chembl_id)
    return sorted(ids)


async def run(input_path: Path, output_dir: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(
            f"input file {input_path} not found — run fetch_opentargets.py first"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    drug_candidates = json.loads(input_path.read_text())
    chembl_ids = extract_chembl_ids(drug_candidates)
    log.info("chembl.input.parsed", chembl_id_count=len(chembl_ids))

    if not chembl_ids:
        log.warning("chembl.no_ids", input_path=str(input_path))
        molecules: list[dict[str, Any]] = []
    else:
        async with ChEMBLClient() as client:
            molecules = await client.fetch_molecules_batch(chembl_ids)
        log.info(
            "chembl.fetch.done",
            requested=len(chembl_ids),
            received=len(molecules),
        )

    output_path = output_dir / "molecules.json"
    output_path.write_text(
        json.dumps(
            {
                "__meta__": {
                    "fetched_at": datetime.now(tz=UTC).isoformat(),
                    "requested_chembl_ids": chembl_ids,
                },
                "molecules": molecules,
            },
            indent=2,
        )
    )
    log.info("chembl.done", output_path=str(output_path))


def main() -> int:
    configure_logging()
    args = parse_args()
    asyncio.run(run(args.input, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
