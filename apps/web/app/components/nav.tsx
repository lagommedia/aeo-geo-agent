'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

type OppBoard = 'new' | 'refresh' | 'community';

function parseBoard(value: string | null): OppBoard {
  if (value === 'refresh' || value === 'community') return value;
  return 'new';
}

function itemClass(active: boolean): string {
  return `flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
    active
      ? 'border border-white/35 bg-white/10 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.16)]'
      : 'border border-transparent bg-transparent text-white/78 hover:bg-white/6 hover:text-white'
  }`;
}

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const onOpportunities = pathname.startsWith('/opportunities');
  const onIntegrations = pathname.startsWith('/settings');
  const selectedBoard = useMemo(() => parseBoard(searchParams.get('board')), [searchParams]);

  const [oppOpen, setOppOpen] = useState(onOpportunities);

  useEffect(() => {
    if (onOpportunities) setOppOpen(true);
  }, [onOpportunities]);

  return (
    <nav className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => {
          if (!onOpportunities) {
            setOppOpen(true);
            router.push(`/opportunities?board=${selectedBoard}`);
            return;
          }
          setOppOpen((prev) => !prev);
        }}
        className={itemClass(onOpportunities)}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 7h18M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
        </svg>
        <span className="flex-1 text-left">Opportunities</span>
        <svg
          viewBox="0 0 20 20"
          className={`h-4 w-4 transition-transform ${oppOpen ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
        >
          <path d="m7 4 6 6-6 6" />
        </svg>
      </button>

      {oppOpen ? (
        <div className="ml-3 space-y-1 border-l border-white/10 pl-3">
          <Link href="/opportunities?board=new" className={itemClass(onOpportunities && selectedBoard === 'new')}>
            <span>New Opportunities</span>
          </Link>
          <Link href="/opportunities?board=refresh" className={itemClass(onOpportunities && selectedBoard === 'refresh')}>
            <span>Refresh Opportunities</span>
          </Link>
          <Link href="/opportunities?board=community" className={itemClass(onOpportunities && selectedBoard === 'community')}>
            <span>Community</span>
          </Link>
        </div>
      ) : null}

      <Link href="/settings" className={itemClass(onIntegrations)}>
        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 7h18M3 12h18M3 17h18" />
          <circle cx="8" cy="7" r="2" fill="currentColor" stroke="none" />
          <circle cx="15" cy="12" r="2" fill="currentColor" stroke="none" />
          <circle cx="10" cy="17" r="2" fill="currentColor" stroke="none" />
        </svg>
        <span>Integrations</span>
      </Link>
    </nav>
  );
}
