const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = path.join(__dirname, '..', 'data', 'catalogue.db');

let db;

function getDb() {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    db.pragma('foreign_keys = ON');
    initSchema();
  }
  return db;
}

function initSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS uploads (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id),
      original_filename TEXT NOT NULL,
      file_path TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      page_count INTEGER,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sheets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      upload_id INTEGER NOT NULL REFERENCES uploads(id),
      project_id INTEGER NOT NULL REFERENCES projects(id),
      page_number INTEGER NOT NULL,
      sheet_number TEXT,
      sheet_title TEXT,
      is_detail_sheet INTEGER NOT NULL DEFAULT 0,
      user_confirmed INTEGER NOT NULL DEFAULT 0,
      processed INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS details (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sheet_id INTEGER NOT NULL REFERENCES sheets(id),
      project_id INTEGER NOT NULL REFERENCES projects(id),
      upload_id INTEGER NOT NULL REFERENCES uploads(id),
      label TEXT,
      description TEXT,
      discipline TEXT,
      sheet_number TEXT,
      sheet_title TEXT,
      image_path TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id),
      status TEXT NOT NULL DEFAULT 'pending',
      progress INTEGER NOT NULL DEFAULT 0,
      total INTEGER NOT NULL DEFAULT 0,
      message TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS details_fts USING fts5(
      label,
      description,
      sheet_number,
      sheet_title,
      content=details,
      content_rowid=id
    );

    CREATE TRIGGER IF NOT EXISTS details_ai AFTER INSERT ON details BEGIN
      INSERT INTO details_fts(rowid, label, description, sheet_number, sheet_title)
      VALUES (new.id, new.label, new.description, new.sheet_number, new.sheet_title);
    END;

    CREATE TRIGGER IF NOT EXISTS details_ad AFTER DELETE ON details BEGIN
      INSERT INTO details_fts(details_fts, rowid, label, description, sheet_number, sheet_title)
      VALUES ('delete', old.id, old.label, old.description, old.sheet_number, old.sheet_title);
    END;

    CREATE TRIGGER IF NOT EXISTS details_au AFTER UPDATE ON details BEGIN
      INSERT INTO details_fts(details_fts, rowid, label, description, sheet_number, sheet_title)
      VALUES ('delete', old.id, old.label, old.description, old.sheet_number, old.sheet_title);
      INSERT INTO details_fts(rowid, label, description, sheet_number, sheet_title)
      VALUES (new.id, new.label, new.description, new.sheet_number, new.sheet_title);
    END;
  `);
}

// Projects
function createProject(name) {
  const db = getDb();
  const result = db.prepare('INSERT INTO projects (name) VALUES (?)').run(name);
  return db.prepare('SELECT * FROM projects WHERE id = ?').get(result.lastInsertRowid);
}

function getProject(id) {
  return getDb().prepare('SELECT * FROM projects WHERE id = ?').get(id);
}

function getAllProjects() {
  return getDb().prepare('SELECT * FROM projects ORDER BY created_at DESC').all();
}

// Uploads
function createUpload(projectId, originalFilename, filePath) {
  const db = getDb();
  const result = db.prepare(
    'INSERT INTO uploads (project_id, original_filename, file_path) VALUES (?, ?, ?)'
  ).run(projectId, originalFilename, filePath);
  return db.prepare('SELECT * FROM uploads WHERE id = ?').get(result.lastInsertRowid);
}

function updateUpload(id, fields) {
  const db = getDb();
  const sets = Object.keys(fields).map(k => `${k} = ?`).join(', ');
  db.prepare(`UPDATE uploads SET ${sets} WHERE id = ?`).run(...Object.values(fields), id);
  return db.prepare('SELECT * FROM uploads WHERE id = ?').get(id);
}

function getUpload(id) {
  return getDb().prepare('SELECT * FROM uploads WHERE id = ?').get(id);
}

function getUploadsByProject(projectId) {
  return getDb().prepare('SELECT * FROM uploads WHERE project_id = ?').all(projectId);
}

// Sheets
function createSheet(data) {
  const db = getDb();
  const result = db.prepare(`
    INSERT INTO sheets (upload_id, project_id, page_number, sheet_number, sheet_title, is_detail_sheet)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(data.upload_id, data.project_id, data.page_number, data.sheet_number || null, data.sheet_title || null, data.is_detail_sheet ? 1 : 0);
  return db.prepare('SELECT * FROM sheets WHERE id = ?').get(result.lastInsertRowid);
}

