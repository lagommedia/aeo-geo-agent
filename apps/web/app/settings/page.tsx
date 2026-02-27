'use client';

import { useEffect, useState } from 'react';
import { authedGet, authedPost } from '@/lib/api';
import { useToken } from '../components/token-context';

type SourceConfig = {
  id: number;
  source_name: string;
  status: string;
  notes?: string;
};

export default function SettingsPage() {
  const token = useToken();
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [sourceName, setSourceName] = useState('gsc');
  const [notes, setNotes] = useState('Using sample file adapter');

  async function loadSources() {
    const data = await authedGet('/sources', token);
    setSources(data);
  }

  useEffect(() => {
    if (!token) return;
    loadSources();
  }, [token]);

  async function save() {
    await authedPost('/sources', token, {
      source_name: sourceName,
      config: {},
      status: 'connected',
      notes
    });
    await loadSources();
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="rounded-2xl border border-black/20 bg-panel p-4">
        <h2 className="mb-3 text-xl font-semibold">Connect Sources</h2>
        <p className="mb-4 text-sm text-muted">For local MVP use sample files in `/sample_data`. Add real env credentials in `.env` later.</p>
        <select value={sourceName} onChange={(e) => setSourceName(e.target.value)} className="mb-3 w-full rounded border px-2 py-2">
          <option value="gsc">Google Search Console</option>
          <option value="semrush">SEMrush</option>
          <option value="ahrefs">Ahrefs</option>
          <option value="ai_citations">AI Citations</option>
        </select>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="mb-3 w-full rounded border px-2 py-2" rows={4} />
        <button className="rounded bg-accent px-3 py-2 text-white" onClick={save}>
          Save Source Config
        </button>
      </section>

      <section className="rounded-2xl border border-black/20 bg-panel p-4">
        <h3 className="mb-3 text-lg font-semibold">Connected Sources</h3>
        <ul className="space-y-2 text-sm">
          {sources.map((s) => (
            <li key={s.id} className="rounded border border-black/15 p-2">
              <div className="font-medium">{s.source_name}</div>
              <div>Status: {s.status}</div>
              <div className="text-muted">{s.notes}</div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
