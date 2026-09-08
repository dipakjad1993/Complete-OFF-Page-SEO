import axios from 'axios';

const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  // 35-module full analysis takes 60-180s — 30s timeout killed it. 5 min + retries.
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Long-poll helper for background analysis jobs (progress every 2s, up to ~6 min).
export async function pollAnalysisUntilDone(
  brandId: number,
  onProgress?: (p: any) => void,
  intervalMs = 2000,
  maxWaitMs = 360000,
): Promise<any> {
  const started = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { data } = await api.get(`/analysis/progress/${brandId}`);
    if (onProgress) {
      try { onProgress(data); } catch { /* ignore */ }
    }
    if (data?.status === 'completed' || data?.status === 'failed') return data;
    if (Date.now() - started > maxWaitMs) return data;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export const brandAPI = {
  create: (data: any) => api.post('/brands/', data),
  list: () => api.get('/brands/'),
  get: (id: number) => api.get(`/brands/${id}`),
  update: (id: number, data: any) => api.put(`/brands/${id}`, data),
  delete: (id: number) => api.delete(`/brands/${id}`),
  overview: (id: number) => api.get(`/brands/${id}/overview`),
  executives: (id: number) => api.get(`/brands/${id}/executives`),
  competitors: (id: number) => api.get(`/brands/${id}/competitors`),
};

export const dashboardAPI = {
  executive: (brandId: number) => api.get(`/dashboard/${brandId}`),
  revenueImpact: (brandId: number) => api.get(`/dashboard/${brandId}/revenue-impact`),
};

export const featuresAPI = {
  list: () => api.get('/features/'),
  get: (id: number) => api.get(`/features/${id}`),
  status: () => api.get('/features/status/summary'),
};

export const campaignAPI = {
  create: (data: any) => api.post('/campaigns/', data),
  list: (brandId?: number) => api.get('/campaigns/', { params: { brand_id: brandId } }),
  get: (id: number) => api.get(`/campaigns/${id}`),
  updateStatus: (id: number, status: string) => api.put(`/campaigns/${id}/status`, null, { params: { status } }),
};

export const alertAPI = {
  list: (params: any) => api.get('/alerts/', { params }),
  critical: () => api.get('/alerts/critical'),
  resolve: (id: number) => api.put(`/alerts/${id}/resolve`),
  stats: () => api.get('/alerts/stats'),
};

export const knowledgeGraphAPI = {
  createTriple: (data: any) => api.post('/knowledge-graph/triples', data),
  getTriples: (brandId: number) => api.get(`/knowledge-graph/triples/${brandId}`),
  checkWikidata: (brandId: number) => api.get(`/knowledge-graph/wikidata/${brandId}`),
  identifyGaps: (brandId: number) => api.get(`/knowledge-graph/gaps/${brandId}`),
  syncFromWikidata: (brandId: number) => api.post(`/knowledge-graph/sync-from-wikidata/${brandId}`),
};

export const ragMonitorAPI = {
  scan: (data: any) => api.post('/rag-monitor/scan', data),
  getCitations: (brandId: number) => api.get(`/rag-monitor/citations/${brandId}`),
  getHallucinations: (brandId: number) => api.get(`/rag-monitor/hallucinations/${brandId}`),
  verifyAccuracy: (brandId: number) => api.post(`/rag-monitor/verify/${brandId}`),
  accuracyReport: (brandId: number) => api.get(`/rag-monitor/accuracy-report/${brandId}`),
};

export const vectorEngineAPI = {
  measure: (data: any) => api.post('/vector-engine/measure', data),
  getDistances: (brandId: number) => api.get(`/vector-engine/distances/${brandId}`),
  gapAnalysis: (brandId: number) => api.get(`/vector-engine/gap-analysis/${brandId}`),
};

export const prEngineAPI = {
  createPitch: (data: any) => api.post('/pr-engine/pitches', data),
  listPitches: (brandId?: number) => api.get('/pr-engine/pitches', { params: { brand_id: brandId } }),
  // FIX: backend is POST /pr-engine/generate-pitch (was GET → 405). Keep backwards-compat wrapper.
  generatePitch: (params: { brand_id: number; topic: string; journalist_name: string; publication: string }) =>
    api.post('/pr-engine/generate-pitch', null, { params: {
      brand_id: (params as any).brand_id ?? (params as any).brandId,
      topic: (params as any).topic,
      journalist_name: (params as any).journalist_name ?? (params as any).journalistName,
      publication: (params as any).publication,
    } }),
  generatePitchLegacyGet: (params: any) => api.get('/pr-engine/generate-pitch', { params }),
  dataHooks: (brandId: number) => api.get(`/pr-engine/data-hooks/${brandId}`),
};

export const analysisAPI = {
  run: (brand_id: number, analysis_type = 'full') =>
    api.post('/analysis/run', { brand_id, analysis_type }, { timeout: 300000 }),
  runAsync: (brand_id: number, analysis_type = 'full') =>
    api.post('/analysis/run-async', { brand_id, analysis_type }, { timeout: 30000 }),
  progress: (brandId: number) => api.get(`/analysis/progress/${brandId}`),
  results: (brandId: number) => api.get(`/analysis/results/${brandId}`),
  status: (brandId: number) => api.get(`/analysis/status/${brandId}`),
  exportCsv: (brandId: number) => api.get(`/analysis/export/${brandId}?format=csv`, { responseType: 'blob' }),
  pollUntilDone: pollAnalysisUntilDone,
};

export const intakeAPI = {
  saveSchema: (data: any) => api.post('/intake/brand-schema', data),
  getSchema: (brandId: number) => api.get(`/intake/brand-schema/${brandId}`),
  saveRisk: (data: any) => api.post('/intake/risk-config', data),
  saveScraper: (data: any) => api.post('/intake/scraper-config', data),
  saveCompetitors: (data: any) => api.post('/intake/competitors', data),
  listCompetitors: (brandId: number) => api.get(`/intake/competitors/${brandId}`),
};

export const scraperAPI = {
  scrape: (url: string) => api.post('/scraper/scrape-website', { url }, { timeout: 120000 }),
};

export const extendedAPI = {
  satelliteDiscover: (brandId: number) => api.get(`/satellite-entities/discover/${brandId}`),
  schemaGenerate: (brandId: number) => api.get(`/schema-validator/generate/${brandId}`),
  anchorDistribution: (brandId: number) => api.get(`/anchor-analysis/distribution/${brandId}`),
  crawlStatus: (brandId: number) => api.get(`/crawl-accelerator/status/${brandId}`),
  visualGap: (brandId: number) => api.get(`/visual-audit/authority-gap/${brandId}`),
  deadEquityScan: (brandId: number) => api.get(`/dead-equity/scan/${brandId}`),
  zeroPartyList: (brandId: number) => api.get(`/zero-party-data/assets/${brandId}`),
  simulationRun: (data: any) => api.post('/simulation/run', data, { timeout: 120000 }),
};

export const podcastAPI = {
  detect: (data: any) => api.post('/podcast-monitor/detect', data),
  list: (brandId: number) => api.get(`/podcast-monitor/pitches/${brandId}`),
  search: (brandId: number) => api.get(`/podcast-monitor/search/${brandId}`),
};

export const complianceAPI = {
  createRule: (data: any) => api.post('/compliance/rules', data),
  getRules: (brandId: number) => api.get(`/compliance/rules/${brandId}`),
  checkPitch: (brandId: number, pitchText: string) => 
    api.post('/compliance/check-pitch', null, { params: { brand_id: brandId, pitch_text: pitchText } }),
  sponsoredScan: (brandId: number) => api.get(`/compliance/sponsored-scan/${brandId}`),
};

export const toxicAnalysisAPI = {
  scan: (brandId: number) => api.get(`/toxic-analysis/scan/${brandId}`),
  anchorEntropy: (brandId: number) => api.get(`/toxic-analysis/anchor-entropy/${brandId}`),
  generateDisavow: (brandId: number) => api.post(`/toxic-analysis/disavow/${brandId}`),
  anomalyDetection: (brandId: number) => api.get(`/toxic-analysis/anomaly-detection/${brandId}`),
};

export const consensusAPI = {
  measure: (data: any) => api.post('/consensus/measure', data),
  getScore: (brandId: number) => api.get(`/consensus/score/${brandId}`),
  history: (brandId: number) => api.get(`/consensus/history/${brandId}`),
  gaps: (brandId: number) => api.get(`/consensus/gaps/${brandId}`),
  reddit: (brandId: number) => api.get(`/consensus/reddit/${brandId}`),
};

export const simulationAPI = {
  run: (data: any) => api.post('/simulation/run', data),
  revenueForecast: (brandId: number, months?: number) => 
    api.get(`/simulation/revenue-forecast/${brandId}`, { params: { months } }),
};

export const shareOfSearchAPI = {
  record: (data: any) => api.post('/share-of-search/record', data),
  current: (brandId: number) => api.get(`/share-of-search/current/${brandId}`),
  history: (brandId: number) => api.get(`/share-of-search/history/${brandId}`),
  trend: (brandId: number) => api.get(`/share-of-search/trend/${brandId}`),
  revenueAttribution: (brandId: number) => api.get(`/share-of-search/revenue-attribution/${brandId}`),
};

export const geoAuditAPI = {
  regions: (brandId: number) => api.get(`/geo-audit/regions/${brandId}`),
  blackouts: (brandId: number) => api.get(`/geo-audit/blackouts/${brandId}`),
  recommendations: (brandId: number) => api.get(`/geo-audit/recommendations/${brandId}`),
};

export const edgeRedirectAPI = {
  listRedirects: (brandId: number) => api.get(`/edge-redirect/redirects/${brandId}`),
  deploy: (id: number) => api.post(`/edge-redirect/deploy/${id}`),
  deadEquity: (brandId: number) => api.get(`/edge-redirect/dead-equity/${brandId}`),
  edgeRules: (brandId: number) => api.get(`/edge-redirect/edge-rules/${brandId}`),
};

export const passageScoringAPI = {
  score: (data: any) => api.post('/passage-scoring/score', data),
  analysis: (brandId: number) => api.get(`/passage-scoring/analysis/${brandId}`),
  lowValue: (brandId: number) => api.get(`/passage-scoring/low-value/${brandId}`),
};

export const redditAPI = {
  track: (data: any) => api.post('/reddit-monitor/track', data),
  mentions: (brandId: number) => api.get(`/reddit-monitor/mentions/${brandId}`),
  sentiment: (brandId: number) => api.get(`/reddit-monitor/sentiment/${brandId}`),
  coOccurrence: (brandId: number) => api.get(`/reddit-monitor/co-occurrence/${brandId}`),
};

export default api;
