'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useAppStore } from '@/store/useAppStore';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';
import ChatTab from '@/components/tabs/ChatTab';
import ErrorBoundary from '@/components/ErrorBoundary';

// 탭 lazy load — 첫 로드 시 ChatTab만 즉시 로드, 나머지는 필요할 때
const DashboardTab = dynamic(() => import('@/components/tabs/DashboardTab'), { ssr: false });
const GraphTab = dynamic(() => import('@/components/tabs/GraphTab'), { ssr: false });
const AgentsTab = dynamic(() => import('@/components/tabs/AgentsTab'), { ssr: false });
const MemoryTab = dynamic(() => import('@/components/tabs/MemoryTab'), { ssr: false });
const LogsTab = dynamic(() => import('@/components/tabs/LogsTab'), { ssr: false });
const ToolsTab = dynamic(() => import('@/components/tabs/ToolsTab'), { ssr: false });
const SettingsTab = dynamic(() => import('@/components/tabs/SettingsTab'), { ssr: false });

export default function Home() {
  const { activeTab, setActiveTab, loadSystemStatus, loadAgents } = useAppStore();

  useEffect(() => {
    // URL 해시로 초기 탭 설정 (예: #dashboard, #agents)
    const hash = window.location.hash.slice(1);
    const validTabs = ['dashboard', 'chat', 'graph', 'agents', 'memory', 'logs', 'tools', 'settings'] as const;
    if (hash && validTabs.includes(hash as typeof validTabs[number])) {
      setActiveTab(hash as typeof validTabs[number]);
    }

    // 초기 데이터 로드 (각 탭이 자체 갱신을 담당)
    loadSystemStatus();
    loadAgents();
  }, [setActiveTab, loadSystemStatus, loadAgents]);

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab />;
      case 'graph':
        return <GraphTab />;
      case 'agents':
        return <AgentsTab />;
      case 'memory':
        return <MemoryTab />;
      case 'logs':
        return <LogsTab />;
      case 'tools':
        return <ToolsTab />;
      case 'settings':
        return <SettingsTab />;
      default:
        return <DashboardTab />;
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header />
        <main className="flex-1 overflow-auto p-4 md:p-6 pt-14 md:pt-6">
          {/* ChatTab은 항상 마운트 — 탭 전환해도 SSE 스트리밍 유지 */}
          <div className={activeTab === 'chat' ? 'h-full' : 'hidden'}>
            <ErrorBoundary>
              <ChatTab />
            </ErrorBoundary>
          </div>
          {activeTab !== 'chat' && (
            <ErrorBoundary key={activeTab}>
              {renderTab()}
            </ErrorBoundary>
          )}
        </main>
      </div>
    </div>
  );
}
