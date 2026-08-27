const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');

const ROOT = process.cwd();
const CONTENT_DIR = path.join(ROOT, 'content');
const PAGES_PATH = path.join(CONTENT_DIR, 'pages.json');
const TEXTS_PATH = path.join(CONTENT_DIR, 'i18n', 'sw-TZ', 'texts.json');
const PDF_SOURCE = path.join(
  ROOT,
  'HISABATI DRS 4 PB (SEPT 2025).pdf'
);
const OUT_DIR = path.join(ROOT, 'artifacts', 'page-style-audit');
const OUT_HTML_DIR = path.join(OUT_DIR, 'html');
const OUT_PDF_DIR = path.join(OUT_DIR, 'source');
const OUT_DIFF_DIR = path.join(OUT_DIR, 'diff');

const pages = JSON.parse(fs.readFileSync(PAGES_PATH, 'utf8'));
const texts = JSON.parse(fs.readFileSync(TEXTS_PATH, 'utf8'));

const args = process.argv.slice(2).reduce((acc, arg) => {
  const match = arg.match(/^--([^=]+)=(.*)$/);
  if (match) {
    acc[match[1]] = match[2];
  } else if (arg === '--no-pdf' || arg === '--no-html') {
    acc[arg.replace(/^--/, '')] = 'true';
  }
  return acc;
}, {});

const startPage = Number(args.start || 1);
const limit = Number(args.limit || pages.length);
const parseBool = (value, fallback) => {
  if (value === undefined) return fallback;
  const normalized = String(value).toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return fallback;
};

const includePdf = parseBool(args['no-pdf'], false) ? false : true;
const includeHtml = parseBool(args['no-html'], false) ? false : true;
const includeCompare = parseBool(args.compare, true);
const checkOrder = parseBool(args['strict-order'], true);

const TARGET_PAGES = pages
  .filter((page) => /^index\.html$|^pg\d+_sec001\.html$/.test(page.href))
  .slice(startPage - 1, startPage - 1 + limit);

function commandExists(command) {
  const result = spawnSync('where.exe', [command], {
    stdio: ['ignore', 'ignore', 'ignore'],
    shell: false,
    windowsHide: true,
  });
  return result.status === 0;
}

function runCommand(command, args, cwd = ROOT) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
    windowsHide: true,
    encoding: 'utf8',
  });
  const code = result.status ?? 1;
  const stdout = (result.stdout || '').toString();
  const stderr = (result.stderr || '').toString();
  return { code, stdout, stderr, ok: code === 0 || code === 1 };
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function stripHtml(text) {
  return text
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function decodeHtmlEntities(value) {
  const text = String(value || '');
  const namedEntities = {
    '&nbsp;': ' ',
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&apos;': "'",
    '&ldquo;': '"',
    '&rdquo;': '"',
    '&lsquo;': "'",
    '&rsquo;': "'",
    '&mdash;': '—',
    '&ndash;': '–',
    '&hellip;': '...',
    '&copy;': '©',
    '&reg;': '®',
  };

  return text
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) =>
      String.fromCodePoint(Number.parseInt(hex, 16))
    )
    .replace(/&#([0-9]+);/g, (_, num) => String.fromCodePoint(Number.parseInt(num, 10)))
    .replace(/&[a-zA-Z]+;/g, (entity) => namedEntities[entity] ?? entity);
}

