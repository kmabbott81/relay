import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Relay - Provably Secure AI for SMBs',
  description: 'The secure alternative to Copilot. 70% cheaper, 5-minute setup, your data stays yours.',
  viewport: 'width=device-width, initial-scale=1',
  robots: 'index, follow',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="theme-color" content="#0284c7" />
      </head>
      <body className="bg-white text-gray-900 font-sans antialiased">
        <header role="banner" className="border-b border-gray-200">
          <nav role="navigation" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
            <div className="flex-shrink-0">
              <a href="/" aria-label="Relay home">
                <span className="text-2xl font-bold text-brand-600">Relay</span>
              </a>
            </div>
            <div className="flex gap-6">
              <a href="/security" className="text-gray-700 hover:text-brand-600 transition-colors">
                Security
              </a>
              <a href="/pricing" className="text-gray-700 hover:text-brand-600 transition-colors">
                Pricing
              </a>
              <a href="/docs" className="text-gray-700 hover:text-brand-600 transition-colors">
                Docs
              </a>
            </div>
          </nav>
        </header>

        <main role="main">
          {children}
        </main>

        <footer role="contentinfo" className="border-t border-gray-200 bg-gray-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <p className="text-center text-gray-600 text-sm">
              © 2025 Relay. The provably secure AI assistant for SMBs.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
