import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart3, Brain, Network, PenTool, Link2, Mic, Server, ShieldAlert,
  ShieldCheck, Fingerprint, Bug, Database, Globe, FileCode2, Handshake, Gauge, Hash,
  Download, Loader2, FileText, Activity, AlertTriangle, CheckCircle2,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';

interface Props {
  summary: Record<string, any>;
  sections: Record<string, any>;
  brandId?: number | null;
  brandName?: string;
  brandDomain?: string;
}

function fmt(v: unknown, unit = ''): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return `${v % 1 === 0 ? v.toLocaleString() : v.toFixed(2)}${unit}`;
  return String(v);
}

function Empty({ label, requires }: { label: string; requires?: string }) {
  return (
    <div className="deliverable-empty">
      <ShieldAlert size={14} />
      <span>{label} — no verified data was produced{requires ? ` (${requires} not configured)` : ''}. No numbers are fabricated.</span>
    </div>
  );
}

function Block({ title, icon: Icon, children }: { title: string; icon: React.ComponentType<{ size?: number | string }>; children: React.ReactNode }) {
  return (
    <section className="deliverable-block">
      <h3 className="deliverable-title"><Icon size={16} /> {title}</h3>
      {children}
    </section>
  );
}

function Takeaway({ text }: { text?: unknown }) {
  if (!text) return null;
  return <p className="deliverable-note" style={{ borderLeft: '3px solid var(--accent)', paddingLeft: '0.6rem' }}>{String(text)}</p>;
}

function Conf({ value, limitations }: { value?: unknown; limitations?: unknown }) {
  const lims = Array.isArray(limitations) ? limitations.map(String).filter(Boolean) : [];
  if (typeof value !== 'number' && lims.length === 0) return null;
  const pct = typeof value === 'number' ? Math.max(0, Math.min(100, value > 1 && value <= 100 ? value : value * 100)) : null;
  return (
    <div style={{ marginTop: '0.6rem' }}>
      {pct !== null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
          <div className="key-metric-track" style={{ flex: 1 }}>
            <div className="key-metric-fill" style={{ width: `${pct}%` }} />
          </div>
          <span style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
            Confidence {typeof value === 'number' ? value : ''}{pct !== null && typeof value === 'number' && value <= 1 ? ' (coverage)' : ''}
          </span>
        </div>
      )}
      {lims.length > 0 && <p className="deliverable-note" style={{ margin: 0 }}>Limits: {lims.slice(0, 3).join(' · ')}</p>}
    </div>
  );
}

