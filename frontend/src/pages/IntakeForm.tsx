import React from 'react';
import { Globe2, Loader2, Sparkles, CheckCircle2, XCircle } from 'lucide-react';

export interface Spokesperson {
  name: string;
  title: string;
  bio: string;
  credentials: string;
  expertise: string;
  linkedin: string;
  twitter: string;
  quotes: string;
  kgMid: string;
  wikidataId: string;
  isSme: boolean;
  department: string;
}

export interface CompetitorInput {
  name: string;
  domain: string;
  wikidata_id: string;
}

export interface IntakeState {
  // A. Core Entity & Brand Schema Data
  name: string;
  domain: string;
  description: string;
  kgMid: string;
  wikidataId: string;
  crunchbaseId: string;
  wikipediaUrl: string;
  officialMessaging: string;
  taxonomy: string;
  categories: string;
  keywords: string;
  spokes: Spokesperson[];
  competitors: CompetitorInput[];
  // B. Technical & Performance APIs
  gscFile: string;
  gscProperty: string;
  ga4Id: string;
  botCrawlApi: string;
  ahrefs: string;
  majestic: string;
  mozId: string;
  mozSecret: string;
  linkProviders: string[];
  // C. Real-Time Web & Social Listening Streams
  sources: string[];
  aiEngines: string[];
  listeningStreams: string[];
  // D. Governance & Guardrail Parameters
  riskLevel: string;
  riskScore: number;
  tactics: string[];
  blockedDomains: string;
  blockedTopics: string;
  maxOutreach: number;
  compName: string;
  compType: string;
  compContent: string;
}

export const emptyIntake = (): IntakeState => ({
  name: '',
  domain: '',
  description: '',
  kgMid: '',
  wikidataId: '',
  crunchbaseId: '',
  wikipediaUrl: '',
  officialMessaging: '',
  taxonomy: '',
  categories: '',
  keywords: '',
  spokes: [{ name: '', title: '', bio: '', credentials: '', expertise: '', linkedin: '', twitter: '', quotes: '', kgMid: '', wikidataId: '', isSme: false, department: '' }],
  competitors: [{ name: '', domain: '', wikidata_id: '' }],
  gscFile: '',
  gscProperty: '',
  ga4Id: '',
  botCrawlApi: '',
  ahrefs: '',
  majestic: '',
  mozId: '',
  mozSecret: '',
  linkProviders: [],
  sources: ['news', 'indpub', 'medium', 'substack', 'reddit', 'twitter', 'youtube', 'podcasts', 'stackoverflow', 'github', 'quora', 'trustpilot', 'g2', 'linkedin'],
  aiEngines: ['perplexity', 'chatgpt', 'gemini'],
  listeningStreams: ['podcast_transcripts', 'youtube_transcripts', 'news_rss', 'reddit_stream'],
  riskLevel: 'enterprise_safe',
  riskScore: 10,
  tactics: ['digital_pr', 'guest_posts', 'podcasts', 'data_studies', 'expert_quotes'],
  blockedDomains: '',
  blockedTopics: 'gambling, adult content, political controversy, crypto pump schemes',
  maxOutreach: 20,
  compName: 'Competitor Name Blacklist',
  compType: 'restricted_keywords',
  compContent: '',
});

interface Props {
  value: IntakeState;
  onChange: (v: IntakeState) => void;
}

