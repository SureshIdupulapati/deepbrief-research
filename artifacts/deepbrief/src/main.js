import './index.css';
import './deepbrief-theme.css';

const root = document.querySelector('#root');
const stageNames = [
  'Input Normalizer & Intent Expansion',
  'Multi-Source Harvester',
  'Evidence Normalizer',
  'Claim Linkage & Caveat Review',
  'Evidence-Led Summary',
  'Artifact Builder & Cryptographic Signer',
];
const eventNames = [
  'run_created', 'run_started', 'stage_transition', 'resume',
  'crash_checkpoint', 'process_recovery', 'run_completed', 'run_failed',
];
const state = {
  health: 'checking',
  runs: [],
  selectedId: null,
  detail: null,
  selectedStage: 1,
  inspectorTab: 'output',
  stream: [],
  streamState: 'idle',
  topic: '',
  sourceMode: 'live',
  selectedSources: ['crossref', 'arxiv'],
  injectRateLimit: false,
  injectOutage: false,
  crashAtStage4: false,
  busy: false,
  error: '',
  copyStatus: '',
  lastEventId: 0,
};
let eventSource;
let streamCounter = 0;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function icon(name, size = 14) {
  const paths = {
    branch: '<path d="M6 3v12M6 7h7a3 3 0 0 0 3-3V3M6 11h7a3 3 0 0 1 3 3v1"/><circle cx="6" cy="3" r="2"/><circle cx="16" cy="3" r="2"/><circle cx="16" cy="15" r="2"/>',
    play: '<path d="m7 4 12 8-12 8z" fill="currentColor" stroke="none"/>',
    book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z"/><path d="M4 5.5v13A2.5 2.5 0 0 1 6.5 16H20"/>',
    radio: '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19a10 10 0 0 1 0-14"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    sliders: '<path d="M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M2 14h4m4-6h4m4 8h4"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8m-8 4h8"/>',
    retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5m-5 5V3"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    alert: '<path d="m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? ''}</svg>`;
}

function statusLabel(status = 'pending') {
  if (status === 'fallback') return 'fallback used';
  return status.replaceAll('_', ' ');
}

function formatDuration(ms) {
  if (ms == null) return '—';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
}

function formatDate(dateString) {
  if (!dateString) return '—';
  const date = new Date(dateString);
  return Number.isNaN(date.getTime()) ? escapeHtml(dateString) : date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? payload.error ?? `Request failed (${response.status})`);
  }
  return payload;
}

function fallbackStages() {
  return stageNames.map((name, index) => ({
    stage: index + 1, name, status: 'pending', attempts: 0,
    resiliencePolicy: 'Awaiting run',
  }));
}

function safeDossier() {
  return state.detail?.dossier && typeof state.detail.dossier === 'object'
    ? state.detail.dossier : null;
}

function renderStageNode(stage) {
  const status = stage.status ?? 'pending';
  const selected = stage.stage === state.selectedStage ? 'selected' : '';
  const retry = status === 'retrying'
    ? (stage.message?.match(/Retry \d+\/\d+ in [^)]+/)?.[0] ?? `Retry ${stage.attempts}/3`)
    : formatDuration(stage.durationMs);
  const badge = status === 'failed'
    ? icon('alert', 12)
    : ['completed', 'fallback'].includes(status) ? icon('check', 12) : String(stage.stage).padStart(2, '0');
  return `<button class="stage-node ${escapeHtml(status)} ${selected}" type="button" data-stage="${stage.stage}" aria-label="Stage ${stage.stage}: ${escapeHtml(stage.name)}, ${escapeHtml(statusLabel(status))}">
    <span class="stage-number">${badge}</span>
    <span class="stage-name">${escapeHtml(stage.name)}</span>
    <span class="stage-latency">${escapeHtml(retry)}</span>
    ${status === 'fallback' ? '<span class="stage-state-tag">FALLBACK USED</span>' : ''}
  </button>`;
}

function renderInspector(stage) {
  if (!stage) return '<div class="empty-inspector"><div>Select a graph node to inspect its execution context.</div></div>';
  const tab = state.inspectorTab;
  const content = tab === 'output' ? stage.output
    : tab === 'input' ? stage.inputContext
      : null;
  const panel = tab === 'policy'
    ? `<div><div class="inspect-policy">${escapeHtml(stage.resiliencePolicy || 'No policy reported')}</div>${stage.message ? `<p class="policy-message">${escapeHtml(stage.message)}</p>` : ''}</div>`
    : `<pre>${escapeHtml(content == null ? 'No checkpoint data reported yet.' : JSON.stringify(content, null, 2))}</pre>`;
  return `<div class="panel-body">
    <div class="inspect-grid">
      <div><div class="inspect-label">Stage</div><div class="inspect-value">${escapeHtml(stage.name)}</div></div>
      <div><div class="inspect-label">State · elapsed</div><div class="inspect-value">${escapeHtml(statusLabel(stage.status))} · ${escapeHtml(formatDuration(stage.durationMs))}</div></div>
      <div><div class="inspect-label">Attempts</div><div class="inspect-value">${Number(stage.attempts) || 0}</div></div>
    </div>
    <div class="inspector-tabs" role="tablist" aria-label="Stage checkpoint details">
      ${[['output', 'Output checkpoint'], ['input', 'Input context'], ['policy', 'Resilience policy']].map(([key, label]) => `<button role="tab" aria-selected="${tab === key}" class="${tab === key ? 'active' : ''}" data-inspector-tab="${key}" type="button">${label}</button>`).join('')}
    </div>
    <div class="inspector-content" role="tabpanel">${panel}</div>
  </div>`;
}

function renderDossier(dossier) {
  if (!dossier) {
    const detail = state.detail;
    return `<div class="dossier-empty">${icon('file', 20)}<strong>${detail ? 'Research brief is being assembled' : 'Your research brief will appear here'}</strong>${detail ? 'Evidence synthesis and dossier integrity hash are still being prepared.' : 'Completed research is saved with its source trail, checkpoint history, and integrity hash.'}</div>`;
  }
  const findings = Array.isArray(dossier.findings) ? dossier.findings : [];
  const actions = Array.isArray(dossier.actionPlan) ? dossier.actionPlan : [];
  const sources = Array.isArray(dossier.sources) ? dossier.sources : [];
  return `<div class="dossier-top">
      <div><h2 class="section-title">Decision brief</h2><p class="section-note">${escapeHtml(state.detail.topic)}</p></div>
      <span class="verified">${icon('check', 12)}${state.detail.status === 'completed' ? 'RUN COMPLETE' : escapeHtml(statusLabel(state.detail.status).toUpperCase())}</span>
    </div>
    <div class="dossier-tools">
      <button type="button" data-action="copy">${icon('copy', 12)}Copy team card</button>
      <button type="button" data-action="download" ${dossier.markdown ? '' : 'disabled'}>${icon('download', 12)}Download Markdown</button>
      ${state.copyStatus ? `<span role="status">${escapeHtml(state.copyStatus)}</span>` : ''}
    </div>
    <section class="summary-callout"><div class="inspect-label">Executive summary</div><p>${escapeHtml(dossier.executiveSummary ?? 'The executive summary is not available for this run.')}</p></section>
    ${findings.length ? `<section class="findings-section"><div class="inspect-label">Architectural findings</div><div class="findings-grid">${findings.map((item) => `<article class="finding-card">
      <span class="finding-confidence">${escapeHtml(item.evidenceLabel ?? item.confidence ?? 'Source record')}</span><h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.detail)}</p><strong>${escapeHtml(item.metric)}</strong>
    </article>`).join('')}</div></section>` : ''}
    ${actions.length ? `<section class="actions-section"><div class="inspect-label">Immediate action plan</div><div class="action-table-wrap"><table class="action-table">
      <thead><tr><th>Horizon</th><th>Priority</th><th>Action</th></tr></thead><tbody>${actions.map((item) => `<tr>
        <td>${escapeHtml(item.period)}</td><td><span class="priority-badge ${escapeHtml(String(item.priority).toLowerCase())}">${escapeHtml(item.priority)}</span></td>
        <td>${escapeHtml(item.action)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
    ${dossier.providerStatuses?.length ? `<section class="sources-section"><div class="inspect-label">Selected provider status</div>${dossier.providerStatuses.map((provider) => `<div class="provider-status ${escapeHtml(provider.status)}">
      <strong>${escapeHtml(provider.label)}</strong><span>${escapeHtml(provider.message)}</span></div>`).join('')}</section>` : ''}
    ${sources.length ? `<section class="sources-section"><div class="inspect-label">Evidence trail · ${escapeHtml(dossier.sourceMode === 'fixtures' ? 'DEMO FIXTURES' : 'LIVE SOURCES')}</div>${sources.map((source) => `<article class="source-row">
      <div class="source-main"><strong>${escapeHtml(source.source)} · ${escapeHtml(source.type)}</strong>
        ${source.url?.startsWith('https://') && !source.url.includes('example.invalid')
    ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>`
    : `<span class="source-title">${escapeHtml(source.title)}</span>`}
        <small>Retrieved ${escapeHtml(formatDate(source.retrievedAt))} · Claim ${escapeHtml(source.claimId)}</small>
        <p class="source-claim">${escapeHtml(source.claim)}</p></div>
      </article>`).join('')}</section>` : ''}
    ${dossier.evidenceDisclosure ? `<p class="evidence-disclosure">${escapeHtml(dossier.evidenceDisclosure)}</p>` : ''}
    ${state.detail.verificationHash ? `<div class="hash"><div class="inspect-label">Dossier integrity hash</div>${escapeHtml(state.detail.verificationHash)}</div>` : ''}`;
}

function render() {
  const stages = state.detail?.stages?.length
    ? [...state.detail.stages].sort((a, b) => a.stage - b.stage)
    : fallbackStages();
  const currentStage = stages.find((stage) => stage.stage === state.selectedStage) ?? stages[0];
  const dossier = safeDossier();
  const active = stages.some((stage) => ['running', 'retrying'].includes(stage.status));
  root.innerHTML = `<div class="app-shell">
    <header class="topbar">
      <div class="brand" aria-label="DeepBrief workspace"><div class="brand-mark">${icon('branch', 16)}</div><div class="brand-name">deepbrief<span> / workspace</span></div></div>
      <div class="top-right"><span data-testid="health-status"><i class="health-dot ${state.health === 'ok' ? '' : 'off'}"></i>${state.health === 'ok' ? 'Systems operational' : state.health === 'checking' ? 'Checking service' : 'Service unavailable'}</span><span class="top-label">${state.detail ? (state.detail.sourceMode === 'fixtures' ? 'DEMO FIXTURE RUN' : 'LIVE RESEARCH RUN') : (state.sourceMode === 'fixtures' ? 'DEMO FIXTURES' : 'LIVE RESEARCH')}</span></div>
    </header>
    <main class="workspace">
      <div class="page-heading"><div><div class="eyebrow">Research operations · 01</div><h1>Technical research, made auditable.</h1><p class="heading-copy">Trace every source, checkpoint and recovery decision from question to research brief.</p></div>
      ${state.detail ? `<div class="run-id">RUN / ${escapeHtml(state.detail.id)}</div>` : ''}</div>
      <div class="content-grid">
        <section class="left-stack" aria-label="Research pipeline">
          <div class="panel new-run"><div class="new-run-head"><div><h2 class="section-title">Start a research run</h2><p class="section-note">Define the technical decision. DeepBrief will build a sourced, verifiable dossier.</p></div><div class="run-id">INPUT · RUN/CREATE</div></div>
            ${state.error ? `<div class="error-banner" role="alert">${escapeHtml(state.error)}<button class="link-btn" data-action="dismiss" type="button">Dismiss</button></div>` : ''}
            <form id="run-form"><div class="input-wrap"><input class="topic-input" name="topic" value="${escapeHtml(state.topic)}" maxlength="280" placeholder="e.g. Compare Raft and Paxos for geo-distributed metadata..." aria-label="Research question" data-testid="input-research-topic">
              <button class="submit-btn" type="submit" ${state.busy ? 'disabled' : ''} data-testid="button-start-run">${icon('play', 13)}${state.busy ? 'Starting' : 'Run research'}</button><span class="char-count">${state.topic.length}/280</span></div>
              <div class="source-picker" aria-label="Research source selection">
                <div class="source-picker-heading"><span>Evidence mode</span><small>Live mode never falls back to sample records</small></div>
                <div class="source-mode-options">
                  <button type="button" class="source-choice ${state.sourceMode === 'live' ? 'active' : ''}" data-source-mode="live" aria-pressed="${state.sourceMode === 'live'}">Live sources</button>
                  <button type="button" class="source-choice ${state.sourceMode === 'fixtures' ? 'active' : ''}" data-source-mode="fixtures" aria-pressed="${state.sourceMode === 'fixtures'}">Demo fixtures</button>
                </div>
                ${state.sourceMode === 'live' ? `<div class="live-source-options"><label><input type="checkbox" data-source="crossref" ${state.selectedSources.includes('crossref') ? 'checked' : ''}>Crossref <small>Research publications</small></label><label><input type="checkbox" data-source="arxiv" ${state.selectedSources.includes('arxiv') ? 'checked' : ''}>arXiv <small>Research preprints</small></label></div>` : '<p class="demo-note">Fixture records are illustrative and are not live research results.</p>'}
              </div>
              <div class="fault-row"><span class="fault-label">Resilience test</span>
                ${toggleHtml('rate', state.injectRateLimit, 'Rate limit')}
                ${toggleHtml('outage', state.injectOutage, 'Provider outage')}
                ${toggleHtml('crash', state.crashAtStage4, 'Crash at stage 4')}
                ${(state.injectRateLimit || state.injectOutage || state.crashAtStage4) ? '<span class="fault-warning">Fault injection enabled</span>' : ''}
              </div>
            </form>
          </div>
          <div class="panel"><div class="graph-wrap"><div class="graph-topline"><h2 class="graph-title">Pipeline execution graph</h2><div class="graph-status"><span class="live-dot"></span>${escapeHtml(state.detail ? statusLabel(state.detail.status) : 'Ready for input')}</div></div>
            <div class="dag ${active ? 'is-active' : ''}" aria-label="Six-stage research pipeline">
              <svg class="dag-conduit" viewBox="0 0 1200 32" preserveAspectRatio="none" aria-hidden="true"><path class="conduit-base" d="M 95 16 H 1105"/><path class="conduit-active" d="M 95 16 H 1105"/></svg>
              ${stages.map(renderStageNode).join('')}
            </div><div class="graph-foot"><div class="legend"><span class="legend-item"><i class="legend-swatch done"></i>Complete</span><span class="legend-item"><i class="legend-swatch active"></i>In progress</span><span class="legend-item"><i class="legend-swatch retry"></i>Recovery path</span></div><span>${state.detail ? `${state.detail.completedStages} / 6 checkpoints` : 'Six stages · click to inspect'}</span></div>
          </div></div>
          <div class="panel"><div class="panel-head"><div class="panel-title">${icon('sliders', 14)}Stage inspector</div><span class="panel-meta">${currentStage ? `CHECKPOINT ${String(currentStage.stage).padStart(2, '0')}` : 'NO CHECKPOINT SELECTED'}</span></div>${renderInspector(currentStage)}</div>
        </section>
        <aside class="right-stack">
          <div class="panel"><div class="panel-head"><div class="panel-title">${icon('book', 14)}Research brief</div>${dossier ? '<span class="verified">SAVED</span>' : ''}</div>
            <div class="dossier">${state.detailLoading ? '<div class="history-loading"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>' : renderDossier(dossier)}
              ${state.detail?.status === 'paused' ? `<button class="resume-btn" style="margin-top:14px" data-action="resume" type="button" ${state.busy ? 'disabled' : ''}>${icon('retry', 12)}${state.busy ? 'Resuming…' : 'Resume from checkpoint'}</button>` : ''}
            </div>
          </div>
          <div class="panel"><div class="panel-head"><div class="panel-title">${icon('radio', 14)}Run stream</div><span class="panel-meta">${state.selectedId ? state.streamState.toUpperCase() : 'AWAITING RUN'}</span></div>
            ${state.stream.length ? `<div class="stream" aria-live="polite">${state.stream.map((line) => `<div class="stream-line"><span class="stream-time">${escapeHtml(line.at)}</span><i class="stream-marker"></i><span class="stream-msg"><strong>${escapeHtml(line.label)}</strong> · ${escapeHtml(line.detail)}</span></div>`).join('')}</div>` : `<div class="empty-inspector" style="min-height:112px"><div>${state.selectedId ? state.streamState === 'reconnecting' ? 'Stream reconnecting. Rehydrating latest checkpoint…' : 'Connected to run events. State transitions will appear here.' : 'Start or select a run to follow its live state transitions.'}</div></div>`}
          </div>
          <div class="panel"><div class="panel-head"><div class="panel-title">${icon('clock', 14)}Saved runs</div><span class="panel-meta">${state.runs.length} RUN${state.runs.length === 1 ? '' : 'S'}</span></div>
            ${state.runs.length ? `<div class="history-list">${state.runs.map((run) => `<button class="history-row ${state.selectedId === run.id ? 'active' : ''}" data-run-id="${escapeHtml(run.id)}" type="button">
              <span class="history-icon">${icon('file', 13)}</span><span class="history-main"><span class="history-topic">${escapeHtml(run.topic)}</span><span class="history-sub">${formatDate(run.createdAt)} · ${run.completedStages}/6</span></span>
              <span class="status-pill ${escapeHtml(run.status)}">${escapeHtml(statusLabel(run.status))}</span><span class="chevron">›</span></button>`).join('')}</div>` : '<div class="history-empty">No research runs yet.<br>Your saved pipeline history will collect here.</div>'}
          </div>
        </aside>
      </div>
      <p class="footer-note">DeepBrief · auditable research infrastructure · exact stage timing from source checkpoints</p>
    </main>
  </div>`;
  bindEvents();
}

function toggleHtml(key, checked, label) {
  return `<button type="button" class="fault-toggle ${checked ? 'active' : ''}" aria-pressed="${checked}" data-toggle="${key}"><span class="toggle-track" aria-hidden="true"></span><span>${label}</span></button>`;
}

function bindEvents() {
  const input = root.querySelector('[name="topic"]');
  input?.addEventListener('input', () => {
    state.topic = input.value;
    const count = root.querySelector('.char-count');
    if (count) count.textContent = `${state.topic.length}/280`;
  });
  root.querySelector('#run-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const topic = state.topic.trim();
    if (topic.length < 8) {
      state.error = 'Add a specific research question with at least 8 characters.';
      render();
      return;
    }
    if (state.sourceMode === 'live' && !state.selectedSources.length) {
      state.error = 'Choose at least one live research source.';
      render();
      return;
    }
    state.error = '';
    state.busy = true;
    render();
    try {
      const run = await request('/runs', {
        method: 'POST',
        body: JSON.stringify({
          topic,
          sourceMode: state.sourceMode,
          sources: state.selectedSources,
          injectRateLimit: state.injectRateLimit,
          injectOutage: state.injectOutage,
          crashAtStage4: state.crashAtStage4,
        }),
      });
      state.topic = '';
      await loadRuns();
      await selectRun(run.id);
    } catch (error) {
      state.error = error.message;
    } finally {
      state.busy = false;
      render();
    }
  });
  root.querySelectorAll('[data-toggle]').forEach((button) => button.addEventListener('click', () => {
    const key = { rate: 'injectRateLimit', outage: 'injectOutage', crash: 'crashAtStage4' }[button.dataset.toggle];
    state[key] = !state[key];
    render();
  }));
  root.querySelectorAll('[data-source-mode]').forEach((button) => button.addEventListener('click', () => {
    state.sourceMode = button.dataset.sourceMode;
    render();
  }));
  root.querySelectorAll('[data-source]').forEach((checkbox) => checkbox.addEventListener('change', () => {
    const source = checkbox.dataset.source;
    state.selectedSources = checkbox.checked
      ? [...new Set([...state.selectedSources, source])]
      : state.selectedSources.filter((selected) => selected !== source);
    render();
  }));
  root.querySelectorAll('[data-stage]').forEach((button) => button.addEventListener('click', () => {
    state.selectedStage = Number(button.dataset.stage);
    render();
  }));
  root.querySelectorAll('[data-inspector-tab]').forEach((button) => button.addEventListener('click', () => {
    state.inspectorTab = button.dataset.inspectorTab;
    render();
  }));
  root.querySelectorAll('[data-run-id]').forEach((button) => button.addEventListener('click', () => selectRun(button.dataset.runId)));
  root.querySelector('[data-action="dismiss"]')?.addEventListener('click', () => { state.error = ''; render(); });
  root.querySelector('[data-action="copy"]')?.addEventListener('click', copyTeamCard);
  root.querySelector('[data-action="download"]')?.addEventListener('click', downloadMarkdown);
  root.querySelector('[data-action="resume"]')?.addEventListener('click', resumeRun);
}

