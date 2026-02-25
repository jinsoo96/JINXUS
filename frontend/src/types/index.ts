// 채팅 메시지 타입
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  agentsUsed?: string[];
  success?: boolean;
}

// 에이전트 상태
export interface AgentStatus {
  name: string;
  description: string;
  status: 'idle' | 'running' | 'error';
  lastUsed?: Date;
  tasksCompleted: number;
  successRate: number;
}

// 시스템 상태
export interface SystemStatus {
  status: string;
  uptime_seconds: number;
  redis_connected: boolean;
  qdrant_connected: boolean;
  total_tasks_processed: number;
  active_agents: string[];
}

// 채팅 응답
export interface ChatResponse {
  task_id: string;
  session_id: string;
  response: string;
  agents_used: string[];
  success: boolean;
}

// 메모리 검색 결과
export interface MemorySearchResult {
  agent_name: string;
  task_id: string;
  instruction: string;
  summary: string;
  outcome: string;
  success_score: number;
  timestamp: string;
}

// 에이전트 정보
export interface AgentInfo {
  name: string;
  description: string;
  capabilities: string[];
}
