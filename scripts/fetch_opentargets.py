"""Fetch Rett-associated targets and drug candidates from Open Targets.

Resolves the disease ID via the `search` query, then writes three raw JSON
files into the output directory:

    disease_search.json     -- response of the search query (audit trail)
    disease_targets.json    -- response of DiseaseTargets (Query A)
    drug_candidates.json    -- response of drugAndClinicalCandidates (Query B)

Idempotent: re-running overwrites the JSON files in place.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from rett_repurposing.fetchers.opentargets import OpenTargetsClient
from rett_repurposing.logging import configure_logging

log = structlog.get_logger("scripts.fetch_opentargets")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disease",
        default="Rett syndrome",
        help="Free-text disease name (resolved via Open Targets search). Default: 'Rett syndrome'.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/opentargets"),
        help="Output directory for raw JSON files. Default: data/raw/opentargets/",
    )
    parser.add_argument(
        "--targets-size",
        type=int,
        default=100,
        help="Page size for associatedTargets. Default: 100.",
    )
    return parser.parse_args()


async def run(disease: str, output_dir: Path, targets_size: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    async with OpenTargetsClient() as client:
        log.info("opentargets.search.start", disease=disease)
        search_data = await client.search_disease(disease)
        (output_dir / "disease_search.json").write_text(json.dumps(search_data, indent=2))

        efo_id, resolved_name = await client.resolve_disease_id(disease)
        log.info("opentargets.resolved", efo_id=efo_id, name=resolved_name)

        log.info("opentargets.targets.start", efo_id=efo_id, size=targets_size)
        targets_data = await client.fetch_disease_targets(efo_id, size=targets_size)
        targets_data["__meta__"] = {
            "fetched_at": datetime.now(tz=UTC).isoformat(),
            "efo_id": efo_id,
            "resolved_name": resolved_name,
        }
        (output_dir / "disease_targets.json").write_text(json.dumps(targets_data, indent=2))

        log.info("opentargets.drugs.start", efo_id=efo_id)
        drugs_data = await client.fetch_drug_candidates(efo_id)
        drugs_data["__meta__"] = {
            "fetched_at": datetime.now(tz=UTC).isoformat(),
            "efo_id": efo_id,
            "resolved_name": resolved_name,
        }
        (output_dir / "drug_candidates.json").write_text(json.dumps(drugs_data, indent=2))

    log.info("opentargets.done", output_dir=str(output_dir))


def main() -> int:
    configure_logging()
    args = parse_args()
    asyncio.run(run(args.disease, args.output, args.targets_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
