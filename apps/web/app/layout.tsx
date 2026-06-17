import './globals.css';
import type { Metadata } from 'next';
import { Montserrat } from 'next/font/google';
import Nav from './components/nav';
import AuthGate from './components/auth-gate';
import { TokenProvider } from './components/token-context';

const montserrat = Montserrat({ subsets: ['latin'], weight: ['400', '500', '600', '700'] });

export const metadata: Metadata = {
  title: 'Zeni AEO / GEO Agent',
  description: 'Zeni demand capture across SEO, AEO, and GEO'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={montserrat.className} suppressHydrationWarning>
        <AuthGate>
          <TokenProvider>
            <main className="mx-auto flex min-h-screen w-full max-w-[1600px] gap-6 p-5 md:gap-8 md:p-8">
              <aside className="sticky top-5 h-[calc(100vh-2.5rem)] w-[250px] shrink-0 rounded-2xl border border-white/10 bg-panel/80 p-4 backdrop-blur md:top-8 md:h-[calc(100vh-4rem)] md:p-5">
                <div className="mb-6 border-b border-white/10 pb-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-muted">BA AEO / GEO AGENT</p>
                  <h1 className="mt-2 text-3xl font-semibold text-ink">Zeni</h1>
                  <p className="mt-2 text-xs text-muted">Demand Capture Intelligence</p>
                </div>
                <Nav />
              </aside>

              <section className="min-w-0 flex-1">{children}</section>
            </main>
          </TokenProvider>
        </AuthGate>
      </body>
    </html>
  );
}
