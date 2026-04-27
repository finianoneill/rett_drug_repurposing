# Rett Syndrome Drug Repurposing — Project Design Document

*An in-silico repurposing system for rare disease, built as a hobby project to learn biology, exercise modern agentic patterns, and explore the NVIDIA BioNeMo ecosystem.*

---

## 1. Project Vision

A publicly available agentic system that performs **in-silico drug repurposing for Rett syndrome** by reasoning over public biomedical data and ranking off-patent compounds as repurposing candidates. The system is built around a closed experimental decision loop — hypothesis → "assay" → readout → updated belief → next hypothesis — where the "assays" are data queries and computational models rather than wet experiments.

The project has three personal objectives, in priority order:

1. **Learn neurodevelopmental rare-disease biology** by working a real repurposing pipeline end-to-end.
2. **Build a meaningful agentic system** outside the constraints of enterprise infrastructure.
3. **Explore the NVIDIA BioNeMo ecosystem** in the places where it earns its keep (deferred to v1).

It is explicitly **not** a digital twin of laboratory equipment. The interesting abstraction is a twin of the *experimental decision loop*, not the bench.

---

## 2. Why Rett Syndrome

Rett is unusually well-suited to a hobby-scale repurposing project for three converging reasons.

**A built-in oracle for validation.** Trofinetide (brand name Daybue, an IGF-1 analog) was approved by the FDA in 2023 as the first disease-modifying treatment for Rett syndrome. Its development emerged from exactly the kind of pathway-driven repurposing reasoning this system aims to automate. If our pipeline ranks IGF-1 axis modulators, BDNF-pathway compounds, NMDA modulators, or sigma-1 agonists in its top results, we have empirical evidence the methodology is working — *before* using it to surface novel candidates. This is an unusually clean validation story for a hobby project and a strong README narrative.

**A single causal gene that is undruggable.** Rett is caused by loss-of-function mutations in MECP2, an X-linked transcriptional regulator. MECP2 itself has no druggable pocket — it is a chromatin reader, not an enzyme. This means *every* viable repurposing strategy must operate on **downstream pathways**, which forces the agent to reason about pathway context rather than direct binding. Pedagogically this is ideal: it makes you learn the disease biology to interpret any result.

**Rich, license-clean public data.** Rett has substantial coverage in Open Targets, GEO (multiple Mecp2-null mouse expression datasets), ChEMBL, LINCS, and the rare-disease ontologies. There is enough signal in public data alone to do this work credibly.

---

## 3. Biology Primer (Working Knowledge for v0)

A short list of concepts the system needs to model and the developer needs to internalize.

**MECP2.** X-linked gene encoding methyl-CpG-binding protein 2. Acts as a global regulator of gene expression by binding methylated DNA. Loss-of-function mutations cause Rett syndrome. Because of X-linkage, the disease almost exclusively affects females (heterozygous, mosaic expression due to X-inactivation); affected males typically do not survive infancy.

**Disease course.** Apparently normal early development, followed by regression at roughly 6–18 months: loss of acquired speech and purposeful hand use, characteristic stereotyped hand movements, gait abnormalities, breathing irregularities, seizures, autonomic dysfunction.

**Key downstream pathways (the actual repurposing surface).**

- **IGF-1 / Insulin-like growth factor signaling** — implicated in synaptic maturation deficits; the trofinetide axis.
- **BDNF / TrkB signaling** — MECP2 regulates BDNF expression; many Rett phenotypes track BDNF deficiency.
- **NMDA / glutamate balance** — excitatory/inhibitory imbalance is a core feature; NMDA modulators are an active class.
- **KCC2 / NKCC1 chloride balance** — GABAergic signaling polarity, relevant to seizures and excitatory tone.
- **Sigma-1 receptor** — neuroprotective chaperone, investigational target class for Rett.
- **Mitochondrial function** — bioenergetic deficits documented in Rett models.

These pathways are the targets the system should preferentially explore when MECP2 itself is not directly actionable.

---

## 4. Data Layer

The single most important architectural decision: **do not build a knowledge graph from scratch.** Open Targets already integrates ChEMBL, Reactome, GWAS Catalog, ClinVar, Orphanet, and gene expression atlases under a unified schema with a public GraphQL API. It *is* the knowledge graph for this use case. Supplement with raw sources where needed.

