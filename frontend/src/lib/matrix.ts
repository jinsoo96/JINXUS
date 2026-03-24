/**
 * Matrix Client-Server API — 경량 클라이언트 (matrix-js-sdk 의존성 없음)
 *
 * JINXUS 팀채팅에서 Synapse 홈서버와 직접 통신한다.
 * 에이전트들은 AS 토큰으로 가상 계정을 통해 메시지를 보내고,
 * 진수는 @jinsu 계정으로 Matrix 룸에 메시지를 보낸다.
 */

import { PERSONA_MAP } from './personas';

// 홈서버 URL — Next.js rewrite 프록시 경유 (브라우저→Next.js→Synapse)
// /_matrix/:path* → http://localhost:8008/_matrix/:path* (next.config.js에서 설정)
export function getMatrixHS(): string {
  // 서버사이드에서는 직접 연결, 클라이언트에서는 상대경로로 프록시 경유
  if (typeof window === 'undefined') return 'http://localhost:8008';
  return '';
}

// Matrix 서버 이름 (room alias suffix) — Synapse homeserver.yaml의 server_name
// 프록시 경유하더라도 room alias/user ID에는 Synapse가 인식하는 server_name 사용
const MATRIX_SERVER_NAME = process.env.NEXT_PUBLIC_MATRIX_SERVER_NAME || '100.75.83.105';
export function getMatrixServerName(): string {
  return MATRIX_SERVER_NAME;
}

// JINXUS 채널 → Matrix 룸 별칭 localpart 매핑
export const CHANNEL_TO_ALIAS_LOCALPART: Record<string, string> = {
  general:      'jinxus-general',
  dev:          'jinxus-dev',
  platform:     'jinxus-platform',
  product:      'jinxus-product',
  marketing:    'jinxus-marketing',
  'biz-support': 'jinxus-biz-support',
};

// Matrix localpart → 한국 이름 (PERSONA_MAP에서 자동 파생)
const LOCALPART_TO_FIRSTNAME: Record<string, string> = {
  // 에이전트 (코드→소문자 변환, JINXUS_CORE 예외) — 성+이름 표시
  ...Object.fromEntries(
    Object.entries(PERSONA_MAP).map(([code, p]) => {
      const localpart = code === 'JINXUS_CORE' ? 'jinxus_bot' : code.toLowerCase();
      return [localpart, p.name];  // name = 성+이름 (이채영), firstName = 이름만 (채영)
    })
  ),
  jinsu: '진수',  // 실제 사용자
};

// Matrix localpart → 직무 (PERSONA_MAP에서 자동 파생)
const LOCALPART_TO_ROLE: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(PERSONA_MAP).map(([code, p]) => {
      const localpart = code === 'JINXUS_CORE' ? 'jinxus_bot' : code.toLowerCase();
      return [localpart, p.role];
    })
  ),
};

// Matrix localpart → 이모지 (PERSONA_MAP에서 자동 파생)
const LOCALPART_TO_EMOJI: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(PERSONA_MAP).map(([code, p]) => {
      const localpart = code === 'JINXUS_CORE' ? 'jinxus_bot' : code.toLowerCase();
      return [localpart, p.emoji];
    })
  ),
  jinsu: '👤',
};

/** Matrix sender 주소 → 표시 이름 (이름 + 직무) */
export function senderToName(sender: string): string {
  // "@jx_coder:100.75.83.105" → "jx_coder"
  const localpart = sender.split(':')[0].replace('@', '');
  const name = LOCALPART_TO_FIRSTNAME[localpart] ?? localpart;
  // 진수 → CEO, 에이전트 → 직무 표시
  if (localpart === 'jinsu') return '진수 (CEO)';
  // localpart → 에이전트 코드 역매핑
  const role = LOCALPART_TO_ROLE[localpart];
  return role ? `${name} (${role})` : name;
}

/** Matrix sender 주소 → 이모지 */
export function senderToEmoji(sender: string): string {
  const localpart = sender.split(':')[0].replace('@', '');
  return LOCALPART_TO_EMOJI[localpart] ?? '🤖';
}

/** sender가 진수(실제 사용자)인지 */
export function isUserSender(sender: string): boolean {
  const localpart = sender.split(':')[0].replace('@', '');
  return localpart === 'jinsu';
}

// ── Matrix 인증 ────────────────────────────────────────────────

const LS_TOKEN_KEY = 'matrix_access_token';
const LS_DEVICE_KEY = 'matrix_device_id';

export interface MatrixSession {
  accessToken: string;
  userId: string;
  deviceId: string;
}

/** fetch with timeout helper */
function fetchWithTimeout(url: string, opts: RequestInit & { timeoutMs?: number } = {}): Promise<Response> {
  const { timeoutMs = 8000, ...fetchOpts } = opts;
  const controller = new AbortController();
  // 기존 signal이 있으면 abort 전파
  if (fetchOpts.signal) {
    fetchOpts.signal.addEventListener('abort', () => controller.abort());
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...fetchOpts, signal: controller.signal })
    .finally(() => clearTimeout(timer));
}

/** 저장된 세션 로드 (없으면 null) */
export function loadSession(): MatrixSession | null {
  if (typeof window === 'undefined') return null;
  const token = localStorage.getItem(LS_TOKEN_KEY);
  const deviceId = localStorage.getItem(LS_DEVICE_KEY);
  if (!token) return null;
  const serverName = getMatrixServerName();
  return { accessToken: token, userId: `@jinsu:${serverName}`, deviceId: deviceId ?? '' };
}

