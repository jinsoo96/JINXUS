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

export default function Home() {
  const { activeTab, loadSystemStatus, loadAgents } = useAppStore();

  useEffect(() => {
    // 초기 데이터 로드
    loadSystemStatus();
    loadAgents();

    // 15초마다 상태 갱신
    const interval = setInterval(() => {
      loadSystemStatus();
    }, 15000);

    return () => clearInterval(interval);
  }, [loadSystemStatus, loadAgents]);

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab />;
      case 'chat':
        return <ChatTab />;
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
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          {renderTab()}
        </main>
      </div>
    </div>
  );
}
