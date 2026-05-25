/* ─── Story Viewer ────────────────────────────────────── */

let story       = null;
let pages       = [];
let currentPage = 0;
let isCrayon    = false;
let isFav       = false;

// Translation cache & state
const transCache = {};   // { `${lang}:${pageIdx}`: translatedText }
let   currentLang = 'en';

const autoAdvance = {
  intervalId: null,
  remaining: 5,
};
let pendingAutoPlayOnArrive = false;
const preloadedImageUrls = new Set();
const pageLoadState = {
  controller: null,
  token: 0,
  contentReady: false,
};

// ── Utils ──────────────────────────────────────────────
function storyId() {
  return location.pathname.split('/').pop();
}
function showToast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
function authHeaders() {
  const h = {};
  const t = localStorage.getItem('cc_token');
  if (t) h['Authorization'] = `Bearer ${t}`;
  return h;
}

function hideAutoAdvanceCountdown() {
  if (autoAdvance.intervalId) {
    clearInterval(autoAdvance.intervalId);
    autoAdvance.intervalId = null;
  }
  const widget = document.getElementById('auto-advance-widget');
  if (widget) widget.classList.add('hidden');
}

function _updateAutoAdvanceCountdownUI() {
  const count = document.getElementById('auto-advance-count');
  if (count) count.textContent = String(autoAdvance.remaining);
}

function requestNextPageWithAutoPlay() {
  pendingAutoPlayOnArrive = true;
  const nextBtn = document.getElementById('next-btn');
  if (nextBtn) nextBtn.click();
}

function runAutoPlayOnArriveEffect() {
  if (!pendingAutoPlayOnArrive) return;
  pendingAutoPlayOnArrive = false;
  // Reuse the same narrate-button play handler after page render settles.
  requestAnimationFrame(() => requestAnimationFrame(() => handleNarrateButtonClick()));
}

function startPageLoadCycle() {
  if (pageLoadState.controller) {
    try { pageLoadState.controller.abort(); } catch { /* ignore */ }
  }
  pageLoadState.controller = new AbortController();
  pageLoadState.token += 1;
  pageLoadState.contentReady = false;
  return { signal: pageLoadState.controller.signal, token: pageLoadState.token };
}

function clearPageContentForTransition(nextPageIdx = null) {
  const textContainer = document.getElementById('story-text-content');
  if (textContainer) {
    textContainer.classList.toggle('crayon-mode', isCrayon);
    textContainer.innerHTML = '<span class="text-muted" style="font-size:.95rem">Loading page...</span>';
  }

  const img = document.getElementById('story-img');
  const ph = document.getElementById('img-placeholder');
  const pageLabel = document.getElementById('img-page-label');

  if (typeof nextPageIdx === 'number' && pageLabel) {
    pageLabel.textContent = `Page ${nextPageIdx + 1}`;
  }

  if (img) {
    img.onload = null;
    img.onerror = null;
    img.removeAttribute('src');
    img.style.display = 'none';
  }
  if (ph) ph.style.display = 'flex';
}

function preloadNextPageImage() {
  const nextPage = pages[currentPage + 1];
  const url = nextPage && nextPage.imageUrl ? nextPage.imageUrl : '';
  if (!url || preloadedImageUrls.has(url)) return;
  preloadedImageUrls.add(url);
  const prefImg = new Image();
  prefImg.onload = () => {};
  prefImg.onerror = () => {};
  prefImg.src = url;
}

function startAutoAdvanceCountdown() {
  hideAutoAdvanceCountdown();
  if (!pages.length || currentPage >= pages.length - 1) return;

  autoAdvance.remaining = 5;
  _updateAutoAdvanceCountdownUI();
  const widget = document.getElementById('auto-advance-widget');
  if (widget) widget.classList.remove('hidden');

  autoAdvance.intervalId = setInterval(() => {
    autoAdvance.remaining -= 1;
    _updateAutoAdvanceCountdownUI();
    if (autoAdvance.remaining <= 0) {
      hideAutoAdvanceCountdown();
      requestNextPageWithAutoPlay();
    }
  }, 1000);
}

function setupAutoAdvanceControls() {
  const replayBtn = document.getElementById('auto-advance-replay');
  const skipBtn = document.getElementById('auto-advance-skip');
  if (!replayBtn || !skipBtn) return;

  replayBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    hideAutoAdvanceCountdown();
    Narrator.unlockAudio();
    Narrator.restart();
  });

  skipBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    hideAutoAdvanceCountdown();
    requestNextPageWithAutoPlay();
  });
}

function handleNarrateButtonClick() {
  hideAutoAdvanceCountdown();
  Narrator.toggle();
}

// ── Load story ─────────────────────────────────────────
async function loadStory() {
  try {
    const res = await fetch(`/api/stories/${storyId()}`, { headers: authHeaders() });
    if (!res.ok) throw new Error('Not found');
    story = await res.json();
    if (typeof story.pages === 'string') {
      try { pages = JSON.parse(story.pages); } catch { pages = []; }
    } else {
      pages = story.pages || [];
    }
    isFav = !!story.isFavorite;
    document.title = `${story.storyTitle} · Brave Story Maker`;
    updateFavBtn();
    renderPage();
    if (new URLSearchParams(window.location.search).get('new') === '1') {
      setTimeout(() => {
        if (window.launchBalloons) window.launchBalloons();
        else window._execBalloons = () => window.launchBalloons();
      }, 600);
    }
  } catch {
    document.getElementById('story-card').innerHTML =
      '<div style="padding:3rem;text-align:center;color:var(--destructive)">Story not found. <a href="/">Go home</a></div>';
  }
}