| Source | Purpose | Access | License |
|---|---|---|---|
| Open Targets Platform | Primary disease–target–drug graph | GraphQL API, parquet downloads | CC0 |
| ChEMBL | Compound bioactivity, approval status | REST API, SQL dump | CC BY-SA 3.0 |
| LINCS L1000 (clue.io) | Drug-induced gene expression signatures | clue.io query API, Touchstone signatures | CC0 / open |
| GEO | Raw RNA-seq for Mecp2-null mouse models | Programmatic via GEOquery / direct FTP | Public domain (NIH) |
| GTEx | Human tissue expression context | Portal + API | Open access |
| Human Protein Atlas | Tissue/subcellular protein expression | API + downloads | CC BY-SA 3.0 |
| STRING | Protein–protein interaction network | Downloads + API | CC BY 4.0 |
| OmniPath | Curated signaling pathways | pypath, REST API | Mixed, attribution required |
| MONDO | Cross-ontology disease ID harmonization | OBO download | CC BY 4.0 |
| Orphanet | Rare disease ontology, gene associations | XML/OWL dump | CC BY 4.0 |
| OMIM | Gene–phenotype associations | Licensed API (free for academic) | Restricted |
| PDB / AlphaFold DB | Structures (deferred to v1) | Direct download | Open |

**Operational rule.** Commit fetchers and schemas; never commit raw bulk data. Local store is **DuckDB** (single file, embedded, fast on the analytic joins this workload requires). Postgres is unnecessary at v0 and can be swapped in later if the project graduates.

**Data licensing posture.** Methods, code, and derived analyses are publishable. DrugBank's open subset is CC BY-NC and is fine for a non-commercial hobby project but should be flagged in the README. A `DATA_LICENSES.md` file enumerates per-source attribution.

---

## 5. Repurposing Strategies

Classical in-silico repurposing decomposes into four strategy families. The system implements three of them at v0 (one at a time), defers the fourth, and uses an aggregation layer to combine their rankings.

**Target-based.** Disease has a known causal gene; find approved off-patent drugs that hit that gene or its high-confidence pathway neighbors. For Rett: MECP2 is undruggable, so this strategy operates on the downstream pathway gene set. Open Targets makes this tractable in one or two GraphQL queries. *Implemented first because end-to-end shippability is highest.*

**Signature reversal (connectivity mapping).** Build a "Rett signature" from MECP2-knockout mouse brain RNA-seq (GEO has multiple datasets). Score drugs by how strongly their LINCS L1000 perturbation signature reverses the disease signature. Works even when mechanism is unclear. *Implemented second.*

**Network proximity.** Compute graph distance between drug-target sets and the Rett gene set on the STRING PPI network. Methodology follows Barabási group's published approach. *Implemented third.*

**Structure-based (DiffDock and friends).** Dock off-patent compound libraries against specific structural targets. *Deferred to v1.* Most Rett-relevant signaling lives at the pathway level; there is no single structural target where docking earns its keep at v0. The natural v1 entry point is scoring binding of top candidates surfaced by other strategies against specific downstream targets (TrkB, sigma-1, etc.).

---

## 6. Architecture

The orchestration pattern is a direct map of how a real preclinical team works: a principal investigator (supervisor) triages the question, dispatches bench scientists (strategy nodes) based on what evidence is available, and convenes a results meeting (synthesizer) to integrate findings into a ranked candidate list with an evidence trail.

```
                ┌──────────────────┐
                │   Supervisor     │   triages: which strategies are
                │   (LangGraph)    │   feasible given available data?
                └────────┬─────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────────┐  ┌───────────────┐
   │ Target-  │   │  Signature   │  │   Network     │
   │ based    │   │  Reversal    │  │   Proximity   │
   └────┬─────┘   └──────┬───────┘  └───────┬───────┘
        │                │                  │
        └────────────────┼──────────────────┘
                         ▼
                ┌──────────────────┐
                │   Synthesizer    │   v0: weighted ensemble
                │                  │   v1: hierarchical Bayesian
                └────────┬─────────┘
                         │
                         ▼
              Ranked candidate list
              + evidence trail per candidate
```

**Tool interface convention.** Each strategy is implemented as a function whose signature matches what an MCP tool would look like — `run_target_based(disease_id: str) -> CandidateList`. This is deliberate: when the project graduates to wanting an external Claude Desktop client to drive the system, exposing each strategy as an MCP server is a refactor of one decorator, not a rewrite.

