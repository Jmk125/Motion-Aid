'use strict';

const express = require('express');
const router = express.Router();
const db = require('../db');

// GET /api/jobs/:jobId/stream  – SSE endpoint for job progress
router.get('/:jobId/stream', (req, res) => {
  const jobId = parseInt(req.params.jobId, 10);

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const sendEvent = (data) => {
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  let interval = null;
  let closed = false;

  const poll = () => {
    if (closed) return;
    const job = db.getJob(jobId);
    if (!job) {
      sendEvent({ status: 'error', message: 'Job not found' });
      res.end();
      return;
    }

    sendEvent({
      status: job.status,
      progress: job.progress,
      total: job.total,
      message: job.message
    });

    if (job.status === 'done' || job.status === 'error') {
      clearInterval(interval);
      res.end();
    }
  };

  // Send first event immediately
  poll();

  interval = setInterval(poll, 500);

  req.on('close', () => {
    closed = true;
    clearInterval(interval);
  });
});

module.exports = router;
