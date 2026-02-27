'use client';

import { useEffect, useState } from 'react';
import { authedGet } from '@/lib/api';
import { useToken } from '../components/token-context';

type Run = {
  id: number;
  run_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
};

export default function SchedulerPage() {
  const token = useToken();
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    if (!token) return;
    authedGet('/runs', token).then(setRuns);
  }, [token]);

  return (
    <div className="rounded-2xl border border-black/20 bg-panel p-4">
      <h2 className="mb-3 text-xl font-semibold">Scheduler Runs</h2>
      <p className="mb-4 text-sm text-muted">Nightly ingestion and interval jobs are driven by Celery beat (dev cadence in minutes).</p>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b">
            <th className="py-2">Job</th>
            <th>Status</th>
            <th>Last run</th>
            <th>Finished</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-2">{r.run_type}</td>
              <td>{r.status}</td>
              <td>{new Date(r.started_at).toLocaleString()}</td>
              <td>{r.finished_at ? new Date(r.finished_at).toLocaleString() : '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
