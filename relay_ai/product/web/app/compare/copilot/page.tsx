'use client';

import Link from 'next/link';
import { SecurityBadge } from '@/components/SecurityBadge';
import { CheckIcon, XIcon, ArrowRightIcon } from 'lucide-react';

export default function ComparisonPage() {
  const comparisonData = [
    {
      category: 'Pricing',
      items: [
        { feature: 'Per-User Cost', relay: '$9–15/month', copilot: '$30/month (list)', winner: 'relay' },
        { feature: 'Free Tier', relay: '10/day queries', copilot: 'None', winner: 'relay' },
        { feature: 'Setup Cost', relay: '$0', copilot: '$5–10k IT setup', winner: 'relay' },
        { feature: 'Volume Discount', relay: 'Yes', copilot: 'Enterprise negotiated', winner: 'relay' },
      ],
    },
    {
      category: 'Security & Privacy',
      items: [
        { feature: 'Data Training', relay: 'No, by design', copilot: 'No, by policy', winner: 'tie' },
        { feature: 'Encryption Type', relay: 'AES-256-GCM E2E', copilot: 'TLS + MS-managed', winner: 'relay' },
        { feature: 'Data Isolation', relay: 'Database RLS', copilot: 'App-level + compliance', winner: 'relay' },
        { feature: 'Audit Trail', relay: 'Full per-query', copilot: 'Compliance scenarios', winner: 'relay' },
        { feature: 'Security Transparency', relay: 'Daily canary reports', copilot: 'Compliance certs', winner: 'different' },
      ],
    },
    {
      category: 'Setup & Deployment',
      items: [
        { feature: 'Time to Deploy', relay: '5 minutes', copilot: '4+ hours', winner: 'relay' },
        { feature: 'IT Involvement', relay: 'None', copilot: 'Required', winner: 'relay' },
        { feature: 'SSO Support', relay: 'Google/GitHub', copilot: 'Entra ID + SAML', winner: 'copilot' },
      ],
    },
    {
      category: 'Features',
      items: [
        { feature: 'Knowledge Base', relay: 'File upload ✓', copilot: 'Limited', winner: 'relay' },
        { feature: 'IDE Integration', relay: 'Planned', copilot: 'Yes ✓', winner: 'copilot' },
        { feature: 'Office Integration', relay: 'Planned', copilot: 'Yes ✓', winner: 'copilot' },
        { feature: 'Workflow Automation', relay: 'Yes ✓', copilot: 'Limited', winner: 'relay' },
        { feature: 'API Access', relay: 'Yes ✓', copilot: 'Limited', winner: 'relay' },
      ],
    },
    {
      category: 'Compliance',
      items: [
        { feature: 'SOC 2 Type II', relay: 'Q4 2025', copilot: 'Yes ✓', winner: 'copilot' },
        { feature: 'GDPR', relay: 'Yes ✓', copilot: 'Yes ✓', winner: 'tie' },
        { feature: 'Penetration Testing', relay: 'Annual ✓', copilot: 'Microsoft-managed', winner: 'relay' },
      ],
    },
  ];

  const costComparison = [
    {
      name: 'Relay',
      users: 100,
      licensing: 14400,
      setup: 50,
      training: 400,
      support: 0,
      total: 14850,
    },
    {
      name: 'Microsoft Copilot for M365 (List)',
      users: 100,
      licensing: 36000,
      setup: 1500,
      training: 1200,
      support: 2000,
      total: 46700,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      {/* Header */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            Relay vs Microsoft Copilot for Microsoft 365
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto mb-2">
            Cheaper. Different approach to security. Faster to deploy. See the side-by-side comparison.
          </p>
          <p className="text-sm text-gray-500">
            Prices reflect public list as of Nov 1, 2025. Both products protect customer data.
          </p>

          {/* Security Badge */}
          <div className="flex justify-center mb-8">
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <SecurityBadge
                encrypted="✓ AES-256-GCM"
                isolated="✓ Database RLS"
                training="✗ Never"
              />
            </div>
          </div>

          {/* Key Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-2xl mx-auto mb-8">
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold text-brand-600">70%</p>
              <p className="text-sm text-gray-600">Cheaper</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold text-brand-600">5 min</p>
              <p className="text-sm text-gray-600">Setup</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold text-brand-600">100%</p>
              <p className="text-sm text-gray-600">Private</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold text-brand-600">Daily</p>
              <p className="text-sm text-gray-600">Proof</p>
            </div>
          </div>
        </div>
      </div>

      {/* Comparison Sections */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12 mb-16">
        {comparisonData.map((section) => (
          <div key={section.category}>
            <h2 className="text-2xl font-bold text-gray-900 mb-6">{section.category}</h2>

            {/* Mobile: Stacked cards */}
            <div className="md:hidden space-y-4">
              {section.items.map((item, idx) => (
                <div key={idx} className="bg-white border border-gray-200 rounded-lg p-4">
                  <p className="font-semibold text-gray-900 mb-3">{item.feature}</p>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Relay:</span>
                      <span className={`font-semibold ${item.winner === 'relay' ? 'text-green-600' : 'text-gray-700'}`}>
                        {item.relay}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Copilot:</span>
                      <span className={`font-semibold ${item.winner === 'copilot' ? 'text-blue-600' : 'text-gray-700'}`}>
                        {item.copilot}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop: Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b-2 border-gray-300 bg-gray-50">
                    <th className="py-4 px-6 font-bold text-gray-900">Feature</th>
                    <th className="py-4 px-6 font-bold text-gray-900">Relay</th>
                    <th className="py-4 px-6 font-bold text-gray-900">Microsoft Copilot for M365</th>
                  </tr>
                </thead>
                <tbody>
                  {section.items.map((item, idx) => (
                    <tr key={idx} className="border-b border-gray-200 hover:bg-gray-50">
                      <td className="py-4 px-6 font-semibold text-gray-900">{item.feature}</td>
                      <td
                        className={`py-4 px-6 font-semibold ${
                          item.winner === 'relay' ? 'text-green-600' : 'text-gray-700'
                        }`}
                      >
                        {item.relay}
                      </td>
                      <td
                        className={`py-4 px-6 font-semibold ${
                          item.winner === 'copilot' ? 'text-blue-600' : 'text-gray-700'
                        }`}
                      >
                        {item.copilot}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      {/* TCO Comparison */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-16">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Total Cost of Ownership (Year 1)</h2>
        <p className="text-gray-600 mb-8">100-user company, fully deployed</p>

        <div className="grid md:grid-cols-2 gap-8">
          {costComparison.map((solution) => (
            <div key={solution.name} className="bg-white border border-gray-200 rounded-lg p-8">
              <h3 className="text-2xl font-bold text-gray-900 mb-6">{solution.name}</h3>

              <div className="space-y-3 mb-6 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Licensing (100 users, 12 months)</span>
                  <span className="font-semibold text-gray-900">${solution.licensing.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Setup & Integration</span>
                  <span className="font-semibold text-gray-900">${solution.setup.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Training</span>
                  <span className="font-semibold text-gray-900">${solution.training.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Support</span>
                  <span className="font-semibold text-gray-900">${solution.support.toLocaleString()}</span>
                </div>

                <div className="border-t pt-3">
                  <div className="flex justify-between">
                    <span className="font-bold text-gray-900">Total Year 1</span>
                    <span className="text-xl font-bold text-gray-900">${solution.total.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs text-gray-600 mt-2">
                    <span>Per-user cost</span>
                    <span>${(solution.total / 100).toFixed(2)}</span>
                  </div>
                </div>
              </div>

              {solution.name === 'Relay' && (
                <div className="bg-green-50 border border-green-200 rounded p-4 text-sm text-green-800">
                  <p className="font-semibold">💰 You save: $31,850 vs Copilot</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Why Choose Relay */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-16">
        <div className="grid md:grid-cols-2 gap-8">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Why Choose Relay</h2>
            <div className="space-y-4">
              <div className="flex gap-4">
                <CheckIcon className="text-green-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Provably Secure</p>
                  <p className="text-sm text-gray-600">Daily canary reports prove your data stays private</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-green-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">70% Cheaper</p>
                  <p className="text-sm text-gray-600">$9–15/user/month vs Copilot's $30</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-green-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">5-Minute Setup</p>
                  <p className="text-sm text-gray-600">No IT involvement. Start in minutes, not hours.</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-green-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Knowledge Base</p>
                  <p className="text-sm text-gray-600">Upload files, search across them with AI</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-green-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Full Audit Trail</p>
                  <p className="text-sm text-gray-600">Know exactly who accessed what and when</p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Why Choose Copilot</h2>
            <div className="space-y-4">
              <div className="flex gap-4">
                <CheckIcon className="text-blue-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Code Completion</p>
                  <p className="text-sm text-gray-600">IDE integration for real-time code suggestions</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-blue-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Office Integration</p>
                  <p className="text-sm text-gray-600">Works in Word, Excel, Teams, Outlook</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-blue-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Brand Trust</p>
                  <p className="text-sm text-gray-600">Established Microsoft compliance & support</p>
                </div>
              </div>
              <div className="flex gap-4">
                <CheckIcon className="text-blue-600 w-6 h-6 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">Enterprise Scale</p>
                  <p className="text-sm text-gray-600">Mature SOC 2, GDPR, and regional compliance</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Evidence & Resources */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-16">
        <div className="bg-brand-50 border border-brand-200 rounded-lg p-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">See the Proof</h2>
          <p className="text-gray-600 mb-8">
            Unlike Copilot's claims, Relay proves its security daily. Here's where to see it:
          </p>

          <div className="grid md:grid-cols-3 gap-8">
            <Link href="/security" className="group cursor-pointer">
              <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-lg transition-shadow">
                <p className="font-semibold text-gray-900 group-hover:text-brand-600 mb-2">
                  🔒 Security Proof
                </p>
                <p className="text-sm text-gray-600">Live dashboard showing encryption, isolation, and audit trail</p>
                <p className="text-xs text-brand-600 mt-4 font-semibold">View →</p>
              </div>
            </Link>

            <a
              href="/evidence/canaries/"
              target="_blank"
              rel="noopener noreferrer"
              className="group cursor-pointer"
            >
              <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-lg transition-shadow">
                <p className="font-semibold text-gray-900 group-hover:text-brand-600 mb-2">
                  📊 Daily Canary Reports
                </p>
                <p className="text-sm text-gray-600">Live security test results proving data isolation works</p>
                <p className="text-xs text-brand-600 mt-4 font-semibold">View →</p>
              </div>
            </a>

            <a href="/docs/openapi.json" target="_blank" rel="noopener noreferrer" className="group cursor-pointer">
              <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-lg transition-shadow">
                <p className="font-semibold text-gray-900 group-hover:text-brand-600 mb-2">
                  📋 API Documentation
                </p>
                <p className="text-sm text-gray-600">Full OpenAPI schema with security definitions</p>
                <p className="text-xs text-brand-600 mt-4 font-semibold">View →</p>
              </div>
            </a>
          </div>
        </div>
      </div>

      {/* Disclaimer Footer */}
      <div className="bg-gray-100 border-t border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <p className="text-xs text-gray-600 text-center">
            <strong>Accuracy Note:</strong> Prices reflect public list pricing as of Nov 1, 2025, and may vary by contract. Both Relay and Microsoft Copilot for Microsoft 365 protect customer data and don't train on customer prompts. Relay publishes daily security canary reports; Microsoft publishes compliance certifications. For the latest pricing and features, visit relay.ai/pricing and microsoft.com/copilot-for-microsoft-365.
          </p>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-gradient-to-r from-brand-600 to-brand-700 text-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
          <h2 className="text-4xl font-bold mb-4">Ready to Switch?</h2>
          <p className="text-xl text-brand-100 mb-8">
            Start free with 10 queries/day. No credit card. See the difference.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button className="bg-white text-brand-600 hover:bg-brand-50 font-bold py-3 px-8 rounded-lg transition-colors">
              Start Free Trial
            </button>
            <Link href="/pricing">
              <button className="border-2 border-white text-white hover:bg-brand-700 font-bold py-3 px-8 rounded-lg transition-colors">
                View Pricing
              </button>
            </Link>
          </div>

          <p className="text-sm text-brand-100 mt-6">Questions? Email sales@relay.ai</p>
        </div>
      </div>
    </div>
  );
}