// ── Render page ────────────────────────────────────────
function renderPage() {
  hideAutoAdvanceCountdown();
  Narrator.stop();
  const page = pages[currentPage];
  if (!page) return;
  const loadCtx = startPageLoadCycle();
  let textReady = false;
  let imageReady = false;

  function markReadyIfComplete() {
    if (loadCtx.signal.aborted || loadCtx.token !== pageLoadState.token) return;
    if (!textReady || !imageReady) return;
    pageLoadState.contentReady = true;
    preloadNextPageImage();
    runAutoPlayOnArriveEffect();
  }

  // Image
  const img       = document.getElementById('story-img');
  const ph        = document.getElementById('img-placeholder');
  const pageLabel = document.getElementById('img-page-label');
  if (pageLabel) pageLabel.textContent = `Page ${currentPage + 1}`;
  img.onload = null;
  img.onerror = null;
  img.style.display = 'none';
  ph.style.display = 'flex';

  if (page.imageUrl) {
    img.alt = story.storyTitle;
    img.classList.add('fade-in');
    img.onload  = () => {
      if (loadCtx.signal.aborted || loadCtx.token !== pageLoadState.token) return;
      img.classList.remove('fade-in');
      img.style.display = 'block';
      ph.style.display  = 'none';
      imageReady = true;
      markReadyIfComplete();
    };
    img.onerror = () => {
      if (loadCtx.signal.aborted || loadCtx.token !== pageLoadState.token) return;
      img.style.display = 'none';
      ph.style.display = 'flex';
      imageReady = true;
      markReadyIfComplete();
    };
    img.src = page.imageUrl;
  } else {
    img.style.display = 'none';
    ph.style.display  = 'flex';
    imageReady = true;
  }

  // Text
  const text = getDisplayText();
  renderText(text);
  textReady = true;

  // Keep text direction aligned with what's actually showing: when the cache
  // misses we fall back to English, so force ltr regardless of currentLang.
  const hasTranslation = currentLang !== 'en' && !!transCache[`${currentLang}:${currentPage}`];
  applyTextDirection(hasTranslation ? (transDirCache[currentLang] || 'ltr') : 'ltr');

  updatePageBadge();
  updateNavBtns();
  markReadyIfComplete();
}

function getDisplayText() {
  if (currentLang === 'en') {
    return pages[currentPage]?.text || '';
  }
  const key = `${currentLang}:${currentPage}`;
  if (transCache[key]) return transCache[key];
  return pages[currentPage]?.text || '';
}

function splitWords(text) {
  const trimmed = (text || '').trim();
  return trimmed ? trimmed.split(/\s+/) : [];
}

function renderText(raw) {
  const container = document.getElementById('story-text-content');
  container.classList.toggle('crayon-mode', isCrayon);
  container.onclick = (e) => {
    const word = e.target.closest('.word-span[data-index]');
    if (!word || !container.contains(word)) return;
    const idx = parseInt(word.dataset.index, 10);
    if (Number.isNaN(idx)) return;
    Narrator.playFromWord(idx);
  };

  const allWords = splitWords(raw);
  if (!allWords.length) { container.innerHTML = ''; return; }
  let out = '';
  allWords.forEach((w, i) => {
    out += `<span class="word-span" data-index="${i}" data-idx="${i}">${escHtml(w)}</span> `;
  });
  container.innerHTML = out;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function updatePageBadge() {
  document.getElementById('page-badge').textContent = `Page ${currentPage + 1} of ${pages.length}`;
}

function updateNavBtns() {
  const prev = document.getElementById('prev-btn');
  const next = document.getElementById('next-btn');
  const isFirst = currentPage === 0;
  const isLast  = pages.length > 0 && currentPage === pages.length - 1;

  prev.disabled = false;
  prev.innerHTML = isFirst
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15 18l-6-6 6-6"/></svg> Library`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15 18l-6-6 6-6"/></svg> Back`;

  if (isLast) {
    next.innerHTML = `New Story
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 5v14M5 12h14"/></svg>`;
  } else {
    next.innerHTML = `Next
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18l6-6-6-6"/></svg>`;
  }
}

function _preloadAdjacentImages() {
  [currentPage - 1, currentPage + 1].forEach(i => {
    const p = pages[i];
    if (!p || !p.imageUrl || preloadedImageUrls.has(p.imageUrl)) return;
    preloadedImageUrls.add(p.imageUrl);
    const im = new Image(); im.src = p.imageUrl;
  });
}

function _prefersReducedMotion() {
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

let _flipInProgress = false;

function changePage(delta) {
  if (_flipInProgress) return;
  hideAutoAdvanceCountdown();
  const next = currentPage + delta;
  if (next < 0 || next >= pages.length) return;

  const card = document.getElementById('story-card');
  const dir  = delta > 0 ? 'next' : 'prev';
  Narrator.stop();
  _preloadAdjacentImages();

  if (_prefersReducedMotion() || !card) {
    clearPageContentForTransition(next);
    currentPage = next;
    renderPage();
    _announcePage();
    return;
  }

  _flipInProgress = true;
  card.classList.remove('fade-in', 'pf-flip-next-in', 'pf-flip-prev-in');
  void card.offsetWidth;
  card.classList.add(`pf-flip-${dir}-out`);

  const half = 260;   // swap content at the apex of the curl
  const full = 520;   // total flip duration (matches CSS)
  setTimeout(() => {
    clearPageContentForTransition(next);
    currentPage = next;
    renderPage();
    _announcePage();
    card.classList.remove(`pf-flip-${dir}-out`);
    card.classList.add(`pf-flip-${dir}-in`);
  }, half);
  setTimeout(() => {
    card.classList.remove(`pf-flip-${dir}-in`);
    _flipInProgress = false;
  }, full + 20);
}

function _announcePage() {
  let live = document.getElementById('pf-live');
  if (!live) {
    live = document.createElement('div');
    live.id = 'pf-live';
    live.setAttribute('aria-live', 'polite');
    live.setAttribute('aria-atomic', 'true');
    live.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);';
    document.body.appendChild(live);
  }
  live.textContent = `Page ${currentPage + 1} of ${pages.length}`;
}

