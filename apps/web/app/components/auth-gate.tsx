'use client';

import { useEffect, useState } from 'react';
import { login, register } from '@/lib/api';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState('demo@zeni.ai');
  const [password, setPassword] = useState('demo1234');
  const [error, setError] = useState('');

  useEffect(() => {
    const t = localStorage.getItem('dc_token');
    if (t) setToken(t);
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

  if (token) return <>{children}</>;

  return (
    <div className="mx-auto mt-24 max-w-md rounded-2xl border border-black/20 bg-panel p-8 shadow">
      <h1 className="mb-2 text-2xl font-semibold">AI Content Demand Capture</h1>
      <p className="mb-6 text-sm text-muted">Use demo credentials or create a user.</p>
      <input className="mb-3 w-full rounded border px-3 py-2" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="mb-4 w-full rounded border px-3 py-2" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <div className="flex gap-2">
        <button className="rounded bg-accent px-4 py-2 text-white" onClick={() => handleAuth('login')}>
          Login
        </button>
        <button className="rounded border border-black/20 px-4 py-2" onClick={() => handleAuth('register')}>
          Register
        </button>
      </div>
      {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
    </div>
  );
}
