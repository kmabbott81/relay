/**
 * SecurityBadge Component
 *
 * Renders visible security indicators on every response.
 * A11y: Uses ARIA labels, semantic HTML, strong contrast (WCAG AAA).
 */

interface SecurityBadgeProps {
  encrypted?: string;
  isolated?: string;
  training?: string;
  proof?: string;
  variant?: 'compact' | 'full';
}

export function SecurityBadge({
  encrypted = '✓ AES-256-GCM',
  isolated = '✓ User-scoped RLS',
  training = '✗ Never',
  proof = 'Download audit',
  variant = 'full',
}: SecurityBadgeProps) {
  if (variant === 'compact') {
    return (
      <div
        className="inline-flex gap-3 bg-security-green bg-opacity-10 border border-security-green rounded px-3 py-1 text-xs font-semibold"
        role="status"
        aria-label="Security status: data protected"
      >
        <span className="text-security-green">🔒 Secure</span>
      </div>
    );
  }

  return (
    <div
      className="space-y-3"
      role="region"
      aria-label="Security guarantees"
    >
      {/* Encryption Badge */}
      <div className="flex items-center gap-2 p-3 bg-security-green bg-opacity-5 border border-security-green rounded">
        <span className="text-lg" aria-hidden="true">
          🔐
        </span>
        <span className="font-semibold text-gray-900">
          Encryption:
        </span>
        <span className="text-security-green font-bold">
          {encrypted}
        </span>
        <span className="sr-only">Data encrypted with AES-256-GCM</span>
      </div>

      {/* Isolation Badge */}
      <div className="flex items-center gap-2 p-3 bg-security-green bg-opacity-5 border border-security-green rounded">
        <span className="text-lg" aria-hidden="true">
          🔒
        </span>
        <span className="font-semibold text-gray-900">
          Isolation:
        </span>
        <span className="text-security-green font-bold">
          {isolated}
        </span>
        <span className="sr-only">Your data isolated per user via RLS</span>
      </div>

      {/* Training Badge */}
      <div className="flex items-center gap-2 p-3 bg-security-green bg-opacity-5 border border-security-green rounded">
        <span className="text-lg" aria-hidden="true">
          ✋
        </span>
        <span className="font-semibold text-gray-900">
          Training:
        </span>
        <span className="text-security-green font-bold">
          {training}
        </span>
        <span className="sr-only">Your data never used to train models</span>
      </div>

      {/* Proof Button */}
      <button
        className="w-full mt-2 px-4 py-2 bg-brand-600 text-white hover:bg-brand-700 rounded font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        aria-label={proof}
        onClick={() => {
          // TODO: Wire to audit log download
          console.log('Download audit log');
        }}
      >
        📥 {proof}
      </button>
    </div>
  );
}
