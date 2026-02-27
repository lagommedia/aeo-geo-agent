import './globals.css';
import type { Metadata } from 'next';
import Nav from './components/nav';
import AuthGate from './components/auth-gate';
import { TokenProvider } from './components/token-context';

export const metadata: Metadata = {
  title: 'Demand Capture Agent',
  description: 'SEO/AEO/GEO demand capture MVP'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
          <TokenProvider>
            <main className="mx-auto max-w-6xl p-6 md:p-10">
              <header className="mb-6">
                <h1 className="text-3xl font-bold">Demand Capture Agent</h1>
                <p className="text-sm text-muted">Zeni SEO/AEO/GEO Opportunity System</p>
              </header>
              <Nav />
              {children}
            </main>
          </TokenProvider>
        </AuthGate>
      </body>
    </html>
  );
}
