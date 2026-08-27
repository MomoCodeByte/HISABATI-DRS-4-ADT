const fs = require('fs');
const path = require('path');

const root = process.cwd();
const contentDir = path.join(root, 'content');
const i18nDir = path.join(contentDir, 'i18n', 'sw-TZ');
const textsPath = path.join(i18nDir, 'texts.json');
const pagesPath = path.join(contentDir, 'pages.json');
const imagesDir = path.join(root, 'images', 'pages');

const htmlTemplate = {
  lang: 'sw-TZ',
  title: 'Hisabati: Kitabu cha Mwanafunzi Darasa la Nne',
  baseStyle:
`body{margin:0;background:#eef1ed}main{width:100%;display:flex;justify-content:center;padding:1rem 1rem 5rem;box-sizing:border-box}#content{width:100%;display:flex;justify-content:center}.pdf-page{position:relative;width:min(calc(100vw - 2rem),56rem);aspect-ratio:540.8980102539062/750.6610107421875;background:white;box-shadow:0 4px 24px #0002;overflow:auto;padding:1.25rem 1.25rem}.pdf-text{position:relative;z-index:2;color:#111827;line-height:1.6;font-size:1rem}h2.pdf-page-title{font-size:1.35rem;font-weight:700;margin:0 0 0.75rem 0;line-height:1.25}.pdf-text p{margin:0 0 0.85rem 0}.pdf-text p:last-child{margin-bottom:0}.page-image-fallback{display:flex;justify-content:center;margin:0.75rem 0}.page-image-fallback img{max-width:100%;height:auto;border:1px solid #d1d5db;box-shadow:0 1px 8px #0001;background:#fff}`,
};

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function toParagraphs(rawText) {
  if (!rawText) {
    return '';
  }

  return rawText
    .replace(/\u0007/g, '\n')
    .split(/\n+/)
    .map((chunk) => chunk.trim())
    .filter((chunk) => chunk.length > 0)
    .map((chunk) => `<p>${escapeHtml(chunk)}</p>`) 
    .join('\n');
}

const pages = JSON.parse(fs.readFileSync(pagesPath, 'utf8'));
const texts = JSON.parse(fs.readFileSync(textsPath, 'utf8'));

let updated = 0;
let skipped = 0;

for (const page of pages) {
  const href = page.href;
  const isIndex = href === 'index.html';
  const isPg = /^pg\d+_sec001\.html$/.test(href);

  if (!isIndex && !isPg) {
    skipped += 1;
    continue;
  }

  const sectionId = page.section_id;
  const pageNum = page.page_number;
  const m = /^pg(\d+)_/.exec(sectionId);

  const textId = m ? `pg${m[1]}_gp001_tx001` : null;
  const text = textId ? texts[textId] : null;

  const imageFile = path.join(imagesDir, `pg${String(pageNum).padStart(3, '0')}.jpg`);
  const imageAvailable = fs.existsSync(imageFile);
  const pageImageHtml = imageAvailable
    ? `<figure class="page-image-fallback" aria-hidden="true"><img src="./images/pages/${path.basename(imageFile)}" loading="lazy" alt="Picha ya asili ya ukurasa ${pageNum}"></figure>`
    : '';

  const contentHtml = (typeof text === 'string' && text.trim())
    ? `<section role="article" data-section-type="pdf_accessible_page" data-section-id="${sectionId}" aria-labelledby="page-heading" class="pdf-page"><h2 class="pdf-page-title" id="page-heading">Ukurasa wa ${pageNum}</h2><div class="pdf-text" data-id="${textId}">${toParagraphs(text)}
</div></section>`
    : `<section role="article" data-section-type="pdf_accessible_page" data-section-id="${sectionId}" aria-labelledby="page-heading" class="pdf-page"><h2 class="pdf-page-title" id="page-heading">Ukurasa wa ${pageNum}</h2><div class="pdf-text">Hakuna maandishi yaliyopatikana kwa ukurasa huu.</div>${pageImageHtml}</section>`;

  const output = `<!DOCTYPE html>\n<html lang="${htmlTemplate.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>${htmlTemplate.title}</title>\n<meta name="title-id" content="${sectionId}"><meta name="page-section-id" content="${pageNum}"><link href="./content/tailwind_output.css" rel="stylesheet"><link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet"><link href="./assets/fonts.css" rel="stylesheet">\n<style>${htmlTemplate.baseStyle}</style>\n</head><body><main><div id="content" class="opacity-0">${contentHtml}</div></main><div class="relative z-50" id="interface-container"></div><div class="relative z-50" id="nav-container"></div><script src="./assets/offline-preloader.js?v=audiofix-20260824-1"></script><script src="./assets/scorm.js"></script><script src="./assets/base.bundle.local.js?v=audiofix-20260824-1"></script></body></html>`;

  fs.writeFileSync(path.join(root, href), output);
  updated += 1;
}

console.log(`updated=${updated}`);
console.log(`skipped=${skipped}`);
