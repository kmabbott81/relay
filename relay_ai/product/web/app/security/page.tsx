import { SecurityDashboard } from '@/components/SecurityDashboard';

export default function SecurityPage() {
  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Security. Transparent. Proven.
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl">
            Unlike Copilot, we don't just claim security—we prove it. Every day.
            Here's your live security dashboard showing exactly how your data is protected.
          </p>
        </div>

        {/* Dashboard */}
        <SecurityDashboard />

        {/* Security Features */}
        <div className="mt-16 grid md:grid-cols-2 gap-8">
          {/* Feature 1: RLS */}
          <div className="bg-white p-8 rounded-lg border border-gray-200">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Row-Level Security (RLS)
            </h3>
            <p className="text-gray-600 mb-4">
              Your data is isolated at the database level. Not the application level.
              That means even if someone hacks Relay, they can't access your files.
            </p>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✓ PostgreSQL RLS policies on every table</li>
              <li>✓ User hash verified per transaction</li>
              <li>✓ Cross-tenant access: Impossible</li>
              <li>✓ Tested daily in production</li>
            </ul>
          </div>

          {/* Feature 2: Encryption */}
          <div className="bg-white p-8 rounded-lg border border-gray-200">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              End-to-End Encryption
            </h3>
            <p className="text-gray-600 mb-4">
              Files encrypted with AES-256-GCM before they hit disk.
              Your encryption key never leaves your browser.
            </p>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✓ AES-256-GCM encryption</li>
              <li>✓ HMAC-SHA256 binding (prevents tampering)</li>
              <li>✓ Key derived from JWT (per-session)</li>
              <li>✓ No key material on disk</li>
            </ul>
          </div>

          {/* Feature 3: Audit Trail */}
          <div className="bg-white p-8 rounded-lg border border-gray-200">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Complete Audit Trail
            </h3>
            <p className="text-gray-600 mb-4">
              Every action logged. Download your audit trail anytime.
              Know exactly who accessed what and when.
            </p>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✓ All queries logged with timestamps</li>
              <li>✓ User identification via JWT</li>
              <li>✓ Export as CSV/JSON</li>
              <li>✓ 90-day retention (compliant)</li>
            </ul>
          </div>

          {/* Feature 4: No Model Training */}
          <div className="bg-white p-8 rounded-lg border border-gray-200">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Your Data Never Trains Models
            </h3>
            <p className="text-gray-600 mb-4">
              Copilot trains on everything. Relay trains on nothing from you.
              Cryptographically guaranteed.
            </p>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✓ No model training on user data</li>
              <li>✓ No telemetry collection</li>
              <li>✓ No sharing with third parties</li>
              <li>✓ Verified in our DPA</li>
            </ul>
          </div>
        </div>

        {/* Compliance Section */}
        <div className="mt-16 bg-brand-50 border border-brand-200 rounded-lg p-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Compliance & Certifications
          </h2>
          <p className="text-gray-600 mb-6">
            We take security seriously. Here's what we're building toward:
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <span className="text-2xl">📋</span>
              <div>
                <p className="font-semibold">SOC 2 Type II</p>
                <p className="text-sm text-gray-600">In progress (Q4 2025)</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">🛡️</span>
              <div>
                <p className="font-semibold">GDPR Compliant</p>
                <p className="text-sm text-gray-600">DPA available</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">🔐</span>
              <div>
                <p className="font-semibold">ISO 27001</p>
                <p className="text-sm text-gray-600">Planned (2026)</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">📊</span>
              <div>
                <p className="font-semibold">Penetration Testing</p>
                <p className="text-sm text-gray-600">Annual (starting 2025)</p>
              </div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="mt-16 text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Security you can prove to your IT team.
          </h2>
          <p className="text-gray-600 mb-6 max-w-xl mx-auto">
            Download your security audit today. Show it to your CTO, CISO, or IT manager.
            Prove your data is safer with Relay than Copilot.
          </p>
          <button className="bg-brand-600 hover:bg-brand-700 text-white font-bold py-3 px-8 rounded-lg transition-colors">
            Download Security Report
          </button>
        </div>
      </div>
    </div>
  );
}
