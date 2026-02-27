'use client';

import { marked } from 'marked';
import { useEffect, useState } from 'react';
import { authedGet } from '@/lib/api';
import { useToken } from '@/app/components/token-context';

export default function BriefPage({ params }: { params: { id: string } }) {
  const token = useToken();
  const [brief, setBrief] = useState('');

  useEffect(() => {
    if (!token) return;
    authedGet(`/opportunities/${params.id}/brief`, token).then((data) => setBrief(data.brief || ''));
  }, [token, params.id]);

  return (
    <div className="rounded-2xl border border-black/20 bg-panel p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Brief Editor</h2>
        <a
          href={`data:text/markdown;charset=utf-8,${encodeURIComponent(brief)}`}
          download={`brief-${params.id}.md`}
          className="rounded bg-accent px-3 py-2 text-sm text-white"
        >
          Download markdown
        </a>
      </div>
      <article className="prose max-w-none" dangerouslySetInnerHTML={{ __html: marked.parse(brief) as string }} />
    </div>
  );
}
