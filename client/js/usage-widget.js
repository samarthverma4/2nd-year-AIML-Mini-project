/* Usage widget — small card showing tier + monthly usage. Renders only when logged in. */

(function () {
  const token = localStorage.getItem('cc_token');
  if (!token) return;

  const STYLE = `
    .usage-widget {
      max-width: 720px;
      margin: 1.5rem auto 0;
      background: var(--card);
      border: 2px solid var(--border);
      border-radius: var(--radius);
      padding: 1.1rem 1.4rem;
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 4px 16px rgba(124,58,237,.06);
    }
    .uw-tier {
      font-family: var(--font-display);
      font-weight: 600;
      font-size: .85rem;
      letter-spacing: .04em;
      text-transform: uppercase;
      padding: .35rem .75rem;
      border-radius: 9999px;
      background: var(--primary-light);
      color: var(--primary);
    }
    .uw-tier.caregiver { background: #fce7f3; color: #be185d; }
    .uw-tier.hospital  { background: #dcfce7; color: #15803d; }
    .uw-stats { display: flex; gap: 1.5rem; font-size: .9rem; color: var(--muted-fg); }
    .uw-stats strong { color: var(--foreground); font-weight: 700; }
    .uw-cta { font-size: .85rem; }
  `;

  const style = document.createElement('style');
  style.textContent = STYLE;
  document.head.appendChild(style);

  fetch('/api/subscription/status', { headers: { 'Authorization': `Bearer ${token}` } })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) return;
      const tier = data.tier || 'free';
      const usage = data.usage || {};
      const limits = data.limits || {};
      const fmt = (used, cap) => cap == null ? `${used} / ∞` : `${used} / ${cap}`;

      const upgrade = tier === 'free'
        ? `<a href="/pricing" class="btn btn-primary uw-cta">Upgrade</a>`
        : '';

      const widget = document.createElement('div');
      widget.className = 'usage-widget';
      widget.innerHTML = `
        <span class="uw-tier ${tier}">${tier}</span>
        <div class="uw-stats">
          <span>Stories this month: <strong>${fmt(usage.storybooks || 0, limits.storybooks)}</strong></span>
          <span>Heroes: <strong>${fmt(usage.child_profiles || 0, limits.child_profiles)}</strong></span>
        </div>
        ${upgrade}
      `;

      const hero = document.querySelector('.hero-inner') || document.querySelector('.hero') || document.body;
      hero.appendChild(widget);
    })
    .catch(() => {});
})();
