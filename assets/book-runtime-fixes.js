(function () {
  'use strict';

  var PDF_WIDTH = 540.8980102539062;
  var PDF_HEIGHT = 750.6610107421875;
  var resizeFrame = 0;

  function fitPdfCanvas(page) {
    var canvas = page.querySelector('.pdf-dom-canvas');
    if (!canvas) return;

    var scale = Math.min(
      page.clientWidth / PDF_WIDTH,
      page.clientHeight / PDF_HEIGHT
    );
    var renderedWidth = PDF_WIDTH * scale;
    var left = Math.max(0, (page.clientWidth - renderedWidth) / 2);

    canvas.style.transform = 'translateX(' + left + 'px) scale(' + scale + ')';
  }

  function fitComposedPage(page) {
    var inner = page.querySelector('.page-inner');
    if (!inner || page.classList.contains('pdf-dom-page')) return;

    inner.style.transform = '';
    inner.style.transformOrigin = '';

    var pageRect = page.getBoundingClientRect();
    var children = Array.prototype.filter.call(
      inner.querySelectorAll('*'),
      function (element) {
        return getComputedStyle(element).display !== 'none' &&
          !element.classList.contains('page-narration-hook') &&
          !element.classList.contains('online-watermark');
      }
    );
    if (!children.length) return;

    var maxBottom = Math.max.apply(null, children.map(function (element) {
      return element.getBoundingClientRect().bottom - pageRect.top;
    }));
    var maxRight = Math.max.apply(null, children.map(function (element) {
      return element.getBoundingClientRect().right - pageRect.left;
    }));
    var scale = Math.min(
      1,
      (page.clientHeight - 2) / Math.max(maxBottom, 1),
      (page.clientWidth - 2) / Math.max(maxRight, 1)
    );

    if (scale < 0.999) {
      inner.style.transformOrigin = '0 0';
      inner.style.transform = 'scale(' + scale + ')';
    }
  }

  function ensureNarrationHook(page) {
    var existing = page.querySelector('[data-id$="_gp001_tx001"]');
    if (existing && existing.classList.contains('page-narration-hook')) return;
    var sectionId = page.getAttribute('data-section-id') || '';
    var match = sectionId.match(/^pg(\d{3})_sec001$/);
    if (!match) return;
    var audioId = 'pg' + match[1] + '_gp001_tx001';
    if (existing) existing.removeAttribute('data-id');
    var hook = document.createElement('div');
    hook.className = 'page-narration-hook';
    hook.setAttribute('data-id', audioId);
    page.insertBefore(hook, page.firstChild);
  }

  function repairBookPages() {
    Array.prototype.forEach.call(document.querySelectorAll('.book-page'), function (page) {
      ensureNarrationHook(page);
      fitPdfCanvas(page);
      fitComposedPage(page);
    });
  }

  function scheduleRepair() {
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(function () {
      resizeFrame = 0;
      repairBookPages();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', repairBookPages, { once: true });
  } else {
    repairBookPages();
  }

  window.addEventListener('load', repairBookPages, { once: true });
  window.addEventListener('resize', scheduleRepair);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(repairBookPages);
  }
})();
/* Match browser glyph widths to the PDF-extracted span widths. */
(() => {
  const fitPdfTextSpans = async () => {
    const canvas = document.querySelector('.pdf-dom-canvas');
    if (!canvas) return;
    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (_) {}
    }
    const canvasRect = canvas.getBoundingClientRect();
    const canvasScale = canvas.offsetWidth ? canvasRect.width / canvas.offsetWidth : 1;
    document.querySelectorAll('.pdf-dom-page .pdf-span').forEach((span) => {
      if (span.dataset.pdfWidthFitted === 'true' || !span.textContent.trim()) return;
      const targetWidth = Number.parseFloat(span.style.width);
      if (!Number.isFinite(targetWidth) || targetWidth <= 0) return;
      const originalTransform = span.style.transform && span.style.transform !== 'none'
        ? span.style.transform
        : '';
      span.style.display = 'inline-block';
      span.style.width = 'max-content';
      span.style.whiteSpace = 'pre';
      const naturalWidth = span.getBoundingClientRect().width / (canvasScale || 1);
      if (!Number.isFinite(naturalWidth) || naturalWidth <= 0) return;
      const ratio = targetWidth / naturalWidth;
      if (ratio >= 0.72 && ratio <= 1.28 && Math.abs(1 - ratio) > 0.004) {
        span.style.transformOrigin = 'left top';
        span.style.transform = (originalTransform + ' scaleX(' + ratio + ')').trim();
      }
      span.style.width = naturalWidth + 'px';
      span.dataset.pdfWidthFitted = 'true';
    });
  };
  const startPdfTextFit = () => requestAnimationFrame(() => {
    fitPdfTextSpans();
    setTimeout(fitPdfTextSpans, 250);
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startPdfTextFit, { once: true });
  } else {
    startPdfTextFit();
  }
})();

