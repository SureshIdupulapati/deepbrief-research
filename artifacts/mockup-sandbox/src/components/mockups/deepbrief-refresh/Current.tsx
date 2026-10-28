import './_group.css';
import './Current.css';

function Icon({ name, size = 14 }: { name: string; size?: number }) {
  const shapes: Record<string, React.ReactNode> = {
    branch: <><path d="M6 3v12M6 7h7a3 3 0 0 0 3-3V3M6 11h7a3 3 0 0 1 3 3v1" /><circle cx="6" cy="3" r="2" /><circle cx="16" cy="3" r="2" /><circle cx="16" cy="15" r="2" /></>,
    play: <path d="m7 4 12 8-12 8z" fill="currentColor" stroke="none" />,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z" /><path d="M4 5.5v13A2.5 2.5 0 0 1 6.5 16H20" /></>,
    radio: <><circle cx="12" cy="12" r="2" /><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19a10 10 0 0 1 0-14" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    sliders: <path d="M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M2 14h4m4-6h4m4 8h4" />,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8m-8 4h8" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}

const stages = [
  'Input Normalizer & Intent Expansion',
  'Multi-Source Harvester',
  'DOM Sanitizer & Content Distiller',
  'Cross-Source Fact Corroborator',
  'Intelligence Synthesizer',
  'Artifact Builder & Cryptographic Signer',
];

export function Current() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" aria-label="DeepBrief workspace">
          <div className="brand-mark"><Icon name="branch" size={16} /></div>
          <div className="brand-name">deepbrief<span> / workspace</span></div>
        </div>
        <div className="top-right">
          <span><i className="health-dot" />Systems operational</span>
          <span className="top-label">SIMULATED SOURCE ARCHIVE</span>
        </div>
      </header>
      <main className="workspace">
        <div className="page-heading">
          <div>
            <div className="eyebrow">Research operations · 01</div>
            <h1>Technical research, made auditable.</h1>
            <p className="heading-copy">Trace every source, checkpoint and recovery decision from question to verified brief.</p>
          </div>
        </div>
        <div className="content-grid">
          <section className="left-stack" aria-label="Research pipeline">
            <div className="panel new-run">
              <div className="new-run-head">
                <div>
                  <h2 className="section-title">Start a research run</h2>
                  <p className="section-note">Define the technical decision. DeepBrief will build a sourced, verifiable dossier.</p>
                </div>
                <div className="run-id">INPUT · RUN/CREATE</div>
              </div>
              <form>
                <div className="input-wrap">
                  <input className="topic-input" placeholder="e.g. Compare Raft and Paxos for geo-distributed metadata..." aria-label="Research question" readOnly />
                  <button className="submit-btn" type="button"><Icon name="play" size={13} />Run research</button>
                  <span className="char-count">0/280</span>
                </div>
                <div className="fault-row">
                  <span className="fault-label">Resilience test</span>
                  <button className="fault-toggle" type="button" aria-pressed="false"><span className="toggle-track" />Rate limit</button>
                  <button className="fault-toggle" type="button" aria-pressed="false"><span className="toggle-track" />Provider outage</button>
                  <button className="fault-toggle" type="button" aria-pressed="false"><span className="toggle-track" />Crash at stage 4</button>
                </div>
                <p className="demo-note">Demo mode: source records are fixtures, not live research results.</p>
              </form>
            </div>

            <div className="panel">
              <div className="graph-wrap">
                <div className="graph-topline">
                  <h2 className="graph-title">Pipeline execution graph</h2>
                  <div className="graph-status"><span className="live-dot" />Ready for input</div>
                </div>
                <div className="dag" aria-label="Six-stage research pipeline">
                  <svg className="dag-conduit" viewBox="0 0 1200 32" preserveAspectRatio="none" aria-hidden="true">
                    <path className="conduit-base" d="M 95 16 H 1105" />
                    <path className="conduit-active" d="M 95 16 H 1105" />
                  </svg>
                  {stages.map((stage, index) => (
                    <button className={`stage-node pending ${index === 0 ? 'selected' : ''}`} type="button" key={stage} aria-label={`Stage ${index + 1}: ${stage}, pending`}>
                      <span className="stage-number">{String(index + 1).padStart(2, '0')}</span>
                      <span className="stage-name">{stage}</span>
                      <span className="stage-latency">—</span>
                    </button>
                  ))}
                </div>
                <div className="graph-foot">
                  <div className="legend">
                    <span className="legend-item"><i className="legend-swatch done" />Verified</span>
                    <span className="legend-item"><i className="legend-swatch active" />In progress</span>
                    <span className="legend-item"><i className="legend-swatch retry" />Recovery path</span>
                  </div>
                  <span>Six stages · click to inspect</span>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><Icon name="sliders" size={14} />Stage inspector</div>
                <span className="panel-meta">CHECKPOINT 01</span>
              </div>
              <div className="panel-body">
                <div className="inspect-grid">
                  <div><div className="inspect-label">Stage</div><div className="inspect-value">Input Normalizer &amp; Intent Expansion</div></div>
                  <div><div className="inspect-label">State · elapsed</div><div className="inspect-value">pending · —</div></div>
                  <div><div className="inspect-label">Attempts</div><div className="inspect-value">0</div></div>
                </div>
                <div className="inspector-tabs" role="tablist" aria-label="Stage checkpoint details">
                  <button role="tab" aria-selected="true" className="active" type="button">Output checkpoint</button>
                  <button role="tab" aria-selected="false" type="button">Input context</button>
                  <button role="tab" aria-selected="false" type="button">Resilience policy</button>
                </div>
                <div className="inspector-content" role="tabpanel"><pre>No checkpoint data reported yet.</pre></div>
              </div>
            </div>
          </section>

          <aside className="right-stack">
            <div className="panel">
              <div className="panel-head"><div className="panel-title"><Icon name="book" size={14} />Verified dossier</div></div>
              <div className="dossier">
                <div className="dossier-empty">
                  <Icon name="file" size={20} />
                  <strong>Your verified brief will appear here</strong>
                  Completed research is rendered with its checkpoint trail and verification fingerprint.
                </div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><Icon name="radio" size={14} />Run stream</div>
                <span className="panel-meta">AWAITING RUN</span>
              </div>
              <div className="empty-inspector" style={{ minHeight: 112 }}>
                <div>Start or select a run to follow its live state transitions.</div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><Icon name="clock" size={14} />Saved runs</div>
                <span className="panel-meta">0 RUNS</span>
              </div>
              <div className="history-empty">No research runs yet.<br />Your saved pipeline history will collect here.</div>
            </div>
          </aside>
        </div>
        <p className="footer-note">DeepBrief · auditable research infrastructure · exact stage timing from source checkpoints</p>
      </main>
    </div>
  );
}
