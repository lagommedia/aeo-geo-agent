export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type Opportunity = {
  id: number;
  query_text: string;
  source: string;
  intent: string;
  funnel_stage: string;
  trend_score: number;
  refresh_needed: boolean;
  priority_score: number;
  priority_explanation: string;
  recommended_actions: string[];
  brief: string;
  status: string;
  metadata_json?: Record<string, unknown>;
  links?: string[];
};

export type SourceConfig = {
  id: number;
  source_name: string;
  config: Record<string, unknown>;
  status: string;
  notes?: string;
  created_at: string;
  updated_at: string;
};

export type SourceTestResult = {
  source_name: string;
  status: string;
  message: string;
  details: Record<string, unknown>;
};

function handleUnauthorized() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('dc_token');
  window.dispatchEvent(new Event('dc-auth'));
}

async function buildError(prefix: string, path: string, res: Response): Promise<Error> {
  if (res.status === 401) {
    handleUnauthorized();
    return new Error('Session expired. Please log in again.');
  }
  let detail = '';
  try {
    const body = await res.json();
    if (body?.detail) {
      detail = ` (${body.detail})`;
    }
  } catch {
    detail = '';
  }
  return new Error(`${prefix}: ${path}${detail}`);
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (!res.ok) throw new Error('Login failed');
  const data = await res.json();
  return data.access_token;
}

export async function register(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (!res.ok) throw new Error('Register failed');
  const data = await res.json();
  return data.access_token;
}

export async function authedGet(path: string, token: string) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  });
  if (!res.ok) throw await buildError('Request failed', path, res);
  return res.json();
}

export async function authedPatch(path: string, token: string, payload: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw await buildError('Patch failed', path, res);
  return res.json();
}

export async function authedPost(path: string, token: string, payload: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw await buildError('Post failed', path, res);
  return res.json();
}

export async function connectGscStart(token: string) {
  return authedPost('/sources/gsc/oauth/start', token, {});
}

export async function connectGscCallback(token: string, code: string, state: string): Promise<SourceConfig> {
  return authedPost('/sources/gsc/oauth/callback', token, { code, state });
}

export async function saveSourceCredentials(token: string, source_name: string, credentials: Record<string, unknown>, notes?: string) {
  return authedPost('/sources/credentials', token, { source_name, credentials, notes });
}

export async function testSource(token: string, source_name: string): Promise<SourceTestResult> {
  return authedPost(`/sources/${source_name}/test`, token, {});
}



export async function authedDelete(path: string, token: string) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw await buildError('Delete failed', path, res);
  return res.json();
}

export async function authedUpload(path: string, token: string, formData: FormData) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData
  });
  if (!res.ok) throw await buildError('Upload failed', path, res);
  return res.json();
}

export type KnowledgeBaseFile = {
  id: string;
  name: string;
  size_bytes: number;
  content_type: string;
  uploaded_at: string;
};
export type RefreshScanRow = {
  url: string;
  page_type: string;
  primary_prompt_target: string;
  long_tail_keyword_cluster: string;
  ai_visibility_impact: number;
  prompt_influence: number;
  entity_gap_severity: number;
  freshness_deficit: number;
  competitive_opportunity: number;
  effort: string;
  priority: string;
};

export type RefreshScanResult = {
  created_count: number;
  scanned_urls: string[];
  rows: RefreshScanRow[];
};

export type CommunityDiscoverResult = { created_count: number; terms_used: string[] };
