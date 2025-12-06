import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

// Initialize the worker for pdfjs-dist v5 using local worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

export const extractTextFromPDF = async (file: File): Promise<string> => {
  try {
    const arrayBuffer = await file.arrayBuffer();
    
    // Create loading task with additional options for better compatibility
    const loadingTask = pdfjsLib.getDocument({ 
      data: arrayBuffer,
      useSystemFonts: true,
      disableFontFace: false,
    });
    
    const pdf = await loadingTask.promise;
    
    let fullText = '';
    
    // Iterate through all pages
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      
      // Extract text items and join them with proper spacing
      const pageText = textContent.items
        .map((item) => {
          // Handle both text items and marked content items
          if ('str' in item) {
            return (item as { str: string }).str;
          }
          return '';
        })
        .filter(Boolean)
        .join(' ');
        
      // Add double newline to simulate paragraph breaks between pages
      fullText += pageText + '\n\n';
    }

    // Check if we got any text
    if (!fullText.trim()) {
      console.warn("PDF appears to be image-based or contains no extractable text");
      return '[This PDF appears to be image-based. Text extraction is limited.]';
    }

    return fullText;
  } catch (error) {
    console.error("Error extracting PDF text:", error);
    
    // Provide more specific error messages
    if (error instanceof Error) {
      if (error.message.includes('Invalid PDF')) {
        throw new Error("Invalid PDF file. The file may be corrupted.");
      }
      if (error.message.includes('password')) {
        throw new Error("This PDF is password protected. Please provide an unprotected PDF.");
      }
    }
    
    throw new Error("Failed to parse PDF file. Please ensure it is a valid text-based PDF.");
  }
};