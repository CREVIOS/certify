import React, { useState } from 'react';
import { 
  CheckCircle2, AlertTriangle, XCircle, 
  FileText, ChevronDown, Check, Pencil, X, Plus, Trash2
} from 'lucide-react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';
import {
  TableRow,
  TableCell,
} from './ui/table';
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

interface EvidenceEntry {
  id: string;
  text: string;
  sourceId?: string;
}

interface AuditTableRowProps {
  sentence: VerifiedSentence;
  index: number;
  isActive: boolean;
  documents: SupportingDocument[];
  selectedSources: string[];
  editableEvidenceForSentence?: EvidenceEntry[];
  isEditingEvidence: boolean;
  isStatusDropdownOpen: boolean;
  isSourceDropdownOpen: boolean;
  onSentenceClick: (sentence: VerifiedSentence) => void;
  onStatusChange: (sentenceId: number, status: VerificationStatus) => void;
  onStatusDropdownToggle: (sentenceId: number) => void;
  onSourceDropdownToggle: (sentenceId: number) => void;
  onSourceToggle: (sentenceId: number, sourceId: string) => void;
  onEvidenceChange: (sentenceId: number, evidenceId: string, text: string) => void;
  onEvidenceSourceChange: (sentenceId: number, evidenceId: string, sourceId: string) => void;
  onAddEvidence: (sentenceId: number) => void;
  onRemoveEvidence: (sentenceId: number, evidenceId: string) => void;
  onEvidenceSave: (sentenceId: number) => void;
  onEvidenceCancel: (sentenceId: number) => void;
  onEvidenceEdit: (sentenceId: number) => void;
  onDelete?: (sentenceId: number) => void;
  statusDropdownRef: (el: HTMLDivElement | null) => void;
  sourceDropdownRef: (el: HTMLDivElement | null) => void;
}

const getStatusConfig = (status: VerificationStatus) => {
  switch (status) {
    case VerificationStatus.VERIFIED:
      return { 
        icon: <CheckCircle2 className="w-4 h-4" />, 
        text: 'text-emerald-600', 
        bg: 'bg-emerald-50', 
        border: 'border-emerald-200',
        label: 'Verified',
      };
    case VerificationStatus.PARTIAL:
      return { 
        icon: <AlertTriangle className="w-4 h-4" />, 
        text: 'text-amber-600', 
        bg: 'bg-amber-50', 
        border: 'border-amber-200',
        label: 'Partial',
      };
    case VerificationStatus.UNVERIFIED:
      return { 
        icon: <XCircle className="w-4 h-4" />, 
        text: 'text-rose-600', 
        bg: 'bg-rose-50', 
        border: 'border-rose-200',
        label: 'Not Verified',
      };
    default:
      return { 
        icon: null,
        text: 'text-slate-500', 
        bg: 'bg-slate-50', 
        border: 'border-slate-200',
        label: 'Unknown',
      };
  }
};

const deriveEvidenceList = (
  editableEvidenceForSentence: EvidenceEntry[] | undefined,
  sentence: VerifiedSentence
): EvidenceEntry[] => {
  let evidenceList = editableEvidenceForSentence;

  // If no evidence in state, try to parse from sentence
  if (!evidenceList || evidenceList.length === 0) {
    if (sentence.citationText) {
      try {
        const parsed = JSON.parse(sentence.citationText);
        if (Array.isArray(parsed) && parsed.length > 0) {
          evidenceList = parsed.map((entry: { text?: string; sourceId?: string }, idx: number) => ({
            id: String(idx + 1),
            text: entry.text || '',
            sourceId: entry.sourceId
          }));
        } else {
          // Single evidence entry (backward compatibility)
          evidenceList = [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }];
        }
      } catch {
        // Not JSON, treat as single evidence entry
        evidenceList = [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }];
      }
    } else {
      evidenceList = [];
    }
  }

  return evidenceList;
};