function clearHighlight() {
  document.querySelectorAll('.word-span.highlighted').forEach(el => el.classList.remove('highlighted'));
}

/* ─── Narrator ───────────────────────────────────────────
 * A single controller for the play/pause feature. All state lives here,
 * all transitions go through setState(). Supports Azure TTS (preferred)
 * and browser speechSynthesis (fallback).
 *
 * State machine:
 *   idle ──play()──► loading ──ready──► playing ──pause()──► paused
 *    ▲                 │                   │                   │
 *    │                 │                   └──stop()──┐        │
 *    └────stop()───────┴───────────────────────────── ┴──play()┘ (resume)
 */
const _SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAAACABAAZGF0YQAAAAA=';

const Narrator = {
  // 'idle' | 'loading' | 'playing' | 'paused'
  state: 'idle',

  azureAvailable: false,
  azureVoices:    [],
  browserVoices:  [],

  audio:      null,   // HTMLAudioElement (Azure)
  utterance:  null,   // SpeechSynthesisUtterance (browser)

  blobCache:  {},     // `${voiceId}:${lang}:${pageIdx}` → objectURL
  generation: 0,      // bumps on every stop() — invalidates stale async work
  controller: null,   // AbortController for in-flight /api/tts fetch

  highlightTimer: null,
  audioUnlocked:  false,
  activeVoiceId:  null, // the voice the current/last playback was started with
  browserBoundarySeen: false,
  browserLastBoundaryAt: 0,
  browserFallbackStartIndex: 0,
  browserFallbackWordCount: 0,
  browserFallbackIndex: 0,
  browserVoiceRef: null,
  browserUtteranceRef: null,

  // ── Init ─────────────────────────────────────────────
  async init() {
    // Azure TTS config
    try {
      const res = await fetch('/api/tts/config');
      if (res.ok) {
        const cfg = await res.json();
        this.azureAvailable = !!cfg.available;
        this.azureVoices    = cfg.voices || [];
      }
    } catch { /* Azure not reachable — fall back to browser TTS */ }

    // Browser voices load asynchronously
    this._loadBrowserVoices();
    if (window.speechSynthesis && typeof window.speechSynthesis.onvoiceschanged !== 'undefined') {
      window.speechSynthesis.onvoiceschanged = () => this._loadBrowserVoices();
    }

    this._populateVoiceSelect();
    this._updateUI();
  },

  _loadBrowserVoices() {
    if (!window.speechSynthesis) return;
    const all = window.speechSynthesis.getVoices();
    const en  = all.filter(v => v.lang.startsWith('en'));
    this.browserVoices = en.length ? en : all;
    if (!this.azureAvailable) this._populateVoiceSelect();
  },

  _liveBrowserVoices() {
    if (!window.speechSynthesis) return [];
    return window.speechSynthesis.getVoices() || [];
  },

  _matchVoiceByRef(ref) {
    if (!ref) return null;
    const voices = this._liveBrowserVoices();
    if (!voices.length) return null;
    if (ref.voiceURI) {
      const byUri = voices.find(v => v.voiceURI === ref.voiceURI);
      if (byUri) return byUri;
    }
    if (ref.name) {
      const byName = voices.find(v => v.name === ref.name);
      if (byName) return byName;
    }
    return null;
  },

  _resolveSelectedBrowserVoice() {
    const rawIdx = this.currentVoiceId;
    const idx = parseInt(rawIdx, 10);
    if (!Number.isNaN(idx) && this.browserVoices[idx]) {
      const selected = this.browserVoices[idx];
      const live = this._liveBrowserVoices();
      let matched = null;
      if (selected.voiceURI) {
        matched = live.find(v => v.voiceURI === selected.voiceURI) || null;
      }
      if (!matched && selected.name) {
        matched = live.find(v => v.name === selected.name) || null;
      }
      matched = matched || selected;

      this.browserVoiceRef = { name: matched.name, voiceURI: matched.voiceURI };
      this.activeVoiceId = rawIdx;
      return matched;
    }

    return this._matchVoiceByRef(this.browserVoiceRef);
  },

  _rememberBrowserUtterance(u) {
    if (!u) return;
    if (u.voice) {
      this.browserVoiceRef = { name: u.voice.name, voiceURI: u.voice.voiceURI };
    }
    this.browserUtteranceRef = {
      rate: typeof u.rate === 'number' ? u.rate : 1,
      pitch: typeof u.pitch === 'number' ? u.pitch : 1.1,
      volume: typeof u.volume === 'number' ? u.volume : 1,
    };
  },

  _populateVoiceSelect() {
    const sel   = document.getElementById('voice-select');
    const row   = document.getElementById('voice-row');
    const badge = document.getElementById('el-badge');
    if (!sel) return;

    const prev = sel.value;
    sel.innerHTML = '';

    if (this.azureAvailable && this.azureVoices.length) {
      this.azureVoices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = v.name;
        sel.appendChild(opt);
      });
      if (row)   row.style.display   = '';
      if (badge) badge.style.display = '';
      if (prev && this.azureVoices.some(v => v.id === prev)) sel.value = prev;
    } else if (this.browserVoices.length) {
      this.browserVoices.forEach((v, i) => {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = `${v.name} (${v.lang})`;
        sel.appendChild(opt);
      });
      if (row)   row.style.display   = '';
      if (badge) badge.style.display = 'none';
      if (prev && sel.querySelector(`option[value="${prev}"]`)) sel.value = prev;
    } else {
      if (row) row.style.display = 'none';
    }
  },

  // ── Accessors for live UI values ─────────────────────
  get currentVoiceId() {
    const el = document.getElementById('voice-select');
    return el ? el.value : '';
  },
  get currentSpeed() {
    const el = document.getElementById('speed-range');
    return el ? parseFloat(el.value) || 1 : 1;
  },

  /* Unlock HTMLAudioElement playback for Brave/Chrome.
   * Must be called inside a user gesture — plays a silent data URI
   * so subsequent Audio.play() calls are permitted. */
  unlockAudio() {
    if (this.audioUnlocked) return;
    const a = new Audio(_SILENT_WAV);
    a.play().then(() => { this.audioUnlocked = true; }).catch(() => {});
  },

  // ── Public API ───────────────────────────────────────
  async toggle() {
    this.unlockAudio();
    switch (this.state) {
      case 'idle':    return this.play();
      case 'loading': return this.stop();     // click again = cancel
      case 'playing': return this.pause();
      case 'paused':  return this.resume();
    }
  },

  async play() {
    hideAutoAdvanceCountdown();
    // Always start from a known-clean slate.
    this.stop();
    const text = getDisplayText();
    if (!text.trim()) return;

    if (this.azureAvailable) {
      await this._playAzure(text);
    } else {
      this._playBrowser(text);
    }
  },

  async playFromWord(startIndex) {
    hideAutoAdvanceCountdown();
    const words = splitWords(getDisplayText());
    if (!words.length) return;
    if (!Number.isInteger(startIndex) || startIndex < 0 || startIndex >= words.length) return;

    const textFromWord = words.slice(startIndex).join(' ');
    if (!textFromWord) return;

    // Keep word-click aligned with the GPT voice by seeking the already-cached
    // Azure audio for this page when available.
    if (this.azureAvailable) {
      const started = await this._playAzureFromWord(getDisplayText(), startIndex);
      if (started) return;
      showToast('Tap play once to load GPT narration, then click a word', 'error');
      return;
    }

    // Browser-only fallback when Azure narration is unavailable.
    this.stop();
    if (!window.speechSynthesis) {
      showToast('Narration not supported in this browser', 'error');
      return;
    }

    this._playBrowser(textFromWord, {
      startIndex,
      fallbackMsPerWord: 300,
      useSavedUtteranceRef: true,
    });
  },

  pause() {
    if (this.state !== 'playing') return;
    if (this.audio) {
      this.audio.pause();
    } else if (window.speechSynthesis) {
      try { window.speechSynthesis.pause(); } catch { /* ignore */ }
    }
    clearInterval(this.highlightTimer);
    this._setState('paused');
  },

  resume() {
    hideAutoAdvanceCountdown();
    if (this.state !== 'paused') return;

    if (this.audio) {
      this._setState('playing');
      this.audio.play()
        .then(() => this._startAzureHighlight(getDisplayText(), this.audio))
        .catch(() => this._softReset());
      return;
    }
    if (window.speechSynthesis && this.utterance) {
      try { window.speechSynthesis.resume(); } catch { /* ignore */ }
      this._setState('playing');
      this._startBrowserFallback(this.utterance, 300, true);
    }
  },

  stop() {
    hideAutoAdvanceCountdown();
    // Bumping generation cancels any in-flight async work.
    this.generation++;

    if (this.controller) {
      try { this.controller.abort(); } catch { /* ignore */ }
      this.controller = null;
    }

    if (this.audio) {
      try { this.audio.pause(); } catch { /* ignore */ }
      this.audio.onended = null;
      this.audio.onerror = null;
      this.audio.onloadedmetadata = null;
      this.audio = null;
    }

    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel(); } catch { /* ignore */ }
    }
    this.utterance = null;

    clearInterval(this.highlightTimer);
    this.highlightTimer = null;
    this.browserBoundarySeen = false;
    this.browserLastBoundaryAt = 0;
    this.browserFallbackStartIndex = 0;
    this.browserFallbackWordCount = 0;
    this.browserFallbackIndex = 0;
    clearHighlight();

    this._setState('idle');
  },

  restart() {
    this.stop();
    return this.play();
  },

  /* Called when the user picks a different voice/model. If anything is
   * active (loading / playing / paused), restart with the new voice so
   * the switch is immediate. Cached blobs from other voices are kept —
   * their cache keys include the voice id. */
  onVoiceChange() {
    if (this.state === 'idle') return;
    const newVoice = this.currentVoiceId;
    if (newVoice && newVoice === this.activeVoiceId) return;
    this.restart();
  },

  onSpeedChange(rate) {
    if (this.audio && (this.state === 'playing' || this.state === 'paused')) {
      this.audio.playbackRate = rate;
      // Rehighlight timing depends on rate; restart highlight loop if playing.
      if (this.state === 'playing') {
        this._startAzureHighlight(getDisplayText(), this.audio);
      }
      return;
    }
    // Browser speechSynthesis can't change rate mid-utterance.
    if (this.utterance && window.speechSynthesis && window.speechSynthesis.speaking) {
      this.restart();
    }
  },

  _getAzureVoiceIdForPage() {
    const availableIds = new Set((this.azureVoices || []).map(v => v.id));
    if (this.activeVoiceId && availableIds.has(this.activeVoiceId)) return this.activeVoiceId;
    if (this.currentVoiceId && availableIds.has(this.currentVoiceId)) return this.currentVoiceId;
    return this.azureVoices[0]?.id || null;
  },

  async _playAzureFromWord(fullText, startIndex) {
    const words = splitWords(fullText);
    if (!words.length) return false;

    const voiceId = this._getAzureVoiceIdForPage();
    if (!voiceId) return false;

    const cacheKey = `${voiceId}:${currentLang}:${currentPage}`;
    const blobUrl = this.blobCache[cacheKey];
    if (!blobUrl) return false;

    this.stop();
    const gen = ++this.generation;
    this.activeVoiceId = voiceId;
    this._setState('loading');

    const fail = () => {
      if (gen !== this.generation) return;
      const cached = this.blobCache[cacheKey];
      if (cached) {
        try { URL.revokeObjectURL(cached); } catch { /* ignore */ }
        delete this.blobCache[cacheKey];
      }
      this._softReset();
    };

    try {
      const audio = new Audio(blobUrl);
      audio.playbackRate = this.currentSpeed;

      audio.onended = () => {
        if (gen !== this.generation) return;
        clearInterval(this.highlightTimer);
        clearHighlight();
        this.audio = null;
        this._setState('idle');
        startAutoAdvanceCountdown();
      };
      audio.onerror = fail;

      this.audio = audio;

      if (audio.readyState < 1) {
        await new Promise(resolve => {
          audio.addEventListener('loadedmetadata', resolve, { once: true });
        });
      }

      if (gen !== this.generation) return false;

      if (audio.duration && isFinite(audio.duration) && audio.duration > 0) {
        const ratio = Math.max(0, Math.min(1, startIndex / words.length));
        const seekTo = Math.min(
          Math.max(0, ratio * audio.duration),
          Math.max(0, audio.duration - 0.05)
        );
        try { audio.currentTime = seekTo; } catch { /* ignore */ }
      }

      await audio.play();
      if (gen !== this.generation) {
        try { audio.pause(); } catch { /* ignore */ }
        this.audio = null;
        return false;
      }

      this._setState('playing');
      this._startAzureHighlight(fullText, audio);
      return true;
    } catch {
      fail();
      return false;
    }
  },

  // ── Azure TTS playback ───────────────────────────────
  async _playAzure(text) {
    const voiceId = this.currentVoiceId || this.azureVoices[0]?.id;
    if (!voiceId) return;

    const gen      = ++this.generation;
    const cacheKey = `${voiceId}:${currentLang}:${currentPage}`;

    this.activeVoiceId = voiceId;
    this._setState('loading');

    // A single error path — audio.play() rejection and audio.onerror can both
    // fire for one underlying failure, so dedupe by first-one-wins.
    let reported = false;
    const fail = (msg) => {
      if (gen !== this.generation || reported) return;
      reported = true;
      // Broken blob URL — drop it so the next attempt refetches.
      const cached = this.blobCache[cacheKey];
      if (cached) {
        try { URL.revokeObjectURL(cached); } catch { /* ignore */ }
        delete this.blobCache[cacheKey];
      }
      this._softReset();
      if (msg) showToast(msg, 'error');
    };

    try {
      let blobUrl = this.blobCache[cacheKey];

      if (!blobUrl) {
        const token = localStorage.getItem('cc_token');
        this.controller = new AbortController();

        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch('/api/tts', {
          method:  'POST',
          headers,
          body:    JSON.stringify({ text, voice: voiceId }),
          signal:  this.controller.signal,
        });
        if (gen !== this.generation) return;
        if (!res.ok) throw new Error(`fetch:${res.status}`);

        // Guard against upstream returning HTML/JSON instead of audio — the
        // <audio> element can't decode those and would throw a confusing error.
        const ct = (res.headers.get('Content-Type') || '').toLowerCase();
        const blob = await res.blob();
        if (gen !== this.generation) return;
        if (!ct.startsWith('audio/') || blob.size === 0) {
          throw new Error('bad-audio');
        }

        blobUrl = URL.createObjectURL(blob);
        this.blobCache[cacheKey] = blobUrl;
      }

      if (gen !== this.generation) return;

      const audio = new Audio(blobUrl);
      audio.playbackRate = this.currentSpeed;

      audio.onended = () => {
        if (gen !== this.generation) return;
        clearInterval(this.highlightTimer);
        clearHighlight();
        this.audio = null;
        this._setState('idle');
        startAutoAdvanceCountdown();
      };
      audio.onerror = () => fail('Narration playback failed — try again');

      this.audio = audio;
      await audio.play();

      if (gen !== this.generation) {
        try { audio.pause(); } catch { /* ignore */ }
        this.audio = null;
        return;
      }

      this._setState('playing');
      this._startAzureHighlight(text, audio);
    } catch (err) {
      if (gen !== this.generation) return;
      if (err && err.name === 'AbortError') return;

      console.error('[Narrator]', err && err.name, err && err.message);

      if (err && err.name === 'NotAllowedError') {
        fail('Tap play again to start audio');
      } else if (err && typeof err.message === 'string' && err.message.startsWith('fetch:')) {
        const status = err.message.split(':')[1];
        fail(status === '401'
          ? 'Please log in to use voice narration'
          : 'Voice generation failed — try again');
      } else if (err && err.message === 'bad-audio') {
        fail('Voice service returned no audio — try again');
      } else {
        fail('Narration failed — try again');
      }
    }
  },

  // ── Browser TTS fallback ─────────────────────────────
  _highlightWord(wordIndex) {
    clearHighlight();
    const target = document.querySelector(`.word-span[data-index="${wordIndex}"]`);
    if (!target) return;
    target.classList.add('highlighted');
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  _startBrowserFallback(utterance, msPerWord = 300, resume = false) {
    clearInterval(this.highlightTimer);
    this.highlightTimer = null;

    if (!utterance || this.browserFallbackWordCount <= 0) return;

    const rate = this.currentSpeed || 1;
    const tick = Math.max(120, msPerWord / rate);
    const start = this.browserFallbackStartIndex;
    const end = start + this.browserFallbackWordCount - 1;

    if (!resume) {
      this.browserFallbackIndex = start;
      this._highlightWord(this.browserFallbackIndex);
    } else if (this.browserFallbackIndex < start) {
      this.browserFallbackIndex = start;
      this._highlightWord(this.browserFallbackIndex);
    }

    this.highlightTimer = setInterval(() => {
      if (this.utterance !== utterance || this.state !== 'playing') return;
      if (
        this.browserBoundarySeen &&
        (Date.now() - this.browserLastBoundaryAt) <= (tick * 1.8)
      ) {
        return;
      }
      if (this.browserFallbackIndex >= end) {
        clearInterval(this.highlightTimer);
        this.highlightTimer = null;
        return;
      }
      this.browserFallbackIndex += 1;
      this._highlightWord(this.browserFallbackIndex);
    }, tick);
  },

  _playBrowser(text, options = {}) {
    const synth = window.speechSynthesis;
    if (!synth) { showToast('Narration not supported in this browser', 'error'); return; }

    const startIndex = Number.isInteger(options.startIndex) ? options.startIndex : 0;
    const fallbackMsPerWord = options.fallbackMsPerWord || 300;
    const useSavedUtteranceRef = !!options.useSavedUtteranceRef;
    const wordCount = splitWords(text).length;
    this.browserBoundarySeen = false;
    this.browserLastBoundaryAt = 0;
    this.browserFallbackStartIndex = startIndex;
    this.browserFallbackWordCount = wordCount;
    this.browserFallbackIndex = startIndex;

    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);

    const voiceFromRef = useSavedUtteranceRef ? this._matchVoiceByRef(this.browserVoiceRef) : null;
    const voice = voiceFromRef || this._resolveSelectedBrowserVoice();
    if (voice) {
      u.voice = voice;
    }
    const saved = this.browserUtteranceRef;
    u.rate = useSavedUtteranceRef && saved ? saved.rate : this.currentSpeed;
    u.pitch = useSavedUtteranceRef && saved ? saved.pitch : 1.1;
    u.volume = useSavedUtteranceRef && saved ? saved.volume : 1;
    this._rememberBrowserUtterance(u);
    u.onstart = () => {
      if (this.utterance !== u) return;
      // Capture the effective voice/settings actually used by the browser.
      this._rememberBrowserUtterance(u);
    };

    u.onboundary = (e) => {
      if (this.utterance !== u) return;
      if (e.name && e.name !== 'word') return;
      const before = text.slice(0, e.charIndex || 0);
      const localWordIdx = before.trim() === '' ? 0 : before.trim().split(/\s+/).length;
      const wordIdx = startIndex + localWordIdx;
      this.browserBoundarySeen = true;
      this.browserLastBoundaryAt = Date.now();
      this.browserFallbackIndex = wordIdx;
      this._highlightWord(wordIdx);
    };
    u.onend = () => {
      if (this.utterance !== u) return;
      clearHighlight();
      this.utterance = null;
      clearInterval(this.highlightTimer);
      this.highlightTimer = null;
      this.browserBoundarySeen = false;
      this.browserLastBoundaryAt = 0;
      this.browserFallbackWordCount = 0;
      this._setState('idle');
      startAutoAdvanceCountdown();
    };
    u.onerror = () => {
      if (this.utterance !== u) return;
      this._softReset();
    };

    this.utterance = u;
    this._setState('playing');
    if (wordCount) {
      this._highlightWord(startIndex);
    }
    synth.speak(u);
    this._startBrowserFallback(u, fallbackMsPerWord);
  },

  /* Time-based word highlight for Azure audio. Uses audio.duration once
   * metadata has loaded — falls back to ~400 ms/word before that. */
  _startAzureHighlight(text, audio) {
    clearInterval(this.highlightTimer);
    this.highlightTimer = null;

    const words = text.trim().split(/\s+/);
    if (!words.length || !audio) return;

    const rate = audio.playbackRate || 1;
    let msPerWord = 400;
    if (audio.duration && isFinite(audio.duration) && audio.duration > 0) {
      msPerWord = (audio.duration * 1000) / words.length;
    } else {
      audio.addEventListener('loadedmetadata', () => {
        if (this.audio === audio && this.state === 'playing') {
          this._startAzureHighlight(text, audio);
        }
      }, { once: true });
    }
    const tick = Math.max(80, msPerWord / rate);

    // Sync highlight index to current playback position (supports resume).
    let idx = 0;
    if (audio.currentTime && audio.duration && isFinite(audio.duration) && audio.duration > 0) {
      idx = Math.floor((audio.currentTime / audio.duration) * words.length);
    }

    clearHighlight();
    const spans = document.querySelectorAll('.word-span');
    if (spans[idx]) spans[idx].classList.add('highlighted');

    this.highlightTimer = setInterval(() => {
      if (!this.audio || this.audio !== audio || this.audio.paused || this.state !== 'playing') {
        return;
      }
      clearHighlight();
      idx++;
      if (idx < words.length) {
        const el = document.querySelectorAll('.word-span')[idx];
        if (el) {
          el.classList.add('highlighted');
          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        clearInterval(this.highlightTimer);
        this.highlightTimer = null;
      }
    }, tick);
  },

  // ── State / UI ───────────────────────────────────────
  _softReset() {
    this.audio     = null;
    this.utterance = null;
    clearInterval(this.highlightTimer);
    this.highlightTimer = null;
    this.browserBoundarySeen = false;
    this.browserLastBoundaryAt = 0;
    this.browserFallbackStartIndex = 0;
    this.browserFallbackWordCount = 0;
    this.browserFallbackIndex = 0;
    clearHighlight();
    this._setState('idle');
  },

  _setState(s) {
    if (this.state === s) return;
    this.state = s;
    this._updateUI();
  },

  _updateUI() {
    const btn  = document.getElementById('narrate-btn');
    const icon = document.getElementById('narrate-icon');
    if (!btn || !icon) return;

    switch (this.state) {
      case 'loading':
        btn.classList.add('playing');
        icon.innerHTML =
          '<circle cx="6" cy="12" r="2" fill="white">' +
            '<animate attributeName="opacity" values=".3;1;.3" dur="1s" repeatCount="indefinite" begin="0s"/>' +
          '</circle>' +
          '<circle cx="12" cy="12" r="2" fill="white">' +
            '<animate attributeName="opacity" values=".3;1;.3" dur="1s" repeatCount="indefinite" begin=".2s"/>' +
          '</circle>' +
          '<circle cx="18" cy="12" r="2" fill="white">' +
            '<animate attributeName="opacity" values=".3;1;.3" dur="1s" repeatCount="indefinite" begin=".4s"/>' +
          '</circle>';
        btn.title = 'Loading voice… (click to cancel)';
        break;

      case 'playing':
        btn.classList.add('playing');
        icon.innerHTML =
          '<rect x="6"  y="4" width="4" height="16" fill="white"/>' +
          '<rect x="14" y="4" width="4" height="16" fill="white"/>';
        btn.title = 'Pause narration';
        break;

      case 'paused':
        btn.classList.remove('playing');
        icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3" fill="white"/>';
        btn.title = 'Resume narration';
        break;

      case 'idle':
      default:
        btn.classList.remove('playing');
        icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
        btn.title = 'Read aloud';
        break;
    }
  },
};