**Why no Temporal in v0.** "Experiments" at this scale run in seconds to minutes, not hours. LangGraph with a SQLite checkpointer handles state. Temporal becomes worth its weight when long-running activities (real docking, large-scale signature computation) enter the picture in v1+.

---

## 7. Stack Decisions

| Layer | Choice | Rationale |
|---|---|---|
| Orchestration | LangGraph + SQLite checkpointer | No infra, full agentic state machine |
| Backend | FastAPI | Streaming SSE bridge, matches GMIND patterns |
| Frontend | Next.js + Vercel AI SDK | Consistent with GMIND practice |
| Local store | DuckDB | Embedded, single-file, ideal for analytic joins |
| Models (data) | Pydantic | Disease, Target, Drug, Evidence, Candidate |
| Observability | Langfuse (optional v0) | Already familiar; nice-to-have for hobby scale |
| Aggregation | Weighted ensemble at v0; PyMC/NumPyro at v1 | Means-to-end first, sophistication later |
| LLM | Claude (via API or Bedrock) | Reasoning + evidence-trail generation |
| BioNeMo | Deferred to v1 | No Rett-relevant structural target at v0 |
| MCP servers | Deferred (interface-shaped) | Wrap as servers when external clients matter |
| Temporal | Deferred to v1+ | No long-running activities at v0 |

---

## 8. Phased Roadmap

The guiding principle: **ship one strategy end-to-end before building the second.** This is the difference between a hobby project that lives and one that dies in a half-built `strategies/` directory.

### Phase 1 — Target-based, end-to-end (~2–3 weekends)
- Open Targets GraphQL fetcher: Rett associations graph, MECP2 target context.
- ChEMBL fetcher: off-patent compounds (`max_phase >= 4`) hitting MECP2 pathway neighbors.
- DuckDB local store, schema + load scripts.
- Single LangGraph node implementing target-based ranking.
- FastAPI endpoint with SSE streaming.
- Next.js UI: ranked candidates with collapsible evidence chain per candidate ("drug X → hits target Y → Y is downstream of MECP2 via pathway Z").
- **Validation gate:** does trofinetide's IGF-1 axis surface in the top ranks?

### Phase 2 — Signature reversal
- LINCS L1000 fetcher (clue.io API or Touchstone signatures).
- Build Rett disease signature from Mecp2-null mouse brain RNA-seq (GEO).
- Reversal scoring (e.g., weighted connectivity score).
- Add as second LangGraph strategy node.

### Phase 3 — Network proximity
- STRING PPI network ingest.
- Closest-distance and Z-score normalization between drug-target set and Rett gene set.
- Add as third LangGraph strategy node.

### Phase 4 — Real synthesizer
- Rank-normalize each strategy's output.
- Weighted ensemble combining the three.
- Calibration check against oracle compounds.

### Phase 5+ (v1 and beyond)
- Hierarchical Bayesian aggregation (PyMC or NumPyro): treat each strategy as a "site" with bias and precision parameters; infer latent repurposing potential with calibrated uncertainty.
- Posterior-variance-driven active learning: agent picks the next candidate to investigate based on where uncertainty is highest, not just top-K.
- BioNeMo entry point: DiffDock NIM scoring of top candidates against specific downstream targets (TrkB, sigma-1).
- MCP server wrappers, enabling external Claude Desktop or Claude Code to drive experiments.
- Generalize to a second rare disease — discover what was disease-specific vs. reusable.
- Optional Temporal migration when long-running activities arrive.

---

## 9. Repository Layout

```
rett-repurposing/
├── README.md                    # validation story (trofinetide as oracle)
├── LICENSE                      # Apache-2.0
├── DATA_LICENSES.md             # per-source attribution table
├── pyproject.toml               # uv-managed
├── data/                        # gitignored
│   └── .gitkeep
├── notebooks/
│   └── journal/                 # dated learning-journal notebooks
├── scripts/
│   ├── fetch_opentargets.py
│   ├── fetch_chembl.py
│   ├── fetch_lincs.py           # phase 2
│   ├── fetch_string.py          # phase 3
│   └── build_local_store.py
├── src/rett_repurposing/
│   ├── models.py                # Pydantic: Disease, Target, Drug, Evidence, Candidate
│   ├── store/                   # DuckDB wrappers
│   ├── strategies/
│   │   ├── base.py              # Strategy ABC; signature matches future MCP tool shape
│   │   ├── target_based.py
│   │   ├── signature_reversal.py
│   │   └── network_proximity.py
│   ├── graph/
│   │   ├── nodes.py
│   │   ├── supervisor.py
│   │   └── synthesizer.py
│   ├── aggregation/             # v0 weighted; v1 hierarchical Bayes
│   ├── api/                     # FastAPI
│   └── ui_bridge/               # SSE streaming layer for Next.js
├── frontend/                    # Next.js + Vercel AI SDK
└── tests/
```

