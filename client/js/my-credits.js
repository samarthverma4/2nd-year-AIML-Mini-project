/* ─── My Subscription dashboard ───────────────────────── */

const Auth = {
  getToken()  { return localStorage.getItem('cc_token'); },
  getUser()   { try { return JSON.parse(localStorage.getItem('cc_user')); } catch { return null; } },
  isLoggedIn(){ return !!this.getToken(); },
  headers()   {
    const h = { 'Content-Type': 'application/json' };
    const t = this.getToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  },
};

function showToast(msg, type = 'error') {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

if (!Auth.isLoggedIn()) {
  document.getElementById('dashboard').style.display = 'none';
  document.getElementById('login-required').style.display = 'block';
} else {
  loadSubscription();
}

const FEATURE_LABELS = {
  multilingual_tts: 'Multilingual narration',
  pdf_export:       'PDF export',
  face_api:         'Face-based hero personalisation',
  custom_mood:      'Custom story mood',
  analytics:        'Engagement analytics',
  custom_branding:  'Custom hospital branding',
};

const TIER_BLURB = {
  free:      'You\'re on the Free plan. Upgrade for more stories, multilingual narration, and PDF export.',
  caregiver: 'You\'re on the Caregiver plan — thanks for supporting Cartoon Care!',
  hospital:  'Your organisation is on the Hospital plan. Engagement analytics is unlocked.',
};

const ICON_CHECK = `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary);"><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_X     = `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

async function loadSubscription() {
  try {
    const res = await fetch('/api/subscription/status', { headers: Auth.headers() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderSummary(data);
    renderFeatures(data);
  } catch (err) {
    showToast(`Could not load subscription: ${err.message}`);
  }
}

function fmtUsage(used, cap) {
  if (cap == null) return `${used} <small>/ unlimited</small>`;
  return `${used} <small>/ ${cap}</small>`;
}

function progressBar(used, cap) {
  if (cap == null) return '';
  const pct = Math.min(100, Math.round((used / cap) * 100));
  const cls = pct >= 100 ? 'progress danger' : pct >= 80 ? 'progress warn' : 'progress';
  return `<div class="${cls}"><div style="width:${pct}%"></div></div>`;
}

function fmtExpiry(iso) {
  if (!iso) return 'No expiry';
  try {
    const d = new Date(iso);
    if (isNaN(d)) return 'No expiry';
    const days = Math.ceil((d - new Date()) / (1000 * 60 * 60 * 24));
    if (days <= 0) return 'Expired';
    return `${d.toLocaleDateString()} <small>(${days} day${days === 1 ? '' : 's'} left)</small>`;
  } catch {
    return 'No expiry';
  }
}

function renderSummary(data) {
  const tier = data.tier || 'free';
  const usage = data.usage || {};
  const limits = data.limits || {};
  const wrap = document.getElementById('sub-summary');

  const expiryCard = (tier === 'free')
    ? `<div class="sub-card"><div class="lbl">Status</div><div class="val">Free plan</div></div>`
    : `<div class="sub-card"><div class="lbl">Renews / expires</div><div class="val" style="font-size:1.1rem">${fmtExpiry(data.expires_at)}</div></div>`;

  wrap.innerHTML = `
    <div class="sub-card">
      <div class="lbl">Current plan</div>
      <div class="val"><span class="sub-tier ${tier}">${tier}</span></div>
    </div>
    <div class="sub-card">
      <div class="lbl">Stories this month</div>
      <div class="val">${fmtUsage(usage.storybooks || 0, limits.storybooks)}</div>
      ${progressBar(usage.storybooks || 0, limits.storybooks)}
    </div>
    <div class="sub-card">
      <div class="lbl">Hero profiles</div>
      <div class="val">${fmtUsage(usage.child_profiles || 0, limits.child_profiles)}</div>
      ${progressBar(usage.child_profiles || 0, limits.child_profiles)}
    </div>
    ${expiryCard}
  `;
}

function renderFeatures(data) {
  const tier = data.tier || 'free';
  const features = data.features || {};
  document.getElementById('features-desc').textContent = TIER_BLURB[tier] || '';

  const list = document.getElementById('feature-list');
  list.innerHTML = Object.entries(FEATURE_LABELS).map(([key, label]) => {
    const has = !!features[key];
    return `<li class="${has ? 'yes' : 'no'}">${has ? ICON_CHECK : ICON_X}<span>${label}</span></li>`;
  }).join('');

  const cta = document.getElementById('upgrade-cta');
  if (tier === 'free') {
    cta.innerHTML = `<a href="/pricing" class="btn btn-primary">See plans &amp; upgrade</a>`;
  } else if (tier === 'caregiver') {
    cta.innerHTML = `<a href="/pricing" class="btn btn-outline">View Hospital plan</a>`;
  } else {
    cta.innerHTML = '';
  }
}
