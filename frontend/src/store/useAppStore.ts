import { create } from 'zustand';
import type { ChatMessage, SystemStatus, AgentInfo } from '@/types';
import { systemApi, agentApi } from '@/lib/api';

interface AppState {
  // 채팅 상태
  messages: ChatMessage[];
  isLoading: boolean;
  sessionId: string | null;

  // 시스템 상태
  systemStatus: SystemStatus | null;
  agents: AgentInfo[];

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
}

export const useAppStore = create<AppState>((set) => ({
  // 초기 상태
  messages: [],
  isLoading: false,
  sessionId: null,
  systemStatus: null,
  agents: [],
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
    try {
      const response = await agentApi.getAll();
      set({ agents: response.agents });
    } catch (error) {
      console.error('Failed to load agents:', error);
    }
  },
}));