---

## 10. Validation Plan

The trofinetide oracle is the centerpiece of validation, but a small set of literature-supported repurposing classes for Rett gives a richer test bed:

- **IGF-1 axis** modulators (trofinetide territory)
- **BDNF / TrkB pathway** activators
- **NMDA receptor** modulators (ketamine and analogs have been studied)
- **Sigma-1 receptor** agonists
- **KCC2 enhancers** (chloride balance restoration)

**Top-K eyeball test.** For each candidate in the top 20, can the developer tell a mechanistic story about *why* the system surfaced it? If not, the system is a black box, not a learning tool — the evidence trail needs more work.

**Pathway plausibility report.** For each phase, generate a markdown report mapping ranked candidates to known Rett pathways. Diff between phases tells the story of what each new strategy added.

---

## 11. Learning Journal Structure

The pedagogical objective is non-negotiable: this project is a vehicle for learning rare-disease biology, not just a software exercise.

`notebooks/journal/` will contain dated Jupyter notebooks covering biology learned during each phase:

- **Phase 1:** MECP2 biology, X-linkage and mosaic expression, downstream pathway tour.
- **Phase 2:** Reading expression signatures, batch effects in GEO data, what an L1000 profile actually is.
- **Phase 3:** Network biology fundamentals, why proximity ≠ causation, PPI data quality caveats.
- **Phase 4:** Rank aggregation, bias/precision modeling, why uncertainty matters in candidate selection.
- **Phase 5+:** Specific disease pathway deep-dives as new diseases are added.

Over time these notebooks become a small textbook on neurodevelopmental rare-disease repurposing — written by working through it.

---

## 12. Licensing

**Code license:** Apache-2.0. Permissive, with an explicit patent grant clause useful for a project that touches drug-discovery methodology.

**Data attribution:** `DATA_LICENSES.md` enumerates each source, license, and required attribution language.

**Operational rules:**
- Never commit bulk raw data.
- Commit fetcher scripts, schemas, and derived analyses.
- DrugBank open subset (CC BY-NC) is fine for non-commercial use; flagged in README.
- ChEMBL CC BY-SA: derived works should preserve attribution.

---

## 13. Open Questions and Future Directions

**Hierarchical Bayesian aggregation (v1).** Each strategy produces rankings with its own bias, precision, and data coverage. A hierarchical model treating strategies as "sites" with their own bias/precision parameters and a latent "true repurposing potential" is the principled aggregator. Posterior variance becomes the active-learning signal.

**MCP server graduation (v1).** Wrap each strategy as an MCP server so an external Claude Desktop or Claude Code client can drive the system as a tool-using agent. The function signatures are already shaped for this.

**BioNeMo integration points (v1).** DiffDock NIM for protein-ligand docking against TrkB or sigma-1; ESM-2 for protein representations in network features; MolMIM if generative compound suggestions become interesting.

**Multi-disease generalization (v2).** Add a second rare disease (Friedreich's ataxia, Niemann-Pick C). Discover what was Rett-specific vs. reusable.

**Real digital-twin loop (v2+).** Once the decision loop is solid, *then* a thin lab-protocol abstraction layer becomes interesting: representing samples, plates, and assay readouts as state objects flowing through Temporal workflows. Built on a working repurposing system, not as the foundation for one.

---

## 14. Success Criteria

The project succeeds if, at the end of v0:

1. The top-20 ranked candidates for Rett include at least one compound from each of the validated oracle classes (IGF-1, BDNF, NMDA, sigma-1).
2. The developer can look at any top-20 candidate and explain its biological rationale in 2–3 sentences without consulting external sources.
3. The repository is public, the README tells the trofinetide validation story, and a stranger could clone and run the system end-to-end with a single command.
4. The learning journal has at least four dated notebooks of substantive biology writeup.

The project succeeds at v1 if the hierarchical Bayesian aggregator produces calibrated uncertainty estimates that meaningfully differentiate between top candidates, and if the system can be driven from an external Claude client via MCP.
