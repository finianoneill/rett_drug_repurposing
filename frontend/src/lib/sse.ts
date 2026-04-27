// Minimal SSE stream parser. The backend uses the standard text/event-stream
// format with `event:` and `data:` lines per event, separated by blank lines.
// We don't pull in the Vercel AI SDK's parseDataStream because that targets
// the AI SDK's specific stream protocol, not generic SSE.

export type SseEvent = { event: string; data: string };

export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent: string | null = null;
  let currentData: string | null = null;

  const flush = (): SseEvent | null => {
    if (currentEvent !== null && currentData !== null) {
      const event: SseEvent = { event: currentEvent, data: currentData };
      currentEvent = null;
      currentData = null;
      return event;
    }
    currentEvent = null;
    currentData = null;
    return null;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIdx: number;
    while ((newlineIdx = buffer.indexOf("\n")) >= 0) {
      const rawLine = buffer.slice(0, newlineIdx);
      buffer = buffer.slice(newlineIdx + 1);
      // Strip trailing CR for CRLF servers
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;

      if (line === "") {
        const event = flush();
        if (event) yield event;
        continue;
      }
      if (line.startsWith(":")) {
        // Comment / heartbeat — ignore
        continue;
      }
      if (line.startsWith("event:")) {
        currentEvent = line.slice("event:".length).trimStart();
      } else if (line.startsWith("data:")) {
        const datum = line.slice("data:".length).trimStart();
        currentData = currentData === null ? datum : `${currentData}\n${datum}`;
      }
    }
  }

  const trailing = flush();
  if (trailing) yield trailing;
}
