'use strict';

const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs');
const db = require('../db');

const DETAILS_DIR = path.join(__dirname, '..', '..', 'data', 'details');

// GET /api/details/:id/image  – serve the cropped JPEG
router.get('/:id/image', (req, res) => {
  const detail = db.getDetail(parseInt(req.params.id, 10));
  if (!detail) return res.status(404).json({ error: 'Detail not found' });

  const imgPath = path.join(DETAILS_DIR, detail.image_path);
  if (!fs.existsSync(imgPath)) {
    return res.status(404).json({ error: 'Image file not found' });
  }

  res.setHeader('Content-Type', 'image/jpeg');
  res.setHeader('Cache-Control', 'public, max-age=86400');
  fs.createReadStream(imgPath).pipe(res);
});

// GET /api/details/:id  – detail metadata
router.get('/:id', (req, res) => {
  const detail = db.getDetail(parseInt(req.params.id, 10));
  if (!detail) return res.status(404).json({ error: 'Detail not found' });
  res.json({ ...detail, image_url: `/api/details/${detail.id}/image` });
});

module.exports = router;
