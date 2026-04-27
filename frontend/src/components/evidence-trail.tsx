"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import type { EvidenceLink } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  target_associated_with_disease: "Target ↔ Disease",
  drug_targets: "Drug ↔ Target",
  pathway_context: "Pathway",
  alternative_targets: "Alternative targets",
};

const KIND_VARIANTS: Record<string, "default" | "secondary" | "outline"> = {
  target_associated_with_disease: "secondary",
  drug_targets: "secondary",
  pathway_context: "default",
  alternative_targets: "outline",
};

export function EvidenceTrail({
  evidence,
  defaultOpen,
}: {
  evidence: EvidenceLink[];
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (evidence.length === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-2">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        {open ? "Hide evidence" : `Show evidence (${evidence.length})`}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2">
        {evidence.map((link, i) => (
          <div key={i} className="flex gap-2 items-start text-sm">
            <Badge
              variant={KIND_VARIANTS[link.kind] ?? "outline"}
              className="shrink-0 mt-0.5"
            >
              {KIND_LABELS[link.kind] ?? link.kind}
            </Badge>
            <span className="text-foreground/80 leading-snug">{link.description}</span>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
