'use client';

import { useState, useEffect, useCallback } from 'react';
import { whiteboardApi, type WhiteboardItem } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  new: { label: 'NEW', color: 'bg-emerald-500' },
  seen: { label: '발견됨', color: 'bg-blue-500' },
  claimed: { label: '작업중', color: 'bg-amber-500' },
  done: { label: '완료', color: 'bg-zinc-500' },
  archived: { label: '보관', color: 'bg-zinc-700' },
};

const TYPE_LABELS: Record<string, { label: string; icon: string }> = {
  guideline: { label: '지침', icon: '📋' },
  memo: { label: '메모', icon: '📝' },
};

export default function WhiteboardPanel() {
  const { whiteboardOpen, setWhiteboardOpen } = useAppStore();
  const [items, setItems] = useState<WhiteboardItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'all' | 'guideline' | 'memo'>('all');

  // 새 항목 추가 폼
  const [showForm, setShowForm] = useState(false);
  const [formType, setFormType] = useState<'guideline' | 'memo'>('memo');
  const [formTitle, setFormTitle] = useState('');
  const [formContent, setFormContent] = useState('');
  const [formTags, setFormTags] = useState('');

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await whiteboardApi.listAll();
      setItems(res.items);
    } catch (e) {
      console.error('[Whiteboard] 로드 실패:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (whiteboardOpen) loadItems();
  }, [whiteboardOpen, loadItems]);

  const handleCreate = async () => {
    if (!formTitle.trim() || !formContent.trim()) return;
    try {
      const tags = formTags.split(',').map(t => t.trim()).filter(Boolean);
      await whiteboardApi.createItem(formType, formTitle.trim(), formContent.trim(), tags);
      setFormTitle(''); setFormContent(''); setFormTags(''); setShowForm(false);
      loadItems();
    } catch (e) {
      console.error('[Whiteboard] 추가 실패:', e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await whiteboardApi.deleteItem(id);
      setItems(prev => prev.filter(i => i.id !== id));
    } catch (e) {
      console.error('[Whiteboard] 삭제 실패:', e);
    }
  };

  const handleStatusChange = async (id: string, status: string) => {
    try {
      await whiteboardApi.updateItem(id, { status });
      loadItems();
    } catch (e) {
      console.error('[Whiteboard] 상태 변경 실패:', e);
    }
  };

  if (!whiteboardOpen) return null;

  const filtered = tab === 'all' ? items : items.filter(i => i.type === tab);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setWhiteboardOpen(false)}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-xl w-[640px] max-h-[80vh] flex flex-col shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-700">
          <div className="flex items-center gap-2">
            <span className="text-lg">📋</span>
            <h2 className="text-zinc-100 font-semibold text-sm">Whiteboard</h2>
            <span className="text-zinc-500 text-xs">{items.length}개 항목</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
            >
              + 추가
            </button>
            <button onClick={() => setWhiteboardOpen(false)} className="text-zinc-500 hover:text-zinc-300 text-lg">&times;</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 py-2 border-b border-zinc-800">
          {(['all', 'guideline', 'memo'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                tab === t ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {t === 'all' ? '전체' : TYPE_LABELS[t].label}
              <span className="ml-1 text-zinc-600">
                {t === 'all' ? items.length : items.filter(i => i.type === t).length}
              </span>
            </button>
          ))}
        </div>

        {/* Add Form */}
        {showForm && (
          <div className="px-5 py-3 border-b border-zinc-800 bg-zinc-800/50 space-y-2">
            <div className="flex gap-2">
              <select
                value={formType}
                onChange={e => setFormType(e.target.value as 'guideline' | 'memo')}
                className="bg-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 border border-zinc-600"
              >
                <option value="memo">📝 메모</option>
                <option value="guideline">📋 지침</option>
              </select>
              <input
                value={formTitle}
                onChange={e => setFormTitle(e.target.value)}
                placeholder="제목"
                className="flex-1 bg-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 border border-zinc-600 placeholder:text-zinc-500"
              />
            </div>
            <textarea
              value={formContent}
              onChange={e => setFormContent(e.target.value)}
              placeholder="내용을 입력하세요..."
              rows={3}
              className="w-full bg-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 border border-zinc-600 placeholder:text-zinc-500 resize-none"
            />
            <div className="flex gap-2 items-center">
              <input
                value={formTags}
                onChange={e => setFormTags(e.target.value)}
                placeholder="태그 (쉼표 구분)"
                className="flex-1 bg-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 border border-zinc-600 placeholder:text-zinc-500"
              />
              <button
                onClick={handleCreate}
                disabled={!formTitle.trim() || !formContent.trim()}
                className="px-3 py-1 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-600 disabled:text-zinc-400 text-white rounded transition-colors"
              >
                등록
              </button>
            </div>
          </div>
        )}

        {/* Items List */}
        <div className="flex-1 overflow-y-auto px-5 py-2 space-y-2">
          {loading ? (
            <div className="text-zinc-500 text-xs text-center py-8">로딩 중...</div>
          ) : filtered.length === 0 ? (
            <div className="text-zinc-500 text-xs text-center py-8">
              항목이 없습니다. + 추가 버튼으로 메모나 지침을 등록하세요.
            </div>
          ) : (
            filtered.map(item => (
              <div key={item.id} className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-3 group">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs">{TYPE_LABELS[item.type]?.icon}</span>
                      <span className="text-zinc-200 text-xs font-medium truncate">{item.title}</span>
                      <span className={`px-1.5 py-0.5 text-[10px] text-white rounded ${STATUS_LABELS[item.status]?.color}`}>
                        {STATUS_LABELS[item.status]?.label}
                      </span>
                    </div>
                    <p className="text-zinc-400 text-xs leading-relaxed whitespace-pre-wrap">{item.content}</p>
                    <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
                      <span>{new Date(item.created_at).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                      {item.tags.length > 0 && (
                        <span>{item.tags.map(t => `#${t}`).join(' ')}</span>
                      )}
                      {item.discovered_by && (
                        <span>발견: {item.discovered_by}</span>
                      )}
                      {item.mission_id && (
                        <span className="text-amber-500">미션 진행중</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {item.status === 'done' && (
                      <button onClick={() => handleStatusChange(item.id, 'archived')} className="text-zinc-500 hover:text-zinc-300 text-xs" title="보관">📦</button>
                    )}
                    <button onClick={() => handleDelete(item.id)} className="text-zinc-500 hover:text-red-400 text-xs" title="삭제">🗑</button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
