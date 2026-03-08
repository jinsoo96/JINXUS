'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';
import DashboardTab from '@/components/tabs/DashboardTab';
import ChatTab from '@/components/tabs/ChatTab';
import GraphTab from '@/components/tabs/GraphTab';
import AgentsTab from '@/components/tabs/AgentsTab';
import MemoryTab from '@/components/tabs/MemoryTab';
import LogsTab from '@/components/tabs/LogsTab';
import ToolsTab from '@/components/tabs/ToolsTab';
import SettingsTab from '@/components/tabs/SettingsTab';
import ErrorBoundary from '@/components/ErrorBoundary';

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
