import React from 'react';
import {
  BarChart3, Brain, Network, PenTool, Link2, Mic, Server, ShieldAlert,
  ShieldCheck, Fingerprint, Bug, Database, Globe, FileCode2, Handshake, Gauge, Hash,
} from 'lucide-react';

interface Props {
  summary: Record<string, any>;
  sections: Record<string, any>;
}

function fmt(v: unknown, unit = ''): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return `${v % 1 === 0 ? v.toLocaleString() : v.toFixed(2)}${unit}`;
  return String(v);
}

function Empty({ label }: { label: string }) {
  return (
    <div className="deliverable-empty">
      <ShieldAlert size={14} />
      <span>{label} — no verified data was produced. No numbers are fabricated.</span>
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

export default function Deliverables({ summary: _summary, sections }: Props) {
  const llm = sections.llm_perception ?? {};
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
  const kg = sections.kg_arbitrage ?? {};
  const hreflang = sections.hreflang ?? {};
  const schema = sections.schema_auditor ?? {};
  const aeo = sections.aeo ?? {};

  const isUnavail = (s: any) => s?.status === 'unavailable' || s?.data_status === 'unavailable';

  return (
    <div className="deliverables">
      {/* Output 1 — C-Suite Executive Dashboard */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 1 · The C-Suite Executive Dashboard <span>"The Boardroom View"</span></h2>
        <div className="deliverable-grid3">
          <Block title="Share of Search (SoS) Revenue Attributor" icon={BarChart3}>
            {isUnavail(sim) ? <Empty label="SoS revenue attributor" /> : (
              <>
                <p><strong>Branded-query share of search:</strong> {fmt(sim.share_of_search_branded_query, '%')} of the top-10 SERP results mention the brand.</p>
                <p><strong>Category-query share of search:</strong> {fmt(sim.share_of_search_category_query, '%')}</p>
                {sim.revenue_projection == null ? (
                  <Empty label="Revenue projection" />
                ) : (
                  <p><strong>Projected pipeline:</strong> {fmt(sim.revenue_projection)}</p>
                )}
                {sim.revenue_projection_note && <p className="deliverable-note">{linkify(String(sim.revenue_projection_note))}</p>}
              </>
            )}
          </Block>

          <Block title="LLM Citation Share-of-Voice Matrix" icon={Brain}>
            {isUnavail(llm) ? <Empty label="LLM citation share-of-voice" /> : (
              <>
                <p><strong>Citation rate:</strong> {fmt(llm.citation_rate, '%')} of AI-assistant answers cited verified brand sources.</p>
                <p><strong>Questions tested:</strong> {fmt(llm.answered)} of {fmt(llm.total_questions)} answered by live LLM output.</p>
                {Array.isArray(llm.llm_answers) && llm.llm_answers.length > 0 && (
                  <ul className="deliverable-list">
                    {llm.llm_answers.slice(0, 5).map((a: any, i: number) => (
                      <li key={i}>{String(a.question)} — {String(a.model ?? 'model')}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Block>

          <Block title="Topical Vector Distance Index" icon={Network}>
            {isUnavail(vec) ? <Empty label="Vector distance index" /> : (
              <>
                <p><strong>Avg cosine similarity vs competitors:</strong> {fmt(vec.avg_cosine_similarity)}</p>
                {Array.isArray(vec.competitor_distances) && vec.competitor_distances.length > 0 && (
                  <ul className="deliverable-list">
                    {vec.competitor_distances.slice(0, 6).map((p: any, i: number) => (
                      <li key={i}>{String(p.competitor)} · {fmt(p.cosine_similarity)}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 2 — Human-in-the-Loop Action & Outreach Queues */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 2 · Human-in-the-Loop Action &amp; Outreach Queues</h2>
        <div className="deliverable-grid3">
          <Block title="Predictive PR & Data-Hook Pitches" icon={PenTool}>
            {isUnavail(pr) || !pr.hook_count ? <Empty label="PR data-hook pitches" /> : (
              <ul className="deliverable-list">
                {Array.isArray(pr.hooks) && pr.hooks.slice(0, 8).map((h: any, i: number) => (
                  <li key={i}>{linkify(String(h.title ?? h.pitch ?? JSON.stringify(h)))}</li>
                ))}
              </ul>
            )}
          </Block>

          <Block title="Unlinked Mention & Citation Conversion Deck" icon={Link2}>
            {isUnavail(unlinked) || !unlinked.total_mentions_found ? <Empty label="Unlinked mention deck" /> : (
              <>
                <p><strong>{fmt(unlinked.unlinked_count)}</strong> unlinked of {fmt(unlinked.examined)} examined pages ({fmt(unlinked.conversion_rate, '%')} linked).</p>
                {Array.isArray(unlinked.mentions) && unlinked.mentions.filter((m: any) => m.links_to_brand === false).slice(0, 8).map((m: any, i: number) => (
                  <p key={i} className="deliverable-linkline">{linkify(String(m.url))}</p>
                ))}
              </>
            )}
          </Block>

          <Block title="Podcast & Video Transcript Pitch Packs" icon={Mic}>
            {isUnavail(podcast) || !podcast.opportunity_count ? <Empty label="Podcast pitch packs" /> : (
              <>
                <p><strong>{fmt(podcast.opportunity_count)}</strong> real podcast/video pages across {fmt(podcast.unique_platforms)} platforms.</p>
                {Array.isArray(podcast.mentions) && podcast.mentions.slice(0, 8).map((m: any, i: number) => (
                  <p key={i} className="deliverable-linkline">{linkify(String(m.url))}</p>
                ))}
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 3 — Edge-Network & Technical Execution Rules */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 3 · Edge-Network &amp; Technical Execution Rules</h2>
        <div className="deliverable-grid3">
          <Block title="Serverless Edge Redirect Payloads (dead-equity salvage)" icon={Server}>
            {isUnavail(dead) || !dead.broken_count ? <Empty label="Edge redirect payloads" /> : (
              <>
                <p><strong>{fmt(dead.broken_count)}</strong> broken outbound links on the brand site recoverable via 301s.</p>
                {Array.isArray(dead.broken_links) && dead.broken_links.filter(Boolean).slice(0, 5).map((b: any, i: number) => (
                  <p key={i} className="deliverable-linkline">→ {linkify(String(b.url))} <em>(HTTP {fmt(b.status)})</em></p>
                ))}
                <pre className="deliverable-code">{`addEventListener('fetch', e => {\n  const u = new URL(e.request.url);\n  const map = {\n    '/old-path': '/new-page', // map each dead URL to its semantic 2026 target\n  };\n  if (map[u.pathname]) return e.respondWith(Response.redirect(map[u.pathname], 301));\n});`}</pre>
              </>
            )}
          </Block>

          <Block title="Active Anti-Scrape & Canonical Shield Headers" icon={ShieldCheck}>
            {isUnavail(neg) ? <Empty label="Anti-scrape shield" /> : (
              <>
                <p><strong>{fmt(neg.negative_mention_count)}</strong> pages surfaced by brand + risk-term queries.</p>
                <pre className="deliverable-code">{`# Deploy at edge on scraped/param URLs\nX-Robots-Tag: noindex, nofollow\nLink: <https://brand.com/canonical>; rel="canonical"`}</pre>
              </>
            )}
          </Block>

          <Block title="Developer Ecosystem Pull-Requests (GitHub)" icon={FileCode2}>
            {isUnavail(gh) || !gh.github_references ? <Empty label="GitHub attribution PRs" /> : (
              <>
                <p><strong>{fmt(gh.github_references)}</strong> GitHub/Stack Overflow references found via live search.</p>
                {Array.isArray(gh.references) && gh.references.slice(0, 6).map((m: any, i: number) => (
                  <p key={i} className="deliverable-linkline">{linkify(String(m.url ?? ''))}</p>
                ))}
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 4 — Algorithmic Defense & Compliance Risk Register */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 4 · Algorithmic Defense &amp; Compliance Risk Register</h2>
        <div className="deliverable-grid3">
          <Block title="Neural Anchor Entropy & Over-Optimization Radar" icon={Hash}>
            {isUnavail(anchor) ? <Empty label="Anchor entropy radar" /> : (
              <>
                <p><strong>Normalized anchor entropy:</strong> {fmt(anchor.normalized_entropy)} (higher = more natural)</p>
                <p><strong>Unique anchors:</strong> {fmt(anchor.unique_anchors)} · <strong>Branded share:</strong> {fmt(anchor.branded_pct, '%')}</p>
              </>
            )}
          </Block>

          <Block title="FTC & Sponsored-Link Compliance Alerts" icon={Gauge}>
            {isUnavail(ftc) ? <Empty label="FTC compliance alerts" /> : (
              <>
                <p><strong>Sponsored content found:</strong> {fmt(ftc.total_sponsored_content)} · <strong>Compliance issues:</strong> {fmt(ftc.total_compliance_issues)} · <strong>FTC score:</strong> {fmt(ftc.ftc_score)}</p>
                {Array.isArray(ftc.compliance_issues) && ftc.compliance_issues.length > 0 ? (
                  <ul className="deliverable-list">
                    {ftc.compliance_issues.slice(0, 8).map((x: any, i: number) => (
                      <li key={i}>{linkify(String(x.url ?? x))}</li>
                    ))}
                  </ul>
                ) : (
                  <Empty label="FTC compliance issues" />
                )}
              </>
            )}
          </Block>

          <Block title="Synthetic Network & PBN Forensic Red-Flags" icon={Fingerprint}>
            {isUnavail(pbn) ? <Empty label="PBN forensic red-flags" /> : (
              <p><strong>{fmt(pbn.suspicious_count)}</strong> suspicious nodes flagged by the footprint detector.</p>
            )}
          </Block>

          <Block title="RAG Hallucination & Cache-Purge Alerts" icon={Bug}>
            {isUnavail(rag) ? <Empty label="RAG hallucination alerts" /> : (
              <>
                <p><strong>{fmt(rag.hallucination_count)}</strong> of {fmt(rag.tests_run)} LLM answers cited sources that failed brand verification ({fmt(rag.hallucination_rate, '%')}).</p>
                {Array.isArray(rag.tests) && rag.tests.filter((t: any) => t.likely_hallucination).slice(0, 5).map((t: any, i: number) => (
                  <p key={i} className="deliverable-linkline">Q: {String(t.question)}</p>
                ))}
              </>
            )}
          </Block>
        </div>
      </div>

      {/* Output 5 — Global Entity & Knowledge Graph Blueprint */}
      <div className="deliverable-group">
        <h2 className="deliverable-group-title">Output 5 · Global Entity &amp; Knowledge Graph Blueprint</h2>
        <div className="deliverable-grid3">
          <Block title="Wikidata & Triple Gap Reports" icon={Database}>
            {isUnavail(kg) ? <Empty label="Wikidata triple gaps" /> : (
              <>
                <p><strong>Triple coverage:</strong> {fmt(kg.triple_coverage_pct, '%')} of the brand's entity graph nodes connected.</p>
                {Array.isArray(kg.missing_triples) && kg.missing_triples.length > 0 && (
                  <ul className="deliverable-list">
                    {kg.missing_triples.slice(0, 6).map((t: any, i: number) => (
                      <li key={i}>{String(t.property ?? '')} · {String(t.label ?? '')}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Block>

          <Block title="Multi-Regional Hreflang Equity Balancer" icon={Globe}>
            {isUnavail(hreflang) ? <Empty label="Hreflang equity balancer" /> : (
              <>
                <p><strong>Hreflang tags found:</strong> {fmt(hreflang.hreflang_tags?.length)} · <strong>Cannibalization risk:</strong> {fmt(hreflang.cannibalization_risk)}</p>
                {Array.isArray(hreflang.international_links) && hreflang.international_links.length > 0 && (
                  <ul className="deliverable-list">
                    {hreflang.international_links.slice(0, 6).map((x: any, i: number) => <li key={i}>{linkify(String(x))}</li>)}
                  </ul>
                )}
              </>
            )}
          </Block>

          <Block title="Machine-to-Machine (AEO) Protocol Manifests" icon={Handshake}>
            {isUnavail(schema) && isUnavail(aeo) ? <Empty label="AEO protocol manifests" /> : (
              <>
                <p><strong>Schema score:</strong> {fmt(schema.schema_score)} · <strong>AEO score:</strong> {fmt(aeo.aeo_score)}</p>
                {Array.isArray(schema.schema_checks) && schema.schema_checks.length > 0 && (
                  <pre className="deliverable-code">{JSON.stringify(schema.schema_checks.slice(0, 5), null, 2)}</pre>
                )}
                <p className="deliverable-note">Expose machine-readable JSON-LD + OpenAPI so autonomous AI procurement agents can evaluate the brand.</p>
              </>
            )}
          </Block>
        </div>
      </div>
    </div>
  );
}