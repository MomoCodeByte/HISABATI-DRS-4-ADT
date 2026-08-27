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
      function (element) { return getComputedStyle(element).display !== 'none'; }
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
