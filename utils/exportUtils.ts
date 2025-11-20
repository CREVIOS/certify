import { VerifiedSentence, SupportingDocument } from '../types';

export const downloadVerificationReport = (
  sentences: VerifiedSentence[],
  documents: SupportingDocument[]
) => {
  // Define headers
  const headers = [
    "ID",
    "Claim Text",
    "Verification Status",
    "Confidence Score",
    "Source Document",
    "Evidence Citation",
    "AI Reasoning"
  ];

  // Map data to rows
  const rows = sentences.map(s => {
    const sourceDoc = documents.find(d => d.id === s.citationSourceId);
    
    // Escape quotes for CSV format
    const escape = (str: string) => `"${(str || '').replace(/"/g, '""')}"`;

    return [
      s.id,
      escape(s.text),
      s.status,
      `${s.confidence || 0}%`,
      escape(sourceDoc?.name || 'N/A'),
      escape(s.citationText || ''),
      escape(s.reasoning || '')
    ].join(',');
  });

  // Combine headers and rows
  const csvContent = [headers.join(','), ...rows].join('\n');

  // Create blob and download link
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `IPO_Verification_Report_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};