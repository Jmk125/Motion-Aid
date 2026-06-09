'use strict';

require('dotenv').config();

const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3051;

// Ensure required directories exist
const BASE = __dirname;
fs.mkdirSync(path.join(BASE, 'uploads'), { recursive: true });
fs.mkdirSync(path.join(BASE, 'data', 'details'), { recursive: true });

// Body parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static frontend
app.use(express.static(path.join(BASE, 'public')));

// API routes
app.use('/api/projects', require('./src/routes/projects'));
app.use('/api/upload', require('./src/routes/upload'));
app.use('/api/process', require('./src/routes/process'));
app.use('/api/search', require('./src/routes/search'));
app.use('/api/details', require('./src/routes/details'));
app.use('/api/jobs', require('./src/routes/jobs'));

// SPA fallback: serve index.html for unknown routes
app.get('*', (req, res) => {
  res.sendFile(path.join(BASE, 'public', 'index.html'));
});

// Global error handler
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: err.message || 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`Detail Catalogue running at http://localhost:${PORT}`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn('WARNING: ANTHROPIC_API_KEY is not set. Claude analysis will fail.');
  }
});
