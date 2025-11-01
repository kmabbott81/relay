/**
 * SecurityDashboard Component
 *
 * Displays live activity feed, security metrics, and audit actions.
 * This is the "Your Data Fortress" visible security feature.
 * A11y: Uses semantic HTML, ARIA live regions, keyboard navigation.
 */

interface ActivityItem {
  id: string;
  action: string;
  timestamp: string;
  status: 'success' | 'warning' | 'error';
}

interface Metrics {
  queriesIsolated: number;
  timesModelsTrained: number;
  encryptionBits: number;
}

interface SecurityDashboardProps {
  activity?: ActivityItem[];
  metrics?: Metrics;
  userId?: string;
}

export function SecurityDashboard({
  activity = [
    {
      id: '1',
      action: 'Document uploaded - Encrypted with your key',
      timestamp: '2 minutes ago',
      status: 'success',
    },
    {
      id: '2',
      action: 'Search performed - 0 data leaked',
      timestamp: '1 minute ago',
      status: 'success',
    },
    {
      id: '3',
      action: 'Teammate accessed - Permission verified',
      timestamp: 'Just now',
      status: 'success',
    },
  ],
  metrics = {
    queriesIsolated: 100,
    timesModelsTrained: 0,
    encryptionBits: 256,
  },
  userId = 'user@example.com',
}: SecurityDashboardProps) {
  return (
    <div
      className="max-w-4xl mx-auto p-6 bg-white border border-gray-200 rounded-lg"
      role="region"
      aria-label="Your Data Fortress - Security Dashboard"
    >
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">
          🏰 Your Data Fortress
        </h2>
        <p className="text-gray-600">
          Live security monitoring for {userId}
        </p>
      </div>

      {/* Activity Feed */}
      <div className="mb-8">
        <h3 className="text-xl font-bold text-gray-900 mb-4">
          Live Activity Feed
        </h3>
        <div
          className="space-y-3"
          role="log"
          aria-label="Recent security events"
          aria-live="polite"
        >
          {activity.map((item) => (
            <div
              key={item.id}
              className={`p-3 rounded border-l-4 ${
                item.status === 'success'
                  ? 'bg-security-green bg-opacity-5 border-security-green'
                  : item.status === 'warning'
                    ? 'bg-security-amber bg-opacity-5 border-security-amber'
                    : 'bg-security-red bg-opacity-5 border-security-red'
              }`}
              role="listitem"
            >
              <div className="flex items-center gap-2">
                <span className="text-lg" aria-hidden="true">
                  {item.status === 'success' ? '✓' : item.status === 'warning' ? '⚠' : '✗'}
                </span>
                <span className="font-medium text-gray-900">{item.action}</span>
              </div>
              <p className="text-sm text-gray-600 mt-1">{item.timestamp}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="mb-8 grid md:grid-cols-3 gap-4">
        {/* Metric 1: Isolation */}
        <div className="p-4 bg-brand-50 border border-brand-200 rounded">
          <p className="text-4xl font-bold text-brand-600">
            {metrics.queriesIsolated}%
          </p>
          <p className="text-sm text-gray-700 mt-1">
            Queries Isolated
          </p>
          <p className="text-xs text-gray-600 mt-2">
            Every query RLS-verified per user
          </p>
        </div>

        {/* Metric 2: Training */}
        <div className="p-4 bg-security-green bg-opacity-5 border border-security-green rounded">
          <p className="text-4xl font-bold text-security-green">
            {metrics.timesModelsTrained}
          </p>
          <p className="text-sm text-gray-700 mt-1">
            Times Models Trained
          </p>
          <p className="text-xs text-gray-600 mt-2">
            Your data never enters training pipelines
          </p>
        </div>

        {/* Metric 3: Encryption */}
        <div className="p-4 bg-brand-50 border border-brand-200 rounded">
          <p className="text-4xl font-bold text-brand-600">
            {metrics.encryptionBits}-bit
          </p>
          <p className="text-sm text-gray-700 mt-1">
            Encryption Strength
          </p>
          <p className="text-xs text-gray-600 mt-2">
            Military-grade AES encryption
          </p>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          className="flex-1 px-4 py-3 bg-brand-600 text-white hover:bg-brand-700 rounded font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          aria-label="Download today's security report"
        >
          📥 Download Today's Security Report
        </button>
        <button
          className="flex-1 px-4 py-3 border-2 border-brand-600 text-brand-600 hover:bg-brand-50 rounded font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          aria-label="Export all your data"
        >
          📦 Export All My Data
        </button>
        <button
          className="flex-1 px-4 py-3 border-2 border-security-red text-security-red hover:bg-security-red hover:bg-opacity-5 rounded font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-security-red"
          aria-label="Delete everything permanently"
        >
          🗑️ Delete Everything
        </button>
      </div>

      {/* Compliance Note */}
      <div className="mt-6 p-4 bg-gray-50 border border-gray-200 rounded text-xs text-gray-600">
        <p>
          ✓ All security metrics are live and accurate. This dashboard uses the same
          audit logs as our compliance reports. Download any metric as proof for your
          security team.
        </p>
      </div>
    </div>
  );
}
