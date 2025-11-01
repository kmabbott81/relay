export default function PricingPage() {
  const tiers = [
    {
      name: 'Personal Free',
      price: '$0',
      period: 'forever',
      description: 'Perfect for trying Relay',
      features: [
        '10 queries/day',
        '1 document upload/day',
        'Basic security dashboard',
        'Community support',
      ],
      cta: 'Get started free',
      highlighted: false,
    },
    {
      name: 'Student',
      price: '$0',
      period: 'with .edu',
      description: 'For students and educators',
      features: [
        'Unlimited queries',
        'Unlimited uploads',
        'Full security dashboard',
        'Priority support',
      ],
      cta: 'Verify student',
      highlighted: false,
    },
    {
      name: 'Professional',
      price: '$9',
      period: '/month',
      description: 'For power users',
      features: [
        'Unlimited queries',
        'Unlimited uploads',
        'Full security dashboard',
        'Email support',
        'Export data anytime',
      ],
      cta: 'Start free trial',
      highlighted: false,
    },
    {
      name: 'Team',
      price: '$49',
      period: '/month',
      description: 'For small teams (5 users)',
      features: [
        'Unlimited queries per user',
        'Unlimited uploads',
        'Shared documents',
        'Team invites',
        'Priority support',
        'Usage analytics',
      ],
      cta: 'Start free trial',
      highlighted: true,
    },
    {
      name: 'Business',
      price: '$199',
      period: '/month',
      description: 'For growing SMBs (25 users)',
      features: [
        'Unlimited everything',
        'Advanced permissions',
        'API access',
        'Custom retention',
        'SLA (99.9%)',
        'Dedicated support',
      ],
      cta: 'Contact sales',
      highlighted: false,
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      period: 'for 100+ users',
      description: 'For large organizations',
      features: [
        'Everything in Business',
        'SSO / SAML',
        'Custom SLA',
        'On-premise option',
        'Security audit',
        'Account manager',
      ],
      cta: 'Schedule demo',
      highlighted: false,
    },
  ];

  return (
    <div className="min-h-screen bg-white py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Pricing that makes sense
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto mb-8">
            No surprise charges. No enterprise bloat. Just honest pricing for real teams.
          </p>

          {/* Pricing Comparison */}
          <div className="inline-block bg-brand-50 border border-brand-200 rounded-lg p-6">
            <p className="text-gray-700">
              <span className="font-bold text-brand-600">Copilot:</span> $30/user/month
              <br />
              <span className="font-bold text-security-green">Relay Professional:</span> $9/user/month
              <br />
              <span className="font-bold text-security-green">You save: 70%</span>
            </p>
          </div>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 mb-16">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`rounded-lg border transition-all ${
                tier.highlighted
                  ? 'border-brand-600 ring-2 ring-brand-600 transform lg:scale-105 bg-brand-50'
                  : 'border-gray-200 bg-white'
              } p-8`}
            >
              {tier.highlighted && (
                <div className="mb-4">
                  <span className="inline-block bg-brand-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                    Most Popular
                  </span>
                </div>
              )}

              <h3 className="text-2xl font-bold text-gray-900 mb-2">
                {tier.name}
              </h3>
              <p className="text-gray-600 text-sm mb-6">{tier.description}</p>

              <div className="mb-6">
                <span className="text-5xl font-bold text-gray-900">
                  {tier.price}
                </span>
                <span className="text-gray-600 ml-2">{tier.period}</span>
              </div>

              <button
                className={`w-full font-bold py-3 rounded-lg transition-colors mb-8 focus-visible:outline-2 focus-visible:outline-offset-2 ${
                  tier.highlighted
                    ? 'bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600'
                    : 'border-2 border-brand-600 text-brand-600 hover:bg-brand-50 focus-visible:outline-brand-600'
                }`}
              >
                {tier.cta}
              </button>

              <ul className="space-y-3">
                {tier.features.map((feature, idx) => (
                  <li
                    key={idx}
                    className="flex items-center gap-3 text-gray-700"
                  >
                    <span className="text-security-green font-bold">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* FAQ Section */}
        <div className="bg-gray-50 rounded-lg p-8 mb-16">
          <h2 className="text-3xl font-bold text-gray-900 mb-8">
            Frequently Asked Questions
          </h2>

          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                Can I upgrade/downgrade anytime?
              </h3>
              <p className="text-gray-600">
                Yes. No long-term contracts. Change your plan monthly. Prorated charges applied.
              </p>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                Do you offer annual billing?
              </h3>
              <p className="text-gray-600">
                Yes. Pay annually and get 2 months free (17% discount on monthly rate).
              </p>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                What about per-seat pricing for teams?
              </h3>
              <p className="text-gray-600">
                Team tier is $49/month for 5 users ($9.80/user). Add more users at $9 each.
              </p>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                Do you offer discounts for nonprofits?
              </h3>
              <p className="text-gray-600">
                Yes! Contact us for nonprofit pricing. Usually 50% off.
              </p>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                What happens if I exceed my query limit?
              </h3>
              <p className="text-gray-600">
                Free tier: Hard limit (1 day wait). Paid tiers: Unlimited.
              </p>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">
                Is there a free trial for paid plans?
              </h3>
              <p className="text-gray-600">
                Yes. 14-day free trial on all paid tiers. No credit card required.
              </p>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Ready to switch from Copilot?
          </h2>
          <p className="text-gray-600 mb-8 max-w-xl mx-auto">
            Start free, no credit card required. If you're happy after 14 days, upgrade.
            If not, delete everything. No questions asked.
          </p>
          <button className="bg-brand-600 hover:bg-brand-700 text-white font-bold py-3 px-8 rounded-lg transition-colors">
            Start your free trial
          </button>
        </div>
      </div>
    </div>
  );
}
