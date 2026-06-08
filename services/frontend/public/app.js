/* =====================================================
   CedarFix AI — app.js
   Handles form submission, image preview, GPS, results
   ===================================================== */

const GATEWAY_URL = window.GATEWAY_URL || '/api';

// ── DOM refs ──────────────────────────────────────────
const form          = document.getElementById('complaintForm');
const textArea      = document.getElementById('text');
const charCount     = document.getElementById('charCount');
const textError     = document.getElementById('textError');
const uploadZone    = document.getElementById('uploadZone');
const imageInput    = document.getElementById('image');
const uploadPlaceholder = document.getElementById('uploadPlaceholder');
const imagePreview  = document.getElementById('imagePreview');
const removeImageBtn= document.getElementById('removeImage');
const districtInput = document.getElementById('district');
const addressHintInput = document.getElementById('addressHint');
const locationModeInputs = Array.from(document.querySelectorAll('input[name="locationMode"]'));
const currentLocationRow = document.getElementById('currentLocationRow');
const manualLocationRow = document.getElementById('manualLocationRow');
const locationError = document.getElementById('locationError');
const detectBtn     = document.getElementById('detectLocation');
const coordsRow     = document.getElementById('coordsRow');
const coordsDisplay = document.getElementById('coordsDisplay');
const latInput      = document.getElementById('latitude');
const lngInput      = document.getElementById('longitude');
const submitBtn     = document.getElementById('submitBtn');
const btnText       = submitBtn.querySelector('.btn-text');
const btnSpinner    = document.getElementById('btnSpinner');

const resultPanel   = document.getElementById('resultPanel');
const resultMulti   = document.getElementById('resultMulti');
const resultSuccess = document.getElementById('resultSuccess');
const resultError   = document.getElementById('resultError');
const resultContradiction  = document.getElementById('resultContradiction');
const resultClarification  = document.getElementById('resultClarification');
const resultHumanReview    = document.getElementById('resultHumanReview');
const resultInvalid        = document.getElementById('resultInvalid');
const formPanel     = document.querySelector('.form-panel');

// All result cards — used to hide all before showing one
const ALL_RESULT_CARDS = [
  resultMulti, resultSuccess, resultError, resultContradiction,
  resultClarification, resultHumanReview, resultInvalid,
];

function selectedLocationMode() {
  return document.querySelector('input[name="locationMode"]:checked')?.value || 'current_device';
}

function syncLocationMode() {
  const mode = selectedLocationMode();
  const isCurrent = mode === 'current_device';
  currentLocationRow.classList.toggle('hidden', !isCurrent);
  coordsRow.classList.toggle('hidden', !isCurrent || !latInput.value || !lngInput.value);
  manualLocationRow.classList.toggle('hidden', isCurrent);
  locationError.textContent = '';
  if (isCurrent) {
    addressHintInput.value = '';
  } else {
    latInput.value = '';
    lngInput.value = '';
    coordsDisplay.textContent = '';
    coordsRow.classList.add('hidden');
  }
}

locationModeInputs.forEach(input => input.addEventListener('change', syncLocationMode));
syncLocationMode();

// ── Character counter ─────────────────────────────────
textArea.addEventListener('input', () => {
  const n = textArea.value.length;
  charCount.textContent = n;
  charCount.style.color = n > 1800 ? '#C1121F' : '';
});

// ── Image upload ──────────────────────────────────────
uploadZone.addEventListener('click', (e) => {
  if (e.target === removeImageBtn) return;
  imageInput.click();
});

uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) showPreview(file);
});

imageInput.addEventListener('change', () => {
  const file = imageInput.files[0];
  if (file) showPreview(file);
});

removeImageBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  clearImage();
});

function showPreview(file) {
  const reader = new FileReader();
  reader.onload = (ev) => {
    imagePreview.src = ev.target.result;
    imagePreview.classList.remove('hidden');
    uploadPlaceholder.classList.add('hidden');
    removeImageBtn.classList.remove('hidden');
  };
  reader.readAsDataURL(file);
}

function clearImage() {
  imageInput.value = '';
  imagePreview.src = '';
  imagePreview.classList.add('hidden');
  uploadPlaceholder.classList.remove('hidden');
  removeImageBtn.classList.add('hidden');
}

