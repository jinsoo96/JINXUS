/**
 * SSE 파서 유틸 — 중복 제거 (Vercel AI SDK eventsource-parser 패턴 참고)
 *
 * api.ts의 streamMessage, streamAgentDirect, streamTaskProgress에서
 * 동일한 SSE 파싱 로직이 3곳에 중복되어 있었음 → 단일 유틸로 추출
 */

export type SSECallback = (event: string, data: unknown) => void;

/**
 * ReadableStream 기반 SSE 소비
 *
 * fetch 응답의 body를 읽으며 SSE event/data를 파싱하고 콜백으로 전달.
 * 배열 축적 + join() 패턴으로 O(n) 파싱 보장.
 */
export async function consumeSSE(
  response: Response,
  onEvent: SSECallback,
  signal?: AbortSignal,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';
  let dataChunks: string[] = [];

  const flush = () => {
    if (dataChunks.length > 0) {
      try {
        const data = JSON.parse(dataChunks.join(''));
        onEvent(currentEvent, data);
      } catch { /* JSON 파싱 실패 무시 */ }
    }
    currentEvent = 'message';
    dataChunks = [];
  };

  try {
    while (true) {
      if (signal?.aborted) { reader.cancel(); break; }
      const { done, value } = await reader.read();
      if (done) { flush(); break; }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.trim() === '') flush();
        else if (line.startsWith('event:')) currentEvent = line.slice(6).trim();
        else if (line.startsWith('data:')) dataChunks.push(line.slice(5).trim());
      }
    }
  } finally {
    reader.releaseLock();
  }
}
