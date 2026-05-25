/**
 * PageFlip — vanilla JS storybook page-flip transition.
 *
 * Usage:
 *   const flip = createPageFlip({
 *     mount: document.getElementById('story-reader-root'),
 *     pages: [{ imageUrl, text }, ...],
 *     renderPage: (page, { isActive }) => {
 *       const el = document.createElement('div');
 *       el.innerHTML = `<img src="${page.imageUrl}" alt=""><p>${page.text}</p>`;
 *       return el;
 *     },
 *     onFlipStart: (dir) => tts.pause(),
 *     onFlipEnd:   (dir, newIndex) => tts.playPage(newIndex),
 *     onIndexChange: (i) => { /* sync external state *\/ },
 *   });
 *   flip.goTo(0);
 *   // later: flip.next(); flip.prev(); flip.setPages(newPages); flip.destroy();
 */
function createPageFlip(opts) {
  const {
    mount,
    renderPage,
    onIndexChange = () => {},
    onFlipStart = () => {},
    onFlipEnd = () => {},
  } = opts;

  let pages = opts.pages || [];
  let index = 0;
  let drag = null;           // { dir, progress, animating }
  let dragState = null;      // { startX, width, dir }
  let animTimer = null;

  const reduceMotionMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  let reduceMotion = reduceMotionMQ.matches;
  const onMQChange = (e) => { reduceMotion = e.matches; root.classList.toggle('pf-reduced', reduceMotion); };
  reduceMotionMQ.addEventListener('change', onMQChange);

  // ---- DOM ----
  const root = document.createElement('div');
  root.className = 'pf-root' + (reduceMotion ? ' pf-reduced' : '');
  root.tabIndex = 0;
  root.setAttribute('role', 'region');
  root.setAttribute('aria-roledescription', 'storybook');
  root.setAttribute('aria-label', 'Story pages');

  const live = document.createElement('div');
  live.className = 'pf-sr';
  live.setAttribute('aria-live', 'polite');
  live.setAttribute('aria-atomic', 'true');

  const stage = document.createElement('div');
  stage.className = 'pf-stage';

  const underlay = document.createElement('div');
  underlay.className = 'pf-page pf-underlay';
  underlay.setAttribute('aria-hidden', 'true');

  const active = document.createElement('div');
  active.className = 'pf-page pf-active is-active';
  active.tabIndex = -1;

  const shadow = document.createElement('div');
  shadow.className = 'pf-shadow';
  active.appendChild(shadow);

  const prevBtn = document.createElement('button');
  prevBtn.className = 'pf-nav pf-prev';
  prevBtn.setAttribute('aria-label', 'Previous page');
  prevBtn.textContent = '‹';

  const nextBtn = document.createElement('button');
  nextBtn.className = 'pf-nav pf-next';
  nextBtn.setAttribute('aria-label', 'Next page');
  nextBtn.textContent = '›';

  stage.appendChild(underlay);
  stage.appendChild(active);
  root.appendChild(live);
  root.appendChild(stage);
  root.appendChild(prevBtn);
  root.appendChild(nextBtn);
  mount.appendChild(root);

  // ---- helpers ----
  function canPrev() { return index > 0; }
  function canNext() { return index < pages.length - 1; }

  function preloadNeighbours() {
    [index - 1, index + 1].forEach((i) => {
      const p = pages[i];
      if (p && p.imageUrl) { const img = new Image(); img.src = p.imageUrl; }
    });
  }

  function announce() {
    live.textContent = `Page ${index + 1} of ${pages.length}`;
  }

  function renderInto(container, page, isActive) {
    // Clear children except the shadow node (kept on active layer).
    [...container.childNodes].forEach((n) => { if (n !== shadow) container.removeChild(n); });
    if (!page) return;
    const node = renderPage(page, { isActive });
    if (node) container.insertBefore(node, shadow.parentNode === container ? shadow : null);
  }

  function applyFlipTransform() {
    const angle = drag ? drag.progress * 180 * drag.dir * -1 : 0;
    active.style.transform = `rotateY(${angle}deg)`;
    active.style.transition = drag && drag.animating
      ? 'transform 520ms cubic-bezier(.22,.61,.36,1)'
      : drag ? 'none' : 'transform 280ms ease';
    shadow.style.opacity = drag ? String(0.35 * drag.progress) : '0';
  }

  function paint() {
    const cur = pages[index];
    const neighbourIdx = index + ((drag && drag.dir) || 1);
    const neighbour = pages[neighbourIdx] || pages[index];
    renderInto(active, cur, true);
    renderInto(underlay, neighbour, false);
    prevBtn.disabled = !canPrev();
    nextBtn.disabled = !canNext();
    applyFlipTransform();
  }

  function commit(dir) {
    const target = index + dir;
    if (target < 0 || target >= pages.length) return;
    onFlipStart(dir);
    if (reduceMotion) {
      index = target;
      drag = null;
      paint();
      announce();
      onIndexChange(index, dir);
      onFlipEnd(dir, index);
      return;
    }
    drag = { dir, progress: 1, animating: true };
    applyFlipTransform();
    clearTimeout(animTimer);
    animTimer = setTimeout(() => {
      index = target;
      drag = null;
      paint();
      announce();
      active.focus({ preventScroll: true });
      onIndexChange(index, dir);
      onFlipEnd(dir, index);
      preloadNeighbours();
    }, 520);
  }

  function go(dir) {
    if (dir > 0 && canNext()) commit(1);
    else if (dir < 0 && canPrev()) commit(-1);
  }

  // ---- events ----
  function onKey(e) {
    if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
  }
  function onPointerDown(e) {
    if (reduceMotion) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    dragState = { startX: e.clientX, width: root.clientWidth, dir: 0 };
    try { root.setPointerCapture(e.pointerId); } catch (_) {}
  }
  function onPointerMove(e) {
    if (!dragState) return;
    const dx = e.clientX - dragState.startX;
    if (Math.abs(dx) < 6) return;
    const dir = dx < 0 ? 1 : -1;
    if ((dir > 0 && !canNext()) || (dir < 0 && !canPrev())) return;
    const progress = Math.min(1, Math.abs(dx) / dragState.width);
    dragState.dir = dir;
    drag = { dir, progress, animating: false };
    // Re-render underlay only if neighbour direction changed.
    const neighbour = pages[index + dir];
    renderInto(underlay, neighbour || pages[index], false);
    applyFlipTransform();
  }
  function onPointerUp() {
    const s = dragState;
    dragState = null;
    if (!s || !s.dir) { drag = null; applyFlipTransform(); return; }
    const cur = (drag && drag.progress) || 0;
    if (cur > 0.4) { commit(s.dir); return; }
    drag = { dir: s.dir, progress: 0, animating: true };
    applyFlipTransform();
    clearTimeout(animTimer);
    animTimer = setTimeout(() => { drag = null; applyFlipTransform(); }, 280);
  }

  root.addEventListener('keydown', onKey);
  root.addEventListener('pointerdown', onPointerDown);
  root.addEventListener('pointermove', onPointerMove);
  root.addEventListener('pointerup', onPointerUp);
  root.addEventListener('pointercancel', onPointerUp);
  prevBtn.addEventListener('click', () => go(-1));
  nextBtn.addEventListener('click', () => go(1));

  // ---- init ----
  paint();
  announce();
  preloadNeighbours();

  // ---- public API ----
  return {
    next() { go(1); },
    prev() { go(-1); },
    goTo(i) {
      if (i < 0 || i >= pages.length || i === index) return;
      const dir = i > index ? 1 : -1;
      // Jump to target without animating each page — fade swap.
      index = i;
      drag = null;
      paint();
      announce();
      onIndexChange(index, dir);
      preloadNeighbours();
    },
    setPages(newPages, startIndex = 0) {
      pages = newPages || [];
      index = Math.max(0, Math.min(startIndex, pages.length - 1));
      drag = null;
      paint();
      announce();
      preloadNeighbours();
    },
    getIndex() { return index; },
    destroy() {
      clearTimeout(animTimer);
      reduceMotionMQ.removeEventListener('change', onMQChange);
      root.remove();
    },
  };
}

if (typeof window !== 'undefined') window.createPageFlip = createPageFlip;
if (typeof module !== 'undefined' && module.exports) module.exports = { createPageFlip };
