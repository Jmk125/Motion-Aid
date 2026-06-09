'use strict';

const express = require('express');
const router = express.Router();
const db = require('../db');

// GET /api/search?q=&discipline=&project_id=
router.get('/', (req, res) => {
  const { q, discipline, project_id } = req.query;

  const results = db.searchDetails(
    q || '',
    discipline && discipline !== 'all' ? discipline : null,
    project_id && project_id !== 'all' ? parseInt(project_id, 10) : null
  );

  const mapped = results.map(d => ({
    id: d.id,
    label: d.label,
    description: d.description,
    discipline: d.discipline,
    sheet_number: d.sheet_number,
    sheet_title: d.sheet_title,
    project_name: d.project_name,
    project_id: d.project_id,
    image_url: `/api/details/${d.id}/image`
  }));

  res.json(mapped);
});

// GET /api/search/meta  – disciplines and projects for filter dropdowns
router.get('/meta', (req, res) => {
  const projects = db.getAllProjects();
  const disciplinesRaw = db.getDb()
    .prepare("SELECT DISTINCT discipline FROM details WHERE discipline IS NOT NULL ORDER BY discipline")
    .all();
  res.json({
    projects,
    disciplines: disciplinesRaw.map(r => r.discipline)
  });
});

module.exports = router;
