#!/usr/bin/env python3
"""
Relay AI Beta User Invitation Script
Sends beta invites and tracks onboarding
"""

import asyncio
import os
from datetime import datetime

from resend import Resend

# Install: pip install supabase resend
from supabase import Client, create_client

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
APP_URL = os.getenv("NEXT_PUBLIC_APP_URL", "https://relay-beta.vercel.app")

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
resend = Resend(RESEND_API_KEY) if RESEND_API_KEY else None

# Beta user list (update with your beta testers)
BETA_USERS = [
    {"email": "founder@example.com", "name": "Founder", "company": "Self", "tier": "unlimited"},
    {"email": "advisor@example.com", "name": "Advisor", "company": "Advisory", "tier": "pro"},
    {"email": "friend1@example.com", "name": "Friend 1", "company": "Startup A", "tier": "beta"},
    {"email": "friend2@example.com", "name": "Friend 2", "company": "Startup B", "tier": "beta"},
    # Add more beta users here
]

INVITE_EMAIL_TEMPLATE = """
Hi {name},

You're invited to the Relay AI private beta! 🎉

Relay is a secure AI assistant that's 70% cheaper than Copilot, deploys in 5 minutes, and proves your data stays private with daily security reports.

**Your Beta Access:**
- 100 free queries per day
- Upload unlimited documents
- Full security dashboard
- Direct founder support

**Get Started:**
1. Click here to activate: {magic_link}
2. Upload your first document
3. Try a search query
4. Send feedback directly in-app

**What We're Testing:**
- Knowledge base search accuracy
- Upload/indexing speed
- Security transparency features
- Overall user experience

**Beta Perks:**
- 50% off for life when we launch
- Direct access to founder for feature requests
- Your company logo on our "Beta Champions" page
- First access to new features

Questions? Reply directly to this email.

Welcome aboard!

Kyle & the Relay Team

P.S. Join our beta Slack: {slack_invite_link}
"""


async def create_beta_user(user: dict) -> str:
    """Create user in Supabase and return magic link"""
    try:
        # Create auth user with magic link
        result = supabase.auth.admin.create_user(
            {
                "email": user["email"],
                "email_confirm": True,  # Auto-confirm for beta
                "user_metadata": {
                    "full_name": user["name"],
                    "company": user["company"],
                    "beta_tier": user.get("tier", "beta"),
                    "invited_at": datetime.utcnow().isoformat(),
                },
            }
        )

        # Generate magic link
        magic_link_result = supabase.auth.admin.generate_link({"type": "magiclink", "email": user["email"]})

        # Update profile with beta settings
        if result.user:
            supabase.table("profiles").upsert(
                {
                    "id": result.user.id,
                    "email": user["email"],
                    "full_name": user["name"],
                    "company": user["company"],
                    "role": "beta_user",
                    "beta_access": True,
                    "usage_limit": 100 if user.get("tier") == "beta" else 1000,
                }
            ).execute()

        return magic_link_result.properties.action_link

    except Exception as e:
        print(f"Error creating user {user['email']}: {e}")
        return None


async def send_invite_email(user: dict, magic_link: str):
    """Send invitation email via Resend or log to console"""

    email_content = INVITE_EMAIL_TEMPLATE.format(
        name=user["name"],
        magic_link=magic_link,
        slack_invite_link="https://join.slack.com/relay-beta",  # Update with real link
    )

    if resend:
        try:
            resend.emails.send(
                {
                    "from": "Kyle <kyle@relay.ai>",
                    "to": [user["email"]],
                    "subject": "🚀 Welcome to Relay AI Beta",
                    "html": email_content.replace("\n", "<br>"),
                    "reply_to": "kyle@relay.ai",
                }
            )
            print(f"✓ Sent invite to {user['email']}")
        except Exception as e:
            print(f"✗ Failed to send email to {user['email']}: {e}")
    else:
        # Fallback: Log magic link for manual sending
        print(f"\n{'='*50}")
        print(f"Manual invite for {user['name']} ({user['email']}):")
        print(f"Magic Link: {magic_link}")
        print(f"{'='*50}\n")


async def setup_demo_data(user_id: str):
    """Pre-populate demo data for better first experience"""

    demo_files = [
        {
            "user_id": user_id,
            "filename": "Welcome to Relay AI.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "storage_path": "demo/welcome.pdf",
        },
        {
            "user_id": user_id,
            "filename": "Security Whitepaper.pdf",
            "content_type": "application/pdf",
            "size_bytes": 2048,
            "storage_path": "demo/security.pdf",
        },
    ]

    # Insert demo files
    for file in demo_files:
        supabase.table("files").insert(file).execute()

    print(f"  Added demo files for user {user_id}")


async def main():
    """Main invitation flow"""

    print("🚀 Relay AI Beta Invitation Script")
    print("==================================\n")

    # Verify connection
    try:
        supabase.table("profiles").select("count").execute()
        print("✓ Connected to Supabase\n")
    except Exception as e:
        print(f"✗ Failed to connect to Supabase: {e}")
        return

    # Process invitations
    invited = []
    failed = []

    for user in BETA_USERS:
        print(f"Processing {user['email']}...")

        # Check if already exists
        existing = supabase.table("profiles").select("id").eq("email", user["email"]).execute()
        if existing.data:
            print("  → Already exists, skipping")
            continue

        # Create user and get magic link
        magic_link = await create_beta_user(user)
        if magic_link:
            # Send invite
            await send_invite_email(user, magic_link)
            invited.append(user["email"])

            # Optional: Setup demo data
            # await setup_demo_data(user_result.user.id)
        else:
            failed.append(user["email"])

    # Summary
    print("\n" + "=" * 50)
    print("📊 Invitation Summary")
    print("=" * 50)
    print(f"✓ Successfully invited: {len(invited)}")
    for email in invited:
        print(f"  - {email}")

    if failed:
        print(f"\n✗ Failed invitations: {len(failed)}")
        for email in failed:
            print(f"  - {email}")

    print("\n📋 Next Steps:")
    print("1. Check Supabase dashboard for new users")
    print("2. Monitor feedback table for beta responses")
    print("3. Join Slack to support beta users")
    print("4. Review usage metrics daily\n")


def track_metrics():
    """Quick function to check beta metrics"""

    # Get metrics
    users = supabase.table("profiles").select("*").eq("beta_access", True).execute()
    queries = supabase.table("queries").select("count").execute()
    files = supabase.table("files").select("count").execute()
    feedback = supabase.table("feedback").select("*").order("created_at", desc=True).limit(5).execute()

    print("\n📊 Beta Metrics Dashboard")
    print("=" * 50)
    print(f"Total Beta Users: {len(users.data) if users.data else 0}")
    print(f"Total Queries: {queries.data[0]['count'] if queries.data else 0}")
    print(f"Total Files Uploaded: {files.data[0]['count'] if files.data else 0}")

    if feedback.data:
        print("\n📝 Recent Feedback:")
        for item in feedback.data:
            print(f"  - {item['type']}: {item['message'][:50]}...")

    print("\n💰 Usage Today:")
    for user in (users.data or [])[:5]:
        print(f"  {user['email']}: {user.get('usage_today', 0)}/{user.get('usage_limit', 100)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "metrics":
        track_metrics()
    else:
        asyncio.run(main())

"""
Usage:
1. Set environment variables in .env
2. Run: python scripts/invite_beta_users.py
3. Check metrics: python scripts/invite_beta_users.py metrics
"""
