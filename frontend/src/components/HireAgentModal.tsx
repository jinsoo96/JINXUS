'use client';

import { useState, useEffect } from 'react';
import { X, UserPlus, Loader2 } from 'lucide-react';
import { hrApi, type AvailableSpec } from '@/lib/api';

interface HireAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onHired: () => void;
}

export default function HireAgentModal({ isOpen, onClose, onHired }: HireAgentModalProps) {
  const [specs, setSpecs] = useState<AvailableSpec[]>([]);
  const [selectedSpec, setSelectedSpec] = useState<string>('');
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');
  const [role, setRole] = useState<'senior' | 'junior' | 'intern'>('senior');
  const [loading, setLoading] = useState(false);
  const [specsLoading, setSpecsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchSpecs();
    }
  }, [isOpen]);

  const fetchSpecs = async () => {
    try {
      setSpecsLoading(true);
      const data = await hrApi.getAvailableSpecs();
      setSpecs(data.specs);
      if (data.specs.length > 0) {
        setSelectedSpec(data.specs[0].specialty);
      }
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

      await hrApi.hireAgent({
        specialty: selectedSpec,
        name: customName || undefined,
        description: customDescription || undefined,
      });

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
    setError(null);
  };

  const selectedSpecData = specs.find(s => s.specialty === selectedSpec);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-dark-card border border-dark-border rounded-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-dark-border">
          <div className="flex items-center gap-2">
            <UserPlus size={20} className="text-primary" />
            <h2 className="text-lg font-semibold">새 에이전트 고용</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-zinc-800 rounded transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {specsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
            </div>
          ) : (
            <>
              {/* Specialty Selection */}
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
              </div>

              {/* Selected Spec Info */}
              {selectedSpecData && (
                <div className="p-3 bg-zinc-900/50 rounded-lg">
                  <p className="text-sm text-zinc-400 mb-2">
                    {selectedSpecData.description}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {selectedSpecData.capabilities.map((cap, i) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-0.5 bg-zinc-800 rounded text-zinc-300"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Role Selection */}
              <div>
                <label className="block text-sm font-medium mb-2">직급</label>
                <div className="flex gap-2">
                  {[
                    { value: 'senior', label: 'Senior', color: 'blue' },
                    { value: 'junior', label: 'Junior', color: 'green' },
                    { value: 'intern', label: 'Intern', color: 'zinc' },
                  ].map((r) => (
                    <button
                      key={r.value}
                      onClick={() => setRole(r.value as typeof role)}
                      className={`flex-1 px-3 py-2 rounded-lg border text-sm transition-colors ${
                        role === r.value
                          ? `bg-${r.color}-500/20 border-${r.color}-500 text-${r.color}-400`
                          : 'bg-zinc-900 border-dark-border text-zinc-400 hover:border-zinc-600'
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Name */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  이름 (선택)
                </label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="JX_CUSTOM_NAME"
                  className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600"
                />
                <p className="text-xs text-zinc-500 mt-1">
                  비워두면 자동으로 생성됩니다.
                </p>
              </div>

              {/* Custom Description */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  설명 (선택)
                </label>
                <textarea
                  value={customDescription}
                  onChange={(e) => setCustomDescription(e.target.value)}
                  placeholder="이 에이전트의 역할을 설명합니다..."
                  rows={3}
                  className="w-full bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-zinc-600 resize-none"
                />
              </div>

              {/* Error */}
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-dark-border">
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
              <>
                <Loader2 size={14} className="animate-spin" />
                고용 중...
              </>
            ) : (
              <>
                <UserPlus size={14} />
                고용하기
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
