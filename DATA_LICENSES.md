# Data Licenses & Attribution

This file enumerates every external data source the project consumes, the license it ships under, and the attribution required when using it. Keep this file in sync with the fetchers in `scripts/` and `src/rett_repurposing/fetchers/`.

## Phase 1 sources

### Open Targets Platform

- **Use:** primary source of disease–target associations and known drug–target–disease evidence (`knownDrugs`).
- **Endpoint:** `https://api.platform.opentargets.org/api/v4/graphql`
- **License:** [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) — public domain dedication.
- **Attribution:** not legally required, but requested. We cite Open Targets in the README and in any derived publications. Suggested citation:
  > Ochoa et al., "Open Targets Platform: supporting systematic drug–target identification and prioritisation," *Nucleic Acids Research*, 2023.
- **Notes:** Open Targets integrates many upstream sources (ChEMBL, Reactome, GWAS Catalog, ClinVar, Orphanet, gene expression atlases). Each upstream source carries its own license; for the slice we consume via the GraphQL API the CC0 dedication applies to the integrated representation.

### ChEMBL

- **Use:** drug enrichment — `max_phase`, `first_approval`, `withdrawn_flag`, canonical SMILES, ATC classification.
- **Endpoint:** `https://www.ebi.ac.uk/chembl/api/data/`
- **License:** [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
- **Attribution required:** yes. We cite ChEMBL in the README and in any derived publications. Suggested citation:
  > Zdrazil et al., "The ChEMBL Database in 2023: a drug discovery platform spanning multiple bioactivity data types and time periods," *Nucleic Acids Research*, 2024.
- **Share-alike implication:** derived works that redistribute ChEMBL data (not just analyses) must use the same CC BY-SA license. We do not redistribute raw ChEMBL data — we fetch on demand and persist a derived DuckDB locally (gitignored).

## Phase 2+ sources (placeholders)

Add entries here as additional sources are integrated. Anticipated:

- **LINCS L1000 / clue.io** — drug-induced gene expression signatures (CC0 / open).
- **GEO** — raw RNA-seq for Mecp2-null mouse models (NIH public domain).
- **GTEx** — human tissue expression (open access).
- **Human Protein Atlas** — tissue/subcellular expression (CC BY-SA 3.0).
- **STRING** — protein–protein interaction network (CC BY 4.0).
- **OmniPath** — curated signaling pathways (mixed licenses; attribution required per upstream).
- **MONDO / Orphanet** — disease ontologies (CC BY 4.0).
- **OMIM** — gene–phenotype (restricted academic license).
- **PDB / AlphaFold DB** — structures (open).

## Posture

Methods, code, and derived analyses are publishable. Raw bulk data is **never committed** — the `.gitignore` blocks `data/` and the common biomedical formats (`.duckdb`, `.parquet`, `.h5ad`, `.gctx`, `.mtx`, `.loom`).