function normalizeForComparison(value) {
  return decodeHtmlEntities(value || '')
    .toLowerCase()
    .replace(/[\u200b\u00a0]+/g, ' ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function compareTextOrder(htmlText, transcriptText) {
  const htmlTokens = normalizeForComparison(htmlText).split(' ').filter(Boolean);
  const transcriptTokens = normalizeForComparison(transcriptText).split(' ').filter(Boolean);

  if (!htmlTokens.length || !transcriptTokens.length) {
    return { similar: false, score: 0, reason: 'empty-content' };
  }

  const compareCount = Math.min(80, Math.max(12, Math.floor(transcriptTokens.length * 0.7)));
  const left = htmlTokens.slice(0, compareCount);
  const right = transcriptTokens.slice(0, compareCount);
  if (!left.length || !right.length) {
    return { similar: false, score: 0, reason: 'small-sample' };
  }

  const leftSet = new Set(left);
  const overlap = right.filter((token) => leftSet.has(token)).length;
  const maxBase = Math.max(left.length, right.length);
  const overlapRatio = maxBase === 0 ? 0 : overlap / maxBase;

  let prefixMatches = 0;
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
    if (left[i] === right[i]) {
      prefixMatches += 1;
    } else {
      break;
    }
  }

  const prefixRatio =
    Math.min(left.length, right.length) === 0
      ? 0
      : prefixMatches / Math.min(left.length, right.length);

  const score = overlapRatio * 0.65 + prefixRatio * 0.35;
  if (left.length > 0 && overlapRatio < 0.38 && prefixRatio < 0.35) {
    return {
      similar: false,
      score,
      reason: `low-overlap (overlap=${overlapRatio.toFixed(3)}, prefix=${prefixRatio.toFixed(3)})`,
    };
  }

  return { similar: true, score, reason: null };
}

function pickBrowserBinary() {
  const explicit = process.env.BROWSER_BIN;
  if (explicit && fs.existsSync(explicit)) return explicit;

  const fallbackPaths = [
    'chrome',
    'msedge',
    path.join(
      process.env.ProgramFiles || 'C:\\Program Files',
      'Google',
      'Chrome',
      'Application',
      'chrome.exe'
    ),
    path.join(
      process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)',
      'Google',
      'Chrome',
      'Application',
      'chrome.exe'
    ),
    path.join(
      process.env.ProgramFiles || 'C:\\Program Files',
      'Microsoft',
      'Edge',
      'Application',
      'msedge.exe'
    ),
  ];

  for (const candidate of fallbackPaths) {
    if (!candidate) continue;
    if (candidate.includes('\\') || candidate.includes('/')) {
      if (fs.existsSync(candidate)) return candidate;
      continue;
    }
    if (commandExists(candidate)) return candidate;
  }

  return null;
}

function capturePdfPage(pageNumber, fileName) {
  if (!commandExists('pdftoppm')) {
    return { status: 'missing_tool', path: null, reason: 'pdftoppm not installed' };
  }
  if (!fs.existsSync(PDF_SOURCE)) {
    return { status: 'missing_file', path: null, reason: 'pdf source file not found' };
  }

  const outBase = path.join(OUT_PDF_DIR, `${fileName}`);
  const result = runCommand('pdftoppm', [
    '-f',
    String(pageNumber),
    '-l',
    String(pageNumber),
    '-png',
    '-r',
    '170',
    '-singlefile',
    PDF_SOURCE,
    outBase,
  ]);
  if (!result.ok) {
    return {
      status: 'failed',
      path: null,
      reason: result.stderr || result.stdout || 'pdftoppm failed',
      command: `pdftoppm -f ${pageNumber} -l ${pageNumber}`,
    };
  }

  const outputPath = `${outBase}.png`;
  if (fs.existsSync(outputPath)) {
    return { status: 'ok', path: outputPath };
  }

  const fallbackPath = fs
    .readdirSync(OUT_PDF_DIR)
    .map((name) => path.join(OUT_PDF_DIR, name))
    .find((p) => {
      const basename = path.basename(p);
      return basename.startsWith(`${fileName}-`) && /\.(png|jpg|jpeg)$/i.test(basename);
    });

  if (fallbackPath) return { status: 'ok', path: fallbackPath };
  return { status: 'missing_output', path: null, reason: 'pdf screenshot output was not created' };
}

function captureHtmlPage(htmlPath, outPath) {
  if (!includeHtml) {
    return { status: 'skipped', path: null, reason: 'html capture disabled' };
  }

  const browser = pickBrowserBinary();
  if (!browser) {
    return { status: 'missing_tool', path: null, reason: 'chrome/msedge not found' };
  }

  const result = runCommand(browser, [
    '--headless',
    '--disable-gpu',
    '--hide-scrollbars',
    '--no-sandbox',
    '--screenshot=' + outPath,
    '--window-size=1400,2100',
    '--virtual-time-budget=5000',
    pathToFileURL(htmlPath).href,
  ]);

  if (!result.ok || !fs.existsSync(outPath)) {
    return {
      status: 'failed',
      path: null,
      reason: result.stderr || result.stdout || 'html capture failed',
      command: `${path.basename(browser)} --headless ... --screenshot`,
    };
  }
  return { status: 'ok', path: outPath };
}

