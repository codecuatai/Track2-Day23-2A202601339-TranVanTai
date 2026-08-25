/**
 * Disaster Recovery Dashboard - Interactive Client Controller
 */

// State management
const state = {
  activeRegion: 'a',
  regionA: { alive: false, ready: false, vectors: 0, poolState: 'cold', weights: false, latency: null },
  regionB: { alive: false, ready: false, vectors: 0, poolState: 'cold', weights: false, latency: null },
  ttl: 5,
  cacheAge: 0,
  pollInterval: null,
  isPolling: true
};

// UI Elements
const el = {
  edgeStatusPill: document.getElementById('edge-status-pill'),
  activeRegionBadge: document.getElementById('active-region-badge'),
  edgeLatencyVal: document.getElementById('edge-latency-val'),
  cacheAgeVal: document.getElementById('cache-age-val'),
  
  // Region A
  cardRegionA: document.getElementById('card-region-a'),
  badgeRegionA: document.getElementById('badge-region-a'),
  statusAAlive: document.getElementById('status-a-alive'),
  statusAReady: document.getElementById('status-a-ready'),
  statusAPool: document.getElementById('status-a-pool'),
  statusAVectors: document.getElementById('status-a-vectors'),
  statusAWeights: document.getElementById('status-a-weights'),
  
  // Region B
  cardRegionB: document.getElementById('card-region-b'),
  badgeRegionB: document.getElementById('badge-region-b'),
  statusBAlive: document.getElementById('status-b-alive'),
  statusBReady: document.getElementById('status-b-ready'),
  statusBPool: document.getElementById('status-b-pool'),
  statusBVectors: document.getElementById('status-b-vectors'),
  statusBWeights: document.getElementById('status-b-weights'),
  
  // Logs & Forms
  logConsole: document.getElementById('log-console'),
  inferInput: document.getElementById('infer-input'),
  inferForm: document.getElementById('infer-form'),
  toastContainer: document.getElementById('toast-container')
};

// Helpers
function showToast(message, type = 'info') {
  if (!el.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === 'danger' ? '❌' : type === 'success' ? '✅' : 'ℹ️'}</span> <div>${message}</div>`;
  el.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function appendLog(tag, message, type = 'info') {
  if (!el.logConsole) return;
  const now = new Date().toLocaleTimeString();
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `<span class="log-ts">[${now}]</span><span class="log-tag ${tag.toLowerCase()}">[${tag.toUpperCase()}]</span> ${escapeHtml(message)}`;
  el.logConsole.insertBefore(entry, el.logConsole.firstChild);
  
  // Limit logs to last 100 entries
  while (el.logConsole.children.length > 100) {
    el.logConsole.removeChild(el.logConsole.lastChild);
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Fetch dashboard state
async function fetchDashboardState() {
  try {
    const res = await fetch('/api/dashboard/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    
    // Update local state
    state.activeRegion = data.edge.active_region;
    state.ttl = data.edge.ttl_seconds;
    state.cacheAge = data.edge.cache_age_s;
    
    state.regionA = data.regions.a;
    state.regionB = data.regions.b;
    
    renderUI();
  } catch (err) {
    console.warn('Dashboard poll error:', err);
    if (el.edgeStatusPill) {
      el.edgeStatusPill.className = 'status-pill offline';
      el.edgeStatusPill.innerHTML = '<span class="status-dot"></span> Edge Proxy Offline';
    }
  }
}

// Render UI based on state
function renderUI() {
  // Edge Header
  if (el.activeRegionBadge) {
    el.activeRegionBadge.textContent = `Region ${state.activeRegion.toUpperCase()}`;
  }
  if (el.cacheAgeVal) {
    el.cacheAgeVal.textContent = `${state.cacheAge}s / ${state.ttl}s`;
  }
  
  const activeRegData = state.activeRegion === 'a' ? state.regionA : state.regionB;
  if (el.edgeStatusPill) {
    if (activeRegData && activeRegData.ready) {
      el.edgeStatusPill.className = 'status-pill online';
      el.edgeStatusPill.innerHTML = '<span class="status-dot"></span> System Healthy';
    } else if (activeRegData && activeRegData.alive) {
      el.edgeStatusPill.className = 'status-pill degraded';
      el.edgeStatusPill.innerHTML = '<span class="status-dot"></span> Degraded (Warming/No State)';
    } else {
      el.edgeStatusPill.className = 'status-pill offline';
      el.edgeStatusPill.innerHTML = '<span class="status-dot"></span> Outage Detected';
    }
  }

  // Region A Render
  renderRegionCard('a', state.regionA, state.activeRegion === 'a');
  
  // Region B Render
  renderRegionCard('b', state.regionB, state.activeRegion === 'b');
}

function renderRegionCard(regionKey, regData, isActive) {
  const isA = regionKey === 'a';
  const card = isA ? el.cardRegionA : el.cardRegionB;
  const badge = isA ? el.badgeRegionA : el.badgeRegionB;
  const statusAlive = isA ? el.statusAAlive : el.statusBAlive;
  const statusReady = isA ? el.statusAReady : el.statusBReady;
  const statusPool = isA ? el.statusAPool : el.statusBPool;
  const statusVectors = isA ? el.statusAVectors : el.statusBVectors;
  const statusWeights = isA ? el.statusAWeights : el.statusBWeights;

  if (!card) return;

  if (isActive) {
    card.classList.add('is-active');
    if (badge) {
      badge.className = 'badge-active';
      badge.textContent = 'ACTIVE (ROUTING)';
    }
  } else {
    card.classList.remove('is-active');
    if (badge) {
      badge.className = 'badge-standby';
      badge.textContent = 'STANDBY';
    }
  }

  if (statusAlive) {
    statusAlive.innerHTML = regData.alive 
      ? '<span style="color: var(--color-green)">● Alive (200)</span>' 
      : '<span style="color: var(--color-red)">✕ Down / Unreachable</span>';
  }

  if (statusReady) {
    statusReady.innerHTML = regData.ready 
      ? '<span style="color: var(--color-green)">● Ready (200)</span>' 
      : `<span style="color: var(--color-amber)">✕ Not Ready (${(regData.reasons || []).join(', ') || '503'})</span>`;
  }

  if (statusPool) {
    const pColor = regData.poolState === 'full' ? 'var(--color-green)' : regData.poolState === 'warm' ? 'var(--color-amber)' : 'var(--text-muted)';
    statusPool.innerHTML = `<span style="color: ${pColor}">${regData.poolState.toUpperCase()}</span>`;
  }

  if (statusVectors) {
    statusVectors.textContent = `${regData.vectors || 0} docs`;
  }

  if (statusWeights) {
    statusWeights.innerHTML = regData.weights 
      ? '<span style="color: var(--color-green)">✓ Present</span>' 
      : '<span style="color: var(--color-red)">✕ Missing</span>';
  }
}

// Inference Testing
async function sendInferQuery(query) {
  const t0 = performance.now();
  appendLog('infer', `Sending request: "${query}"...`, 'infer');
  try {
    const res = await fetch(`/v1/infer?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    const duration = Math.round(performance.now() - t0);
    
    if (el.edgeLatencyVal) {
      el.edgeLatencyVal.textContent = `${duration} ms`;
    }

    if (res.ok && !data.error) {
      appendLog('infer', `[200 OK] Region ${data.edge_region?.toUpperCase() || data.region?.toUpperCase()}: "${data.answer}" (${duration}ms)`, 'infer');
      showToast(`Inference returned from [${data.edge_region || data.region}] in ${duration}ms`, 'success');
    } else {
      appendLog('infer', `[${res.status} ERR] Error: ${data.error || 'Failed'} | Reasons: ${(data.reasons || []).join(', ')}`, 'chaos');
      showToast(`Inference failed: ${data.error || 'Region Unavailable'}`, 'danger');
    }
  } catch (err) {
    appendLog('infer', `[503 Network Error] ${err.message}`, 'chaos');
    showToast(`Network Error: ${err.message}`, 'danger');
  }
}