const F = ({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) => (
  <div className="fg">
    <label>{label}</label>
    {children}
    {hint && <div className="field-hint">{hint}</div>}
  </div>
);

const I = (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />;
const TA = (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea rows={3} {...props} />;

const CHECKBOX_GROUPS: { key: 'sources' | 'tactics'; title: string; options: { v: string; l: string }[] }[] = [
  {
    key: 'sources',
    title: 'Web & social listening sources',
    options: [
      { v: 'news', l: 'High-authority news' },
      { v: 'indpub', l: 'Industry publications' },
      { v: 'medium', l: 'Medium' },
      { v: 'substack', l: 'Substack' },
      { v: 'reddit', l: 'Reddit' },
      { v: 'twitter', l: 'X / Twitter' },
      { v: 'youtube', l: 'YouTube' },
      { v: 'podcasts', l: 'Podcast transcripts' },
      { v: 'stackoverflow', l: 'Stack Overflow' },
      { v: 'github', l: 'GitHub' },
      { v: 'quora', l: 'Quora' },
      { v: 'trustpilot', l: 'Trustpilot' },
      { v: 'g2', l: 'G2' },
      { v: 'linkedin', l: 'LinkedIn' },
    ],
  },
  {
    key: 'tactics',
    title: 'Allowed outreach tactics',
    options: [
      { v: 'digital_pr', l: 'Digital PR' },
      { v: 'guest_posts', l: 'Guest posts' },
      { v: 'podcasts', l: 'Podcasts' },
      { v: 'data_studies', l: 'Data studies' },
      { v: 'expert_quotes', l: 'Expert quotes' },
      { v: 'expired', l: 'Expired domain redirects (aggressive)' },
      { v: 'sponsorship', l: 'Sponsorships' },
      { v: 'forum', l: 'Forum / community' },
      { v: 'reddit', l: 'Reddit participation' },
      { v: 'conference', l: 'Conference mentions' },
    ],
  },
];

const AI_ENGINE_OPTIONS = [
  { v: 'perplexity', l: 'Perplexity' },
  { v: 'chatgpt', l: 'ChatGPT / OpenAI Search' },
  { v: 'gemini', l: 'Google Gemini / AI Overviews' },
];

const LISTENING_OPTIONS = [
  { v: 'podcast_transcripts', l: 'Podcast transcripts (Whisper-vector monitor)' },
  { v: 'youtube_transcripts', l: 'YouTube transcripts' },
  { v: 'news_rss', l: 'News RSS firehose' },
  { v: 'reddit_stream', l: 'Reddit / forum streams' },
  { v: 'github_stream', l: 'GitHub / Stack Overflow' },
  { v: 'substack_stream', l: 'Substack / Medium' },
];

const LINK_PROVIDER_OPTIONS = [
  { v: 'ahrefs', l: 'Ahrefs link graph' },
  { v: 'majestic', l: 'Majestic link graph' },
  { v: 'moz', l: 'Moz link graph' },
  { v: 'serpapi', l: 'SerpAPI Google SERPs' },
];

export default function IntakeForm({ value, onChange }: Props) {
  const [urlInput, setUrlInput] = React.useState('');
  const [fetching, setFetching] = React.useState(false);
  const [fetchError, setFetchError] = React.useState('');
  const [fetchInfo, setFetchInfo] = React.useState('');
  const set = <K extends keyof IntakeState>(k: K, v: IntakeState[K]) => onChange({ ...value, [k]: v });
  const setSpoke = (i: number, k: keyof Spokesperson, v: string | boolean) => {
    const spokes = value.spokes.map((s, j) => (j === i ? { ...s, [k]: v } : s));
    set('spokes', spokes);
  };

  const toggle = <K extends 'sources' | 'tactics'>(key: K, v: string) => {
    const arr = value[key] as string[];
    set(key, (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]) as IntakeState[K]);
  };

  const handleUrlFetch = async () => {
    const url = urlInput.trim();
    if (!url) {
      setFetchError('Paste your website URL or any live article/blog URL first.');
      return;
    }
    setFetching(true);
    setFetchError('');
    setFetchInfo('');
    try {
      const res = await fetch('/api/v1/scraper/scrape-website', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((json.detail as string) || `Auto-fetch failed (${res.status})`);
      const d = json ?? {};
      const domain = String(d.domain || '').replace(/^www\./, '');
      // Prefer flattened frontend-ready candidates; fall back to raw execs / spokesperson.
      const candPool: Array<any> =
        Array.isArray(d.spokesperson_candidates) && d.spokesperson_candidates.length ? d.spokesperson_candidates
          : Array.isArray(d.all_executives) && d.all_executives.length ? d.all_executives
          : d.spokesperson && d.spokesperson.name ? [d.spokesperson] : [];
      const flatStr = (v: any): string => {
        if (typeof v === 'string') return v;
        if (Array.isArray(v)) return v.map((x: any) => (typeof x === 'string' ? x : String(x?.text || ''))).filter(Boolean).join('; ');
        return '';
      };
      const flatLines = (v: any): string => {
        if (typeof v === 'string') return v;
        if (Array.isArray(v)) return v.map((x: any) => (typeof x === 'string' ? x : String(x?.text || ''))).filter(Boolean).join('\n');
        return '';
      };
      const brandQuotes: string[] = Array.isArray(d.quote_repository) ? d.quote_repository.map(String).filter(Boolean)
        : Array.isArray(d.brand_quotes) ? d.brand_quotes.map((q: any) => String(q?.text || q || '')).filter(Boolean) : [];
      const competitors = Array.isArray(d.competitors)
        ? d.competitors.map((c: any) => ({ name: String(c?.name || ''), domain: String(c?.domain || ''), wikidata_id: String(c?.wikidata_id || '') }))
        : [{ name: '', domain: '', wikidata_id: '' }];
      const keywords = Array.isArray(d.keywords) ? d.keywords.map(String) : [];
      const seedKeywords = Array.isArray(d.seed_keywords) ? d.seed_keywords.map(String) : keywords;
      const taxonomy = Array.isArray(d.topical_taxonomy) ? d.topical_taxonomy.map(String) : [];
      const mappedSpokes: Spokesperson[] = candPool.slice(0, 12).map((e: any, idx: number) => ({
        name: String(e.name || ''),
        title: String(e.title || ''),
        bio: String(e.bio || ''),
        credentials: flatStr(e.credentials),
        expertise: flatStr(e.expertise),
        linkedin: String(e.linkedin || e.social_links?.linkedin || ''),
        twitter: String(e.twitter || e.social_links?.twitter || ''),
        quotes: flatLines(e.quotes) || (idx === 0 ? brandQuotes.slice(0, 4).join('\n') : ''),
        kgMid: String(e.kg_mid || ''),
        wikidataId: String(e.wikidata_id || ''),
        isSme: false,
        department: '',
      })).filter((s: any) => s.name);
      onChange({
        ...value,
        name: String(d.name || value.name),
        domain: domain || value.domain,
        description: String(d.description || d.wikidata_description || value.description),
        officialMessaging: String(d.official_messaging || value.officialMessaging),
        kgMid: String(d.kg_mid || value.kgMid),
        wikidataId: String(d.wikidata_id || value.wikidataId),
        crunchbaseId: String(d.crunchbase_id || value.crunchbaseId),
        wikipediaUrl: String(d.wikipedia_url || value.wikipediaUrl),
        taxonomy: (taxonomy.length ? taxonomy : seedKeywords).slice(0, 8).join(', ') || value.taxonomy,
        categories: String(d.category || value.categories),
        keywords: seedKeywords.join(', ') || value.keywords,
        spokes: mappedSpokes.length > 0 ? mappedSpokes : value.spokes,
        competitors: competitors.length > 0 ? competitors : value.competitors,
      });
      const v: any = d.verification ?? {};
      const ds: any = d.data_sources ?? {};
      const filled = [
        d.name ? 'brand name' : null,
        domain ? 'domain' : null,
        d.description || d.wikidata_description ? 'description' : null,
        d.official_messaging ? 'official messaging' : null,
        d.wikidata_id ? `wikidata ID (${v.wikidata_source ? 'site-verified' : 'best-match'})` : null,
        d.founded_year ? `founded ${d.founded_year}` : null,
        seedKeywords.length ? `${seedKeywords.length} seed keywords` : null,
        taxonomy.length ? `${taxonomy.length} topical pillars` : null,
        mappedSpokes.length ? `${mappedSpokes.length} spokespeople (${(v.executives_sources || []).join(', ') || 'verified sources'})` : null,
        !mappedSpokes.length ? 'spokespeople: none verified — add real people manually (never invented)' : null,
        brandQuotes.length ? `${brandQuotes.length} verbatim brand quotes with page URLs` : null,
        ds.bylines_found ? 'article bylines detected' : null,
        competitors.length ? `${competitors.length} competitors (${v.competitors_verified ?? 0} domain-verified)` : null,
      ].filter(Boolean);
      const note = typeof d.spokesperson_note === 'string' && d.spokesperson_note ? ` ${d.spokesperson_note}` : '';
      setFetchInfo(
        `Auto-researched ${String(d.pages_crawled || 0)} live pages from ${domain || url}. Pre-filled: ${filled.join(', ') || 'basic identity'}.${note} Every field below stays fully editable.`
      );
    } catch (err) {
      setFetchError((err as Error).message || 'Auto-fetch failed. Please fill the fields manually.');
    } finally {
      setFetching(false);
    }
  };

  return (
    <div className="intake-form">
      {/* URL auto-fetch bar */}
      <div className="url-fetch-bar">
        <div className="url-fetch-icon"><Globe2 size={18} /></div>
        <div className="url-fetch-main">
          <div className="url-fetch-label">Paste any live URL — your website home page OR a blog article — and let the tool crawl &amp; auto-fill every field</div>
          <div className="url-fetch-row">
            <input
              className="url-fetch-input"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleUrlFetch(); }}
              placeholder="https://yourbrand.com  ·  https://yourbrand.com/blog/some-article"
              disabled={fetching}
            />
            <button type="button" className="btn btn-primary url-fetch-btn" onClick={handleUrlFetch} disabled={fetching}>
              {fetching ? <><Loader2 size={16} className="animate-spin" /> Fetching…</> : <><Sparkles size={16} /> Fetch &amp; Auto-Fill</>}
            </button>
          </div>
          <div className="url-fetch-hint">
            Deep-crawls the site (home, about, team, blog, contact + sitemap-linked pages), resolves Wikipedia/Wikidata,
            discovers executives, competitors, keywords, socials and categories — then fills the intake below. Prefer manual entry? Just type in the fields directly.
          </div>
          {fetching && <div className="url-fetch-status"><Loader2 size={13} className="animate-spin" /> Crawling live pages &amp; resolving entity data…</div>}
          {fetchInfo && <div className="url-fetch-status ok"><CheckCircle2 size={13} /> {fetchInfo}</div>}
          {fetchError && <div className="url-fetch-status err"><XCircle size={13} /> {fetchError}</div>}
        </div>
      </div>

      <div className="intake-warning">
        <strong>Honest-data mode.</strong> This tool never fabricates results. Fields below are stored per brand and
        used to scope real analysis. Provider keys also read from <code>.env</code> (see <code>config/.env.example</code>).
        Modules without configured live sources report an explicit "no data" state instead of inventing numbers.
      </div>

      {/* A. Core Entity & Brand Schema Data */}
      <section className="intake-section">
        <h3 className="intake-section-title">1 · Core Entity &amp; Brand Schema Data</h3>
        <div className="intake-grid">
          <F label="Brand name">
            <I value={value.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. SERPrecon" />
          </F>
          <F label="Brand domain">
            <I value={value.domain} onChange={(e) => set('domain', e.target.value)} placeholder="serprecon.com" />
          </F>
          <F label="Description" hint="Used for entity resolution across knowledge graphs.">
            <I value={value.description} onChange={(e) => set('description', e.target.value)} placeholder="What the brand does, in one sentence" />
          </F>
          <F label="Official messaging" hint="Official positioning/messaging rendered as semantic vectors.">
            <TA value={value.officialMessaging} onChange={(e) => set('officialMessaging', e.target.value)} placeholder="Official brand positioning, value props, message house…" />
          </F>
          <F label="Topical taxonomy" hint="Comma-separated topic pillars the brand owns.">
            <I value={value.taxonomy} onChange={(e) => set('taxonomy', e.target.value)} placeholder="semantic seo, topical authority, digital pr" />
          </F>
          <F label="Primary product categories">
            <I value={value.categories} onChange={(e) => set('categories', e.target.value)} placeholder="marketing, seo software" />
          </F>
          <F label="Seed keywords" hint="Seed set used to seed LLM/search entity probes.">
            <TA value={value.keywords} onChange={(e) => set('keywords', e.target.value)} placeholder="semantic seo, topical authority, ai search, …" />
          </F>
        </div>

        <h4 className="intake-subtitle">Knowledge Graph identifiers</h4>
        <div className="intake-grid">
          <F label="Google KG MID">
            <I value={value.kgMid} onChange={(e) => set('kgMid', e.target.value)} placeholder="/m/0xxxxxx" />
          </F>
          <F label="Wikidata ID">
            <I value={value.wikidataId} onChange={(e) => set('wikidataId', e.target.value)} placeholder="Q1954843" />
          </F>
          <F label="Crunchbase entity">
            <I value={value.crunchbaseId} onChange={(e) => set('crunchbaseId', e.target.value)} placeholder="serprecon" />
          </F>
          <F label="Wikipedia URL">
            <I value={value.wikipediaUrl} onChange={(e) => set('wikipediaUrl', e.target.value)} placeholder="https://en.wikipedia.org/wiki/…" />
          </F>
        </div>

        <h4 className="intake-subtitle">Spokesperson matrix</h4>
        {value.spokes.map((s, i) => (
          <div key={i} className="spoke-card">
            <div className="intake-grid">
              <F label="Full name">
                <I value={s.name} onChange={(e) => setSpoke(i, 'name', e.target.value)} placeholder="Real person — no fictional people" />
              </F>
              <F label="Title">
                <I value={s.title} onChange={(e) => setSpoke(i, 'title', e.target.value)} placeholder="CTO" />
              </F>
              <F label="Credentials" hint="Degrees, certs, awards used for expert-consensus pitches.">
                <I value={s.credentials} onChange={(e) => setSpoke(i, 'credentials', e.target.value)} placeholder="PhD, CISSP…" />
              </F>
              <F label="Expertise areas">
                <I value={s.expertise} onChange={(e) => setSpoke(i, 'expertise', e.target.value)} placeholder="zero trust, cloud security" />
              </F>
              <F label="LinkedIn">
                <I value={s.linkedin} onChange={(e) => setSpoke(i, 'linkedin', e.target.value)} placeholder="https://linkedin.com/in/…" />
              </F>
              <F label="X / Twitter">
                <I value={s.twitter} onChange={(e) => setSpoke(i, 'twitter', e.target.value)} placeholder="@handle" />
              </F>
            </div>
            <F label="Biography">
              <TA value={s.bio} onChange={(e) => setSpoke(i, 'bio', e.target.value)} placeholder="Real, verifiable bio." />
            </F>
            <F label="Quote repository" hint="Verbatim quotes available for placement. No invented quotes.">
              <TA value={s.quotes} onChange={(e) => setSpoke(i, 'quotes', e.target.value)} placeholder="Each real quote on its own line" />
            </F>
            <div className="intake-grid">
              <F label="KG MID (executive)" hint="Google Knowledge Graph ID for this person, if known.">
                <I value={s.kgMid} onChange={(e) => setSpoke(i, 'kgMid', e.target.value)} placeholder="kg:/m/…" />
              </F>
              <F label="Wikidata ID (executive)">
                <I value={s.wikidataId} onChange={(e) => setSpoke(i, 'wikidataId', e.target.value)} placeholder="Q…" />
              </F>
              <F label="Department">
                <I value={s.department} onChange={(e) => setSpoke(i, 'department', e.target.value)} placeholder="Engineering, Research…" />
              </F>
              <F label="Subject-matter expert">
                <label className="checkbox-item">
                  <input type="checkbox" checked={!!s.isSme} onChange={(e) => setSpoke(i, 'isSme', e.target.checked)} />
                  <span>SME — prioritize for expert-consensus pitches</span>
                </label>
              </F>
            </div>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-b"
          onClick={() => set('spokes', [...value.spokes, { name: '', title: '', bio: '', credentials: '', expertise: '', linkedin: '', twitter: '', quotes: '', kgMid: '', wikidataId: '', isSme: false, department: '' }])}
        >
          + Add spokesperson
        </button>

        <h4 className="intake-subtitle">Competitor entities</h4>
        {value.competitors.map((c, i) => (
          <div key={i} className="intake-grid" style={{ marginBottom: '0.75rem' }}>
            <F label="Competitor name">
              <I value={c.name} onChange={(e) => {
                const list = value.competitors.map((x, j) => (j === i ? { ...x, name: e.target.value } : x));
                set('competitors', list);
              }} placeholder="e.g. CrowdStrike" />
            </F>
            <F label="Domain">
              <I value={c.domain} onChange={(e) => {
                const list = value.competitors.map((x, j) => (j === i ? { ...x, domain: e.target.value } : x));
                set('competitors', list);
              }} placeholder="crowdstrike.com" />
            </F>
            <F label="Wikidata ID">
              <I value={c.wikidata_id} onChange={(e) => {
                const list = value.competitors.map((x, j) => (j === i ? { ...x, wikidata_id: e.target.value } : x));
                set('competitors', list);
              }} placeholder="Q28091265" />
            </F>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-b"
          onClick={() => set('competitors', [...value.competitors, { name: '', domain: '', wikidata_id: '' }])}
        >
          + Add competitor
        </button>
      </section>

      {/* B. Technical & Performance APIs */}
      <section className="intake-section">
        <h3 className="intake-section-title">2 · Technical &amp; Performance APIs</h3>
        <div className="intake-grid">
          <F label="GSC credentials file" hint="Path to service-account JSON. Tracks Brand Search Volume + referral paths.">
            <I value={value.gscFile} onChange={(e) => set('gscFile', e.target.value)} placeholder="/path/to/gsc-service-account.json" />
          </F>
          <F label="GSC property" hint="Search Console property, e.g. sc-domain:example.com. Enables real branded-query volume.">
            <I value={value.gscProperty} onChange={(e) => set('gscProperty', e.target.value)} placeholder="sc-domain:example.com" />
          </F>
          <F label="GA4 property ID" hint="Multi-touch attribution + branded-query pipeline conversion.">
            <I value={value.ga4Id} onChange={(e) => set('ga4Id', e.target.value)} placeholder="384756129" />
          </F>
          <F label="Bot crawl / log API" hint="Log-file or bot-crawl endpoint. Monitors spider re-crawls after citation spikes.">
            <I value={value.botCrawlApi} onChange={(e) => set('botCrawlApi', e.target.value)} placeholder="https://…/crawl-logs or provider name" />
          </F>
          <F label="Ahrefs API key" hint="Link graph, anchor distribution, link velocity.">
            <I type="password" value={value.ahrefs} onChange={(e) => set('ahrefs', e.target.value)} placeholder="Stored in brand config; engine also reads .env" />
          </F>
          <F label="Majestic API key">
            <I type="password" value={value.majestic} onChange={(e) => set('majestic', e.target.value)} placeholder="—" />
          </F>
          <F label="Moz Access ID">
            <I type="password" value={value.mozId} onChange={(e) => set('mozId', e.target.value)} placeholder="—" />
          </F>
          <F label="Moz Secret key">
            <I type="password" value={value.mozSecret} onChange={(e) => set('mozSecret', e.target.value)} placeholder="—" />
          </F>
        </div>
        <div className="field-hint" style={{ marginTop: '0.6rem' }}>
          Provider integrations also honor <code>.env</code> (AHREFS_API_KEY, MAJESTIC_API_KEY, MOZ_ACCESS_KEY / MOZ_SECRET_KEY, GSC_CREDENTIALS_FILE, GA4_PROPERTY_ID). Keys entered here are saved to the brand's credential vault via the API.
        </div>
        <div className="checkbox-group">
          <div className="checkbox-title">Link-graph providers to use for this brand (anchor distribution, velocity)</div>
          <div className="checkbox-list">
            {LINK_PROVIDER_OPTIONS.map((o) => (
              <label key={o.v} className="checkbox-item">
                <input type="checkbox" checked={value.linkProviders.includes(o.v)} onChange={() => {
                  const arr = value.linkProviders;
                  set('linkProviders', arr.includes(o.v) ? arr.filter((x) => x !== o.v) : [...arr, o.v]);
                }} />
                <span>{o.l}</span>
              </label>
            ))}
          </div>
        </div>
      </section>

      {/* C. Real-Time Web & Social Listening Streams */}
      <section className="intake-section">
        <h3 className="intake-section-title">3 · Real-Time Web &amp; Social Listening Streams</h3>
        {CHECKBOX_GROUPS.map((g) => (
          <div key={g.key} className="checkbox-group">
            <div className="checkbox-title">{g.title}</div>
            <div className="checkbox-list">
              {g.options.map((o) => (
                <label key={o.v} className="checkbox-item">
                  <input type="checkbox" checked={value[g.key].includes(o.v)} onChange={() => toggle(g.key, o.v)} />
                  <span>{o.l}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
        <div className="checkbox-group">
          <div className="checkbox-title">Transcript-first listening streams (Whisper-vector monitor inputs)</div>
          <div className="checkbox-list">
            {LISTENING_OPTIONS.map((o) => (
              <label key={o.v} className="checkbox-item">
                <input type="checkbox" checked={value.listeningStreams.includes(o.v)} onChange={() => {
                  const arr = value.listeningStreams;
                  set('listeningStreams', arr.includes(o.v) ? arr.filter((x) => x !== o.v) : [...arr, o.v]);
                }} />
                <span>{o.l}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="checkbox-group">
          <div className="checkbox-title">AI search engines to monitor (RAG pipeline on engine outputs)</div>
          <div className="checkbox-list">
            {AI_ENGINE_OPTIONS.map((o) => (
              <label key={o.v} className="checkbox-item">
                <input type="checkbox" checked={value.aiEngines.includes(o.v)} onChange={() => {
                  const arr = value.aiEngines;
                  set('aiEngines', arr.includes(o.v) ? arr.filter((x) => x !== o.v) : [...arr, o.v]);
                }} />
                <span>{o.l}</span>
              </label>
            ))}
          </div>
        </div>
      </section>

      {/* D. Governance & Guardrail Parameters */}
      <section className="intake-section">
        <h3 className="intake-section-title">4 · Governance &amp; Guardrail Parameters</h3>
        <div className="intake-grid">
          <F label="Risk tolerance" hint="Strict logic gate for what the engine may propose.">
            <select value={value.riskLevel} onChange={(e) => set('riskLevel', e.target.value)}>
              <option value="enterprise_safe">Fortune 50 Enterprise Safety — 100% white-hat Digital PR, zero paid placements</option>
              <option value="aggressive">Venture-Backed Aggressive — tactical expired-domain redirects, high-risk sponsorships</option>
            </select>
          </F>
          <F label={`Risk score: ${value.riskScore} / 100`} hint="0 = Fortune-50 safe (white-hat only) · 100 = venture aggressive. Gates expired-domain + sponsorship tactics.">
            <input type="range" min={0} max={100} value={value.riskScore} onChange={(e) => set('riskScore', Number(e.target.value))} style={{ width: '100%' }} />
          </F>
          <F label="Max outreach per day">
            <I type="number" value={value.maxOutreach} onChange={(e) => set('maxOutreach', Number(e.target.value) || 0)} />
          </F>
        </div>
        {CHECKBOX_GROUPS.filter((g) => g.key === 'tactics').map((g) => (
          <div key={g.key} className="checkbox-group">
            <div className="checkbox-title">{g.title}</div>
            <div className="checkbox-list">
              {g.options.map((o) => (
                <label key={o.v} className="checkbox-item">
                  <input type="checkbox" checked={value[g.key].includes(o.v)} onChange={() => toggle(g.key, o.v)} />
                  <span>{o.l}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
        <div className="intake-grid">
          <F label="Blocked domains (one per line)" hint="Off-limit media outlets / domains.">
            <TA value={value.blockedDomains} onChange={(e) => set('blockedDomains', e.target.value)} placeholder="example-spam-domain.com" />
          </F>
          <F label="Blocked topics" hint="Disallowed topics enforced before any pitch goes out.">
            <I value={value.blockedTopics} onChange={(e) => set('blockedTopics', e.target.value)} />
          </F>
        </div>
        <div className="intake-grid">
          <F label="Compliance rule name">
            <I value={value.compName} onChange={(e) => set('compName', e.target.value)} placeholder="Competitor Name Blacklist" />
          </F>
          <F label="Compliance rule type">
            <select value={value.compType} onChange={(e) => set('compType', e.target.value)}>
              <option value="restricted_keywords">Restricted keywords</option>
              <option value="unreleased_features">Unreleased features / roadmap</option>
              <option value="forward_looking">Forward-looking statements</option>
              <option value="ftc_disclosure">FTC disclosure</option>
            </select>
          </F>
          <F label="Compliance rule content" hint="FTC/SEC guardrail checked before any automated outreach text.">
            <TA value={value.compContent} onChange={(e) => set('compContent', e.target.value)} placeholder="CrowdStrike, Palo Alto Networks, SentinelOne, Fortinet" />
          </F>
        </div>
      </section>
    </div>
  );
}