function getSheetsByProject(projectId) {
  const db = getDb();
  return db.prepare(`
    SELECT s.*, u.original_filename
    FROM sheets s
    JOIN uploads u ON s.upload_id = u.id
    WHERE s.project_id = ?
    ORDER BY u.original_filename, s.page_number
  `).all(projectId);
}

function getSheetsByIds(ids) {
  if (!ids || ids.length === 0) return [];
  const db = getDb();
  const placeholders = ids.map(() => '?').join(',');
  return db.prepare(`
    SELECT s.*, u.file_path, u.original_filename
    FROM sheets s
    JOIN uploads u ON s.upload_id = u.id
    WHERE s.id IN (${placeholders})
  `).all(...ids);
}

function confirmSheets(sheetIds) {
  const db = getDb();
  const stmt = db.prepare('UPDATE sheets SET user_confirmed = 1 WHERE id = ?');
  const updateMany = db.transaction((ids) => {
    for (const id of ids) stmt.run(id);
  });
  updateMany(sheetIds);
}

function markSheetProcessed(sheetId) {
  getDb().prepare('UPDATE sheets SET processed = 1 WHERE id = ?').run(sheetId);
}

// Details
function createDetail(data) {
  const db = getDb();
  const result = db.prepare(`
    INSERT INTO details (sheet_id, project_id, upload_id, label, description, discipline, sheet_number, sheet_title, image_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    data.sheet_id, data.project_id, data.upload_id,
    data.label, data.description, data.discipline,
    data.sheet_number, data.sheet_title, data.image_path
  );
  return db.prepare('SELECT * FROM details WHERE id = ?').get(result.lastInsertRowid);
}

function searchDetails(query, discipline, projectId) {
  const db = getDb();
  let sql;
  const params = [];

  if (query && query.trim()) {
    sql = `
      SELECT d.*, p.name as project_name
      FROM details d
      JOIN projects p ON d.project_id = p.id
      WHERE d.id IN (
        SELECT rowid FROM details_fts WHERE details_fts MATCH ?
      )
    `;
    params.push(query.trim() + '*');
  } else {
    sql = `
      SELECT d.*, p.name as project_name
      FROM details d
      JOIN projects p ON d.project_id = p.id
      WHERE 1=1
    `;
  }

  if (discipline) {
    sql += ' AND d.discipline = ?';
    params.push(discipline);
  }
  if (projectId) {
    sql += ' AND d.project_id = ?';
    params.push(projectId);
  }

  sql += ' ORDER BY d.created_at DESC LIMIT 200';

  return db.prepare(sql).all(...params);
}

function getDetail(id) {
  return getDb().prepare('SELECT * FROM details WHERE id = ?').get(id);
}

// Jobs
function createJob(projectId) {
  const db = getDb();
  const result = db.prepare(
    'INSERT INTO jobs (project_id, status, progress, total, message) VALUES (?, ?, 0, 0, ?)'
  ).run(projectId, 'pending', 'Starting...');
  return db.prepare('SELECT * FROM jobs WHERE id = ?').get(result.lastInsertRowid);
}

function updateJob(id, fields) {
  const db = getDb();
  const sets = Object.keys(fields).map(k => `${k} = ?`).join(', ');
  db.prepare(`UPDATE jobs SET ${sets}, updated_at = datetime('now') WHERE id = ?`).run(...Object.values(fields), id);
}

function getJob(id) {
  return getDb().prepare('SELECT * FROM jobs WHERE id = ?').get(id);
}

module.exports = {
  getDb,
  createProject, getProject, getAllProjects,
  createUpload, updateUpload, getUpload, getUploadsByProject,
  createSheet, getSheetsByProject, getSheetsByIds, confirmSheets, markSheetProcessed,
  createDetail, searchDetails, getDetail,
  createJob, updateJob, getJob
};
