
import React, { useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Quote, ExternalLink, Sparkles, ArrowRight, FileSearch, Scale, Trash2 } from 'lucide-react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from './ui/alert-dialog';

interface RightSidebarProps {
  activeSentence: VerifiedSentence | null;
  documents: SupportingDocument[];
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onDelete?: (id: number) => void;
}

const RightSidebar: React.FC<RightSidebarProps> = ({ 
  activeSentence, 
  documents,
  onDelete,
}) => {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  if (!activeSentence) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-white p-8 text-center border-l border-slate-200/60">
        <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-6 border border-slate-100">
          <Scale className="w-8 h-8 text-slate-300" />
        </div>
        <h3 className="text-slate-900 font-semibold text-base tracking-tight">Audit Inspector</h3>
        <p className="text-sm text-slate-500 mt-3 max-w-[240px] leading-relaxed">
          Select a highlighted sentence in the document to review verification details and evidence.
        </p>
      </div>
    );
  }

  const getStatusConfig = (status: VerificationStatus) => {
    switch (status) {
      case VerificationStatus.VERIFIED:
        return { 
          icon: <CheckCircle2 className="w-5 h-5" />, 
          text: 'text-emerald-700', 
          bg: 'bg-emerald-50', 
          border: 'border-emerald-100',
          label: 'Verified Fact',
          description: 'Directly supported by evidence'
        };
      case VerificationStatus.PARTIAL:
        return { 
          icon: <AlertTriangle className="w-5 h-5" />, 
          text: 'text-amber-700', 
          bg: 'bg-amber-50', 
          border: 'border-amber-100',
          label: 'Partially Verified',
          description: 'Minor discrepancies found'
        };
      case VerificationStatus.UNVERIFIED:
        return { 
          icon: <XCircle className="w-5 h-5" />, 
          text: 'text-rose-700', 
          bg: 'bg-rose-50', 
          border: 'border-rose-100',
          label: 'Unverified Claim',
          description: 'Contradicts or lacks evidence'
        };
      default:
        return { 
          icon: <Sparkles className="w-5 h-5" />, 
          text: 'text-slate-600', 
          bg: 'bg-slate-50', 
          border: 'border-slate-100',
          label: 'Pending Analysis',
          description: 'Processing content...'
        };
    }
  };

  const config = getStatusConfig(activeSentence.status);
  const confidence = activeSentence.confidence || 0;

  // Calculate Missing Source
  const hasMissingSource = (): boolean => {
    if (activeSentence.status === VerificationStatus.UNVERIFIED) {
      let hasSource = false;
      if (activeSentence.citationSourceId) {
        hasSource = true;
      } else if (activeSentence.citationText) {
        try {
          const parsed = JSON.parse(activeSentence.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            hasSource = parsed.some((entry: { sourceId?: string }) => entry.sourceId);
          } else if (typeof parsed === 'object' && parsed.sourceId) {
            hasSource = true;
          }
        } catch {
          if (activeSentence.citationText && activeSentence.citationText.trim() !== '') {
            hasSource = false;
          }
        }
      }
      return !hasSource;
    } else {
      let hasSource = false;
      if (activeSentence.citationSourceId) {
        hasSource = true;
      } else if (activeSentence.citationText) {
        try {
          const parsed = JSON.parse(activeSentence.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            hasSource = parsed.some((entry: { sourceId?: string }) => entry.sourceId);
          } else if (typeof parsed === 'object' && parsed.sourceId) {
            hasSource = true;
          }
        } catch {
          if (activeSentence.citationText && activeSentence.citationText.trim() !== '') {
            hasSource = false;
          }
        }
      }
      return !hasSource;
    }
  };

  // Calculate Conflicting Info
  const hasConflictingInfo = (): boolean => {
    if (activeSentence.status === VerificationStatus.PARTIAL) {
      return true;
    } else if (activeSentence.status === VerificationStatus.UNVERIFIED) {
      const reasoning = activeSentence.reasoning?.toLowerCase() || '';
      return reasoning.includes('contradict') || 
             reasoning.includes('conflict') || 
             reasoning.includes('discrepanc');
    } else {
      return false;
    }
  };

  const missingSource = hasMissingSource();
  const conflictingInfo = hasConflictingInfo();

  return (
    <div className="w-full h-full flex flex-col bg-white border-l border-slate-200/60 shadow-xl shadow-slate-200/50">

      {/* Status Header */}
      <div className={`px-6 py-3 border-b border-slate-100 ${config.bg}`}>
        <div className="flex items-start justify-between">
           <div className="flex items-center gap-3">
              <div className={`p-1 rounded-lg bg-white/60 backdrop-blur-sm border border-white/50 shadow-sm ${config.text}`}>
                {config.icon}
              </div>
              <div>
                <h2 className={`text-base font-bold tracking-tight ${config.text}`}>{config.label}</h2>
                <p className="text-xs text-slate-500 font-medium mt-0.5">{config.description}</p>
              </div>
           </div>
           <span className="text-[10px] font-mono text-slate-400 bg-white/50 px-2 py-1 rounded-md border border-white/50">
             #{activeSentence.id}
           </span>
        </div>

        {/* Confidence Meter */}
        <div className="mt-4">
           <div className="flex justify-between items-end mb-2">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Confidence Score</span>
              <span className="text-sm font-bold text-slate-900 font-mono">{confidence}%</span>
           </div>
           <div className="w-full h-1.5 bg-white/50 rounded-full overflow-hidden border border-white/20">
             <div 
               className={`h-full rounded-full transition-all duration-1000 ease-out shadow-sm ${
                 confidence > 80 ? 'bg-emerald-500' : confidence > 50 ? 'bg-amber-500' : 'bg-rose-500'
               }`}
               style={{ width: `${confidence}%` }}
             />
           </div>
        </div>
      </div>

      {/* Content Scrollable Area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8 custom-scrollbar bg-white">
        
        {/* Claim Section */}
        <div className="relative">
          <div className="absolute -left-3 top-0 bottom-0 w-0.5 bg-slate-100 rounded-full"></div>
          <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3">
            <Quote className="w-3 h-3" />
            Claim
          </h4>
          <p className="text-sm text-slate-800 leading-relaxed font-medium italic">
            &quot;{activeSentence.text}&quot;
          </p>
        </div>

        {/* Evidence Section */}
        {activeSentence.status !== VerificationStatus.UNVERIFIED && activeSentence.citationText && (() => {
          // Parse evidence entries (could be JSON array or plain text)
          let evidenceEntries: Array<{ text: string; sourceId?: string }> = [];
          try {
            const parsed = JSON.parse(activeSentence.citationText);
            if (Array.isArray(parsed) && parsed.length > 0) {
              evidenceEntries = parsed;
            } else if (typeof parsed === 'object' && parsed.text) {
              evidenceEntries = [parsed];
            }
          } catch {
            // Not JSON, treat as single evidence entry
            if (activeSentence.citationText && activeSentence.citationText.trim() !== '') {
              evidenceEntries = [{ text: activeSentence.citationText, sourceId: activeSentence.citationSourceId }];
            }
          }

          if (evidenceEntries.length === 0) return null;

          // Get unique source documents (computed but not currently used in rendering)
          // const sourceIds = Array.from(new Set(
          //   evidenceEntries
          //     .map(e => e.sourceId)
          //     .filter((id): id is string => !!id)
          // ));

          return (
            <div>
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3">
                <FileSearch className="w-3 h-3" />
                Evidence
              </h4>
              
            {evidenceEntries.map((evidence, idx) => {
              const evidenceSourceDoc = evidence.sourceId ? documents.find(d => d.id === evidence.sourceId) : null;
              return (
                <div key={idx} className="group rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-200 hover:shadow-md hover:shadow-indigo-500/5 transition-all duration-300 cursor-pointer overflow-hidden mb-3">
                  <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-white">
                    <div className="flex items-center gap-2 min-w-0">
                      <ExternalLink className="w-3 h-3 text-indigo-500" />
                      <span className="text-xs font-semibold text-slate-700 truncate">
                        {evidenceSourceDoc?.name || 'Unknown Source'}
                      </span>
                    </div>
                    <ArrowRight className="w-3 h-3 text-slate-300 group-hover:text-indigo-500 transition-transform group-hover:translate-x-0.5" />
                  </div>
                  
                  <div className="p-4">
                    <p className="text-xs text-slate-600 leading-relaxed font-mono bg-white p-3 rounded border border-slate-100 text-justify">
                      &quot;{evidence.text}&quot;
                    </p>
                  </div>
                </div>
              );
            })}
            </div>
          );
        })()}

        {/* Reasoning Section */}
        <div>
          <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3">
            <Sparkles className="w-3 h-3" />
            AI Reasoning
          </h4>
          <div className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-xl border border-slate-100 font-medium">
            {activeSentence.reasoning || "Pending analysis..."}
          </div>
        </div>

        {/* Issues Cards Section */}
        <div className="space-y-3">
          <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3">
            <AlertTriangle className="w-3 h-3" />
            Issues
          </h4>
          
          {/* Missing Source Card */}
          <div className={`rounded-xl border p-4 transition-all ${
            missingSource
              ? 'bg-rose-50 border-rose-200'
              : 'bg-emerald-50 border-emerald-200'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileSearch className={`w-4 h-4 ${
                  missingSource ? 'text-rose-600' : 'text-emerald-600'
                }`} />
                <span className="text-xs font-semibold text-slate-700">Missing Source</span>
              </div>
              <span className={`px-2.5 py-1 rounded text-xs font-medium ${
                missingSource
                  ? 'bg-rose-100 text-rose-700 border border-rose-200'
                  : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
              }`}>
                {missingSource ? 'Yes' : 'No'}
              </span>
            </div>
          </div>

          {/* Conflicting Info Card */}
          <div className={`rounded-xl border p-4 transition-all ${
            conflictingInfo
              ? 'bg-amber-50 border-amber-200'
              : 'bg-emerald-50 border-emerald-200'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className={`w-4 h-4 ${
                  conflictingInfo ? 'text-amber-600' : 'text-emerald-600'
                }`} />
                <span className="text-xs font-semibold text-slate-700">Conflicting Info</span>
              </div>
              <span className={`px-2.5 py-1 rounded text-xs font-medium ${
                conflictingInfo
                  ? 'bg-amber-100 text-amber-700 border border-amber-200'
                  : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
              }`}>
                {conflictingInfo ? 'Yes' : 'No'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Delete Button Footer */}
      {onDelete && (
        <div className="border-t border-slate-200 p-4 bg-slate-50">
          <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
            <AlertDialogTrigger asChild>
              <button
                onClick={() => setDeleteDialogOpen(true)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-rose-600 bg-white hover:bg-rose-50 border border-rose-200 rounded-lg transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                Delete This Claim
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete Claim</AlertDialogTitle>
                <AlertDialogDescription>
                  Are you sure you want to delete this claim? This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    onDelete(activeSentence.id);
                    setDeleteDialogOpen(false);
                  }}
                  className="bg-rose-600 hover:bg-rose-700"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
};

export default RightSidebar;
