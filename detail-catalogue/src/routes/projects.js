const express = require('express');
const router = express.Router();
const db = require('../db');

// POST /api/projects - create a new project
router.post('/', (req, res) => {
  const { name } = req.body;
  if (!name || !name.trim()) {
    return res.status(400).json({ error: 'Project name is required' });
  }
  const project = db.createProject(name.trim());
  res.json(project);
});

// GET /api/projects - list all projects
router.get('/', (req, res) => {
  const projects = db.getAllProjects();
  res.json(projects);
});

// GET /api/projects/:id - get a single project
router.get('/:id', (req, res) => {
  const project = db.getProject(req.params.id);
  if (!project) return res.status(404).json({ error: 'Project not found' });
  res.json(project);
});

// GET /api/projects/:id/sheets - get all sheets for a project
router.get('/:id/sheets', (req, res) => {
  const project = db.getProject(req.params.id);
  if (!project) return res.status(404).json({ error: 'Project not found' });
  const sheets = db.getSheetsByProject(req.params.id);
  res.json(sheets);
});

module.exports = router;