// ── Translation ────────────────────────────────────────
// Backed by /api/translate → Azure AI Translator. The hero's name is
// protected server-side via the story_id so it doesn't get translated.

const transDirCache = {};  // `${lang}` → "ltr" | "rtl"

function applyTextDirection(dir) {
  const container = document.getElementById('story-text-content');
  if (!container) return;
  container.setAttribute('dir', dir || 'ltr');
}

function showTranslateLoading(langLabel) {
  const ov = document.getElementById('translate-overlay');
  const tx = document.getElementById('translate-overlay-text');
  if (tx) tx.textContent = langLabel ? `Translating to ${langLabel}…` : 'Translating story…';
  if (ov) ov.classList.remove('hidden');
}
function hideTranslateLoading() {
  const ov = document.getElementById('translate-overlay');
  if (ov) ov.classList.add('hidden');
}

async function translatePage(lang) {
  if (lang === 'en') {
    currentLang = 'en';
    applyTextDirection('ltr');
    renderPage();
    return;
  }

  // Figure out which pages still need translating.
  const missingIdx = [];
  const missingText = [];
  pages.forEach((p, i) => {
    const txt = (p && p.text) || '';
    if (!txt) return;
    if (!transCache[`${lang}:${i}`]) {
      missingIdx.push(i);
      missingText.push(txt);
    }
  });

  // Everything already cached → just switch language and render.
  if (missingIdx.length === 0) {
    currentLang = lang;
    applyTextDirection(transDirCache[lang] || 'ltr');
    renderPage();
    return;
  }

  const langOpt = document.querySelector(`#lang-select option[value="${lang}"]`);
  const langLabel = langOpt ? langOpt.textContent.replace(/^[^A-Za-z]+/, '').trim() : lang;
  showTranslateLoading(langLabel);

  try {
    const res = await fetch('/api/translate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body:    JSON.stringify({
        texts:       missingText,
        target_lang: lang,
        story_id:    storyId(),
      }),
    });
    if (!res.ok) {
      if (res.status === 503) {
        showToast('Translation is unavailable right now', 'error');
      } else if (res.status === 401) {
        showToast('Please log in to translate', 'error');
      } else if (res.status === 413) {
        showToast('Story too long to translate in one go', 'error');
      } else {
        showToast('Translation failed — try again', 'error');
      }
      return;
    }
    const data = await res.json();
    const translated = data.translated || [];
    missingIdx.forEach((pageIdx, i) => {
      const t = translated[i] || pages[pageIdx].text;
      transCache[`${lang}:${pageIdx}`] = t;
    });
    transDirCache[lang] = data.direction || 'ltr';
    currentLang = lang;
    applyTextDirection(data.direction);
    renderPage();
  } catch {
    showToast('Translation failed — try again', 'error');
  } finally {
    hideTranslateLoading();
  }
}

