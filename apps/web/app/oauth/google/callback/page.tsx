'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { API_URL } from '@/lib/api';

export default function GoogleOAuthCallbackPage() {
  const params = useSearchParams();
  const [message, setMessage] = useState('Finishing connection...');

  useEffect(() => {
    async function complete() {
      const code = params.get('code');
      const state = params.get('state');
      const error = params.get('error');

      if (error) {
        const payload = { type: 'gsc_oauth_result', error };
        if (window.opener) {
          window.opener.postMessage(payload, window.location.origin);
        }
        setMessage(`OAuth error: ${error}`);
        return;
      }

      if (!code || !state) {
        return;
      }

      const key = `gsc-oauth:${state}:${code}`;
      if (window.sessionStorage.getItem(key) === 'sent') {
        return;
      }
      window.sessionStorage.setItem(key, 'sent');

      const token = window.localStorage.getItem('dc_token');
      if (!token) {
        const payload = { type: 'gsc_oauth_result', error: 'Missing local session token. Please login again.' };
        if (window.opener) {
          window.opener.postMessage(payload, window.location.origin);
        }
        setMessage('Missing local session token. Please login again.');
        return;
      }

      try {
        const res = await fetch(`${API_URL}/sources/gsc/oauth/callback`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ code, state })
        });

        if (!res.ok) {
          let detail = 'OAuth callback failed';
          try {
            const body = await res.json();
            if (body?.detail) detail = body.detail;
          } catch {
            // ignore json parse
          }
          const payload = { type: 'gsc_oauth_result', error: detail };
          if (window.opener) {
            window.opener.postMessage(payload, window.location.origin);
          }
          setMessage(detail);
          return;
        }

        const payload = { type: 'gsc_oauth_result', ok: true };
        if (window.opener) {
          window.opener.postMessage(payload, window.location.origin);
        }
        setMessage('Google Search Console connected. Closing...');
        setTimeout(() => window.close(), 150);
      } catch {
        const payload = { type: 'gsc_oauth_result', error: 'Network error during OAuth callback' };
        if (window.opener) {
          window.opener.postMessage(payload, window.location.origin);
        }
        setMessage('Network error during OAuth callback.');
      }
    }

    complete();
  }, [params]);

  return (
    <main className="mx-auto mt-24 max-w-md rounded border border-black/20 bg-white p-6 text-center">
      <h1 className="mb-2 text-xl font-semibold">Google OAuth</h1>
      <p className="text-sm text-gray-600">{message}</p>
    </main>
  );
}
