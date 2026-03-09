import type { ChatResponse, SystemStatus, MemorySearchResult, AgentInfo } from '@/types';

const API_BASE = '/api';

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
  event: 'start' | 'manager_thinking' | 'decompose_done' | 'agent_started' | 'agent_done' | 'message' | 'done' | 'error' | 'cancelled';
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
    message?: string;        // cancelled, error 메시지
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
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController?.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      // SSE 파서: event/data 쌍 손실 방지
      let buffer = '';
      let currentEvent: SSEEvent['event'] = 'message';
      let currentData = '';

      const flushEvent = () => {
        if (currentData) {
          try {
            const data = JSON.parse(currentData);
            onEvent({ event: currentEvent, data });
          } catch {
            // JSON 파싱 실패 무시
          }
        }
        currentEvent = 'message';
        currentData = '';
      };

      try {
        while (true) {
          if (abortController?.signal.aborted) {
            reader.cancel();
            break;
          }

          const { done, value } = await reader.read();
          if (done) {
            flushEvent();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim() === '') {
              flushEvent();
            } else if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim() as SSEEvent['event'];
            } else if (line.startsWith('data:')) {
              currentData += line.slice(5).trim();
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
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

// 시스템 API
export const systemApi = {
  getStatus: async (): Promise<SystemStatus> => {
    return apiCall<SystemStatus>('/status');
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
};

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

export const agentApi = {
  getAll: async (): Promise<{ agents: AgentInfo[] }> => {
    return apiCall<{ agents: AgentInfo[] }>('/agents');
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
    role?: string;
  }): Promise<{ success: boolean; agent: HRAgentRecord; message: string }> => {
    return apiCall<{ success: boolean; agent: HRAgentRecord; message: string }>('/hr/hire', {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  },

  // 에이전트 해고
  fireAgent: async (agentId: string): Promise<{ success: boolean; message: string }> => {
    return apiCall<{ success: boolean; message: string }>(`/hr/fire/${agentId}`, {
      method: 'POST',
    });
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
    return apiCall<{ success: boolean }>('/logs', {
      method: 'DELETE',
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
  status: 'pending' | 'running' | 'in_progress';
  progress: number;
  started_at: string | null;
  created_at: string;
  source: 'background' | 'api';
}

export const taskApi = {
  // 활성 작업 목록 조회
  getActiveTasks: async (): Promise<{ active_tasks: ActiveTask[]; count: number }> => {
    return apiCall<{ active_tasks: ActiveTask[]; count: number }>('/task/active/list');
  },

  // 작업 취소
  cancelTask: async (taskId: string): Promise<{ task_id: string; status: string }> => {
    return apiCall<{ task_id: string; status: string }>(`/task/active/${taskId}`, {
      method: 'DELETE',
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
