import type { ChatResponse, SystemStatus, MemorySearchResult, AgentInfo } from '@/types';

const API_BASE = '/api';
// SSE 스트리밍: Edge Runtime 프록시 경유 (버퍼링 없음)
const STREAM_BASE = '/api/sse';

// 재시도 설정
const RETRY_CONFIG = {
  maxRetries: 2,
  baseDelay: 500,    // ms
  maxDelay: 3000,    // ms
  retryableStatuses: [502, 503, 504, 408, 429],
};

// 기본 API 호출 (exponential backoff 재시도 포함)
async function apiCall<T>(endpoint: string, options?: RequestInit): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= RETRY_CONFIG.maxRetries; attempt++) {
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });

      if (!response.ok) {
        // 재시도 가능한 상태 코드인 경우
        if (attempt < RETRY_CONFIG.maxRetries && RETRY_CONFIG.retryableStatuses.includes(response.status)) {
          const delay = Math.min(RETRY_CONFIG.baseDelay * Math.pow(2, attempt), RETRY_CONFIG.maxDelay);
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || error.message || `API Error: ${response.status}`);
      }

      return response.json();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      // 네트워크 에러일 때 재시도
      if (attempt < RETRY_CONFIG.maxRetries && !(lastError.message.startsWith('API Error'))) {
        const delay = Math.min(RETRY_CONFIG.baseDelay * Math.pow(2, attempt), RETRY_CONFIG.maxDelay);
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
      throw lastError;
    }
  }

  throw lastError || new Error('API call failed');
}

// 채팅 세션 정보
export interface ChatSession {
  session_id: string;
  session_type: 'web' | 'telegram' | 'scheduled';
  chat_id: string | null;
  message_count: number;
  first_message_at: string;
  last_message_at: string;
  ttl_seconds: number | null;
  preview: string;
}

// 채팅 메시지 (서버 저장용)
export interface StoredMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  metadata?: {
    task_id?: string;
    agents_used?: string[];
  };
}

// SSE 이벤트 타입
export interface SSEEvent {
  event: 'start' | 'manager_thinking' | 'decompose_done' | 'agent_started' | 'agent_done' | 'message' | 'done' | 'error' | 'cancelled' | 'log' | 'team_progress' | 'tool_call' | 'routed';
  data: {
    task_id?: string;
    session_id?: string;
    agent?: string;
    instruction?: string;    // agent_started - 에이전트에 할당된 작업
    step?: string;           // manager_thinking
    detail?: string;         // manager_thinking 상세
    subtasks_count?: number; // decompose_done
    mode?: string;           // decompose_done
    content?: string;        // message chunk
    chunk?: boolean;         // message
    score?: number;          // agent_done
    agents_used?: string[];  // done
    response?: string;       // done - full response
    success?: boolean;
    error?: string;
    message?: string;        // cancelled, error 메시지, 또는 직접 에이전트 응답
    line?: string;           // log - raw Python logger output
    specialist?: string;     // team_progress - 전문가 이름
    status?: string;         // team_progress - 'running' | 'done' | 'error'
    tool?: string;           // tool_call - 도구 이름
    route?: string;          // routed - SmartRouter 라우팅 결과 (background/project/chat/task)
    project_id?: string;     // routed - project 라우팅 시 프로젝트 ID
  };
}

