import type { ChatResponse, SystemStatus, MemorySearchResult, AgentInfo } from '@/types';

const API_BASE = '/api';

// 기본 API 호출
async function apiCall<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || `API Error: ${response.status}`);
  }

  return response.json();
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

  // SSE 스트리밍 채팅
  streamMessage: (message: string, sessionId?: string): EventSource => {
    const params = new URLSearchParams({ message });
    if (sessionId) params.append('session_id', sessionId);
    return new EventSource(`${API_BASE}/chat?${params.toString()}`);
  },
};

// 시스템 API
export const systemApi = {
  getStatus: async (): Promise<SystemStatus> => {
    return apiCall<SystemStatus>('/status');
  },
};

// 에이전트 API
export const agentApi = {
  getAll: async (): Promise<{ agents: AgentInfo[] }> => {
    return apiCall<{ agents: AgentInfo[] }>('/agents');
  },
};

// 메모리 API
export const memoryApi = {
  search: async (agentName: string, query: string): Promise<{ results: MemorySearchResult[] }> => {
    return apiCall<{ results: MemorySearchResult[] }>('/memory/search', {
      method: 'POST',
      body: JSON.stringify({ agent_name: agentName, query }),
    });
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
