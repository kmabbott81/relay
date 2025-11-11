'use client';

import Link from 'next/link';
import { SecurityBadge } from '@/components/SecurityBadge';

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero Section */}
      <section className="flex-grow bg-gradient-to-br from-brand-50 to-blue-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
          <div className="text-center">
            <h1 className="text-5xl md:text-6xl font-bold text-brand-900 mb-6">
              Relay — the provably secure
              <br />
              <span className="text-brand-600">Copilot alternative</span>
            </h1>
            <p className="text-xl text-gray-700 mb-8 max-w-2xl mx-auto">
              Cheaper than Copilot. Faster to value. Your data stays yours.
              <br />
              <strong>We prove it daily.</strong>
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
              <Link href="/beta">
                <button
                  className="bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3 px-8 rounded-lg transition-colors"
                  aria-label="Try beta dashboard"
                >
                  Try beta app →
                </button>
              </Link>
              <Link href="/security">
                <button
                  className="border-2 border-brand-600 text-brand-600 hover:bg-brand-50 font-semibold py-3 px-8 rounded-lg transition-colors"
                  aria-label="View security proof"
                >
                  See security proof
                </button>
              </Link>
            </div>

            {/* Key Stats */}
            <div className="grid grid-cols-3 gap-8 max-w-2xl mx-auto mb-12">
              <div>
                <p className="text-3xl font-bold text-brand-600">70%</p>
                <p className="text-gray-600 text-sm">Cheaper than Copilot</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-brand-600">5 min</p>
                <p className="text-gray-600 text-sm">Setup time</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-brand-600">∞</p>
                <p className="text-gray-600 text-sm">Your data security</p>
              </div>
            </div>

            {/* Security Badges */}
            <div className="bg-white rounded-lg border border-gray-200 p-6 inline-block">
              <SecurityBadge
                encrypted="✓ AES-256"
                isolated="✓ Your data only"
                training="✗ Never used for training"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="bg-white py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-center mb-12">
            Why Relay beats Copilot
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="p-6 border border-gray-200 rounded-lg">
              <div className="text-3xl mb-4">🔒</div>
              <h3 className="text-xl font-bold mb-2">Provably Secure</h3>
              <p className="text-gray-600">
                Daily security proofs. Your competitor cannot access your data. Cryptographically impossible.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 border border-gray-200 rounded-lg">
              <div className="text-3xl mb-4">⚡</div>
              <h3 className="text-xl font-bold mb-2">5-Minute Setup</h3>
              <p className="text-gray-600">
                Google sign-in. Auto-provisioned workspace. No IT involvement needed. Works anywhere.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 border border-gray-200 rounded-lg">
              <div className="text-3xl mb-4">💰</div>
              <h3 className="text-xl font-bold mb-2">70% Cheaper</h3>
              <p className="text-gray-600">
                $9/user/month vs Copilot's $30. Free tier for 10 queries/day. No credit card.
              </p>
            </div>
          </div>

          {/* Comparison Table */}
          <div className="mt-16 overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b-2 border-gray-300">
                  <th className="py-3 px-4 font-bold">Feature</th>
                  <th className="py-3 px-4 font-bold">Copilot</th>
                  <th className="py-3 px-4 font-bold">Relay</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-gray-200">
                  <td className="py-3 px-4">Price</td>
                  <td className="py-3 px-4">$30/user/month</td>
                  <td className="py-3 px-4 font-bold text-security-green">$9/user/month</td>
                </tr>
                <tr className="border-b border-gray-200">
                  <td className="py-3 px-4">Setup</td>
                  <td className="py-3 px-4">2-4 hours</td>
                  <td className="py-3 px-4 font-bold text-security-green">5 minutes</td>
                </tr>
                <tr className="border-b border-gray-200">
                  <td className="py-3 px-4">Data Training</td>
                  <td className="py-3 px-4 font-bold text-security-red">Yes</td>
                  <td className="py-3 px-4 font-bold text-security-green">Never</td>
                </tr>
                <tr className="border-b border-gray-200">
                  <td className="py-3 px-4">Audit Trail</td>
                  <td className="py-3 px-4">Limited</td>
                  <td className="py-3 px-4 font-bold text-security-green">Full</td>
                </tr>
                <tr>
                  <td className="py-3 px-4">Free Tier</td>
                  <td className="py-3 px-4">None</td>
                  <td className="py-3 px-4 font-bold text-security-green">10/day</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-brand-600 text-white py-16">
        <div className="max-w-4xl mx-auto text-center px-4">
          <h2 className="text-4xl font-bold mb-4">
            Stop paying for surveillance.
          </h2>
          <p className="text-xl mb-8 text-brand-100">
            Join SMBs that switched from Copilot and kept their data.
          </p>
          <Link href="/beta">
            <button className="bg-white text-brand-600 hover:bg-brand-50 font-bold py-3 px-8 rounded-lg transition-colors">
              Try beta app free →
            </button>
          </Link>
        </div>
      </section>
    </div>
  );
}
