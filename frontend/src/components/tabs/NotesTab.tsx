'use client';

import { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { devNotesApi, type DevNote } from '@/lib/api';
import {
  FileText, Plus, Trash2, Edit3, Check, X,
  RefreshCw, Loader2, Calendar, Clock,
} from 'lucide-react';
import toast from 'react-hot-toast';

// 새 노트 기본 템플릿
const DEFAULT_TEMPLATE = (title: string) => `# ${title}

**날짜:** ${new Date().toISOString().slice(0, 10)}
**작업자:** 직접 작성

## 작업 내용

(여기에 내용 작성)

## 변경 파일

-
`;

export default function NotesTab() {
  const [notes, setNotes] = useState<DevNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNote, setSelectedNote] = useState<DevNote | null>(null);
  const [noteLoading, setNoteLoading] = useState(false);

  // 편집 모드
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);

  // 새 노트 생성
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const loadNotes = useCallback(async () => {
    try {
      const res = await devNotesApi.list();
      setNotes(res.notes);
    } catch (e) {
      console.error('노트 목록 로드 실패:', e);
      toast.error('노트 목록 로드 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNotes();
  }, [loadNotes]);

  const handleSelect = async (id: string) => {
    if (selectedId === id) return;
    setSelectedId(id);
    setEditMode(false);
    setNoteLoading(true);
    try {
      const note = await devNotesApi.get(id);
      setSelectedNote(note);
      setEditContent(note.content || '');
    } catch (e) {
      console.error('노트 로드 실패:', e);
      toast.error('노트 로드 실패');
    } finally {
      setNoteLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const updated = await devNotesApi.update(selectedId, editContent);
      setSelectedNote({ ...updated, content: editContent });
      setNotes(prev => prev.map(n => n.id === selectedId ? { ...n, ...updated } : n));
      setEditMode(false);
      toast.success('저장됨');
    } catch (e) {
      console.error('노트 저장 실패:', e);
      toast.error('저장 실패');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('이 노트를 삭제하시겠습니까?')) return;
    try {
      await devNotesApi.delete(id);
      setNotes(prev => prev.filter(n => n.id !== id));
      if (selectedId === id) {
        setSelectedId(null);
        setSelectedNote(null);
      }
      toast.success('삭제됨');
    } catch (e) {
      console.error('노트 삭제 실패:', e);
      toast.error('삭제 실패');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const content = DEFAULT_TEMPLATE(newTitle.trim());
      const note = await devNotesApi.create(newTitle.trim(), content);
      setNotes(prev => [note, ...prev]);
      setShowCreate(false);
      setNewTitle('');
      // 생성 즉시 선택 + 편집 모드
      setSelectedId(note.id);
      setSelectedNote({ ...note, content });
      setEditContent(content);
      setEditMode(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '생성 실패';
      toast.error(msg);
    } finally {
      setCreating(false);
    }
  };

  const formatDate = (s: string) => {
    if (!s) return '';
    try { return new Date(s).toLocaleDateString('ko-KR'); } catch { return s; }
  };

  return (
    <div className="h-full flex gap-4 min-h-0">

      {/* ── 왼쪽: 노트 목록 ── */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-3">

        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-zinc-300">
            개발 노트 ({notes.length})
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={loadNotes}
              className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
              title="새로고침"
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1 px-2 py-1 bg-primary hover:bg-primary/90 text-black rounded text-[11px] font-medium transition-colors"
            >
              <Plus size={11} />
              새 노트
            </button>
          </div>
        </div>

        {/* 노트 목록 */}
        <div className="flex-1 overflow-y-auto border border-dark-border rounded-xl divide-y divide-dark-border">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 size={20} className="animate-spin text-zinc-500" />
            </div>
          ) : notes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-2 text-zinc-600">
              <FileText size={28} />
              <p className="text-xs">노트 없음</p>
            </div>
          ) : (
            notes.map(note => (
              <div
                key={note.id}
                onClick={() => handleSelect(note.id)}
                className={`px-3 py-2.5 cursor-pointer transition-colors relative group ${
                  selectedId === note.id
                    ? 'bg-primary/10 border-l-2 border-l-primary'
                    : 'hover:bg-zinc-800/40 border-l-2 border-l-transparent'
                }`}
              >
                <p className="text-sm font-medium text-zinc-200 truncate pr-6">{note.title}</p>
                {note.date && (
                  <p className="text-[10px] text-zinc-500 flex items-center gap-1 mt-0.5">
                    <Calendar size={9} />
                    {note.date}
                  </p>
                )}
                {note.summary && (
                  <p className="text-[10px] text-zinc-600 truncate mt-0.5">{note.summary}</p>
                )}
                {/* 삭제 버튼 */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(note.id); }}
                  className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/20 text-zinc-500 hover:text-red-400 transition-all"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* 새 노트 생성 모달 */}
        {showCreate && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-dark-card border border-dark-border rounded-2xl p-5 w-80">
              <h3 className="text-sm font-semibold mb-3">새 노트</h3>
              <form onSubmit={handleCreate} className="space-y-3">
                <input
                  autoFocus
                  type="text"
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  placeholder="노트 제목..."
                  className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => { setShowCreate(false); setNewTitle(''); }}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-dark-border hover:bg-zinc-800 text-sm transition-colors"
                  >
                    취소
                  </button>
                  <button
                    type="submit"
                    disabled={!newTitle.trim() || creating}
                    className="flex-1 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-black text-sm font-medium transition-colors disabled:opacity-50"
                  >
                    {creating ? <Loader2 size={14} className="animate-spin mx-auto" /> : '생성'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>

      {/* ── 오른쪽: 노트 뷰어/편집기 ── */}
      <div className="flex-1 flex flex-col min-h-0 border border-dark-border rounded-xl overflow-hidden">
        {!selectedNote ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <FileText size={40} className="mx-auto mb-3 text-zinc-700" />
              <p className="text-sm text-zinc-500">노트를 선택하거나</p>
              <p className="text-sm text-zinc-500">새 노트를 만드세요</p>
            </div>
          </div>
        ) : noteLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 size={24} className="animate-spin text-zinc-500" />
          </div>
        ) : (
          <>
            {/* 헤더 */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-dark-border bg-zinc-900/60 flex-shrink-0">
              <div className="flex-1 min-w-0">
                <h2 className="text-sm font-semibold text-white truncate">{selectedNote.title}</h2>
                <div className="flex items-center gap-3 mt-0.5">
                  {selectedNote.date && (
                    <span className="text-[10px] text-zinc-500 flex items-center gap-1">
                      <Calendar size={9} />
                      {selectedNote.date}
                    </span>
                  )}
                  <span className="text-[10px] text-zinc-600 flex items-center gap-1">
                    <Clock size={9} />
                    {formatDate(selectedNote.modified_at)}
                  </span>
                  <span className="text-[10px] text-zinc-600 font-mono">{selectedNote.filename}</span>
                </div>
              </div>
              {/* 편집/저장 버튼 */}
              <div className="flex items-center gap-1.5 ml-3">
                {editMode ? (
                  <>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="flex items-center gap-1 px-2.5 py-1.5 bg-primary/80 hover:bg-primary text-black rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                      저장
                    </button>
                    <button
                      onClick={() => { setEditMode(false); setEditContent(selectedNote.content || ''); }}
                      className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setEditMode(true)}
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded-lg text-xs transition-colors"
                  >
                    <Edit3 size={12} />
                    편집
                  </button>
                )}
              </div>
            </div>

            {/* 본문 */}
            {editMode ? (
              <textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                className="flex-1 bg-zinc-900/40 p-5 font-mono text-sm text-zinc-200 resize-none focus:outline-none"
                spellCheck={false}
              />
            ) : (
              <div className="flex-1 overflow-y-auto p-5">
                <div className="prose prose-invert prose-sm max-w-none
                  prose-headings:text-zinc-100
                  prose-p:text-zinc-300 prose-p:leading-relaxed
                  prose-a:text-primary
                  prose-strong:text-zinc-200
                  prose-code:text-primary prose-code:bg-zinc-800/80 prose-code:px-1 prose-code:rounded
                  prose-pre:bg-zinc-900 prose-pre:border prose-pre:border-zinc-700
                  prose-blockquote:border-l-primary prose-blockquote:text-zinc-400
                  prose-table:text-sm
                  prose-th:text-zinc-300 prose-td:text-zinc-400
                  prose-li:text-zinc-300
                  prose-hr:border-zinc-700
                ">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {selectedNote.content || ''}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
