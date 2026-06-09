'use strict';

const express = require('express');
const router = express.Router();
const db = require('../db');
const { scanProject, processConfirmedSheets } = require('../processor');

// POST /api/process/scan/:projectId
// Trigger text extraction / sheet detection for all uploaded PDFs of a project
router.post('/scan/:projectId', async (req, res) => {
  const projectId = parseInt(req.params.projectId, 10);
  const project = db.getProject(projectId);
  if (!project) return res.status(404).json({ error: 'Project not found' });

  const uploads = db.getUploadsByProject(projectId);
  if (!uploads.length) {
    return res.status(400).json({ error: 'No uploads found for this project' });
  }

  const job = db.createJob(projectId);

  // Run in background
  setImmediate(async () => {
    try {
      await scanProject(projectId, job.id);
    } catch (err) {
      console.error('Scan error', err);
      db.updateJob(job.id, { status: 'error', message: err.message });
    }
  });

  res.json({ jobId: job.id });
});

// POST /api/process/confirm/:projectId
// Confirm selected sheet IDs and trigger Claude processing
router.post('/confirm/:projectId', async (req, res) => {
  const projectId = parseInt(req.params.projectId, 10);
  const project = db.getProject(projectId);
  if (!project) return res.status(404).json({ error: 'Project not found' });

  const { sheetIds } = req.body;
  if (!Array.isArray(sheetIds) || sheetIds.length === 0) {
    return res.status(400).json({ error: 'sheetIds array is required' });
  }

  const ids = sheetIds.map(id => parseInt(id, 10)).filter(n => !isNaN(n));
  if (ids.length === 0) {
    return res.status(400).json({ error: 'No valid sheet IDs provided' });
  }

  const job = db.createJob(projectId);

  // Run in background
  setImmediate(async () => {
    try {
      await processConfirmedSheets(projectId, ids, job.id);
    } catch (err) {
      console.error('Processing error', err);
      db.updateJob(job.id, { status: 'error', message: err.message });
    }
  });

  res.json({ jobId: job.id });
});

module.exports = router;