// ── GPS Location ──────────────────────────────────────
detectBtn.addEventListener('click', () => {
  if (!navigator.geolocation) {
    alert('Geolocation is not supported by your browser.');
    return;
  }
  detectBtn.textContent = '⏳ Detecting...';
  detectBtn.disabled = true;

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords;
      latInput.value  = latitude.toFixed(6);
      lngInput.value  = longitude.toFixed(6);
      coordsDisplay.textContent = `📍 ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
      coordsRow.classList.remove('hidden');
      locationError.textContent = '';
      detectBtn.innerHTML = '<span>✅</span> Located';
      detectBtn.disabled = false;
    },
    () => {
      detectBtn.innerHTML = '<span>📍</span> Use my location';
      detectBtn.disabled = false;
      alert('Could not detect location. Please enter the district manually.');
    }
  );
});

// ── Form submission ───────────────────────────────────
form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Validate
  const text = textArea.value.trim();
  if (text.length < 10) {
    textError.textContent = 'Please describe the issue (at least 10 characters).';
    textArea.classList.add('invalid');
    textArea.focus();
    return;
  }
  textError.textContent = '';
  textArea.classList.remove('invalid');

  setLoading(true);

  try {
    const fd = new FormData();
    fd.append('text', text);

    const locationMode = selectedLocationMode();
    fd.append('location_input_mode', locationMode);
    locationError.textContent = '';

    const district = districtInput.value.trim();
    if (locationMode === 'current_device') {
      if (!latInput.value || !lngInput.value) {
        locationError.textContent = 'Use your device location or choose Somewhere else and type the complaint location.';
        setLoading(false);
        return;
      }
      fd.append('latitude',  latInput.value);
      fd.append('longitude', lngInput.value);
    } else {
      if (!district) {
        locationError.textContent = 'Enter where the complaint is located.';
        districtInput.focus();
        setLoading(false);
        return;
      }
      addressHintInput.value = district;
      fd.append('district', district);
      fd.append('address_hint', district);
    }
    if (imageInput.files[0]) fd.append('image', imageInput.files[0]);

    // Attach auth token if logged in so gateway binds complaint to user
    const headers = {};
    const cfToken = localStorage.getItem('cf_token');
    if (cfToken) headers['Authorization'] = `Bearer ${cfToken}`;

    const resp = await fetch(`${GATEWAY_URL}/complaints`, {
      method: 'POST',
      headers,
      body: fd,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }

    const data = await resp.json();
    const normalized = normalizeSubmissionResponse(data);
    if (normalized.isMulti) {
      showMultiResult(normalized.response);
      return;
    }
    const decision = normalized.primary;

    // Route to the correct result panel based on pipeline status
    switch (decision.status) {
      case 'needs_clarification':
        showClarification(decision);
        break;
      case 'contradiction':
        showContradiction(decision);
        break;
      case 'invalid_no_complaint':
        showInvalid();
        break;
      case 'review_required':
        // Could be human_review gate OR low-confidence routing — check media_validation
        if (decision.media_validation?.status === 'human_review') {
          showHumanReview(decision);
        } else {
          showSuccess(decision);
        }
        break;
      default:
        showSuccess(decision);
    }

  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});

// ── Render success result ─────────────────────────────
function normalizeSubmissionResponse(data) {
  if (Array.isArray(data?.complaints)) {
    return {
      response: data,
      isMulti: data.is_multi === true && data.complaints.length > 1,
      primary: data.primary_decision || data.complaints[0],
    };
  }
  return { response: data, isMulti: false, primary: data };
}

function showMultiResult(response) {
  document.getElementById('multiSubmissionId').textContent = `Submission: ${response.submission_id}`;
  const split = response.split_result || {};
  document.getElementById('multiSplitDetail').textContent =
    `${response.complaint_count || response.complaints.length} separate complaints were created from your submission. Split source: ${split.source || 'unknown'}.`;

  const list = document.getElementById('multiComplaintList');
  list.innerHTML = '';
  (response.complaints || []).forEach((d, idx) => {
    const item = document.createElement('div');
    item.className = 'multi-item';
    const conf = d.routing_confidence != null ? `${Math.round(d.routing_confidence * 100)}%` : '-';
    const text = d.original_text || '';
    const secondary = d.routing?.secondary_entity;
    item.innerHTML = `
      <div class="multi-item-head">
        <strong>Complaint ${idx + 1}</strong>
        <span>${d.status || 'processing'}</span>
      </div>
      <div class="multi-item-grid">
        <span>ID</span><b>${d.complaint_id || '-'}</b>
        <span>Type</span><b>${displayType(d.complaint_type || 'unknown', d.text_analysis?.subcategory || '')}</b>
        <span>Routed To</span><b>${d.assigned_entity || '-'}</b>
        ${secondary ? `<span>Also Notify</span><b>${escapeHtml(secondary)}</b>` : ''}
        <span>Confidence</span><b>${conf}</b>
      </div>
      <p>${escapeHtml(text)}</p>
    `;
    list.appendChild(item);
  });
  _showCard(resultMulti);
}

function showSuccess(d) {
  // Complaint ID
  document.getElementById('resultId').textContent = `ID: ${d.complaint_id}`;

  // Basic fields — Type: show subcategory as the primary label when type is "other"
  const rawType = d.text_analysis?.issue_type || d.complaint_type || 'Unknown';
  const sub = d.text_analysis?.subcategory || '';
  const isOther = rawType === 'other';
  const specificSub = sub && !['other', 'unknown', ''].includes(sub.toLowerCase());

  document.getElementById('resType').textContent = displayType(rawType, sub);

  // Category Detail row — show category when type is "other" with a specific subcategory
  const subRow = document.getElementById('subcategoryRow');
  const cat = d.text_analysis?.category || '';
  const specificCat = cat && !['other', 'unknown', ''].includes(cat.toLowerCase());
  if (isOther && specificSub && specificCat && cat !== sub) {
    document.getElementById('resSubcategory').textContent =
      cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    subRow.classList.remove('hidden');
  } else {
    subRow.classList.add('hidden');
  }

  const lang = d.text_analysis?.detected_language;
  const langMap = { ar: '🇦🇷 Arabic', fr: '🇫🇷 French', en: '🇬🇧 English', unknown: '—' };
  document.getElementById('resLang').textContent = langMap[lang] || lang || '—';

  // Severity with color
  const sev = d.severity || '—';
  const sevEl = document.getElementById('resSeverity');
  sevEl.textContent = sev;
  sevEl.className = `result-value sev-${sev}`;

  // Priority score
  const ps = d.priority_score;
  document.getElementById('resPriority').textContent =
    ps != null ? `${Math.round(ps * 100)} / 100` : '—';

  // Routing entity
  document.getElementById('resEntity').textContent =
    d.assigned_entity || '—';

  const secondaryEntity = d.routing?.secondary_entity;
  document.getElementById('resSecondaryEntity').textContent = secondaryEntity || '-';
  toggleEl('secondaryEntityRow', !!secondaryEntity);

  // Confidence bar
  const conf = d.routing_confidence || 0;
  const confPct = Math.round(conf * 100);
  document.getElementById('resConfidenceBar').style.width = `${confPct}%`;
  document.getElementById('resConfidenceBar').style.background =
    conf >= 0.85 ? '#2D6A4F' : conf >= 0.65 ? '#F4A261' : '#C1121F';
  document.getElementById('resConfidencePct').textContent = `${confPct}%`;

  // Duplicate warning
  toggleEl('duplicateWarning', d.is_duplicate);

  // Review flag
  toggleEl('reviewFlag', d.routing?.requires_review === true);

  // Explanation
  const expText = d.explanation?.explanation_text;
  if (expText) {
    document.getElementById('resExplanation').textContent = expText;
    document.getElementById('explanationBlock').style.display = '';
  } else {
    document.getElementById('explanationBlock').style.display = 'none';
  }

  // Image + Alignment analysis details
  const vu = d.image_analysis?.visual_understanding;
  const align = d.text_image_alignment;
  const hasImageData = vu || align;

  if (hasImageData) {
    document.getElementById('analysisBlock').classList.remove('hidden');

    if (vu?.visual_subcategory) {
      document.getElementById('resImageDetection').textContent =
        vu.visual_subcategory.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      document.getElementById('imageAnalysisRow').classList.remove('hidden');
    }
    if (vu?.confidence != null) {
      document.getElementById('resImageConfidence').textContent =
        `${Math.round(vu.confidence * 100)}%`;
      document.getElementById('imageConfidenceRow').classList.remove('hidden');
    }
    if (align?.alignment_status) {
      const statusEl = document.getElementById('resAlignmentStatus');
      const statusMap = {
        CONFIRMS: '✅ Confirms',
        CONTRADICTS: '⚠️ Contradicts',
        PARTIAL: '🔶 Partial',
        UNRELATED: '❓ Unrelated',
        NO_IMAGE: '—',
      };
      statusEl.textContent = statusMap[align.alignment_status] || align.alignment_status;
      statusEl.className = `analysis-value alignment-badge align-${align.alignment_status.toLowerCase()}`;
      document.getElementById('alignmentRow').classList.remove('hidden');
    }
    if (align?.conflict_reason) {
      document.getElementById('resAlignmentReason').textContent = align.conflict_reason;
      document.getElementById('alignmentReasonRow').classList.remove('hidden');
    }
  } else {
    document.getElementById('analysisBlock').classList.add('hidden');
  }

  // Show result, hide error
  _showCard(resultSuccess);
}

// ── Render error ──────────────────────────────────────
function showError(message) {
  document.getElementById('errorMessage').textContent = message || 'Submission failed. Is the server running?';
  _showCard(resultError);
}

// ── Contradiction: text and image disagree ────────────
function showContradiction(d) {
  const reason = d.media_validation?.contradiction_reason ||
    'Your text and image describe different issues. Please resubmit with matching evidence.';
  document.getElementById('contradictionDetail').textContent = reason;
  _showCard(resultContradiction);
}

// ── Clarification: image has complaint but text doesn't ─
function showClarification(d) {
  const question = d.media_validation?.clarification_question || '';
  document.getElementById('clarificationDetail').textContent = question;
  document.getElementById('clarificationId').textContent = d.complaint_id;
  _showCard(resultClarification);
}

// ── Human review: both text and image ambiguous ───────
function showHumanReview(d) {
  const reason = d.media_validation?.clarification_question ||
    'Your submission was unclear and has been queued for human review.';
  document.getElementById('humanReviewDetail').textContent = reason;
  document.getElementById('humanReviewId').textContent = d.complaint_id;
  _showCard(resultHumanReview);
}

// ── Invalid: no complaint detected, no image ──────────
function showInvalid() {
  _showCard(resultInvalid);
}

// ── Show a single result card, hide all others ────────
function _showCard(card) {
  ALL_RESULT_CARDS.forEach(c => c.classList.add('hidden'));
  card.classList.remove('hidden');
  resultPanel.style.display = '';
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Reset form ────────────────────────────────────────
document.getElementById('btnReset').addEventListener('click', resetForm);
document.getElementById('btnMultiReset').addEventListener('click', resetForm);
document.getElementById('btnErrorReset').addEventListener('click', resetForm);
document.getElementById('btnContradictionReset').addEventListener('click', resetForm);
document.getElementById('btnClarificationReset').addEventListener('click', resetForm);
document.getElementById('btnHumanReviewReset').addEventListener('click', resetForm);
document.getElementById('btnInvalidReset').addEventListener('click', resetForm);

function resetForm() {
  form.reset();
  charCount.textContent = '0';
  clearImage();
  coordsRow.classList.add('hidden');
  latInput.value = '';
  lngInput.value = '';
  addressHintInput.value = '';
  locationError.textContent = '';
  locationModeInputs.forEach(input => { input.checked = input.value === 'current_device'; });
  syncLocationMode();
  detectBtn.innerHTML = '<span>📍</span> Use my location';
  detectBtn.disabled = false;
  resultPanel.style.display = 'none';
  formPanel.scrollIntoView({ behavior: 'smooth' });
}

// ── Loading state ─────────────────────────────────────
function setLoading(on) {
  submitBtn.disabled = on;
  btnText.classList.toggle('hidden', on);
  btnSpinner.classList.toggle('hidden', !on);
}

// ── Helpers ───────────────────────────────────────────
function toggleEl(id, show) {
  document.getElementById(id).classList.toggle('hidden', !show);
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }[ch]));
}

/**
 * Returns a human-readable type label.
 * When issue_type is "other" and a specific subcategory exists, shows that instead.
 *   displayType('other', 'broken_bench')  → 'Broken Bench'
 *   displayType('pothole', '')            → 'Pothole'
 *   displayType('other', 'other')         → 'Other'
 */
function displayType(type, subcategory) {
  const t = (type || '').toLowerCase();
  const s = (subcategory || '').toLowerCase().trim();
  const isSpecific = s && s !== 'other' && s !== 'unknown';
  const label = (t === 'other' && isSpecific) ? s : t;
  return label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '—';
}


// ── Ticker: load recent complaints ───────────────────
async function loadTicker() {
  try {
    // We'll simulate a ticker with recent complaint types
    // In production: fetch from a /complaints?limit=10 endpoint
    const items = [
      '🔴 CRITICAL: Flooding — Tripoli (routed to Ministry of Environment)',
      '🟠 HIGH: Road Damage — Jounieh (Ministry of Public Works)',
      '🟡 MEDIUM: Pothole — Hamra (Ministry of Public Works)',
      '🟡 MEDIUM: Streetlight out — Ashrafieh (EDL)',
      '🟢 LOW: Garbage — Cola (Beirut Municipality)',
      '🔴 CRITICAL: Electricity Outage — Sidon (EDL)',
      '🟠 HIGH: Traffic light broken — Baabda (Internal Security Forces)',
    ];
    document.getElementById('tickerTrack').textContent = items.join('   ·   ');
  } catch {
    document.getElementById('tickerBar').style.display = 'none';
  }
}

loadTicker();
