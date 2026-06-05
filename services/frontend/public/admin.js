/* =====================================================
   CedarFix AI — admin.js
   Admin dashboard: stats, all complaints, review queue, duplicates
   ===================================================== */

const GATEWAY = window.GATEWAY_URL || '/api';
const reviewItemsById = new Map();
let activeReviewItem = null;

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
// ── Shared helper ──────────────────────────────
function displayType(type, subcategory) {
  const t = (type || '').toLowerCase();
  const s = (subcategory || '').toLowerCase().trim();
  const isSpecific = s && s !== 'other' && s !== 'unknown';
  const label = (t === 'other' && isSpecific) ? s : t;
  return label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '—';
}
// ── Tab switching ─────────────────────────────────────
function switchTab(tab) {
  document.getElementById('tabAll').classList.toggle('active',    tab === 'all');
  document.getElementById('tabReview').classList.toggle('active', tab === 'review');
  document.getElementById('tabResolved').classList.toggle('active', tab === 'resolved');
  document.getElementById('tabDup').classList.toggle('active',    tab === 'dup');
  document.getElementById('sectionAll').classList.toggle('active',    tab === 'all');
  document.getElementById('sectionReview').classList.toggle('active', tab === 'review');
  document.getElementById('sectionResolved').classList.toggle('active', tab === 'resolved');
  document.getElementById('sectionDup').classList.toggle('active',    tab === 'dup');

  if (tab === 'all')    loadAll();
  if (tab === 'review') loadReview();
  if (tab === 'resolved') loadResolvedReviews();
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

function showToast(message, type = 'success') {
  const stack = document.getElementById('toastStack');
  if (!stack) return;

  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.textContent = message;
  stack.appendChild(el);

  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 220);
  }, 3200);
}

function setReviewEditorError(message = '') {
  const el = document.getElementById('reviewEditorError');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('show', !!message);
}

function prettyJson(value) {
  if (value == null || value === '') return '';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}

function parseJsonArea(id) {
  const raw = (document.getElementById(id)?.value || '').trim();
  if (!raw) return null;
  return JSON.parse(raw);
}

function pruneEmbeddings(value) {
  if (Array.isArray(value)) {
    return value.map(pruneEmbeddings);
  }
  if (value && typeof value === 'object') {
    const out = {};
    Object.entries(value).forEach(([k, v]) => {
      // Hide heavy vectors and embedding-related fields from the editor.
      if (/embedding/i.test(k)) return;
      out[k] = pruneEmbeddings(v);
    });
    return out;
  }
  return value;
}

function setReviewImage(imageFilename) {
  const img = document.getElementById('reviewImagePreview');
  const ph = document.getElementById('reviewImagePlaceholder');
  if (!img || !ph) return;

  if (!imageFilename) {
    img.style.display = 'none';
    img.removeAttribute('src');
    ph.style.display = '';
    ph.textContent = 'No image available for this complaint.';
    return;
  }

  const src = /^https?:\/\//i.test(imageFilename)
    ? imageFilename
    : `${GATEWAY}/media?ref=${encodeURIComponent(imageFilename)}`;

  img.src = src;
  img.style.display = '';
  ph.style.display = 'none';

  img.onerror = () => {
    img.style.display = 'none';
    ph.style.display = '';
    ph.textContent = 'Image preview unavailable (file may be missing).';
  };
}

