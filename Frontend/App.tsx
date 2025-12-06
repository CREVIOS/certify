
import React, { useState, useRef, useEffect } from 'react';
import { SupportingDocument, IPODocument, VerificationStatus, Section } from './types';
import LeftSidebar from './components/LeftSidebar';
import RightSidebar from './components/RightSidebar';
import DocumentViewer from './components/DocumentViewer';
import AuditPanel from './components/AuditPanel';
import SectionModal from './components/SectionModal';
import {
  ensureProject,
  uploadDocument,
  indexDocument,
  pollDocumentIndexed,
  createVerificationJob,
  startVerificationJob,
  pollVerificationJob,
  reviewSentence,
  suggestSections,
  updateDocument,
} from './services/api';
import { downloadVerificationReport } from './utils/exportUtils';
import { extractTextFromPDF } from './utils/pdfHelpers';
import { ShieldCheck, Download, Loader2, FileUp, UploadCloud, PanelLeftClose, PanelLeftOpen, FileText, ClipboardCheck } from 'lucide-react';

type ViewMode = 'pdf' | 'audit';

const App: React.FC = () => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [loadingStage, setLoadingStage] = useState<string>('');
  const [indexingProgress, setIndexingProgress] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('pdf');
  
  // Initialize sidebar widths based on screen size (percentage-based)
  const getInitialLeftWidth = () => {
    if (typeof window !== 'undefined') {
      return window.innerWidth * 0.20; // 20% default
    }
    return 280; // fallback
  };
  
  const getInitialRightWidth = () => {
    if (typeof window !== 'undefined') {
      return window.innerWidth * 0.35; // 35% default
    }
    return 340; // fallback
  };
  
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(() => getInitialLeftWidth());
  const [rightSidebarWidth, setRightSidebarWidth] = useState(() => getInitialRightWidth());
  const [isResizingLeft, setIsResizingLeft] = useState(false);
  const [isResizingRight, setIsResizingRight] = useState(false);
  
  const [supportingDocs, setSupportingDocs] = useState<SupportingDocument[]>([]);
  const [ipoDoc, setIpoDoc] = useState<IPODocument | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [mainDocumentId, setMainDocumentId] = useState<string | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [showSectionModal, setShowSectionModal] = useState(false);
  const [activeSentenceId, setActiveSentenceId] = useState<number | null>(null);
  const mainDocInputRef = useRef<HTMLInputElement>(null);

  const pendingSupportDocs = supportingDocs.filter(d => !d.isIndexed).length;

  const ensureDefaultProject = async () => {
    try {
      const project = await ensureProject('IPO Verification Workspace');
      setProjectId(project.id);
    } catch (err) {
      console.error(err);
      alert('Unable to initialize project. Check backend connectivity.');
    }
  };

  const mapValidationResult = (value: string): VerificationStatus => {
    const normalized = (value || '').toLowerCase();
    if (normalized === 'validated' || normalized === 'verified') return VerificationStatus.VERIFIED;
    if (normalized === 'incorrect') return VerificationStatus.UNVERIFIED;
    return VerificationStatus.PARTIAL;
  };

  // Handle responsive breakdown
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
      else setSidebarOpen(true);
      
      // Constrain sidebar widths to min/max when window resizes
      const leftMinWidth = window.innerWidth * 0.15; // 15% min
      const leftMaxWidth = window.innerWidth * 0.30; // 30% max
      const rightMinWidth = window.innerWidth * 0.25; // 25% min
      const rightMaxWidth = window.innerWidth * 0.40; // 40% max
      
      setLeftSidebarWidth(prev => Math.min(Math.max(prev, leftMinWidth), leftMaxWidth));
      setRightSidebarWidth(prev => Math.min(Math.max(prev, rightMinWidth), rightMaxWidth));
    };
    
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Ensure a project exists on load
  useEffect(() => {
    ensureDefaultProject();
  }, []);

  // Handle left sidebar resize
  useEffect(() => {
    if (!isResizingLeft) return;

    const handleMouseMove = (e: MouseEvent) => {
      const minWidth = window.innerWidth * 0.15; // 15% min
      const maxWidth = window.innerWidth * 0.30; // 30% max
      const newWidth = Math.min(Math.max(e.clientX, minWidth), maxWidth);
      setLeftSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizingLeft(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizingLeft]);

  // Handle right sidebar resize
  useEffect(() => {
    if (!isResizingRight) return;

    const handleMouseMove = (e: MouseEvent) => {
      const minWidth = window.innerWidth * 0.25; // 25% min
      const maxWidth = window.innerWidth * 0.40; // 40% max
      const newWidth = Math.min(Math.max(window.innerWidth - e.clientX, minWidth), maxWidth);
      setRightSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizingRight(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizingRight]);
  
  const processMainFile = async (file: File) => {
    setIsParsing(true);
    try {
      if (!projectId) await ensureDefaultProject();

      // Extract text locally for preview/highlight
      let text = '';
      if (file.type === 'application/pdf') {
        text = await extractTextFromPDF(file);
      } else {
        text = await file.text();
      }

      const tempDoc: IPODocument = {
        id: `temp-${Date.now()}`,
        title: file.name.replace(/\.[^/.]+$/, ""),
        content: text,
        sentences: [],
        file: file,
        sections: []
      };
      setIpoDoc(tempDoc);
      setActiveSentenceId(null);
      setViewMode('pdf');

      // Upload to backend and trigger indexing
      const uploaded = await uploadDocument(file, projectId as string, 'main');
      setMainDocumentId(uploaded.document_id);
      setIpoDoc((prev) => prev ? { ...prev, id: uploaded.document_id } : null);

      await indexDocument(uploaded.document_id);
      await pollDocumentIndexed(uploaded.document_id);

      // Prompt user to section the IPO
      setShowSectionModal(true);
    } catch (err) {
      console.error("PDF processing error:", err);
      const errorMessage = err instanceof Error ? err.message : "Error reading file. Please ensure it is a valid text-based PDF.";
      alert(errorMessage);
    } finally {
      setIsParsing(false);
    }
  };

  const handleMainDocUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processMainFile(file);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    const file = e.dataTransfer.files?.[0];
    if (file && file.type === "application/pdf") {
        await processMainFile(file);
    } else if (file) {
        alert("Please upload a PDF file.");
    }
  };

  const handleUploadEvidence = async (file: File, content: string) => {
    if (!projectId) await ensureDefaultProject();

    const tempId = `DOC-${String(supportingDocs.length + 1).padStart(3, '0')}`;
    const newDoc: SupportingDocument = {
      id: tempId,
      name: file.name,
      type: 'uploaded',
      uploadDate: new Date().toISOString().split('T')[0],
      content,
      isIndexed: false,
    };
    setSupportingDocs(prev => [...prev, newDoc]);

    try {
      const uploaded = await uploadDocument(file, projectId as string, 'supporting');
      const backendId = uploaded.document_id;

      // Replace temp id with backend id
      setSupportingDocs(prev => prev.map(d => d.id === tempId ? { ...d, id: backendId, backendId } : d));

      await indexDocument(backendId);
      await pollDocumentIndexed(backendId);

      setSupportingDocs(prev => prev.map(d => d.id === backendId ? { ...d, isIndexed: true } : d));
    } catch (err) {
      console.error("Indexing failed", err);
      alert("Failed to index supporting document.");
    }
  };

  const handleAnalyze = async () => {
    if (!ipoDoc || !mainDocumentId || supportingDocs.length === 0) {
      alert("Please upload both an IPO Prospectus and at least one Supporting Document.");
      return;
    }

    if (pendingSupportDocs > 0) {
      alert(`Please wait for ${pendingSupportDocs} supporting document(s) to finish indexing.`);
      return;
    }

    setIsAnalyzing(true);

    try {
      if (sections.length && mainDocumentId) {
        await updateDocument(mainDocumentId, { metadata: { sections } });
      }

      setLoadingStage('Starting verification...');
      setIndexingProgress(0); 

      const job = await createVerificationJob(projectId as string, mainDocumentId);
      await startVerificationJob(job.id);

      const completedJob = await pollVerificationJob(job.id, (p) => setIndexingProgress(Math.round(p)));

      if (['failed', 'FAILED'].includes(completedJob.status)) {
        throw new Error(completedJob.error_message || 'Verification failed');
      }

      const mappedSentences = (completedJob.sentences || []).map((s: any, idx: number) => ({
        id: idx,
        backendId: s.id,
        text: s.content,
        status: mapValidationResult(s.validation_result),
        reasoning: s.reasoning,
        citationText: s.citations?.[0]?.cited_text,
        citationSourceId: s.citations?.[0]?.source_document_id || s.citations?.[0]?.document_id,
        confidence: Math.round((s.confidence_score || 0) * 100),
        pageNumber: s.page_number
      }));

      setIpoDoc(prev => prev ? ({ ...prev, sentences: mappedSentences }) : null);

      if (mappedSentences.length > 0) {
        setActiveSentenceId(mappedSentences[0].id);
      }

      setViewMode('audit');
    } catch (error) {
      console.error("Error verifying document:", error);
      alert("Failed to verify document. Check console or API for details.");
    } finally {
      setIsAnalyzing(false);
      setLoadingStage('');
      setIndexingProgress(0);
    }
  };

  const handleApprove = async (id: number) => {
    if (!ipoDoc) return;
    const target = ipoDoc.sentences.find(s => s.id === id);
    if (target?.backendId) {
      await reviewSentence(target.backendId, 'validated');
    }
    setIpoDoc(prev => prev ? ({
      ...prev,
      sentences: prev.sentences.map(s => 
        s.id === id ? { ...s, status: VerificationStatus.VERIFIED, confidence: 100 } : s
      )
    }) : null);
  };

  const handleReject = async (id: number) => {
    if (!ipoDoc) return;
    const target = ipoDoc.sentences.find(s => s.id === id);
    if (target?.backendId) {
      await reviewSentence(target.backendId, 'incorrect');
    }
    setIpoDoc(prev => prev ? ({
      ...prev,
      sentences: prev.sentences.map(s => 
        s.id === id ? { ...s, status: VerificationStatus.UNVERIFIED, confidence: 0 } : s
      )
    }) : null);
  };

  const handleDeleteSentence = (id: number) => {
    if (!ipoDoc) return;
    setIpoDoc(prev => prev ? ({
      ...prev,
      sentences: prev.sentences.filter(s => s.id !== id)
    }) : null);
    // Clear active sentence if it was deleted
    if (activeSentenceId === id) {
      setActiveSentenceId(null);
    }
  };

  const handleSaveSections = async (secs: Section[]) => {
    setSections(secs);
    setIpoDoc(prev => prev ? { ...prev, sections: secs } : prev);
    if (mainDocumentId) {
      try {
        await updateDocument(mainDocumentId, { metadata: { sections: secs } });
      } catch (err) {
        console.error(err);
      }
    }
  };

  const handleAiSuggestSections = async (): Promise<Section[]> => {
    if (!mainDocumentId) throw new Error('Main document not ready');
    const res = await suggestSections(mainDocumentId);
    setSections(res.sections);
    return res.sections;
  };

  const handleSentenceUpdate = async (id: number, updates: Partial<IPODocument['sentences'][number]>) => {
    const sentence = ipoDoc?.sentences.find(s => s.id === id);
    setIpoDoc(prev => prev ? ({
      ...prev,
      sentences: prev.sentences.map(s => s.id === id ? { ...s, ...updates } : s)
    }) : null);

    // Push review changes to backend if status changed
    if (sentence?.backendId && updates.status) {
      const status = updates.status;
      if (status === VerificationStatus.VERIFIED) await reviewSentence(sentence.backendId, 'validated');
      else if (status === VerificationStatus.UNVERIFIED) await reviewSentence(sentence.backendId, 'incorrect');
      else if (status === VerificationStatus.PARTIAL) await reviewSentence(sentence.backendId, 'uncertain');
    }
  };

  const handleDownload = () => {
    if (ipoDoc) {
      downloadVerificationReport(ipoDoc.sentences, supportingDocs);
    }
  };

  const activeSentence = ipoDoc?.sentences.find(s => s.id === activeSentenceId) || null;
  
  const stats = ipoDoc ? {
    verified: ipoDoc.sentences.filter(s => s.status === VerificationStatus.VERIFIED).length,
    partial: ipoDoc.sentences.filter(s => s.status === VerificationStatus.PARTIAL).length,
    unverified: ipoDoc.sentences.filter(s => s.status === VerificationStatus.UNVERIFIED).length,
    total: ipoDoc.sentences.length
  } : { verified: 0, partial: 0, unverified: 0, total: 0 };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 text-slate-900 font-sans selection:bg-indigo-100 selection:text-indigo-900">
      
      <input 
        ref={mainDocInputRef} 
        type="file" 
        accept=".pdf" 
        className="hidden" 
        onChange={handleMainDocUpload}
      />

      {/* Header */}
      <header className="fixed top-0 w-full h-14 bg-white/80 backdrop-blur-md border-b border-slate-200/60 z-50 flex items-center justify-between px-4 transition-all duration-300">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 text-slate-500 hover:bg-slate-100 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-slate-200"
          >
            {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
          </button>
          
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-gradient-to-br from-slate-800 to-slate-950 rounded-lg flex items-center justify-center text-white shadow-sm ring-1 ring-white/20">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h1 className="font-bold text-sm text-slate-900 tracking-tight leading-tight">
                Certify<span className="text-indigo-600">AI</span>
              </h1>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
           {ipoDoc && stats.total > 0 && !isAnalyzing && (
             <div className="flex items-center gap-2 text-[10px] font-semibold mr-4 hidden lg:flex">
               <div className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 shadow-sm flex items-center gap-1.5">
                 <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                 {Math.round((stats.verified / stats.total) * 100)}% Verified
               </div>
                <div className="px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-100 shadow-sm flex items-center gap-1.5">
                 <div className="w-1.5 h-1.5 rounded-full bg-rose-500"></div>
                 {stats.unverified} Risks
               </div>
             </div>
           )}

           <div className="flex items-center gap-2">
            {ipoDoc && (
              <>
                {/* View Mode Toggle */}
                <div className="flex items-center bg-slate-100 rounded-lg p-0.5 mr-2">
                  <button 
                    onClick={() => setViewMode('pdf')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      viewMode === 'pdf' 
                        ? 'bg-white text-slate-900 shadow-sm' 
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">PDF</span>
                  </button>
                  <button 
                    onClick={() => setViewMode('audit')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      viewMode === 'audit' 
                        ? 'bg-white text-indigo-600 shadow-sm' 
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <ClipboardCheck className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Audit</span>
                  </button>
                </div>

                <div className="w-px h-4 bg-slate-200 mx-1 hidden md:block"></div>

                <button 
                  onClick={() => mainDocInputRef.current?.click()}
                  className="hidden md:flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-all"
                >
                  <FileUp className="w-3.5 h-3.5" />
                  <span>Replace PDF</span>
                </button>

                <button 
                  onClick={handleDownload}
                  className="p-1.5 md:px-3 md:py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-all flex items-center gap-2"
                  title="Export Report"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span className="hidden md:inline">Export</span>
                </button>
                
                <div className="w-px h-4 bg-slate-200 mx-1 hidden md:block"></div>
              </>
            )}
           </div>
        </div>
      </header>

      {/* Main Layout */}
      <div className="pt-14 w-full h-full flex relative">
        
        {/* Left Sidebar */}
        <div 
          className={`
            fixed top-14 bottom-0 left-0 z-40 bg-white transition-all duration-300 ease-in-out transform
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full w-0'}
            lg:relative lg:translate-x-0 lg:top-0
            ${!sidebarOpen && 'lg:w-0 lg:overflow-hidden'}
          `}
          style={{ 
            width: sidebarOpen ? `${leftSidebarWidth}px` : '0px',
            transition: isResizingLeft ? 'none' : 'width 0.3s ease-in-out'
          }}
        >
          <div className="h-full overflow-hidden flex flex-col" style={{ width: `${leftSidebarWidth}px` }}>
             <LeftSidebar 
              documents={supportingDocs} 
              onUpload={handleUploadEvidence}
              onRunAudit={handleAnalyze}
              isAnalyzing={isAnalyzing}
              hasIpoDoc={!!ipoDoc}
              indexingProgress={indexingProgress}
              pendingCount={pendingSupportDocs}
            />
          </div>
          
          {/* Left Resize Handle */}
          {sidebarOpen && !isMobile && (
            <div
              className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-indigo-400/30 bg-transparent z-50 group transition-colors"
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsResizingLeft(true);
              }}
            >
              <div className="absolute top-1/2 right-0 -translate-y-1/2 translate-x-1/2 w-1 h-16 bg-slate-300 rounded-full group-hover:bg-indigo-500 transition-colors opacity-0 group-hover:opacity-100" />
            </div>
          )}
        </div>

        {/* Mobile Overlay */}
        {isMobile && sidebarOpen && (
          <div 
            className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Center Content */}
        <div className={`h-full relative min-w-0 bg-slate-50/50 bg-dot-pattern flex flex-col transition-all duration-300 ${viewMode === 'audit' ? 'flex-1' : 'flex-1'}`}>
           {ipoDoc ? (
             viewMode === 'pdf' ? (
               <DocumentViewer 
                 doc={ipoDoc} 
                 onSentenceClick={(s) => setActiveSentenceId(s.id)}
                 activeSentenceId={activeSentenceId}
                 isAnalyzing={isAnalyzing}
               />
             ) : (
               <AuditPanel 
                 sentences={ipoDoc.sentences}
                 documents={supportingDocs}
                 activeSentenceId={activeSentenceId}
                 onSentenceClick={(s) => setActiveSentenceId(s.id)}
                 onSentenceUpdate={handleSentenceUpdate}
                 onSentenceDelete={handleDeleteSentence}
               />
             )
           ) : (
             <div 
               className={`h-full flex flex-col items-center justify-center p-8 transition-colors duration-300 ${dragActive ? 'bg-indigo-50/80' : ''}`}
               onDragEnter={handleDrag}
               onDragLeave={handleDrag}
               onDragOver={handleDrag}
               onDrop={handleDrop}
             >
               {dragActive && (
                 <div className="absolute inset-6 border-2 border-dashed border-indigo-400 rounded-2xl bg-indigo-50/30 z-10 flex items-center justify-center pointer-events-none">
                    <div className="px-6 py-3 bg-white rounded-lg shadow-xl text-indigo-600 font-bold text-sm animate-bounce">
                       Drop to Upload
                    </div>
                 </div>
               )}

               {isParsing ? (
                 <div className="flex flex-col items-center animate-in fade-in duration-500">
                   <div className="relative w-12 h-12 mb-6">
                     <div className="absolute inset-0 border-2 border-slate-200 rounded-full"></div>
                     <div className="absolute inset-0 border-2 border-indigo-600 rounded-full border-t-transparent animate-spin"></div>
                   </div>
                   <p className="text-base font-semibold text-slate-800">Processing Document</p>
                   <p className="text-xs text-slate-500 mt-1">Extracting geometric data...</p>
                 </div>
               ) : (
                 <div className="text-center max-w-lg animate-in slide-in-from-bottom-4 duration-500">
                    <div className="w-16 h-16 bg-white rounded-2xl shadow-lg shadow-slate-200/50 flex items-center justify-center mx-auto mb-6 border border-slate-100 group transition-transform hover:scale-110 duration-300">
                      <UploadCloud className="w-8 h-8 text-indigo-500" />
                    </div>
                    <h2 className="text-2xl font-bold text-slate-900 mb-3 tracking-tight">Verify Prospectus</h2>
                    <p className="text-slate-500 mb-8 leading-relaxed text-sm">
                      Drag & drop your IPO Prospectus PDF here to begin the automated audit verification process.
                    </p>
                    <button 
                      onClick={() => mainDocInputRef.current?.click()}
                      className="px-6 py-3 bg-indigo-600 text-white rounded-xl font-semibold shadow-lg shadow-indigo-500/20 hover:bg-indigo-700 hover:shadow-indigo-500/30 transition-all active:scale-95 flex items-center gap-2 mx-auto"
                    >
                      <FileUp className="w-4 h-4" />
                      Select PDF Document
                    </button>
                 </div>
               )}
             </div>
           )}
           
           {/* Progress Toast */}
           {isAnalyzing && (
             <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-4 px-5 py-2.5 bg-slate-900 text-white rounded-full text-xs font-medium shadow-2xl animate-in slide-in-from-bottom-4 ring-1 ring-white/10">
               <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
               <span className="tracking-wide">{loadingStage}</span>
               <div className="h-3 w-px bg-white/20"></div>
               <span className="font-mono text-indigo-300">{indexingProgress}%</span>
             </div>
           )}
        </div>

        {/* Right Sidebar - Only visible in PDF view mode */}
        {viewMode === 'pdf' && (
          <div 
            className={`
              fixed top-14 bottom-0 right-0 z-30 bg-white transition-transform duration-300 ease-in-out
              shadow-2xl lg:shadow-none
              ${(activeSentenceId !== null || (!isMobile && ipoDoc)) ? 'translate-x-0' : 'translate-x-full'}
              lg:relative lg:top-0 lg:translate-x-0 lg:flex lg:flex-col
              ${!ipoDoc && 'lg:hidden'}
            `}
            style={{ 
              width: `${rightSidebarWidth}px`,
              transition: isResizingRight ? 'none' : 'transform 0.3s ease-in-out, width 0.3s ease-in-out'
            }}
          >
             {/* Mobile Close */}
             {isMobile && activeSentenceId !== null && (
               <button 
                 onClick={() => setActiveSentenceId(null)}
                 className="absolute top-16 left-4 z-50 p-2 bg-white rounded-full shadow-lg border border-slate-100 text-slate-500"
               >
                 <PanelLeftClose className="w-5 h-5 rotate-180" />
               </button>
             )}

            <div className="h-full" style={{ width: `${rightSidebarWidth}px` }}>
              <RightSidebar 
                activeSentence={activeSentence}
                documents={supportingDocs}
                onApprove={handleApprove}
                onReject={handleReject}
                onDelete={handleDeleteSentence}
              />
            </div>
            
            {/* Right Resize Handle */}
            {!isMobile && ipoDoc && (
              <div
                className="absolute top-0 left-0 w-1 h-full cursor-col-resize hover:bg-indigo-400/30 bg-transparent z-50 group transition-colors"
                onMouseDown={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsResizingRight(true);
                }}
              >
                <div className="absolute top-1/2 left-0 -translate-y-1/2 -translate-x-1/2 w-1 h-16 bg-slate-300 rounded-full group-hover:bg-indigo-500 transition-colors opacity-0 group-hover:opacity-100" />
              </div>
            )}
          </div>
        )}
      </div>

      <SectionModal 
        open={showSectionModal}
        onClose={() => setShowSectionModal(false)}
        onSave={handleSaveSections}
        onAiSuggest={handleAiSuggestSections}
      />
    </div>
  );
};

export default App;
