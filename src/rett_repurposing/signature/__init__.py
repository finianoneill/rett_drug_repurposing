"""Rett disease-signature construction — Phase 2.

Parses a GEO counts matrix, runs a light differential-expression pass
(Mecp2-null vs wild-type cortex), and maps the top dysregulated mouse genes to
human orthologs. The resulting up/down human gene signature is the query fed to
SigCom LINCS to find reversing perturbagens.
"""

from __future__ import annotations

from rett_repurposing.signature.differential_expression import (
    CountsMatrix,
    DiseaseSignature,
    compute_disease_signature,
    parse_counts_matrix,
)
from rett_repurposing.signature.orthology import (
    load_ortholog_map,
    map_signature_to_human,
)

__all__ = [
    "CountsMatrix",
    "DiseaseSignature",
    "compute_disease_signature",
    "load_ortholog_map",
    "map_signature_to_human",
    "parse_counts_matrix",
]
