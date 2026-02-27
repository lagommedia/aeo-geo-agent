'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { authedGet, authedPatch, Opportunity } from '@/lib/api';
import { useToken } from '../components/token-context';

export default function OpportunitiesPage() {
  const token = useToken();
  const [items, setItems] = useState<Opportunity[]>([]);
  const [source, setSource] = useState('');
  const [status, setStatus] = useState('');
  const [active, setActive] = useState<Opportunity | null>(null);

  useEffect(() => {
    if (!token) return;
    authedGet('/opportunities', token).then(setItems);
  }, [token]);

  const filtered = useMemo(
    () => items.filter((o) => (!source || o.source === source) && (!status || o.status === status)),
    [items, source, status]
  );

  async function changeStatus(id: number, nextStatus: string) {
    await authedPatch(`/opportunities/${id}`, token, { status: nextStatus });
    const refreshed = await authedGet('/opportunities', token);
    setItems(refreshed);
    setActive(refreshed.find((x: Opportunity) => x.id === id) || null);
  }

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <section className="rounded-2xl border border-black/20 bg-panel p-4">
        <div className="mb-3 flex gap-2">
          <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border px-2 py-1">
            <option value="">All sources</option>
            <option value="gsc">GSC</option>
            <option value="ai_citations">AI citations</option>
            <option value="competitor_velocity">Competitor velocity</option>
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border px-2 py-1">
            <option value="">All statuses</option>
            <option value="new">new</option>
            <option value="triaged">triaged</option>
            <option value="in-progress">in-progress</option>
            <option value="done">done</option>
          </select>
        </div>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="py-2">Query</th>
              <th>Source</th>
              <th>Priority</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.id} className="cursor-pointer border-b hover:bg-black/5" onClick={() => setActive(o)}>
                <td className="py-2">{o.query_text}</td>
                <td>{o.source}</td>
                <td>{o.priority_score.toFixed(1)}</td>
                <td>{o.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <aside className="rounded-2xl border border-black/20 bg-panel p-4">
        {active ? (
          <>
            <h3 className="mb-2 text-lg font-semibold">{active.query_text}</h3>
            <p className="mb-2 text-sm">{active.priority_explanation}</p>
            <p className="mb-2 text-sm">Trend: {active.trend_score.toFixed(1)}</p>
            <ul className="mb-3 list-disc pl-5 text-sm">
              {active.recommended_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <button className="rounded border px-2 py-1 text-sm" onClick={() => changeStatus(active.id, 'in-progress')}>
                Mark in progress
              </button>
              <button className="rounded border px-2 py-1 text-sm" onClick={() => changeStatus(active.id, 'done')}>
                Mark done
              </button>
              <Link href={`/briefs/${active.id}`} className="rounded bg-accent px-2 py-1 text-sm text-white">
                Export brief
              </Link>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted">Select an opportunity to view details.</p>
        )}
      </aside>
    </div>
  );
}
