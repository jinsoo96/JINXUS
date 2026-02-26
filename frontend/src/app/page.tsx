'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';
import ChatTab from '@/components/tabs/ChatTab';
import AgentsTab from '@/components/tabs/AgentsTab';
import MemoryTab from '@/components/tabs/MemoryTab';
import LogsTab from '@/components/tabs/LogsTab';
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
      case 'chat':
        return <ChatTab />;
      case 'agents':
        return <AgentsTab />;
      case 'memory':
        return <MemoryTab />;
      case 'logs':
        return <LogsTab />;
      case 'settings':
        return <SettingsTab />;
      default:
        return <ChatTab />;
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