// ── Favourite ──────────────────────────────────────────
async function toggleFav() {
  try {
    const res = await fetch(`/api/stories/${storyId()}/favorite`, { method: 'POST', headers: authHeaders() });
    if (!res.ok) throw new Error();
    const data = await res.json();
    isFav = data.isFavorite;
    updateFavBtn();
    showToast(isFav ? 'Added to favourites!' : 'Removed from favourites');
  } catch {
    showToast('Could not update favourite', 'error');
  }
}
function updateFavBtn() {
  const btn  = document.getElementById('fav-btn');
  const icon = document.getElementById('fav-icon');
  if (isFav) {
    btn.classList.add('active');
    icon.setAttribute('fill', 'currentColor');
  } else {
    btn.classList.remove('active');
    icon.setAttribute('fill', 'none');
  }
}

// ── Popovers & button wiring ───────────────────────────
function setupPopovers() {
  // Big green play / pause toggle
  document.getElementById('narrate-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    handleNarrateButtonClick();
  });

  // Reset — stop & restart from the beginning
  document.getElementById('reset-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    hideAutoAdvanceCountdown();
    Narrator.unlockAudio();
    Narrator.restart();
  });

  // Audio settings popover
  document.getElementById('volume-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    togglePanel('narrate-panel');
    closePanel('translate-panel');
  });

  // Translate popover
  document.getElementById('translate-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    togglePanel('translate-panel');
    closePanel('narrate-panel');
  });

  document.addEventListener('click', () => {
    closePanel('narrate-panel');
    closePanel('translate-panel');
  });
  document.querySelectorAll('.popover-panel').forEach(p =>
    p.addEventListener('click', e => e.stopPropagation())
  );
}
function togglePanel(id) { document.getElementById(id).classList.toggle('hidden'); }
function closePanel(id)  { document.getElementById(id).classList.add('hidden'); }