async function openReviewEditor(itemId) {
  const item = reviewItemsById.get(itemId);
  if (!item) {
    showToast('Could not open review item.', 'error');
    return;
  }

  activeReviewItem = item;
  setReviewEditorError('');

  document.getElementById('reviewModalTitle').textContent = `Review ${item.id} — ${item.complaint_id}`;
  document.getElementById('reviewContextText').textContent =
    `Status: ${item.validation_status || '—'} | Created: ${fmtDate(item.created_at)} | Reason: ${item.review_reason || '—'}`;
  document.getElementById('reviewComplaintText').textContent = item.text_preview || '—';

  document.getElementById('reviewDecision').value = '';
  document.getElementById('reviewMatch').value = '';
  document.getElementById('reviewNotes').value = '';
  document.getElementById('reviewTextJson').value = '';
  document.getElementById('reviewImageJson').value = '';
  document.getElementById('reviewRoutingJson').value = '';
  setReviewImage(null);
  document.getElementById('reviewModalOverlay').classList.add('open');

  try {
    const [retrainingResp, complaintResp] = await Promise.all([
      fetch(`${GATEWAY}/admin/retraining/${encodeURIComponent(item.complaint_id)}`, { headers: authHeaders() }),
      fetch(`${GATEWAY}/complaints/${encodeURIComponent(item.complaint_id)}`, { headers: authHeaders() }),
    ]);

    let retraining = null;
    if (retrainingResp.ok) retraining = await retrainingResp.json();

    let complaint = null;
    if (complaintResp.ok) complaint = await complaintResp.json();

    if (complaint?.original_text) {
      document.getElementById('reviewComplaintText').textContent = complaint.original_text;
    }
    setReviewImage(complaint?.image_filename || retraining?.image_filename || null);

    // Best effort prefill for explicit admin match confirmation.
    const autoMatch = complaint?.media_validation?.status === 'valid'
      ? 'true'
      : complaint?.media_validation?.status === 'contradiction'
        ? 'false'
        : '';
    document.getElementById('reviewMatch').value = autoMatch;

    if (retraining) {
      document.getElementById('reviewDecision').value = retraining.admin_decision || '';
      document.getElementById('reviewNotes').value = retraining.admin_notes || '';
      document.getElementById('reviewTextJson').value = prettyJson(
        pruneEmbeddings(
          retraining.corrected_text_json ||
          retraining.text_classification_json ||
          complaint?.text_analysis ||
          null
        )
      );
      document.getElementById('reviewImageJson').value = prettyJson(
        pruneEmbeddings(
          retraining.corrected_image_json ||
          retraining.image_classification_json ||
          complaint?.image_analysis ||
          null
        )
      );
      document.getElementById('reviewRoutingJson').value = prettyJson(
        pruneEmbeddings(
          retraining.corrected_rag_response ||
          retraining.rag_routing_response ||
          complaint?.routing ||
          null
        )
      );
    } else if (complaint) {
      document.getElementById('reviewTextJson').value = prettyJson(pruneEmbeddings(complaint.text_analysis || null));
      document.getElementById('reviewImageJson').value = prettyJson(pruneEmbeddings(complaint.image_analysis || null));
      document.getElementById('reviewRoutingJson').value = prettyJson(pruneEmbeddings(complaint.routing || null));
    }
  } catch (e) {
    console.warn('Review detail load failed', e);
    showToast('Could not pre-load review details. You can still submit manually.', 'error');
  }
}

function closeReviewEditor() {
  document.getElementById('reviewModalOverlay').classList.remove('open');
  activeReviewItem = null;
  setReviewEditorError('');
}

