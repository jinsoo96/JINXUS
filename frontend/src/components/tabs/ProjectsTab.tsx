'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { projectApi, type ProjectDetail, type ProjectPhase } from '@/lib/api';
import toast from 'react-hot-toast';
import {
  FolderKanban, Plus, Play, Square, Trash2, RefreshCw,
  CheckCircle, XCircle, Clock, Loader2, ChevronDown,
  ChevronRight, Pencil, ArrowRight, AlertCircle,
  PanelBottomClose, PanelBottomOpen, Terminal,
} from 'lucide-react';
import DockerLogPanel from '@/components/DockerLogPanel';

// 페이즈 상태 색상
const PHASE_STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  pending:   { color: 'text-zinc-400', bg: 'bg-zinc-700',       label: '대기' },
  waiting:   { color: 'text-amber-400', bg: 'bg-amber-500/20',  label: '의존성 대기' },
  running:   { color: 'text-blue-400', bg: 'bg-blue-500/20',    label: '실행 중' },
  completed: { color: 'text-green-400', bg: 'bg-green-500/20',  label: '완료' },
  failed:    { color: 'text-red-400', bg: 'bg-red-500/20',      label: '실패' },
  cancelled: { color: 'text-zinc-500', bg: 'bg-zinc-800',       label: '취소' },
};

const PROJECT_STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  planning:  { color: 'text-amber-400',  label: '계획 중' },
  ready:     { color: 'text-blue-400',   label: '준비 완료' },
  running:   { color: 'text-green-400',  label: '실행 중' },
  paused:    { color: 'text-amber-400',  label: '일시정지' },
  completed: { color: 'text-green-400',  label: '완료' },
  failed:    { color: 'text-red-400',    label: '실패' },
  cancelled: { color: 'text-zinc-500',   label: '취소' },
};

