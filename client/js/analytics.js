/* Analytics dashboard — Hospital tier only. */

const token = localStorage.getItem('cc_token');
const content = document.getElementById('an-content');

if (!token) {
  window.location.href = '/login';
}

const HEADERS = { 'Authorization': `Bearer ${token}` };

function locked(reason) {
  content.innerHTML = `
    <div class="an-locked">
      <h2>Hospital plan required</h2>
      <p>${reason || 'Engagement analytics is part of our Hospital plan. Get in touch to upgrade.'}</p>
      <a href="/pricing" class="btn btn-primary">See plans</a>
    </div>
  `;
}

fetch('/api/analytics/engagement', { headers: HEADERS })
  .then(async r => {
    if (r.status === 403) {
      const body = await r.json().catch(() => ({}));
      locked(body.message);
      return null;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  })
  .then(data => {
    if (!data) return;
    render(data);
  })
  .catch(err => {
    content.textContent = '';
    const div = document.createElement('div');
    div.className = 'an-empty';
    div.textContent = `Could not load analytics: ${err.message}`;
    content.appendChild(div);
  });

function render(data) {
  const hasAny = (data.per_child?.length || 0) + (data.per_day?.length || 0) > 0;
  if (!hasAny) {
    content.innerHTML = `<div class="an-empty">No story activity in the last 30 days yet.</div>`;
    return;
  }

  content.innerHTML = `
    <div class="an-grid">
      <div class="an-card full"><h3>Stories per day</h3><canvas id="chart-daily"></canvas></div>
      <div class="an-card"><h3>Stories per child</h3><canvas id="chart-children"></canvas></div>
      <div class="an-card"><h3>Top conditions / themes</h3><canvas id="chart-conditions"></canvas></div>
      <div class="an-card full"><h3>Read time per child (minutes)</h3><canvas id="chart-readtime"></canvas></div>
    </div>
  `;

  const c1 = document.getElementById('chart-daily').getContext('2d');
  new Chart(c1, {
    type: 'line',
    data: {
      labels: data.per_day.map(d => d.day),
      datasets: [{
        label: 'Stories', data: data.per_day.map(d => d.stories),
        borderColor: '#7c3aed', backgroundColor: 'rgba(124,58,237,.15)',
        tension: .35, fill: true, pointRadius: 4,
      }],
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } },
  });

  const c2 = document.getElementById('chart-children').getContext('2d');
  new Chart(c2, {
    type: 'bar',
    data: {
      labels: data.per_child.map(d => d.child_name),
      datasets: [{ label: 'Stories', data: data.per_child.map(d => d.stories), backgroundColor: '#38bdf8' }],
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } },
  });

  const c3 = document.getElementById('chart-conditions').getContext('2d');
  new Chart(c3, {
    type: 'doughnut',
    data: {
      labels: data.by_condition.map(d => d.condition),
      datasets: [{
        data: data.by_condition.map(d => d.stories),
        backgroundColor: ['#7c3aed', '#38bdf8', '#f59e0b', '#ec4899', '#10b981', '#f97316', '#06b6d4', '#a78bfa'],
      }],
    },
  });

  const c4 = document.getElementById('chart-readtime').getContext('2d');
  new Chart(c4, {
    type: 'bar',
    data: {
      labels: data.read_time.map(d => d.child_name),
      datasets: [{
        label: 'Minutes',
        data: data.read_time.map(d => Math.round((d.read_seconds || 0) / 60)),
        backgroundColor: '#f59e0b',
      }],
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });
}
