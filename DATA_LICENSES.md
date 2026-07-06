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

## Phase 2 sources (signature reversal)

### SigCom LINCS / LINCS L1000

- **Use:** ranks chemical perturbagens by how strongly their L1000 transcriptional signature reverses the Rett disease signature. Accessed via the SigCom LINCS REST API (`enrich/ranktwosided`, `l1000_cp`).
- **Endpoint:** `https://maayanlab.cloud/sigcom-lincs` (metadata-api + data-api).
- **License:** LINCS L1000 data is released as open/CC0 by the NIH LINCS program; the SigCom LINCS search engine (Ma'ayan Lab) is free and key-less.
- **Attribution:** cite the LINCS program and SigCom LINCS. Suggested citations:
  > Evangelista et al., "SigCom LINCS: data and metadata search engine for a million gene expression signatures," *Nucleic Acids Research*, 2022.
  > Subramanian et al., "A Next Generation Connectivity Map: L1000 Platform and the First 1,000,000 Profiles," *Cell*, 2017.
- **Notes:** we persist only derived reversal scores (aggregated per drug) in the local DuckDB — not the raw L1000 signature matrices.

### GEO (Gene Expression Omnibus)

- **Use:** the Rett disease expression signature is derived from Mecp2-null vs wild-type mouse cortex RNA-seq. Default series **GSE300534** ("Brain Mecp2 Genetic Dosage and Gene Therapy... in Rett Syndrome"); we download its supplementary raw-counts matrix.
- **Endpoint:** `https://ftp.ncbi.nlm.nih.gov/geo/series/…` (NCBI GEO).
- **License:** NIH GEO data is public domain (U.S. Government work). Individual submitters retain authorship credit.
- **Attribution:** cite the originating study's GEO accession (GSE300534) in derived analyses.

### MGI (Mouse Genome Informatics)

- **Use:** mouse → human gene ortholog mapping (`HOM_MouseHumanSequence.rpt`), applied when translating the mouse disease signature to the human gene space LINCS uses. A derived two-column table is committed under `src/rett_repurposing/signature/reference/`.
- **Endpoint:** `https://www.informatics.jax.org/downloads/reports/`
- **License:** MGI data are freely available for research use; attribution requested.
- **Attribution:**
  > Baldarelli et al., "Mouse Genome Informatics: an integrated knowledgebase system for the laboratory mouse," *Genetics*, 2024.

## Phase 3+ sources (placeholders)

Add entries here as additional sources are integrated. Anticipated:

- **GTEx** — human tissue expression (open access).
- **Human Protein Atlas** — tissue/subcellular expression (CC BY-SA 3.0).
- **STRING** — protein–protein interaction network (CC BY 4.0).
- **OmniPath** — curated signaling pathways (mixed licenses; attribution required per upstream).
- **MONDO / Orphanet** — disease ontologies (CC BY 4.0).
- **OMIM** — gene–phenotype (restricted academic license).
- **PDB / AlphaFold DB** — structures (open).

## Posture

Methods, code, and derived analyses are publishable. Raw bulk data is **never committed** — the `.gitignore` blocks `data/` and the common biomedical formats (`.duckdb`, `.parquet`, `.h5ad`, `.gctx`, `.mtx`, `.loom`).