// ── Event wiring ───────────────────────────────────────
document.getElementById('prev-btn').addEventListener('click', () => {
  hideAutoAdvanceCountdown();
  if (currentPage === 0) { window.location.href = '/'; }
  else { changePage(-1); }
});
document.getElementById('next-btn').addEventListener('click', () => {
  hideAutoAdvanceCountdown();
  if (pages.length > 0 && currentPage === pages.length - 1) { window.location.href = '/create'; }
  else { changePage(1); }
});

document.getElementById('fav-btn').addEventListener('click', toggleFav);

document.getElementById('font-toggle-btn').addEventListener('click', () => {
  isCrayon = !isCrayon;
  document.getElementById('font-toggle-btn').classList.toggle('active', isCrayon);
  renderPage();
});

document.getElementById('speed-range').addEventListener('input', (e) => {
  const rate = parseFloat(e.target.value);
  document.getElementById('speed-val').textContent = `${rate.toFixed(1)}×`;
  Narrator.onSpeedChange(rate);
});

document.getElementById('voice-select').addEventListener('change', () => {
  Narrator.onVoiceChange();
});

document.getElementById('translate-go').addEventListener('click', async () => {
  const lang = document.getElementById('lang-select').value;
  closePanel('translate-panel');
  await translatePage(lang);
});
document.getElementById('translate-reset').addEventListener('click', () => {
  currentLang = 'en';
  document.getElementById('lang-select').value = 'en';
  applyTextDirection('ltr');
  closePanel('translate-panel');
  renderPage();
});

