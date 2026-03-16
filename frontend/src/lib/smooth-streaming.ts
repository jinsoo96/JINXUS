/**
 * 타이핑 애니메이션 큐 — NextChat remainText 패턴
 *
 * SSE 청크가 버스트로 들어와도 requestAnimationFrame으로
 * 60fps에 맞춰 조금씩 꺼내 렌더링 → 매끄러운 타이핑 효과
 *
 * 참고: https://github.com/ChatGPTNextWeb/NextChat
 */

export function createSmoothStreamer(onUpdate: (text: string) => void) {
  let remainText = '';
  let outputText = '';
  let rafId: number | null = null;

  /** 청크 추가 (SSE onEvent에서 호출) */
  function push(chunk: string) {
    remainText += chunk;
    if (!rafId) scheduleFrame();
  }

  function scheduleFrame() {
    rafId = requestAnimationFrame(() => {
      if (remainText.length === 0) { rafId = null; return; }
      // 큐 깊이에 비례하여 꺼내는 양 조절 (최소 1글자, 최대 큐/30)
      const count = Math.max(1, Math.round(remainText.length / 30));
      const slice = remainText.slice(0, count);
      remainText = remainText.slice(count);
      outputText += slice;
      onUpdate(outputText);
      if (remainText.length > 0) scheduleFrame();
      else rafId = null;
    });
  }

  /** 잔여 텍스트 즉시 출력 (done 이벤트 시 호출) */
  function flush() {
    if (rafId) cancelAnimationFrame(rafId);
    outputText += remainText;
    remainText = '';
    rafId = null;
    onUpdate(outputText);
  }

  /** 전체 텍스트 반환 (flush 없이) */
  function getText() {
    return outputText + remainText;
  }

  /** 초기화 */
  function reset() {
    if (rafId) cancelAnimationFrame(rafId);
    remainText = '';
    outputText = '';
    rafId = null;
  }

  return { push, flush, getText, reset };
}
