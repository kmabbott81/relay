#!/usr/bin/env python3
"""
Alerts system for DJP workflow monitoring.

Evaluates workflow metrics against thresholds and sends alerts to webhooks.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Add parent directory to path for src imports
sys.path.append(str(Path(__file__).parent.parent))
from relay_ai.metrics import filter_runs_by_date, load_runs, summarize_kpis


def parse_time_period(period: str) -> int:
    """
    Parse time period string into number of days.

    Args:
        period: Period string like "7d", "24h", "3w"

    Returns:
        Number of days
    """
    period = period.lower().strip()

    if period.endswith("d"):
        return int(period[:-1])
    elif period.endswith("h"):
        return max(1, int(period[:-1]) // 24)  # Convert hours to days, minimum 1
    elif period.endswith("w"):
        return int(period[:-1]) * 7
    else:
        # Assume it's just a number of days
        try:
            return int(period)
        except ValueError:
            raise ValueError(f"Invalid time period format: {period}. Use format like '7d', '24h', '3w'")


def evaluate_thresholds(
    kpis: dict[str, Any],
    threshold_advisory: float = 0.3,
    threshold_avg_cost: float = 0.01,
    threshold_failure_rate: float = 0.2,
    threshold_grounded: float = 0.6,
    threshold_redacted: float = 0.10,
    min_runs: int = 5,
) -> list[dict[str, Any]]:
    """
    Evaluate KPIs against thresholds and return alerts.

    Args:
        kpis: KPIs dictionary from summarize_kpis()
        threshold_advisory: Maximum acceptable advisory rate (0.0-1.0)
        threshold_avg_cost: Maximum acceptable average cost per run
        threshold_failure_rate: Maximum acceptable failure rate (0.0-1.0)
        threshold_grounded: Minimum acceptable grounded rate (0.0-1.0)
        threshold_redacted: Maximum acceptable redacted rate (0.0-1.0)
        min_runs: Minimum runs required for evaluation

    Returns:
        List of alert dictionaries
    """
    alerts = []

    if kpis["total_runs"] < min_runs:
        return alerts  # Not enough data

    # Advisory rate alert
    if kpis["advisory_rate"] > threshold_advisory:
        alerts.append(
            {
                "type": "advisory_rate",
                "severity": "warning" if kpis["advisory_rate"] < threshold_advisory * 1.5 else "critical",
                "message": f"Advisory rate is {kpis['advisory_rate']:.1%}, exceeds threshold of {threshold_advisory:.1%}",
                "value": kpis["advisory_rate"],
                "threshold": threshold_advisory,
                "details": {
                    "total_runs": kpis["total_runs"],
                    "advisory_runs": kpis["advisory_runs"],
                    "top_reasons": kpis["top_failure_reasons"],
                },
            }
        )

    # Average cost alert
    if kpis["avg_cost"] > threshold_avg_cost:
        alerts.append(
            {
                "type": "avg_cost",
                "severity": "warning" if kpis["avg_cost"] < threshold_avg_cost * 1.5 else "critical",
                "message": f"Average cost is ${kpis['avg_cost']:.4f}, exceeds threshold of ${threshold_avg_cost:.4f}",
                "value": kpis["avg_cost"],
                "threshold": threshold_avg_cost,
                "details": {"total_runs": kpis["total_runs"], "provider_mix": kpis["provider_mix"]},
            }
        )

    # Failure rate alert
    failure_rate = kpis.get("failure_rate", 0.0)
    if failure_rate > threshold_failure_rate:
        alerts.append(
            {
                "type": "failure_rate",
                "severity": "critical",
                "message": f"Failure rate is {failure_rate:.1%}, exceeds threshold of {threshold_failure_rate:.1%}",
                "value": failure_rate,
                "threshold": threshold_failure_rate,
                "details": {
                    "total_runs": kpis["total_runs"],
                    "failed_runs": kpis["failed_runs"],
                    "top_reasons": kpis["top_failure_reasons"],
                },
            }
        )

    # Grounded rate alert
    grounded_rate = kpis.get("grounded_rate", 0.0)
    if grounded_rate < threshold_grounded:
        alerts.append(
            {
                "type": "grounded_rate",
                "severity": "warning",
                "message": f"Grounded rate is {grounded_rate:.1%}, below threshold of {threshold_grounded:.1%}",
                "value": grounded_rate,
                "threshold": threshold_grounded,
                "details": {"total_runs": kpis["total_runs"], "grounded_runs": kpis.get("grounded_runs", 0)},
            }
        )

    # Redacted rate alert
    redacted_rate = kpis.get("redacted_rate", 0.0)
    if redacted_rate > threshold_redacted:
        alerts.append(
            {
                "type": "redacted_rate",
                "severity": "warning" if redacted_rate < threshold_redacted * 1.5 else "critical",
                "message": f"Redacted rate is {redacted_rate:.1%}, exceeds threshold of {threshold_redacted:.1%}",
                "value": redacted_rate,
                "threshold": threshold_redacted,
                "details": {
                    "total_runs": kpis["total_runs"],
                    "redacted_runs": kpis.get("redacted_runs", 0),
                    "total_redactions": kpis.get("total_redactions", 0),
                },
            }
        )

    return alerts


def format_slack_payload(alerts: list[dict[str, Any]], period: str, total_runs: int) -> dict[str, Any]:
    """
    Format alerts as Slack-compatible webhook payload.

    Args:
        alerts: List of alert dictionaries
        period: Time period for the analysis
        total_runs: Total number of runs analyzed

    Returns:
        Slack webhook payload dictionary
    """
    if not alerts:
        return {
            "text": f"✅ DJP Workflow Health Check: All systems normal ({total_runs} runs in {period})",
            "attachments": [],
        }

    # Count alerts by severity
    critical_count = sum(1 for alert in alerts if alert["severity"] == "critical")
    warning_count = sum(1 for alert in alerts if alert["severity"] == "warning")

    # Main message
    severity_emoji = "🚨" if critical_count > 0 else "⚠️"
    main_text = f"{severity_emoji} DJP Workflow Alerts: {len(alerts)} issues detected ({total_runs} runs in {period})"

    attachments = []

    for alert in alerts:
        color = "danger" if alert["severity"] == "critical" else "warning"
        emoji = "🚨" if alert["severity"] == "critical" else "⚠️"

        # Format value based on alert type
        if alert["type"] in ["advisory_rate", "failure_rate", "grounded_rate", "redacted_rate"]:
            value_format = f"{alert['value']:.1%}"
            threshold_format = f"{alert['threshold']:.1%}"
        else:  # cost
            value_format = f"${alert['value']:.4f}"
            threshold_format = f"${alert['threshold']:.4f}"

        attachment = {
            "color": color,
            "title": f"{emoji} {alert['type'].replace('_', ' ').title()}",
            "text": alert["message"],
            "fields": [
                {"title": "Current Value", "value": value_format, "short": True},
                {"title": "Threshold", "value": threshold_format, "short": True},
            ],
            "ts": int(datetime.now().timestamp()),
        }

        # Add details for specific alert types
        if alert["type"] == "advisory_rate" and alert["details"]["top_reasons"]:
            reasons_text = ", ".join(list(alert["details"]["top_reasons"].keys())[:3])
            attachment["fields"].append({"title": "Top Reasons", "value": reasons_text, "short": False})

        attachments.append(attachment)

    return {"text": main_text, "attachments": attachments}


def send_webhook(payload: dict[str, Any], webhook_url: str) -> bool:
    """
    Send payload to webhook URL.

    Args:
        payload: JSON payload to send
        webhook_url: Webhook URL

    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.post(webhook_url, json=payload, timeout=10, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to send webhook: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="DJP workflow alerts system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check last 7 days with default thresholds
  python scripts/alerts.py --since 7d

  # Custom thresholds and dry run
  python scripts/alerts.py --since 24h --threshold-advisory 0.4 --threshold-cost 0.005 --dry-run

  # Send to webhook (requires WEBHOOK_URL environment variable)
  export WEBHOOK_URL=https://hooks.slack.com/your/webhook/url
  python scripts/alerts.py --since 7d
        """,
    )

    parser.add_argument("--since", default="7d", help="Time period to analyze (e.g., '7d', '24h', '3w') (default: 7d)")

    parser.add_argument(
        "--threshold-advisory", type=float, default=0.3, help="Advisory rate threshold (0.0-1.0) (default: 0.3)"
    )

    parser.add_argument(
        "--threshold-cost", type=float, default=0.01, help="Average cost threshold in USD (default: 0.01)"
    )

    parser.add_argument(
        "--threshold-failure", type=float, default=0.2, help="Failure rate threshold (0.0-1.0) (default: 0.2)"
    )

    parser.add_argument(
        "--threshold-grounded", type=float, default=0.6, help="Minimum grounded rate threshold (0.0-1.0) (default: 0.6)"
    )

    parser.add_argument(
        "--threshold-redacted",
        type=float,
        default=0.10,
        help="Maximum redacted rate threshold (0.0-1.0) (default: 0.10)",
    )

    parser.add_argument("--min-runs", type=int, default=5, help="Minimum runs required for evaluation (default: 5)")

    parser.add_argument("--webhook-url", help="Webhook URL (overrides WEBHOOK_URL environment variable)")

    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending webhook")

    parser.add_argument("--runs-dir", default="runs", help="Directory containing run artifacts (default: runs)")

    args = parser.parse_args()

    print("DJP Workflow Alerts")
    print("=" * 40)

    # Load runs data
    df = load_runs(args.runs_dir)

    if df.empty:
        print(f"No runs found in {args.runs_dir}/ directory")
        return 0

    # Filter by time period
    try:
        days = parse_time_period(args.since)
        filtered_df = filter_runs_by_date(df, days)
        print(f"Analyzing {len(filtered_df)} runs from last {args.since}")
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if filtered_df.empty:
        print(f"No runs found in the specified time period ({args.since})")
        return 0

    # Calculate KPIs
    kpis = summarize_kpis(filtered_df)

    # Calculate grounded and redacted ratios
    grounded_runs = filtered_df[filtered_df["grounded"] == True].shape[0]
    redacted_runs = filtered_df[filtered_df["redacted"] == True].shape[0]
    total_runs = kpis["total_runs"]

    kpis["grounded_runs"] = grounded_runs
    kpis["grounded_rate"] = grounded_runs / total_runs if total_runs > 0 else 0.0
    kpis["redacted_runs"] = redacted_runs
    kpis["redacted_rate"] = redacted_runs / total_runs if total_runs > 0 else 0.0
    kpis["total_redactions"] = int(filtered_df["redaction_count"].sum())

    print("\nKPI Summary:")
    print(f"  Total Runs: {kpis['total_runs']}")
    print(f"  Advisory Rate: {kpis['advisory_rate']:.1%}")
    print(f"  Average Cost: ${kpis['avg_cost']:.4f}")
    print(f"  Failure Rate: {kpis.get('failure_rate', 0.0):.1%}")
    print(f"  Grounded Rate: {kpis['grounded_rate']:.1%}")
    print(f"  Redacted Rate: {kpis['redacted_rate']:.1%}")

    # Evaluate thresholds
    alerts = evaluate_thresholds(
        kpis,
        threshold_advisory=args.threshold_advisory,
        threshold_avg_cost=args.threshold_cost,
        threshold_failure_rate=args.threshold_failure,
        threshold_grounded=args.threshold_grounded,
        threshold_redacted=args.threshold_redacted,
        min_runs=args.min_runs,
    )

    if not alerts:
        print("\n✅ All metrics within acceptable thresholds")

        if not args.dry_run:
            # Send success notification if webhook configured
            webhook_url = args.webhook_url or os.getenv("WEBHOOK_URL")
            if webhook_url:
                payload = format_slack_payload(alerts, args.since, kpis["total_runs"])
                success = send_webhook(payload, webhook_url)
                print(f"Webhook sent: {'✅' if success else '❌'}")

        return 0

    # Alerts found
    print(f"\n🚨 {len(alerts)} alert(s) triggered:")
    for alert in alerts:
        print(f"  [{alert['severity'].upper()}] {alert['message']}")

    # Format webhook payload
    payload = format_slack_payload(alerts, args.since, kpis["total_runs"])

    if args.dry_run:
        print("\nDry run - would send this payload:")
        print(json.dumps(payload, indent=2))
    else:
        webhook_url = args.webhook_url or os.getenv("WEBHOOK_URL")
        if webhook_url:
            success = send_webhook(payload, webhook_url)
            print(f"\nWebhook sent to {webhook_url}: {'✅' if success else '❌'}")
        else:
            print("\nNo webhook URL configured (set WEBHOOK_URL env var or use --webhook-url)")
            print("Payload would be:")
            print(json.dumps(payload, indent=2))

    return 1 if any(alert["severity"] == "critical" for alert in alerts) else 0


if __name__ == "__main__":
    sys.exit(main())
