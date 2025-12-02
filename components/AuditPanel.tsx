
import React, { useMemo, useState } from 'react';
import { 
  CheckCircle2, AlertTriangle, XCircle, ChevronDown, ChevronRight, 
  FileText, Quote, Sparkles, ExternalLink, Filter, LayoutGrid, List,
  Check, X, TrendingUp, TrendingDown, Minus
} from 'lucide-react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';

interface AuditPanelProps {
  sentences: VerifiedSentence[];
  documents: SupportingDocument[];
  activeSentenceId: number | null;
  onSentenceClick: (sentence: VerifiedSentence) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
}

type GroupByType = 'status' | 'source' | 'all';
type FilterType = 'all' | 'verified' | 'partial' | 'unverified';

const AuditPanel: React.FC<AuditPanelProps> = ({
  sentences,
  documents,
  activeSentenceId,
  onSentenceClick,
  onApprove,
  onReject
}) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['unverified', 'partial', 'verified']));
  const [groupBy, setGroupBy] = useState<GroupByType>('status');
  const [filter, setFilter] = useState<FilterType>('all');
  const [viewMode, setViewMode] = useState<'compact' | 'detailed'>('detailed');

  const analyzedSentences = useMemo(() => 
    sentences.filter(s => s.status !== VerificationStatus.PENDING),
    [sentences]
  );

  const filteredSentences = useMemo(() => {
    if (filter === 'all') return analyzedSentences;
    const statusMap: Record<string, VerificationStatus> = {
      'verified': VerificationStatus.VERIFIED,
      'partial': VerificationStatus.PARTIAL,
      'unverified': VerificationStatus.UNVERIFIED
    };
    return analyzedSentences.filter(s => s.status === statusMap[filter]);
  }, [analyzedSentences, filter]);

  const groupedSentences = useMemo(() => {
    const groups: Record<string, VerifiedSentence[]> = {};
    
    if (groupBy === 'status') {
      groups['unverified'] = filteredSentences.filter(s => s.status === VerificationStatus.UNVERIFIED);
      groups['partial'] = filteredSentences.filter(s => s.status === VerificationStatus.PARTIAL);
      groups['verified'] = filteredSentences.filter(s => s.status === VerificationStatus.VERIFIED);
    } else if (groupBy === 'source') {
      filteredSentences.forEach(s => {
        const sourceId = s.citationSourceId || 'No Source';
        const sourceDoc = documents.find(d => d.id === sourceId);
        const key = sourceDoc?.name || sourceId;
        if (!groups[key]) groups[key] = [];
        groups[key].push(s);
      });
    } else {
      groups['All Claims'] = filteredSentences;
    }
    
    return groups;
  }, [filteredSentences, groupBy, documents]);

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const stats = useMemo(() => ({
    total: analyzedSentences.length,
    verified: analyzedSentences.filter(s => s.status === VerificationStatus.VERIFIED).length,
    partial: analyzedSentences.filter(s => s.status === VerificationStatus.PARTIAL).length,
    unverified: analyzedSentences.filter(s => s.status === VerificationStatus.UNVERIFIED).length,
  }), [analyzedSentences]);

  const getStatusConfig = (status: VerificationStatus | string) => {
    switch (status) {
      case VerificationStatus.VERIFIED:
      case 'verified':
        return { 
          icon: <CheckCircle2 className="w-4 h-4" />, 
          text: 'text-emerald-600', 
          bg: 'bg-emerald-50', 
          border: 'border-emerald-200',
          label: 'Verified',
          ring: 'ring-emerald-500/20'
        };
      case VerificationStatus.PARTIAL:
      case 'partial':
        return { 
          icon: <AlertTriangle className="w-4 h-4" />, 
          text: 'text-amber-600', 
          bg: 'bg-amber-50', 
          border: 'border-amber-200',
          label: 'Partial',
          ring: 'ring-amber-500/20'
        };
      case VerificationStatus.UNVERIFIED:
      case 'unverified':
        return { 
          icon: <XCircle className="w-4 h-4" />, 
          text: 'text-rose-600', 
          bg: 'bg-rose-50', 
          border: 'border-rose-200',
          label: 'Unverified',
          ring: 'ring-rose-500/20'
        };
      default:
        return { 
          icon: <Sparkles className="w-4 h-4" />, 
          text: 'text-slate-500', 
          bg: 'bg-slate-50', 
          border: 'border-slate-200',
          label: status,
          ring: 'ring-slate-500/20'
        };
    }
  };

  const getGroupConfig = (groupKey: string) => {
    if (groupBy === 'status') {
      return getStatusConfig(groupKey);
    }
    return {
      icon: <FileText className="w-4 h-4" />,
      text: 'text-indigo-600',
      bg: 'bg-indigo-50',
      border: 'border-indigo-200',
      label: groupKey,
      ring: 'ring-indigo-500/20'
    };
  };

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
      <div className="flex-shrink-0 px-6 py-5 border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white">
        <div className="flex items-center justify-between mb-4">
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
          <div className="bg-emerald-50 rounded-xl p-3 border border-emerald-100">
            <div className="flex items-center gap-2 mb-1">
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
          
          <div className="bg-amber-50 rounded-xl p-3 border border-amber-100">
            <div className="flex items-center gap-2 mb-1">
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
          
          <div className="bg-rose-50 rounded-xl p-3 border border-rose-100">
            <div className="flex items-center gap-2 mb-1">
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
      <div className="flex-shrink-0 px-6 py-3 border-b border-slate-100 bg-white flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select 
            value={filter}
            onChange={(e) => setFilter(e.target.value as FilterType)}
            className="text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
          >
            <option value="all">All Claims</option>
            <option value="unverified">Risks Only</option>
            <option value="partial">Partial Only</option>
            <option value="verified">Verified Only</option>
          </select>
          
          <select 
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as GroupByType)}
            className="text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
          >
            <option value="status">Group by Status</option>
            <option value="source">Group by Source</option>
            <option value="all">No Grouping</option>
          </select>
        </div>

        <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-0.5">
          <button 
            onClick={() => setViewMode('compact')}
            className={`p-1.5 rounded-md transition-all ${viewMode === 'compact' ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-400 hover:text-slate-600'}`}
          >
            <List className="w-3.5 h-3.5" />
          </button>
          <button 
            onClick={() => setViewMode('detailed')}
            className={`p-1.5 rounded-md transition-all ${viewMode === 'detailed' ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-400 hover:text-slate-600'}`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Claims List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="p-4 space-y-3">
          {Object.entries(groupedSentences).map(([groupKey, groupSentences]) => {
            if (groupSentences.length === 0) return null;
            
            const config = getGroupConfig(groupKey);
            const isExpanded = expandedGroups.has(groupKey);
            
            return (
              <div key={groupKey} className={`rounded-xl border ${config.border} overflow-hidden`}>
                {/* Group Header */}
                <button
                  onClick={() => toggleGroup(groupKey)}
                  className={`w-full px-4 py-3 flex items-center justify-between ${config.bg} hover:brightness-95 transition-all`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`p-1.5 rounded-lg bg-white/60 ${config.text}`}>
                      {config.icon}
                    </div>
                    <span className={`text-sm font-semibold ${config.text}`}>
                      {config.label}
                    </span>
                    <span className={`text-xs font-mono ${config.text} bg-white/50 px-2 py-0.5 rounded-md`}>
                      {groupSentences.length}
                    </span>
                  </div>
                  {isExpanded ? (
                    <ChevronDown className={`w-4 h-4 ${config.text}`} />
                  ) : (
                    <ChevronRight className={`w-4 h-4 ${config.text}`} />
                  )}
                </button>

                {/* Group Content */}
                {isExpanded && (
                  <div className="bg-white divide-y divide-slate-100">
                    {groupSentences.map((sentence) => {
                      const sentenceConfig = getStatusConfig(sentence.status);
                      const sourceDoc = documents.find(d => d.id === sentence.citationSourceId);
                      const isActive = activeSentenceId === sentence.id;
                      
                      return (
                        <div 
                          key={sentence.id}
                          onClick={() => onSentenceClick(sentence)}
                          className={`p-4 cursor-pointer transition-all duration-200 ${
                            isActive 
                              ? `${sentenceConfig.bg} ring-2 ${sentenceConfig.ring} ring-inset` 
                              : 'hover:bg-slate-50'
                          }`}
                        >
                          {viewMode === 'detailed' ? (
                            <>
                              {/* Claim Text */}
                              <div className="flex items-start gap-3 mb-3">
                                <div className={`flex-shrink-0 mt-0.5 p-1 rounded ${sentenceConfig.bg} ${sentenceConfig.text}`}>
                                  {sentenceConfig.icon}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm text-slate-800 leading-relaxed font-medium">
                                    "{sentence.text}"
                                  </p>
                                </div>
                                <span className="flex-shrink-0 text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                                  #{sentence.id}
                                </span>
                              </div>

                              {/* Meta Info */}
                              <div className="flex items-center gap-4 text-xs text-slate-500 ml-9">
                                <div className="flex items-center gap-1.5">
                                  <div className={`w-1.5 h-1.5 rounded-full ${
                                    sentence.confidence && sentence.confidence > 80 ? 'bg-emerald-500' : 
                                    sentence.confidence && sentence.confidence > 50 ? 'bg-amber-500' : 'bg-rose-500'
                                  }`}></div>
                                  <span className="font-medium">{sentence.confidence || 0}% confidence</span>
                                </div>
                                {sourceDoc && (
                                  <div className="flex items-center gap-1.5">
                                    <ExternalLink className="w-3 h-3" />
                                    <span className="truncate max-w-[150px]">{sourceDoc.name}</span>
                                  </div>
                                )}
                              </div>

                              {/* AI Reasoning */}
                              {sentence.reasoning && (
                                <div className="mt-3 ml-9 p-3 bg-slate-50 rounded-lg border border-slate-100">
                                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                    <Sparkles className="w-3 h-3" />
                                    AI Reasoning
                                  </div>
                                  <p className="text-xs text-slate-600 leading-relaxed">
                                    {sentence.reasoning}
                                  </p>
                                </div>
                              )}

                              {/* Evidence Quote */}
                              {sentence.citationText && (
                                <div className="mt-3 ml-9 p-3 bg-indigo-50/50 rounded-lg border border-indigo-100/50">
                                  <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-bold text-indigo-400 uppercase tracking-wider">
                                    <Quote className="w-3 h-3" />
                                    Evidence
                                  </div>
                                  <p className="text-xs text-indigo-700 leading-relaxed italic">
                                    "{sentence.citationText}"
                                  </p>
                                </div>
                              )}

                              {/* Action Buttons */}
                              <div className="mt-3 ml-9 flex items-center gap-2">
                                <button 
                                  onClick={(e) => { e.stopPropagation(); onReject(sentence.id); }}
                                  className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg border border-slate-200 hover:border-rose-200 transition-all flex items-center gap-1.5"
                                >
                                  <X className="w-3 h-3" />
                                  Reject
                                </button>
                                <button 
                                  onClick={(e) => { e.stopPropagation(); onApprove(sentence.id); }}
                                  className="px-3 py-1.5 text-xs font-medium text-white bg-slate-800 hover:bg-indigo-600 rounded-lg transition-all flex items-center gap-1.5"
                                >
                                  <Check className="w-3 h-3" />
                                  Approve
                                </button>
                              </div>
                            </>
                          ) : (
                            /* Compact View */
                            <div className="flex items-center gap-3">
                              <div className={`flex-shrink-0 p-1 rounded ${sentenceConfig.bg} ${sentenceConfig.text}`}>
                                {sentenceConfig.icon}
                              </div>
                              <p className="flex-1 text-sm text-slate-700 truncate">{sentence.text}</p>
                              <div className="flex items-center gap-2">
                                <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                  sentence.confidence && sentence.confidence > 80 ? 'bg-emerald-100 text-emerald-700' : 
                                  sentence.confidence && sentence.confidence > 50 ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'
                                }`}>
                                  {sentence.confidence || 0}%
                                </span>
                                <button 
                                  onClick={(e) => { e.stopPropagation(); onApprove(sentence.id); }}
                                  className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-all"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button 
                                  onClick={(e) => { e.stopPropagation(); onReject(sentence.id); }}
                                  className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default AuditPanel;

