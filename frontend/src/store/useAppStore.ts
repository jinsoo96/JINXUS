import { create } from 'zustand';
import type { ChatMessage, SystemStatus, AgentInfo } from '@/types';
import { systemApi, agentApi, hrApi, type HRAgentRecord } from '@/lib/api';

interface AppState {
  // 채팅 상태
  messages: ChatMessage[];
  isLoading: boolean;
  sessionId: string | null;

  // 시스템 상태
  systemStatus: SystemStatus | null;
  agents: AgentInfo[];
  hrAgents: HRAgentRecord[];
  _agentsLoading: boolean;

  // 현재 탭
  activeTab: 'dashboard' | 'chat' | 'graph' | 'agents' | 'memory' | 'logs' | 'tools' | 'settings' | 'notes';

  // 로그 탭 에이전트 필터 (Sidebar에서 클릭 시 설정)
  logsAgentFilter: string;

  // 액션
  addMessage: (message: ChatMessage) => void;
  setLoading: (loading: boolean) => void;
  setSessionId: (sessionId: string) => void;
  setActiveTab: (tab: AppState['activeTab']) => void;
  setLogsAgentFilter: (filter: string) => void;
  clearMessages: () => void;

  // 데이터 로드
  loadSystemStatus: () => Promise<void>;
  loadAgents: () => Promise<void>;

  // HR 헬퍼
  getAgentRole: (name: string) => string;
}

export const useAppStore = create<AppState>((set) => ({
  // 초기 상태
  messages: [],
  isLoading: false,
  sessionId: null,
  systemStatus: null,
  agents: [],
  hrAgents: [],
  _agentsLoading: false,
  activeTab: 'dashboard',
  logsAgentFilter: 'all',

  // 채팅 액션
  addMessage: (message) =>
    set((state) => {
      const newMessages = [...state.messages, message];
      // 최대 300개 유지 (메모리 누수 방지)
      if (newMessages.length > 300) {
        return { messages: newMessages.slice(-300) };
      }
      return { messages: newMessages };
    }),

  setLoading: (loading) => set({ isLoading: loading }),

  setSessionId: (sessionId) => set({ sessionId }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  setLogsAgentFilter: (filter) => set({ logsAgentFilter: filter }),

  clearMessages: () => set({ messages: [] }),

  // 데이터 로드
  loadSystemStatus: async () => {
    try {
      const status = await systemApi.getStatus();
      set({ systemStatus: status });
    } catch (error) {
      console.error('Failed to load system status:', error);
    }
  },

  loadAgents: async () => {
    const { agents: existing, _agentsLoading } = useAppStore.getState();
    // 이미 로드됐거나 로딩 중이면 skip (중복/동시 호출 방지)
    if (existing.length > 0 || _agentsLoading) return;

    set({ _agentsLoading: true });
    try {
      const [agentResponse, hrResponse] = await Promise.all([
        agentApi.getAll(),
        hrApi.getAgents(true).catch(() => ({ agents: [], total: 0 })),
      ]);
      set({
        agents: agentResponse.agents,
        hrAgents: hrResponse.agents,
      });
    } catch (error) {
      console.error('Failed to load agents:', error);
    } finally {
      set({ _agentsLoading: false });
    }
  },

  getAgentRole: (name: string): string => {
    const hrAgents = useAppStore.getState().hrAgents as HRAgentRecord[];
    const hr = hrAgents.find((a: HRAgentRecord) => a.name === name);
    if (hr) return `${hr.specialty} 전문가`;
    return '에이전트';
  },
}));
