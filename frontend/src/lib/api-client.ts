import type { Candidate } from "@/lib/types";
import { parseSseStream, type SseEvent } from "@/lib/sse";

export type StatusPayload = {
  phase: string;
  message: string;
  [key: string]: unknown;
};

export type CompletePayload = {
  total: number;
  strategies_run: string[];
};

export type ErrorPayload = {
  message: string;
  phase: string;
};

export type RepurposeStreamHandlers = {
  onStatus?: (payload: StatusPayload) => void;
  onCandidate?: (candidate: Candidate) => void;
  onComplete?: (payload: CompletePayload) => void;
  onError?: (payload: ErrorPayload) => void;
};

export async function streamRepurpose(
  disease: string,
  handlers: RepurposeStreamHandlers,
  options?: { signal?: AbortSignal; strategies?: string[] },
): Promise<void> {
  const body: Record<string, unknown> = { disease };
  if (options?.strategies && options.strategies.length > 0) {
    body.enabled_strategies = options.strategies;
  }
  const response = await fetch("/api/repurpose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options?.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backend ${response.status}: ${text || response.statusText}`);
  }
  if (!response.body) {
    throw new Error("Response body is empty — cannot stream.");
  }

  for await (const event of parseSseStream(response.body)) {
    dispatch(event, handlers);
  }
}

function dispatch(event: SseEvent, handlers: RepurposeStreamHandlers): void {
  switch (event.event) {
    case "status":
      handlers.onStatus?.(JSON.parse(event.data) as StatusPayload);
      return;
    case "candidate":
      handlers.onCandidate?.(JSON.parse(event.data) as Candidate);
      return;
    case "complete":
      handlers.onComplete?.(JSON.parse(event.data) as CompletePayload);
      return;
    case "error":
      handlers.onError?.(JSON.parse(event.data) as ErrorPayload);
      return;
    default:
      // Unknown event — ignore (forwards-compat for future event types).
      return;
  }
}
