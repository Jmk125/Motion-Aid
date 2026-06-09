const Anthropic = require('@anthropic-ai/sdk');
const fs = require('fs');

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const EXTRACT_TOOL = {
  name: 'extract_details',
  description: 'Extract all construction details found on the drawing sheet',
  input_schema: {
    type: 'object',
    properties: {
      details: {
        type: 'array',
        description: 'List of individual construction details found on the sheet',
        items: {
          type: 'object',
          properties: {
            label: {
              type: 'string',
              description: 'The detail title or name as shown on the drawing'
            },
            description: {
              type: 'string',
              description: 'Brief description of what this detail shows'
            },
            discipline: {
              type: 'string',
              enum: ['Architectural', 'Structural', 'Civil', 'Mechanical', 'Electrical', 'Plumbing', 'General'],
              description: 'Engineering discipline this detail belongs to'
            },
            bbox: {
              type: 'object',
              description: 'Bounding box as fractions of image dimensions (0.0 to 1.0)',
              properties: {
                x: { type: 'number', description: 'Left edge as fraction of image width' },
                y: { type: 'number', description: 'Top edge as fraction of image height' },
                w: { type: 'number', description: 'Width as fraction of image width' },
                h: { type: 'number', description: 'Height as fraction of image height' }
              },
              required: ['x', 'y', 'w', 'h']
            }
          },
          required: ['label', 'description', 'discipline', 'bbox']
        }
      }
    },
    required: ['details']
  }
};

async function analyzeSheet(imagePath, sheetNumber, sheetTitle) {
  const imageData = fs.readFileSync(imagePath);
  const base64Image = imageData.toString('base64');

  const disciplineHint = inferDisciplineFromSheetNumber(sheetNumber);

  const prompt = `This is an architectural/construction drawing sheet ${sheetNumber ? `numbered "${sheetNumber}"` : ''} ${sheetTitle ? `titled "${sheetTitle}"` : ''}.

Identify each distinct construction detail on this sheet. A detail is an individual drawing showing a specific construction assembly, connection, or condition — typically with a title, callout number, and border or clear separation from adjacent details.

For each detail found:
- label: the detail title or callout name exactly as shown
- description: brief plain-English description of what it depicts
- discipline: one of Architectural, Structural, Civil, Mechanical, Electrical, Plumbing, General
  ${disciplineHint ? `(The sheet number prefix suggests ${disciplineHint} discipline, but use visual content to confirm)` : ''}
- bbox: bounding box covering just that detail (including its title and border) as fractions of the full image dimensions, where {x, y} is the top-left corner and {w, h} is width and height

If the entire sheet is one large detail, return it as a single entry covering the whole sheet (bbox: {x:0, y:0, w:1, h:1}).

Call the extract_details tool with all details found.`;

  const response = await client.messages.create({
    model: 'claude-opus-4-8',
    max_tokens: 4096,
    tools: [EXTRACT_TOOL],
    tool_choice: { type: 'tool', name: 'extract_details' },
    messages: [
      {
        role: 'user',
        content: [
          {
            type: 'image',
            source: {
              type: 'base64',
              media_type: 'image/jpeg',
              data: base64Image
            }
          },
          {
            type: 'text',
            text: prompt
          }
        ]
      }
    ]
  });

  for (const block of response.content) {
    if (block.type === 'tool_use' && block.name === 'extract_details') {
      const details = block.input.details || [];
      return details.map(d => ({
        label: d.label || 'Untitled Detail',
        description: d.description || '',
        discipline: d.discipline || 'General',
        bbox: {
          x: clamp(d.bbox.x),
          y: clamp(d.bbox.y),
          w: clamp(d.bbox.w),
          h: clamp(d.bbox.h)
        }
      }));
    }
  }

  return [];
}

function clamp(v) {
  if (typeof v !== 'number' || isNaN(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function inferDisciplineFromSheetNumber(sheetNumber) {
  if (!sheetNumber) return null;
  const prefix = sheetNumber.trim().charAt(0).toUpperCase();
  const map = {
    A: 'Architectural',
    S: 'Structural',
    C: 'Civil',
    M: 'Mechanical',
    E: 'Electrical',
    P: 'Plumbing'
  };
  return map[prefix] || null;
}

module.exports = { analyzeSheet };