const AuditTableRow: React.FC<AuditTableRowProps> = ({
  sentence,
  index,
  isActive,
  documents,
  selectedSources,
  editableEvidenceForSentence,
  isEditingEvidence,
  isStatusDropdownOpen,
  isSourceDropdownOpen,
  onSentenceClick,
  onStatusChange,
  onStatusDropdownToggle,
  onSourceDropdownToggle,
  onSourceToggle,
  onEvidenceChange,
  onEvidenceSourceChange,
  onAddEvidence,
  onRemoveEvidence,
  onEvidenceSave,
  onEvidenceCancel,
  onEvidenceEdit,
  onDelete,
  statusDropdownRef,
  sourceDropdownRef,
}) => {
  const statusConfig = getStatusConfig(sentence.status);

  const handleRowClick = () => {
    onSentenceClick(sentence);
  };

  const evidenceList = deriveEvidenceList(editableEvidenceForSentence, sentence);

  const filteredEvidence = evidenceList.filter(e => e && e.text && e.text.trim());

  const [deleteEvidenceDialogOpen, setDeleteEvidenceDialogOpen] = useState<Record<string, boolean>>({});
  const [deleteRowDialogOpen, setDeleteRowDialogOpen] = useState(false);

  // Check for missing source - need to check both citationSourceId and evidence entries
  const hasMissingSource = (): boolean => {
    // Default values based on status:
    // - UNVERIFIED: likely missing source (default: Yes)
    // - PARTIAL: might have source but incomplete (default: No, unless explicitly missing)
    // - VERIFIED: should have source (default: No, unless explicitly missing)
    
    if (sentence.status === VerificationStatus.UNVERIFIED) {
      // For UNVERIFIED, default to "Yes" unless we find a source
      let hasSource = false;
      if (sentence.citationSourceId) {
        hasSource = true;
      } else if (sentence.citationText) {
        try {
          const parsed = JSON.parse(sentence.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            hasSource = parsed.some((entry: { sourceId?: string }) => entry.sourceId);
          } else if (typeof parsed === 'object' && parsed.sourceId) {
            hasSource = true;
          }
        } catch {
          // Not JSON, if there's citation text, check if it has meaningful content
          if (sentence.citationText && sentence.citationText.trim() !== '') {
            hasSource = false; // Has text but no source ID
          }
        }
      }
      
      // Also check evidence list for sources
      if (!hasSource && evidenceList.length > 0) {
        hasSource = evidenceList.some(e => e.sourceId);
      }
      
      return !hasSource; // UNVERIFIED without source = missing
    } else {
      // For VERIFIED and PARTIAL, default to "No" unless explicitly missing
      let hasSource = false;
      if (sentence.citationSourceId) {
        hasSource = true;
      } else if (sentence.citationText) {
        try {
          const parsed = JSON.parse(sentence.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            hasSource = parsed.some((entry: { sourceId?: string }) => entry.sourceId);
          } else if (typeof parsed === 'object' && parsed.sourceId) {
            hasSource = true;
          }
        } catch {
          // Not JSON, if there's citation text, it might have source
          if (sentence.citationText && sentence.citationText.trim() !== '') {
            hasSource = false; // Has text but no source ID
          }
        }
      }
      
      // Also check evidence list for sources
      if (!hasSource && evidenceList.length > 0) {
        hasSource = evidenceList.some(e => e.sourceId);
      }
      
      return !hasSource; // Only show "Yes" if explicitly missing
    }
  };

  // Check for conflicting information
  const hasConflictingInfo = (): boolean => {
    // Default values based on status:
    // - PARTIAL: indicates conflicts/discrepancies (default: Yes)
    // - UNVERIFIED: might indicate conflicts (default: No, unless reasoning suggests it)
    // - VERIFIED: no conflicts (default: No)
    
    if (sentence.status === VerificationStatus.PARTIAL) {
      return true; // PARTIAL status indicates conflicting info
    } else if (sentence.status === VerificationStatus.UNVERIFIED) {
      // Check reasoning for conflict indicators
      const reasoning = sentence.reasoning?.toLowerCase() || '';
      return reasoning.includes('contradict') || 
             reasoning.includes('conflict') || 
             reasoning.includes('discrepanc');
    } else {
      return false; // VERIFIED has no conflicts
    }
  };

  const missingSource = hasMissingSource();
  const conflictingInfo = hasConflictingInfo();

  return (
    <TableRow
      key={sentence.id}
      onClick={handleRowClick}
      className={`cursor-pointer transition-colors ${
        isActive ? `${statusConfig.bg} ${statusConfig.border} border-l-4` : 'hover:bg-slate-50'
      }`}
    >
      <TableCell className="font-mono text-xs text-slate-500">
        {index + 1}
      </TableCell>
      <TableCell className="text-sm text-slate-800 leading-relaxed">
        {sentence.text}
      </TableCell>
      <TableCell>
        <div 
          className="relative" 
          ref={statusDropdownRef}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              onStatusDropdownToggle(sentence.id);
            }}
            className="flex items-center gap-2 w-full"
          >
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md ${statusConfig.bg} ${statusConfig.text}`}>
              {statusConfig.icon}
              <span className="text-xs font-medium">{statusConfig.label}</span>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>
          {isStatusDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 min-w-[180px]">
              <div className="py-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onStatusChange(sentence.id, VerificationStatus.VERIFIED);
                  }}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-emerald-50 ${
                    sentence.status === VerificationStatus.VERIFIED ? 'bg-emerald-50' : ''
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                    sentence.status === VerificationStatus.VERIFIED 
                      ? 'border-emerald-600 bg-emerald-600' 
                      : 'border-slate-300'
                  }`}>
                    {sentence.status === VerificationStatus.VERIFIED && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </div>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-700 font-medium">Verified</span>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onStatusChange(sentence.id, VerificationStatus.PARTIAL);
                  }}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-amber-50 ${
                    sentence.status === VerificationStatus.PARTIAL ? 'bg-amber-50' : ''
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                    sentence.status === VerificationStatus.PARTIAL 
                      ? 'border-amber-600 bg-amber-600' 
                      : 'border-slate-300'
                  }`}>
                    {sentence.status === VerificationStatus.PARTIAL && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </div>
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  <span className="text-amber-700 font-medium">Partially Verified</span>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onStatusChange(sentence.id, VerificationStatus.UNVERIFIED);
                  }}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-rose-50 ${
                    sentence.status === VerificationStatus.UNVERIFIED ? 'bg-rose-50' : ''
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                    sentence.status === VerificationStatus.UNVERIFIED 
                      ? 'border-rose-600 bg-rose-600' 
                      : 'border-slate-300'
                  }`}>
                    {sentence.status === VerificationStatus.UNVERIFIED && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </div>
                  <XCircle className="w-3.5 h-3.5 text-rose-600" />
                  <span className="text-rose-700 font-medium">Not Verified</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </TableCell>
      <TableCell className="text-sm text-slate-600">
        <div 
          className="relative" 
          ref={sourceDropdownRef}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              onSourceDropdownToggle(sentence.id);
            }}
            className="flex items-center gap-1.5 w-full hover:bg-slate-50 rounded px-1 py-1 transition-colors"
          >
            {selectedSources && selectedSources.length > 0 ? (
              <div className="flex-1 min-w-0">
                {selectedSources.length === 1 ? (
                  <div className="flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                    <span className="truncate text-xs">
                      {documents.find(d => d.id === selectedSources[0])?.name || 'Unknown'}
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    {selectedSources.slice(0, 2).map((sourceId, idx) => (
                      <div key={idx} className="flex items-center gap-1.5">
                        <FileText className="w-3 h-3 text-slate-400 flex-shrink-0" />
                        <span className="truncate text-xs">
                          {documents.find(d => d.id === sourceId)?.name || 'Unknown'}
                        </span>
                      </div>
                    ))}
                    {selectedSources.length > 2 && (
                      <span className="text-xs text-slate-500">
                        +{selectedSources.length - 2} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <span className="text-slate-400 italic text-xs">No source</span>
            )}
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
          </button>
          {isSourceDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 min-w-[200px] max-h-[200px] overflow-y-auto">
              <div className="py-1">
                {documents.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-slate-400">No documents available</div>
                ) : (
                  documents.map((doc) => {
                    const isSelected = selectedSources?.includes(doc.id) || false;
                    return (
                      <button
                        key={doc.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSourceToggle(sentence.id, doc.id);
                        }}
                        className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-slate-50 ${
                          isSelected ? 'bg-indigo-50' : ''
                        }`}
                      >
                        <div className={`w-4 h-4 border-2 rounded flex items-center justify-center flex-shrink-0 ${
                          isSelected 
                            ? 'border-indigo-600 bg-indigo-600' 
                            : 'border-slate-300'
                        }`}>
                          {isSelected && <Check className="w-3 h-3 text-white" />}
                        </div>
                        <FileText className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="truncate text-slate-700">{doc.name}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </TableCell>
      <TableCell className="text-sm">
        {isEditingEvidence ? (
          <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
            {(evidenceList.length === 0
              ? [{
                  id: '1',
                  text: sentence.citationText || '',
                  sourceId: sentence.citationSourceId,
                }]
              : evidenceList
            ).map((evidence) => (
              <div key={evidence.id} className="space-y-2">
                <div className="flex items-start gap-2">
                  <textarea
                    data-sentence-id={sentence.id}
                    data-evidence-id={evidence.id}
                    value={evidence.text}
                    onChange={(e) => {
                      onEvidenceChange(sentence.id, evidence.id, e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    onFocus={(e) => {
                      e.target.style.height = 'auto';
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    placeholder="Enter evidence text..."
                    className="flex-1 text-xs text-slate-700 bg-indigo-50/50 rounded-lg p-2 border border-indigo-100/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300 resize-none leading-relaxed overflow-hidden"
                    style={{ 
                      fontFamily: 'inherit',
                      minHeight: '60px',
                      maxHeight: '300px'
                    }}
                    rows={1}
                  />
                  <AlertDialog 
                    open={deleteEvidenceDialogOpen[evidence.id] || false}
                    onOpenChange={(open) => setDeleteEvidenceDialogOpen(prev => ({ ...prev, [evidence.id]: open }))}
                  >
                    <AlertDialogTrigger asChild>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteEvidenceDialogOpen(prev => ({ ...prev, [evidence.id]: true }));
                        }}
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-md transition-colors flex-shrink-0 mt-1"
                        title="Remove evidence"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </AlertDialogTrigger>
                    <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Remove Evidence</AlertDialogTitle>
                        <AlertDialogDescription>
                          Are you sure you want to remove this evidence entry? This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemoveEvidence(sentence.id, evidence.id);
                            setDeleteEvidenceDialogOpen(prev => ({ ...prev, [evidence.id]: false }));
                          }}
                          className="bg-rose-600 hover:bg-rose-700"
                        >
                          Remove
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={evidence.sourceId || ''}
                    onChange={(e) => onEvidenceSourceChange(sentence.id, evidence.id, e.target.value)}
                    className="text-xs text-slate-600 bg-white border border-slate-200 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
                  >
                    <option value="">Select source file...</option>
                    {documents.map(doc => (
                      <option key={doc.id} value={doc.id}>{doc.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            ))}
            <button
              onClick={() => onAddEvidence(sentence.id)}
              className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-md transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Evidence
            </button>
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={() => onEvidenceSave(sentence.id)}
                className="px-2 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors flex items-center gap-1"
              >
                <Check className="w-3 h-3" />
                Save
              </button>
              <button
                onClick={() => onEvidenceCancel(sentence.id)}
                className="px-2 py-1 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors flex items-center gap-1"
              >
                <X className="w-3 h-3" />
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                {filteredEvidence.length === 0 ? (
                  <span className="text-slate-400 italic text-xs">No evidence</span>
                ) : (
                  filteredEvidence.map((evidence, idx) => (
                    <div key={evidence.id || idx} className="bg-indigo-50/50 rounded-lg p-2 border border-indigo-100/50">
                      <p className="text-xs text-indigo-700 leading-relaxed italic">
                        &quot;{evidence.text}&quot;
                      </p>
                      {evidence.sourceId && (
                        <div className="flex items-center gap-1 mt-1">
                          <FileText className="w-3 h-3 text-indigo-400" />
                          <span className="text-[10px] text-indigo-500">
                            {documents.find(d => d.id === evidence.sourceId)?.name || 'Unknown source'}
                          </span>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
              <div className="flex flex-col gap-1 flex-shrink-0">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEvidenceEdit(sentence.id);
                  }}
                  className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                  title="Edit evidence"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onAddEvidence(sentence.id);
                    onEvidenceEdit(sentence.id);
                  }}
                  className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                  title="Add evidence"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        )}
      </TableCell>
      <TableCell className="text-sm">
        {sentence.reasoning ? (
          <div className="bg-slate-50 rounded-lg p-2 border border-slate-100">
            <p className="text-xs text-slate-600 leading-relaxed">
              {sentence.reasoning}
            </p>
          </div>
        ) : (
          <span className="text-slate-400 italic">No reasoning</span>
        )}
      </TableCell>
      <TableCell className="text-sm">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-medium ${
            missingSource
              ? 'bg-rose-50 text-rose-700 border border-rose-200'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          }`}
        >
          {missingSource ? 'Yes' : 'No'}
        </span>
      </TableCell>
      <TableCell className="text-sm">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-medium ${
            conflictingInfo
              ? 'bg-amber-50 text-amber-700 border border-amber-200'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          }`}
        >
          {conflictingInfo ? 'Yes' : 'No'}
        </span>
      </TableCell>
      <TableCell>
        {onDelete && (
          <AlertDialog open={deleteRowDialogOpen} onOpenChange={setDeleteRowDialogOpen}>
            <AlertDialogTrigger asChild>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteRowDialogOpen(true);
                }}
                className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-md transition-colors"
                title="Delete row"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent onClick={(e) => e.stopPropagation()}>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete Row</AlertDialogTitle>
                <AlertDialogDescription>
                  Are you sure you want to delete this row? This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(sentence.id);
                    setDeleteRowDialogOpen(false);
                  }}
                  className="bg-rose-600 hover:bg-rose-700"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </TableCell>
    </TableRow>
  );
};

export default AuditTableRow;


