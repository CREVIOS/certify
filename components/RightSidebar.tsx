
import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Quote, ExternalLink, Sparkles, X, Check, ArrowRight, FileSearch, Scale } from 'lucide-react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';

interface RightSidebarProps {
  activeSentence: VerifiedSentence | null;
  documents: SupportingDocument[];
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
}

const RightSidebar: React.FC<RightSidebarProps> = ({ 
  activeSentence, 
  documents,
  onApprove,
  onReject
}) => {
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
  const sourceDoc = documents.find(d => d.id === activeSentence.citationSourceId);
  const confidence = activeSentence.confidence || 0;

  return (
    <div className="w-full h-full flex flex-col bg-white border-l border-slate-200/60 shadow-xl shadow-slate-200/50">
      
      {/* Status Header */}
      <div className={`px-6 py-8 border-b border-slate-100 ${config.bg}`}>
        <div className="flex items-start justify-between">
           <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg bg-white/60 backdrop-blur-sm border border-white/50 shadow-sm ${config.text}`}>
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
        <div className="mt-6">
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
            "{activeSentence.text}"
          </p>
        </div>

        {/* Evidence Section */}
        {activeSentence.status !== VerificationStatus.UNVERIFIED && sourceDoc && (
          <div>
             <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3">
               <FileSearch className="w-3 h-3" />
               Evidence
             </h4>
             
             <div className="group rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-200 hover:shadow-md hover:shadow-indigo-500/5 transition-all duration-300 cursor-pointer overflow-hidden">
                <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-white">
                   <div className="flex items-center gap-2 min-w-0">
                      <ExternalLink className="w-3 h-3 text-indigo-500" />
                      <span className="text-xs font-semibold text-slate-700 truncate">
                        {sourceDoc.name}
                      </span>
                   </div>
                   <ArrowRight className="w-3 h-3 text-slate-300 group-hover:text-indigo-500 transition-transform group-hover:translate-x-0.5" />
                </div>
                
                <div className="p-4">
                  <p className="text-xs text-slate-600 leading-relaxed font-mono bg-white p-3 rounded border border-slate-100 text-justify">
                    "{activeSentence.citationText}"
                  </p>
                </div>
             </div>
          </div>
        )}

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
      </div>

      {/* Sticky Footer Actions */}
      <div className="p-5 border-t border-slate-100 bg-white/90 backdrop-blur-md absolute bottom-0 w-full z-10">
        <div className="flex gap-3">
          <button 
            onClick={() => onReject(activeSentence.id)}
            className="flex-1 py-2.5 bg-white border border-slate-200 rounded-lg shadow-sm text-xs font-semibold text-slate-600 hover:text-rose-600 hover:border-rose-200 hover:bg-rose-50 hover:shadow transition-all flex items-center justify-center gap-2 active:scale-95"
          >
             <X className="w-3.5 h-3.5" />
             Reject
          </button>
          <button 
            onClick={() => onApprove(activeSentence.id)}
            className="flex-1 py-2.5 bg-slate-900 border border-transparent rounded-lg shadow-md shadow-slate-900/10 text-xs font-semibold text-white hover:bg-indigo-600 hover:shadow-indigo-500/20 transition-all flex items-center justify-center gap-2 active:scale-95"
          >
             <Check className="w-3.5 h-3.5" />
             Confirm
          </button>
        </div>
      </div>
      
      {/* Spacer for sticky footer */}
      <div className="h-20"></div>
    </div>
  );
};

export default RightSidebar;
