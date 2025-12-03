import React, { useState, useRef, useEffect, useMemo } from 'react';
import { VerifiedSentence, VerificationStatus, SupportingDocument } from '../types';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import AuditTableFilters, { FilterType } from './AuditTableFilters';
import AuditTableRow from './AuditTableRow';

interface AuditTableProps {
  sentences: VerifiedSentence[];
  documents: SupportingDocument[];
  activeSentenceId: number | null;
  onSentenceClick: (sentence: VerifiedSentence) => void;
  onSentenceUpdate?: (id: number, updates: Partial<VerifiedSentence>) => void;
}

const AuditTable: React.FC<AuditTableProps> = ({
  sentences,
  documents,
  activeSentenceId,
  onSentenceClick,
  onSentenceUpdate,
}) => {
  const [filter, setFilter] = useState<FilterType>('all');
  const [openStatusDropdown, setOpenStatusDropdown] = useState<number | null>(null);
  const [openSourceDropdown, setOpenSourceDropdown] = useState<number | null>(null);
  const [editableEvidence, setEditableEvidence] = useState<Record<number, Array<{id: string, text: string, sourceId?: string}>>>({});
  const [selectedSources, setSelectedSources] = useState<Record<number, string[]>>({});
  const [editingEvidence, setEditingEvidence] = useState<number | null>(null);

  const statusDropdownRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const sourceDropdownRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const filteredSentences = useMemo(() => {
    if (filter === 'all') return sentences;
    const statusMap: Record<string, VerificationStatus> = {
      'verified': VerificationStatus.VERIFIED,
      'partial': VerificationStatus.PARTIAL,
      'unverified': VerificationStatus.UNVERIFIED
    };
    return sentences.filter(s => s.status === statusMap[filter]);
  }, [sentences, filter]);

  // Initialize editable evidence and selected sources from sentences
  useEffect(() => {
    const evidenceMap: Record<number, Array<{id: string, text: string, sourceId?: string}>> = {};
    const sourcesMap: Record<number, string[]> = {};
    sentences.forEach(s => {
      if (s.citationText) {
        try {
          // Try to parse as JSON (multiple evidence entries)
          const parsed = JSON.parse(s.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            // Multiple evidence entries stored as JSON
            evidenceMap[s.id] = parsed.map((entry: any, idx: number) => ({
              id: String(idx + 1),
              text: entry.text || '',
              sourceId: entry.sourceId
            }));
          } else {
            // Single evidence entry (backward compatibility)
            evidenceMap[s.id] = [{ id: '1', text: s.citationText, sourceId: s.citationSourceId }];
          }
        } catch {
          // Not JSON, treat as single evidence entry (backward compatibility)
          evidenceMap[s.id] = [{ id: '1', text: s.citationText, sourceId: s.citationSourceId }];
        }
      }
      if (s.citationSourceId) {
        sourcesMap[s.id] = [s.citationSourceId];
      }
    });
    setEditableEvidence(prev => {
      const merged = { ...prev };
      Object.keys(evidenceMap).forEach(id => {
        const numId = Number(id);
        const sentence = sentences.find(s => s.id === numId);
        // Only initialize if not already set or if sentence has new citationText
        if (!merged[numId] || (sentence?.citationText && sentence.citationText !== JSON.stringify(merged[numId].map(e => ({ text: e.text, sourceId: e.sourceId }))))) {
          merged[numId] = evidenceMap[numId];
        }
      });
      return merged;
    });
    // Only update selectedSources if not already set (preserve user selections)
    setSelectedSources(prev => {
      const updated = { ...prev };
      Object.keys(sourcesMap).forEach(id => {
        const numId = Number(id);
        // Only initialize if not already set by user
        if (!updated[numId] || updated[numId].length === 0) {
          updated[numId] = sourcesMap[numId];
        }
      });
      return updated;
    });
  }, [sentences]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      
      // Check status dropdowns
      if (openStatusDropdown !== null) {
        const ref = statusDropdownRefs.current[openStatusDropdown];
        if (ref && !ref.contains(target)) {
          setOpenStatusDropdown(null);
        }
      }
      
      // Check source dropdowns
      if (openSourceDropdown !== null) {
        const ref = sourceDropdownRefs.current[openSourceDropdown];
        if (ref && !ref.contains(target)) {
          setOpenSourceDropdown(null);
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [openStatusDropdown, openSourceDropdown]);

  const handleStatusDropdownToggle = (sentenceId: number) => {
    setOpenStatusDropdown(current => current === sentenceId ? null : sentenceId);
  };

  const handleSourceDropdownToggle = (sentenceId: number) => {
    setOpenSourceDropdown(current => current === sentenceId ? null : sentenceId);
  };

  const handleStatusChange = (sentenceId: number, newStatus: VerificationStatus) => {
    if (onSentenceUpdate) {
      onSentenceUpdate(sentenceId, { status: newStatus });
    }
    setOpenStatusDropdown(null);
  };

  const handleSourceToggle = (sentenceId: number, sourceId: string) => {
    const current = selectedSources[sentenceId] || [];
    const newSelection = current.includes(sourceId)
      ? current.filter(id => id !== sourceId)
      : [...current, sourceId];
    
    setSelectedSources(prev => ({ ...prev, [sentenceId]: newSelection }));
    
    // Store all selected sources - we'll use citationSourceId for the first one (backward compatibility)
    // and could extend the type later to support multiple sources
    if (onSentenceUpdate) {
      // For now, store first selected source in citationSourceId
      // The full list is maintained in selectedSources state
      onSentenceUpdate(sentenceId, { citationSourceId: newSelection.length > 0 ? newSelection[0] : undefined });
    }
  };

  const handleEvidenceChange = (sentenceId: number, evidenceId: string, text: string) => {
    setEditableEvidence(prev => {
      const current = prev[sentenceId] || [];
      return {
        ...prev,
        [sentenceId]: current.map(e => e.id === evidenceId ? { ...e, text } : e)
      };
    });
  };

  const handleEvidenceSourceChange = (sentenceId: number, evidenceId: string, sourceId: string) => {
    setEditableEvidence(prev => {
      const current = prev[sentenceId] || [];
      return {
        ...prev,
        [sentenceId]: current.map(e => e.id === evidenceId ? { ...e, sourceId } : e)
      };
    });
  };

  const handleAddEvidence = (sentenceId: number) => {
    setEditableEvidence(prev => {
      const current = prev[sentenceId] || [];
      // If no evidence exists, initialize with empty entry
      if (current.length === 0) {
        const sentence = sentences.find(s => s.id === sentenceId);
        if (sentence?.citationText) {
          return {
            ...prev,
            [sentenceId]: [
              { id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId },
              { id: String(Date.now()), text: '', sourceId: undefined }
            ]
          };
        }
      }
      const newId = String(Date.now());
      return {
        ...prev,
        [sentenceId]: [...current, { id: newId, text: '', sourceId: undefined }]
      };
    });
  };

  const handleRemoveEvidence = (sentenceId: number, evidenceId: string) => {
    setEditableEvidence(prev => {
      const current = prev[sentenceId] || [];
      const filtered = current.filter(e => e.id !== evidenceId);
      return {
        ...prev,
        [sentenceId]: filtered.length > 0 ? filtered : [{ id: '1', text: '', sourceId: undefined }]
      };
    });
  };

  const handleEvidenceSave = (sentenceId: number) => {
    const evidenceEntries = editableEvidence[sentenceId] || [];
    // Filter out empty entries
    const validEntries = evidenceEntries.filter(e => e.text && e.text.trim());
    
    if (onSentenceUpdate && validEntries.length > 0) {
      // Store evidence entries as JSON string to preserve separation
      // Format: JSON array of {text, sourceId} objects
      const evidenceData = JSON.stringify(validEntries.map(e => ({
        text: e.text,
        sourceId: e.sourceId
      })));
      onSentenceUpdate(sentenceId, { citationText: evidenceData });
    }
    setEditingEvidence(null);
  };

  const handleEvidenceCancel = (sentenceId: number) => {
    // Restore original value from sentence
    const sentence = sentences.find(s => s.id === sentenceId);
    if (sentence?.citationText) {
      try {
        // Try to parse as JSON (multiple evidence entries)
        const parsed = JSON.parse(sentence.citationText);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setEditableEvidence(prev => ({
            ...prev,
            [sentenceId]: parsed.map((entry: any, idx: number) => ({
              id: String(idx + 1),
              text: entry.text || '',
              sourceId: entry.sourceId
            }))
          }));
        } else {
          // Single evidence entry (backward compatibility)
          setEditableEvidence(prev => ({
            ...prev,
            [sentenceId]: [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }]
          }));
        }
      } catch {
        // Not JSON, treat as single evidence entry
        setEditableEvidence(prev => ({
          ...prev,
          [sentenceId]: [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }]
        }));
      }
    } else {
      setEditableEvidence(prev => ({
        ...prev,
        [sentenceId]: [{ id: '1', text: '', sourceId: undefined }]
      }));
    }
    setEditingEvidence(null);
  };

  const handleEvidenceEdit = (sentenceId: number) => {
    const sentence = sentences.find(s => s.id === sentenceId);
    const current = editableEvidence[sentenceId];
    
    if (!current || current.length === 0) {
      // Initialize with existing citationText or empty
      if (sentence?.citationText) {
        try {
          // Try to parse as JSON (multiple evidence entries)
          const parsed = JSON.parse(sentence.citationText);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setEditableEvidence(prev => ({
              ...prev,
              [sentenceId]: parsed.map((entry: any, idx: number) => ({
                id: String(idx + 1),
                text: entry.text || '',
                sourceId: entry.sourceId
              }))
            }));
          } else {
            // Single evidence entry (backward compatibility)
            setEditableEvidence(prev => ({
              ...prev,
              [sentenceId]: [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }]
            }));
          }
        } catch {
          // Not JSON, treat as single evidence entry
          setEditableEvidence(prev => ({
            ...prev,
            [sentenceId]: [{ id: '1', text: sentence.citationText, sourceId: sentence.citationSourceId }]
          }));
        }
      } else {
        setEditableEvidence(prev => ({
          ...prev,
          [sentenceId]: [{ id: '1', text: '', sourceId: undefined }]
        }));
      }
    }
    
    setEditingEvidence(sentenceId);
    // Auto-resize textareas after a brief delay to ensure they're rendered
    setTimeout(() => {
      const textareas = document.querySelectorAll(`textarea[data-sentence-id="${sentenceId}"]`);
      textareas.forEach(textarea => {
        const ta = textarea as HTMLTextAreaElement;
        ta.style.height = 'auto';
        ta.style.height = `${ta.scrollHeight}px`;
      });
    }, 10);
  };

  return (
    <>
      <AuditTableFilters
        filter={filter}
        onFilterChange={(value) => setFilter(value)}
      />

      {/* Table */}
      <div className="flex-1 relative w-full overflow-auto table-scroll-wrapper" style={{
        scrollbarWidth: 'auto',
        scrollbarColor: '#cbd5e1 #f1f5f9'
      }}>
        <style>{`
          .table-scroll-wrapper::-webkit-scrollbar {
            width: 12px;
            height: 12px;
          }
          .table-scroll-wrapper::-webkit-scrollbar-track {
            background: #f1f5f9;
            border-radius: 6px;
          }
          .table-scroll-wrapper::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 6px;
            border: 2px solid #f1f5f9;
          }
          .table-scroll-wrapper::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
          }
          .table-scroll-wrapper::-webkit-scrollbar-corner {
            background: #f1f5f9;
          }
        `}</style>
        <div className="p-6">
          <Table className="min-w-full">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]">Index</TableHead>
                <TableHead className="min-w-[300px]">Sentence</TableHead>
                <TableHead className="w-[150px]">Status</TableHead>
                <TableHead className="min-w-[150px]">Source File Name</TableHead>
                <TableHead className="min-w-[250px]">Evidence</TableHead>
                <TableHead className="min-w-[300px]">AI Reasoning</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredSentences.map((sentence, index) => {
                const isActive = activeSentenceId === sentence.id;

                const selectedSourcesForSentence = selectedSources[sentence.id] || [];
                const editableEvidenceForSentence = editableEvidence[sentence.id];

                return (
                  <AuditTableRow
                    key={sentence.id}
                    sentence={sentence}
                    index={index}
                    isActive={isActive}
                    documents={documents}
                    selectedSources={selectedSourcesForSentence}
                    editableEvidenceForSentence={editableEvidenceForSentence}
                    isEditingEvidence={editingEvidence === sentence.id}
                    isStatusDropdownOpen={openStatusDropdown === sentence.id}
                    isSourceDropdownOpen={openSourceDropdown === sentence.id}
                    onSentenceClick={onSentenceClick}
                    onStatusChange={handleStatusChange}
                    onStatusDropdownToggle={handleStatusDropdownToggle}
                    onSourceDropdownToggle={handleSourceDropdownToggle}
                    onSourceToggle={handleSourceToggle}
                    onEvidenceChange={handleEvidenceChange}
                    onEvidenceSourceChange={handleEvidenceSourceChange}
                    onAddEvidence={handleAddEvidence}
                    onRemoveEvidence={handleRemoveEvidence}
                    onEvidenceSave={handleEvidenceSave}
                    onEvidenceCancel={handleEvidenceCancel}
                    onEvidenceEdit={handleEvidenceEdit}
                    statusDropdownRef={(el) => { statusDropdownRefs.current[sentence.id] = el; }}
                    sourceDropdownRef={(el) => { sourceDropdownRefs.current[sentence.id] = el; }}
                  />
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    </>
  );
};

export default AuditTable;


