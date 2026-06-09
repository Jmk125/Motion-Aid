# Detail Catalogue

A Node.js web application for construction/architecture firms to catalogue construction details extracted from PDF drawing sets using Claude AI (vision).

## Features

- Upload single or multiple PDF drawing sets per project
- Automatically detects "detail sheets" using PDF text extraction
- User reviews and confirms which sheets to process
- Claude AI (claude-opus-4-8) analyzes each sheet, identifies individual details, and returns bounding boxes + labels + discipline
- Each detail is cropped and saved as a compressed JPEG (quality 82)
- Original PDFs and full-page rasters are deleted after processing (optimized for Raspberry Pi)
- Full-text search by keyword, filterable by discipline and project
- Server-Sent Events (SSE) for real-time processing progress

## Requirements

- **Node.js** 18+
- **poppler-utils** (for `pdftoppm`)
- An **Anthropic API key**

## Setup

### 1. Install system dependencies

**Debian / Ubuntu / Raspberry Pi OS:**
```bash
sudo apt update && sudo apt install -y poppler-utils
```

**macOS (Homebrew):**
```bash
brew install poppler
```

**Verify installation:**
```bash
pdftoppm -h
```

### 2. Clone / navigate to the project

```bash
cd detail-catalogue
```

### 3. Install Node.js dependencies

```bash
npm install
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your Anthropic API key:
```
ANTHROPIC_API_KEY=sk-ant-...
PORT=3000
```

### 5. Start the server

```bash
npm start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Usage

1. **Click "+ New Project"** in the top-right corner
2. **Enter a project name** (e.g. "456 Main Street – SD Package")
3. **Upload PDF drawing sets** — drag and drop or click to select. Multiple files supported.
4. Wait for the **scan** to complete (text extraction detects sheet numbers and titles)
5. On the **Review Sheets** page, check which sheets should be processed. Detail sheets are pre-selected.
6. Click **"Process Selected Sheets"** — Claude AI analyzes each sheet and extracts individual details
7. When done, you're redirected to the **search page** where you can browse and search all extracted details

## Architecture

```
detail-catalogue/
  server.js           Main Express server
  src/
    db.js             SQLite database (better-sqlite3) with all queries
    processor.js      PDF scanning pipeline + Claude processing pipeline
    claude.js         Anthropic SDK calls with tool_use for structured extraction
    routes/
      projects.js     GET/POST /api/projects
      upload.js       POST /api/upload (multipart PDF upload)
      process.js      POST /api/process/scan/:id and /api/process/confirm/:id
      search.js       GET /api/search (full-text search with filters)
      details.js      GET /api/details/:id/image (serve cropped JPEG)
      jobs.js         GET /api/jobs/:id/stream (SSE job progress)
  public/
    index.html        Main search/browse UI
    upload.html       Project creation + file upload wizard
    review.html       Sheet selection before AI processing
    style.css         Vanilla CSS (no framework)
    app.js            Shared utility functions
  data/
    catalogue.db      SQLite database (auto-created)
    details/          Cropped detail JPEG images (auto-created)
  uploads/            Temporary PDF storage (deleted after processing)
```

## Database Schema

| Table    | Key columns |
|----------|-------------|
| projects | id, name, created_at |
| uploads  | id, project_id, original_filename, file_path, status, page_count |
| sheets   | id, upload_id, project_id, page_number, sheet_number, sheet_title, is_detail_sheet, user_confirmed, processed |
| details  | id, sheet_id, project_id, label, description, discipline, sheet_number, sheet_title, image_path |
| jobs     | id, project_id, status, progress, total, message |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key for Claude |
| `PORT` | `3000` | HTTP port to listen on |

## Notes for Raspberry Pi

- The app is designed to minimize storage: original PDFs and full-page rasters are deleted after processing
- Only compressed JPEG crops (~quality 82) are retained
- SQLite database is stored in `data/catalogue.db`
- Recommended: at least 2 GB free disk space during processing large drawing sets

## Troubleshooting

**`pdftoppm: command not found`** – Install poppler-utils: `sudo apt install poppler-utils`

**Claude API errors** – Ensure `ANTHROPIC_API_KEY` is set correctly in `.env`

**"pdfjs-dist not available"** – Run `npm install` to install all dependencies

**Empty detail images** – Claude may return bounding boxes of 0 width/height; these are clamped to at least 1px. Check that the rasterized image exists before reporting a bug.
