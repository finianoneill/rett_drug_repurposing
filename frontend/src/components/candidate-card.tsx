"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EvidenceTrail } from "@/components/evidence-trail";
import type { Candidate } from "@/lib/types";

export function CandidateCard({ candidate, rank }: { candidate: Candidate; rank: number }) {
  const { drug, target, score, score_components } = candidate;
  const defaultOpen = rank <= 3;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-baseline gap-3 min-w-0">
            <span className="text-sm font-mono text-muted-foreground tabular-nums w-6 shrink-0">
              {rank}
            </span>
            <div className="min-w-0">
              <h3 className="text-base font-semibold truncate">{drug.name}</h3>
              {drug.trade_names.length > 0 && (
                <p className="text-xs text-muted-foreground truncate">
                  {drug.trade_names.join(", ")}
                </p>
              )}
            </div>
          </div>
          <ScoreBadge score={score} components={score_components} />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">target</span>
          <Badge variant="outline" className="font-mono">
            {target.symbol ?? target.ensembl_id}
          </Badge>
          {target.overall_association_score != null && (
            <span className="text-xs text-muted-foreground">
              assoc {target.overall_association_score.toFixed(2)}
            </span>
          )}
          {drug.first_approval_year && (
            <span className="text-xs text-muted-foreground ml-auto">
              approved {drug.first_approval_year}
            </span>
          )}
        </div>
        <EvidenceTrail evidence={candidate.evidence} defaultOpen={defaultOpen} />
      </CardContent>
    </Card>
  );
}

function ScoreBadge({
  score,
  components,
}: {
  score: number;
  components: Record<string, number>;
}) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="shrink-0 cursor-help">
            <Badge variant="default" className="font-mono tabular-nums">
              {score.toFixed(3)}
            </Badge>
          </div>
        </TooltipTrigger>
        <TooltipContent side="left" className="max-w-xs">
          <div className="space-y-1">
            <div className="font-semibold">Score breakdown</div>
            {Object.entries(components).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 font-mono text-[11px]">
                <span className="text-muted-foreground">{key}</span>
                <span>{value.toFixed(3)}</span>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
