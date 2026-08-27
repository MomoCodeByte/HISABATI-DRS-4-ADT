# HISABATI DRS 4 PB (ADT) - HTML-first book build

## Why this repository was updated

The book pages were converted to render semantic HTML from transcript text first, instead of loading raster page images as the primary content.

## Build workflow (recommended)

From the repository root:

- `npm run build:book-html`

This command does two things:

1. Rebuilds all HTML page files (`index.html` and `pg###_sec001.html`) from:
   - `content/pages.json`
   - `content/i18n/sw-TZ/texts.json`

   using [tools/rebuild-page-html.js](tools/rebuild-page-html.js)

2. Refreshes the embedded cache used by the offline preloader in:
   - `assets/offline-preloader.js`

   via [tools/sync_pages_to_offline_preloader.py](tools/sync_pages_to_offline_preloader.py)

## Rendering model

- Primary rendering: semantic HTML for `data-section-type="pdf_accessible_page"` using text transcripts.
- Fallback: only when a transcript is missing, a lazy-loaded image fallback is included from `images/pages/`.

## Manual script

You can still run the steps separately:

- `node tools/rebuild-page-html.js`
- `python tools/sync_pages_to_offline_preloader.py`

## Page-by-page style parity audit

After HTML-first conversion, run:

- `npm run audit:page-style`

What it generates in `artifacts/page-style-audit/`:

- `report.json`: detailed structured results
- `report.csv`: quick spreadsheet-friendly audit table
- `report.md`: human-readable list of pages needing attention
- `source/`: PDF-derived source page screenshots (if `pdftoppm` is installed)
- `html/`: rendered HTML page screenshots (if Chrome/Edge is installed)
- `diff/`: visual diff images (if ImageMagick `magick` is installed)

Useful options:

- `--start=1` to set first page index
- `--limit=184` to set how many pages to audit
- `--no-pdf=true` skip source page rendering
- `--no-html=true` skip HTML rendering
- `--compare=false` skip visual diff comparison
- `--strict-order=false` disable the text order/content similarity check

Example:

```bash
npm run audit:page-style -- --start=1 --limit=184
```

Use `artifacts/page-style-audit/report.csv` as your page-by-page queue:
- `green`: low-risk pages
- `yellow`: review spacing/font/contrast
- `red`: fix first