async function loadHealth() {
  try {
    const result = await request('/healthz');
    state.health = result.status === 'ok' ? 'ok' : 'error';
  } catch {
    state.health = 'error';
  }
}

async function loadRuns() {
  try {
    state.runs = await request('/runs');
  } catch (error) {
    state.error = `Run history could not be loaded: ${error.message}`;
  }
}

async function loadDetail(id, showLoading = true) {
  if (showLoading) state.detailLoading = true;
  try {
    state.detail = await request(`/runs/${encodeURIComponent(id)}`);
    const live = state.detail.stages?.find((stage) => ['running', 'retrying', 'fallback', 'failed'].includes(stage.status));
    if (!state.detail.stages?.some((stage) => stage.stage === state.selectedStage)) {
      state.selectedStage = live?.stage ?? state.detail.stages?.[0]?.stage ?? 1;
    }
  } catch (error) {
    state.error = error.message;
  } finally {
    state.detailLoading = false;
    render();
  }
}

async function selectRun(id) {
  state.selectedId = id;
  state.detail = null;
  state.stream = [];
  state.streamState = 'connecting';
  state.lastEventId = 0;
  state.selectedStage = 1;
  eventSource?.close();
  render();
  await loadDetail(id);
  connectEvents(id);
}

function connectEvents(id) {
  eventSource?.close();
  state.streamState = 'connecting';
  const source = new EventSource(`/api/runs/${encodeURIComponent(id)}/events/${state.lastEventId}`);
  eventSource = source;
  source.onopen = () => {
    if (state.selectedId !== id) return;
    state.streamState = 'live';
    render();
  };
  const onEvent = async (event, name) => {
    if (state.selectedId !== id) return;
    if (event.lastEventId) state.lastEventId = Number(event.lastEventId) || state.lastEventId;
    let payload = {};
    try { payload = JSON.parse(event.data); } catch { payload = { message: event.data }; }
    const detail = payload.message ?? payload.status ?? (payload.stage ? `Stage ${payload.stage}` : 'Pipeline state updated');
    state.stream.unshift({
      at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      label: name.replaceAll('_', ' '),
      detail: String(detail),
    });
    state.stream = state.stream.slice(0, 40);
    if (payload.stage) state.selectedStage = Number(payload.stage);
    if (['run_completed', 'run_failed', 'crash_checkpoint'].includes(name)) {
      source.close();
      state.streamState = 'idle';
    }
    render();
    await Promise.all([loadDetail(id, false), loadRuns()]);
    if (['run_completed', 'run_failed', 'crash_checkpoint'].includes(name)) render();
  };
  eventNames.forEach((name) => source.addEventListener(name, (event) => { void onEvent(event, name); }));
  source.onmessage = (event) => { void onEvent(event, 'message'); };
  source.onerror = () => {
    if (state.selectedId !== id) return;
    state.streamState = 'reconnecting';
    render();
    void Promise.all([loadDetail(id, false), loadRuns()]);
  };
}

