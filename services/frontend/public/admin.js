/* =====================================================
   CedarFix AI — admin.js
   Admin dashboard: stats, all complaints, review queue, duplicates
   ===================================================== */

const GATEWAY = window.GATEWAY_URL || 'http://localhost:8000';

// ── Auth guard ────────────────────────────────────────
const token    = localStorage.getItem('cf_token');
const role     = localStorage.getItem('cf_role');
const username = localStorage.getItem('cf_username');

if (!token || role !== 'admin') {
  window.location.href = 'login.html';
}

document.getElementById('adminUsername').textContent = `👤 ${username}`;

function logout() {
  localStorage.clear();
  window.location.href = 'login.html';
}

function authHeaders() {
  return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// ── Pagination state ──────────────────────────────────
const state = { all: { page: 1, total: 0 }, dup: { page: 1, total: 0 } };

// ── Tab switching ─────────────────────────────────────
function switchTab(tab) {
  ['all', 'review', 'dup'].forEach(t => {
    document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1) === 'All' ? 'All' : t === 'review' ? 'Review' : 'Dup'}`);
  });
  document.getElementById('tabAll').classList.toggle('active',    tab === 'all');
  document.getElementById('tabReview').classList.toggle('active', tab === 'review');
  document.getElementById('tabDup').classList.toggle('active',    tab === 'dup');
  document.getElementById('sectionAll').classList.toggle('active',    tab === 'all');
  document.getElementById('sectionReview').classList.toggle('active', tab === 'review');
  document.getElementById('sectionDup').classList.toggle('active',    tab === 'dup');

  if (tab === 'all')    loadAll();
  if (tab === 'review') loadReview();
  if (tab === 'dup')    loadDup();
}

// ── Stats ─────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await fetch(`${GATEWAY}/admin/stats`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return logout();
    const d = await res.json();
    document.getElementById('statTotal').textContent  = d.total ?? 0;
    document.getElementById('statReview').textContent = d.pending_review ?? 0;
    document.getElementById('statDup').textContent    = d.duplicates ?? 0;
    document.getElementById('statAuto').textContent   = d.auto_routed ?? 0;
    document.getElementById('statOpen').textContent   = d.open_reviews ?? 0;
    document.getElementById('reviewBadge').textContent = d.open_reviews ?? 0;
  } catch (e) { console.warn('Stats load failed', e); }
}

// ── Helpers ───────────────────────────────────────────
function severityPill(s) {
  const map = { low: 'pill-low', medium: 'pill-medium', high: 'pill-high', critical: 'pill-critical' };
  const cls = map[(s || '').toLowerCase()] || 'pill-new';
  return `<span class="badge-pill ${cls}">${s || '—'}</span>`;
}

function dupPill(s) {
  const map = {
    NEW: 'pill-new', DUPLICATE: 'pill-duplicate',
    RELATED_SAME_CLUSTER: 'pill-related', NEEDS_ADMIN_REVIEW: 'pill-review',
  };
  const cls = map[s] || 'pill-new';
  return `<span class="badge-pill ${cls}">${s || 'NEW'}</span>`;
}

function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
}

function shortId(id) {
  return id ? `<span style="font-family:monospace;font-size:12px;color:var(--gray-600)">${id.slice(0,8)}…</span>` : '—';
}

function changePage(section, delta) {
  state[section].page = Math.max(1, state[section].page + delta);
  if (section === 'all') loadAll();
  if (section === 'dup') loadDup();
}

function updatePagination(section, total, limit) {
  const pages = Math.ceil(total / limit) || 1;
  const p = state[section].page;
  document.getElementById(`${section}PageInfo`).textContent = `Page ${p} / ${pages}`;
  document.getElementById(`${section}Prev`).disabled = p <= 1;
  document.getElementById(`${section}Next`).disabled = p >= pages;
}

// ── All Complaints ────────────────────────────────────
async function loadAll() {
  document.getElementById('allTable').innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>Loading…</div>`;
  try {
    const res = await fetch(`${GATEWAY}/admin/complaints?page=${state.all.page}&limit=20`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return logout();
    const d = await res.json();
    state.all.total = d.total || 0;
    document.getElementById('allMeta').textContent = `${d.total} total`;
    updatePagination('all', d.total, 20);

    if (!d.complaints || d.complaints.length === 0) {
      document.getElementById('allTable').innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><p>No complaints yet.</p></div>`;
      return;
    }

    const rows = d.complaints.map(c => `
      <tr>
        <td>${shortId(c.id)}</td>
        <td>${fmtDate(c.created_at)}</td>
        <td><span class="text-preview" title="${(c.text_preview||'').replace(/"/g,'&quot;')}">${c.text_preview || '—'}</span></td>
        <td>${c.complaint_type || '—'}</td>
        <td>${severityPill(c.severity)}</td>
        <td style="font-size:12px">${c.assigned_entity || '—'}</td>
        <td>${dupPill(c.duplicate_status)}</td>
        <td>${c.requires_review ? '<span style="color:var(--red);font-weight:700">⚠ Yes</span>' : '<span style="color:var(--green)">✓</span>'}</td>
        <td style="font-family:monospace;font-size:12px">${c.user_id ? c.user_id.slice(0,8)+'…' : '—'}</td>
      </tr>`).join('');

    document.getElementById('allTable').innerHTML = `
      <table>
        <thead>
          <tr>
            <th>ID</th><th>Submitted</th><th>Text</th><th>Type</th>
            <th>Severity</th><th>Entity</th><th>Dup Status</th><th>Review?</th><th>User</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    document.getElementById('allTable').innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>Failed to load.</p></div>`;
    console.error(e);
  }
}

// ── Review Queue ──────────────────────────────────────
async function loadReview() {
  document.getElementById('reviewTable').innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>Loading…</div>`;
  try {
    const res = await fetch(`${GATEWAY}/admin/review-queue`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return logout();
    const items = await res.json();
    document.getElementById('reviewMeta').textContent = `${items.length} open`;

    if (!items || items.length === 0) {
      document.getElementById('reviewTable').innerHTML = `<div class="empty-state"><div class="empty-icon">✅</div><p>No items pending review.</p></div>`;
      return;
    }

    const rows = items.map(item => `
      <tr id="review-row-${item.id}">
        <td>${item.id}</td>
        <td>${fmtDate(item.created_at)}</td>
        <td>${shortId(item.complaint_id)}</td>
        <td><span class="badge-pill pill-review">${item.validation_status || '—'}</span></td>
        <td style="max-width:280px;font-size:13px;color:var(--gray-600)">${item.review_reason || '—'}</td>
        <td><span class="text-preview" title="${(item.text_preview||'').replace(/"/g,'&quot;')}">${item.text_preview || '—'}</span></td>
        <td>
          <button class="btn-resolve" onclick="resolveItem(${item.id}, this)">Resolve</button>
        </td>
      </tr>`).join('');

    document.getElementById('reviewTable').innerHTML = `
      <table>
        <thead>
          <tr>
            <th>#</th><th>Created</th><th>Complaint ID</th><th>Status</th>
            <th>Reason</th><th>Text Preview</th><th>Action</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    document.getElementById('reviewTable').innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>Failed to load.</p></div>`;
    console.error(e);
  }
}

async function resolveItem(itemId, btn) {
  const notes = prompt('Resolution notes (optional):') || '';
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const res = await fetch(`${GATEWAY}/admin/review/${itemId}/resolve`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ notes }),
    });
    if (!res.ok) throw new Error(await res.text());
    const row = document.getElementById(`review-row-${itemId}`);
    if (row) row.style.opacity = '0.4';
    await loadStats();
  } catch (e) {
    alert('Failed to resolve: ' + e.message);
    btn.disabled = false;
    btn.textContent = 'Resolve';
  }
}

