/* =====================================================
   CedarFix AI — app.js
   Handles form submission, image preview, GPS, results
   ===================================================== */

const GATEWAY_URL = window.GATEWAY_URL || 'http://localhost:8000';

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
const detectBtn     = document.getElementById('detectLocation');
const coordsRow     = document.getElementById('coordsRow');
const coordsDisplay = document.getElementById('coordsDisplay');
const latInput      = document.getElementById('latitude');
const lngInput      = document.getElementById('longitude');
const submitBtn     = document.getElementById('submitBtn');
const btnText       = submitBtn.querySelector('.btn-text');
const btnSpinner    = document.getElementById('btnSpinner');

const resultPanel   = document.getElementById('resultPanel');
const resultSuccess = document.getElementById('resultSuccess');
const resultError   = document.getElementById('resultError');
const resultContradiction  = document.getElementById('resultContradiction');
const resultClarification  = document.getElementById('resultClarification');
const resultHumanReview    = document.getElementById('resultHumanReview');
const resultInvalid        = document.getElementById('resultInvalid');
const formPanel     = document.querySelector('.form-panel');

// All result cards — used to hide all before showing one
const ALL_RESULT_CARDS = [
  resultSuccess, resultError, resultContradiction,
  resultClarification, resultHumanReview, resultInvalid,
];

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

    const district = districtInput.value.trim();
    if (district)            fd.append('district', district);
    if (latInput.value)      fd.append('latitude',  latInput.value);
    if (lngInput.value)      fd.append('longitude', lngInput.value);
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

    // Route to the correct result panel based on pipeline status
    switch (data.status) {
      case 'needs_clarification':
        showClarification(data);
        break;
      case 'contradiction':
        showContradiction(data);
        break;
      case 'invalid_no_complaint':
        showInvalid();
        break;
      case 'review_required':
        // Could be human_review gate OR low-confidence routing — check media_validation
        if (data.media_validation?.status === 'human_review') {
          showHumanReview(data);
        } else {
          showSuccess(data);
        }
        break;
      default:
        showSuccess(data);
    }

  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});

// ── Render success result ─────────────────────────────
function showSuccess(d) {
  // Complaint ID
  document.getElementById('resultId').textContent = `ID: ${d.complaint_id}`;

  // Basic fields
  document.getElementById('resType').textContent =
    (d.complaint_type || 'Unknown').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

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
