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
};

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
  if (!res.ok) throw new Error(`Request failed: ${path}`);
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
  if (!res.ok) throw new Error(`Patch failed: ${path}`);
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
  if (!res.ok) throw new Error(`Post failed: ${path}`);
  return res.json();
}
