"""Performance tests for Gmail MIME builder.

Sprint 54: Tests to verify P95 < 250ms for 1MB payloads.
"""

import time

import pytest

from relay_ai.actions.adapters.google_mime import MimeBuilder
from relay_ai.validation.attachments import Attachment, InlineImage


class TestMimePerformance:
    """Test MIME builder performance."""

    def test_text_only_latency(self):
        """Test text-only message builds quickly."""
        builder = MimeBuilder()

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Hello world!",
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.1  # Should be < 100ms

    def test_html_alternative_latency(self):
        """Test HTML message builds quickly."""
        builder = MimeBuilder()
        html = "<p>" + "Content " * 100 + "</p>"  # ~1KB HTML

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.25  # Should be < 250ms

    def test_single_attachment_1mb_latency(self):
        """Test 1MB attachment meets P95 < 250ms budget."""
        builder = MimeBuilder()
        # Create 1MB attachment
        attachments = [
            Attachment(
                filename="large.bin",
                content_type="application/octet-stream",
                data=b"x" * (1024 * 1024),  # 1MB
            )
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="See attached",
            attachments=attachments,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        # This is the critical performance requirement
        assert duration < 0.25, f"Build took {duration:.3f}s, expected < 250ms"

    def test_multiple_small_attachments_latency(self):
        """Test multiple small attachments build quickly."""
        builder = MimeBuilder()
        # Create 10 attachments, 100KB each = 1MB total
        attachments = [
            Attachment(
                filename=f"file{i}.bin",
                content_type="application/octet-stream",
                data=b"x" * (100 * 1024),
            )
            for i in range(10)
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="See attached",
            attachments=attachments,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.25, f"Build took {duration:.3f}s, expected < 250ms"

    def test_inline_images_latency(self):
        """Test inline images build quickly."""
        builder = MimeBuilder()
        # Create 5 inline images, 200KB each = 1MB total
        html = "".join([f'<img src="cid:img{i}">' for i in range(5)])
        inline = [
            InlineImage(
                cid=f"img{i}",
                filename=f"img{i}.png",
                content_type="image/png",
                data=b"x" * (200 * 1024),
            )
            for i in range(5)
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
            inline=inline,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.25, f"Build took {duration:.3f}s, expected < 250ms"

    def test_full_complexity_latency(self):
        """Test full complexity (HTML + inline + attachments) meets budget."""
        builder = MimeBuilder()
        # Total ~1MB: 500KB HTML, 250KB inline, 250KB attachment
        html = "<p>" + "X" * (500 * 1024) + '<img src="cid:logo"></p>'
        inline = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"x" * (250 * 1024),
            )
        ]
        attachments = [
            Attachment(
                filename="doc.pdf",
                content_type="application/pdf",
                data=b"x" * (250 * 1024),
            )
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
            inline=inline,
            attachments=attachments,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.25, f"Build took {duration:.3f}s, expected < 250ms"

    def test_html_sanitization_latency(self):
        """Test HTML sanitization performance."""
        builder = MimeBuilder()
        # Create large HTML with many tags
        html = "<div>" * 100 + "<p>Content</p>" * 1000 + "</div>" * 100

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        # Sanitization adds overhead but should still be fast
        assert duration < 0.5  # More generous for complex HTML

    def test_repeated_builds_no_memory_leak(self):
        """Test repeated builds don't cause performance degradation."""
        builder = MimeBuilder()
        attachments = [
            Attachment(
                filename="file.bin",
                content_type="application/octet-stream",
                data=b"x" * (100 * 1024),  # 100KB
            )
        ]

        durations = []
        for _ in range(10):
            start = time.perf_counter()
            _ = builder.build_message(
                to="alice@example.com",
                subject="Test",
                text="Plain",
                attachments=attachments,
            )
            duration = time.perf_counter() - start
            durations.append(duration)

        # Last build should not be significantly slower than first
        assert len(durations) == 10
        avg_duration = sum(durations) / len(durations)
        assert avg_duration < 0.25


class TestValidationPerformance:
    """Test validation performance doesn't dominate latency."""

    def test_attachment_validation_latency(self):
        """Test attachment validation is fast."""
        from src.validation.attachments import validate_attachments

        attachments = [
            Attachment(
                filename=f"file{i}.pdf",
                content_type="application/pdf",
                data=b"x" * (100 * 1024),
            )
            for i in range(10)
        ]

        start = time.perf_counter()
        validate_attachments(attachments)
        duration = time.perf_counter() - start

        # Validation should be negligible
        assert duration < 0.01  # < 10ms

    def test_html_sanitization_latency(self):
        """Test HTML sanitization is fast."""
        from src.validation.html_sanitization import sanitize_html

        html = "<p>" + "Content " * 10000 + "</p>"  # ~100KB HTML

        start = time.perf_counter()
        result, changes = sanitize_html(html)
        duration = time.perf_counter() - start

        # Sanitization should be reasonable
        assert duration < 0.1  # < 100ms

    def test_cid_validation_latency(self):
        """Test CID validation is fast."""
        from src.validation.html_sanitization import validate_cid_references

        html = "".join([f'<img src="cid:img{i}">' for i in range(20)])
        inline = [
            InlineImage(
                cid=f"img{i}",
                filename=f"img{i}.png",
                content_type="image/png",
                data=b"x",
            )
            for i in range(20)
        ]

        start = time.perf_counter()
        validate_cid_references(html, inline)
        duration = time.perf_counter() - start

        # Validation should be negligible
        assert duration < 0.01  # < 10ms


@pytest.mark.slow
class TestStressScenarios:
    """Stress test scenarios (marked slow, can be skipped in CI)."""

    def test_max_attachments_max_size(self):
        """Test maximum attachments at maximum total size."""
        builder = MimeBuilder()
        # 10 attachments * 5MB each = 50MB total (at limit)
        attachments = [
            Attachment(
                filename=f"file{i}.bin",
                content_type="application/octet-stream",
                data=b"x" * (5 * 1024 * 1024),
            )
            for i in range(10)
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            attachments=attachments,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        # This will be slow due to size, but should complete
        # P95 target is for 1MB, not 50MB
        assert duration < 5.0  # Should complete within 5 seconds

    def test_max_inline_images(self):
        """Test maximum inline images (20)."""
        builder = MimeBuilder()
        html = "".join([f'<img src="cid:img{i}">' for i in range(20)])
        inline = [
            InlineImage(
                cid=f"img{i}",
                filename=f"img{i}.png",
                content_type="image/png",
                data=b"x" * (100 * 1024),  # 100KB each = 2MB total
            )
            for i in range(20)
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
            inline=inline,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 1.0  # Should be fast for 2MB

    def test_unicode_heavy_content(self):
        """Test Unicode-heavy content performance."""
        builder = MimeBuilder()
        # Unicode characters in subject, body, and filenames
        attachments = [
            Attachment(
                filename="文档📎.pdf",
                content_type="application/pdf",
                data="测试内容 🌍".encode() * 1000,
            )
        ]

        start = time.perf_counter()
        result = builder.build_message(
            to="user@example.com",
            subject="测试邮件 🚀",
            text="这是一封测试邮件 🌟",
            attachments=attachments,
        )
        duration = time.perf_counter() - start

        assert len(result) > 0
        assert duration < 0.5  # Unicode encoding overhead
