import React, { useMemo } from 'react';
import { 
  CheckCircle2, AlertTriangle, XCircle, 
  Sparkles
} from 'lucide-react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';
import AuditTable from './AuditTable';

interface AuditPanelProps {
  sentences: VerifiedSentence[];
  documents: SupportingDocument[];
  activeSentenceId: number | null;
  onSentenceClick: (sentence: VerifiedSentence) => void;
  onApprove?: (id: number) => void;
  onReject?: (id: number) => void;
  onSentenceUpdate?: (id: number, updates: Partial<VerifiedSentence>) => void;
  onSentenceDelete?: (id: number) => void;
}

const AuditPanel: React.FC<AuditPanelProps> = ({
  sentences,
  documents,
  activeSentenceId,
  onSentenceClick,
  onSentenceUpdate,
  onSentenceDelete,
}) => {
  const analyzedSentences = useMemo(() => 
    sentences.filter(s => s.status !== VerificationStatus.PENDING),
    [sentences]
  );

  const stats = useMemo(() => ({
    total: analyzedSentences.length,
    verified: analyzedSentences.filter(s => s.status === VerificationStatus.VERIFIED).length,
    partial: analyzedSentences.filter(s => s.status === VerificationStatus.PARTIAL).length,
    unverified: analyzedSentences.filter(s => s.status === VerificationStatus.UNVERIFIED).length,
  }), [analyzedSentences]);

  if (analyzedSentences.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center">
        <div className="w-20 h-20 bg-slate-50 rounded-2xl flex items-center justify-center mb-6 border border-slate-100">
          <Sparkles className="w-10 h-10 text-slate-300" />
        </div>
        <h3 className="text-slate-900 font-semibold text-lg tracking-tight">No Analysis Results</h3>
        <p className="text-sm text-slate-500 mt-3 max-w-[300px] leading-relaxed">
          Run the audit to see verification results for each claim in the document.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Stats Header */}
      <div className="flex-shrink-0 px-6 py-2 border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-bold text-lg text-slate-900 tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-500" />
            IPO Verification Audit
          </h2>
          <span className="text-xs font-mono text-slate-400 bg-slate-100 px-2.5 py-1 rounded-md">
            {stats.total} claims
          </span>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-emerald-50 rounded-xl p-1 border border-emerald-100">
            <div className="flex items-center gap-1 mb-0.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              <span className="text-xs font-semibold text-emerald-700">Verified</span>
            </div>
            <div className="flex items-end justify-between">
              <span className="text-2xl font-bold text-emerald-900">{stats.verified}</span>
              <span className="text-xs font-medium text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded">
                {stats.total > 0 ? Math.round((stats.verified / stats.total) * 100) : 0}%
              </span>
            </div>
          </div>
          
          <div className="bg-amber-50 rounded-xl p-1 border border-amber-100">
            <div className="flex items-center gap-1 mb-0.5">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span className="text-xs font-semibold text-amber-700">Partial</span>
            </div>
            <div className="flex items-end justify-between">
              <span className="text-2xl font-bold text-amber-900">{stats.partial}</span>
              <span className="text-xs font-medium text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded">
                {stats.total > 0 ? Math.round((stats.partial / stats.total) * 100) : 0}%
              </span>
            </div>
          </div>
          
          <div className="bg-rose-50 rounded-xl p-1 border border-rose-100">
            <div className="flex items-center gap-1 mb-0.5">
              <XCircle className="w-4 h-4 text-rose-500" />
              <span className="text-xs font-semibold text-rose-700">Risks</span>
            </div>
            <div className="flex items-end justify-between">
              <span className="text-2xl font-bold text-rose-900">{stats.unverified}</span>
              <span className="text-xs font-medium text-rose-600 bg-rose-100 px-1.5 py-0.5 rounded">
                {stats.total > 0 ? Math.round((stats.unverified / stats.total) * 100) : 0}%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <AuditTable
        sentences={analyzedSentences}
        documents={documents}
        activeSentenceId={activeSentenceId}
        onSentenceClick={onSentenceClick}
        onSentenceUpdate={onSentenceUpdate}
        onSentenceDelete={onSentenceDelete}
      />
    </div>
  );
};

export default AuditPanel;
