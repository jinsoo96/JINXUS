'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useAppStore } from '@/store/useAppStore';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';
import ErrorBoundary from '@/components/ErrorBoundary';
import { systemApi } from '@/lib/api';

// MissionTab(Office)은 항상 마운트 (기본 탭) — 서브탭으로 근무 환경/업무 포함
const MissionTab = dynamic(() => import('@/components/tabs/MissionTab'), { ssr: false });
// 자주 쓰는 탭은 항상 마운트 유지 — 탭 전환 시 로딩 없음
const TeamTab = dynamic(() => import('@/components/tabs/TeamTab'), { ssr: false });
// 나머지 탭은 lazy load (ssr: false — 클라이언트 전용)
const ProjectsTab = dynamic(() => import('@/components/tabs/ProjectsTab'), { ssr: false });
const MemoryTab = dynamic(() => import('@/components/tabs/MemoryTab'), { ssr: false });
const LogsTab = dynamic(() => import('@/components/tabs/LogsTab'), { ssr: false });
const ToolsTab = dynamic(() => import('@/components/tabs/ToolsTab'), { ssr: false });
const NotesTab = dynamic(() => import('@/components/tabs/NotesTab'), { ssr: false });
const SettingsTab = dynamic(() => import('@/components/tabs/SettingsTab'), { ssr: false });

export default function Home() {
  const { activeTab, setActiveTab, loadSystemStatus, loadAgents, loadPersonas } = useAppStore();

  useEffect(() => {
    // URL 해시로 초기 탭 설정 (예: #mission, #team, #settings)
    const hash = window.location.hash.slice(1);
    const validTabs = ['mission', 'team', 'projects', 'memory', 'logs', 'tools', 'notes', 'settings'] as const;
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
    <div className="flex h-dvh">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header />
        <main id="main-content" className="flex-1 overflow-auto p-0 pt-12 sm:pt-14 md:pt-0">
          {/* Office (미션 + 플레이그라운드) */}
          <div className={activeTab === 'mission' ? 'h-full overflow-hidden' : 'hidden'}>
            <ErrorBoundary><MissionTab isActive={activeTab === 'mission'} /></ErrorBoundary>
          </div>
          {/* Corporation (팀 관리 + 조직도) */}
          <div className={activeTab === 'team' ? 'h-full overflow-hidden p-3 sm:p-4 md:p-6' : 'hidden'}>
            <ErrorBoundary><TeamTab isActive={activeTab === 'team'} /></ErrorBoundary>
          </div>
          {/* 나머지 탭은 필요할 때만 마운트 */}
          {activeTab === 'projects' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="projects"><ProjectsTab /></ErrorBoundary></div>}
          {activeTab === 'memory' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="memory"><MemoryTab /></ErrorBoundary></div>}
          {activeTab === 'logs' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="logs"><LogsTab /></ErrorBoundary></div>}
          {activeTab === 'tools' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="tools"><ToolsTab /></ErrorBoundary></div>}
          {activeTab === 'notes' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="notes"><NotesTab /></ErrorBoundary></div>}
          {activeTab === 'settings' && <div className="p-3 sm:p-4 md:p-6"><ErrorBoundary key="settings"><SettingsTab isActive /></ErrorBoundary></div>}
        </main>
      </div>
    </div>
  );
}
