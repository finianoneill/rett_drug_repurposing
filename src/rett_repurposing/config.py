"""Application configuration via pydantic-settings.

Reads environment variables (and `.env` when present). Other modules should
inject a `Settings` instance rather than reading `os.environ` directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    duckdb_path: Path = Field(
        default=Path("data/rett_repurposing.duckdb"),
        description="Path to the DuckDB file. Container default: /app/data/rett_repurposing.duckdb.",
    )

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-7"

    opentargets_graphql_url: str = "https://api.platform.opentargets.org/api/v4/graphql"
    chembl_base_url: str = "https://www.ebi.ac.uk/chembl/api/data"

    # Phase 2 — signature reversal.
    # SigCom LINCS lives behind the maayanlab.cloud proxy; the bare ldp3.cloud
    # hostname does not resolve publicly.
    sigcom_lincs_base_url: str = "https://maayanlab.cloud/sigcom-lincs"
    lincs_database: str = "l1000_cp"  # chemical perturbagen signatures
    # GEO series backing the Rett disease signature (Mecp2-null mouse cortex).
    geo_series_accession: str = "GSE300534"
    geo_counts_url: str = (
        "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE300nnn/GSE300534/suppl/"
        "GSE300534_Raw_counts.txt.gz"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance.

    Caching ensures we read `.env` once per process. Tests can clear the cache
    via `get_settings.cache_clear()` after monkey-patching env vars.
    """
    return Settings()
