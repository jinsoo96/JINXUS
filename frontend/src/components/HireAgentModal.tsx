'use client';

import { useState, useEffect } from 'react';
import { X, UserPlus, Loader2, ChevronRight } from 'lucide-react';
import { hrApi, type AvailableSpec } from '@/lib/api';

interface HireAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onHired: () => void;
}

type ModalTab = 'basic' | 'advanced' | 'prompt';

export default function HireAgentModal({ isOpen, onClose, onHired }: HireAgentModalProps) {
  const [specs, setSpecs] = useState<AvailableSpec[]>([]);
  const [selectedSpec, setSelectedSpec] = useState<string>('');
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');
  const [role, setRole] = useState<'senior' | 'junior' | 'intern'>('senior');
  const [capabilities, setCapabilities] = useState('');
  const [tools, setTools] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [activeTab, setActiveTab] = useState<ModalTab>('basic');
  const [loading, setLoading] = useState(false);
  const [specsLoading, setSpecsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) fetchSpecs();
  }, [isOpen]);

  const fetchSpecs = async () => {
    try {
      setSpecsLoading(true);
      const data = await hrApi.getAvailableSpecs();
      setSpecs(data.specs);
      if (data.specs.length > 0) setSelectedSpec(data.specs[0].specialty);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch specs');
    } finally {
      setSpecsLoading(false);
    }
  };

  const handleHire = async () => {
    if (!selectedSpec) return;
    try {
      setLoading(true);
      setError(null);

      const capList = capabilities.split(',').map(s => s.trim()).filter(Boolean);
      const toolList = tools.split(',').map(s => s.trim()).filter(Boolean);

      await hrApi.hireAgent({
        specialty: selectedSpec,
        name: customName || undefined,
        description: customDescription || undefined,
        role,
        capabilities: capList.length > 0 ? capList : undefined,
        tools: toolList.length > 0 ? toolList : undefined,
        system_prompt: systemPrompt || undefined,
      } as Parameters<typeof hrApi.hireAgent>[0]);

      onHired();
      onClose();
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to hire agent');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setSelectedSpec(specs.length > 0 ? specs[0].specialty : '');
    setCustomName('');
    setCustomDescription('');
    setRole('senior');
    setCapabilities('');
    setTools('');
    setSystemPrompt('');
    setActiveTab('basic');
    setError(null);
  };

  const selectedSpecData = specs.find(s => s.specialty === selectedSpec);

  if (!isOpen) return null;

  const tabs: { id: ModalTab; label: string }[] = [
    { id: 'basic', label: '기본 설정' },
    { id: 'advanced', label: '고급 설정' },
    { id: 'prompt', label: '시스템 프롬프트' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-dark-card border border-dark-border rounded-xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-dark-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <UserPlus size={20} className="text-primary" />
            <h2 className="text-lg font-semibold">새 에이전트 고용</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-zinc-800 rounded transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Tab Nav */}
        <div className="flex border-b border-dark-border px-4 flex-shrink-0">
          {tabs.map((tab, i) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary text-white'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {i > 0 && <ChevronRight size={12} className="text-zinc-600" />}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1">
          {specsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
            </div>
          ) : (
            <>
              {/* 기본 설정 탭 */}
              {activeTab === 'basic' && (
                <div className="space-y-5">
                  {/* 전문 분야 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">전문 분야</label>
                    <select
                      value={selectedSpec}
                      onChange={(e) => setSelectedSpec(e.target.value)}
                      className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                    >
                      {specs.map((spec) => (
                        <option key={spec.specialty} value={spec.specialty}>
                          {spec.name} ({spec.specialty})
                        </option>
                      ))}
                    </select>
                    {selectedSpecData && (
                      <div className="mt-2 p-3 bg-zinc-900/50 rounded-lg">
                        <p className="text-sm text-zinc-400 mb-2">{selectedSpecData.description}</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedSpecData.capabilities.map((cap, i) => (
                            <span key={i} className="text-xs px-2 py-0.5 bg-zinc-800 rounded text-zinc-300">
                              {cap}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 직급 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">직급</label>
                    <div className="flex gap-2">
                      {([
                        { value: 'senior', label: 'Senior', active: 'bg-blue-500/20 border-blue-500 text-blue-400' },
                        { value: 'junior', label: 'Junior', active: 'bg-green-500/20 border-green-500 text-green-400' },
                        { value: 'intern', label: 'Intern', active: 'bg-zinc-500/20 border-zinc-500 text-zinc-400' },
                      ] as const).map((r) => (
                        <button
                          key={r.value}
                          onClick={() => setRole(r.value)}
                          className={`flex-1 px-3 py-2 rounded-lg border text-sm transition-colors ${
                            role === r.value ? r.active : 'bg-zinc-900 border-dark-border text-zinc-400 hover:border-zinc-600'
                          }`}
                        >
                          {r.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 이름 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">이름 (선택)</label>
                    <input
                      type="text"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                      placeholder="JX_CUSTOM_NAME"
                      className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600"
                    />
                    <p className="text-xs text-zinc-500 mt-1">비워두면 자동으로 생성됩니다.</p>
                  </div>
                </div>
              )}

              {/* 고급 설정 탭 */}
              {activeTab === 'advanced' && (
                <div className="space-y-5">
                  {/* 설명 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">설명 (선택)</label>
                    <textarea
                      value={customDescription}
                      onChange={(e) => setCustomDescription(e.target.value)}
                      placeholder="이 에이전트의 역할을 설명합니다..."
                      rows={3}
                      className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600 resize-none"
                    />
                  </div>

                  {/* 추가 역량 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">추가 역량 (선택)</label>
                    <input
                      type="text"
                      value={capabilities}
                      onChange={(e) => setCapabilities(e.target.value)}
                      placeholder="예: web_search, code_review, data_analysis"
                      className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600"
                    />
                    <p className="text-xs text-zinc-500 mt-1">쉼표로 구분. 기본 역량에 추가됩니다.</p>
                  </div>

                  {/* 추가 도구 */}
                  <div>
                    <label className="block text-sm font-medium mb-2">추가 도구 (선택)</label>
                    <input
                      type="text"
                      value={tools}
                      onChange={(e) => setTools(e.target.value)}
                      placeholder="예: web_searcher, code_executor, github_agent"
                      className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600"
                    />
                    <p className="text-xs text-zinc-500 mt-1">쉼표로 구분. 기본 도구 외에 추가로 허용할 도구.</p>
                  </div>
                </div>
              )}

              {/* 시스템 프롬프트 탭 */}
              {activeTab === 'prompt' && (
                <div>
                  <label className="block text-sm font-medium mb-2">시스템 프롬프트 (선택)</label>
                  <p className="text-xs text-zinc-500 mb-3">
                    비워두면 전문 분야 기본 프롬프트가 사용됩니다. 직접 정의 시 기본 프롬프트를 완전히 대체합니다.
                  </p>
                  <textarea
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder={`예:\n너는 JINXUS의 전문 에이전트다.\n주어진 작업을 정확하고 신속하게 처리하라.\n...`}
                    className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600 resize-y font-mono"
                    style={{ minHeight: '240px' }}
                  />
                  <div className="flex justify-between mt-2">
                    <p className="text-xs text-zinc-600">{systemPrompt.length}자</p>
                    {systemPrompt && (
                      <button
                        onClick={() => setSystemPrompt('')}
                        className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
                      >
                        초기화
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center gap-2 p-4 border-t border-dark-border flex-shrink-0">
          <div className="flex gap-2 text-xs text-zinc-500">
            {activeTab !== 'basic' && (
              <button
                onClick={() => setActiveTab(activeTab === 'prompt' ? 'advanced' : 'basic')}
                className="hover:text-zinc-300 transition-colors"
              >
                ← 이전
              </button>
            )}
            {activeTab !== 'prompt' && (
              <button
                onClick={() => setActiveTab(activeTab === 'basic' ? 'advanced' : 'prompt')}
                className="hover:text-zinc-300 transition-colors"
              >
                다음 →
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition-colors"
            >
              취소
            </button>
            <button
              onClick={handleHire}
              disabled={loading || specsLoading || !selectedSpec}
              className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-black rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <><Loader2 size={14} className="animate-spin" />고용 중...</>
              ) : (
                <><UserPlus size={14} />고용하기</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
