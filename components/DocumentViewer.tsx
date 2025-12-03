
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { IPODocument, VerifiedSentence, VerificationStatus } from '../types';
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { ZoomIn, ZoomOut, Loader2, ChevronLeft, ChevronRight, FileText, Maximize2, CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';

// Set worker source for pdfjs-dist v5 using local worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

interface DocumentViewerProps {
  doc: IPODocument;
  onSentenceClick: (sentence: VerifiedSentence) => void;
  activeSentenceId: number | null;
  isAnalyzing: boolean;
}

interface TextItem {
  str: string;
  transform: number[]; // [scaleX, skewY, skewX, scaleY, tx, ty]
  width: number;
  height: number;
}

const DocumentViewer: React.FC<DocumentViewerProps> = ({
  doc,
  onSentenceClick,
  activeSentenceId,
  isAnalyzing,
}) => {
  const [pdfDocument, setPdfDocument] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [textItems, setTextItems] = useState<TextItem[]>([]);
  const [viewport, setViewport] = useState<{ width: number; height: number } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  
  // Tooltip State
  const [hoveredInfo, setHoveredInfo] = useState<{
    sentence: VerifiedSentence;
    x: number;
    y: number;
  } | null>(null);
  const hoverTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load the PDF document
  useEffect(() => {
    const loadPdf = async () => {
      if (!doc.file) return;
      setIsLoading(true);
      try {
        const arrayBuffer = await doc.file.arrayBuffer();
        const loadingTask = pdfjsLib.getDocument(arrayBuffer);
        const pdf = await loadingTask.promise;
        setPdfDocument(pdf);
        setCurrentPage(1);
      } catch (error) {
        console.error("Error loading PDF:", error);
      } finally {
        setIsLoading(false);
      }
    };
    loadPdf();
  }, [doc.file]);

  // Render the Page and Extract Text
  useEffect(() => {
    const renderPage = async () => {
      if (!pdfDocument || !canvasRef.current) return;

      try {
        const page = await pdfDocument.getPage(currentPage);
        const viewportInstance = page.getViewport({ scale });
        setViewport(viewportInstance);

        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');
        if (!context) return;

        // Set canvas dimensions
        canvas.height = viewportInstance.height;
        canvas.width = viewportInstance.width;

        // Render PDF to Canvas
        const renderContext = {
          canvasContext: context,
          viewport: viewportInstance,
        };
        await page.render(renderContext).promise;

        // Extract Text Content for Highlighting
        const textContent = await page.getTextContent();
        setTextItems(textContent.items as TextItem[]);

      } catch (error) {
        console.error("Error rendering page:", error);
      }
    };

    renderPage();
  }, [pdfDocument, currentPage, scale]);

  // Styling for the "Highlighter" effect
  const getHighlightStyle = (status: VerificationStatus, isActive: boolean) => {
    let bgColor = 'transparent';
    
    switch (status) {
      case VerificationStatus.VERIFIED:
        bgColor = isActive ? 'rgba(16, 185, 129, 0.5)' : 'rgba(110, 231, 183, 0.35)'; // Emerald
        break;
      case VerificationStatus.PARTIAL:
        bgColor = isActive ? 'rgba(245, 158, 11, 0.5)' : 'rgba(252, 211, 77, 0.35)'; // Amber
        break;
      case VerificationStatus.UNVERIFIED:
        bgColor = isActive ? 'rgba(244, 63, 94, 0.5)' : 'rgba(253, 164, 175, 0.35)'; // Rose
        break;
      case VerificationStatus.PENDING:
        return {};
    }

    return {
      backgroundColor: bgColor,
      mixBlendMode: 'multiply' as const, 
      cursor: 'pointer',
      borderRadius: '1px',
      // Add a subtle underline for active state to make it pop without being overwhelming
      borderBottom: isActive ? `2px solid ${status === 'VERIFIED' ? '#059669' : status === 'PARTIAL' ? '#d97706' : '#e11d48'}` : 'none'
    };
  };

  const handleMouseEnter = useCallback((e: React.MouseEvent, sentence: VerifiedSentence) => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    
    // Calculate relative position to container for tooltip
    // We use client coordinates for the fixed tooltip
    const rect = e.currentTarget.getBoundingClientRect();
    setHoveredInfo({
      sentence,
      x: rect.left + rect.width / 2,
      y: rect.top
    });
  }, []);

  const handleMouseLeave = useCallback(() => {
    hoverTimeoutRef.current = setTimeout(() => {
      setHoveredInfo(null);
    }, 150);
  }, []);

  // Memoized text layer
  const textLayer = useMemo(() => {
    if (!viewport || textItems.length === 0) return null;

    const normalize = (str: string) => str.replace(/\s+/g, ' ').trim().toLowerCase();

    return textItems.map((item, index) => {
      const tx = item.transform[4];
      const ty = item.transform[5];
      
      const [x, y] = viewport.convertToViewportPoint(tx, ty);
      const fontSize = item.transform[3] * scale; 
      
      // Simple matching strategy - can be improved with fuzzy matching
      const matchedSentence = doc.sentences.find(s => 
        s.status !== VerificationStatus.PENDING && 
        normalize(s.text).includes(normalize(item.str)) &&
        item.str.trim().length > 3 
      );
      
      const highlightStyle = matchedSentence 
        ? getHighlightStyle(matchedSentence.status, activeSentenceId === matchedSentence.id) 
        : {};

      const style: React.CSSProperties = {
        position: 'absolute',
        left: `${x}px`,
        top: `${y - fontSize}px`, 
        fontSize: `${fontSize}px`,
        fontFamily: 'sans-serif',
        color: 'transparent', 
        whiteSpace: 'pre',
        height: `${fontSize * 1.1}px`, // Slightly taller for better highlight coverage
        transform: `scale(${1})`,
        transformOrigin: '0% 0%',
        lineHeight: 1,
        ...highlightStyle
      };

      return (
        <span
          key={index}
          style={style}
          onMouseEnter={(e) => matchedSentence && handleMouseEnter(e, matchedSentence)}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => {
            e.stopPropagation();
            if (matchedSentence) onSentenceClick(matchedSentence);
          }}
        >
          {item.str}
        </span>
      );
    });
  }, [textItems, viewport, scale, doc.sentences, activeSentenceId, onSentenceClick, handleMouseEnter, handleMouseLeave]);

  const getStatusIcon = (status: VerificationStatus) => {
    switch (status) {
      case VerificationStatus.VERIFIED: return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
      case VerificationStatus.PARTIAL: return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
      case VerificationStatus.UNVERIFIED: return <XCircle className="w-3.5 h-3.5 text-rose-400" />;
      default: return <HelpCircle className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-50/50 bg-dot-pattern relative group">
      {/* Dynamic Island Toolbar */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-40 transition-all duration-300 hover:translate-y-1">
        <div className="bg-slate-900/90 backdrop-blur-xl text-white px-1.5 py-1.5 rounded-full flex items-center gap-4 shadow-2xl border border-white/10 ring-1 ring-black/20">
           
           <div className="flex items-center gap-2 pl-3 pr-2">
              <FileText className="w-3.5 h-3.5 text-indigo-400" />
              <span className="text-xs font-medium text-slate-200 truncate max-w-[150px]">{doc.title}</span>
           </div>

           <div className="h-4 w-px bg-white/10"></div>

           <div className="flex items-center gap-1">
             <button 
               onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
               disabled={currentPage <= 1}
               className="p-1.5 hover:bg-white/10 rounded-full disabled:opacity-30 transition-colors text-slate-300 hover:text-white"
             >
               <ChevronLeft className="w-4 h-4" />
             </button>
             <span className="text-xs font-mono w-14 text-center text-slate-300">
               {currentPage} <span className="text-slate-500">/</span> {pdfDocument?.numPages || '-'}
             </span>
             <button 
               onClick={() => setCurrentPage(p => Math.min(pdfDocument?.numPages || 1, p + 1))}
               disabled={!pdfDocument || currentPage >= pdfDocument.numPages}
               className="p-1.5 hover:bg-white/10 rounded-full disabled:opacity-30 transition-colors text-slate-300 hover:text-white"
             >
               <ChevronRight className="w-4 h-4" />
             </button>
           </div>

           <div className="h-4 w-px bg-white/10"></div>

           <div className="flex items-center gap-1 pr-1">
              <button onClick={() => setScale(s => Math.max(0.5, s - 0.1))} className="p-1.5 hover:bg-white/10 rounded-full text-slate-300 hover:text-white"><ZoomOut className="w-4 h-4" /></button>
              <span className="text-xs font-mono w-10 text-center text-slate-300">{Math.round(scale * 100)}%</span>
              <button onClick={() => setScale(s => Math.min(3, s + 0.1))} className="p-1.5 hover:bg-white/10 rounded-full text-slate-300 hover:text-white"><ZoomIn className="w-4 h-4" /></button>
            </div>
        </div>
      </div>

      {/* Main Canvas */}
      <div 
        className="flex-1 overflow-auto p-8 md:p-16 flex justify-center relative custom-scrollbar"
        ref={containerRef}
      >
         {/* Analysis Overlay */}
         {isAnalyzing && (
          <div className="fixed inset-0 bg-white/30 backdrop-blur-[2px] z-30 pointer-events-none"></div>
        )}

        {/* PDF Page */}
        {pdfDocument ? (
          <div 
            className="relative bg-white shadow-[0_20px_50px_-12px_rgba(0,0,0,0.15)] transition-all duration-300 ring-1 ring-slate-200"
            style={{ 
              width: viewport ? viewport.width : 'auto', 
              height: viewport ? viewport.height : 'auto',
              borderRadius: '2px'
            }}
          >
            <canvas ref={canvasRef} className="block rounded-[2px]" />
            <div className="absolute inset-0 overflow-hidden select-none rounded-[2px]">
              {textLayer}
            </div>
          </div>
        ) : (
           <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-4">
             {isLoading ? (
                <>
                  <Loader2 className="animate-spin w-10 h-10 text-indigo-500" />
                  <span className="text-sm font-medium text-slate-500">Rendering Document...</span>
                </>
             ) : (
                <>
                  <div className="w-20 h-20 bg-slate-100 rounded-full flex items-center justify-center">
                     <Maximize2 className="w-8 h-8 text-slate-300" />
                  </div>
                  <span className="text-sm font-medium text-slate-400">No document loaded</span>
                </>
             )}
           </div>
        )}
      </div>

      {/* Hover Tooltip - Enhanced */}
      {hoveredInfo && (
        <div 
          className="fixed z-50 px-4 py-3.5 bg-slate-900/95 text-white text-xs rounded-lg shadow-2xl pointer-events-none transform -translate-x-1/2 -translate-y-full -mt-4 w-[300px] border border-white/10 backdrop-blur-md ring-1 ring-black/40 animate-in fade-in zoom-in-95 duration-200"
          style={{ 
            left: hoveredInfo.x, 
            top: hoveredInfo.y,
          }}
        >
           <div className="flex items-center gap-2.5 mb-3 border-b border-white/10 pb-2.5">
             {getStatusIcon(hoveredInfo.sentence.status)}
             <span className={`font-bold uppercase tracking-wider text-[10px] ${
               hoveredInfo.sentence.status === VerificationStatus.VERIFIED ? 'text-emerald-400' :
               hoveredInfo.sentence.status === VerificationStatus.PARTIAL ? 'text-amber-400' : 'text-rose-400'
             }`}>
               {hoveredInfo.sentence.status}
             </span>
             <div className="ml-auto text-[9px] font-mono text-slate-400 bg-white/5 px-1.5 py-0.5 rounded">
               CONF: {hoveredInfo.sentence.confidence}%
             </div>
           </div>
           <p className="line-clamp-3 text-slate-300 leading-relaxed font-medium">
             &quot;{hoveredInfo.sentence.text}&quot;
           </p>
           
           {/* Arrow */}
           <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[6px] border-t-slate-900/95"></div>
        </div>
      )}
    </div>
  );
};

export default DocumentViewer;
