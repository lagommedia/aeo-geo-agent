'use client';

import { useEffect, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, BarChart, Bar } from 'recharts';
import { authedGet } from '@/lib/api';
import { useToken } from './components/token-context';

type Point = { label: string; value: number };

export default function DashboardPage() {
  const token = useToken();
  const [citationShare, setCitationShare] = useState<Point[]>([]);
  const [pipeline, setPipeline] = useState<Point[]>([]);
  const [velocity, setVelocity] = useState<Point[]>([]);

  useEffect(() => {
    if (!token) return;
    authedGet('/metrics', token).then((data) => {
      setCitationShare(data.ai_citation_share || []);
      setPipeline(data.non_branded_pipeline || []);
      setVelocity(data.competitor_velocity || []);
    });
  }, [token]);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="rounded-2xl border border-black/20 bg-panel p-5">
        <h2 className="mb-3 text-lg font-semibold">AI Citation Share</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={citationShare}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#c3472c" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="rounded-2xl border border-black/20 bg-panel p-5">
        <h2 className="mb-3 text-lg font-semibold">Non-Branded Pipeline Proxy</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={pipeline}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#2f6f5e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="rounded-2xl border border-black/20 bg-panel p-5 md:col-span-2">
        <h2 className="mb-3 text-lg font-semibold">Competitor Content Velocity</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={velocity}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#1d3557" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
