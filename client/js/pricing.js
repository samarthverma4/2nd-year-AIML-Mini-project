/* Pricing page — renders three tier cards from /api/subscription/plans */

const TIER_META = {
  free: {
    name: 'Free',
    tag: 'For families just getting started',
    featured: false,
    cta: { label: 'Get started', action: 'signup' },
    bullets: [
      { t: '3 storybooks per month', y: true },
      { t: '1 child profile', y: true },
      { t: 'Basic story themes', y: true },
      { t: 'TTS narration in English', y: true },
      { t: 'Multilingual TTS', y: false },
      { t: 'PDF export', y: false },
      { t: 'Face personalisation', y: false },
    ],
  },
  caregiver: {
    name: 'Caregiver',
    tag: 'For active families',
    featured: true,
    price: '₹299', period: 'month',
    cta: { label: 'Subscribe', action: 'subscribe' },
    bullets: [
      { t: '20 storybooks per month', y: true },
      { t: '3 child profiles', y: true },
      { t: 'All themes + custom mood', y: true },
      { t: 'Multilingual TTS (5 languages)', y: true },
      { t: 'PDF export', y: true },
      { t: 'Face-based personalisation', y: true },
    ],
  },
  hospital: {
    name: 'Hospital',
    tag: 'For pediatric care teams',
    featured: false,
    price: '₹4,999', period: 'month',
    cta: { label: 'Contact sales', action: 'contact' },
    bullets: [
      { t: 'Unlimited storybooks', y: true },
      { t: 'Unlimited child profiles', y: true },
      { t: '10 staff accounts per organisation', y: true },
      { t: 'All 10+ TTS languages', y: true },
      { t: 'Engagement analytics dashboard', y: true },
      { t: 'Custom hospital branding', y: true },
      { t: 'Priority support', y: true },
    ],
  },
};

const ICON_CHECK = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary);"><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_X = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

function renderPlans() {
  const grid = document.getElementById('plans-grid');
  const order = ['free', 'caregiver', 'hospital'];
  grid.innerHTML = order.map(tier => {
    const m = TIER_META[tier];
    const priceHtml = tier === 'free'
      ? `<div class="plan-price">₹0 <small>/ forever</small></div>`
      : `<div class="plan-price">${m.price} <small>/ ${m.period}</small></div>`;
    const bullets = m.bullets.map(b =>
      `<li class="${b.y ? 'yes' : 'no'}">${b.y ? ICON_CHECK : ICON_X}<span>${b.t}</span></li>`
    ).join('');
    const btnClass = m.featured ? 'btn btn-primary plan-cta' : 'btn btn-outline plan-cta';
    return `
      <div class="plan-card ${m.featured ? 'featured' : ''}">
        <div class="plan-name">${m.name}</div>
        <div class="plan-tag">${m.tag}</div>
        ${priceHtml}
        <ul class="plan-features">${bullets}</ul>
        <button class="${btnClass}" data-tier="${tier}" data-action="${m.cta.action}">${m.cta.label}</button>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('button[data-action]').forEach(btn => {
    btn.addEventListener('click', () => handleCta(btn.dataset.tier, btn.dataset.action));
  });
}

function showModal(title, body) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent = body;
  document.getElementById('cta-modal').classList.add('show');
}
document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('cta-modal').classList.remove('show');
});

function handleCta(tier, action) {
  if (action === 'signup') {
    window.location.href = localStorage.getItem('cc_token') ? '/' : '/login';
    return;
  }
  if (action === 'contact') {
    showModal(
      'Talk to our team',
      'For Hospital plans we set things up by contract. Send us a note via the Help & Support page and we’ll get back within 1 business day.',
    );
    return;
  }
  if (action === 'subscribe') {
    showModal(
      'Subscriptions launching soon',
      'Online payments are coming shortly. In the meantime drop us a note via Help & Support and we’ll activate Caregiver for you manually.',
    );
  }
}

renderPlans();
