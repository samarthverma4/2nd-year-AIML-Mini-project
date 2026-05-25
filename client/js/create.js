/* ─── Create story page ───────────────────────────────── */

// Auth guard
if (!localStorage.getItem('cc_token')) {
  window.location.href = '/login?redirect=/create';
}

const HERO_PALETTE = ['#9b6dff','#f59e0b','#22d3ee','#f472b6','#4ade80','#fb923c'];

let selectedChildId = null;

// ── Auth helper ────────────────────────────────────────
function authHeaders() {
  const t = localStorage.getItem('cc_token');
  return t ? { 'Authorization': `Bearer ${t}` } : {};
}

// ── Toast ──────────────────────────────────────────────
function showToast(msg, type = 'error') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ── Hero Picker ────────────────────────────────────────
function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function showHeroSummary(child) {
  const summary = document.getElementById('hero-summary');
  const genderMap = { male: 'Boy', female: 'Girl', neutral: 'Neutral', '': 'Neutral' };

  document.getElementById('hs-age').textContent = `Age ${child.age}`;
  document.getElementById('hs-gender').textContent = genderMap[child.gender] || child.gender;

  const medEl = document.getElementById('hs-medical');
  const mc = child.medicalChallenge || (child.conditions || []).join(', ');
  if (mc) { medEl.textContent = mc; medEl.classList.remove('hidden'); }
  else     { medEl.classList.add('hidden'); }

  const traitEl = document.getElementById('hs-traits');
  if (child.characteristics) { traitEl.textContent = child.characteristics; traitEl.classList.remove('hidden'); }
  else                       { traitEl.classList.add('hidden'); }

  summary.classList.remove('hidden');
}

async function loadHeroPicker() {
  const grid = document.getElementById('hero-picker-grid');
  let children = [];
  try {
    const res = await fetch('/api/children', { headers: authHeaders() });
    if (res.status === 401) { window.location.href = '/login'; return; }
    children = await res.json();
  } catch {
    grid.innerHTML = '<p style="color:var(--destructive);font-size:.9rem">Could not load heroes.</p>';
    return;
  }

  if (!Array.isArray(children) || !children.length) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:1.5rem 0">
        <p style="color:var(--muted-fg);margin-bottom:.75rem">No heroes yet — create one first.</p>
        <a href="/profiles" class="btn btn-secondary btn-sm">Go to Profiles</a>
      </div>`;
    return;
  }

  // Default to active child or first
  let active = null;
  try { active = JSON.parse(localStorage.getItem('cc_active_child')); } catch {}
  if (!active || !children.find(c => c.id === active.id)) active = children[0];

  grid.innerHTML = children.map((c, i) => {
    const color   = HERO_PALETTE[i % HERO_PALETTE.length];
    const initial = (c.name || '?')[0].toUpperCase();
    return `
      <button type="button" class="hero-pick-card" data-id="${c.id}">
        <div class="hero-pick-avatar" style="background:${color}">${escHtml(initial)}</div>
        <div class="hero-pick-name">${escHtml(c.name)}</div>
        ${c.medicalChallenge || (c.conditions||[]).length
          ? '<div class="hero-pick-badge">Hero</div>' : ''}
      </button>`;
  }).join('');

  // wire up clicks
  grid.querySelectorAll('.hero-pick-card').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('.hero-pick-card').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedChildId = Number(btn.dataset.id);
      const child = children.find(c => c.id === selectedChildId);
      if (child) showHeroSummary(child);
      document.getElementById('hero-error').classList.add('hidden');
    });
  });

  // pre-select active hero
  const activeBtn = grid.querySelector(`[data-id="${active.id}"]`);
  if (activeBtn) { activeBtn.click(); }
}

// ── Settings toggle ────────────────────────────────────
document.getElementById('settings-toggle').addEventListener('click', () => {
  document.getElementById('settings-panel').classList.toggle('hidden');
  document.getElementById('settings-toggle').classList.toggle('open');
});

// ── Form submit ────────────────────────────────────────
document.getElementById('create-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  if (!selectedChildId) {
    document.getElementById('hero-error').classList.remove('hidden');
    return;
  }

  document.getElementById('loading-overlay').classList.remove('hidden');
  document.getElementById('submit-btn').disabled = true;

  try {
    const headers = { 'Content-Type': 'application/json', ...authHeaders() };
    const form = e.target;

    const body = { childId: selectedChildId };

    const storyLength      = (form.storyLength      && form.storyLength.value)      || '';
    const tone             = (form.tone             && form.tone.value)             || '';
    const theme            = (form.theme            && form.theme.value)            || '';
    const villainType      = (form.villainType      && form.villainType.value)      || '';
    const endingType       = (form.endingType       && form.endingType.value)       || '';
    const readingLevel     = (form.readingLevel     && form.readingLevel.value)     || '';
    const illustrationStyle = (form.illustrationStyle && form.illustrationStyle.value) || '';

    if (storyLength)      body.storyLength      = storyLength;
    if (tone)             body.tone             = tone;
    if (theme)            body.theme            = theme;
    if (villainType)      body.villainType      = villainType;
    if (endingType)       body.endingType       = endingType;
    if (readingLevel)     body.readingLevel     = readingLevel;
    if (illustrationStyle) body.illustrationStyle = illustrationStyle;

    const res = await fetch('/api/stories/generate', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || err.message || `Server error ${res.status}`);
    }

    const story = await res.json();
    window.location.href = `/story/${story.id}?new=1`;
  } catch (err) {
    document.getElementById('loading-overlay').classList.add('hidden');
    document.getElementById('submit-btn').disabled = false;
    showToast(err.message || 'Something went wrong. Please try again.');
  }
});

// ── Init ───────────────────────────────────────────────
loadHeroPicker();