function compareImages(baseImage, generatedImage, outDiffPath) {
  if (!includeCompare) {
    return { status: 'disabled', diffPixels: null };
  }
  if (!commandExists('magick')) {
    return { status: 'missing_tool', diffPixels: null };
  }
  if (!baseImage || !generatedImage) {
    return { status: 'missing_input', diffPixels: null };
  }
  if (!fs.existsSync(baseImage) || !fs.existsSync(generatedImage)) {
    return { status: 'missing_input', diffPixels: null };
  }

  const compare = runCommand('magick', [
    'compare',
    '-metric',
    'AE',
    baseImage,
    generatedImage,
    outDiffPath,
  ]);

  if (compare.code !== 0 && compare.code !== 1) {
    return { status: 'failed', diffPixels: null, reason: compare.stderr || compare.stdout };
  }

  const metricMatch = (compare.stderr || compare.stdout || '').match(/(\d+(?:\.\d+)?)/);
  const value = metricMatch ? Number(metricMatch[1]) : null;
  return {
    status: value === null ? 'unparseable' : 'ok',
    diffPixels: value,
    reason: value === null ? (compare.stderr || compare.stdout) : null,
  };
}

function analyzeHtml(pageFileName) {
  const html = fs.readFileSync(path.join(ROOT, pageFileName), 'utf8');
  const styleMatch = html.match(/<style>([\s\S]*?)<\/style>/i);
  const styleCss = styleMatch ? styleMatch[1] : '';
  const textMatch = html.match(/<div[^>]*class=\"pdf-text\"[^>]*>([\s\S]*?)<\/div>/i);
  const textBlock = textMatch ? textMatch[1] : '';
  const textPlain = textMatch ? stripHtml(textMatch[0]) : '';
  const paragraphTags = textBlock ? textBlock.match(/<p\b/gi) : [];
  const paragraphCount = paragraphTags ? paragraphTags.length : 0;
  const dataIdMatch = html.match(/<div[^>]*class=\"pdf-text\"[^>]*data-id=\"([^\"]+)\"/i);
  const textId = dataIdMatch ? dataIdMatch[1] : '';
  const hasHeading = /<h2[^>]*class=\"pdf-page-title\"/i.test(html);
  const sectionIdMatch = html.match(/data-section-id=\"([^\"]+)\"/i);
  const sectionId = sectionIdMatch ? sectionIdMatch[1] : '';

  const fontSizes = [
    ...new Set(
      (styleCss.match(/font-size:\s*[^;\n}]+/gi) || []).map((entry) =>
        entry.replace(/font-size:\s*/i, '').trim()
      )
    ),
  ].join(', ');
  const colors = [
    ...new Set(
      (styleCss.match(/(?:color|background(?:-color)?):\s*[^;\n}]+/gi) || []).map((entry) =>
        entry.replace(/(?:color|background(?:-color)?):\s*/i, '').trim()
      )
    ),
  ].join(', ');

  const transcript = textId && texts[textId] ? texts[textId] : '';
  const transcriptNormalized = transcript ? transcript.replace(/\r\n/g, '\n').replace(/\r/g, '\n') : '';
  const transcriptPlain = transcriptNormalized ? stripHtml(`<p>${transcriptNormalized}</p>`) : '';
  const transcriptParagraphs = transcriptNormalized
    ? transcriptNormalized.split(/\n+/).filter(Boolean).length
    : 0;
  const transcriptLines = transcriptParagraphs;

  const textDensityDelta = transcriptLines ? Math.abs((transcriptLines - paragraphCount) / transcriptLines) : 0;

  const issues = [];
  if (!hasHeading) issues.push('missing-page-title');
  if (!textMatch) issues.push('missing-pdf-text-block');
  if (!paragraphCount) issues.push('no-paragraphs');
  if (!textId) issues.push('missing-text-id');
  if (transcript && !transcriptPlain) issues.push('transcript-empty');
  if (transcriptLines && textDensityDelta > 0.45) issues.push('paragraph-count-mismatch');

  const orderMatch = compareTextOrder(textPlain, transcriptPlain);
  if (checkOrder && transcript && textPlain && transcriptPlain && !orderMatch.similar) {
    issues.push('possible-order/content-shift');
  }

  return {
    pageFileName,
    sectionId,
    textId,
    textPlain,
    paragraphCount,
    transcriptParagraphs,
    hasHeading,
    styleCss: Boolean(styleCss),
    fontSizes,
    colors,
    transcriptAvailable: Boolean(transcript),
    orderMatch,
    issues,
  };
}

function scorePage(analysis, compare) {
  let score = 100;
  if (analysis.paragraphCount === 0) score -= 35;
  if (!analysis.hasHeading) score -= 15;
  if (!analysis.transcriptAvailable) score -= 20;
  if (analysis.issues.includes('missing-text-id')) score -= 20;
  if (analysis.issues.includes('possible-order/content-shift')) score -= 20;
  if (analysis.issues.includes('paragraph-count-mismatch')) score -= 10;
  if (!analysis.textId || !analysis.transcriptAvailable) score -= 5;
  if (compare && compare.status === 'ok' && Number.isFinite(compare.diffPixels)) {
    if (compare.diffPixels > 600000) score -= 40;
    else if (compare.diffPixels > 120000) score -= 20;
    else if (compare.diffPixels > 20000) score -= 10;
  }
  if (compare && compare.status === 'failed') score -= 10;
  if (compare && compare.status === 'missing_tool') score -= 5;

  const clamp = Math.max(0, Math.min(100, score));
  const status = clamp >= 80 ? 'green' : clamp >= 60 ? 'yellow' : 'red';
  return { score: clamp, status };
}

function parseCsvField(value) {
  const raw = value === undefined || value === null ? '' : String(value);
  const needsQuote = /[",\r\n]/.test(raw);
  const safe = raw.replace(/"/g, '""');
  return needsQuote ? `"${safe}"` : safe;
}

async function run() {
  ensureDir(OUT_DIR);
  ensureDir(OUT_HTML_DIR);
  ensureDir(OUT_PDF_DIR);
  ensureDir(OUT_DIFF_DIR);

  const rows = [];
  const audit = [];

  for (const page of TARGET_PAGES) {
    const pageNum = Number(page.page_number);
    const fileName = page.href === 'index.html' ? 'pg001' : `pg${String(pageNum).padStart(3, '0')}`;
    const sourceName = `${fileName}-source`;
    const htmlName = `${fileName}-html.png`;
    const diffName = `${fileName}-diff.png`;

    const analysis = analyzeHtml(page.href);
    const pageResult = {
      page: pageNum,
      href: page.href,
      sectionId: analysis.sectionId,
      issueCount: analysis.issues.length,
      issues: analysis.issues.join(';'),
    };

    let pdfImageResult = { status: 'skipped', path: null };
    if (includePdf) {
      pdfImageResult = capturePdfPage(pageNum, sourceName);
    } else {
      pdfImageResult.status = 'disabled';
    }

    const htmlImagePath = path.join(OUT_HTML_DIR, htmlName);
    const htmlImageResult = captureHtmlPage(path.join(ROOT, page.href), htmlImagePath);

    const diffResult = compareImages(
      includePdf ? pdfImageResult.path : null,
      includeHtml ? htmlImageResult.path : null,
      path.join(OUT_DIFF_DIR, diffName)
    );

    const { score, status } = scorePage(analysis, diffResult);
    audit.push({
      page: pageNum,
      href: page.href,
      sectionId: analysis.sectionId,
      styleStatus: analysis.styleCss ? 'present' : 'missing',
      paragraphCount: analysis.paragraphCount,
      transcriptParagraphs: analysis.transcriptParagraphs,
      paragraphDensityDelta: analysis.transcriptParagraphs
        ? Math.abs(analysis.paragraphCount - analysis.transcriptParagraphs) / Math.max(1, analysis.transcriptParagraphs)
        : null,
      orderSimilarity: analysis.orderMatch ? analysis.orderMatch.score : null,
      orderReason: analysis.orderMatch ? analysis.orderMatch.reason : '',
      diffPixels: diffResult.diffPixels ?? null,
      diffStatus: diffResult.status,
      pdfImage: pdfImageResult.path || null,
      htmlImage: htmlImageResult.path || null,
      fontSizes: analysis.fontSizes,
      colors: analysis.colors,
      issues: analysis.issues,
      score,
      status,
      transcriptAvailable: analysis.transcriptAvailable,
      orderMatch: analysis.orderMatch ? analysis.orderMatch.score : null,
      hasTextId: Boolean(analysis.textId),
    });

    rows.push([
      pageNum,
      page.href,
      analysis.sectionId,
      status,
      score,
      analysis.issues.join('|'),
      analysis.paragraphCount,
      analysis.transcriptParagraphs,
      analysis.orderMatch ? analysis.orderMatch.score : '',
      analysis.orderMatch ? analysis.orderMatch.reason : '',
      diffResult.diffPixels ?? '',
      pdfImageResult.status,
      htmlImageResult.status,
      diffResult.status,
      analysis.fontSizes,
      analysis.colors,
      (analysis.styleCss && page.href) ? 'yes' : 'no',
    ]);
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    totalPages: rows.length,
    green: audit.filter((row) => row.status === 'green').length,
    yellow: audit.filter((row) => row.status === 'yellow').length,
    red: audit.filter((row) => row.status === 'red').length,
    highestRisk: audit
      .filter((row) => row.status === 'red')
      .map((row) => row.page)
      .slice(0, 20),
    missingPdfTool: !commandExists('pdftoppm'),
    missingBrowser: !pickBrowserBinary(),
    missingImageMagick: !commandExists('magick'),
  };

  fs.writeFileSync(
    path.join(OUT_DIR, 'report.json'),
    JSON.stringify({ summary, rows: audit }, null, 2),
    'utf8'
  );

  const csv = [
    ['page', 'href', 'sectionId', 'status', 'score', 'issues', 'paragraphs', 'transcriptParagraphs', 'orderSimilarity', 'orderReason', 'diffPixels', 'pdfCapture', 'htmlCapture', 'compare', 'fontSizes', 'colors', 'hasInlineStyle']
      .map(parseCsvField)
      .join(','),
    ...rows.map((row) => row.map(parseCsvField).join(',')),
  ].join('\n');
  fs.writeFileSync(path.join(OUT_DIR, 'report.csv'), csv, 'utf8');

  const issuePages = audit
    .filter((row) => row.status !== 'green')
    .sort((a, b) => a.score - b.score)
    .map((row) => `- p${String(row.page).padStart(3, '0')} (${row.href}) => ${row.status}/${row.score}: ${row.issues.join(', ')}`)
    .join('\n');

  const readmeNotes = [
    '# Page style audit report',
    '',
    `Generated: ${summary.generatedAt}`,
    `Scope: pages ${startPage}-${Math.min(startPage + limit - 1, TARGET_PAGES[TARGET_PAGES.length - 1]?.page_number || 0)}`,
    '',
    `Summary: ${summary.green} green, ${summary.yellow} yellow, ${summary.red} red`,
    '',
    'Needs attention:',
    issuePages || '(none)',
    '',
    `Artifacts`,
    `- source: artifacts/page-style-audit/source`,
    `- html: artifacts/page-style-audit/html`,
    `- diff: artifacts/page-style-audit/diff`,
  ].join('\n');
  fs.writeFileSync(path.join(OUT_DIR, 'report.md'), readmeNotes, 'utf8');

  console.log(`Pages audited: ${summary.totalPages}`);
  console.log(`Status: ${summary.green} green, ${summary.yellow} yellow, ${summary.red} red`);
  console.log(`Reports:
  - ${path.join('artifacts', 'page-style-audit', 'report.json')}
  - ${path.join('artifacts', 'page-style-audit', 'report.csv')}
  - ${path.join('artifacts', 'page-style-audit', 'report.md')}`);
}

run().catch((err) => {
  console.error('Audit failed:', err.message);
  process.exit(1);
});
