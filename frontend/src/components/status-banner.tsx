import { CheckCircle2, Circle, Loader2 } from "lucide-react";

const PHASE_ORDER = ["resolving_disease", "disease_resolved", "running_strategy"] as const;
type Phase = (typeof PHASE_ORDER)[number];
const PHASE_LABELS: Record<string, string> = {
  resolving_disease: "Resolving disease",
  disease_resolved: "Disease resolved",
  running_strategy: "Running strategies",
};

export function StatusBanner({
  currentPhase,
  message,
  done,
}: {
  currentPhase: string | null;
  message: string | null;
  done: boolean;
}) {
  if (currentPhase === null && !done) return null;

  return (
    <div className="rounded-md border bg-muted/30 px-4 py-3 flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        {PHASE_ORDER.map((phase) => (
          <PhaseChip
            key={phase}
            phase={phase}
            currentPhase={currentPhase}
            done={done}
          />
        ))}
      </div>
      {message && <p className="text-xs text-muted-foreground">{message}</p>}
    </div>
  );
}

function PhaseChip({
  phase,
  currentPhase,
  done,
}: {
  phase: Phase;
  currentPhase: string | null;
  done: boolean;
}) {
  const currentIdx = currentPhase ? PHASE_ORDER.indexOf(currentPhase as Phase) : -1;
  const myIdx = PHASE_ORDER.indexOf(phase);
  const isDone = done || currentIdx > myIdx;
  const isActive = !done && currentIdx === myIdx;

  return (
    <div
      className={
        "flex items-center gap-1.5 " +
        (isDone
          ? "text-foreground"
          : isActive
            ? "text-foreground"
            : "text-muted-foreground/60")
      }
    >
      {isDone ? (
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      ) : isActive ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Circle className="h-4 w-4" />
      )}
      <span className="text-xs font-medium">{PHASE_LABELS[phase] ?? phase}</span>
    </div>
  );
}
