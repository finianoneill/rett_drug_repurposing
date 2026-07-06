"""Download the GEO counts matrix backing the Rett disease signature.

Fetches the configured series' supplementary counts file (default
``GSE300534``, Mecp2-null mouse cortex) and writes the decompressed TSV to
``data/raw/geo/counts.tsv``. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from rett_repurposing.config import get_settings
from rett_repurposing.fetchers.geo import GeoClient
from rett_repurposing.logging import configure_logging

log = structlog.get_logger("scripts.fetch_geo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/geo"),
        help="Output directory for counts.tsv. Default: data/raw/geo/",
    )
    return parser.parse_args()


async def run(output_dir: Path) -> None:
    settings = get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)

    async with GeoClient() as client:
        text = await client.fetch_counts()

    counts_path = output_dir / "counts.tsv"
    counts_path.write_text(text)
    (output_dir / "meta.json").write_text(
        _meta_json(settings.geo_series_accession, settings.geo_counts_url)
    )
    log.info("geo.done", output_path=str(counts_path), bytes=len(text))


def _meta_json(accession: str, url: str) -> str:
    import json

    return json.dumps(
        {
            "fetched_at": datetime.now(tz=UTC).isoformat(),
            "series_accession": accession,
            "source_url": url,
        },
        indent=2,
    )


def main() -> int:
    configure_logging()
    args = parse_args()
    asyncio.run(run(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
