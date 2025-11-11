"""Generate sample MIME messages for golden cases.

Sprint 54: Demonstrates the three main MIME structures.
"""

from relay_ai.actions.adapters.google_mime import MimeBuilder
from relay_ai.validation.attachments import Attachment, InlineImage


def generate_samples():
    """Generate three golden case MIME samples."""
    builder = MimeBuilder()

    print("=" * 80)
    print("GOLDEN CASE 1: Text-only message")
    print("=" * 80)

    sample1 = builder.build_message(
        to="alice@example.com",
        subject="Weekly Status Report",
        text="Hi Alice,\n\nThis week's progress:\n- Completed MIME builder\n- All tests passing\n\nBest,\nBob",
    )
    print(sample1)
    print("\n")

    print("=" * 80)
    print("GOLDEN CASE 2: HTML + inline image")
    print("=" * 80)

    html2 = """<html>
<body>
<h1>Product Launch</h1>
<p>We're excited to announce our new product:</p>
<p><img src="cid:logo" alt="Product Logo" width="200"></p>
<p>Learn more at <a href="https://example.com">our website</a>.</p>
</body>
</html>"""

    # Fake 50-byte PNG data
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 42

    sample2 = builder.build_message(
        to="team@example.com",
        subject="Product Launch Announcement",
        text="Product Launch\n\nWe're excited to announce our new product. Learn more at https://example.com",
        html=html2,
        inline=[
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=fake_png,
            )
        ],
    )
    print(sample2)
    print("\n")

    print("=" * 80)
    print("GOLDEN CASE 3: HTML + inline image + 2 attachments")
    print("=" * 80)

    html3 = """<html>
<body>
<h1>Q4 Results</h1>
<p>Please find attached our Q4 financial results.</p>
<p><img src="cid:chart" alt="Revenue Chart" width="400"></p>
<p>Attachments:</p>
<ul>
  <li>Q4_Report.pdf - Full detailed report</li>
  <li>Data.xlsx - Raw data spreadsheet</li>
</ul>
</body>
</html>"""

    # Fake chart image (100 bytes)
    fake_chart = b"CHART_DATA" * 10

    # Fake PDF (200 bytes)
    fake_pdf = b"%PDF-1.4" + b"\x00" * 192

    # Fake Excel (200 bytes)
    fake_excel = b"PK\x03\x04" + b"\x00" * 196

    sample3 = builder.build_message(
        to="board@example.com",
        subject="Q4 Financial Results",
        text="Q4 Results\n\nPlease find attached our Q4 financial results.\n\nAttachments:\n- Q4_Report.pdf\n- Data.xlsx",
        html=html3,
        cc=["cfo@example.com"],
        inline=[
            InlineImage(
                cid="chart",
                filename="revenue_chart.png",
                content_type="image/png",
                data=fake_chart,
            )
        ],
        attachments=[
            Attachment(
                filename="Q4_Report.pdf",
                content_type="application/pdf",
                data=fake_pdf,
            ),
            Attachment(
                filename="Data.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                data=fake_excel,
            ),
        ],
    )
    print(sample3)
    print("\n")

    print("=" * 80)
    print("Summary:")
    print(f"Sample 1 size: {len(sample1)} bytes (text-only)")
    print(f"Sample 2 size: {len(sample2)} bytes (HTML + 1 inline image)")
    print(f"Sample 3 size: {len(sample3)} bytes (HTML + 1 inline + 2 attachments)")
    print("=" * 80)


if __name__ == "__main__":
    generate_samples()