// ── Duplicates ────────────────────────────────────────
async function loadDup() {
  document.getElementById('dupTable').innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>Loading…</div>`;
  try {
    const res = await fetch(`${GATEWAY}/admin/duplicates?page=${state.dup.page}&limit=20`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return logout();
    const d = await res.json();
    state.dup.total = d.total || 0;
    document.getElementById('dupMeta').textContent = `${d.total} total`;
    updatePagination('dup', d.total, 20);

    if (!d.complaints || d.complaints.length === 0) {
      document.getElementById('dupTable').innerHTML = `<div class="empty-state"><div class="empty-icon">🔁</div><p>No duplicates detected yet.</p></div>`;
      return;
    }

    const rows = d.complaints.map(c => `
      <tr>
        <td>${shortId(c.id)}</td>
        <td>${fmtDate(c.created_at)}</td>
        <td><span class="text-preview" title="${(c.text_preview||'').replace(/"/g,'&quot;')}">${c.text_preview || '—'}</span></td>
        <td>${c.complaint_type || '—'}</td>
        <td>${dupPill(c.duplicate_status)}</td>
        <td>${c.duplicate_of ? shortId(c.duplicate_of) : '—'}</td>
        <td style="font-family:monospace;font-size:12px">${c.cluster_id ? c.cluster_id.slice(0,8)+'…' : '—'}</td>
        <td style="font-size:12px">${c.assigned_entity || '—'}</td>
        <td>${severityPill(c.severity)}</td>
      </tr>`).join('');

    document.getElementById('dupTable').innerHTML = `
      <table>
        <thead>
          <tr>
            <th>ID</th><th>Submitted</th><th>Text</th><th>Type</th>
            <th>Status</th><th>Duplicate Of</th><th>Cluster</th><th>Entity</th><th>Severity</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    document.getElementById('dupTable').innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>Failed to load.</p></div>`;
    console.error(e);
  }
}

// ── Init ──────────────────────────────────────────────
loadStats();
loadAll();
