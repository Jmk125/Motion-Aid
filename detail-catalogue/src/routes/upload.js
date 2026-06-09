'use strict';

const express = require('express');
const router = express.Router();
const path = require('path');
const multer = require('multer');
const db = require('../db');

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOADS_DIR),
  filename: (req, file, cb) => {
    const ts = Date.now();
    const safe = file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
    cb(null, `${ts}_${safe}`);
  }
});

const upload = multer({
  storage,
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf' || file.originalname.toLowerCase().endsWith('.pdf')) {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files are accepted'));
    }
  },
  limits: { fileSize: 500 * 1024 * 1024 } // 500MB
});

// POST /api/upload  (multipart, field 'files', query param: projectId)
router.post('/', upload.array('files'), (req, res) => {
  const projectId = req.body.projectId || req.query.projectId;
  if (!projectId) {
    return res.status(400).json({ error: 'projectId is required' });
  }

  const project = db.getProject(parseInt(projectId, 10));
  if (!project) {
    return res.status(404).json({ error: 'Project not found' });
  }

  if (!req.files || req.files.length === 0) {
    return res.status(400).json({ error: 'No files uploaded' });
  }

  const created = [];
  for (const file of req.files) {
    const row = db.createUpload(project.id, file.originalname, file.path);
    created.push(row);
  }

  res.json({ uploads: created });
});

module.exports = router;
