'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useAppStore } from '@/store/useAppStore';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';
import ChatTab from '@/components/tabs/ChatTab';
import ErrorBoundary from '@/components/ErrorBoundary';
import { systemApi } from '@/lib/api';

// 자주 쓰는 탭(Chat, Agents)은 항상 마운트 유지 — 탭 전환 시 로딩 없음
// 나머지 탭은 lazy load (ssr: false — 클라이언트 전용)
const ProjectsTab = dynamic(() => import('@/components/tabs/ProjectsTab'), { ssr: false });
const AgentsTab = dynamic(() => import('@/components/tabs/AgentsTab'), { ssr: false });
const MemoryTab = dynamic(() => import('@/components/tabs/MemoryTab'), { ssr: false });
const LogsTab = dynamic(() => import('@/components/tabs/LogsTab'), { ssr: false });
const ToolsTab = dynamic(() => import('@/components/tabs/ToolsTab'), { ssr: false });
const NotesTab = dynamic(() => import('@/components/tabs/NotesTab'), { ssr: false });
const SettingsTab = dynamic(() => import('@/components/tabs/SettingsTab'), { ssr: false });
const CompanyChat = dynamic(() => import('@/components/tabs/CompanyChat'), { ssr: false });

export default function Home() {
  const { activeTab, setActiveTab, loadSystemStatus, loadAgents, loadPersonas } = useAppStore();

  useEffect(() => {
    // URL 해시로 초기 탭 설정 (예: #agents, #settings)
    const hash = window.location.hash.slice(1);
    const validTabs = ['chat', 'projects', 'agents', 'memory', 'logs', 'tools', 'notes', 'settings', 'channel'] as const;
    if (hash && validTabs.includes(hash as typeof validTabs[number])) {
      setActiveTab(hash as typeof validTabs[number]);
    }

    // 초기 데이터 로드 (각 탭이 자체 갱신을 담당)
    loadPersonas();   // 페르소나 맵 동기화 (백엔드 → 프론트 단일 소스)
    loadSystemStatus();
    loadAgents();

    // 브라우저 탭 타이틀에 버전 표시
    systemApi.getInfo().then(info => {
      if (info.version) document.title = `JINXUS - v${info.version}`;
    }).catch(() => {});
  }, [setActiveTab, loadSystemStatus, loadAgents, loadPersonas]);

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header />
        <main className="flex-1 overflow-auto p-3 sm:p-4 md:p-6 pt-12 sm:pt-14 md:pt-6">
          {/* 항상 마운트 유지 — 탭 전환 시 즉시 표시 */}
          <div className={activeTab === 'chat' ? 'h-full overflow-hidden' : 'hidden'}>
            <ErrorBoundary><ChatTab /></ErrorBoundary>
          </div>
          <div className={activeTab === 'agents' ? 'h-full overflow-hidden' : 'hidden'}>
            <ErrorBoundary><AgentsTab isActive={activeTab === 'agents'} /></ErrorBoundary>
          </div>
          {/* 나머지 탭은 필요할 때만 마운트 */}
          {activeTab === 'projects' && <ErrorBoundary key="projects"><ProjectsTab /></ErrorBoundary>}
          {activeTab === 'memory' && <ErrorBoundary key="memory"><MemoryTab /></ErrorBoundary>}
          {activeTab === 'logs' && <ErrorBoundary key="logs"><LogsTab /></ErrorBoundary>}
          {activeTab === 'tools' && <ErrorBoundary key="tools"><ToolsTab /></ErrorBoundary>}
          {activeTab === 'notes' && <ErrorBoundary key="notes"><NotesTab /></ErrorBoundary>}
          {activeTab === 'settings' && <ErrorBoundary key="settings"><SettingsTab isActive /></ErrorBoundary>}
          {activeTab === 'channel' && <div className="h-full overflow-hidden"><ErrorBoundary key="channel"><CompanyChat isActive={activeTab === 'channel'} /></ErrorBoundary></div>}
        </main>
      </div>
    </div>
  );
}
