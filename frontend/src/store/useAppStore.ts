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

  // 현재 탭
  activeTab: 'dashboard' | 'chat' | 'graph' | 'agents' | 'memory' | 'logs' | 'tools' | 'settings';

  // 액션
  addMessage: (message: ChatMessage) => void;
  setLoading: (loading: boolean) => void;
  setSessionId: (sessionId: string) => void;
  setActiveTab: (tab: AppState['activeTab']) => void;
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
  activeTab: 'chat',

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
    // 이미 로드된 경우 재요청 방지 (탭 전환 시 중복 호출 방지)
    const { agents: existing } = useAppStore.getState();
    if (existing.length > 0) return;

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
    }
  },

  getAgentRole: (name: string): string => {
    const hrAgents = useAppStore.getState().hrAgents as HRAgentRecord[];
    const hr = hrAgents.find((a: HRAgentRecord) => a.name === name);
    if (hr) return `${hr.specialty} 전문가`;
    return '에이전트';
  },
}));
