// scorm.js — SCORM 1.2 adapter, auto-generated, do not edit by hand
(function () {
  'use strict';

  // --- Find the SCORM 1.2 API by traversing parent frames ---
  function findAPI(win) {
    var depth = 0;
    while (depth < 7) {
      if (win.API) return win.API;
      if (!win.parent || win.parent === win) break;
      win = win.parent;
      depth++;
    }
    return null;
  }

  var API = findAPI(window);
  if (!API) return; // Not in a SCORM LMS — exit silently

  // --- Initialize the session ---
  API.LMSInitialize('');

  // --- Identify the current page ---
  var metaTitleId = document.querySelector('meta[name="title-id"]');
  var pageId = metaTitleId ? metaTitleId.getAttribute('content') : '';

  // All activity IDs in this ADT (embedded at generation time)
  var ALL_ACTIVITY_IDS = ["qz001","qz002","qz003","qz004","qz005","qz006","qz007","qz008","qz009","qz010","qz011","qz012","qz013","qz014","qz015","qz016","qz017","qz018","qz019","qz020","qz021","qz022","qz023","qz024","qz025","qz026","qz027","qz028","qz029","qz030","qz031","qz032","qz033","qz034","qz035"];
  var hasActivities = ALL_ACTIVITY_IDS.length > 0;

  // --- Record where the learner is ---
  API.LMSSetValue('cmi.core.lesson_location', pageId);

  // --- Set lesson status ---
  if (hasActivities) {
    applyStatus();
    watchForCompletions();
  } else {
    // Content-only ADT — mark as passed on first visit
    var existingStatus = API.LMSGetValue('cmi.core.lesson_status') || '';
    if (existingStatus !== 'passed') {
      API.LMSSetValue('cmi.core.lesson_status', 'passed');
      API.LMSSetValue('cmi.core.score.raw', '100');
      API.LMSSetValue('cmi.core.score.min', '0');
      API.LMSSetValue('cmi.core.score.max', '100');
    }
  }

  API.LMSCommit('');

  // --- Session close ---
  window.addEventListener('beforeunload', function () {
    if (hasActivities) applyStatus();
    API.LMSCommit('');
    API.LMSFinish('');
  });

  // -------------------------------------------------------
  // Helpers
  // -------------------------------------------------------

  function getCompletedIds() {
    var completed = [];
    try {
      completed = JSON.parse(localStorage.getItem('completedActivities') || '[]');
    } catch (e) { /* ignore */ }

    var ids = {};
    for (var i = 0; i < completed.length; i++) {
      if (typeof completed[i] === 'string') {
        var dashIdx = completed[i].indexOf('-');
        var actId = dashIdx > -1 ? completed[i].substring(0, dashIdx) : completed[i];
        ids[actId] = true;
      }
    }
    return ids;
  }

  function applyStatus() {
    var completedIds = getCompletedIds();
    var completedCount = 0;
    for (var i = 0; i < ALL_ACTIVITY_IDS.length; i++) {
      if (completedIds[ALL_ACTIVITY_IDS[i]]) completedCount++;
    }

    var score = Math.round((completedCount / ALL_ACTIVITY_IDS.length) * 100);
    API.LMSSetValue('cmi.core.score.raw', String(score));
    API.LMSSetValue('cmi.core.score.min', '0');
    API.LMSSetValue('cmi.core.score.max', '100');

    if (completedCount === ALL_ACTIVITY_IDS.length) {
      API.LMSSetValue('cmi.core.lesson_status', 'passed');
    } else {
      var existingStatus = API.LMSGetValue('cmi.core.lesson_status') || '';
      if (existingStatus !== 'passed') {
        API.LMSSetValue('cmi.core.lesson_status', 'incomplete');
      }
    }
  }

  function watchForCompletions() {
    var _origSetItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
      _origSetItem(key, value);
      if (key === 'completedActivities') {
        applyStatus();
        API.LMSCommit('');
      }
    };

    window.addEventListener('storage', function (e) {
      if (e.key === 'completedActivities') {
        applyStatus();
        API.LMSCommit('');
      }
    });
  }
})();

// Make the read-aloud Previous/Next controls seek within the current page.
(function () {
  'use strict';

  var SEEK_SECONDS = 20;
  var previousLabel = 'Nenda kwenye sauti iliyopita';
  var nextLabel = 'Nenda kwenye sauti inayofuata';
  var NativeAudio = window.Audio;
  var audioInstances = [];
  window.__adtAudioInstances = audioInstances;

  function TrackedAudio() {
    var audio = new (Function.prototype.bind.apply(
      NativeAudio,
      [null].concat(Array.prototype.slice.call(arguments))
    ))();
    audioInstances.push(audio);
    return audio;
  }
  TrackedAudio.prototype = NativeAudio.prototype;
  window.Audio = TrackedAudio;
  var nativePlay = window.HTMLMediaElement.prototype.play;
  window.HTMLMediaElement.prototype.play = function () {
    window.__adtCurrentMedia = this;
    return nativePlay.apply(this, arguments);
  };

  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest
      ? event.target.closest('button[aria-label]')
      : null;
    if (!button) return;

    var label = button.getAttribute('aria-label');
    var direction = label === nextLabel ? 1 : label === previousLabel ? -1 : 0;
    if (!direction) return;

    var audio = document.querySelector('audio');
    if (!audio && window.__adtCurrentMedia) audio = window.__adtCurrentMedia;
    if (!audio && audioInstances.length) {
      audio = audioInstances.slice().reverse().find(function (item) {
        return !item.paused;
      }) || audioInstances[audioInstances.length - 1];
    }
    if (!audio || !Number.isFinite(audio.duration)) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.stopImmediatePropagation) event.stopImmediatePropagation();

    audio.currentTime = Math.max(
      0,
      Math.min(audio.duration, audio.currentTime + direction * SEEK_SECONDS)
    );
    audio.play().catch(function () { /* the user can press Play if blocked */ });
  }, true);
})();