async function submitReviewEditor() {
  if (!activeReviewItem) return;

  const submitBtn = document.getElementById('btnSubmitReviewEditor');
  const decision = (document.getElementById('reviewDecision').value || '').trim();
  const matchRaw = (document.getElementById('reviewMatch').value || '').trim();
  const notes = document.getElementById('reviewNotes').value || '';

  const allowedDecisions = new Set(['can_be_processed', 'cannot_be_processed', 'fake', 'unsupported']);
  if (decision && !allowedDecisions.has(decision)) {
    setReviewEditorError('Invalid decision value.');
    return;
  }

  let corrected_text_json = null;
  let corrected_image_json = null;
  let corrected_rag_response = null;

  try {
    corrected_text_json = parseJsonArea('reviewTextJson');
    corrected_image_json = parseJsonArea('reviewImageJson');
    corrected_rag_response = parseJsonArea('reviewRoutingJson');
  } catch (e) {
    setReviewEditorError(`Invalid JSON: ${e.message}`);
    return;
  }

  const payload = { notes };
  if (decision) payload.admin_decision = decision;
  if (matchRaw === 'true') payload.image_text_match = true;
  if (matchRaw === 'false') payload.image_text_match = false;

  // Always submit editable JSON snapshots to the new admin_review_edits table.
  payload.text_llm_json = corrected_text_json;
  payload.image_llm_json = corrected_image_json;
  payload.routing_json = corrected_rag_response;

  // Keep compatibility with retraining feedback flow when decision allows processing.
  if (decision === 'can_be_processed') {
    if (corrected_text_json) payload.corrected_text_json = corrected_text_json;
    if (corrected_image_json) payload.corrected_image_json = corrected_image_json;
    if (corrected_rag_response) payload.corrected_rag_response = corrected_rag_response;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Saving...';
  setReviewEditorError('');

  try {
    const res = await fetch(`${GATEWAY}/admin/review/${activeReviewItem.id}/resolve`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());

    await loadReview();
    await loadStats();
    closeReviewEditor();
    showToast(
      decision
        ? `Review resolved and feedback saved (${decision}).`
        : 'Review item resolved successfully.'
    );
  } catch (e) {
    setReviewEditorError(`Failed to resolve: ${e.message}`);
    showToast('Failed to resolve review item.', 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Save & Resolve';
  }
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
        <td>${displayType(c.complaint_type, c.subcategory)}</td>
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

    reviewItemsById.clear();
    items.forEach(item => reviewItemsById.set(item.id, item));

    const rows = items.map(item => `
      <tr id="review-row-${item.id}">
        <td>${item.id}</td>
        <td>${fmtDate(item.created_at)}</td>
        <td>${shortId(item.complaint_id)}</td>
        <td><span class="badge-pill pill-review">${item.validation_status || '—'}</span></td>
        <td style="max-width:280px;font-size:13px;color:var(--gray-600)">${item.review_reason || '—'}</td>
        <td><span class="text-preview" title="${(item.text_preview||'').replace(/"/g,'&quot;')}">${item.text_preview || '—'}</span></td>
        <td>
          <button class="btn-resolve" onclick="openReviewEditor(${item.id})">Open Review</button>
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

// ── Resolved Human Reviews ───────────────────────────
async function loadResolvedReviews() {
  document.getElementById('resolvedTable').innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>Loading…</div>`;
  try {
    const res = await fetch(`${GATEWAY}/admin/review-resolved?limit=250`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return logout();
    const items = await res.json();
    document.getElementById('resolvedMeta').textContent = `${items.length} resolved`;

    if (!items || items.length === 0) {
      document.getElementById('resolvedTable').innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><p>No resolved review items yet.</p></div>`;
      return;
    }

    const rows = items.map(item => `
      <tr>
        <td>${item.id}</td>
        <td>${fmtDate(item.created_at)}</td>
        <td>${fmtDate(item.resolved_at)}</td>
        <td>${shortId(item.complaint_id)}</td>
        <td><span class="badge-pill pill-review">${item.validation_status || '—'}</span></td>
        <td style="max-width:220px;font-size:13px;color:var(--gray-600)">${item.review_reason || '—'}</td>
        <td><span class="text-preview" title="${(item.text_preview||'').replace(/"/g,'&quot;')}">${item.text_preview || '—'}</span></td>
        <td style="font-family:monospace;font-size:12px">${item.resolved_by || '—'}</td>
        <td>${item.admin_decision || '—'}</td>
        <td>${item.image_text_match === true ? 'match' : item.image_text_match === false ? 'mismatch' : '—'}</td>
        <td style="max-width:220px;font-size:13px;color:var(--gray-600)">${item.resolution_notes || '—'}</td>
      </tr>`).join('');

    document.getElementById('resolvedTable').innerHTML = `
      <table>
        <thead>
          <tr>
            <th>#</th><th>Created</th><th>Resolved</th><th>Complaint ID</th><th>Status</th>
            <th>Reason</th><th>Text Preview</th><th>Resolved By</th><th>Decision</th><th>Match</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    document.getElementById('resolvedTable').innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>Failed to load.</p></div>`;
    console.error(e);
  }
}

document.getElementById('btnCloseReviewModal')?.addEventListener('click', closeReviewEditor);
document.getElementById('btnCancelReviewModal')?.addEventListener('click', closeReviewEditor);
document.getElementById('btnSubmitReviewEditor')?.addEventListener('click', submitReviewEditor);
document.getElementById('reviewModalOverlay')?.addEventListener('click', (e) => {
  if (e.target.id === 'reviewModalOverlay') closeReviewEditor();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('reviewModalOverlay')?.classList.contains('open')) {
    closeReviewEditor();
  }
});

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
        <td>${displayType(c.complaint_type, c.subcategory)}</td>
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
