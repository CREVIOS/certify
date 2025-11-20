
import React, { useRef, useState, useMemo } from 'react';
import { FileText, Database, BarChart3, ShieldCheck, Plus, Loader2, FolderGit2, Search, Zap, File, FileSpreadsheet, FileType } from 'lucide-react';
import { SupportingDocument } from '../types';
import { extractTextFromPDF } from '../utils/pdfHelpers';

interface LeftSidebarProps {
  documents: SupportingDocument[];
  onUpload: (file: File, content: string) => void;
}

const getIcon = (type: string, name: string) => {
  const ext = name.split('.').pop()?.toLowerCase();
  
  if (ext === 'pdf') return <FileText className="w-4 h-4 text-rose-500" />;
  if (['xls', 'xlsx', 'csv'].includes(ext || '')) return <FileSpreadsheet className="w-4 h-4 text-emerald-500" />;
  if (['json', 'xml'].includes(ext || '')) return <Database className="w-4 h-4 text-amber-500" />;
  
  switch (type) {
    case 'financial': return <BarChart3 className="w-4 h-4 text-indigo-500" />;
    case 'legal': return <ShieldCheck className="w-4 h-4 text-violet-500" />;
    default: return <File className="w-4 h-4 text-slate-400" />;
  }
};

const LeftSidebar: React.FC<LeftSidebarProps> = ({ documents, onUpload }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      let content = '';
      if (file.type === 'application/pdf') {
        content = await extractTextFromPDF(file);
      } else {
        content = await file.text();
      }
      onUpload(file, content);
    } catch (err) {
      console.error(err);
      alert("Failed to upload file. Please check the format.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const filteredDocs = useMemo(() => {
    if (!searchQuery) return documents;
    return documents.filter(doc => 
      doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.id.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [documents, searchQuery]);

  return (
    <div className="h-full flex flex-col bg-white w-full border-r border-slate-200/60">
      {/* Header */}
      <div className="px-5 py-5 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-sm text-slate-900 tracking-tight flex items-center gap-2">
            <FolderGit2 className="w-4 h-4 text-slate-500" />
            Data Room
          </h2>
          <div className="flex items-center gap-2">
             <span className="px-2 py-1 rounded-md bg-slate-200/50 text-[10px] font-bold text-slate-600 border border-slate-200">
               {documents.length}
             </span>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
          <input 
            type="text" 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter files..." 
            className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm placeholder:text-slate-400"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-1">
        {documents.length === 0 ? (
          <div className="mt-12 px-6 py-12 text-center border border-dashed border-slate-200 rounded-2xl bg-slate-50/50 mx-2">
            <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm border border-slate-100 ring-4 ring-slate-50">
              <FileType className="w-6 h-6 text-slate-300" />
            </div>
            <p className="text-sm font-medium text-slate-900">No Documents</p>
            <p className="text-xs text-slate-500 mt-1.5 max-w-[180px] mx-auto leading-relaxed">
              Upload supporting evidence (PDF, CSV, JSON) to cross-reference claims.
            </p>
          </div>
        ) : (
          filteredDocs.map((doc) => (
            <div 
              key={doc.id} 
              className="group relative p-3 rounded-xl bg-white hover:bg-slate-50 border border-transparent hover:border-slate-200/60 transition-all duration-200 cursor-default"
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-9 h-9 bg-slate-50 border border-slate-100 rounded-lg flex items-center justify-center group-hover:bg-white group-hover:shadow-sm transition-all">
                  {getIcon(doc.type, doc.name)}
                </div>
                <div className="flex-1 min-w-0 pt-0.5">
                  <h3 className="text-xs font-medium text-slate-700 truncate group-hover:text-slate-900 transition-colors">
                    {doc.name}
                  </h3>
                  <div className="flex items-center justify-between mt-1.5">
                     <span className="text-[10px] font-mono text-slate-400 bg-slate-100/50 px-1.5 rounded border border-slate-100/50">{doc.id}</span>
                     {doc.isIndexed ? (
                       <span className="flex items-center gap-1 text-[9px] text-emerald-600 font-medium">
                         <Zap className="w-2.5 h-2.5 fill-emerald-600" />
                         Indexed
                       </span>
                     ) : (
                       <span className="flex items-center gap-1 text-[9px] text-indigo-600 font-medium animate-pulse">
                         <Loader2 className="w-2.5 h-2.5 animate-spin" />
                         Processing
                       </span>
                     )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
        
        {documents.length > 0 && filteredDocs.length === 0 && (
           <div className="text-center py-8">
             <p className="text-xs text-slate-400">No files match "{searchQuery}"</p>
           </div>
        )}
      </div>
      
      {/* Footer Action */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/50 backdrop-blur-sm">
        <button 
          onClick={() => !isUploading && fileInputRef.current?.click()}
          disabled={isUploading}
          className="w-full py-2.5 bg-white border border-slate-200 rounded-xl shadow-sm text-xs font-semibold text-slate-700 hover:text-indigo-600 hover:border-indigo-300 hover:shadow-md hover:shadow-indigo-500/5 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed group"
        >
          <input 
            type="file" 
            ref={fileInputRef}
            className="hidden"
            accept=".txt,.json,.md,.csv,.pdf" 
            onChange={handleFileChange}
          />
          {isUploading ? (
             <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />
          ) : (
             <Plus className="w-4 h-4 text-slate-400 group-hover:text-indigo-500 transition-colors" />
          )}
          <span>{isUploading ? "Processing..." : "Add Evidence"}</span>
        </button>
      </div>
    </div>
  );
};

export default LeftSidebar;
