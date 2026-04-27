"use client";

import { useState } from "react";
import { AlertCircle, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CandidateCard } from "@/components/candidate-card";
import { StatusBanner } from "@/components/status-banner";
import {
  streamRepurpose,
  type StatusPayload,
  type CompletePayload,
} from "@/lib/api-client";
import type { Candidate } from "@/lib/types";

export default function Home() {
  const [disease, setDisease] = useState("Rett syndrome");
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [completion, setCompletion] = useState<CompletePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (running) return;

    setRunning(true);
    setPhase(null);
    setStatusMessage(null);
    setCandidates([]);
    setCompletion(null);
    setError(null);

    try {
      await streamRepurpose(disease, {
        onStatus: (payload: StatusPayload) => {
          setPhase(payload.phase);
          setStatusMessage(payload.message);
        },
        onCandidate: (c: Candidate) => {
          setCandidates((prev) => [...prev, c]);
        },
        onComplete: (payload: CompletePayload) => {
          setCompletion(payload);
        },
        onError: (payload) => {
          setError(`${payload.phase}: ${payload.message}`);
        },
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="container max-w-3xl py-10 space-y-6">
      <header className="space-y-2">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Rett Drug Repurposing</h1>
          <a
            href="https://github.com/"
            target="_blank"
            rel="noreferrer"
            className="text-muted-foreground hover:text-foreground"
            aria-label="GitHub repository"
          >
            <Github className="h-5 w-5" />
          </a>
        </div>
        <p className="text-sm text-muted-foreground max-w-prose">
          Phase 1 — target-based repurposing for Rett syndrome via Open Targets +
          ChEMBL. Approved compounds are scored by combining disease–target
          association strength and the breadth of mechanism evidence.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={disease}
          onChange={(e) => setDisease(e.target.value)}
          placeholder="Disease (e.g. Rett syndrome)"
          aria-label="Disease"
          disabled={running}
        />
        <Button type="submit" disabled={running || disease.trim().length === 0}>
          {running ? "Running…" : "Run analysis"}
        </Button>
      </form>

      <StatusBanner
        currentPhase={phase}
        message={statusMessage}
        done={completion !== null}
      />

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 flex gap-2 text-sm">
          <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
          <span className="text-destructive">{error}</span>
        </div>
      )}

      {candidates.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">
              {candidates.length} candidate{candidates.length === 1 ? "" : "s"}
              {completion && ` · strategy: ${completion.strategies_run.join(", ")}`}
            </h2>
          </div>
          <ul className="space-y-3">
            {candidates.map((c, i) => (
              <li key={`${c.drug.chembl_id}:${c.target.ensembl_id}`}>
                <CandidateCard candidate={c} rank={i + 1} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
