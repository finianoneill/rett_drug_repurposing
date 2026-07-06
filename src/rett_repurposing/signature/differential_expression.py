"""Differential expression → up/down gene signature.

The default input is the ``GSE300534`` counts matrix (Mecp2-null mouse cortex),
whose header carries per-sample metadata. Sample selection isolates a clean
knockout-vs-wild-type contrast (Cortex, untreated/PBS controls — excluding the
AAV gene-therapy and Tau-overexpression arms), then a CPM + log2 transform and a
Welch t-statistic rank genes by dysregulation.

This is deliberately light (limma-style, not a negative-binomial model): the
downstream SigCom LINCS query only needs the *sets* of top up/down genes.

# TODO(phase-5): swap the Welch t-statistic for pydeseq2 (negative-binomial DE)
# once the pipeline graduates from a hobby-scale signature.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog
from numpy.typing import NDArray

from rett_repurposing.exceptions import GEOError

log = structlog.get_logger(__name__)

# --- GSE300534 sample-selection constants (see phase-2 data notes) -----------
GENE_HEADER_LABEL = "Ensembl ID"
META_BRAIN_AREA = "Brain Area"
META_GENOTYPE = "Genotype"
META_INJECTION = "Injection Status"

BRAIN_AREA = "Cortex"
KO_GENOTYPE_TOKEN = "-/Y"  # MeCP2: -/Y  (hemizygous null)
WT_GENOTYPE_TOKEN = "+/Y"  # MeCP2: +/Y  (wild-type)
GENOTYPE_PREFIX = "MeCP2"  # excludes the Tau-overexpression arms
EXCLUDE_INJECTION_TOKEN = "rtt271"  # excludes AAV gene-therapy samples

# Drop genes expressed below this mean log2-CPM across kept samples.
MIN_MEAN_LOG_CPM = 1.0
DEFAULT_TOP_N = 150


@dataclass(frozen=True)
class CountsMatrix:
    """A parsed genes-by-samples counts matrix with per-sample metadata."""

    gene_symbols: list[str]
    sample_ids: list[str]
    sample_meta: dict[str, list[str]]  # metadata label -> value per sample
    counts: NDArray[np.float64]  # shape (n_genes, n_samples)


@dataclass(frozen=True)
class DiseaseSignature:
    """Top up/down genes (disease-relative) with their per-gene statistics."""

    up_genes: list[str]  # up in disease (KO) — a reverser pushes these down
    down_genes: list[str]  # down in disease (KO) — a reverser pushes these up
    stats: dict[str, dict[str, float]]  # gene -> {log2fc, t, mean_ko, mean_wt}
    n_ko: int
    n_wt: int


def parse_counts_matrix(tsv_text: str) -> CountsMatrix:
    """Parse a GEO counts matrix with a metadata header block.

    Metadata rows precede a row whose first cell is ``Ensembl ID``; each
    metadata row is ``["", label, val_sample_1, ...]`` and each gene row is
    ``[ensembl_id, symbol, count_1, ...]``.
    """
    rows = [line.split("\t") for line in tsv_text.splitlines() if line.strip()]
    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0].strip() == GENE_HEADER_LABEL),
        None,
    )
    if header_idx is None:
        raise GEOError(f"counts matrix has no '{GENE_HEADER_LABEL}' gene-header row")

    meta_rows = rows[:header_idx]
    gene_rows = rows[header_idx + 1 :]
    if not gene_rows:
        raise GEOError("counts matrix has no gene rows")

    n_samples = len(gene_rows[0]) - 2
    if n_samples <= 0:
        raise GEOError("counts matrix has no sample columns")

    sample_meta: dict[str, list[str]] = {}
    for r in meta_rows:
        label = r[1].strip() if len(r) > 1 else ""
        if label:
            sample_meta[label] = [c.strip() for c in r[2 : 2 + n_samples]]

    # Sample ids: prefer the first metadata row's values (the Admera IDs).
    sample_ids = next(iter(sample_meta.values()), [f"s{i}" for i in range(n_samples)])

    gene_symbols: list[str] = []
    count_rows: list[list[float]] = []
    for r in gene_rows:
        if len(r) < 2 + n_samples:
            continue
        symbol = r[1].strip()
        if not symbol:
            continue
        try:
            values = [float(c) for c in r[2 : 2 + n_samples]]
        except ValueError:
            continue
        gene_symbols.append(symbol)
        count_rows.append(values)

    if not count_rows:
        raise GEOError("counts matrix parsed to zero usable gene rows")

    counts = np.asarray(count_rows, dtype=np.float64)
    log.info(
        "signature.counts_parsed",
        n_genes=len(gene_symbols),
        n_samples=n_samples,
        metadata_labels=sorted(sample_meta.keys()),
    )
    return CountsMatrix(
        gene_symbols=gene_symbols,
        sample_ids=list(sample_ids),
        sample_meta=sample_meta,
        counts=counts,
    )


def _select_groups(matrix: CountsMatrix) -> tuple[list[int], list[int]]:
    """Return (ko_column_indices, wt_column_indices) per the selection rules."""
    area = matrix.sample_meta.get(META_BRAIN_AREA, [])
    geno = matrix.sample_meta.get(META_GENOTYPE, [])
    inj = matrix.sample_meta.get(META_INJECTION, [])
    if not (area and geno):
        raise GEOError(f"counts matrix missing '{META_BRAIN_AREA}'/'{META_GENOTYPE}' metadata rows")

    ko: list[int] = []
    wt: list[int] = []
    n = len(matrix.sample_ids)
    for i in range(n):
        a = area[i] if i < len(area) else ""
        g = geno[i] if i < len(geno) else ""
        j = inj[i] if i < len(inj) else ""
        if a != BRAIN_AREA or GENOTYPE_PREFIX not in g:
            continue
        if EXCLUDE_INJECTION_TOKEN in j.lower():
            continue
        if KO_GENOTYPE_TOKEN in g:
            ko.append(i)
        elif WT_GENOTYPE_TOKEN in g:
            wt.append(i)
    return ko, wt


def compute_disease_signature(
    matrix: CountsMatrix,
    *,
    top_n: int = DEFAULT_TOP_N,
) -> DiseaseSignature:
    """Rank genes by KO-vs-WT dysregulation and return the top up/down sets."""
    ko_idx, wt_idx = _select_groups(matrix)
    if len(ko_idx) < 2 or len(wt_idx) < 2:
        raise GEOError(
            f"insufficient samples for DE: {len(ko_idx)} KO, {len(wt_idx)} WT (need >=2 each)"
        )

    # CPM + log2 normalisation (library-size correction, then variance-stabilise).
    lib_size = matrix.counts.sum(axis=0)
    lib_size[lib_size == 0] = 1.0
    cpm = matrix.counts / lib_size * 1e6
    logcpm = np.log2(cpm + 1.0)

    ko = logcpm[:, ko_idx]
    wt = logcpm[:, wt_idx]
    mean_ko = ko.mean(axis=1)
    mean_wt = wt.mean(axis=1)
    log2fc = mean_ko - mean_wt

    # Welch t-statistic with a small variance floor to avoid divide-by-zero.
    var_ko = ko.var(axis=1, ddof=1)
    var_wt = wt.var(axis=1, ddof=1)
    se = np.sqrt(var_ko / len(ko_idx) + var_wt / len(wt_idx))
    se = np.maximum(se, 1e-8)
    tstat = log2fc / se

    # Expression filter: ignore genes that are near-silent in both groups.
    expressed = (0.5 * (mean_ko + mean_wt)) >= MIN_MEAN_LOG_CPM

    order = np.argsort(tstat)  # ascending: most-down first, most-up last
    up_idx = [int(i) for i in order[::-1] if expressed[i] and log2fc[i] > 0][:top_n]
    down_idx = [int(i) for i in order if expressed[i] and log2fc[i] < 0][:top_n]

    def _stat(i: int) -> dict[str, float]:
        return {
            "log2fc": round(float(log2fc[i]), 4),
            "t": round(float(tstat[i]), 4),
            "mean_ko": round(float(mean_ko[i]), 4),
            "mean_wt": round(float(mean_wt[i]), 4),
        }

    up_genes = [matrix.gene_symbols[i] for i in up_idx]
    down_genes = [matrix.gene_symbols[i] for i in down_idx]
    stats = {matrix.gene_symbols[i]: _stat(i) for i in (*up_idx, *down_idx)}

    log.info(
        "signature.computed",
        n_ko=len(ko_idx),
        n_wt=len(wt_idx),
        n_up=len(up_genes),
        n_down=len(down_genes),
        top_up=up_genes[:5],
        top_down=down_genes[:5],
    )
    return DiseaseSignature(
        up_genes=up_genes,
        down_genes=down_genes,
        stats=stats,
        n_ko=len(ko_idx),
        n_wt=len(wt_idx),
    )
