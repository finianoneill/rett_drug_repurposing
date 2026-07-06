"""Query SigCom LINCS for perturbagens that reverse the Rett signature.

Reads the up/down human gene signature from
``data/raw/signature/rett_signature.json`` and writes the ranked reversing
perturbagens (with two-sided z-scores and drug metadata) to
``data/raw/lincs/reversers.json``. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from rett_repurposing.fetchers.chembl import ChEMBLClient
from rett_repurposing.fetchers.lincs import SigComLincsClient
from rett_repurposing.logging import configure_logging

log = structlog.get_logger("scripts.fetch_lincs")


async def _resolve_to_chembl(
    reversers: list[dict[str, object]],
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """Resolve unique reverser perturbagen names to ChEMBL molecules.

    Returns ``(pert_name -> chembl_id, [raw molecule records])``. Perturbagens
    that don't resolve (research compounds) are dropped from the map.
    """
    names = sorted({str(r["pert_name"]) for r in reversers if r.get("pert_name")})
    name_to_id: dict[str, str] = {}
    molecules: list[dict[str, object]] = []
    async with ChEMBLClient() as chembl:
        for name in names:
            molecule = await chembl.resolve_molecule_by_name(name)
            if molecule and molecule.get("molecule_chembl_id"):
                name_to_id[name] = molecule["molecule_chembl_id"]
                molecules.append(molecule)
    log.info("lincs.chembl_resolved", names=len(names), resolved=len(name_to_id))
    return name_to_id, molecules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/signature/rett_signature.json"),
        help="Disease signature JSON. Default: data/raw/signature/rett_signature.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/lincs"),
        help="Output directory for reversers.json. Default: data/raw/lincs/",
    )
    parser.add_argument("--limit", type=int, default=200)
    return parser.parse_args()


async def run(input_path: Path, output_dir: Path, limit: int) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found — run build_signature.py first")
    output_dir.mkdir(parents=True, exist_ok=True)

    signature = json.loads(input_path.read_text())
    up_genes = signature.get("up_genes", [])
    down_genes = signature.get("down_genes", [])
    log.info("lincs.input.parsed", up=len(up_genes), down=len(down_genes))

    async with SigComLincsClient() as client:
        result = await client.find_reversers(up_genes, down_genes, limit=limit)

    # Map perturbagen names to ChEMBL so reversers become first-class drugs.
    name_to_id, molecules = await _resolve_to_chembl(result["reversers"])
    for reverser in result["reversers"]:
        reverser["chembl_id"] = name_to_id.get(str(reverser.get("pert_name")))

    output_path = output_dir / "reversers.json"
    output_path.write_text(
        json.dumps(
            {
                "__meta__": {
                    "fetched_at": datetime.now(tz=UTC).isoformat(),
                    "limit": limit,
                    "source_signature": str(input_path),
                },
                **result,
                "molecules": molecules,
            },
            indent=2,
        )
    )
    log.info(
        "lincs.done",
        output_path=str(output_path),
        reversers=len(result["reversers"]),
        resolved_drugs=len(molecules),
    )


def main() -> int:
    configure_logging()
    args = parse_args()
    asyncio.run(run(args.input, args.output, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
