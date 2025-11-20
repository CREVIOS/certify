import * as pdfjsLib from 'pdfjs-dist/build/pdf';

// Initialize the worker
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs';

export const extractTextFromPDF = async (file: File): Promise<string> => {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdf = await loadingTask.promise;
    
    let fullText = '';
    
    // Iterate through all pages
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      
      // Extract text items and join them with spaces
      // We verify for 'str' property to ensure it's text
      const pageText = textContent.items
        .map((item: any) => item.str)
        .join(' ');
        
      // Add double newline to simulate paragraph breaks between pages
      fullText += pageText + '\n\n';
    }

    return fullText;
  } catch (error) {
    console.error("Error extracting PDF text:", error);
    throw new Error("Failed to parse PDF file. Please ensure it is a valid text-based PDF.");
  }
};