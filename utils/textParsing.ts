import { VerifiedSentence, VerificationStatus } from '../types';

export const segmentTextIntoSentences = (text: string): VerifiedSentence[] => {
  // 1. Split by double newlines to preserve original paragraphs if they exist
  const rawParagraphs = text.split(/\n\s*\n/);
  
  let globalIndex = 0;
  const allSentences: VerifiedSentence[] = [];

  // Cast Intl to any to avoid TS error for Segmenter if types are missing
  const segmenter = new (Intl as any).Segmenter('en', { granularity: 'sentence' });

  rawParagraphs.forEach((para) => {
    // If paragraph is too short, it might be a header or noise, but we keep it.
    if (!para.trim()) return;

    const segments = Array.from(segmenter.segment(para) as Iterable<any>);
    
    segments.forEach((seg: any) => {
      const cleanText = seg.segment.trim();
      if (cleanText.length > 0) {
        allSentences.push({
          id: globalIndex,
          text: cleanText,
          status: VerificationStatus.PENDING,
        });
        globalIndex++;
      }
    });

    // Insert a marker for paragraph breaks if needed, 
    // but for our data structure, we will infer paragraphs in the viewer 
    // or we can mark the last sentence of a paragraph.
    if (allSentences.length > 0) {
      allSentences[allSentences.length - 1].isParagraphEnd = true;
    }
  });
  
  return allSentences;
};

// Helper to reconstruct paragraphs for the viewer
export const groupSentencesIntoParagraphs = (sentences: VerifiedSentence[]): VerifiedSentence[][] => {
  const paragraphs: VerifiedSentence[][] = [];
  let currentPara: VerifiedSentence[] = [];

  sentences.forEach((sentence) => {
    currentPara.push(sentence);
    if (sentence.isParagraphEnd) {
      paragraphs.push(currentPara);
      currentPara = [];
    }
  });

  // Flush remaining
  if (currentPara.length > 0) {
    paragraphs.push(currentPara);
  }

  // If no paragraph structure was found (e.g. single blob text), fallback to heuristic
  if (paragraphs.length === 1 && sentences.length > 10) {
     return heuristicParagraphBreak(sentences);
  }

  return paragraphs;
};

const heuristicParagraphBreak = (sentences: VerifiedSentence[]): VerifiedSentence[][] => {
  const paragraphs: VerifiedSentence[][] = [];
  let currentPara: VerifiedSentence[] = [];
  
  sentences.forEach((sentence, i) => {
    currentPara.push(sentence);
    // Randomly break between 4-8 sentences
    const shouldBreak = currentPara.length > 6; 
    if (shouldBreak) {
      paragraphs.push(currentPara);
      currentPara = [];
    }
  });
  if (currentPara.length > 0) paragraphs.push(currentPara);
  return paragraphs;
};