export default function ProjectsTab() {
  const [projects, setProjects] = useState<ProjectDetail[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [input, setInput] = useState('');
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());
  const [editingPhase, setEditingPhase] = useState<string | null>(null);
  const [editInput, setEditInput] = useState('');
  const streamRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 하단 Docker 로그 패널
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(700);
  const isDraggingRef = useRef(false);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    dragStartYRef.current = e.clientY;
    dragStartHeightRef.current = bottomPanelHeight;

    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = dragStartYRef.current - ev.clientY;
      const newHeight = Math.max(120, Math.min(900, dragStartHeightRef.current + delta));
      setBottomPanelHeight(newHeight);
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [bottomPanelHeight]);

  // 프로젝트 목록 로드
  const loadProjects = useCallback(async () => {
    try {
      const list = await projectApi.list();
      setProjects(list);
      // 선택된 프로젝트 갱신
      if (selectedProject) {
        const updated = list.find(p => p.id === selectedProject.id);
        if (updated) setSelectedProject(updated);
        else setSelectedProject(null);
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedProject?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadProjects();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (streamRef.current) streamRef.current.abort();
    };
  }, []);

  // 선택된 프로젝트가 실행 중이면 폴링
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);

    if (selectedProject && selectedProject.status === 'running') {
      pollRef.current = setInterval(async () => {
        try {
          const updated = await projectApi.get(selectedProject.id);
          setSelectedProject(updated);
          setProjects(prev => prev.map(p => p.id === updated.id ? updated : p));
        } catch { /* ignore */ }
      }, 5000);
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [selectedProject?.id, selectedProject?.status]);

  // 프로젝트 생성
  const handleCreate = async () => {
    if (!input.trim() || creating) return;

    setCreating(true);
    try {
      const project = await projectApi.create(input.trim());
      setProjects(prev => [project, ...prev]);
      setSelectedProject(project);
      setInput('');
      toast.success(`프로젝트 생성: ${project.title} (${project.phases.length}개 페이즈)`);
    } catch (error) {
      toast.error(`프로젝트 생성 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`);
    } finally {
      setCreating(false);
    }
  };

  // 프로젝트 실행
  const handleStart = async (projectId: string) => {
    try {
      await projectApi.start(projectId);
      const updated = await projectApi.get(projectId);
      setSelectedProject(updated);
      setProjects(prev => prev.map(p => p.id === projectId ? updated : p));
      toast.success('프로젝트 실행 시작');
    } catch (error) {
      toast.error(`실행 실패: ${error instanceof Error ? error.message : '오류'}`);
    }
  };

  // 프로젝트 중단
  const handleStop = async (projectId: string) => {
    if (!confirm('프로젝트를 중단하시겠습니까? 모든 데이터가 삭제됩니다.')) return;

    try {
      await projectApi.stop(projectId);
      setProjects(prev => prev.filter(p => p.id !== projectId));
      if (selectedProject?.id === projectId) setSelectedProject(null);
      toast.success('프로젝트 중단 및 정리 완료');
    } catch (error) {
      toast.error(`중단 실패: ${error instanceof Error ? error.message : '오류'}`);
    }
  };

  // 프로젝트 삭제
  const handleDelete = async (projectId: string) => {
    if (!confirm('프로젝트를 삭제하시겠습니까?')) return;

    try {
      await projectApi.delete(projectId);
      setProjects(prev => prev.filter(p => p.id !== projectId));
      if (selectedProject?.id === projectId) setSelectedProject(null);
      toast.success('프로젝트 삭제 완료');
    } catch (error) {
      toast.error(`삭제 실패: ${error instanceof Error ? error.message : '오류'}`);
    }
  };

  // 페이즈 지시 수정
  const handlePhaseUpdate = async (projectId: string, phaseId: string) => {
    if (!editInput.trim()) return;

    try {
      await projectApi.updatePhase(projectId, phaseId, editInput.trim());
      const updated = await projectApi.get(projectId);
      setSelectedProject(updated);
      setProjects(prev => prev.map(p => p.id === projectId ? updated : p));
      setEditingPhase(null);
      toast.success('페이즈 지시 수정 완료');
    } catch (error) {
      toast.error(`수정 실패: ${error instanceof Error ? error.message : '오류'}`);
    }
  };

  // 진행률 계산
  const getProgress = (project: ProjectDetail) => {
    if (project.phases.length === 0) return 0;
    const completed = project.phases.filter(p => p.status === 'completed').length;
    return Math.round((completed / project.phases.length) * 100);
  };

  // 페이즈 접기/펼치기
  const togglePhase = (phaseId: string) => {
    setExpandedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phaseId)) next.delete(phaseId);
      else next.add(phaseId);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <FolderKanban className="w-5 h-5" />프로젝트
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={loadProjects} className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors">
            <RefreshCw size={16} />
          </button>
          <button
            onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              bottomPanelOpen
                ? 'bg-zinc-700 text-zinc-200'
                : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
            }`}
            title={bottomPanelOpen ? '패널 닫기' : '패널 열기'}
          >
            {bottomPanelOpen ? <PanelBottomClose size={14} /> : <PanelBottomOpen size={14} />}
          </button>
        </div>
      </div>

      {/* 프로젝트 생성 */}
      <div className="flex gap-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="프로젝트 지시를 입력하세요... (예: 블로그 풀스택 앱 만들어)"
          rows={2}
          className="flex-1 bg-dark-card border border-dark-border rounded-xl px-4 py-3 focus:outline-none focus:border-primary transition-colors resize-none text-sm"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleCreate();
            }
          }}
        />
        <button
          onClick={handleCreate}
          disabled={!input.trim() || creating}
          className="px-5 py-3 bg-primary hover:bg-primary-hover rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed self-end flex items-center gap-2"
        >
          {creating ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
          생성
        </button>
      </div>

      {/* 본문: 좌우 분할 */}
      <div className={`flex gap-4 min-h-0 ${bottomPanelOpen ? '' : 'flex-1'}`} style={bottomPanelOpen ? { flex: '1 1 0', minHeight: 0 } : undefined}>
        {/* 왼쪽: 프로젝트 목록 */}
        <div className="w-80 flex-shrink-0 bg-dark-card border border-dark-border rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-dark-border text-sm font-semibold text-zinc-400">
            프로젝트 ({projects.length})
          </div>
          <div className="flex-1 overflow-y-auto">
            {projects.length === 0 ? (
              <div className="p-8 text-center text-zinc-600 text-sm">
                프로젝트가 없습니다
              </div>
            ) : (
              projects.map(project => {
                const progress = getProgress(project);
                const statusCfg = PROJECT_STATUS_CONFIG[project.status] || PROJECT_STATUS_CONFIG.ready;
                const isSelected = selectedProject?.id === project.id;

                return (
                  <button
                    key={project.id}
                    onClick={() => setSelectedProject(project)}
                    className={`w-full text-left px-4 py-3 border-b border-dark-border/50 transition-colors ${
                      isSelected ? 'bg-primary/10 border-l-2 border-l-primary' : 'hover:bg-zinc-800/50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate flex-1">{project.title || '제목 없음'}</span>
                      <span className={`text-[10px] font-mono ${statusCfg.color}`}>{statusCfg.label}</span>
                    </div>
                    <p className="text-xs text-zinc-500 truncate mb-2">{project.description.slice(0, 60)}</p>
                    {/* 진행률 바 */}
                    <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          project.status === 'failed' ? 'bg-red-500/60' :
                          project.status === 'completed' ? 'bg-green-500/60' : 'bg-primary/60'
                        }`}
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[10px] text-zinc-600">{project.phases.length}개 페이즈</span>
                      <span className="text-[10px] text-zinc-600">{progress}%</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* 오른쪽: 프로젝트 상세 */}
        <div className="flex-1 flex flex-col min-w-0">
          {!selectedProject ? (
            <div className="flex-1 flex items-center justify-center text-zinc-600">
              <div className="text-center">
                <FolderKanban className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p>프로젝트를 선택하거나 새로 생성하세요</p>
              </div>
            </div>
          ) : (
            <>
              {/* 프로젝트 헤더 */}
              <div className="bg-dark-card border border-dark-border rounded-xl p-4 mb-3">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-lg font-bold">{selectedProject.title}</h2>
                  <div className="flex items-center gap-2">
                    {selectedProject.status === 'ready' && (
                      <button
                        onClick={() => handleStart(selectedProject.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-sm transition-colors"
                      >
                        <Play size={14} /> 실행
                      </button>
                    )}
                    {selectedProject.status === 'running' && (
                      <button
                        onClick={() => handleStop(selectedProject.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-sm transition-colors"
                      >
                        <Square size={14} /> 중단
                      </button>
                    )}
                    {['completed', 'failed', 'cancelled'].includes(selectedProject.status) && (
                      <button
                        onClick={() => handleDelete(selectedProject.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors"
                      >
                        <Trash2 size={14} /> 삭제
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-sm text-zinc-400 mb-3">{selectedProject.description}</p>

                {/* 전체 진행률 */}
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        selectedProject.status === 'failed' ? 'bg-red-500' :
                        selectedProject.status === 'completed' ? 'bg-green-500' : 'bg-primary'
                      }`}
                      style={{ width: `${getProgress(selectedProject)}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono text-zinc-400">
                    {selectedProject.phases.filter(p => p.status === 'completed').length}/{selectedProject.phases.length}
                  </span>
                </div>

                {selectedProject.total_duration_s > 0 && (
                  <p className="text-xs text-zinc-500 mt-2">
                    소요 시간: {selectedProject.total_duration_s < 60
                      ? `${Math.round(selectedProject.total_duration_s)}초`
                      : `${Math.round(selectedProject.total_duration_s / 60)}분`}
                  </p>
                )}
              </div>

              {/* 페이즈 목록 */}
              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {selectedProject.phases.map((phase, idx) => {
                  const statusCfg = PHASE_STATUS_CONFIG[phase.status] || PHASE_STATUS_CONFIG.pending;
                  const isExpanded = expandedPhases.has(phase.id);
                  const isEditing = editingPhase === phase.id;
                  const canEdit = ['pending', 'waiting'].includes(phase.status) &&
                                  ['ready', 'running'].includes(selectedProject.status);

                  return (
                    <div
                      key={phase.id}
                      className={`bg-dark-card border rounded-xl overflow-hidden transition-colors ${
                        phase.status === 'running' ? 'border-blue-500/40' :
                        phase.status === 'completed' ? 'border-green-500/20' :
                        phase.status === 'failed' ? 'border-red-500/30' :
                        'border-dark-border'
                      }`}
                    >
                      {/* 페이즈 헤더 */}
                      <button
                        onClick={() => togglePhase(phase.id)}
                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/30 transition-colors"
                      >
                        <span className="text-zinc-500 text-xs font-mono w-6">{idx + 1}</span>

                        {/* 상태 아이콘 */}
                        {phase.status === 'running' ? (
                          <Loader2 size={16} className="text-blue-400 animate-spin flex-shrink-0" />
                        ) : phase.status === 'completed' ? (
                          <CheckCircle size={16} className="text-green-400 flex-shrink-0" />
                        ) : phase.status === 'failed' ? (
                          <XCircle size={16} className="text-red-400 flex-shrink-0" />
                        ) : phase.status === 'waiting' ? (
                          <Clock size={16} className="text-amber-400 flex-shrink-0" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-zinc-600 flex-shrink-0" />
                        )}

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium truncate">{phase.name}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${statusCfg.bg} ${statusCfg.color}`}>
                              {statusCfg.label}
                            </span>
                            <span className="text-[10px] text-zinc-600 font-mono">{phase.agent}</span>
                          </div>
                        </div>

                        {/* 의존성 표시 */}
                        {phase.depends_on.length > 0 && (
                          <span className="text-[9px] text-zinc-600 flex items-center gap-0.5">
                            <ArrowRight size={10} />
                            {phase.depends_on.length}개 의존
                          </span>
                        )}

                        {isExpanded ? <ChevronDown size={14} className="text-zinc-500" /> : <ChevronRight size={14} className="text-zinc-500" />}
                      </button>

                      {/* 페이즈 상세 (확장 시) */}
                      {isExpanded && (
                        <div className="px-4 pb-3 border-t border-dark-border/50 pt-3 space-y-2">
                          {/* 지시 */}
                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-[10px] text-zinc-500 uppercase">지시</label>
                              {canEdit && !isEditing && (
                                <button
                                  onClick={() => { setEditingPhase(phase.id); setEditInput(phase.instruction); }}
                                  className="text-zinc-500 hover:text-primary transition-colors"
                                >
                                  <Pencil size={12} />
                                </button>
                              )}
                            </div>
                            {isEditing ? (
                              <div className="space-y-2">
                                <textarea
                                  value={editInput}
                                  onChange={(e) => setEditInput(e.target.value)}
                                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary resize-none"
                                  rows={3}
                                />
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => handlePhaseUpdate(selectedProject.id, phase.id)}
                                    className="px-3 py-1 bg-primary rounded text-xs"
                                  >
                                    저장
                                  </button>
                                  <button
                                    onClick={() => setEditingPhase(null)}
                                    className="px-3 py-1 bg-zinc-700 rounded text-xs"
                                  >
                                    취소
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <p className="text-xs text-zinc-300 whitespace-pre-wrap">{phase.instruction}</p>
                            )}
                          </div>

                          {/* 에러 */}
                          {phase.error && (
                            <div className="flex items-start gap-1.5 text-xs text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">
                              <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
                              <span>{phase.error}</span>
                            </div>
                          )}

                          {/* 결과 요약 */}
                          {phase.result_summary && (
                            <div>
                              <label className="text-[10px] text-zinc-500 uppercase mb-1 block">결과</label>
                              <p className="text-xs text-zinc-400 whitespace-pre-wrap max-h-40 overflow-y-auto bg-zinc-900/50 rounded-lg px-3 py-2">
                                {phase.result_summary.slice(0, 500)}
                                {phase.result_summary.length > 500 && '...'}
                              </p>
                            </div>
                          )}

                          {/* 시간 정보 */}
                          {(phase.started_at || phase.completed_at) && (
                            <div className="flex gap-4 text-[10px] text-zinc-600">
                              {phase.started_at && <span>시작: {new Date(phase.started_at).toLocaleTimeString('ko-KR', { hour12: false })}</span>}
                              {phase.completed_at && <span>완료: {new Date(phase.completed_at).toLocaleTimeString('ko-KR', { hour12: false })}</span>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 하단 Docker 로그 패널 (VSCode 터미널 스타일) */}
      {bottomPanelOpen && (
        <div className="flex-shrink-0 flex flex-col" style={{ height: bottomPanelHeight }}>
          {/* 리사이즈 핸들 */}
          <div
            className="h-1 bg-dark-border cursor-row-resize hover:bg-primary/40 active:bg-primary/60 transition-colors flex-shrink-0"
            onMouseDown={handleDragStart}
          />
          {/* 탭 바 */}
          <div className="flex items-center justify-between bg-dark-card border-b border-dark-border flex-shrink-0">
            <div className="flex">
              <button
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium border-b-2 border-primary text-zinc-200 bg-dark-bg/50"
              >
                <Terminal size={12} />
                시스템 로그
              </button>
            </div>
            <button
              onClick={() => setBottomPanelOpen(false)}
              className="p-1.5 mr-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition-colors"
              title="패널 닫기"
            >
              <ChevronDown size={14} />
            </button>
          </div>
          {/* 패널 콘텐츠 */}
          <div className="flex-1 overflow-hidden">
            <DockerLogPanel />
          </div>
        </div>
      )}
    </div>
  );
}