function MetricTable({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  const clean = rows.filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== '—');
  if (clean.length === 0) return null;
  return (
    <div className="table-wrap" style={{ marginTop: '0.65rem' }}>
      <table>
        <thead><tr><th style={{ width: '46%' }}>Metric</th><th>Observed (live)</th></tr></thead>
        <tbody>
          {clean.map(([k, v], i) => (
            <tr key={i}><td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{k}</td><td>{v}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="metric-card" style={{ minHeight: '110px' }}>
      <div className="metric-label" style={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.66rem', fontWeight: 700 }}>{label}</div>
      <div className="metric-value" style={tone ? { color: tone } : undefined}>{value}</div>
      {sub && <div className="metric-label" style={{ marginTop: '0.15rem' }}>{sub}</div>}
    </div>
  );
}

const CHART_COLORS = ['#4f5df0', '#0e9fb5', '#7c6cf0', '#f59e0b', '#10b981', '#f43f5e'];

function HealthDonut({ ok, unavail, error }: { ok: number; unavail: number; error: number }) {
  const data = [
    { name: `Verified (${ok})`, value: ok },
    { name: `No data (${unavail})`, value: unavail },
    { name: `Error (${error})`, value: error },
  ].filter((d) => d.value > 0);
  const fills = ['#16a34a', '#f59e0b', '#dc2626'];
  if (data.length === 0) return <p className="deliverable-note">No module status data.</p>;
  return (
    <ResponsiveContainer width="100%" height={210}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} paddingAngle={3} strokeWidth={2}>
          {data.map((_, i) => <Cell key={i} fill={fills[i % fills.length]} />)}
        </Pie>
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: '0.72rem' }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

function SignalsBar({ items }: { items: Array<{ name: string; value: number }> }) {
  const rows = items.filter((d) => typeof d.value === 'number' && !Number.isNaN(d.value)).slice(0, 8);
  if (rows.length === 0) return <p className="deliverable-note">No chartable numeric signals in this run.</p>;
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-14} height={44} />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip />
        <Bar dataKey="value" radius={[6, 6, 0, 0]}>
          {rows.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function linkify(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(https?:\/\/[^\s)"'<>]+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={`t${i++}`}>{text.slice(last, m.index)}</span>);
    const href = m[1].replace(/[.,;:]+$/, '');
    parts.push(<a key={`l${i++}`} href={href} target="_blank" rel="noopener noreferrer" className="inline-link">{href}</a>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(<span key={`e${i++}`}>{text.slice(last)}</span>);
  return parts;
}

function UrlLine({ url, extra }: { url: unknown; extra?: React.ReactNode }) {
  if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) return null;
  let domain = '';
  try { domain = new URL(url).hostname.replace(/^www\./, ''); } catch { domain = url; }
  return (
    <p className="deliverable-linkline">
      <a href={url} target="_blank" rel="noopener noreferrer" className="inline-link">{domain}</a>
      {' · '}<span style={{ color: 'var(--text-muted)', fontSize: '0.72rem', wordBreak: 'break-all' }}>{url.length > 90 ? `${url.slice(0, 90)}…` : url}</span>
      {extra}
    </p>
  );
}

function PdfButton({ brandId, brandName }: { brandId?: number | null; brandName?: string }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState('');
  if (!brandId) return null;
  const download = async () => {
    setBusy(true);
    setErr('');
    try {
      const res = await fetch(`/api/v1/analysis/export/${brandId}?format=pdf`);
      if (!res.ok) throw new Error(`PDF export failed (${res.status})`);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `brand-${brandId}-deliverables.pdf`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
    } catch (e) {
      setErr((e as Error).message || 'PDF download failed.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
      <button type="button" className="info-cta" onClick={download} disabled={busy} style={{ fontSize: '0.85rem', padding: '0.6rem 1.2rem' }}>
        {busy ? <><Loader2 size={15} className="animate-spin" /> Building PDF…</> : <><Download size={15} /> Download full report PDF{brandName ? ` — ${brandName}` : ''}</>}
      </button>
      {err && <span style={{ color: 'var(--danger)', fontSize: '0.78rem' }}>{err}</span>}
    </span>
  );
}

function RunDelta({ brandId }: { brandId?: number | null }) {
  const [delta, setDelta] = useState<any>(null);
  useEffect(() => {
    if (!brandId) return;
    let live = true;
    fetch(`/api/v1/multi-brand/diff?brand_id=${brandId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (live) setDelta(d); })
      .catch(() => {});
    return () => { live = false; };
  }, [brandId]);
  if (!brandId || !delta || delta.status !== 'ok') return null;
  const scores = Object.entries((delta.score_deltas ?? {}) as Record<string, any>);
  const mods = Object.entries((delta.status_deltas ?? {}) as Record<string, any>);
  if (delta.note && scores.length === 0 && mods.length === 0) {
    return (
      <div className="deliverable-block">
        <h3 className="deliverable-title"><Activity size={16} /> Run-over-run delta</h3>
        <p className="deliverable-note" style={{ marginBottom: 0 }}>First recorded run — deltas appear from the second run onward (snapshots auto-saved per run).</p>
      </div>
    );
  }
  return (
    <div className="deliverable-block">
      <h3 className="deliverable-title"><Activity size={16} /> Run-over-run delta{delta.previous_snapshot ? ` · vs ${String(delta.previous_snapshot).slice(0, 19).replace('T', ' ')}` : ''}</h3>
      {scores.length > 0 && (
        <div className="table-wrap" style={{ marginTop: '0.5rem' }}>
          <table>
            <thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Δ</th></tr></thead>
            <tbody>
              {scores.map(([k, v]: any) => (
                <tr key={k}>
                  <td style={{ fontWeight: 600 }}>{k.replace(/_/g, ' ')}</td>
                  <td>{fmt(v.before)}</td><td>{fmt(v.after)}</td>
                  <td style={{ fontWeight: 700, color: Number(v.delta) < 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {Number(v.delta) > 0 ? '+' : ''}{fmt(v.delta)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {mods.length > 0 && (
        <p className="deliverable-note" style={{ marginBottom: 0 }}>
          Module status changes: {mods.slice(0, 8).map(([k, v]: any) => `${k} (${v.before}→${v.after})`).join(' · ')}{mods.length > 8 ? ` · +${mods.length - 8} more` : ''}
        </p>
      )}
      {scores.length === 0 && mods.length === 0 && (
        <p className="deliverable-note" style={{ marginBottom: 0 }}>No changes vs previous run — scores and module mix are stable.</p>
      )}
    </div>
  );
}

export default function Deliverables({ summary, sections, brandId, brandName, brandDomain }: Props) {
  const llm = sections.llm_perception ?? {};
  const cons = sections.consensus ?? {};
  const vec = sections.vector_mapping ?? {};
  const sim = sections.revenue_sim ?? {};
  const unlinked = sections.unlinked_citations ?? {};
  const podcast = sections.podcast_video ?? {};
  const pr = sections.pr_hooks ?? {};
  const dead = sections.dead_equity ?? {};
  const neg = sections.negative_seo ?? {};
  const gh = sections.github_citations ?? {};
  const anchor = sections.anchor_entropy ?? {};
  const ftc = sections.ftc_compliance ?? {};
  const pbn = sections.pbn_detector ?? {};
  const rag = sections.rag_repair ?? {};
  const ragd = sections.rag_defense ?? {};
  const kg = sections.kg_arbitrage ?? {};
  const hreflang = sections.hreflang ?? {};
  const schema = sections.schema_auditor ?? {};
  const aeo = sections.aeo ?? {};

  const isUnavail = (s: any) => s?.status === 'unavailable' || s?.data_status === 'unavailable';
  const avg = typeof vec.avg_cosine_similarity === 'number' ? vec.avg_cosine_similarity : null;
  const vectorIndex = avg !== null ? Math.round(avg * 1000) / 10 : null;

  const brokenPaths = Array.isArray(dead.broken_links)
    ? [...new Set(dead.broken_links.filter((b: any) => typeof b?.url === 'string').map((b: any) => {
      try { return new URL(b.url).pathname || '/'; } catch { return ''; }
    }).filter(Boolean))].slice(0, 20)
    : [];
  const workerScript = `addEventListener('fetch', (e) => {\n  const u = new URL(e.request.url);\n  const map = {\n${brokenPaths.length > 0 ? brokenPaths.map((p) => `    '${p}': '/',  // TODO: point at the semantically closest live URL`).join('\n') : "    // no broken outbound links found in this run"}\n  };\n  const t = map[u.pathname];\n  if (t) return e.respondWith(Response.redirect(new URL(t, u.origin).toString(), 301));\n  return e.respondWith(fetch(e.request));\n});`;

  const manifest = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: brandName || '',
    url: brandDomain ? `https://${brandDomain}` : '',
    identifier: kg.wikidata_id || undefined,
  };

  const allKeys = useMemo(() => Object.keys(sections || {}), [sections]);
  const health = useMemo(() => {
    let ok = 0, un = 0, er = 0;
    for (const k of allKeys) {
      const s: any = (sections as any)[k];
      if (s?.status === 'ok') ok++;
      else if (s?.status === 'unavailable') un++;
      else if (s?.status === 'error') er++;
    }
    return { ok, un, er, total: allKeys.length || 35 };
  }, [sections, allKeys]);

  const signalBars = useMemo(() => {
    const pick: Array<{ name: string; value: number }> = [];
    const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    const sos = num((sections as any)?.revenue_sim?.share_of_search_branded_query);
    const aeoS = num((sections as any)?.aeo?.aeo_score);
    const kgC = num((sections as any)?.kg_arbitrage?.triple_coverage_pct);
    const ent = num((sections as any)?.anchor_entropy?.normalized_entropy);
    const ftcS = num((sections as any)?.ftc_compliance?.ftc_score);
    const vecI = vectorIndex;
    if (sos !== null) pick.push({ name: 'SoS branded %', value: sos });
    if (aeoS !== null) pick.push({ name: 'AEO score', value: aeoS });
    if (kgC !== null) pick.push({ name: 'KG coverage %', value: kgC });
    if (ent !== null) pick.push({ name: 'Anchor entropy ×100', value: Math.round(ent * 1000) / 10 });
    if (ftcS !== null) pick.push({ name: 'FTC score', value: ftcS });
    if (typeof vecI === 'number') pick.push({ name: 'Vector index', value: vecI });
    const hookC = num((sections as any)?.pr_hooks?.hook_count);
    if (hookC !== null) pick.push({ name: 'PR hooks', value: hookC });
    const unlC = num((sections as any)?.unlinked_citations?.unlinked_count);
    if (unlC !== null) pick.push({ name: 'Unlinked', value: unlC });
    return pick;
  }, [sections, vectorIndex]);

  const openRisks = useMemo(() => {
    const ftc: any = (sections as any)?.ftc_compliance ?? {};
    const pbn: any = (sections as any)?.pbn_detector ?? {};
    return (Number(ftc?.total_compliance_issues) || 0) + (Number(pbn?.suspicious_count) || 0);
  }, [sections]);

  const overall = (summary as any)?.overall_score ?? null;
  const entityAuth = (summary as any)?.entity_authority ?? overall;
  const entityGrade = (summary as any)?.entity_grade ?? '';
  const proxySov = (summary as any)?.proxy_sov_free?.proxy_sov ?? null;
  const aeoScore = (sections as any)?.aeo?.aeo_score ?? (summary as any)?.aeo_score ?? null;

  return (
    <div className="deliverables">
      {/* Enterprise report header */}
      <div className="exec-summary" style={{ paddingBottom: '1.25rem' }}>
        <div className="exec-head">
          <div>
            <p style={{ margin: 0, fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.12em', color: 'var(--accent)' }}>OFF-PAGE SEO INTELLIGENCE · 2026 ENTERPRISE REPORT</p>
            <h2 className="section-title" style={{ fontSize: '1.6rem', marginTop: '0.3rem' }}>
              Tool Outputs <span className="gradient-text">— The Deliverables Layer</span>
            </h2>
            <p className="section-sub">
              {brandName ? <strong>{brandName}</strong> : 'Brand'}{brandDomain ? ` · ${brandDomain}` : ''} · every figure below is copied from live module measurements on this page.
              The PDF is generated server-side from the same data — fully formatted with charts, tables and the complete 35-module appendix.
            </p>
          </div>
          <PdfButton brandId={brandId} brandName={brandName} />
        </div>
        <div className="summary-grid" style={{ marginTop: '1.1rem' }}>
          <KpiCard label="Entity Authority (replaces DA)" value={entityAuth !== null && entityAuth !== undefined ? `${entityAuth}${entityGrade ? ` · ${entityGrade}` : ''}` : '—'} sub={`${health.ok} of ${health.total} modules verified · real-data-only`} />
          <KpiCard label="Modules verified" value={`${health.ok}/${health.total}`} sub={`${health.un} no-data · ${health.er} error`} tone={health.er > 0 ? 'var(--danger)' : 'var(--success)'} />
          <KpiCard label="Proxy SoV (free)" value={proxySov !== null ? `${Math.round(Number(proxySov) * 100)}%` : '—'} sub="10-prompt SERP proxy · keyed LLM SoV when keyed" />
          <KpiCard label="AEO / GEO readiness" value={aeoScore !== null && aeoScore !== undefined ? String(aeoScore) : '—'} sub="Machine-readable entity readiness" />
          <KpiCard label="Open risk flags" value={String(openRisks)} sub="FTC issues + PBN suspicious" tone={openRisks > 0 ? 'var(--warning)' : 'var(--success)'} />
        </div>
        <div style={{ marginTop: '1rem' }}>
          <RunDelta brandId={brandId} />
        </div>
        <div className="deliverable-grid2" style={{ marginTop: '1rem' }}>
          <div className="deliverable-block">
            <h3 className="deliverable-title"><Activity size={16} /> Module health — live mix</h3>
            <HealthDonut ok={health.ok} unavail={health.un} error={health.er} />
            <p className="deliverable-note" style={{ textAlign: 'center', marginBottom: 0 }}>Green = verified live · Amber = honest no-data · Red = error. No numbers are fabricated.</p>
          </div>
          <div className="deliverable-block">
            <h3 className="deliverable-title"><BarChart3 size={16} /> Key authority signals — live values</h3>
            <SignalsBar items={signalBars} />
            <p className="deliverable-note" style={{ textAlign: 'center', marginBottom: 0 }}>2026 lens: AI-citation share, AEO readiness, KG coverage, anchor-entropy safety.</p>
          </div>
        </div>
      </div>

      {/* Output 1 — C-Suite Executive Dashboard */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 1 · The C-Suite Executive Dashboard <span>"The Boardroom View" — zero jargon, business impact only</span></h2>
        <div className="deliverable-grid3">
          <Block title="Share of Search (SoS) Revenue Attributor" icon={BarChart3}>
            {isUnavail(sim) ? <Empty label="SoS revenue attributor" requires={sim.requires} /> : (
              <>
                <Takeaway text={sim.executive_takeaway} />
                <MetricTable rows={[
                  ['Branded-query share', <><strong>{fmt(sim.share_of_search_branded_query, '%')}</strong> of top-10 results mention the brand</>],
                  ['Category-query share', fmt(sim.share_of_search_category_query, '%')],
                  ['Revenue projection', sim.revenue_projection == null ? 'Not fabricated — supply a baseline' : fmt(sim.revenue_projection)],
                ]} />
                {Array.isArray(sim.branded_results) && sim.branded_results.length > 0 && (
                  <>
                    <p className="deliverable-note">Branded SERP (top results):</p>
                    {sim.branded_results.slice(0, 5).map((r: any, i: number) => (
                      <p key={i} className="deliverable-linkline">{String(r.title || '').slice(0, 80)} — {r.url ? linkify(String(r.url)) : '—'}</p>
                    ))}
                  </>
                )}
                {sim.revenue_projection == null ? (
                  <p className="deliverable-note"><strong>Revenue projection: not fabricated.</strong> {String(sim.revenue_projection_note || 'Supply a real baseline (annual revenue or deal size) to unlock the monetary forecast.')}</p>
                ) : (
                  <p><strong>Projected pipeline:</strong> {fmt(sim.revenue_projection)}</p>
                )}
                <Conf value={sim.confidence} limitations={sim.limitations} />
                {sim.sources?.length > 0 && <p className="deliverable-note">{sim.sources.length} verified SERP sources · method: {String(sim.method || '')}</p>}
              </>
            )}
          </Block>

          <Block title="LLM Citation Share-of-Voice Matrix" icon={Brain}>
            {!isUnavail(llm) ? (
              <>
                <Takeaway text={llm.executive_takeaway} />
                <p><strong>Citation rate:</strong> {fmt(llm.citation_rate, '%')} of AI-assistant answers cited verified brand sources.</p>
                <p><strong>Questions tested:</strong> {fmt(llm.answered)} of {fmt(llm.total_questions)} answered by live LLM output.</p>
                {Array.isArray(llm.llm_answers) && llm.llm_answers.length > 0 && (
                  <ul className="deliverable-list">
                    {llm.llm_answers.slice(0, 5).map((a: any, i: number) => (
                      <li key={i}>{String(a.question)} — {String(a.model ?? 'model')}</li>
                    ))}
                  </ul>
                )}
                <Conf value={llm.confidence} limitations={llm.limitations} />
              </>
            ) : !isUnavail(cons) ? (
              <>
                <p className="deliverable-note"><strong>LLM answers need a provider key ({String(llm.requires || 'OPENAI/ANTHROPIC/PERPLEXITY')}) — showing the live web-consensus fallback instead (no estimates).</strong></p>
                <Takeaway text={cons.executive_takeaway} />
                <p><strong>Overall web sentiment:</strong> {fmt(cons.overall_sentiment_score)} · <strong>Mentions scored:</strong> {fmt((cons.mentions || []).length)}</p>
                {cons.sentiment_distribution && (
                  <p>Distribution — positive {fmt((cons.sentiment_distribution as any).positive)}, negative {fmt((cons.sentiment_distribution as any).negative)}, neutral {fmt((cons.sentiment_distribution as any).neutral)}</p>
                )}
                {!cons.sentiment_available && <p className="deliverable-note">Model-scored sentiment also needs an LLM key; counts above are live mentions, not sentiment guesses.</p>}
                <Conf value={cons.confidence} limitations={cons.limitations} />
              </>
            ) : <Empty label="LLM citation share-of-voice" requires={llm.requires} />}
          </Block>

          <Block title="Topical Vector Distance Index (0–100)" icon={Network}>
            {isUnavail(vec) ? <Empty label="Vector distance index" requires={vec.requires} /> : (
              <>
                <Takeaway text={vec.executive_takeaway} />
                <MetricTable rows={[
                  ['Brand vector index', vectorIndex !== null ? <><span className="stat-strong">{vectorIndex} / 100</span> (avg cosine {fmt(avg)})</> : '—'],
                  ['Corpus', `${fmt(vec.brand_texts_embedded)} brand texts vs ${fmt(vec.competitors_embedded)} competitor texts`],
                  ['Method', String(vec.method || '—')],
                ]} />
                {Array.isArray(vec.competitor_distances) && vec.competitor_distances.length > 0 && (
                  <ul className="deliverable-list">
                    {vec.competitor_distances.slice(0, 6).map((p: any, i: number) => (
                      <li key={i}>{String(p.competitor)} · cosine {fmt(p.cosine_similarity)} → index {typeof p.cosine_similarity === 'number' ? Math.round(p.cosine_similarity * 1000) / 10 : '—'}</li>
                    ))}
                  </ul>
                )}
                <Conf value={vec.confidence} limitations={vec.limitations} />
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 2 — Human-in-the-Loop Action & Outreach Queues */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 2 · Human-in-the-Loop Action &amp; Outreach Queues <span>co-pilot, never auto-blast</span></h2>
        <div className="deliverable-grid3">
          <Block title="Predictive PR & Data-Hook Pitches" icon={PenTool}>
            {isUnavail(pr) || !pr.hook_count ? <Empty label="PR data-hook pitches" requires={pr.requires} /> : (
              <>
                <Takeaway text={pr.executive_takeaway} />
                <p><strong>{fmt(pr.hook_count)}</strong> hooks from <strong>{fmt(pr.total_articles_scanned)}</strong> last-14-days articles ({fmt(pr.brand_mentions_in_news)} brand mentions).</p>
                {Array.isArray(pr.hooks) && pr.hooks.slice(0, 8).map((h: any, i: number) => (
                  <div key={i} style={{ marginTop: '0.7rem', paddingTop: '0.7rem', borderTop: '1px dashed var(--border-color)' }}>
                    <p><strong>{String(h.title ?? '')}</strong></p>
                    {h.angle && <p className="deliverable-note">{String(h.angle)}</p>}
                    {h.target_outlet && <p className="deliverable-note">Target: {String(h.target_outlet)}{h.verified ? ' · verified outlet' : ''}</p>}
                    {h.source_url && <UrlLine url={h.source_url} />}
                    {Array.isArray(h.source_articles) && h.source_articles.slice(0, 3).map((u: any, j: number) => <UrlLine key={j} url={u} />)}
                  </div>
                ))}
                <Conf value={pr.confidence} limitations={pr.limitations} />
              </>
            )}
          </Block>

          <Block title="Unlinked Mention & Citation Conversion Deck" icon={Link2}>
            {isUnavail(unlinked) || !unlinked.total_mentions_found ? <Empty label="Unlinked mention deck" requires={unlinked.requires} /> : (
              <>
                <Takeaway text={unlinked.executive_takeaway} />
                <p><strong>{fmt(unlinked.unlinked_count)}</strong> unlinked of {fmt(unlinked.examined)} examined ({fmt(unlinked.linked_count)} already linked · conversion {fmt(unlinked.conversion_rate, '%')}).</p>
                {Array.isArray(unlinked.mentions) && unlinked.mentions.filter((m: any) => m.links_to_brand === false).slice(0, 8).map((m: any, i: number) => (
                  <div key={i} style={{ marginTop: '0.6rem', paddingTop: '0.6rem', borderTop: '1px dashed var(--border-color)' }}>
                    <p><strong>{String(m.title || m.domain || '')}</strong> <em>({String(m.domain || '')})</em></p>
                    {m.snippet && <p className="deliverable-note">{String(m.snippet).slice(0, 220)}</p>}
                    <UrlLine url={m.url} extra={typeof m.relevance_score === 'number' ? <em> · relevance {m.relevance_score}</em> : undefined} />
                  </div>
                ))}
                <Conf value={unlinked.confidence} limitations={unlinked.limitations} />
              </>
            )}
          </Block>

          <Block title="Podcast & Video Transcript Pitch Packs" icon={Mic}>
            {isUnavail(podcast) || !podcast.opportunity_count ? <Empty label="Podcast pitch packs" requires={podcast.requires} /> : (
              <>
                <Takeaway text={podcast.executive_takeaway} />
                <p><strong>{fmt(podcast.opportunity_count)}</strong> real pages across {fmt(podcast.unique_platforms)} platform(s){Array.isArray(podcast.platforms) && podcast.platforms.length > 0 ? `: ${podcast.platforms.join(', ')}` : ''}.</p>
                {Array.isArray(podcast.mentions) && podcast.mentions.slice(0, 8).map((m: any, i: number) => (
                  <div key={i} style={{ marginTop: '0.6rem', paddingTop: '0.6rem', borderTop: '1px dashed var(--border-color)' }}>
                    <p><strong>{String(m.title || '').slice(0, 100)}</strong></p>
                    {m.snippet && <p className="deliverable-note">{String(m.snippet).slice(0, 160)}</p>}
                    <UrlLine url={m.url} />
                  </div>
                ))}
                <Conf value={podcast.confidence} limitations={podcast.limitations} />
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 3 — Edge-Network & Technical Execution Rules */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 3 · Edge-Network &amp; Technical Execution Rules <span>copy-paste payloads for DevOps</span></h2>
        <div className="deliverable-grid3">
          <Block title="Serverless Edge Redirect Payloads" icon={Server}>
            {isUnavail(dead) || !dead.broken_count ? <Empty label="Edge redirect payloads" requires={dead.requires} /> : (
              <>
                <Takeaway text={dead.executive_takeaway} />
                <p><strong>{fmt(dead.broken_count)}</strong> broken · {fmt(dead.healthy_count)} healthy · {fmt(dead.redirect_count)} redirected, of {fmt(dead.outbound_links_checked)} outbound links checked live.</p>
                {Array.isArray(dead.broken_links) && dead.broken_links.filter(Boolean).slice(0, 5).map((b: any, i: number) => (
                  <p key={i} className="deliverable-linkline">→ {b.url ? linkify(String(b.url)) : '—'} <em>(HTTP {fmt(b.status)})</em></p>
                ))}
                {Array.isArray(dead.redirected_links) && dead.redirected_links.length > 0 && (
                  <p className="deliverable-note">Already redirecting: {dead.redirected_links.slice(0, 3).map((r: any) => String(r.url || '')).join(', ')}</p>
                )}
                <p className="deliverable-note">Cloudflare Worker generated from the REAL broken paths above — replace each '/' target with the semantically closest live URL, then deploy:</p>
                <pre className="deliverable-code">{workerScript}</pre>
                <Conf value={dead.confidence} limitations={dead.limitations} />
              </>
            )}
          </Block>

          <Block title="Active Anti-Scrape & Canonical Shield Headers" icon={ShieldCheck}>
            {isUnavail(neg) ? <Empty label="Anti-scrape shield" requires={neg.requires} /> : (
              <>
                <Takeaway text={neg.executive_takeaway} />
                <p><strong>{fmt(neg.negative_mention_count)}</strong> pages surfaced by brand + risk-term queries{Array.isArray(neg.risk_terms) && neg.risk_terms.length > 0 ? ` (${neg.risk_terms.join(', ')})` : ''}.</p>
                {Array.isArray(neg.negative_mentions) && neg.negative_mentions.slice(0, 4).map((m: any, i: number) => (
                  <p key={i} className="deliverable-linkline">{m.url ? linkify(String(m.url)) : String(m.title || '')}</p>
                ))}
                <pre className="deliverable-code">{`# Deploy at edge on scraped/param URLs\nX-Robots-Tag: noindex, nofollow\nLink: <https://${brandDomain || 'brand.com'}/>; rel="canonical"`}</pre>
                <Conf value={neg.confidence} limitations={neg.limitations} />
              </>
            )}
          </Block>

          <Block title="Developer Ecosystem Pull-Requests" icon={FileCode2}>
            {isUnavail(gh) || !gh.github_references ? <Empty label="GitHub attribution PRs" requires={gh.requires} /> : (
              <>
                <Takeaway text={gh.executive_takeaway} />
                <p><strong>{fmt(gh.github_references)}</strong> live GitHub/Stack Overflow/HN references.</p>
                {Array.isArray(gh.references) && gh.references.slice(0, 6).map((m: any, i: number) => (
                  <div key={i} style={{ marginTop: '0.5rem' }}>
                    <p><strong>{String(m.title || '').slice(0, 90)}</strong> <em>({String(m.domain || '')})</em></p>
                    {m.snippet && <p className="deliverable-note">{String(m.snippet).slice(0, 160)}</p>}
                    <UrlLine url={m.url} />
                  </div>
                ))}
                <p className="deliverable-note">Attribution markdown for PR bodies:</p>
                <pre className="deliverable-code">{`[${brandName || 'Brand'}](https://${brandDomain || 'brand.com'})`}</pre>
                <Conf value={gh.confidence} limitations={gh.limitations} />
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 4 — Algorithmic Defense & Compliance Risk Register */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 4 · Algorithmic Defense &amp; Compliance Risk Register <span>keeps legal + SpamBrain happy</span></h2>
        <div className="deliverable-grid3">
          <Block title="Neural Anchor Entropy Radar" icon={Hash}>
            {isUnavail(anchor) ? <Empty label="Anchor entropy radar" requires={anchor.requires} /> : (
              <>
                <Takeaway text={anchor.executive_takeaway} />
                <MetricTable rows={[
                  ['Normalized entropy', <>{fmt(anchor.normalized_entropy)} <span style={{ color: 'var(--text-muted)' }}>(1.0 = fully natural · raw {fmt(anchor.entropy)})</span></>],
                  ['Anchor pool', `${fmt(anchor.unique_anchors)} unique of ${fmt(anchor.total_anchors)}`],
                  ['Branded share', fmt(anchor.branded_pct, '%')],
                ]} />
                {Array.isArray(anchor.top_anchors) && anchor.top_anchors.length > 0 && (
                  <ul className="deliverable-list">
                    {anchor.top_anchors.slice(0, 8).map((a: any, i: number) => (
                      <li key={i}>"{String(a.anchor || '').slice(0, 70)}" × {fmt(a.count)}</li>
                    ))}
                  </ul>
                )}
                <Conf value={anchor.confidence} limitations={anchor.limitations} />
              </>
            )}
          </Block>

          <Block title="FTC & Sponsored-Link Compliance Alerts" icon={Gauge}>
            {isUnavail(ftc) ? <Empty label="FTC compliance alerts" requires={ftc.requires} /> : (
              <>
                <Takeaway text={ftc.executive_takeaway} />
                <MetricTable rows={[
                  ['Sponsored items found', fmt(ftc.total_sponsored_content)],
                  ['Open compliance issues', fmt(ftc.total_compliance_issues)],
                  ['FTC safety score', fmt(ftc.ftc_score)],
                ]} />
                {Array.isArray(ftc.sponsored_mentions) && ftc.sponsored_mentions.slice(0, 6).map((m: any, i: number) => (
                  <p key={i} className="deliverable-linkline">
                    {String(m.title || m.domain || '').slice(0, 80)} — disclosure: <strong>{m.has_disclosure ? 'yes' : 'MISSING'}</strong>
                    <br />{m.url ? linkify(String(m.url)) : null}
                  </p>
                ))}
                {Array.isArray(ftc.compliance_issues) && ftc.compliance_issues.length > 0 ? (
                  <ul className="deliverable-list">
                    {ftc.compliance_issues.slice(0, 8).map((x: any, i: number) => (
                      <li key={i}>{linkify(String(x.url ?? x))}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="deliverable-note"><strong>Zero open compliance issues</strong> in the live window — that is a measured result, not an assumption.</p>
                )}
                <Conf value={ftc.confidence} limitations={ftc.limitations} />
              </>
            )}
          </Block>

          <Block title="Synthetic Network & PBN Red-Flags" icon={Fingerprint}>
            {isUnavail(pbn) ? <Empty label="PBN forensic red-flags" requires={pbn.requires} /> : (
              <>
                <Takeaway text={pbn.executive_takeaway} />
                <p><strong>{fmt(pbn.suspicious_count)}</strong> suspicious of {fmt(pbn.total_backlinks)} backlinks (sponsored {fmt(pbn.sponsored_count)} · UGC {fmt(pbn.ugc_count)} · generic anchors {fmt(pbn.generic_anchor_count)}).</p>
                {pbn.registration_footprint && (
                  <p className="deliverable-note">RDAP: {String(pbn.registration_footprint.registrar || '')} · registered {String(pbn.registration_footprint.registered || pbn.registration_footprint.created || '')} · age {fmt(pbn.registration_footprint.domain_age_years)}y · expiry {String(pbn.registration_footprint.expiration || '')}</p>
                )}
                {Array.isArray(pbn.repeated_source_domains) && pbn.repeated_source_domains.length > 0 && (
                  <p className="deliverable-note">Repeated source domains: {pbn.repeated_source_domains.slice(0, 6).join(', ')}</p>
                )}
                <Conf value={pbn.confidence} limitations={pbn.limitations} />
              </>
            )}
          </Block>

          <Block title="RAG Hallucination & Cache-Purge Alerts" icon={Bug}>
            {!isUnavail(rag) ? (
              <>
                <Takeaway text={rag.executive_takeaway} />
                <p><strong>{fmt((rag as any).hallucination_count)}</strong> of {fmt((rag as any).tests_run)} LLM answers failed brand verification ({fmt((rag as any).hallucination_rate, '%')}).</p>
                {Array.isArray((rag as any).tests) && (rag as any).tests.filter((t: any) => t.likely_hallucination).slice(0, 5).map((t: any, i: number) => (
                  <p key={i} className="deliverable-linkline">Q: {String(t.question)}</p>
                ))}
                <Conf value={rag.confidence} limitations={rag.limitations} />
              </>
            ) : !isUnavail(ragd) ? (
              <>
                <p className="deliverable-note"><strong>LLM-answer testing needs a provider key ({String(rag.requires || 'OPENAI/ANTHROPIC/PERPLEXITY')}) — showing the live RAG-cache freshness probe instead.</strong></p>
                <Takeaway text={ragd.executive_takeaway} />
                <p><strong>Freshness:</strong> {fmt(ragd.freshness_rate, '%')} · <strong>Stale caches:</strong> {fmt(ragd.stale_caches_detected)} of {fmt(ragd.total_results_checked)} results checked.</p>
                {Array.isArray(ragd.stale_indicators_used) && <p className="deliverable-note">Stale signals scanned: {ragd.stale_indicators_used.slice(0, 8).join(', ')}</p>}
                <Conf value={ragd.confidence} limitations={ragd.limitations} />
              </>
            ) : <Empty label="RAG hallucination alerts" requires={rag.requires} />}
          </Block>
        </div>
      </div>

      {/* Output 5 — Global Entity & Knowledge Graph Blueprint */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 5 · Global Entity &amp; Knowledge Graph Blueprint <span>for the entity owner</span></h2>
        <div className="deliverable-grid3">
          <Block title="Wikidata & Triple Gap Report" icon={Database}>
            {isUnavail(kg) ? <Empty label="Wikidata triple gaps" requires={kg.requires} /> : (
              <>
                <Takeaway text={kg.executive_takeaway} />
                <p><strong>Triple coverage:</strong> {fmt(kg.triple_coverage_pct, '%')} · <strong>{String(kg.wikidata_label || '')}</strong> (<a className="inline-link" href={`https://www.wikidata.org/wiki/${String(kg.wikidata_id || '')}`} target="_blank" rel="noopener noreferrer">{String(kg.wikidata_id || '')}</a>) · sitelinks {fmt((kg.sitelinks || {}).count)} ({Array.isArray((kg.sitelinks || {}).languages) ? (kg.sitelinks.languages as string[]).join(', ') : ''})</p>
                {kg.wikipedia_url && <UrlLine url={kg.wikipedia_url} />}
                {kg.present_triples && (
                  <p className="deliverable-note">Present: {Object.entries(kg.present_triples).slice(0, 6).map(([k, v]: any) => `${String(v.label || k)}`).join(' · ')}</p>
                )}
                {Array.isArray(kg.missing_triples) && kg.missing_triples.length > 0 && (
                  <ul className="deliverable-list">
                    {kg.missing_triples.slice(0, 6).map((t: any, i: number) => (
                      <li key={i}>Missing: <strong>{String(t.property ?? '')}</strong> · {String(t.label ?? '')} — needs a cited Wikidata edit</li>
                    ))}
                  </ul>
                )}
                {Array.isArray(kg.competitor_monitor) && kg.competitor_monitor.length > 0 && (
                  <ul className="deliverable-list">
                    {kg.competitor_monitor.slice(0, 5).map((c: any, i: number) => (
                      <li key={i}>{String(c.name)} ({String(c.domain)}) · {String(c.wikidata_id)}</li>
                    ))}
                  </ul>
                )}
                <Conf value={kg.confidence} limitations={kg.limitations} />
              </>
            )}
          </Block>

          <Block title="Multi-Regional Hreflang Equity Balancer" icon={Globe}>
            {isUnavail(hreflang) ? <Empty label="Hreflang equity balancer" requires={hreflang.requires} /> : (
              <>
                <Takeaway text={hreflang.executive_takeaway} />
                <p><strong>Hreflang tags:</strong> {fmt((hreflang.hreflang_tags || []).length)} · <strong>Cannibalization risk:</strong> {fmt(hreflang.cannibalization_risk)} · <strong>Readiness:</strong> {fmt(hreflang.international_readiness_score)}</p>
                {Array.isArray(hreflang.international_versions) && hreflang.international_versions.length > 0 && (
                  <ul className="deliverable-list">{hreflang.international_versions.slice(0, 6).map((x: any, i: number) => <li key={i}>{linkify(String(x))}</li>)}</ul>
                )}
                {Array.isArray(hreflang.international_links) && hreflang.international_links.length > 0 && (
                  <ul className="deliverable-list">{hreflang.international_links.slice(0, 6).map((x: any, i: number) => <li key={i}>{linkify(String(x))}</li>)}</ul>
                )}
                {(!hreflang.international_versions || hreflang.international_versions.length === 0) && (!hreflang.international_links || hreflang.international_links.length === 0) && (
                  <p className="deliverable-note">No international versions detected on the live crawl — single-locale footprint.</p>
                )}
                <Conf value={hreflang.confidence} limitations={hreflang.limitations} />
              </>
            )}
          </Block>

          <Block title="Machine-to-Machine (AEO) Protocol Manifest" icon={Handshake}>
            {isUnavail(schema) && isUnavail(aeo) ? <Empty label="AEO protocol manifests" /> : (
              <>
                <Takeaway text={aeo.executive_takeaway || schema.executive_takeaway} />
                <p><strong>Schema score:</strong> {fmt(schema.schema_score)} (JSON-LD {fmt(schema.jsonld_count)} · OG {fmt(schema.opengraph_count)} · Twitter {fmt(schema.twitter_card_count)}) · <strong>AEO score:</strong> {fmt(aeo.aeo_score)}</p>
                <p className="deliverable-note">Probes — llms.txt {String(aeo.llms_txt ?? '—')} · robots {String(aeo.robots_txt ?? '—')} · sitemap {String(aeo.sitemap ?? '—')} · AI plugin {String(aeo.ai_plugin_json ?? '—')}</p>
                {Array.isArray(schema.machine_readable_endpoints) && schema.machine_readable_endpoints.length > 0 && (
                  <ul className="deliverable-list">
                    {schema.machine_readable_endpoints.slice(0, 6).map((e: any, i: number) => (
                      <li key={i}>{String(e.path)} → HTTP {fmt(e.status)} <em>({String(e.content_type || '')})</em></li>
                    ))}
                  </ul>
                )}
                <p className="deliverable-note">Drop-in JSON-LD manifest (real brand fields only):</p>
                <pre className="deliverable-code">{JSON.stringify(manifest, null, 2)}</pre>
                <Conf value={aeo.confidence ?? schema.confidence} limitations={aeo.limitations || schema.limitations} />
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Module coverage matrix — all features / functions at a glance */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Appendix · All-module coverage <span>{health.ok} verified · {health.un} no-data · {health.er} error — full functions &amp; sub-functions ship in the PDF Appendix A</span></h2>
        <div className="deliverable-block">
          <div className="table-wrap">
            <table>
              <thead><tr><th style={{ width: '44px' }}>#</th><th>Module / feature</th><th style={{ width: '110px' }}>Status</th><th>Assessment / function signal</th><th style={{ width: '90px' }}>Findings</th></tr></thead>
              <tbody>
                {allKeys.sort().map((k, i) => {
                  const m: any = (sections as any)[k];
                  const st = String(m?.status ?? '—');
                  const badge = st === 'ok' ? 'low' : st === 'unavailable' ? 'high' : st === 'error' ? 'critical' : 'medium';
                  const fcount = Array.isArray(m?.findings) ? m.findings.length : 0;
                  return (
                    <tr key={k}>
                      <td style={{ color: 'var(--text-muted)', fontWeight: 700 }}>{i + 1}</td>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{String(m?.feature_name || k).slice(0, 60)}</td>
                      <td><span className={`status-badge ${badge}`} style={{ fontSize: '0.66rem' }}>{st === 'ok' ? 'Verified' : st}</span></td>
                      <td style={{ fontSize: '0.78rem' }}>{String(m?.assessment || m?.executive_takeaway || '—').slice(0, 110)}</td>
                      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{fcount}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="deliverable-note" style={{ marginBottom: 0, display: 'flex', gap: '0.45rem', alignItems: 'flex-start' }}>
            <FileText size={13} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>Per-module deep dives (evidence tables, recommendations, actions, limitations, verified sources) live in the “All 35 Modules” tab and in full inside the downloaded PDF — cover, charts, all 5 outputs, Appendix A (35 modules) and Appendix B (methodology + source library).</span>
          </p>
        </div>
      </div>

      <div className="deliverable-block" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <p className="deliverable-note" style={{ margin: 0, display: 'flex', gap: '0.45rem', alignItems: 'center' }}>
          {health.er > 0 ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
          Need this offline? The enterprise PDF contains the cover, KPI cards, charts, all 5 outputs, all 35 modules and the verified source library.
        </p>
        <PdfButton brandId={brandId} brandName={brandName} />
      </div>
    </div>
  );
}
