import axios from 'axios';

const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
  generatePitch: (params: any) => api.get('/pr-engine/generate-pitch', { params }),
  dataHooks: (brandId: number) => api.get(`/pr-engine/data-hooks/${brandId}`),
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
