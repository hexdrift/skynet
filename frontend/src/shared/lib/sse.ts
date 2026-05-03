export interface ServerSentEvent {
  event: string;
  data: Record<string, unknown>;
}

function normalizeStreamChunk(chunk: string): string {
  return chunk.replace(/\r\n/g, "\n");
}

function dispatchNdjsonLine(raw: string, dispatch: (line: string) => void) {
  const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
  dispatch(line);
}

function parseServerSentEvent(raw: string): ServerSentEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of normalizeStreamChunk(raw).split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

export async function readServerSentEvents(
  body: ReadableStream<Uint8Array>,
  processEvent: (event: ServerSentEvent) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      buf += decoder.decode();
      if (buf.trim()) {
        const event = parseServerSentEvent(buf);
        if (event) processEvent(event);
      }
      break;
    }
    buf += normalizeStreamChunk(decoder.decode(value, { stream: true }));
    let sepIdx: number;
    while ((sepIdx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, sepIdx);
      buf = buf.slice(sepIdx + 2);
      const event = parseServerSentEvent(raw);
      if (event) processEvent(event);
    }
  }
}

export async function readNdjsonStream(
  body: ReadableStream<Uint8Array>,
  dispatch: (line: string) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      buf += decoder.decode();
      if (buf.length) dispatch(buf);
      break;
    }
    buf += normalizeStreamChunk(decoder.decode(value, { stream: true }));
    let newlineIdx: number;
    while ((newlineIdx = buf.indexOf("\n")) !== -1) {
      const raw = buf.slice(0, newlineIdx);
      buf = buf.slice(newlineIdx + 1);
      dispatchNdjsonLine(raw, dispatch);
    }
  }
}
