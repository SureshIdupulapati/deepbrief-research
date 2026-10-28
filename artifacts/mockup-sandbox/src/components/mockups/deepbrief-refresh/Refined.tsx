import './_group.css';
import './Refined.css';
import type { ReactNode } from 'react';

type IconName = 'branch' | 'play' | 'book' | 'radio' | 'clock' | 'sliders' | 'file' | 'external' | 'copy' | 'check' | 'arrow' | 'shield' | 'download';

function Icon({ name, size = 15 }: { name: IconName; size?: number }) {
  const shapes: Record<IconName, ReactNode> = {
    branch: <><path d="M6 3v12M6 7h7a3 3 0 0 0 3-3V3M6 11h7a3 3 0 0 1 3 3v1" /><circle cx="6" cy="3" r="2" /><circle cx="16" cy="3" r="2" /><circle cx="16" cy="15" r="2" /></>,
    play: <path d="m7 4 12 8-12 8z" fill="currentColor" stroke="none" />,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z" /><path d="M4 5.5v13A2.5 2.5 0 0 1 6.5 16H20" /></>,
    radio: <><circle cx="12" cy="12" r="2" /><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19a10 10 0 0 1 0-14" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    sliders: <path d="M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M2 14h4m4-6h4m4 8h4" />,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8m-8 4h8" /></>,
    external: <><path d="M14 3h7v7M10 14 21 3" /><path d="M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6" /></>,
    copy: <><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z" /><path d="m9 12 2 2 4-4" /></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5M12 15V3" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}

const stages = [
  { name: 'Input normalizer', time: '0.4s', detail: 'Intent expanded', state: 'done' },
  { name: 'Source harvester', time: '8.2s', detail: '12 sources indexed', state: 'done' },
  { name: 'Content distiller', time: '3.1s', detail: '11 docs retained', state: 'done' },
  { name: 'Fact corroborator', time: '6.7s', detail: '1 retry · recovered', state: 'retry' },
  { name: 'Intelligence synthesis', time: '4.6s', detail: '8 claims verified', state: 'done' },
  { name: 'Artifact signer', time: '0.8s', detail: 'Fingerprint sealed', state: 'done' },
];

const stream = [
  ['09:42:16.402', 'Run created', 'Question normalized into 4 research intents.'],
  ['09:42:17.118', 'Harvest complete', '12 sources found across 4 domains.'],
  ['09:42:26.031', 'Recovery checkpoint', '429 from docs.raft.github.io · backoff 2.0s'],
  ['09:42:28.410', 'Retry succeeded', 'Source resumed from checkpoint; 11 documents retained.'],
  ['09:42:43.912', 'Dossier sealed', 'SHA-256 fingerprint generated. Run completed.'],
];

export function Refined() {
  return (
    <div className="db-refined">
      <header className="db-topbar">
        <div className="db-brand">
          <div className="db-mark"><Icon name="branch" size={17} /></div>
          <div className="db-brand-name">deepbrief<span> / workspace</span></div>
        </div>
        <div className="db-top-right">
          <span className="db-system"><i /> Systems operational</span>
          <span className="db-archive">SIMULATED SOURCE ARCHIVE</span>
          <button className="db-user" aria-label="Research workspace profile">EW</button>
        </div>
      </header>

      <main className="db-workspace">
        <div className="db-heading">
          <div>
            <div className="db-eyebrow">RESEARCH OPERATIONS <span>·</span> 01</div>
            <h1>Technical research,<br className="db-mobile-break" /> made auditable.</h1>
            <p>Trace every source, checkpoint and recovery decision from question to verified brief.</p>
          </div>
          <div className="db-heading-side">
            <span className="db-run-chip"><i /> COMPLETED RUN</span>
            <span className="db-run-ref">RUN&nbsp; DB-2406-018</span>
          </div>
        </div>

        <div className="db-grid">
          <section className="db-left" aria-label="Research pipeline">
            <section className="db-panel db-create">
              <div className="db-create-head">
                <div>
                  <span className="db-kicker">01 / DEFINE THE DECISION</span>
                  <h2>Start a research run</h2>
                  <p>Set the technical question. DeepBrief builds a sourced, verifiable dossier.</p>
                </div>
                <span className="db-run-id">INPUT · RUN/CREATE</span>
              </div>
              <form onSubmit={(event) => event.preventDefault()}>
                <div className="db-input-wrap">
                  <input aria-label="Research question" readOnly value="Compare Raft and Paxos for geo-distributed metadata stores" />
                  <button type="button" className="db-submit"><Icon name="play" size={12} /> Run research</button>
                  <span className="db-char">61/280</span>
                </div>
                <div className="db-fault-row">
                  <span className="db-fault-label">RESILIENCE TEST</span>
                  <button type="button" className="db-toggle"><i /> Rate limit</button>
                  <button type="button" className="db-toggle"><i /> Provider outage</button>
                  <button type="button" className="db-toggle"><i /> Crash at stage 4</button>
                  <span className="db-demo">Fixture run · not live research</span>
                </div>
              </form>
            </section>

            <section className="db-panel">
              <div className="db-graph">
                <div className="db-section-bar">
                  <div><span className="db-kicker">02 / EXECUTION</span><h2>Pipeline execution graph</h2></div>
                  <span className="db-complete"><Icon name="check" size={12} /> ALL STAGES VERIFIED</span>
                </div>
                <div className="db-pipeline">
                  <div className="db-rail" aria-hidden="true"><span /></div>
                  {stages.map((stage, index) => (
                    <button type="button" key={stage.name} className={`db-stage ${stage.state} ${index === 3 ? 'selected' : ''}`} aria-label={`${stage.name}: ${stage.detail}`}>
                      <span className="db-stage-num">{stage.state === 'retry' ? '↻' : String(index + 1).padStart(2, '0')}</span>
                      <span className="db-stage-name">{stage.name}</span>
                      <span className="db-stage-detail">{stage.detail}</span>
                      <span className="db-stage-time">{stage.time}</span>
                    </button>
                  ))}
                </div>
                <div className="db-legend">
                  <div><i className="verified" /> Verified <i className="recovered" /> Recovered checkpoint <i className="failure" /> Failure-aware</div>
                  <span>6 stages <b>·</b> click to inspect</span>
                </div>
              </div>
            </section>

            <section className="db-panel db-inspector">
              <div className="db-panel-head">
                <div className="db-panel-title"><span className="db-iconbox"><Icon name="sliders" /></span><div><span className="db-kicker">CHECKPOINT 04</span><h2>Stage inspector</h2></div></div>
                <span className="db-status-chip recovered">RECOVERED</span>
              </div>
              <div className="db-inspect-body">
                <div className="db-inspect-grid">
                  <div><label>Stage</label><strong>Cross-Source Fact Corroborator</strong></div>
                  <div><label>State · elapsed</label><strong><span className="db-state-dot" /> Completed · 6.7s</strong></div>
                  <div><label>Attempts</label><strong>02 <small>· retry recovered</small></strong></div>
                </div>
                <div className="db-inspector-tabs" role="tablist" aria-label="Stage checkpoint details">
                  <button type="button" role="tab" aria-selected="true">Output checkpoint</button>
                  <button type="button" role="tab" aria-selected="false">Input context</button>
                  <button type="button" role="tab" aria-selected="false">Resilience policy</button>
                </div>
                <div className="db-checkpoint" role="tabpanel">
                  <div className="db-checkpoint-head"><span>RECOVERY RECORD</span><span>CP-04-B · IMMUTABLE</span></div>
                  <p><b>429 Too Many Requests</b> from docs.raft.github.io. Exponential backoff applied; resumed from last durable cursor.</p>
                  <div className="db-checkpoint-foot"><span><i /> source cursor preserved</span><span>retry 02 · 2.0s backoff</span></div>
                </div>
              </div>
            </section>
          </section>

          <aside className="db-right">
            <section className="db-panel db-dossier-panel">
              <div className="db-panel-head">
                <div className="db-panel-title"><span className="db-iconbox teal"><Icon name="book" /></span><div><span className="db-kicker">03 / DECISION BRIEF</span><h2>Verified dossier</h2></div></div>
                <span className="db-status-chip verified-chip"><Icon name="shield" size={12} /> VERIFIED</span>
              </div>
              <div className="db-dossier">
                <div className="db-dossier-title">
                  <div><span className="db-doc-label">TECHNICAL COMPARISON · 8 CLAIMS</span><h3>Raft vs. Paxos for geo-distributed metadata</h3></div>
                  <span className="db-confidence">0.91<br /><small>CONFIDENCE</small></span>
                </div>
                <div className="db-dossier-tools">
                  <button type="button"><Icon name="copy" size={12} /> Copy citation</button>
                  <button type="button"><Icon name="download" size={12} /> Export brief</button>
                  <span><Icon name="check" size={12} /> Checkpoint linked</span>
                </div>
                <div className="db-summary">
                  <span>DECISION SUMMARY</span>
                  <p>For a new geo-distributed metadata store, <strong>Raft is the stronger default</strong> when operator clarity and predictable membership changes matter. Paxos remains viable where an existing implementation or Multi-Paxos throughput advantage is decisive.</p>
                </div>
                <div className="db-findings">
                  <div className="db-subhead"><h4>Verified findings</h4><span>3 OF 8 SHOWN</span></div>
                  <article className="db-finding">
                    <span className="db-finding-index">F01 <i>HIGH CONFIDENCE</i></span>
                    <h5>Understandability is an operational advantage</h5>
                    <p>Raft’s decomposed leader, log and membership model reduces implementation ambiguity.</p>
                    <span className="db-cite">[S01] [S03] <b>· 3 corroborating sources</b></span>
                  </article>
                  <article className="db-finding">
                    <span className="db-finding-index">F02 <i>HIGH CONFIDENCE</i></span>
                    <h5>Neither protocol removes WAN latency</h5>
                    <p>Quorum writes still depend on a majority acknowledgement; topology dominates tail latency.</p>
                    <span className="db-cite">[S02] [S04] <b>· 4 corroborating sources</b></span>
                  </article>
                  <article className="db-finding">
                    <span className="db-finding-index">F03 <i>MODERATE</i></span>
                    <h5>Membership changes need explicit safeguards</h5>
                    <p>Joint consensus in Raft and reconfiguration protocols in Paxos both demand careful rollout.</p>
                    <span className="db-cite">[S01] [S05] <b>· 2 corroborating sources</b></span>
                  </article>
                </div>
                <div className="db-actions">
                  <div className="db-subhead"><h4>Recommended next steps</h4><span>3 ACTIONS</span></div>
                  <div className="db-action-row"><span className="db-priority p1">P1</span><span>Benchmark quorum writes across target regions</span><small>Platform team</small></div>
                  <div className="db-action-row"><span className="db-priority p1">P1</span><span>Document region-loss and rejoin procedures</span><small>SRE</small></div>
                  <div className="db-action-row"><span className="db-priority p2">P2</span><span>Validate membership-change automation</span><small>Storage</small></div>
                </div>
                <div className="db-sources">
                  <div className="db-subhead"><h4>Source lineage</h4><span>12 FOUND · 11 RETAINED</span></div>
                  <div className="db-source"><span className="db-source-count">S01</span><div><strong>In Search of an Understandable Consensus Algorithm</strong><small>USENIX ATC · 2014 · Primary paper</small></div><span className="db-source-link">OPEN <Icon name="external" size={10} /></span></div>
                  <div className="db-source"><span className="db-source-count">S02</span><div><strong>Paxos Made Simple</strong><small>ACM SIGACT News · 2001 · Primary paper</small></div><span className="db-source-link">OPEN <Icon name="external" size={10} /></span></div>
                  <div className="db-source"><span className="db-source-count">S03</span><div><strong>Raft Refloated: Do We Have Consensus?</strong><small>ACM SIGOPS · 2020 · Peer reviewed</small></div><span className="db-source-link">OPEN <Icon name="external" size={10} /></span></div>
                  <button type="button" className="db-all-sources">View all 11 retained sources <Icon name="arrow" size={12} /></button>
                </div>
                <p className="db-disclosure"><b>Evidence note</b> · Source archive is simulated. Citations and confidence labels are fixture data for this completed run.</p>
                <div className="db-hash"><span>SHA-256 FINGERPRINT</span><code>9f3a7c2e…b821c4d6</code><Icon name="copy" size={12} /></div>
              </div>
            </section>

            <section className="db-panel">
              <div className="db-panel-head">
                <div className="db-panel-title"><span className="db-iconbox amber"><Icon name="radio" /></span><div><span className="db-kicker">04 / AUDIT TRAIL</span><h2>Run stream</h2></div></div>
                <span className="db-stream-state"><i /> SEALED</span>
              </div>
              <div className="db-stream">
                {stream.map(([time, title, message], index) => <div className={`db-stream-line ${index === 2 ? 'alert' : ''}`} key={time}>
                  <time>{time}</time><i className="db-stream-marker" /><div><strong>{title}</strong><p>{message}</p></div>
                </div>)}
              </div>
              <div className="db-stream-foot">5 EVENTS <span>·</span> ALL TIMES UTC <span>·</span> APPEND-ONLY</div>
            </section>

            <section className="db-panel">
              <div className="db-panel-head">
                <div className="db-panel-title"><span className="db-iconbox"><Icon name="clock" /></span><div><span className="db-kicker">05 / RUN ARCHIVE</span><h2>Saved runs</h2></div></div>
                <span className="db-panel-meta">03 RUNS</span>
              </div>
              <div className="db-history">
                <button type="button" className="db-history-row active">
                  <span className="db-history-icon"><Icon name="file" size={13} /></span><span className="db-history-main"><strong>Raft vs Paxos for geo-distributed metadata</strong><small>DB-2406-018 · 2m ago · 23.8s</small></span><span className="db-status-chip verified-chip">DONE</span>
                </button>
                <button type="button" className="db-history-row">
                  <span className="db-history-icon"><Icon name="file" size={13} /></span><span className="db-history-main"><strong>Postgres logical replication trade-offs</strong><small>DB-2406-017 · 1h ago · 31.2s</small></span><span className="db-status-chip verified-chip">DONE</span>
                </button>
                <button type="button" className="db-history-row">
                  <span className="db-history-icon"><Icon name="file" size={13} /></span><span className="db-history-main"><strong>Object storage consistency guarantees</strong><small>DB-2406-016 · Yesterday · paused</small></span><span className="db-status-chip paused">PAUSED</span>
                </button>
              </div>
            </section>
          </aside>
        </div>
        <footer className="db-footer"><span>DEEPBRIEF <b>·</b> AUDITABLE RESEARCH INFRASTRUCTURE</span><span><Icon name="shield" size={12} /> EXACT STAGE TIMING FROM SOURCE CHECKPOINTS</span></footer>
      </main>
    </div>
  );
}
