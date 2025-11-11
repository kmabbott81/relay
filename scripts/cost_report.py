"""
Cost Report CLI (Sprint 30)

Prints per-tenant daily/monthly totals, budget status, anomalies.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.cost.anomaly import detect_anomalies  # noqa: E402
from relay_ai.cost.budgets import get_tenant_budget, is_over_budget  # noqa: E402
from relay_ai.cost.ledger import load_cost_events, rollup, window_sum  # noqa: E402


def print_text_report(tenant: str | None = None, days: int = 30):
    """
    Print human-readable text report.

    Args:
        tenant: Filter by tenant (None for all)
        days: Window size in days
    """
    events = load_cost_events(window_days=days)

    print(f"\n=== Cost Report (Last {days} Days) ===\n")

    # Global totals
    if not tenant:
        global_daily = window_sum(events, tenant=None, days=1)
        global_monthly = window_sum(events, tenant=None, days=30)

        print("Global Spend:")
        print(f"  Daily:   ${global_daily:,.2f}")
        print(f"  Monthly: ${global_monthly:,.2f}")
        print()

    # Per-tenant rollup
    tenant_rollup = rollup(events, by=("tenant",))

    if tenant:
        tenant_rollup = [r for r in tenant_rollup if r["tenant"] == tenant]

    print("Per-Tenant Spend:")
    print(f"{'Tenant':<20} {'Daily':>12} {'Monthly':>12} {'Budget Status':>15}")
    print("-" * 65)

    for record in tenant_rollup[:20]:  # Top 20
        tenant_id = record["tenant"]

        daily_spend = window_sum(events, tenant=tenant_id, days=1)
        monthly_spend = window_sum(events, tenant=tenant_id, days=30)

        status = is_over_budget(tenant_id, daily_spend, monthly_spend)

        status_icon = "✅" if not (status["daily"] or status["monthly"]) else "🚨"

        print(f"{tenant_id:<20} ${daily_spend:>10.2f} ${monthly_spend:>10.2f}  {status_icon}")

    print()

    # Anomalies
    anomalies = detect_anomalies(tenant=tenant)

    if anomalies:
        print("\n=== Cost Anomalies ===\n")

        for anom in anomalies:
            print(f"Tenant: {anom['tenant']}")
            print(f"  Today:    ${anom['today_spend']:.2f}")
            print(f"  Baseline: ${anom['baseline_mean']:.2f} (σ={anom['baseline_std_dev']:.2f})")
            print(f"  Threshold: ${anom['threshold']:.2f} ({anom['sigma']}σ)")
            print()


def print_json_report(tenant: str | None = None, days: int = 30):
    """
    Print JSON report.

    Args:
        tenant: Filter by tenant (None for all)
        days: Window size in days
    """
    events = load_cost_events(window_days=days)

    report = {
        "window_days": days,
        "tenant_filter": tenant,
        "global": {
            "daily": window_sum(events, tenant=None, days=1),
            "monthly": window_sum(events, tenant=None, days=30),
        },
        "tenants": [],
        "anomalies": detect_anomalies(tenant=tenant),
    }

    # Per-tenant stats
    tenant_rollup = rollup(events, by=("tenant",))

    if tenant:
        tenant_rollup = [r for r in tenant_rollup if r["tenant"] == tenant]

    for record in tenant_rollup:
        tenant_id = record["tenant"]

        daily_spend = window_sum(events, tenant=tenant_id, days=1)
        monthly_spend = window_sum(events, tenant=tenant_id, days=30)

        budget = get_tenant_budget(tenant_id)
        status = is_over_budget(tenant_id, daily_spend, monthly_spend)

        report["tenants"].append(
            {
                "tenant": tenant_id,
                "daily_spend": daily_spend,
                "monthly_spend": monthly_spend,
                "budget": budget,
                "over_budget": status,
            }
        )

    print(json.dumps(report, indent=2))


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Cost Report - view spend and budget status")

    parser.add_argument("--tenant", help="Filter by tenant")
    parser.add_argument("--days", type=int, default=30, help="Window size in days")
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args()

    if args.json:
        print_json_report(tenant=args.tenant, days=args.days)
    else:
        print_text_report(tenant=args.tenant, days=args.days)

    return 0


if __name__ == "__main__":
    sys.exit(main())
