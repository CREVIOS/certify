import React, { useState, useEffect } from 'react';
import { Section } from '../types';
import { X, Sparkles, Plus, Trash2, Loader2 } from 'lucide-react';

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (sections: Section[]) => void;
  onAiSuggest: () => Promise<Section[]>;
}

const emptyRow = (): Section => ({ title: '', start_page: 1, end_page: 1 });

const SectionModal: React.FC<Props> = ({ open, onClose, onSave, onAiSuggest }) => {
  const [rows, setRows] = useState<Section[]>([emptyRow()]);
  const [isSaving, setIsSaving] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);

  useEffect(() => {
    if (open) {
      setRows([emptyRow()]);
    }
  }, [open]);

  if (!open) return null;

  const updateRow = (idx: number, field: keyof Section, value: string | number) => {
    setRows(prev =>
      prev.map((row, i) => (i === idx ? { ...row, [field]: field.includes('page') ? Number(value) : value } : row))
    );
  };

  const addRow = () => setRows(prev => [...prev, emptyRow()]);

  const removeRow = (idx: number) => setRows(prev => prev.filter((_, i) => i !== idx));

  const handleSave = () => {
    const filtered = rows.filter(r => r.title.trim());
    setIsSaving(true);
    onSave(filtered);
    setIsSaving(false);
    onClose();
  };

  const handleSuggest = async () => {
    setIsSuggesting(true);
    try {
      const suggestions = await onAiSuggest();
      if (suggestions.length) setRows(suggestions);
    } catch (e) {
      console.error(e);
      alert('AI sectioning failed. Please try manual.');
    } finally {
      setIsSuggesting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full overflow-hidden border border-slate-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400 font-semibold">IPO Sectioning</p>
            <h3 className="text-lg font-semibold text-slate-900">Split the prospectus into sections</h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-slate-100 text-slate-500 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-3 max-h-[60vh] overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-600">
              Enter title and page range, or let AI draft sections you can edit.
            </div>
            <button
              onClick={handleSuggest}
              disabled={isSuggesting}
              className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-md bg-indigo-600 text-white shadow-sm hover:bg-indigo-500 disabled:opacity-60"
            >
              {isSuggesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              AI Suggest
            </button>
          </div>

          <div className="grid grid-cols-12 gap-3 text-xs font-semibold text-slate-500 px-2">
            <span className="col-span-6">Title</span>
            <span className="col-span-2">Start Page</span>
            <span className="col-span-2">End Page</span>
            <span className="col-span-2 text-right">Actions</span>
          </div>

          {rows.map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-3 px-2 py-2 bg-slate-50 rounded-lg border border-slate-100">
              <input
                className="col-span-6 px-3 py-2 text-sm rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
                placeholder="e.g. Risk Factors"
                value={row.title}
                onChange={(e) => updateRow(idx, 'title', e.target.value)}
              />
              <input
                type="number"
                min={1}
                className="col-span-2 px-3 py-2 text-sm rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
                value={row.start_page}
                onChange={(e) => updateRow(idx, 'start_page', e.target.value)}
              />
              <input
                type="number"
                min={row.start_page}
                className="col-span-2 px-3 py-2 text-sm rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
                value={row.end_page}
                onChange={(e) => updateRow(idx, 'end_page', e.target.value)}
              />
              <div className="col-span-2 flex items-center justify-end">
                <button
                  onClick={() => removeRow(idx)}
                  className="p-2 rounded-md hover:bg-rose-50 text-rose-500 transition-colors"
                  aria-label="Remove section"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}

          <button
            onClick={addRow}
            className="inline-flex items-center gap-2 text-indigo-600 text-sm font-semibold px-2 py-1 rounded-md hover:bg-indigo-50"
          >
            <Plus className="w-4 h-4" />
            Add Section
          </button>
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            You can edit these later. Section info is stored with the document metadata.
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-semibold text-slate-600 rounded-md hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-md shadow-sm hover:bg-indigo-500 disabled:opacity-70"
            >
              {isSaving ? 'Saving...' : 'Save Sections'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SectionModal;
