const path = require('path');
const fs = require('fs');
const { execSync, spawnSync } = require('child_process');
const sharp = require('sharp');
const db = require('./db');
const { analyzeSheet } = require('./claude');

const DETAILS_DIR = path.join(__dirname, '..', 'data', 'details');

function ensureDetailsDir() {
  fs.mkdirSync(DETAILS_DIR, { recursive: true });
}

// ─── Text extraction via pdf-parse ───────────────────────────────────────────

async function extractSheetsFromPdf(uploadId) {
  const pdfParse = require('pdf-parse');

  const upload = db.getUpload(uploadId);
  if (!upload) throw new Error('Upload not found: ' + uploadId);

  const fileBuffer = fs.readFileSync(upload.file_path);

  // Parse entire PDF to get page count and per-page text
  const pageTexts = [];
  let numPages = 0;

  try {
    await pdfParse(fileBuffer, {
      pagerender: function(pageData) {
        return pageData.getTextContent().then(tc => {
          const text = tc.items.map(i => i.str).join(' ');
          pageTexts.push(text);
        });
      }
    });
    numPages = pageTexts.length;
  } catch (err) {
    // If parsing fails entirely, we can still try to get page count
    try {
      const basic = await pdfParse(fileBuffer);
      numPages = basic.numpages || 0;
    } catch (e2) {
      throw new Error('Could not parse PDF: ' + err.message);
    }
  }

  if (numPages === 0) throw new Error('PDF appears to have no pages');

  db.updateUpload(uploadId, { page_count: numPages, status: 'scanned' });

  const sheets = [];
  const hasUsefulText = pageTexts.some(t => t && t.trim().length > 30);

  for (let pageNum = 1; pageNum <= numPages; pageNum++) {
    const text = pageTexts[pageNum - 1] || '';
    const { sheetNumber, sheetTitle } = parseSheetInfo(text);
    // If the PDF has no extractable text (scanned), flag all pages as potential detail sheets
    // so the user can pick them on the review screen
    const isDetail = hasUsefulText ? isDetailSheet(sheetNumber, sheetTitle, text) : false;

    const sheet = db.createSheet({
      upload_id: uploadId,
      project_id: upload.project_id,
      page_number: pageNum,
      sheet_number: sheetNumber,
      sheet_title: sheetTitle,
      is_detail_sheet: isDetail
    });

    sheets.push(sheet);
  }

  return sheets;
}

function parseSheetInfo(text) {
  // Normalize whitespace
  const normalized = text.replace(/\s+/g, ' ').trim();

  // Match common sheet number patterns: A-501, S-601, A501, M-300, etc.
  const sheetNumRegex = /\b([ASCMEP][-]?\d{3,4}[A-Z]?)\b/i;
  const numMatch = normalized.match(sheetNumRegex);
  const sheetNumber = numMatch ? numMatch[1].toUpperCase() : null;

  // Look for title patterns - typically all-caps words
  let sheetTitle = null;

  // Try to find DETAIL SHEET / DETAILS / TYPICAL DETAILS
  const titlePatterns = [
    /\b((?:TYPICAL\s+)?DETAILS?(?:\s+SHEET)?(?:\s*[-–]\s*[A-Z0-9 ]+)?)\b/i,
    /\b((?:STRUCTURAL|ARCHITECTURAL|CIVIL|MECHANICAL|ELECTRICAL|PLUMBING)\s+DETAILS?)\b/i,
    /\b(MISCELLANEOUS\s+DETAILS?)\b/i,
    /\b([A-Z][A-Z ]{4,40}DETAIL[S]?)\b/i
  ];

  for (const pattern of titlePatterns) {
    const m = normalized.match(pattern);
    if (m) {
      sheetTitle = m[1].replace(/\s+/g, ' ').trim();
      break;
    }
  }

  // Fallback: grab a run of uppercase words near the sheet number
  if (!sheetTitle && normalized.length > 10) {
    const capsRun = normalized.match(/\b([A-Z][A-Z\s&\/]{5,50})\b/);
    if (capsRun) sheetTitle = capsRun[1].replace(/\s+/g, ' ').trim();
  }

  return { sheetNumber, sheetTitle };
}

function isDetailSheet(sheetNumber, sheetTitle, text) {
  // Check title
  if (sheetTitle && /detail/i.test(sheetTitle)) return true;

  // Check raw text
  if (/\bdetails?\b/i.test(text)) return true;

  // Check sheet number patterns: x-5xx, x-6xx (common for detail sheets)
  if (sheetNumber) {
    const numPart = sheetNumber.replace(/[^0-9]/g, '');
    if (numPart.length >= 3) {
      const hundreds = parseInt(numPart.slice(-3, -2), 10);
      if (hundreds === 5 || hundreds === 6) return true;
    }
  }

  return false;
}

// ─── Rasterization via pdftoppm ───────────────────────────────────────────────

function rasterizeSheet(pdfPath, pageNumber, outputPrefix) {
  // pdftoppm uses 1-based page numbers
  const result = spawnSync('pdftoppm', [
    '-r', '150',
    '-jpeg',
    '-f', String(pageNumber),
    '-l', String(pageNumber),
    pdfPath,
    outputPrefix
  ], { encoding: 'buffer' });

  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString() : '';
    throw new Error(`pdftoppm failed for page ${pageNumber}: ${stderr}`);
  }

  // pdftoppm names the output file like: prefix-000001.jpg
  const paddedPage = String(pageNumber).padStart(6, '0');
  const outputPath = `${outputPrefix}-${paddedPage}.jpg`;

  if (!fs.existsSync(outputPath)) {
    // Try without padding
    const files = fs.readdirSync(path.dirname(outputPrefix))
      .filter(f => f.startsWith(path.basename(outputPrefix)) && f.endsWith('.jpg'));
    if (files.length > 0) {
      return path.join(path.dirname(outputPrefix), files[0]);
    }
    throw new Error(`pdftoppm output not found at ${outputPath}`);
  }

  return outputPath;
}