// 채팅 API
export const chatApi = {
  // 동기 채팅
  sendMessage: async (message: string, sessionId?: string): Promise<ChatResponse> => {
    return apiCall<ChatResponse>('/chat/sync', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  },

  // SSE 스트리밍 채팅 (POST + fetch) - AbortController 지원
  streamMessage: async (
    message: string,
    sessionId: string | undefined,
    onEvent: (event: SSEEvent) => void,
    onError: (error: Error) => void,
    abortController?: AbortController
  ): Promise<void> => {
    try {
      const response = await fetch(`${STREAM_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController?.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const { consumeSSE } = await import('./sse-parser');
      await consumeSSE(response, (event, data) => {
        onEvent({ event: event as SSEEvent['event'], data: data as SSEEvent['data'] });
      }, abortController?.signal);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError(error instanceof Error ? error : new Error('Stream error'));
    }
  },

  // 세션 목록 조회
  getSessions: async (): Promise<{ sessions: ChatSession[]; total: number }> => {
    return apiCall<{ sessions: ChatSession[]; total: number }>('/chat/sessions');
  },

  // 세션 히스토리 조회
  getHistory: async (sessionId: string): Promise<{ session_id: string; messages: StoredMessage[]; total: number }> => {
    return apiCall<{ session_id: string; messages: StoredMessage[]; total: number }>(`/chat/history/${sessionId}`);
  },

  // 세션 삭제
  deleteSession: async (sessionId: string): Promise<{ success: boolean; message: string }> => {
    return apiCall<{ success: boolean; message: string }>(`/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  },

  // 스마트 라우팅 SSE 스트리밍 (자동 분류: chat/task/background/project)
  streamSmart: async (
    message: string,
    sessionId: string | undefined,
    onEvent: (event: SSEEvent) => void,
    onError: (error: Error) => void,
    abortController?: AbortController
  ): Promise<void> => {
    try {
      const response = await fetch(`${STREAM_BASE}/chat/smart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController?.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const { consumeSSE } = await import('./sse-parser');
      await consumeSSE(response, (event, data) => {
        onEvent({ event: event as SSEEvent['event'], data: data as SSEEvent['data'] });
      }, abortController?.signal);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError(error instanceof Error ? error : new Error('Smart stream error'));
    }
  },

  // SSE 스트리밍 취소
  cancelStream: async (taskId: string): Promise<{ success: boolean; task_id: string; message: string }> => {
    return apiCall<{ success: boolean; task_id: string; message: string }>(`/chat/cancel/${taskId}`, {
      method: 'POST',
    });
  },

  // 활성 스트림 목록
  getActiveStreams: async (): Promise<{ active_streams: string[]; count: number }> => {
    return apiCall<{ active_streams: string[]; count: number }>('/chat/active');
  },

  // 특정 에이전트와 직접 채팅 (SSE)
  streamAgentDirect: async (
    agentName: string,
    message: string,
    sessionId: string | undefined,
    onEvent: (event: SSEEvent) => void,
    onError: (error: Error) => void,
    abortController?: AbortController,
  ): Promise<void> => {
    try {
      const response = await fetch(`${STREAM_BASE}/chat/agent/${encodeURIComponent(agentName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController?.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const { consumeSSE } = await import('./sse-parser');
      await consumeSSE(response, (event, data) => {
        onEvent({ event: event as SSEEvent['event'], data: data as SSEEvent['data'] });
      }, abortController?.signal);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError(error instanceof Error ? error : new Error('Stream error'));
    }
  },
};

// MCP 상태 타입
export interface MCPTool {
  name: string;
  description: string;
}

export interface MCPServerStatus {
  name: string;
  status: 'connected' | 'disconnected' | 'api_key_missing' | 'disabled';
  description?: string;
  tools_count: number;
  tools: MCPTool[];
  requires_api_key?: string | null;
  has_api_key?: boolean;
  enabled?: boolean;
  error?: string;
}

export interface MCPStatus {
  initialized: boolean;
  connected_count: number;
  configured_count: number;
  total_configured: number;
  total_tools: number;
  servers: MCPServerStatus[];
}

// ToolGraph 타입
export interface ToolGraphNode {
  name: string;
  description: string;
  category: string;
  keywords: string[];
  weight: number;
}

export interface ToolGraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

export interface ToolGraphData {
  nodes: ToolGraphNode[];
  edges: ToolGraphEdge[];
}

export interface ToolGraphVizNode {
  id: string;
  label: string;
  description: string;
  category: string;
  weight: number;
  source: 'native' | 'mcp';
  keywords: string[];
  annotations?: Record<string, boolean>;
}

export interface ToolGraphVizEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
  description: string;
}

export interface ToolGraphVisualization {
  nodes: ToolGraphVizNode[];
  edges: ToolGraphVizEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface ToolGraphWorkflow {
  query: string;
  score: number;
  tools: { name: string; description: string; category: string }[];
  edges: { from: string; to: string; type: string }[];
}

// 도구 목록 타입
export interface NativeTool {
  name: string;
  description: string;
  allowed_agents: string[];
  enabled: boolean;
}

export interface ToolsListResponse {
  total: number;
  mcp_count: number;
  native_count: number;
  mcp_tools: { name: string; description: string; server: string }[];
  native_tools: NativeTool[];
}

// 도구 정책 타입
export interface AgentToolPolicy {
  whitelist: string[] | null;
  blacklist: string[];
  max_rounds: number | null;
}

export interface ToolPoliciesResponse {
  policies: Record<string, AgentToolPolicy>;
}

// 도구 호출 로그 타입
export interface ToolCallLog {
  timestamp: string;
  agent: string;
  tool: string;
  status: 'success' | 'error';
  duration_ms: number | null;
  error: string | null;
}

export interface ToolLogsResponse {
  logs: ToolCallLog[];
  total: number;
}

// 위임 이벤트 타입
export interface DelegationEvent {
  timestamp: string;
  type: 'delegate' | 'complete';
  from?: string;
  to?: string;
  agent?: string;
  instruction?: string;
  task_id?: string;
  execution_mode?: string;
  success?: boolean;
  duration_ms?: number;
  score?: number;
}

export interface DelegationEventsResponse {
  events: DelegationEvent[];
  total: number;
}

// 시스템 API
export const systemApi = {
  getStatus: async (): Promise<SystemStatus> => {
    return apiCall<SystemStatus>('/status');
  },

  clearCompletedTasks: async (): Promise<{ success: boolean; deleted: number }> => {
    return apiCall<{ success: boolean; deleted: number }>('/status/tasks/completed', { method: 'DELETE' });
  },

  // 시스템 정보 (버전 포함) — trailing slash 없이 /api 직접 호출 (308 redirect 방지)
  getInfo: async (): Promise<{ name: string; version: string; status: string }> => {
    return apiCall('');
  },

  // MCP 상태 조회
  getMCPStatus: async (): Promise<MCPStatus> => {
    return apiCall<MCPStatus>('/status/mcp');
  },

  // MCP 서버 재연결
  reconnectMCP: async (serverName: string): Promise<{ success: boolean; message: string }> => {
    return apiCall<{ success: boolean; message: string }>(`/status/mcp/reconnect/${serverName}`, {
      method: 'POST',
    });
  },

  // ToolGraph 조회
  getToolGraph: async (): Promise<ToolGraphData> => {
    return apiCall<ToolGraphData>('/status/tool-graph');
  },

  // ToolGraph 시각화 데이터
  getToolGraphVisualization: async (): Promise<ToolGraphVisualization> => {
    return apiCall<ToolGraphVisualization>('/status/tool-graph/visualization');
  },

  // ToolGraph 워크플로우 탐색
  retrieveWorkflow: async (query: string, topK: number = 5): Promise<ToolGraphWorkflow> => {
    return apiCall<ToolGraphWorkflow>('/status/tool-graph/retrieve', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    });
  },

  // 등록된 도구 목록
  getTools: async (): Promise<ToolsListResponse> => {
    return apiCall<ToolsListResponse>('/status/tools');
  },

  // 에이전트 성능 리포트
  getPerformance: async (): Promise<Record<string, unknown>> => {
    return apiCall('/status/performance');
  },

  // 시스템 메트릭 (에이전트/도구/캐시)
  getMetrics: async (): Promise<Record<string, unknown>> => {
    return apiCall('/status/metrics');
  },

  // 도구 정책 전체 조회
  getToolPolicies: async (): Promise<ToolPoliciesResponse> => {
    return apiCall<ToolPoliciesResponse>('/status/tool-policies');
  },

  // 특정 에이전트 도구 정책 조회
  getAgentToolPolicy: async (agentName: string): Promise<AgentToolPolicy & { agent_name: string }> => {
    return apiCall<AgentToolPolicy & { agent_name: string }>(`/status/tool-policies/${agentName}`);
  },

  // 실시간 도구 호출 로그 조회
  getToolLogs: async (limit: number = 50): Promise<ToolLogsResponse> => {
    return apiCall<ToolLogsResponse>(`/status/tool-logs?limit=${limit}`);
  },

  // 위임 이벤트 타임라인 조회
  getDelegationEvents: async (limit: number = 30): Promise<DelegationEventsResponse> => {
    return apiCall<DelegationEventsResponse>(`/status/delegation-events?limit=${limit}`);
  },

  // 도구별 호출 통계 (analytics)
  getToolAnalytics: async (): Promise<ToolAnalyticsResponse> => {
    return apiCall<ToolAnalyticsResponse>('/status/tool-analytics');
  },

  // 에이전트 도구 정책 업데이트
  updateToolPolicy: async (agentName: string, policy: {
    whitelist?: string[] | null;
    blacklist?: string[];
    allow_all?: boolean;
  }): Promise<{ success: boolean; policy: { whitelist: string[] | null; blacklist: string[] } }> => {
    return apiCall(`/status/tool-policies/${agentName}`, {
      method: 'PUT',
      body: JSON.stringify(policy),
    });
  },

  // MCP 서버 동적 추가
  addMCPServer: async (config: {
    name: string;
    command?: string;
    args: string[];
    env?: Record<string, string>;
    allowed_agents?: string[];
    description?: string;
    requires_api_key?: string;
  }): Promise<{ success: boolean; server_name: string; tools_count: number; tools: string[]; message: string }> => {
    return apiCall('/status/mcp/servers', {
      method: 'POST',
      body: JSON.stringify({ command: 'npx', ...config }),
    });
  },

  // MCP 서버 동적 제거
  removeMCPServer: async (serverName: string): Promise<{ success: boolean; removed_tools: number; message: string }> => {
    return apiCall(`/status/mcp/servers/${serverName}`, { method: 'DELETE' });
  },

  // MCP 서버 테스트
  testMCPServer: async (serverName: string): Promise<{ success: boolean; tools_count: number; tools: { name: string; description: string }[] }> => {
    return apiCall(`/status/mcp/servers/${serverName}/test`, { method: 'POST' });
  },
};

export interface ToolAnalyticsItem {
  tool: string;
  calls: number;
  successes: number;
  success_rate: number;
  avg_duration_ms: number;
  agents: string[];
}

export interface ToolAnalyticsResponse {
  analytics: ToolAnalyticsItem[];
  total_calls: number;
  total_tools: number;
}

// 에이전트 API
export interface AgentRuntimeStatus {
  name: string;
  status: 'idle' | 'working' | 'error';
  current_node: string | null;
  current_task: string | null;
  current_tools: string[];
  last_update: string | null;
  error_message: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  description: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface AgentGraph {
  agent_name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  current_node: string | null;
}

export interface CodingSpecialist {
  name: string;
  description: string;
  status: 'idle' | 'working' | 'error';
  current_task: string | null;
  current_node: string | null;
}

export const agentApi = {
  /** 백엔드 personas.py → 프론트 동기화용. 앱 시작 시 1회 호출. */
  getPersonas: async (): Promise<{ personas: Record<string, import('@/lib/personas').PersonaInfo> }> => {
    return apiCall('/agents/personas');
  },

  getAll: async (): Promise<{ agents: AgentInfo[] }> => {
    return apiCall<{ agents: AgentInfo[] }>('/agents');
  },

  /** 에이전트 이름 변경 */
  rename: async (agentCode: string, koreanName: string, fullName?: string): Promise<{ success: boolean }> => {
    return apiCall(`/agents/${encodeURIComponent(agentCode)}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ korean_name: koreanName, full_name: fullName || koreanName }),
    });
  },

  // 에이전트 실시간 상태 조회
  getRuntimeStatus: async (agentName: string): Promise<AgentRuntimeStatus> => {
    return apiCall<AgentRuntimeStatus>(`/agents/${agentName}/runtime`);
  },

  // 모든 에이전트 실시간 상태 조회
  getAllRuntimeStatus: async (): Promise<{ agents: AgentRuntimeStatus[]; working_count: number }> => {
    return apiCall<{ agents: AgentRuntimeStatus[]; working_count: number }>('/agents/runtime/all');
  },

  // 에이전트 그래프 구조 조회
  getGraph: async (agentName: string): Promise<AgentGraph> => {
    return apiCall<AgentGraph>(`/agents/${agentName}/graph`);
  },

  // 전문가 팀 조회 (범용)
  getTeam: async (parentName: string): Promise<{ parent: string; team: CodingSpecialist[] }> => {
    return apiCall<{ parent: string; team: CodingSpecialist[] }>(`/agents/${parentName}/team`);
  },

  /** @deprecated getTeam('JX_CODER') 사용 */
  getCoderTeam: async (): Promise<{ parent: string; team: CodingSpecialist[] }> => {
    return apiCall<{ parent: string; team: CodingSpecialist[] }>('/agents/JX_CODER/team');
  },

  /** @deprecated getTeam('JX_RESEARCHER') 사용 */
  getResearcherTeam: async (): Promise<{ parent: string; team: CodingSpecialist[] }> => {
    return apiCall<{ parent: string; team: CodingSpecialist[] }>('/agents/JX_RESEARCHER/team');
  },
};

// HR API
export interface OrgNode {
  id: string;
  name: string;
  role: string;
  specialty: string;
  is_active: boolean;
  children: OrgNode[];
}

export interface OrgChartData {
  root: OrgNode;
  total_agents: number;
  active_agents: number;
}

export interface AvailableSpec {
  specialty: string;
  name: string;
  description: string;
  capabilities: string[];
}

export interface HRAgentRecord {
  id: string;
  name: string;
  role: string;
  specialty: string;
  description: string;
  is_active: boolean;
  hired_at: string;
  fired_at: string | null;
  fire_reason: string | null;
  total_tasks: number;
  success_rate: number;
}

export const hrApi = {
  // 조직도 조회
  getOrgChart: async (): Promise<OrgChartData> => {
    return apiCall<OrgChartData>('/hr/org-chart');
  },

  // 에이전트 목록 조회
  getAgents: async (activeOnly: boolean = true): Promise<{ agents: HRAgentRecord[]; total: number }> => {
    return apiCall<{ agents: HRAgentRecord[]; total: number }>(`/hr/agents?active_only=${activeOnly}`);
  },

  // 고용 가능한 스펙 조회
  getAvailableSpecs: async (): Promise<{ specs: AvailableSpec[] }> => {
    return apiCall<{ specs: AvailableSpec[] }>('/hr/available-specs');
  },

  // 에이전트 고용
  hireAgent: async (spec: {
    specialty: string;
    name?: string;
    description?: string;
    capabilities?: string[];
    tools?: string[];
    role?: string;
    system_prompt?: string;
  }): Promise<{ success: boolean; agent: HRAgentRecord; message: string }> => {
    return apiCall<{ success: boolean; agent: HRAgentRecord; message: string }>('/hr/hire', {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  },

  // 에이전트 해고 (soft-delete)
  fireAgent: async (agentId: string, reason?: string): Promise<{ success: boolean; message: string }> => {
    return apiCall<{ success: boolean; message: string }>(`/hr/fire/${agentId}`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || '' }),
    });
  },

  // 해고된 에이전트 재고용
  rehireAgent: async (agentId: string): Promise<{ success: boolean; agent: HRAgentRecord; message: string }> => {
    return apiCall<{ success: boolean; agent: HRAgentRecord; message: string }>(`/hr/rehire/${agentId}`, {
      method: 'POST',
    });
  },

  // 해고된 에이전트 목록
  getFiredAgents: async (): Promise<{ agents: HRAgentRecord[]; total: number }> => {
    return apiCall<{ agents: HRAgentRecord[]; total: number }>('/hr/fired');
  },

  // 새끼 에이전트 스폰
  spawnChild: async (spec: {
    parent_id: string;
    specialty: string;
    task_focus: string;
    temporary?: boolean;
  }): Promise<{ success: boolean; agent: HRAgentRecord; message: string }> => {
    return apiCall<{ success: boolean; agent: HRAgentRecord; message: string }>('/hr/spawn', {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  },
};

// 메모리 API
export const memoryApi = {
  search: async (agentName: string, query: string, limit: number = 5): Promise<{ results: MemorySearchResult[]; total: number }> => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (agentName) params.append('agent', agentName);
    return apiCall<{ results: MemorySearchResult[]; total: number }>(`/memory/search?${params.toString()}`);
  },

  getStats: async (): Promise<{ health: Record<string, unknown>; total_tasks_logged: number; collections: Record<string, unknown> }> => {
    return apiCall('/memory/stats');
  },

  prune: async (agentName: string): Promise<{ success: boolean; agent_name: string; deleted_count: number }> => {
    return apiCall(`/memory/prune/${agentName}`, { method: 'POST' });
  },
};

// 피드백 API
export const feedbackApi = {
  submit: async (taskId: string, score: number, comment?: string): Promise<{ status: string }> => {
    return apiCall<{ status: string }>('/feedback', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, score, comment }),
    });
  },
};

// 로그 API
export interface TaskLog {
  id: string;
  main_task_id: string | null;
  agent_name: string;
  instruction: string;
  success: boolean;
  success_score: number;
  duration_ms: number;
  failure_reason: string | null;
  output: string | null;
  tool_calls: string[] | null;
  created_at: string;
}

export interface LogsSummary {
  total_tasks: number;
  agent_stats: Record<string, {
    total_tasks: number;
    success_rate: number;
    avg_duration_ms: number;
  }>;
}

export const logsApi = {
  // 로그 목록 조회
  getLogs: async (agentName?: string, limit: number = 50, offset: number = 0): Promise<{ logs: TaskLog[]; total: number }> => {
    const params = new URLSearchParams();
    if (agentName) params.append('agent_name', agentName);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return apiCall<{ logs: TaskLog[]; total: number }>(`/logs?${params.toString()}`);
  },

  // 특정 작업(채팅 메시지)의 실행 흐름 조회
  getLogsByTaskId: async (taskId: string): Promise<{ logs: TaskLog[]; total: number }> => {
    return apiCall<{ logs: TaskLog[]; total: number }>(`/logs?main_task_id=${encodeURIComponent(taskId)}&limit=50`);
  },

  // 로그 요약 통계
  getSummary: async (): Promise<LogsSummary> => {
    return apiCall<LogsSummary>('/logs/summary');
  },

  // 개별 로그 삭제
  deleteLog: async (logId: string): Promise<{ success: boolean }> => {
    return apiCall<{ success: boolean }>(`/logs/${logId}`, { method: 'DELETE' });
  },

  // 선택 로그 일괄 삭제
  deleteLogs: async (logIds: string[]): Promise<{ success: boolean }> => {
    return apiCall<{ success: boolean }>('/logs/bulk-delete', {
      method: 'POST',
      body: JSON.stringify({ log_ids: logIds }),
    });
  },

  // 오래된 로그 정리
  cleanup: async (days: number, keepFailures: boolean): Promise<{ deleted_count: number }> => {
    return apiCall<{ deleted_count: number }>('/logs/cleanup', {
      method: 'POST',
      body: JSON.stringify({ days, keep_failures: keepFailures }),
    });
  },
};

// 작업 API
export interface ActiveTask {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'in_progress' | 'paused';
  progress: number;
  started_at: string | null;
  created_at: string;
  source: 'background' | 'api';
  steps_completed?: number;
  steps_total?: number;
}

export interface TaskCreateRequest {
  message: string;
  session_id?: string;
  autonomous?: boolean;
  max_steps?: number;
  timeout_seconds?: number;
}

export interface TaskDetail {
  task_id: string;
  status: string;
  result: string | null;
  agents_used: string[];
  duration_ms: number | null;
  created_at: string;
  completed_at: string | null;
}

export const taskApi = {
  // 활성 작업 목록 조회
  getActiveTasks: async (): Promise<{ active_tasks: ActiveTask[]; count: number }> => {
    return apiCall<{ active_tasks: ActiveTask[]; count: number }>('/task/active/list');
  },

  // 작업 생성 (백그라운드 실행)
  createTask: async (req: TaskCreateRequest): Promise<{ task_id: string; status: string; message: string }> => {
    return apiCall<{ task_id: string; status: string; message: string }>('/task', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  // 작업 상태 조회
  getTaskStatus: async (taskId: string): Promise<TaskDetail> => {
    return apiCall<TaskDetail>(`/task/${taskId}`);
  },

  // 작업 진행 상황 SSE 스트림
  streamTaskProgress: (
    taskId: string,
    onEvent: (event: { event: string; data: Record<string, unknown> }) => void,
    onError: (error: Error) => void,
    onDone: () => void,
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${STREAM_BASE}/task/${taskId}/stream`, {
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No body');

      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = 'progress';
      let dataChunks: string[] = [];

      const flush = () => {
        if (dataChunks.length > 0) {
          try {
            const data = JSON.parse(dataChunks.join(''));
            onEvent({ event: currentEvent, data });
            if (currentEvent === 'done' || currentEvent === 'completed' || currentEvent === 'failed') {
              onDone();
            }
          } catch { /* ignore */ }
        }
        currentEvent = 'progress';
        dataChunks = [];
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) { flush(); onDone(); break; }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim() === '') {
              flush();
            } else if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              dataChunks.push(line.slice(5).trim());
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      onError(err instanceof Error ? err : new Error(String(err)));
    });

    return controller;
  },

  // 작업 취소
  cancelTask: async (taskId: string): Promise<{ task_id: string; status: string }> => {
    return apiCall<{ task_id: string; status: string }>(`/task/active/${taskId}`, {
      method: 'DELETE',
    });
  },

  // 작업 일시정지
  pauseTask: async (taskId: string): Promise<{ task_id: string; status: string }> => {
    return apiCall<{ task_id: string; status: string }>(`/task/active/${taskId}/pause`, {
      method: 'POST',
    });
  },

  // 작업 재개
  resumeTask: async (taskId: string): Promise<{ task_id: string; status: string }> => {
    return apiCall<{ task_id: string; status: string }>(`/task/active/${taskId}/resume`, {
      method: 'POST',
    });
  },
};

// 자가 강화 API
export interface ImproveHistoryItem {
  agent_name: string;
  test_id: string;
  old_score: number;
  new_score: number;
  winner: string;
  test_count: number;
  created_at: string;
}

export interface PromptVersion {
  version: string;
  created_at: string;
  is_active: boolean;
}

export const improveApi = {
  // 수동 자가 강화 트리거
  trigger: async (agentName?: string): Promise<{ success: boolean; improvements: unknown[]; message?: string }> => {
    return apiCall('/improve', {
      method: 'POST',
      body: JSON.stringify({ agent_name: agentName }),
    });
  },

  // 개선 이력 조회
  getHistory: async (agentName?: string, limit: number = 20): Promise<{ history: ImproveHistoryItem[] }> => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (agentName) params.append('agent_name', agentName);
    return apiCall(`/improve/history?${params.toString()}`);
  },

  // 프롬프트 버전 롤백
  rollback: async (agentName: string, version: string): Promise<{ success: boolean; agent_name: string; rolled_back_to: string }> => {
    return apiCall('/improve/rollback', {
      method: 'POST',
      body: JSON.stringify({ agent_name: agentName, version }),
    });
  },

  // 프롬프트 버전 이력
  getPromptVersions: async (agentName: string): Promise<{ agent_name: string; active_version: string; versions: PromptVersion[] }> => {
    return apiCall(`/improve/prompts/${agentName}`);
  },
};

// 플러그인 API
export interface PluginInfo {
  name: string;
  description: string;
  allowed_agents: string[];
  is_mcp?: boolean;
  enabled: boolean;
}

export const pluginsApi = {
  // 플러그인 목록
  getAll: async (): Promise<{ plugins: PluginInfo[] }> => {
    return apiCall('/plugins');
  },

  // 플러그인 상세
  get: async (name: string): Promise<PluginInfo> => {
    return apiCall(`/plugins/${name}`);
  },

  // 활성화
  enable: async (name: string): Promise<{ success: boolean; name: string; enabled: boolean }> => {
    return apiCall('/plugins/enable', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  // 비활성화
  disable: async (name: string): Promise<{ success: boolean; name: string; enabled: boolean }> => {
    return apiCall('/plugins/disable', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  // 전체 재로드
  reload: async (): Promise<{ success: boolean; loaded_count: number }> => {
    return apiCall('/plugins/reload', { method: 'POST' });
  },
};

// ── Docker 컨테이너 ──────────────────────────────────────────────────────────

export interface DockerContainer {
  id: string;
  name: string;
  image: string;
  status: string;
  state: string;
  created: string;
}

export const dockerApi = {
  getContainers: async (): Promise<{ containers: DockerContainer[] }> => {
    return apiCall<{ containers: DockerContainer[] }>('/docker/containers');
  },

  streamLogs: (
    containerId: string,
    tail: number,
    onLine: (line: string, stream: 'stdout' | 'stderr', timestamp: string) => void,
    onError: (error: Error) => void,
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${STREAM_BASE}/docker/containers/${containerId}/logs?tail=${tail}`, {
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { consumeSSE } = await import('./sse-parser');
      await consumeSSE(response, (event, data) => {
        if (event === 'log') {
          const d = data as { line: string; stream: string; timestamp: string };
          onLine(d.line, d.stream as 'stdout' | 'stderr', d.timestamp);
        } else if (event === 'error') {
          const d = data as { error: string };
          onError(new Error(d.error));
        }
      }, controller.signal);
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      onError(err instanceof Error ? err : new Error(String(err)));
    });

    return controller;
  },
};

// ── 개발 노트 ─────────────────────────────────────────────────────────────────

export interface DevNote {
  id: string;
  filename: string;
  title: string;
  date: string;
  summary: string;
  size: number;
  modified_at: string;
  content?: string;
}

export const devNotesApi = {
  list: async (): Promise<{ notes: DevNote[]; count: number }> => {
    return apiCall('/dev-notes');
  },

  get: async (id: string): Promise<DevNote> => {
    return apiCall(`/dev-notes/${id}`);
  },

  create: async (title: string, content: string, filename?: string): Promise<DevNote> => {
    return apiCall('/dev-notes', {
      method: 'POST',
      body: JSON.stringify({ title, content, filename }),
    });
  },

  update: async (id: string, content: string): Promise<DevNote> => {
    return apiCall(`/dev-notes/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  },

  delete: async (id: string): Promise<{ deleted: string }> => {
    return apiCall(`/dev-notes/${id}`, { method: 'DELETE' });
  },
};

// ── 프로젝트 관리 ────────────────────────────────────────────────────────────

export interface ProjectPhase {
  id: string;
  name: string;
  instruction: string;
  agent: string;
  depends_on: string[];
  status: 'pending' | 'waiting' | 'running' | 'completed' | 'failed' | 'cancelled';
  result_summary: string;
  task_id: string;
  started_at: string | null;
  completed_at: string | null;
  error: string;
  max_steps: number;
}

export interface ProjectDetail {
  id: string;
  title: string;
  description: string;
  status: 'planning' | 'ready' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  phases: ProjectPhase[];
  created_at: string;
  updated_at: string;
  completed_at: string;
  total_duration_s: number;
  error: string;
}

export const projectApi = {
  create: async (description: string): Promise<ProjectDetail> => {
    return apiCall<ProjectDetail>('/projects', {
      method: 'POST',
      body: JSON.stringify({ description }),
    });
  },

  list: async (): Promise<ProjectDetail[]> => {
    return apiCall<ProjectDetail[]>('/projects');
  },

  get: async (projectId: string): Promise<ProjectDetail> => {
    return apiCall<ProjectDetail>(`/projects/${projectId}`);
  },

  start: async (projectId: string): Promise<{ success: boolean; message: string }> => {
    return apiCall(`/projects/${projectId}/start`, { method: 'POST' });
  },

  stop: async (projectId: string): Promise<{ success: boolean; message: string }> => {
    return apiCall(`/projects/${projectId}/stop`, { method: 'POST' });
  },

  delete: async (projectId: string): Promise<{ success: boolean; message: string }> => {
    return apiCall(`/projects/${projectId}`, { method: 'DELETE' });
  },

  updatePhase: async (projectId: string, phaseId: string, instruction: string): Promise<{ success: boolean }> => {
    return apiCall(`/projects/${projectId}/phases/${phaseId}`, {
      method: 'PATCH',
      body: JSON.stringify({ instruction }),
    });
  },

  streamProgress: (
    projectId: string,
    onEvent: (event: { event: string; data: Record<string, unknown> }) => void,
    onError: (error: Error) => void,
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${STREAM_BASE}/projects/${projectId}/stream`, {
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { consumeSSE } = await import('./sse-parser');
      await consumeSSE(response, (event, data) => {
        onEvent({ event, data: data as Record<string, unknown> });
      }, controller.signal);
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      onError(err instanceof Error ? err : new Error(String(err)));
    });

    return controller;
  },
};

// ===== Company Channel API =====

export interface ChannelMessage {
  id: string;
  channel: string;
  role: 'agent' | 'user' | 'system';
  from_name: string;
  content: string;
  message_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PendingApproval {
  id: string;
  plan_summary: string;
  subtasks_count: number;
  session_id: string;
  created_at: string;
}

export const channelApi = {
  getHistory: (channel: string, limit = 50) =>
    apiCall<{ channel: string; messages: ChannelMessage[] }>(`/channel/history/${channel}?limit=${limit}`),

  clearHistory: (channel: string) =>
    apiCall<{ success: boolean; channel: string; deleted: number }>(`/channel/history/${channel}`, {
      method: 'DELETE',
    }),

  getAllHistory: (limit = 50) =>
    apiCall<{ channels: Record<string, ChannelMessage[]> }>(`/channel/history?limit=${limit}`),

  postMessage: (content: string, channel?: string, messageType = 'chat') =>
    apiCall<{ success: boolean; message: ChannelMessage }>('/channel/message', {
      method: 'POST',
      body: JSON.stringify({ content, channel, message_type: messageType }),
    }),

  approve: (requestId: string, status: 'approved' | 'modified' | 'cancelled', feedback = '') =>
    apiCall<{ success: boolean }>('/channel/approve', {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId, status, feedback }),
    }),

  getPendingApprovals: () =>
    apiCall<{ pending: PendingApproval[]; count: number }>('/channel/approvals/pending'),

  streamChannel: (
    onData: (data: { type: string; message?: ChannelMessage }) => void,
    signal?: AbortSignal,
    channels?: string,
    clearedAt?: string,
  ): void => {
    // STREAM_BASE: Next.js rewrite 프록시 경유
    const params = new URLSearchParams();
    if (channels) params.set('channels', channels);
    if (clearedAt && clearedAt !== '{}') params.set('cleared_at', clearedAt);
    const qs = params.toString();
    const url = qs
      ? `${STREAM_BASE}/channel/stream?${qs}`
      : `${STREAM_BASE}/channel/stream`;

    let retryDelay = 1000;
    const MAX_RETRY_DELAY = 15000;

    async function connect(): Promise<void> {
      if (signal?.aborted) return;
      try {
        const response = await fetch(url, { signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const reader = response.body?.getReader();
        if (!reader) return;
        retryDelay = 1000; // 연결 성공 시 리셋
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try { onData(JSON.parse(line.slice(6))); } catch { /* ignore */ }
            }
          }
        }
      } catch (e: unknown) {
        if ((e as { name?: string })?.name === 'AbortError' || signal?.aborted) return;
      }
      // 연결 끊김 → 지수 백오프로 자동 재연결
      if (!signal?.aborted) {
        await new Promise(r => setTimeout(r, retryDelay));
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY);
        connect();
      }
    }
    connect();
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Mission API
// ═══════════════════════════════════════════════════════════════════════════

// 미션 SSE 이벤트 타입
export interface MissionSSEEvent {
  event:
    | 'mission_created'
    | 'mission_status'
    | 'mission_huddle'
    | 'mission_briefing_message'
    | 'mission_agent_activity'
    | 'mission_message'
    | 'mission_thinking'
    | 'mission_complete'
    | 'mission_failed'
    | 'mission_cancelled'
    | 'mission_approval_required'
    | 'mission_tool_calls'
    | 'agent_dm'
    | 'agent_report'
    | 'agent_broadcast'
    | 'huddle_start'
    | 'huddle_message'
    | 'huddle_end'
    | 'keepalive';
  data: Record<string, unknown>;
}

// 미션 데이터 타입
export interface MissionData {
  id: string;
  title: string;
  description: string;
  type: 'quick' | 'standard' | 'epic' | 'raid';
  status: 'briefing' | 'in_progress' | 'review' | 'complete' | 'failed' | 'cancelled';
  assigned_agents: string[];
  subtasks: Array<{
    id: string;
    instruction: string;
    assigned_agent: string;
    status: string;
    result?: string;
  }>;
  result?: string;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  original_input: string;
  agent_conversations: Array<{
    from: string;
    to?: string;
    message: string;
    type: string;
    timestamp: string;
  }>;
}

export const missionApi = {
  // 미션 생성 + 실행 (SSE 스트리밍) — SSE 끊기면 자동 재연결
  streamMission: async (
    message: string,
    sessionId: string | undefined,
    onEvent: (event: MissionSSEEvent) => void,
    onError: (error: Error) => void,
    abortController?: AbortController,
  ): Promise<void> => {
    // Geny 패턴: POST로 시작 → EventSource GET으로 실시간 수신
    // POST 응답에서 SSE를 읽지 않으므로 프록시 버퍼링 문제 없음

    // 1단계: POST로 미션 생성 + 실행 시작 (JSON 즉시 반환)
    let missionData: Record<string, unknown>;
    try {
      const response = await fetch(`${API_BASE}/mission/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController?.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      missionData = await response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError(error instanceof Error ? error : new Error('Mission start failed'));
      return;
    }

    const missionId = missionData.id as string;

    // mission_created 이벤트 즉시 전달
    onEvent({
      event: 'mission_created',
      data: missionData as unknown as MissionSSEEvent['data'],
    });

    // 2단계: EventSource GET으로 실시간 이벤트 수신
    return new Promise<void>((resolve) => {
      const evtSource = new EventSource(`${STREAM_BASE}/mission/${missionId}/events`);
      const cleanup = () => { evtSource.close(); resolve(); };

      // abort 시 정리
      abortController?.signal.addEventListener('abort', cleanup);

      // 모든 이벤트를 수신하는 핸들러
      const EVENTS = [
        'mission_status', 'mission_thinking', 'mission_agent_activity',
        'mission_message', 'mission_complete', 'mission_failed', 'mission_cancelled',
        'mission_briefing_message', 'mission_huddle', 'mission_tool_calls',
        'mission_approval_required', 'agent_dm', 'agent_report',
        'huddle_message', 'mission_agent_blocked', 'keepalive',
      ];

      for (const evtName of EVENTS) {
        evtSource.addEventListener(evtName, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            onEvent({ event: evtName as MissionSSEEvent['event'], data });

            // 종료 이벤트
            if (['mission_complete', 'mission_failed', 'mission_cancelled'].includes(evtName)) {
              cleanup();
            }
          } catch { /* JSON 파싱 실패 무시 */ }
        });
      }

      evtSource.onerror = () => {
        // EventSource 자동 재연결 시도. readyState CLOSED면 완전 종료
        if (evtSource.readyState === EventSource.CLOSED) {
          // 미션 상태 직접 조회
          missionApi.getMission(missionId).then(mission => {
            if (mission.status === 'complete' || mission.status === 'failed') {
              onEvent({
                event: mission.status === 'complete' ? 'mission_complete' : 'mission_failed',
                data: mission as unknown as MissionSSEEvent['data'],
              });
            } else {
              onError(new Error('SSE 연결 끊김. 미션은 백그라운드에서 진행 중입니다.'));
            }
          }).catch(() => {
            onError(new Error('SSE 연결 끊김.'));
          }).finally(resolve);
        }
      };
    });
  },

  // 미션 목록 조회
  listMissions: async (status?: string, limit = 20): Promise<{ missions: MissionData[]; total: number }> => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    params.set('limit', String(limit));
    return apiCall<{ missions: MissionData[]; total: number }>(`/mission/list?${params}`);
  },

  // 미션 상세 조회
  getMission: async (missionId: string): Promise<MissionData> => {
    return apiCall<MissionData>(`/mission/${missionId}`);
  },

  // 미션 취소
  cancelMission: async (missionId: string): Promise<{ success: boolean; mission_id: string }> => {
    return apiCall<{ success: boolean; mission_id: string }>(`/mission/${missionId}/cancel`, {
      method: 'POST',
    });
  },

  // 미션 삭제
  deleteMission: async (missionId: string): Promise<{ success: boolean; mission_id: string }> => {
    return apiCall<{ success: boolean; mission_id: string }>(`/mission/${missionId}`, {
      method: 'DELETE',
    });
  },

  // 미션 에이전트 대화 로그
  getConversations: async (missionId: string): Promise<{
    mission_id: string;
    conversations: MissionData['agent_conversations'];
    total: number;
  }> => {
    return apiCall<{ mission_id: string; conversations: MissionData['agent_conversations']; total: number }>(
      `/mission/${missionId}/conversations`
    );
  },
};