async function resumeRun() {
  if (!state.detail?.id) return;
  const id = state.detail.id;
  state.busy = true;
  render();
  try {
    await request(`/runs/${encodeURIComponent(id)}/resume`, { method: 'POST' });
    await loadRuns();
    await loadDetail(id);
    connectEvents(id);
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function copyTeamCard() {
  const dossier = safeDossier();
  if (!dossier) return;
  const card = dossier.teamCard ?? {};
  const findings = card.findings ?? dossier.findings?.map((finding) => finding.title) ?? [];
  const text = [
    `DeepBrief — ${card.title ?? state.detail.topic}`,
    card.summary ?? dossier.executiveSummary ?? '',
    ...findings.map((finding) => `• ${finding}`),
    `SHA-256: ${card.hash ?? state.detail.verificationHash ?? ''}`,
  ].filter(Boolean).join('\n\n');
  try {
    await navigator.clipboard.writeText(text);
    state.copyStatus = 'Team card copied';
  } catch {
    state.copyStatus = 'Clipboard permission unavailable';
  }
  render();
  window.setTimeout(() => { state.copyStatus = ''; render(); }, 2600);
}

function downloadMarkdown() {
  const markdown = safeDossier()?.markdown;
  if (!markdown || !state.detail) return;
  const filename = state.detail.topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || 'deepbrief';
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${filename}-deepbrief.md`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function start() {
  await Promise.all([loadHealth(), loadRuns()]);
  render();
  if (state.runs.length && !state.selectedId) await selectRun(state.runs[0].id);
}

start();
