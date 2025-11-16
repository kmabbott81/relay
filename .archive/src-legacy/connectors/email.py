"""Email connector for sending notifications and fetching messages."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


def send_notification(
    subject: str,
    body: str,
    to_email: str,
    from_email: Optional[str] = None,
    smtp_host: Optional[str] = None,
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> bool:
    """
    Send email notification via SMTP.

    Args:
        subject: Email subject
        body: Email body (plain text or HTML)
        to_email: Recipient email address
        from_email: Sender email (defaults to SMTP_FROM_EMAIL env var)
        smtp_host: SMTP server (defaults to SMTP_HOST env var)
        smtp_port: SMTP port (default: 587)
        smtp_user: SMTP username (defaults to SMTP_USER env var)
        smtp_password: SMTP password (defaults to SMTP_PASSWORD env var)

    Returns:
        Success status

    Environment Variables:
        SMTP_HOST: SMTP server hostname
        SMTP_PORT: SMTP server port
        SMTP_USER: SMTP username
        SMTP_PASSWORD: SMTP password
        SMTP_FROM_EMAIL: Default sender email

    Example:
        >>> send_notification(
        ...     subject="Approval Required",
        ...     body="A new template output requires your approval.",
        ...     to_email="admin@example.com"
        ... )
    """
    # Use env vars as defaults
    smtp_host = smtp_host or os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", smtp_port))
    smtp_user = smtp_user or os.getenv("SMTP_USER")
    smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
    from_email = from_email or os.getenv("SMTP_FROM_EMAIL", smtp_user)

    if not all([smtp_host, smtp_user, smtp_password, from_email]):
        print("Warning: SMTP credentials not configured. Skipping email send.")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach body
        msg.attach(MIMEText(body, "plain"))

        # Connect and send
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        print(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_approval_notification(
    template_name: str,
    preview_text: str,
    artifact_id: str,
    approver_email: str,
    approval_url: Optional[str] = None,
) -> bool:
    """
    Send approval notification for template output.

    Args:
        template_name: Name of template
        preview_text: Preview of output text
        artifact_id: Artifact identifier
        approver_email: Email of approver
        approval_url: Optional URL to approval UI

    Returns:
        Success status
    """
    subject = f"Approval Required: {template_name}"

    body = f"""
A new template output requires your approval.

Template: {template_name}
Artifact ID: {artifact_id}

Preview:
{preview_text[:500]}...

"""

    if approval_url:
        body += f"\nApprove or reject at: {approval_url}\n"

    body += "\n-- DJP Workflow Platform"

    return send_notification(subject, body, approver_email)


# IMAP fetch stubs (not implemented - placeholder for future)
def fetch_messages(mailbox: str = "INBOX", limit: int = 10) -> list[dict]:
    """Fetch recent messages from IMAP server (stub)."""
    print("IMAP fetch not implemented. Configure IMAP_HOST, IMAP_USER, IMAP_PASSWORD.")
    return []
