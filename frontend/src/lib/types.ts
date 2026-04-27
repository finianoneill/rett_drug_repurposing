// Hand-written mirror of `src/rett_repurposing/models.py`. See §7.

export interface Disease {
  efo_id: string;
  name: string;
}

export interface Target {
  ensembl_id: string;
  symbol: string | null;
  name: string | null;
  biotype: string | null;
  overall_association_score: number | null;
  datatype_scores: Record<string, number>;
}

export interface Drug {
  chembl_id: string;
  name: string;
  drug_type: string | null;
  max_phase: number | null;
  is_approved: boolean;
  first_approval_year: number | null;
  withdrawn: boolean;
  trade_names: string[];
  synonyms: string[];
  canonical_smiles: string | null;
  atc_classifications: string[];
}

export interface EvidenceLink {
  kind: string;
  description: string;
  metadata: Record<string, string | number>;
}

export interface Candidate {
  drug: Drug;
  target: Target;
  score: number;
  score_components: Record<string, number>;
  evidence: EvidenceLink[];
  strategy: string;
}

export interface CandidateList {
  disease: Disease;
  candidates: Candidate[];
  strategy: string;
  generated_at: string;
}
