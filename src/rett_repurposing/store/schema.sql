-- DuckDB schema for the Rett repurposing local store.
-- See IMPLEMENTATION_BRIEF.md §6.3 — field names are part of the contract.

-- Disease registry (Phase 1: just Rett, but schema supports multi-disease).
CREATE TABLE IF NOT EXISTS diseases (
    efo_id           VARCHAR PRIMARY KEY,
    name             VARCHAR NOT NULL,
    fetched_at       TIMESTAMP NOT NULL
);

-- Targets associated with diseases (from Open Targets associatedTargets).
CREATE TABLE IF NOT EXISTS disease_targets (
    efo_id                    VARCHAR NOT NULL,
    target_ensembl_id         VARCHAR NOT NULL,
    target_symbol             VARCHAR,
    target_name               VARCHAR,
    biotype                   VARCHAR,
    overall_association_score DOUBLE NOT NULL,
    datatype_scores           JSON,
    PRIMARY KEY (efo_id, target_ensembl_id),
    FOREIGN KEY (efo_id) REFERENCES diseases(efo_id)
);

-- Drugs (enriched with ChEMBL data; basic info bootstrapped from Open Targets).
CREATE TABLE IF NOT EXISTS drugs (
    chembl_id            VARCHAR PRIMARY KEY,
    name                 VARCHAR NOT NULL,
    drug_type            VARCHAR,
    max_phase            DOUBLE,
    is_approved          BOOLEAN,
    first_approval_year  INTEGER,
    withdrawn_flag       BOOLEAN,
    trade_names          JSON,
    synonyms             JSON,
    canonical_smiles     VARCHAR,
    atc_classifications  JSON
);

-- Drug-target-disease evidence (from Open Targets drugAndClinicalCandidates,
-- exploded over each mechanism-target pair so the strategy can join cleanly
-- against disease_targets).
CREATE TABLE IF NOT EXISTS drug_target_disease (
    chembl_id            VARCHAR NOT NULL,
    target_ensembl_id    VARCHAR NOT NULL,
    efo_id               VARCHAR NOT NULL,
    phase                DOUBLE,
    status               VARCHAR,
    mechanism_of_action  VARCHAR,
    ct_ids               JSON,
    PRIMARY KEY (chembl_id, target_ensembl_id, efo_id),
    FOREIGN KEY (chembl_id) REFERENCES drugs(chembl_id),
    FOREIGN KEY (efo_id) REFERENCES diseases(efo_id)
);

-- Approved-drugs view: the strategy reads this directly. See §9.
CREATE VIEW IF NOT EXISTS approved_drugs_for_disease AS
SELECT
    d.chembl_id,
    d.name,
    d.first_approval_year,
    dtd.target_ensembl_id,
    dtd.efo_id,
    dtd.mechanism_of_action,
    dtd.phase,
    dtd.status,
    dtd.ct_ids,
    dt.overall_association_score,
    dt.datatype_scores,
    dt.target_symbol,
    dt.target_name,
    dt.biotype
FROM drugs d
JOIN drug_target_disease dtd ON d.chembl_id = dtd.chembl_id
JOIN disease_targets dt
    ON dtd.target_ensembl_id = dt.target_ensembl_id
   AND dtd.efo_id = dt.efo_id
WHERE d.is_approved = TRUE
  AND COALESCE(d.withdrawn_flag, FALSE) = FALSE;