/* Refit PDF text by measured glyph width and mirror Rehema highlighting visibly. */
(() => {
  const highlightClass = 'rehema-visible-highlight';

  const installHighlightStyle = () => {
    if (document.getElementById('rehema-visible-highlight-style')) return;
    const style = document.createElement('style');
    style.id = 'rehema-visible-highlight-style';
    style.textContent = `
      .${highlightClass} {
        background: rgba(253, 224, 71, .72) !important;
        border-radius: 3px;
        box-shadow: 0 0 0 2px rgba(253, 224, 71, .28);
        transition: background-color 80ms linear;
      }
    `;
    document.head.appendChild(style);
  };

  const fitPdfTextSpansV2 = async () => {
    if (!document.querySelector('.pdf-dom-canvas')) return;
    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (_) {}
    }

    const context = document.createElement('canvas').getContext('2d');
    if (!context) return;

    document.querySelectorAll('.pdf-dom-page .pdf-span').forEach((span) => {
      const storedTarget = Number.parseFloat(span.dataset.pdfTargetWidth || '');
      const inlineTarget = Number.parseFloat(span.style.width);
      const targetWidth = Number.isFinite(storedTarget) ? storedTarget : inlineTarget;
      if (!Number.isFinite(targetWidth) || targetWidth <= 0 || !span.textContent) return;

      span.dataset.pdfTargetWidth = String(targetWidth);
      const originalText = span.dataset.pdfOriginalText || span.textContent;
      span.dataset.pdfOriginalText = originalText;
      const computed = getComputedStyle(span);
      context.font = [
        computed.fontStyle,
        computed.fontVariant,
        computed.fontWeight,
        computed.fontSize,
        computed.fontFamily
      ].join(' ');

      const pieces = Array.from(originalText.matchAll(/\S(?:.*?\S)?(?= {2,}|$)/g));
      if (pieces.length > 1) {
        const parentLeft = Number.parseFloat(span.style.left) || 0;
        const parentTop = Number.parseFloat(span.style.top) || 0;
        const operators = Array.from(span.parentElement.querySelectorAll(':scope > .pdf-span'))
          .filter((candidate) => {
            if (candidate === span || !/^[=+×÷−-]$/.test((candidate.textContent || '').trim())) {
              return false;
            }
            const left = Number.parseFloat(candidate.style.left) || 0;
            const top = Number.parseFloat(candidate.style.top) || 0;
            return Math.abs(top - parentTop) <= 1.5 &&
              left >= parentLeft && left <= parentLeft + targetWidth + 2;
          })
          .map((candidate) => ({
            left: (Number.parseFloat(candidate.style.left) || 0) - parentLeft,
            width: Number.parseFloat(candidate.dataset.pdfTargetWidth || candidate.style.width) || 0
          }))
          .sort((left, right) => left.left - right.left)
          .slice(0, pieces.length - 1);

        span.textContent = '';
        span.style.display = 'block';
        span.style.width = targetWidth + 'px';
        span.style.transform = 'none';
        span.style.overflow = 'visible';
        span.setAttribute('aria-label', originalText.trim());

        pieces.forEach((piece, index) => {
          const text = piece[0].trim();
          if (!text) return;
          const measuredPiece = context.measureText(text).width;
          if (!Number.isFinite(measuredPiece) || measuredPiece <= 0) return;
          const proportionalLeft = targetWidth * piece.index / Math.max(1, originalText.length);
          const proportionalWidth = targetWidth * piece[0].length / Math.max(1, originalText.length);
          const left = index > 0 && operators[index - 1]
            ? operators[index - 1].left + operators[index - 1].width + 2
            : proportionalLeft;
          const operatorBoundary = operators[index]
            ? operators[index].left - 2
            : targetWidth;
          const operatorSlotWidth = operatorBoundary - left;
          const slotWidth = operatorSlotWidth > Math.max(2, proportionalWidth * .6)
            ? operatorSlotWidth
            : proportionalWidth;
          const ratio = Math.max(.45, Math.min(1.45, slotWidth / measuredPiece));
          const child = document.createElement('span');
          child.className = 'pdf-span-part';
          child.textContent = text;
          child.style.position = 'absolute';
          child.style.left = left + 'px';
          child.style.top = '0';
          child.style.width = measuredPiece + 'px';
          child.style.whiteSpace = 'pre';
          child.style.transformOrigin = 'left top';
          child.style.transform = `scaleX(${ratio})`;
          span.appendChild(child);
          span.appendChild(document.createTextNode(' '));
        });
        span.dataset.pdfWidthFitted = 'v2-compound';
        return;
      }

      const measuredWidth = context.measureText(originalText).width;
      if (!Number.isFinite(measuredWidth) || measuredWidth <= 0) return;

      const ratio = Math.max(.45, Math.min(1.45, targetWidth / measuredWidth));
      span.style.display = 'inline-block';
      span.style.width = measuredWidth + 'px';
      span.style.whiteSpace = 'pre';
      span.style.transformOrigin = 'left top';
      span.style.transform = `scaleX(${ratio})`;
      span.dataset.pdfWidthFitted = 'v2';
    });
  };

  const visibleSegments = () => {
    const coordinateSegments = Array.from(document.querySelectorAll('.pdf-dom-text .pdf-span'))
      .filter((element) => {
        const text = (element.textContent || '').trim();
        return text && !/HISABATI DRS|\.indd|\d{2}\/\d{2}\/\d{4}/i.test(text);
      });
    if (coordinateSegments.length) return coordinateSegments;

    return Array.from(document.querySelectorAll(
      '.page-inner h1,.page-inner h2,.page-inner h3,.page-inner h4,' +
      '.page-inner p,.page-inner li,.page-inner dt,.page-inner dd,' +
      '.page-inner address,.page-inner figcaption,.page-inner th,.page-inner td'
    )).filter((element) => {
      const text = (element.textContent || '').trim();
      return text && !element.closest('.page-narration-hook');
    });
  };

  const wordWeight = (element) => {
    const words = (element.textContent || '').match(/[\p{L}\p{N}]+|[+×÷=<>]/gu);
    return Math.max(1, words ? words.length : 1);
  };

  const clearVisibleHighlight = () => {
    document.querySelectorAll('.' + highlightClass).forEach((element) => {
      element.classList.remove(highlightClass);
    });
  };

  const mirrorNarrationHighlight = () => {
    const hook = document.querySelector('.page-narration-hook');
    if (!hook) return;
    const narrationWords = Array.from(hook.querySelectorAll('[data-word-index]'));
    const active = hook.querySelector(
      ".bg-yellow-300,[class*='bg-yellow'],[data-highlighted='true']"
    );
    if (!active || !narrationWords.length) {
      clearVisibleHighlight();
      return;
    }

    const activeIndex = Number.parseInt(active.dataset.wordIndex || '', 10);
    if (!Number.isFinite(activeIndex)) return;
    const segments = visibleSegments();
    if (!segments.length) return;

    const weights = segments.map(wordWeight);
    const totalVisibleWords = weights.reduce((sum, value) => sum + value, 0);
    const progress = narrationWords.length > 1
      ? Math.max(0, Math.min(1, activeIndex / (narrationWords.length - 1)))
      : 0;
    const targetWord = progress * Math.max(0, totalVisibleWords - 1);

    let cumulative = 0;
    let target = segments[segments.length - 1];
    for (let index = 0; index < segments.length; index += 1) {
      cumulative += weights[index];
      if (targetWord < cumulative) {
        target = segments[index];
        break;
      }
    }

    document.querySelectorAll('.' + highlightClass).forEach((element) => {
      if (element !== target) element.classList.remove(highlightClass);
    });
    target.classList.add(highlightClass);
  };

  const startVisibleNarration = () => {
    installHighlightStyle();
    requestAnimationFrame(() => {
      fitPdfTextSpansV2();
      setTimeout(fitPdfTextSpansV2, 350);
    });

    const hook = document.querySelector('.page-narration-hook');
    if (!hook) return;
    const observer = new MutationObserver(mirrorNarrationHighlight);
    observer.observe(hook, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'data-highlighted']
    });
    setInterval(mirrorNarrationHighlight, 120);
    mirrorNarrationHighlight();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startVisibleNarration, { once: true });
  } else {
    startVisibleNarration();
  }
})();

