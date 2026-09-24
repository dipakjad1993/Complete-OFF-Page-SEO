import React, { useState, useMemo, useEffect } from 'react';
import {
  Rocket as RocketIcon, Globe, Loader2, CheckCircle2, XCircle,
  Sparkles, TrendingUp, Target, Brain, Link2, Users, ShieldAlert,
  BarChart3, ChevronDown, Sun, Moon,
  Building2, FileSearch, Database, Crown, Quote, ListChecks, Star,
  Server, Fingerprint, Network, FileText, MessageSquare,
  Webhook, Eye, Bug, ShieldCheck, Code, Mic,
  Map, Scale, PenTool, Handshake, History, Key, Gauge,
  Boxes, Route, ScanSearch, Hash, RefreshCcw,
  BadgeCheck, ArrowUpRight
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { FEATURES, FeatureDef } from '../data/features';
import IntakeForm, { IntakeState, emptyIntake } from './IntakeForm';
const Deliverables = React.lazy(() => import('./Deliverables'));

type StepStatus = 'pending' | 'active' | 'done' | 'error';

interface Step {
  key: string;
  label: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  status: StepStatus;
}

const STEPS: Step[] = [
  { key: 'brand', label: 'Register entity', icon: Building2, status: 'pending' },
  { key: 'schema', label: 'KG schema + execs', icon: Database, status: 'pending' },
  { key: 'intake', label: 'Competitors + governance', icon: Users, status: 'pending' },
  { key: 'analysis', label: '35-module engine', icon: Brain, status: 'pending' },
  { key: 'report', label: 'Compile report', icon: BarChart3, status: 'pending' },
];

const FEATURE_ICONS: Record<string, React.ComponentType<{ size?: number | string; className?: string }>> = {
  llm_perception: Brain, pr_hooks: PenTool, unlinked_citations: Link2,
  link_poisoning: ShieldAlert, podcast_video: Mic, vector_mapping: Network,
  rag_repair: Bug, consensus: Users, aeo: Webhook, pbn_detector: Fingerprint,
  revenue_sim: TrendingUp, dead_equity: Route, negative_seo: ShieldCheck,
  github_citations: Code, transcription: Mic, kg_arbitrage: Database,
  data_pr: BarChart3, simulation: Boxes, satellite: Satellite, rag_defense: ShieldAlert,
  visual_audit: Eye, apn_proxy: Server, graph_decay: History, c2pa: Key,
  compliance_guard: Scale, geo_crawl: Map, zero_party: Handshake,
  passage_scoring: ScanSearch, reddit_consensus: MessageSquare,
  competitor_bert: Brain, schema_auditor: FileSearch, anchor_entropy: Hash,
  crawl_priority: RefreshCcw, ftc_compliance: BadgeCheck, hreflang: Globe,
};

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button onClick={toggleTheme} className="icon-btn" aria-label="Toggle theme" title="Toggle theme">
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

function postJson(path: string, body: unknown) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (res) => {
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((json.detail as string) || `Request to ${path} failed (${res.status})`);
    return json;
  });
}

function formatValue(v: unknown): string {
  if (typeof v === 'number') return v % 1 === 0 ? v.toLocaleString() : v.toFixed(2);
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
}

function extractLinks(obj: unknown): string[] {
  const links = new Set<string>();
  const walk = (value: unknown, key = '') => {
    if (typeof value === 'string') {
      if (/^https?:\/\//i.test(value)) links.add(value);
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, key));
      return;
    }
    if (value && typeof value === 'object') {
      Object.entries(value).forEach(([k, v]) => {
        if (k === 'href' || k === 'url' || k === 'link' || k === 'wikipedia_url' || k === 'profile_url') {
          if (typeof v === 'string' && /^https?:\/\//i.test(v)) links.add(v);
        } else if (typeof v === 'string' && /^https?:\/\//i.test(v)) {
          links.add(v);
        } else {
          walk(v, k);
        }
      });
    }
  };
  walk(obj);
  return [...links].slice(0, 40);
}

function domainOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/* Render inline text with clickable URLs and highlighted key stats */
function renderInline(text: string, key: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(https?:\/\/[^\s)"'<>]+)|(\b\d+(?:\.\d+)?%?\b)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={`${key}-t${i++}`}>{text.slice(last, m.index)}</span>);
    if (m[1]) {
      let href = m[1].replace(/[.,;:]+$/, '');
      parts.push(
        <a key={`${key}-l${i++}`} href={href} target="_blank" rel="noopener noreferrer" className="inline-link" title={href}>
          {href}
        </a>
      );
    } else if (m[2]) {
      parts.push(<b key={`${key}-s${i++}`} className="stat-strong">{m[2]}</b>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(<span key={`${key}-e${i++}`}>{text.slice(last)}</span>);
  return parts;
}

/* Detailed analysis: split into sentences, group into readable paragraphs */
function DetailedAnalysis({ text }: { text?: unknown }) {
  if (!text) return null;
  const t = String(text);
  const sentences = t.split(/(?<=[.!?])\s+/).filter((s) => s.trim().length > 3);
  const paragraphs: string[][] = [];
  for (let i = 0; i < sentences.length; i += 3) paragraphs.push(sentences.slice(i, i + 3));
  const statSentences = sentences.filter((s) => /\d+%|\$\d|#\d|\b\d{2,}\b/.test(s)).slice(0, 5);
  return (
    <div className="detailed-analysis">
      {statSentences.length > 0 && (
        <div className="analysis-stats-row">
          {statSentences.map((s, i) => (
            <div key={i} className="analysis-stat-chip">
              {renderInline(s.replace(/\s*\([^)]*\)\s*$/, ''), `st${i}`)}
            </div>
          ))}
        </div>
      )}
      {paragraphs.map((group, i) => (
        <p key={i}>{group.map((s, j) => renderInline(s, `p${i}-${j}`))}</p>
      ))}
    </div>
  );
}

function DataTable({ rows, data }: { rows: unknown[]; data?: unknown }) {
  const rowsArr = Array.isArray(rows) ? rows : Array.isArray(data) ? data : null;
  if (!rowsArr || rowsArr.length === 0) return null;
  const sample = rowsArr[0];
  if (typeof sample !== 'object' || sample === null) return null;
  const keys = Object.entries(sample as Record<string, unknown>)
    .filter(([, v]) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean')
    .slice(0, 6);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{keys.map(([k]) => <th key={k}>{k.replace(/_/g, ' ')}</th>)}</tr>
        </thead>
        <tbody>
          {(rowsArr as Record<string, unknown>[]).slice(0, 10).map((row, i) => (
            <tr key={i}>
              {keys.map(([k]) => {
                const v = row[k];
                if (typeof v === 'string' && /^https?:\/\//i.test(v)) {
                  return <td key={k}><a href={v} target="_blank" rel="noopener noreferrer" className="table-link" title={v}>{v}</a></td>;
                }
                return <td key={k}>{formatValue(v)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Source card with favicon + full live URL */
function SourceCard({ url }: { url: string }) {
  const dom = domainOf(url);
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="source-card" title={url}>
      <span className="source-fav">{dom.charAt(0).toUpperCase()}</span>
      <span className="source-meta">
        <span className="source-domain">{dom}</span>
        <span className="source-url">{url}</span>
      </span>
      <ArrowUpRight size={13} className="source-arrow" />
    </a>
  );
}

function LinkChip({ href }: { href: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="link-chip" title={href}>
      <span className="link-chip-dot" />
      <span className="link-chip-domain">{domainOf(href)}</span>
      <span className="link-chip-url">{href}</span>
      <ArrowUpRight size={12} />
    </a>
  );
}

function AssessmentBadge({ assessment }: { assessment?: string }) {
  if (!assessment) return null;
  const a = String(assessment).toLowerCase();
  const good = ['good', 'excellent', 'clean', 'strong', 'healthy', 'positive', 'low'];
  const warn = ['attention', 'moderate', 'warning', 'medium', 'fair', 'needs'];
  const cls = good.includes(a) ? 'good' : warn.includes(a) ? 'medium' : 'critical';
  return <span className={`assessment-badge ${cls}`}>{String(assessment)}</span>;
}

function ScorePill({ value }: { value?: unknown }) {
  const n = typeof value === 'number' ? value : typeof value === 'string' && !isNaN(Number(value)) ? Number(value) : null;
  if (n === null) return null;
  const pct = Math.max(0, Math.min(100, n));
  const cls = pct >= 70 ? 'good' : pct >= 40 ? 'medium' : 'critical';
  return (
    <div className="score-pill" title={`Score: ${pct}/100`}>
      <div className={`score-pill-fill ${cls}`} style={{ width: `${pct}%` }} />
      <span>{Math.round(pct)}</span>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const r = 70;
  const c = 2 * Math.PI * r;
  const grade = pct >= 80 ? 'A' : pct >= 65 ? 'B' : pct >= 50 ? 'C' : pct >= 35 ? 'D' : 'F';
  const color = pct >= 80 ? 'var(--success)' : pct >= 65 ? 'var(--accent)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)';
  return (
    <div className="score-ring">
      <svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r={r} fill="none" stroke="var(--bg-inset)" strokeWidth="14" />
        <circle
          cx="90" cy="90" r={r} fill="none" stroke={color} strokeWidth="14"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (pct / 100) * c}
          transform="rotate(-90 90 90)"
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.22, 1, 0.36, 1)' }}
        />
      </svg>
      <div className="score-ring-center">
        <div className="score-ring-value" style={{ color }}>{Math.round(pct)}</div>
        <div className="score-ring-label">Overall Score</div>
        <div className="score-ring-grade">Grade {grade}</div>
      </div>
    </div>
  );
}

function KeyMetricRow({ label, value, index }: { label: string; value: unknown; index: number }) {
  return (
    <div className="key-metric-row">
      <div className="key-metric-label">{label.replace(/_/g, ' ')}</div>
      <div className="key-metric-track"><div className="key-metric-fill" style={{ width: `${Math.min(100, Math.abs(Number(value) || 0) * (index % 2 === 0 ? 1 : 0.6))}%` }} /></div>
      <div className="key-metric-value">{formatValue(value)}</div>
    </div>
  );
}

function SectionCard({ feature, meta }: { feature: FeatureDef; meta: Record<string, any> | null }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = FEATURE_ICONS[feature.key] || Sparkles;
  const unavailable = meta?.status === 'unavailable' || meta?.data_status === 'unavailable';
  const links = useMemo(() => extractLinks(meta), [meta]);
  const sources = useMemo<string[]>(() => {
    const s = meta?.sources;
    if (Array.isArray(s) && s.length > 0) {
      return s.map((x: any) => (typeof x === 'string' ? x : x?.url)).filter((u: any) => typeof u === 'string' && /^https?:\/\//i.test(u));
    }
    return links;
  }, [meta, links]);
  const numeric = meta
    ? Object.entries(meta)
        .filter(([k, v]) => k !== 'feature_name' && k !== 'assessment' && k !== 'recommendation' && k !== 'detailed_analysis' && typeof v === 'number')
        .slice(0, 6)
    : [];
  const CUSTOM_TABLES = new Set(['evidence_table', 'next_steps']);
  const dataTables = meta
    ? Object.entries(meta).filter(([k, v]) => !CUSTOM_TABLES.has(k) && Array.isArray(v) && v.length > 0 && typeof v[0] === 'object')
    : [];
  const evidenceRows: Array<any> = Array.isArray(meta?.evidence_table) ? meta.evidence_table : [];
  const nextSteps: Array<any> = Array.isArray(meta?.next_steps) ? meta.next_steps : [];
  const limitations: Array<any> = Array.isArray(meta?.limitations) ? meta.limitations : [];
  const confidence: number | null = typeof meta?.confidence === 'number' ? meta.confidence : null;

  return (
    <div className={`feature-card ${expanded ? 'expanded' : ''} ${unavailable ? 'unavailable' : ''}`} id={`feature-${feature.num}`}>
      <button className="feature-card-head" onClick={() => setExpanded((e) => !e)}>
        <div className="feature-num">#{feature.num}</div>
        <div className="feature-icon" style={{ ['--tone' as any]: undefined }}>
          <Icon size={19} />
        </div>
        <div className="feature-title-wrap">
          <div className="feature-title">{feature.name}</div>
          <div className="feature-tagline">{feature.tagline}</div>
        </div>
        {unavailable ? (
          <span className="assessment-badge medium">No data</span>
        ) : (
          <>
            <AssessmentBadge assessment={meta?.assessment} />
            <div className="feature-score"><ScorePill value={meta?.score ?? meta?.overall_score} /></div>
          </>
        )}
        <ChevronDown size={18} className={`feature-chev ${expanded ? 'open' : ''}`} />
      </button>

      {expanded && (
        <div className="feature-card-body">
          {unavailable ? (
            <div className="feature-unavailable">
              <ShieldAlert size={15} />
              <div>
                <strong>No verified data available for this module.</strong>
                <p>This tool never fabricates results. {String(meta?.requires ?? 'This module requires an integration or live data source')} is not configured, so no numbers were produced for this brand.</p>
                {meta?.recommendation && <p>{String(meta.recommendation)}</p>}
                {nextSteps.length > 0 && (
                  <ol className="actions-list">
                    {nextSteps.map((n: any, i: number) => (
                      <li key={i}>
                        <span className="assessment-badge medium">{String(n.priority ?? 'P1')}</span>{' '}
                        {String(n.step ?? '')}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="feature-explain">
                <div className="explain-block">
                  <div className="explain-label"><Target size={13} /> What it does</div>
                  <p>{feature.what}</p>
                </div>
                <div className="explain-block">
                  <div className="explain-label"><Crown size={13} /> How it works</div>
                  <p>{feature.how}</p>
                </div>
                {feature.value && (
                  <div className="explain-block accent">
                    <div className="explain-label"><Star size={13} /> The value</div>
                    <p>{feature.value}</p>
                  </div>
                )}
              </div>

              {/* Executive takeaway — plain-language verdict from live numbers */}
              {meta?.executive_takeaway && (
                <div className="feature-recommendation">
                  <h4 className="feature-subhead"><BadgeCheck size={14} /> Executive takeaway</h4>
                  <p className="actions-text">{String(meta.executive_takeaway)}</p>
                </div>
              )}

              {/* Key findings */}
              {meta?.findings && meta.findings.length > 0 && (
                <div className="feature-findings">
                  <h4 className="feature-subhead"><Sparkles size={14} /> Key findings for this brand</h4>
                  <div className="findings-grid">
                    {meta.findings.slice(0, 12).map((f: any, i: number) => (
                      <div key={i} className="finding-card">
                        <div className="finding-value">{f.value}</div>
                        <div className="finding-metric">{f.metric}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Evidence table — every signal with its live reading */}
              {evidenceRows.length > 0 && (
                <div className="feature-findings">
                  <h4 className="feature-subhead"><ListChecks size={14} /> Evidence ({evidenceRows.length} live signals)</h4>
                  <div className="table-container">
                    <table>
                      <thead><tr><th>Signal</th><th>Observed</th><th>Reading</th></tr></thead>
                      <tbody>
                        {evidenceRows.slice(0, 12).map((r: any, i: number) => (
                          <tr key={i}>
                            <td><strong>{String(r.signal ?? '')}</strong></td>
                            <td><span className="stat-strong">{String(r.observed ?? '')}</span></td>
                            <td>{String(r.reading ?? '')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="feature-cols">
                {numeric.length > 0 && (
                  <div className="feature-metrics">
                    <h4 className="feature-subhead"><BarChart3 size={14} /> Key metrics</h4>
                    <div className="key-metrics">
                      {numeric.map(([k, v], i) => (
                        <KeyMetricRow key={k} label={k} value={v} index={i} />
                      ))}
                    </div>
                  </div>
                )}

                {(meta?.recommendation || (Array.isArray(meta?.actions) && meta.actions.length > 0) || nextSteps.length > 0) && (
                  <div className="feature-recommendation">
                    <h4 className="feature-subhead"><Quote size={14} /> Prioritized next steps</h4>
                    {nextSteps.length > 0 ? (
                      <ol className="actions-list">
                        {nextSteps.map((n: any, i: number) => (
                          <li key={i}>
                            <span className={`assessment-badge ${n.priority === 'P1' ? 'critical' : n.priority === 'P2' ? 'medium' : 'low'}`}>
                              {String(n.priority ?? 'P3')}
                            </span>{' '}
                            {typeof n.step === 'string' ? renderInline(n.step, `n${i}`) : String(n.step ?? '')}
                          </li>
                        ))}
                      </ol>
                    ) : Array.isArray(meta?.actions) && meta.actions.length > 0 ? (
                      <ol className="actions-list">
                        {meta.actions.map((a: string, i: number) => (
                          <li key={i}>{renderInline(a, `a${i}`)}</li>
                        ))}
                      </ol>
                    ) : (
                      <p className="actions-text">{renderInline(String(meta?.recommendation ?? ''), 'rec')}</p>
                    )}
                  </div>
                )}

              {/* Confidence + limitations — honest coverage disclosure */}
              {(confidence !== null || limitations.length > 0) && (
                <div className="feature-methodology">
                  <Gauge size={13} />
                  <span>
                    {confidence !== null && <>Confidence <strong>{confidence}</strong> (coverage-based: base 0.6 + sources + provider — see methodology). </>}
                    {limitations.length > 0 && <>Limits: {limitations.map((l: any) => String(l)).join(' ')}</>}
                    {limitations.length === 0 && <>No blocking limitations observed in this run.</>}
                  </span>
                </div>
              )}
              </div>

              {meta?.detailed_analysis && (
                <div className="feature-detail">
                  <h4 className="feature-subhead"><FileText size={14} /> Detailed analysis</h4>
                  <DetailedAnalysis text={meta.detailed_analysis} />
                </div>
              )}

              {dataTables.map(([k, rows]) => (
                <div key={k} className="feature-table-block">
                  <h4 className="feature-subhead"><ListChecks size={14} /> {k.replace(/_/g, ' ')}</h4>
                  <DataTable rows={rows as unknown[]} />
                </div>
              ))}

              {sources.length > 0 && (
                <div className="feature-sources">
                  <h4 className="feature-subhead"><Link2 size={14} /> Verified sources ({sources.length})</h4>
                  <div className="source-grid">
                    {sources.map((s: string) => <SourceCard key={s} url={s} />)}
                  </div>
                </div>
              )}

              {links.length > 0 && sources.length === 0 && (
                <div className="feature-sources">
                  <h4 className="feature-subhead"><Link2 size={14} /> Sources</h4>
                  <div className="link-chips">
                    {links.map((l) => <LinkChip key={l} href={l} />)}
                  </div>
                </div>
              )}

              {meta?.methodology && (
                <div className="feature-methodology">
                  <Gauge size={13} /> {String(meta.methodology)}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SummaryCards({ summary }: { summary: Record<string, any> }) {
  const cards: { label: string; value: unknown; icon: React.ComponentType<{ size?: number | string; className?: string }>; tone: string; fmt?: (v: unknown) => string }[] = [
    { label: 'Total brand mentions', value: summary.total_mentions, icon: MessageSquare, tone: 'indigo' },
    { label: 'Unlinked opportunities', value: summary.unlinked_opportunities, icon: Link2, tone: 'cyan' },
    { label: 'Backlink health', value: summary.backlink_health, icon: ShieldCheck, tone: 'emerald', fmt: (v) => (v == null || v === '' ? '—' : `${formatValue(v)}%`) },
    { label: 'Toxic backlinks', value: summary.toxic_backlinks, icon: ShieldAlert, tone: 'rose' },
    { label: 'LLM citation rate', value: summary.llm_citation_rate, icon: Brain, tone: 'violet', fmt: (v) => (v == null || v === '' ? '—' : `${formatValue(v)}%`) },
    { label: 'Knowledge graph coverage', value: summary.kg_coverage, icon: Database, tone: 'indigo', fmt: (v) => (v == null || v === '' ? '—' : `${formatValue(v)}%`) },
    { label: 'Vector similarity', value: summary.vector_similarity, icon: Network, tone: 'cyan' },
    { label: 'Consensus sentiment', value: summary.sentiment, icon: Users, tone: 'emerald' },
    { label: 'PBN / synthetic risk', value: summary.pbn_risk, icon: Fingerprint, tone: 'amber' },
    { label: 'Anchor entropy', value: summary.anchor_entropy, icon: Hash, tone: 'violet' },
    { label: 'AEO / agentic score', value: summary.aeo_score, icon: Webhook, tone: 'indigo' },
    { label: 'Share of search', value: summary.share_of_search, icon: TrendingUp, tone: 'amber' },
    { label: 'PR hooks generated', value: summary.pr_hooks_generated, icon: PenTool, tone: 'cyan' },
    { label: 'Podcast / video targets', value: summary.podcast_opportunities, icon: Mic, tone: 'emerald' },
    { label: 'GitHub citations', value: summary.github_references, icon: Code, tone: 'rose' },
  ];
  return (
    <div className="summary-grid">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div key={c.label} className="metric-card">
            <div className="metric-top">
              <div className={`metric-icon ${c.tone}`}><Icon size={18} /></div>
            </div>
            <div className="metric-value">{c.fmt ? c.fmt(c.value) : formatValue(c.value)}</div>
            <div className="metric-label">{c.label}</div>
          </div>
        );
      })}
    </div>
  );
}

function ProgressPanel({ progress, now }: { progress: Record<string, any> | null; now: number }) {
  if (!progress || progress.status === 'idle') return null;
  const total = progress.total_modules || 35;
  const done = progress.module_index || 0;
  const pct = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
  const parseUtc = (s: string | undefined) => {
    if (!s) return NaN;
    const t = /(?:Z|[+-]\d\d:\d\d)$/.test(s) ? s : s + 'Z';
    const ms = new Date(t).getTime();
    return isNaN(ms) ? NaN : ms;
  };
  const started = parseUtc(String(progress.started_at || ''));
  const apiUpdated = parseUtc(String(progress.updated_at || ''));
  const apiElapsed = progress.elapsed_secs || 0;
  let elapsedSecs = apiElapsed;
  if (!isNaN(apiUpdated) && !isNaN(started)) {
    elapsedSecs = apiElapsed + Math.max(0, (now - apiUpdated) / 1000);
  } else if (!isNaN(started)) {
    elapsedSecs = Math.max(0, (now - started) / 1000);
  }
  elapsedSecs = Math.round(elapsedSecs);
  const eta = progress.eta_secs || 0;
  const avg = progress.avg_per_module_secs || 0;
  const mods = (progress.modules as Record<string, any>) || {};
  const activeKey = progress.current_module;
  const activeLabel = progress.current_module_label || 'Running…';

  const fmt = (s: number) => {
    s = Math.max(0, Math.round(s));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec.toString().padStart(2, '0')}s` : `${sec}s`;
  };

  return (
    <section className="progress-panel">
      <div className="progress-head">
        <div className="progress-title">
          <Loader2 size={17} className="animate-spin" style={{ color: 'var(--primary)' }} />
          {progress.status === 'completed' ? 'Analysis complete' : 'Analysis in progress'}
        </div>
        <div className="progress-pct">{pct}%</div>
      </div>

      <div className="progress-bar-lg">
        <div className="progress-bar-lg-fill" style={{ width: `${pct}%` }} />
      </div>

      <div className="progress-stats">
        <div><span>Elapsed</span><strong>{fmt(elapsedSecs)}</strong></div>
        <div><span>Estimated remaining</span><strong>{progress.status === 'completed' ? 'Done' : fmt(eta)}</strong></div>
        <div><span>Avg per module</span><strong>{avg ? fmt(avg) : '…'}</strong></div>
        <div><span>Modules done</span><strong>{done} / {total}</strong></div>
      </div>

      <div className="progress-current">
        <span className="progress-current-dot" />
        <span className="progress-current-label">Now analyzing</span>
        <strong>{activeLabel}</strong>
      </div>

      <div className="progress-modules">
        {FEATURES.map((f) => {
          const m = mods[f.key];
          const status = m ? m.status : f.key === activeKey ? 'active' : 'pending';
          return (
            <div key={f.key} className={`progress-module ${status}`} title={`${f.name}${m?.runtime_secs ? ` · ${fmt(m.runtime_secs)}` : ''}`}>
              <span className="progress-module-num">#{f.num}</span>
              <span className="progress-module-name">{f.name}</span>
              {status === 'done' && m?.runtime_secs != null && <span className="progress-module-time">{fmt(m.runtime_secs)}</span>}
              {status === 'active' && <Loader2 size={11} className="animate-spin" />}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function ToolApp() {
  const [phase, setPhase] = useState<'intake' | 'running' | 'results' | 'error'>('intake');
  const [tab, setTab] = useState<'modules' | 'deliverables'>('modules');
  const [intake, setIntake] = useState<IntakeState>(emptyIntake());
  const [intakeError, setIntakeError] = useState('');
  const [error, setError] = useState('');
  const [steps, setSteps] = useState<Step[]>(STEPS.map((s) => ({ ...s })));
  const [progressLabel, setProgressLabel] = useState('');
  const [progress, setProgress] = useState<Record<string, any> | null>(null);
  const [now, setNow] = useState<number>(Date.now());
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [brand, setBrand] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    if (phase !== 'running') return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [phase]);

  const setStepStatus = (key: string, status: StepStatus) =>
    setSteps((prev) => prev.map((s) => (s.key === key ? { ...s, status } : s)));

  const splitList = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean);
  const splitLines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean);

  const runAnalysis = async () => {
    const domain = intake.domain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
    if (!domain) {
      setIntakeError('Enter the brand domain first.');
      return;
    }
    setIntakeError('');
    setError('');
    setPhase('running');
    setResult(null);
    setBrand(null);
    setProgress(null);
    setSteps(STEPS.map((s) => ({ ...s })));

    try {
      // 1. Register / find brand entity
      setStepStatus('brand', 'active');
      setProgressLabel('Registering brand entity…');
      let brandId: number;
      const brandsRes = await fetch('/api/v1/brands/');
      const brandsList = await brandsRes.json();
      const existing = Array.isArray(brandsList)
        ? brandsList.find((b: { domain?: string }) => (b.domain || '').toLowerCase() === domain)
        : null;
      if (existing) {
        brandId = existing.id;
      } else {
        try {
          const created = await postJson('/api/v1/brands/', {
            name: intake.name || domain.split('.')[0],
            domain,
            description: intake.description || '',
            primary_categories: splitList(intake.categories),
            seed_keywords: splitList(intake.keywords),
          });
          brandId = created.id;
        } catch (e) {
          // Race / duplicate: brand was registered already (e.g. another run
          // created it). Reuse the existing record instead of dying on 400.
          const retryRes = await fetch('/api/v1/brands/');
          const retryList = await retryRes.json();
          const found = Array.isArray(retryList)
            ? retryList.find((b: { domain?: string }) => (b.domain || '').toLowerCase() === domain)
            : null;
          if (found) {
            brandId = found.id;
          } else {
            throw e;
          }
        }
      }
      setStepStatus('brand', 'done');

      // 2. Knowledge-graph schema + official messaging + taxonomy
      setStepStatus('schema', 'active');
      setProgressLabel('Saving knowledge-graph schema and official messaging vectors…');
      await postJson('/api/v1/intake/brand-schema', {
        brand_id: brandId,
        name: intake.name || domain.split('.')[0],
        kg_mid: intake.kgMid || '',
        wikidata_id: intake.wikidataId || '',
        crunchbase_id: intake.crunchbaseId || '',
        wikipedia_url: intake.wikipediaUrl || '',
        description: intake.description || '',
        primary_categories: splitList(intake.categories),
        seed_keywords: splitList(intake.keywords),
        official_messaging: intake.officialMessaging || null,
        topical_taxonomy: intake.taxonomy ? { pillars: splitList(intake.taxonomy) } : null,
        gsc_property_id: intake.gscProperty || '',
        ga4_property_id: intake.ga4Id || '',
        bot_crawl_api: (intake as any).botCrawlApi || '',
        link_graph_providers: (intake as any).linkProviders || [],
      });
      for (const s of intake.spokes) {
        if (!s.name || !s.name.trim()) continue;
        try {
          await postJson('/api/v1/intake/executives', {
            brand_id: brandId,
            name: s.name.trim(),
            title: s.title || '',
            bio: s.bio || '',
            credentials: splitList(s.credentials),
            expertise_areas: splitList(s.expertise),
            social_profiles: { linkedin: s.linkedin || '', twitter: s.twitter || '' },
            quotes: splitLines(s.quotes),
            kg_mid: (s as any).kgMid || '',
            wikidata_id: (s as any).wikidataId || '',
            is_sme: !!(s as any).isSme,
            department: (s as any).department || '',
          });
        } catch (_) { /* non-fatal */ }
      }
      setStepStatus('schema', 'done');

      // 3. Competitors + governance (risk config, scrapers, compliance rule)
      setStepStatus('intake', 'active');
      setProgressLabel('Saving competitor intelligence and governance guardrails…');
      try {
        const compsRes = await fetch(`/api/v1/intake/competitors/${brandId}`);
        const compsList = await compsRes.json();
        if (Array.isArray(compsList)) {
          for (const old of compsList) if (old && old.id) await fetch(`/api/v1/intake/competitors/${old.id}`, { method: 'DELETE' });
        }
      } catch (_) { /* non-fatal */ }
      if (intake.competitors && intake.competitors.length > 0) {
        for (const c of intake.competitors) {
          if (!c.name || !c.name.trim()) continue;
          try {
            await postJson('/api/v1/intake/competitors', {
              brand_id: brandId, name: c.name.trim(), domain: c.domain || '', wikidata_id: c.wikidata_id || '',
            });
          } catch (_) { /* non-fatal */ }
        }
      }
      try {
        await postJson('/api/v1/intake/risk-config', {
          brand_id: brandId,
          risk_level: intake.riskLevel,
          risk_score: (intake as any).riskScore ?? 10,
          allowed_tactics: intake.tactics,
          blocked_domains: splitLines(intake.blockedDomains),
          blocked_topics: splitList(intake.blockedTopics),
          ftc_compliance: true,
          sec_compliance: true,
          max_outreach_per_day: intake.maxOutreach,
        });
        await postJson('/api/v1/intake/scraper-config', {
          brand_id: brandId,
          sources: intake.sources,
          frequency: 'daily',
          enabled: true,
          listening_streams: (intake as any).listeningStreams || [],
          include_transcripts: true,
          crawl_depth: 2,
        });
      } catch (_) { /* non-fatal */ }
      if (intake.compName && intake.compContent) {
        try {
          await postJson('/api/v1/compliance/rules', {
            brand_id: brandId,
            rule_type: intake.compType,
            rule_name: intake.compName,
            rule_content: { keywords: splitList(intake.compContent) },
          });
        } catch (_) { /* non-fatal */ }
      }
      setStepStatus('intake', 'done');

      // 4. Run analysis — NON-BLOCKING by default (run-async + poll). Blocking /run kept for scripts only.
      setStepStatus('analysis', 'active');
      setProgressLabel('Starting 35-module engine (non-blocking)…');
      let pollStopped = false;
      (async () => {
        while (!pollStopped) {
          try {
            const res = await fetch(`/api/v1/analysis/progress/${brandId}`);
            const p = await res.json();
            if (p && typeof p === 'object' && p.status) {
              setProgress(p);
              if (p.current_module_label && p.status === 'running') setProgressLabel(p.current_module_label);
              if (p.status === 'completed' || p.status === 'failed') break;
            }
          } catch (_) { /* transient */ }
          await new Promise((r) => setTimeout(r, 1200));
        }
      })();
      // Prefer run-async (50s * 7 batches = 60-180s without holding Render proxy). Fall back to blocking only if /run-async is missing.
      let analysis: any = null;
      try {
        const asyncRes = await postJson('/api/v1/analysis/run-async', { brand_id: brandId, analysis_type: 'full' });
        const jobId = asyncRes.job_id || asyncRes.job;
        // poll progress until completed (or fetch results when progress says completed)
        for (let tries = 0; tries < 180; tries++) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const pr = await fetch(`/api/v1/analysis/progress/${brandId}`).then((x) => x.json());
            if (pr?.status === 'completed') break;
            if (pr?.status === 'failed' || pr?.status === 'error') throw new Error(pr?.reason || 'Analysis failed');
          } catch {}
          // also try fetching results directly — run_full_analysis writes *_latest.json atomically
          try {
            const rr = await fetch(`/api/v1/analysis/results/${brandId}`).then((x) => x.json());
            if (rr && rr.brand) { analysis = rr; break; }
          } catch {}
        }
        if (!analysis) {
          const final = await fetch(`/api/v1/analysis/results/${brandId}`).then((x) => x.json());
          if (final && final.brand) analysis = final;
          else throw new Error('Async job did not produce results in time — check /api/v1/analysis/progress/' + brandId);
        }
        // warn if server returned deprecated header on fallback path
        if (analysis && (analysis as any).deprecated) console.warn('[analysis] using deprecated /run path');
      } catch (e) {
        // Only as last resort for local scripts without run-async: blocking /run (will be Sunset 2026-12-31)
        console.warn('[analysis] run-async failed, falling back to blocking /run (deprecated):', (e as Error).message);
        analysis = await postJson('/api/v1/analysis/run', { brand_id: brandId, analysis_type: 'full' });
      }
      pollStopped = true;
      setProgress((prev) => (prev ? { ...prev, status: 'completed' } : { status: 'completed', module_index: 35, total_modules: 35 }));
      setStepStatus('analysis', 'done');
      setProgressLabel('Analysis complete — compiling report');

      // 5. Report
      setStepStatus('report', 'active');
      setBrand({ id: brandId, name: analysis.brand, domain: analysis.domain, started: analysis.started_at, completed: analysis.completed_at });
      setResult(analysis);
      setStepStatus('report', 'done');
      setPhase('results');
      setTab('modules');
      setTimeout(() => {
        document.getElementById('report')?.scrollIntoView({ behavior: 'smooth' });
      }, 300);
    } catch (err) {
      const msg = (err as Error).message || 'Analysis failed.';
      setError(msg);
      setSteps((prev) =>
        prev.map((s) => (s.status === 'active' ? { ...s, status: 'error' as StepStatus } : s))
      );
      setPhase('error');
    }
  };

  const reset = () => {
    setPhase('intake');
    setResult(null);
    setBrand(null);
    setProgress(null);
    setError('');
    setIntakeError('');
    setSteps(STEPS.map((s) => ({ ...s })));
  };

  const summary = (result?.summary as Record<string, any>) ?? {};
  const sections = (result?.sections as Record<string, Record<string, any>>) ?? {};
  const overallScore = typeof summary.overall_score === 'number' ? summary.overall_score : null;
  const runFeatures = useMemo(() => {
    return FEATURES.filter((f) => sections[f.key]);
  }, [result]);

  const allLinks = useMemo(() => {
    const set = new Set<string>();
    Object.values(sections).forEach((s) => extractLinks(s).forEach((l) => set.add(l)));
    return [...set].slice(0, 60);
  }, [result]);

  return (
    <div className="app-backdrop">
      <header className="topnav">
        <div className="topnav-inner">
          <div className="topnav-brand">
            <div className="brand-mark"><Brain size={20} /></div>
            <div>
              <div className="topnav-title">Off-Page <span className="gradient-text">SEO Intelligence</span></div>
              <div className="topnav-sub">Entity-First Off-Page Command Center · 35 modules</div>
            </div>
          </div>
          <div className="topnav-right">
            <span className="status-badge active">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] animate-pulse" />
              Live
            </span>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="tool-main">
        {/* ============ PAGE 1 · INTAKE (The Required Inputs Layer) ============ */}
        {phase === 'intake' && (
          <section className="intake-page">
            <div className="tool-hero-inner intake-hero">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--primary-soft)] text-[11px] font-bold uppercase tracking-widest text-[var(--primary)] mb-5">
                <Building2 size={13} /> Step 1 · Required Inputs
              </div>
              <h1 className="tool-hero-title">
                Configure the <span className="gradient-text">Intake Data Layer</span>
              </h1>
              <p className="tool-hero-sub">
                No garbage-in, garbage-out enterprise SEO. Feed the engine your entity schema, spokesperson matrix,
                technical APIs, listening streams and governance guardrails — then run the full 35-module analysis.
              </p>
            </div>
            <IntakeForm value={intake} onChange={setIntake} />
            {intakeError && (
              <div className="tool-error">
                <XCircle size={17} className="flex-shrink-0 mt-0.5" />
                <div>{intakeError}</div>
              </div>
            )}
            <div className="intake-actions">
              <button onClick={runAnalysis} className="info-cta tool-run-btn intake-run-btn" style={{ fontSize: '1.05rem', padding: '1rem 2.4rem' }}>
                <Brain size={20} /> Run Full 35-Module Analysis
              </button>
              <p className="field-hint">Runs: entity registration → KG schema → executives → competitors → governance → all 35 modules → deliverables.</p>
            </div>
          </section>
        )}

        {/* ============ RUNNING PIPELINE ============ */}
        {phase === 'running' && (
          <section className="tool-pipeline">
            <div className="tool-hero-inner" style={{ paddingTop: '1.5rem' }}>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--primary-soft)] text-[11px] font-bold uppercase tracking-widest text-[var(--primary)] mb-5">
                <Loader2 size={13} className="animate-spin" /> Step 2 · Processing Engine
              </div>
              <p className="tool-progress-label">
                <Loader2 size={15} className="animate-spin" /> {progressLabel}
              </p>
            </div>
            <div className="pipeline-steps">
              {steps.map((step) => {
                const Icon = step.icon;
                return (
                  <div key={step.key} className={`pipeline-step ${step.status}`}>
                    <div className="pipeline-icon">
                      {step.status === 'done' ? <CheckCircle2 size={17} /> : step.status === 'error' ? <XCircle size={17} /> : step.status === 'active' ? <Loader2 size={17} className="animate-spin" /> : <Icon size={17} />}
                    </div>
                    <div className="pipeline-label">{step.label}</div>
                  </div>
                );
              })}
            </div>
            {phase === 'running' && <ProgressPanel progress={progress} now={now} />}
            {error && (
              <div className="tool-error">
                <XCircle size={17} className="flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-bold mb-0.5">Analysis failed</div>
                  {error}
                </div>
              </div>
            )}
            <div className="intake-actions" style={{ paddingBottom: '2rem' }}>
              <button onClick={reset} className="info-cta tool-run-btn cancel">Cancel & Edit Inputs</button>
            </div>
          </section>
        )}

        {/* ============ ERROR (was missing: any failure rendered a blank page) ============ */}
        {phase === 'error' && (
          <section className="tool-error-page" style={{ maxWidth: '720px', margin: '2rem auto', textAlign: 'center' }}>
            <div className="tool-error" style={{ textAlign: 'left' }}>
              <XCircle size={20} className="flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-bold mb-0.5" style={{ fontSize: '1.1rem' }}>Analysis failed</div>
                <div>{error || 'Something went wrong while running the analysis.'}</div>
                <div className="field-hint" style={{ marginTop: '0.5rem' }}>
                  Nothing was lost — your inputs are still filled in. Common causes: the brand
                  domain is already registered (now auto-reused), a long run timed out, or the
                  server restarted mid-run. Retry, or go back and edit inputs.
                </div>
              </div>
            </div>
            <div className="intake-actions" style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', marginTop: '1rem' }}>
              <button onClick={runAnalysis} className="info-cta tool-run-btn" style={{ fontSize: '1rem', padding: '0.9rem 2rem' }}>
                <Brain size={18} /> Retry Analysis
              </button>
              <button onClick={reset} className="info-cta tool-run-btn cancel">← Back to Inputs</button>
            </div>
          </section>
        )}

        {/* ============ PAGES 2 + 3 · RESULTS (Modules + Deliverables) ============ */}
        {phase === 'results' && result && (
          <div className="results" id="report">
            {/* Tab bar */}
            <div className="results-tabs">
              <button className={tab === 'modules' ? 'active' : ''} onClick={() => setTab('modules')}>
                <BarChart3 size={15} /> All 35 Modules — Full Findings
              </button>
              <button className={tab === 'deliverables' ? 'active' : ''} onClick={() => setTab('deliverables')}>
                <FileText size={15} /> Tool Outputs — The Deliverables Layer
              </button>
              <button className="tab-ghost" onClick={reset}>← New brand / edit inputs</button>
            </div>

            {tab === 'modules' ? (
              <>
                {/* Executive summary */}
                <section className="exec-summary">
                  <div className="exec-head">
                    <div>
                      <h2 className="section-title">Executive Summary</h2>
                      <p className="section-sub">
                        Off-page authority report for <strong>{String(brand?.name ?? result.brand ?? '')}</strong>
                        {brand?.domain ? ` (${String(brand.domain)})` : ''}
                        {brand?.completed ? <> · completed {new Date(String(brand.completed)).toLocaleString()}</> : ''}
                      </p>
                    </div>
                    <div className="exec-badges">
                      <span className="status-badge active"><span className="w-1.5 h-1.5 rounded-full bg-[var(--success)]" /> {summary.features_analyzed ?? 35} modules analyzed</span>
                      {summary.modules_unavailable > 0 && (
                        <span className="status-badge"><span className="w-1.5 h-1.5 rounded-full bg-[var(--warning)]" /> {summary.modules_unavailable} modules report no-data (key required)</span>
                      )}
                    </div>
                  </div>

                  <div className="exec-body">
                    <div className="exec-ring">
                      <ScoreRing score={overallScore ?? 0} />
                      <div className="exec-verdict">
                        <span className="verdict-title">Overall authority</span>
                        <p>
                          {overallScore === null
                            ? 'No composite score returned (no measured metrics were available).'
                            : overallScore >= 80
                              ? 'Exceptional. Your brand entity is strongly embedded across LLM answers, backlinks, knowledge graphs and third-party consensus.'
                              : overallScore >= 65
                                ? 'Strong. Solid off-page footprint with clear, high-leverage gaps to close for top-tier authority.'
                                : overallScore >= 50
                                  ? 'Moderate. Core signals exist, but gaps in consensus, citations and structured presence are capping your authority.'
                                  : 'Weak. Significant gaps across mentions, backlinks and structured entity signals need urgent attention.'}
                        </p>
                      </div>
                    </div>
                    <SummaryCards summary={summary} />
                  </div>
                </section>

                {/* Feature index */}
                <section className="feature-index">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="section-title">All 35 Modules — Full Findings</h2>
                      <p className="section-sub">Every module expanded below with methodology, live metrics, verified sources and recommendations. Modules with no data report an honest "No data" state.</p>
                    </div>
                    <div className="feature-jump">
                      {runFeatures.slice(0, 12).map((f) => (
                        <a key={f.num} href={`#feature-${f.num}`}>#{f.num}</a>
                      ))}
                    </div>
                  </div>
                </section>

                {/* Feature cards */}
                <section className="features-list">
                  {runFeatures.map((f) => (
                    <SectionCard key={f.key} feature={f} meta={sections[f.key] ?? null} />
                  ))}
                </section>

                {/* Source library */}
                {allLinks.length > 0 && (
                  <section className="source-library">
                    <h2 className="section-title">Verified Source Library</h2>
                    <p className="section-sub">Every real URL surfaced by the analysis — click to verify each source directly.</p>
                    <div className="link-chips">
                      {allLinks.map((l) => <LinkChip key={l} href={l} />)}
                    </div>
                  </section>
                )}
              </>
            ) : (
              <React.Suspense fallback={<div className="deliverables" style={{ padding: '2rem', textAlign: 'center' }}><Loader2 size={18} className="animate-spin" style={{ display: 'inline-block' }} /> Loading deliverables (code-split)…</div>}>
                <Deliverables
                  summary={summary}
                  sections={sections}
                  brandId={typeof brand?.id === 'number' ? brand.id : null}
                  brandName={String(brand?.name ?? result?.brand ?? '')}
                  brandDomain={String(brand?.domain ?? result?.domain ?? '')}
                />
              </React.Suspense>
            )}

            {/* Footer info */}
            <section className="tool-footer-info">
              <h2 className="section-title">About this tool</h2>
              <div className="footer-info-grid">
                <div className="footer-info-card">
                  <h4><FileSearch size={15} /> What it is</h4>
                  <p>A 35-module off-page SEO intelligence engine that measures and improves how search engines, LLM agents and AI answers perceive, cite and rank your brand entity.</p>
                </div>
                <div className="footer-info-card">
                  <h4><Database size={15} /> What it needs</h4>
                  <p>Complete the intake layer (entity schema, spokespersons, API connections, governance) for the deepest results. Unconfigured integrations report honest "no data" states.</p>
                </div>
                <div className="footer-info-card">
                  <h4><Crown size={15} /> What it does</h4>
                  <p>Crawls the live web for mentions, backlinks, transcripts, knowledge graphs and consensus — then scores your brand across 35 modules with prioritized actions.</p>
                </div>
                <div className="footer-info-card">
                  <h4><Star size={15} /> What to expect</h4>
                  <p>A client-ready report in minutes: overall score, per-module findings, verified source links, deliverables and recommendations — in plain language.</p>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>

      <footer className="tool-foot">
        <div className="tool-foot-inner">
          <div className="flex items-center gap-2">
            <div className="brand-mark" style={{ width: 34, height: 34 }}><Brain size={16} /></div>
            <div className="text-[12.5px] font-semibold">Off-Page SEO Intelligence · v2026.1</div>
          </div>
          <div className="text-[11px] text-[var(--text-muted)]">Entity-first brand consensus across 35 off-page modules. Real data only — nothing is fabricated.</div>
        </div>
      </footer>
    </div>
  );
}

function Satellite(props: { size?: number | string; className?: string }) {
  return <RocketIcon size={props.size} className={props.className} />;
}