/** 로그인 후 세션 저장 */
export async function matrixLogin(username: string, password: string): Promise<MatrixSession> {
  const hs = getMatrixHS();
  const resp = await fetchWithTimeout(`${hs}/_matrix/client/v3/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'm.login.password',
      identifier: { type: 'm.id.user', user: username },
      password,
    }),
    timeoutMs: 8000,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Matrix 로그인 실패: ${resp.status} ${text}`);
  }
  const data = await resp.json();
  const session: MatrixSession = {
    accessToken: data.access_token,
    userId: data.user_id,
    deviceId: data.device_id ?? '',
  };
  localStorage.setItem(LS_TOKEN_KEY, session.accessToken);
  localStorage.setItem(LS_DEVICE_KEY, session.deviceId);
  return session;
}

/** 저장된 토큰 제거 */
export function clearSession(): void {
  localStorage.removeItem(LS_TOKEN_KEY);
  localStorage.removeItem(LS_DEVICE_KEY);
}

// ── 룸 조회 ────────────────────────────────────────────────────

/** 룸 별칭 → 룸 ID 조회 (없으면 null) */
export async function resolveRoomAlias(
  token: string,
  alias: string,          // 예: "#jinxus-general:100.75.83.105"
): Promise<string | null> {
  const hs = getMatrixHS();
  const encoded = encodeURIComponent(alias);
  try {
    const resp = await fetchWithTimeout(`${hs}/_matrix/client/v3/directory/room/${encoded}`, {
      headers: { Authorization: `Bearer ${token}` },
      timeoutMs: 5000,
    });
    if (resp.status === 200) {
      const data = await resp.json();
      return data.room_id ?? null;
    }
  } catch { /* 네트워크 오류 / 타임아웃 */ }
  return null;
}

/** 모든 JINXUS 채널 룸 ID를 한번에 조회
 *  반환: { channel: roomId, ... } */
export async function resolveAllChannelRooms(token: string): Promise<Record<string, string>> {
  const serverName = getMatrixServerName();
  const channelToRoom: Record<string, string> = {};
  await Promise.all(
    Object.entries(CHANNEL_TO_ALIAS_LOCALPART).map(async ([channel, aliasLocal]) => {
      const alias = `#${aliasLocal}:${serverName}`;
      const roomId = await resolveRoomAlias(token, alias);
      if (roomId) channelToRoom[channel] = roomId;
    })
  );
  return channelToRoom;
}

// ── 메시지 전송 ────────────────────────────────────────────────

/** Matrix 룸에 텍스트 메시지 전송 */
export async function matrixSend(
  token: string,
  roomId: string,
  text: string,
): Promise<string | null> {
  const hs = getMatrixHS();
  const txnId = `jinxus_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const encoded = encodeURIComponent(roomId);
  try {
    const resp = await fetchWithTimeout(
      `${hs}/_matrix/client/v3/rooms/${encoded}/send/m.room.message/${txnId}`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ msgtype: 'm.text', body: text }),
        timeoutMs: 10000,
      }
    );
    if (resp.ok) {
      const data = await resp.json();
      return data.event_id ?? null;
    }
    const errText = await resp.text();
    // 토큰 만료
    if (resp.status === 401) clearSession();
    console.error('[Matrix] send 실패:', resp.status, errText);
  } catch (e) {
    console.error('[Matrix] send 예외:', e);
  }
  return null;
}

// ── Sync (실시간 메시지 수신) ──────────────────────────────────

export interface MatrixEvent {
  event_id: string;
  type: string;
  sender: string;
  room_id: string;
  origin_server_ts: number;
  content: {
    msgtype?: string;
    body?: string;
    [key: string]: unknown;
  };
}

export interface SyncResult {
  nextBatch: string;
  events: MatrixEvent[];
}

/** Matrix /sync 호출 (long-polling)
 *  since 없으면 초기 로드 (최근 50개), since 있으면 변경분만 */
export async function matrixSync(
  token: string,
  since?: string,
  signal?: AbortSignal,
): Promise<SyncResult> {
  const hs = getMatrixHS();
  // since 없으면 초기 로드(빠른 응답), since 있으면 long-poll 10s
  const pollMs = since ? 10000 : 0;
  const params = new URLSearchParams({ timeout: String(pollMs) });
  if (since) {
    params.append('since', since);
  } else {
    // 초기 로드 필터 — 최근 50개 타임라인만, presence/account_data 제외
    const filter = JSON.stringify({
      room: {
        timeline: { limit: 50 },
        state: { lazy_load_members: true },
      },
      presence: { not_types: ['*'] },
      account_data: { not_types: ['*'] },
    });
    params.append('filter', filter);
  }

  const resp = await fetchWithTimeout(`${hs}/_matrix/client/v3/sync?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
    timeoutMs: pollMs + 15000,  // poll 시간 + 15s 여유
  });

  if (resp.status === 401) {
    clearSession();
    throw new Error('Matrix 토큰 만료');
  }
  if (!resp.ok) {
    throw new Error(`Matrix sync 실패: ${resp.status}`);
  }

  const data = await resp.json();
  const nextBatch: string = data.next_batch ?? '';
  const events: MatrixEvent[] = [];

  // 조인된 룸의 타임라인 이벤트 수집
  const joinedRooms: Record<string, unknown> = data.rooms?.join ?? {};
  for (const [roomId, roomData] of Object.entries(joinedRooms)) {
    const rd = roomData as { timeline?: { events?: MatrixEvent[] } };
    const timeline = rd.timeline?.events ?? [];
    for (const ev of timeline) {
      events.push({ ...ev, room_id: roomId });
    }
  }

  return { nextBatch, events };
}
