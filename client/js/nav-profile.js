/* ─── Shared Nav Profile Dropdown ──────────────────────
 *  Renders the user avatar + dropdown menu with:
 *    - Live credit balance
 *    - My Credits link
 *    - Admin Dashboard (if admin)
 *    - Switch Account
 *    - Logout
 *  Include this script on every page that has <div id="nav-auth"></div>
 * ────────────────────────────────────────────────────── */

(function () {
  'use strict';

  const nav = document.getElementById('nav-auth');
  if (!nav) return;

  /* ── Auth helpers ────────────────────────────────────── */
  const token = localStorage.getItem('cc_token');
  let user;
  try { user = JSON.parse(localStorage.getItem('cc_user')); } catch { user = null; }

  /* ─ Not logged in → simple Login button ─────────────── */
  if (!user || !token) {
    nav.innerHTML =
      '<a href="/login" class="btn btn-primary btn-sm" style="padding:.5rem 1.25rem;font-size:.9rem">' +
        '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>' +
        ' Login</a>';
    return;
  }

  /* ── Logged in → build profile dropdown ─────────────── */
  const initial = (user.name || user.email || 'U')[0].toUpperCase();
  const displayName = user.name || user.email || 'User';

  nav.innerHTML = `
    <div class="profile-dropdown-wrap" id="profile-dd-wrap">
      <button class="profile-trigger" id="profile-trigger" aria-haspopup="true" aria-expanded="false">
        <div class="nav-avatar">${initial}</div>
        <span class="nav-username">${displayName}</span>
        <svg class="profile-chevron" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      <div class="profile-dropdown" id="profile-dropdown" role="menu">
        <!-- Credit balance row -->
        <div class="dd-credit-row" id="dd-credit-row">
          <div class="dd-credit-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>
            </svg>
          </div>
          <div class="dd-credit-info">
            <span class="dd-credit-label">Credit Balance</span>
            <span class="dd-credit-value" id="dd-credit-value">
              <span class="dd-credit-loading"></span>
            </span>
          </div>
        </div>

        <div class="dd-divider"></div>

        <!-- Menu items -->
        <a href="/account" class="dd-item" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          Account Settings
        </a>

        <a href="/profiles" class="dd-item" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
            <circle cx="19" cy="5" r="2"/>
            <line x1="19" y1="3" x2="19" y2="7"/>
            <line x1="17" y1="5" x2="21" y2="5"/>
          </svg>
          Profile Settings
        </a>

        <a href="/my-credits" class="dd-item" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          My Subscription
        </a>

        <a href="/feedback" class="dd-item" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          Help &amp; Support
        </a>

        <div class="dd-admin-slot" id="dd-admin-slot"></div>

        <div class="dd-divider"></div>

        <a href="/profiles" class="dd-item" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
            <path d="M19 8l2 2 4-4" transform="scale(.55) translate(14,2)"/>
          </svg>
          Switch Hero
        </a>

        <button class="dd-item" id="dd-switch-account" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="8.5" cy="7" r="4"/>
            <polyline points="17 11 19 13 23 9"/>
          </svg>
          Switch Account
        </button>

        <button class="dd-item dd-item-danger" id="dd-logout" role="menuitem">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
          Logout
        </button>
      </div>
    </div>
  `;

  /* ── Toggle dropdown ─────────────────────────────────── */
  const trigger = document.getElementById('profile-trigger');
  const dropdown = document.getElementById('profile-dropdown');
  let open = false;

  function toggle(force) {
    open = typeof force === 'boolean' ? force : !open;
    dropdown.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', String(open));
  }

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    toggle();
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (open && !dropdown.contains(e.target) && !trigger.contains(e.target)) {
      toggle(false);
    }
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && open) toggle(false);
  });

  /* ── Logout ──────────────────────────────────────────── */
  document.getElementById('dd-logout').addEventListener('click', () => {
    localStorage.removeItem('cc_token');
    localStorage.removeItem('cc_user');
    window.location.href = '/login';
  });

  /* ── Switch Account ──────────────────────────────────── */
  document.getElementById('dd-switch-account').addEventListener('click', () => {
    localStorage.removeItem('cc_token');
    localStorage.removeItem('cc_user');
    window.location.href = '/login#signup';
  });

  /* ── Load credit balance (real-time) ─────────────────── */
  (async function loadCreditBalance() {
    const el = document.getElementById('dd-credit-value');
    try {
      const res = await fetch('/api/credits/my', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (!res.ok) throw new Error('auth');
      const data = await res.json();
      const total = data.total_used != null ? data.total_used : 0;
      el.textContent = '$' + total.toFixed(2);
      el.classList.add('loaded');
    } catch {
      el.textContent = '—';
      el.classList.add('loaded');
    }
  })();

  /* ── Check admin status (best-effort) ────────────────── */
  (async function checkAdmin() {
    try {
      const res = await fetch('/api/admin/credits/overview', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (res.ok) {
        const slot = document.getElementById('dd-admin-slot');
        slot.innerHTML =
          '<a href="/admin-credits" class="dd-item dd-item-admin" role="menuitem">' +
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" ' +
              'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
              '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>' +
            '</svg>' +
            'Admin Dashboard' +
          '</a>';
      }
    } catch { /* not admin — ignore */ }
  })();

})();
