import { create } from 'zustand';
import type { ChatMessage, SystemStatus, AgentInfo } from '@/types';
import { systemApi, agentApi, hrApi, type HRAgentRecord } from '@/lib/api';
import { setDynamicPersonaMap } from '@/lib/personas';
import { MAX_MESSAGES } from '@/lib/constants';

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
  personasVersion: number;  // loadPersonas 완료 시 증가 → 구독 컴포넌트 리렌더링 트리거

  // 현재 탭
  activeTab: 'chat' | 'projects' | 'agents' | 'memory' | 'logs' | 'tools' | 'settings' | 'notes' | 'channel';

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
  /** 백엔드 personas.py → 동적 PERSONA_MAP 덮어쓰기. 앱 시작 시 1회 호출 */
  loadPersonas: () => Promise<void>;

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
  personasVersion: 0,
  activeTab: 'chat',
  logsAgentFilter: 'all',

  // 채팅 액션
  addMessage: (message) =>
    set((state) => {
      // MAX_MESSAGES 초과 시 앞쪽 50개 제거 (매번 1개씩 자르지 않고 배치 트림)
      if (state.messages.length >= MAX_MESSAGES) {
        return { messages: [...state.messages.slice(-(MAX_MESSAGES - 50)), message] };
      }
      return { messages: [...state.messages, message] };
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

  loadPersonas: async () => {
    try {
      const data = await agentApi.getPersonas();
      setDynamicPersonaMap(data.personas);
      // 버전 증가 → 구독 컴포넌트가 리렌더링되어 최신 맵 반영
      useAppStore.setState(s => ({ personasVersion: s.personasVersion + 1 }));
    } catch (error) {
      console.warn('[personas] 백엔드 로드 실패, 정적 fallback 사용:', error);
    }
  },

  getAgentRole: (name: string): string => {
    const hrAgents = useAppStore.getState().hrAgents as HRAgentRecord[];
    const hr = hrAgents.find((a: HRAgentRecord) => a.name === name);
    if (hr) return `${hr.specialty} 전문가`;
    return '에이전트';
  },
}));
