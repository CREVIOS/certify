import { Queue, Worker, Job } from 'bullmq';
import { processDocument, ProcessingJobData } from './documentProcessor';

// Connection to the Redis service defined in docker-compose
const redisConnection = {
  host: 'localhost',
  port: 6379,
};

// 1. The Queue (Producer)
export const documentQueue = new Queue('document-indexing', { 
  connection: redisConnection,
  defaultJobOptions: {
    attempts: 3, // SOTA: Auto-retry on failure
    backoff: {
      type: 'exponential', // SOTA: Exponential backoff to be kind to APIs
      delay: 1000,
    },
    removeOnComplete: true,
  }
});

// 2. The Worker (Consumer)
// This runs in the background, picking up jobs independently of the main API thread
const worker = new Worker<ProcessingJobData>(
  'document-indexing',
  async (job: Job) => {
    console.log(`Processing job ${job.id} attempt ${job.attemptsMade + 1}`);
    
    // Report progress to the UI (if connected via socket)
    await job.updateProgress(10);
    
    const result = await processDocument(job.data);
    
    await job.updateProgress(100);
    return result;
  },
  { 
    connection: redisConnection,
    concurrency: 5 // SOTA: Process 5 documents simultaneously
  }
);

// 3. Events
worker.on('completed', (job) => {
  console.log(`Job ${job.id} has completed!`);
});

worker.on('failed', (job, err) => {
  console.error(`Job ${job?.id} has failed with ${err.message}`);
});

// Helper to add jobs
export const addToQueue = async (docData: ProcessingJobData) => {
  return await documentQueue.add('index-pdf', docData);
};
