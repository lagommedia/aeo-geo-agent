'use client';

import { useEffect, useState } from 'react';
import { login, register } from '@/lib/api';

function isTokenExpired(token: string): boolean {
  try {
    const part = token.split('.')[1];
    if (!part) return true;
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    const exp = Number(payload?.exp || 0);
    if (!Number.isFinite(exp) || exp <= 0) return false;
    return Date.now() >= exp * 1000;
  } catch {
    return true;
  }
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string>('');
  const [checked, setChecked] = useState(false);
  const [email, setEmail] = useState('demo@zeni.ai');
  const [password, setPassword] = useState('demo1234');
  const [error, setError] = useState('');

  useEffect(() => {
    const t = localStorage.getItem('dc_token') || '';
    if (t && isTokenExpired(t)) {
      localStorage.removeItem('dc_token');
      setToken('');
      setChecked(true);
      return;
    }
    setToken(t);
    setChecked(true);
  }, []);

  async function handleAuth(mode: 'login' | 'register') {
    try {
      const t = mode === 'login' ? await login(email, password) : await register(email, password);
      localStorage.setItem('dc_token', t);
      setToken(t);
      window.dispatchEvent(new Event('dc-auth'));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!checked) {
    return <div className="h-24" />;
  }

  if (token) return <>{children}</>;

  return (
    <div className="mx-auto mt-24 max-w-md rounded-2xl border border-white/10 bg-panel/90 p-8 shadow-[0_16px_40px_rgba(0,0,0,0.4)]">
      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-muted">Zeni Platform</p>
      <h1 className="mb-2 text-2xl font-semibold text-ink">Zeni AEO / GEO Agent</h1>
      <p className="mb-6 text-sm text-muted">Use demo credentials or create a user.</p>
      <input
        className="mb-3 w-full rounded-lg border border-white/15 bg-[#10141d] px-3 py-2 text-ink"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        className="mb-4 w-full rounded-lg border border-white/15 bg-[#10141d] px-3 py-2 text-ink"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <div className="flex gap-2">
        <button className="zeni-btn zeni-btn-md" onClick={() => handleAuth('login')}>
          Login
        </button>
        <button className="zeni-btn zeni-btn-secondary zeni-btn-md" onClick={() => handleAuth('register')}>
          Register
        </button>
      </div>
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
    </div>
  );
}
