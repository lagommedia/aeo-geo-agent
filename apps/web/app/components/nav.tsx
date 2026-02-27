'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const links = [
  { href: '/', label: 'Dashboard' },
  { href: '/opportunities', label: 'Opportunity Inbox' },
  { href: '/scheduler', label: 'Scheduler' },
  { href: '/settings', label: 'Connect Sources' }
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="mb-8 flex flex-wrap gap-3">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`rounded-full border px-4 py-2 text-sm transition ${
            pathname === link.href ? 'border-accent bg-accent text-white' : 'border-black/20 bg-panel hover:border-black/50'
          }`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