// Pause if the tab is hidden — browser may suspend audio anyway, so align state.
document.addEventListener('visibilitychange', () => {
  if (document.hidden && Narrator.state === 'playing') {
    Narrator.pause();
  }
});

// ── Init ───────────────────────────────────────────────
setupPopovers();
setupAutoAdvanceControls();
Narrator.init();
loadStory();

// ── Page-flip: swipe + keyboard + ARIA ─────────────────
(function setupPageFlipInteractions() {
  const card = document.getElementById('story-card');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');
  if (!card) return;

  // ARIA — make the card a labelled storybook region.
  card.setAttribute('role', 'region');
  card.setAttribute('aria-roledescription', 'storybook page');
  card.setAttribute('aria-label', 'Story page');
  if (prevBtn && !prevBtn.getAttribute('aria-label')) prevBtn.setAttribute('aria-label', 'Previous page');
  if (nextBtn && !nextBtn.getAttribute('aria-label')) nextBtn.setAttribute('aria-label', 'Next page');

  // Keyboard arrows (ignore when typing into a field).
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      if (pages.length && currentPage < pages.length - 1) changePage(1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      if (currentPage > 0) changePage(-1);
    }
  });

  // Pointer-driven swipe with live curl tracking.
  let drag = null;
  card.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    // Don't hijack drags that start on interactive children (buttons/words).
    if (e.target.closest('button, a, input, select, .word-span')) return;
    drag = { startX: e.clientX, width: card.clientWidth || 1, dir: 0, progress: 0, pid: e.pointerId };
    try { card.setPointerCapture(e.pointerId); } catch (_) {}
    card.classList.add('pf-dragging');
  });
  card.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    if (Math.abs(dx) < 6) return;
    const dir = dx < 0 ? 1 : -1;
    if ((dir > 0 && currentPage >= pages.length - 1) || (dir < 0 && currentPage <= 0)) return;
    drag.dir = dir;
    drag.progress = Math.min(1, Math.abs(dx) / drag.width);
    const angle = drag.progress * 35 * -drag.dir; // soft curl during drag (capped)
    card.style.transform = `rotateY(${angle}deg)`;
    card.style.opacity = String(1 - drag.progress * 0.4);
  });
  function endDrag() {
    if (!drag) return;
    const d = drag; drag = null;
    card.classList.remove('pf-dragging');
    card.style.transform = '';
    card.style.opacity = '';
    if (d.dir && d.progress > 0.35) changePage(d.dir);
  }
  card.addEventListener('pointerup', endDrag);
  card.addEventListener('pointercancel', endDrag);
  card.addEventListener('pointerleave', (e) => { if (drag && e.pointerId === drag.pid) endDrag(); });
})();

