"""Signature construction: counts parsing, sample selection, DE, orthology."""

from __future__ import annotations

from pathlib import Path

import pytest

from rett_repurposing.exceptions import GEOError
from rett_repurposing.signature import (
    compute_disease_signature,
    map_signature_to_human,
    parse_counts_matrix,
)
from rett_repurposing.signature.differential_expression import _select_groups

FIXTURES = Path(__file__).parent / "fixtures"
COUNTS_MINI = (FIXTURES / "geo" / "counts_mini.tsv").read_text()


def test_parse_counts_matrix_shape():
    matrix = parse_counts_matrix(COUNTS_MINI)
    # 8 samples, 5 gene rows.
    assert len(matrix.sample_ids) == 8
    assert matrix.counts.shape == (5, 8)
    assert "Mecp2" in matrix.gene_symbols
    assert matrix.sample_meta["Brain Area"][6] == "Hippocampus"


def test_parse_rejects_matrix_without_gene_header():
    with pytest.raises(GEOError):
        parse_counts_matrix("just\tsome\tnoise\n1\t2\t3\n")


def test_select_groups_excludes_wrong_area_and_treated():
    matrix = parse_counts_matrix(COUNTS_MINI)
    ko, wt = _select_groups(matrix)
    # KO = S1,S2,S3 (cortex, untreated); hippocampus (S7) and rtt271 (S8) excluded.
    assert ko == [0, 1, 2]
    assert wt == [3, 4, 5]


def test_disease_signature_direction_is_correct():
    matrix = parse_counts_matrix(COUNTS_MINI)
    signature = compute_disease_signature(matrix, top_n=10)
    assert signature.n_ko == 3
    assert signature.n_wt == 3
    # Mecp2 and Bdnf are engineered down in KO; Irak1 up.
    assert "Mecp2" in signature.down_genes
    assert "Bdnf" in signature.down_genes
    assert "Irak1" in signature.up_genes
    # Stable / near-silent genes should not dominate the top sets.
    assert "Gm12345" not in signature.up_genes
    assert "Gm12345" not in signature.down_genes


def test_disease_signature_requires_minimum_samples():
    # A matrix with only one KO sample should fail the DE guard.
    single_ko = COUNTS_MINI.replace(
        "MeCP2: -/Y\tMeCP2: -/Y\tMeCP2: -/Y", "MeCP2: -/Y\tMeCP2: +/Y\tMeCP2: +/Y"
    )
    matrix = parse_counts_matrix(single_ko)
    with pytest.raises(GEOError):
        compute_disease_signature(matrix, top_n=10)


def test_orthology_maps_and_dedupes():
    ortholog_map = {"Bdnf": "BDNF", "Mecp2": "MECP2"}
    # Irak1 has no explicit entry but IRAK1 is a known human symbol via identity.
    ortholog_map["Irak1"] = "IRAK1"
    mapped = map_signature_to_human(["Bdnf", "Mecp2", "Bdnf", "Unknownxyz"], ortholog_map)
    assert mapped == ["BDNF", "MECP2"]


def test_orthology_identity_fallback():
    ortholog_map = {"Foo": "IRAK1"}  # IRAK1 present as a value
    # "Irak1" not a key, but "IRAK1" is a known human symbol -> identity fallback.
    assert map_signature_to_human(["Irak1"], ortholog_map) == ["IRAK1"]


def test_real_ortholog_table_covers_rett_genes():
    from rett_repurposing.signature.orthology import load_ortholog_map

    ortholog_map = load_ortholog_map()
    for mouse, human in [("Bdnf", "BDNF"), ("Mecp2", "MECP2"), ("Igf1", "IGF1")]:
        assert ortholog_map.get(mouse) == human
