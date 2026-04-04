'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { aaiApi, type InboxMessage } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  MessageSquare, Mail, Send, Loader2, RefreshCw, ChevronRight,
} from 'lucide-react';

export default function CommsPanel({ isActive }: { isActive: boolean }) {
  const { hrAgents } = useAppStore();
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [selectedAgent, setSelectedAgent] = useState('');
  const [messages, setMessages] = useState<InboxMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [msgLoading, setMsgLoading] = useState(false);

  // 보내기 폼
  const [showCompose, setShowCompose] = useState(false);
  const [compFrom, setCompFrom] = useState('JINXUS_CORE');
  const [compTo, setCompTo] = useState('');
  const [compContent, setCompContent] = useState('');
  const [sending, setSending] = useState(false);

  const loadUnread = useCallback(async () => {
    try {
      const data = await aaiApi.getAllUnread();
      setUnread(data.unread);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (isActive) loadUnread();
  }, [isActive, loadUnread]);

  const loadMessages = async (agent: string) => {
    setSelectedAgent(agent);
    setMsgLoading(true);
    try {
      const data = await aaiApi.getInbox(agent, false, 50);
      setMessages(data.messages);
    } catch { toast.error('메시지 로드 실패'); }
    finally { setMsgLoading(false); }
  };

  const handleSend = async () => {
    if (!compTo || !compContent.trim()) { toast.error('수신자와 내용을 입력하세요'); return; }
    setSending(true);
    try {
      await aaiApi.sendMessage(compFrom, compTo, compContent.trim());
      toast.success('메시지 전송 완료');
      setCompContent('');
      setShowCompose(false);
      if (selectedAgent === compTo) loadMessages(compTo);
      loadUnread();
    } catch { toast.error('전송 실패'); }
    finally { setSending(false); }
  };

  const agentList = [{ name: 'JINXUS_CORE' }, ...hrAgents.filter(a => a.name && a.name !== 'JINXUS_CORE').map(a => ({ name: a.name }))];

  return (
    <div className="flex flex-col md:flex-row gap-3 md:gap-4 min-h-[300px] md:min-h-[500px]">
      {/* 에이전트 목록 — 모바일: 가로 스크롤, 데스크톱: 세로 사이드바 */}
      <div className="md:w-52 flex-shrink-0 bg-dark-card border border-dark-border rounded-xl overflow-hidden">
        <div className="p-3 border-b border-dark-border flex items-center justify-between">
          <span className="text-xs text-zinc-500 uppercase">에이전트 인박스</span>
          <button onClick={loadUnread} className="p-2 md:p-1 rounded hover:bg-zinc-800 text-zinc-500 min-h-[44px] md:min-h-0 min-w-[44px] md:min-w-0 flex items-center justify-center">
            <RefreshCw size={12} />
          </button>
        </div>
        {/* 모바일: 가로 스크롤 pill 형태 / 데스크톱: 세로 리스트 */}
        <div className="flex md:flex-col overflow-x-auto md:overflow-x-visible md:overflow-y-auto md:max-h-[450px] gap-1 p-2 md:p-0">
          {loading ? (
            <div className="flex justify-center py-4 w-full"><Loader2 size={16} className="animate-spin text-zinc-500" /></div>
          ) : (
            agentList.map(a => {
              const count = unread[a.name] || 0;
              const isSelected = selectedAgent === a.name;
              const p = getPersona(a.name);
              return (
                <button
                  key={a.name}
                  onClick={() => loadMessages(a.name)}
                  className={`flex items-center gap-1.5 md:gap-2 px-3 py-2 md:py-2.5 md:w-full text-left transition-colors rounded-lg md:rounded-none whitespace-nowrap min-h-[44px] ${
                    isSelected ? 'bg-zinc-700/60 text-white' : 'text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  <span className="text-sm">{p?.emoji || '🤖'}</span>
                  <span className="text-sm truncate">{getDisplayName(a.name)}</span>
                  {count > 0 && (
                    <span className="px-1.5 py-0.5 text-[10px] bg-primary/20 text-primary rounded-full font-mono">{count}</span>
                  )}
                  <ChevronRight size={12} className="text-zinc-700 hidden md:block" />
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* 메시지 */}
      <div className="flex-1 bg-dark-card border border-dark-border rounded-xl overflow-hidden flex flex-col min-h-[250px]">
        <div className="p-3 border-b border-dark-border flex items-center justify-between">
          <span className="text-sm font-medium">
            {selectedAgent ? (
              <>
                {getPersona(selectedAgent)?.emoji || '🤖'} {getDisplayName(selectedAgent)} 인박스
              </>
            ) : '에이전트를 선택하세요'}
          </span>
          <button
            onClick={() => setShowCompose(!showCompose)}
            className="flex items-center gap-1 px-2.5 py-1 bg-primary/15 text-primary rounded-lg text-xs hover:bg-primary/25"
          >
            <Send size={11} /> 보내기
          </button>
        </div>

        {/* 보내기 폼 */}
        {showCompose && (
          <div className="p-3 border-b border-primary/20 bg-primary/5 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <select value={compFrom} onChange={e => setCompFrom(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-primary">
                {agentList.map(a => <option key={a.name} value={a.name}>{getDisplayName(a.name)}</option>)}
              </select>
              <select value={compTo} onChange={e => setCompTo(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-primary">
                <option value="">수신자</option>
                {agentList.map(a => <option key={a.name} value={a.name}>{getDisplayName(a.name)}</option>)}
              </select>
            </div>
            <div className="flex gap-2">
              <input value={compContent} onChange={e => setCompContent(e.target.value)}
                placeholder="메시지 내용"
                onKeyDown={e => e.key === 'Enter' && handleSend()}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-primary" />
              <button onClick={handleSend} disabled={sending}
                className="px-3 py-1.5 bg-primary text-black rounded-lg text-xs font-medium disabled:opacity-50">
                {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
              </button>
            </div>
          </div>
        )}

        {/* 메시지 목록 */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {msgLoading ? (
            <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-zinc-500" /></div>
          ) : messages.length > 0 ? (
            messages.map(msg => {
              const fromP = getPersona(msg.from_agent);
              const isIncoming = msg.to_agent === selectedAgent;
              return (
                <div key={msg.id} className={`flex ${isIncoming ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[75%] rounded-xl px-3 py-2 ${
                    isIncoming ? 'bg-zinc-800' : 'bg-primary/10'
                  }`}>
                    <div className="flex items-center gap-1 mb-0.5">
                      <span className="text-[10px]">{fromP?.emoji || '🤖'}</span>
                      <span className="text-[10px] text-zinc-500">{getDisplayName(msg.from_agent)}</span>
                      {msg.priority > 0 && <span className="text-[9px] text-red-400 font-bold">!</span>}
                    </div>
                    <p className="text-xs text-zinc-300">{msg.content}</p>
                    <span className="text-[9px] text-zinc-700 block text-right mt-0.5">
                      {new Date(msg.created_at * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' })}
                    </span>
                  </div>
                </div>
              );
            })
          ) : selectedAgent ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-600">
              <Mail size={28} />
              <p className="text-xs">메시지가 없습니다</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-600">
              <MessageSquare size={28} />
              <p className="text-xs">왼쪽에서 에이전트를 선택하세요</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