// ── Fullscreen toggle ──────────────────────────────────
(function () {
  const btn = document.getElementById('fullscreen-btn');
  if (!btn) return;
  const enterIcon = document.getElementById('fullscreen-icon-enter');
  const exitIcon  = document.getElementById('fullscreen-icon-exit');
  const target = document.getElementById('viewer-root') || document.documentElement;

  function isFs() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }
  function syncIcon() {
    const fs = isFs();
    if (enterIcon) enterIcon.style.display = fs ? 'none' : '';
    if (exitIcon)  exitIcon.style.display  = fs ? '' : 'none';
    btn.classList.toggle('active', fs);
    btn.title = fs ? 'Exit fullscreen (F)' : 'Fullscreen (F)';
  }
  async function toggleFs() {
    try {
      if (isFs()) {
        await (document.exitFullscreen?.() ?? document.webkitExitFullscreen?.());
      } else {
        await (target.requestFullscreen?.() ?? target.webkitRequestFullscreen?.());
      }
    } catch (e) {
      if (typeof showToast === 'function') showToast('Fullscreen not available', 'error');
    }
  }

  btn.addEventListener('click', toggleFs);
  document.addEventListener('fullscreenchange', syncIcon);
  document.addEventListener('webkitfullscreenchange', syncIcon);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'f' && e.key !== 'F') return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
    e.preventDefault();
    toggleFs();
  });

  syncIcon();
})();

// ── PDF export (Caregiver+ tier) ───────────────────────
(function () {
  const btn = document.getElementById('pdf-btn');
  if (!btn) return;
  fetch('/api/subscription/status', { headers: authHeaders() })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data && data.features && data.features.pdf_export) {
        btn.classList.remove('hidden');
      }
    })
    .catch(() => {});
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const resp = await fetch(`/api/stories/${storyId()}/pdf`, { headers: authHeaders() });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        showToast(body.message || 'PDF export failed', 'error');
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'story.pdf';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } finally {
      btn.disabled = false;
    }
  });
})();