// Failover Action
async function triggerFailover(targetRegion) {
  appendLog('failover', `Triggering cutover to Region ${targetRegion.toUpperCase()}...`, 'failover');
  try {
    const res = await fetch('/api/dashboard/failover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region: targetRegion })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Cutover pointer updated to Region ${targetRegion.toUpperCase()} (DNS TTL: ${state.ttl}s)`, 'success');
      appendLog('failover', `Cutover success: Active region set to "${targetRegion}". Waiting for DNS cache TTL (${state.ttl}s)...`, 'failover');
      fetchDashboardState();
    } else {
      throw new Error(data.detail || 'Failover command failed');
    }
  } catch (err) {
    showToast(`Failover failed: ${err.message}`, 'danger');
    appendLog('failover', `Failover Error: ${err.message}`, 'chaos');
  }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
  // Initial poll
  fetchDashboardState();
  state.pollInterval = setInterval(fetchDashboardState, 2000);
  
  appendLog('system', 'Disaster Recovery Monitoring Dashboard initialized.', 'info');

  // Form submit
  if (el.inferForm) {
    el.inferForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const q = el.inferInput.value.trim() || 'hoa don thang 7';
      sendInferQuery(q);
    });
  }

  // Failover buttons
  const btnFailoverA = document.getElementById('btn-failover-a');
  const btnFailoverB = document.getElementById('btn-failover-b');
  if (btnFailoverA) btnFailoverA.addEventListener('click', () => triggerFailover('a'));
  if (btnFailoverB) btnFailoverB.addEventListener('click', () => triggerFailover('b'));

  // Quick Infer Buttons
  const btnQuickInfer = document.getElementById('btn-quick-infer');
  if (btnQuickInfer) {
    btnQuickInfer.addEventListener('click', () => {
      sendInferQuery('bao cao doanh thu quy 2');
    });
  }

  // Clear logs button
  const btnClearLogs = document.getElementById('btn-clear-logs');
  if (btnClearLogs) {
    btnClearLogs.addEventListener('click', () => {
      if (el.logConsole) el.logConsole.innerHTML = '';
    });
  }
});