// ─── Main processing pipeline ─────────────────────────────────────────────────

async function scanProject(projectId, jobId) {
  const uploads = db.getUploadsByProject(projectId);

  db.updateJob(jobId, { status: 'running', total: uploads.length, progress: 0, message: 'Scanning PDFs...' });

  let processed = 0;
  for (const upload of uploads) {
    db.updateJob(jobId, {
      message: `Scanning ${upload.original_filename}...`,
      progress: processed
    });

    try {
      await extractSheetsFromPdf(upload.id);
    } catch (err) {
      console.error('Error scanning upload', upload.id, err);
      db.updateUpload(upload.id, { status: 'error' });
    }

    processed++;
    db.updateJob(jobId, { progress: processed });
  }

  db.updateJob(jobId, { status: 'done', message: 'Scan complete.' });
}

async function processConfirmedSheets(projectId, sheetIds, jobId) {
  ensureDetailsDir();

  const sheets = db.getSheetsByIds(sheetIds);

  db.updateJob(jobId, {
    status: 'running',
    total: sheets.length,
    progress: 0,
    message: 'Starting processing...'
  });

  // Confirm sheets in DB
  db.confirmSheets(sheetIds);

  let processed = 0;
  const tempFiles = [];

  for (const sheet of sheets) {
    const label = `${sheet.sheet_number || 'Page ' + sheet.page_number} - ${sheet.sheet_title || 'Unknown'}`;
    db.updateJob(jobId, {
      progress: processed,
      message: `Processing ${label}...`
    });

    let rasterPath = null;
    try {
      // Create a temp dir for raster output
      const tempDir = path.join(__dirname, '..', 'uploads', `temp_${jobId}_${sheet.id}`);
      fs.mkdirSync(tempDir, { recursive: true });
      const outputPrefix = path.join(tempDir, 'page');

      rasterPath = rasterizeSheet(sheet.file_path, sheet.page_number, outputPrefix);
      tempFiles.push(rasterPath);
      tempFiles.push(tempDir);

      db.updateJob(jobId, {
        message: `Analyzing ${label} with Claude...`
      });

      const detailsFromClaude = await analyzeSheet(rasterPath, sheet.sheet_number, sheet.sheet_title);

      db.updateJob(jobId, {
        message: `Cropping ${detailsFromClaude.length} details from ${label}...`
      });

      // Get image dimensions
      const meta = await sharp(rasterPath).metadata();
      const imgWidth = meta.width;
      const imgHeight = meta.height;

      for (const detail of detailsFromClaude) {
        const cropX = Math.round(detail.bbox.x * imgWidth);
        const cropY = Math.round(detail.bbox.y * imgHeight);
        const cropW = Math.max(1, Math.round(detail.bbox.w * imgWidth));
        const cropH = Math.max(1, Math.round(detail.bbox.h * imgHeight));

        // Clamp to image bounds
        const safeX = Math.max(0, Math.min(cropX, imgWidth - 1));
        const safeY = Math.max(0, Math.min(cropY, imgHeight - 1));
        const safeW = Math.max(1, Math.min(cropW, imgWidth - safeX));
        const safeH = Math.max(1, Math.min(cropH, imgHeight - safeY));

        const detailFilename = `detail_${sheet.id}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}.jpg`;
        const detailPath = path.join(DETAILS_DIR, detailFilename);

        await sharp(rasterPath)
          .extract({ left: safeX, top: safeY, width: safeW, height: safeH })
          .jpeg({ quality: 82 })
          .toFile(detailPath);

        db.createDetail({
          sheet_id: sheet.id,
          project_id: sheet.project_id,
          upload_id: sheet.upload_id,
          label: detail.label,
          description: detail.description,
          discipline: detail.discipline,
          sheet_number: sheet.sheet_number,
          sheet_title: sheet.sheet_title,
          image_path: detailFilename
        });
      }

      db.markSheetProcessed(sheet.id);
    } catch (err) {
      console.error('Error processing sheet', sheet.id, err);
      db.updateJob(jobId, { message: `Error on ${label}: ${err.message}` });
    } finally {
      // Delete raster files
      if (rasterPath && fs.existsSync(rasterPath)) {
        try { fs.unlinkSync(rasterPath); } catch (e) {}
      }
    }

    processed++;
    db.updateJob(jobId, { progress: processed });
  }

  // Cleanup temp dirs
  for (const f of tempFiles) {
    try {
      if (fs.existsSync(f)) {
        const stat = fs.statSync(f);
        if (stat.isDirectory()) {
          fs.rmdirSync(f, { recursive: true });
        } else {
          fs.unlinkSync(f);
        }
      }
    } catch (e) {}
  }

  // Delete original PDFs for this project's uploads
  const uploads = db.getUploadsByProject(projectId);
  for (const upload of uploads) {
    if (fs.existsSync(upload.file_path)) {
      try {
        fs.unlinkSync(upload.file_path);
        db.updateUpload(upload.id, { status: 'completed', file_path: '' });
      } catch (e) {
        console.error('Could not delete upload', upload.file_path, e);
      }
    }
  }

  db.updateJob(jobId, {
    status: 'done',
    progress: sheets.length,
    message: 'Processing complete.'
  });
}

module.exports = { scanProject, processConfirmedSheets, extractSheetsFromPdf };
