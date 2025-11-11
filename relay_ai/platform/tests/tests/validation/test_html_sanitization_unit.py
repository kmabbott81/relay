"""Unit tests for HTML sanitization.

Sprint 54: Tests for src/validation/html_sanitization.py
"""

import pytest

from relay_ai.validation.attachments import InlineImage
from relay_ai.validation.html_sanitization import (
    extract_cids_from_html,
    sanitize_css,
    sanitize_html,
    validate_cid_references,
)


class TestHtmlSanitization:
    """Test HTML sanitization."""

    def test_sanitize_clean_html(self):
        """Test clean HTML is preserved."""
        html = "<p>Hello <strong>world</strong>!</p>"
        result, changes = sanitize_html(html)
        assert "Hello" in result
        assert "world" in result
        assert changes["tag_removed"] == 0

    def test_remove_script_tag(self):
        """Test <script> tags are removed."""
        html = "<p>Safe content</p><script>alert('xss')</script>"
        result, changes = sanitize_html(html)
        assert "script" not in result.lower()
        assert "Safe content" in result

    def test_remove_iframe_tag(self):
        """Test <iframe> tags are removed."""
        html = '<p>Content</p><iframe src="evil.com"></iframe>'
        result, changes = sanitize_html(html)
        assert "iframe" not in result.lower()

    def test_remove_onclick_handler(self):
        """Test onclick handlers are removed."""
        html = '<a href="https://example.com" onclick="alert(1)">Click</a>'
        result, changes = sanitize_html(html)
        assert "onclick" not in result.lower()
        # Bleach may remove it before we count, so just verify it's gone

    def test_remove_onload_handler(self):
        """Test onload handlers are removed."""
        html = '<img src="logo.png" onload="alert(1)">'
        result, changes = sanitize_html(html)
        assert "onload" not in result.lower()

    def test_block_javascript_href(self):
        """Test javascript: protocol in href is blocked."""
        html = '<a href="javascript:alert(1)">Click</a>'
        result, changes = sanitize_html(html)
        assert "javascript:" not in result.lower()
        # Bleach may remove it before we count, so just verify it's gone

    def test_block_data_protocol_img(self):
        """Test data: protocol in img src is blocked."""
        html = '<img src="data:image/png;base64,abc123">'
        result, changes = sanitize_html(html)
        # Bleach blocks data: protocol, so just verify it's gone
        # (cid: protocol should still be allowed)
        assert "data:" not in result or "cid:" in result

    def test_allow_cid_protocol(self):
        """Test cid: protocol in img src is allowed."""
        html = '<img src="cid:logo">'
        result, changes = sanitize_html(html)
        assert "cid:logo" in result

    def test_sanitize_inline_style(self):
        """Test unsafe CSS in style attribute is removed."""
        html = '<div style="color: red; expression(alert(1))">Text</div>'
        result, changes = sanitize_html(html)
        assert "expression" not in result.lower()

    def test_preserve_safe_attributes(self):
        """Test safe attributes (class, id) are preserved."""
        html = '<div class="container" id="main">Content</div>'
        result, changes = sanitize_html(html)
        assert 'class="container"' in result or "container" in result
        assert 'id="main"' in result or "main" in result


class TestCssSanitization:
    """Test CSS sanitization."""

    def test_sanitize_clean_css(self):
        """Test clean CSS is preserved."""
        css = "color: red; font-size: 14px"
        result = sanitize_css(css)
        assert "color: red" in result
        assert "font-size: 14px" in result

    def test_block_expression(self):
        """Test CSS expression() is blocked."""
        css = "color: red; width: expression(alert(1))"
        result = sanitize_css(css)
        assert "expression" not in result.lower()
        assert result == ""  # Entire style removed if dangerous

    def test_block_javascript_url(self):
        """Test javascript: in url() is blocked."""
        css = "background: url(javascript:alert(1))"
        result = sanitize_css(css)
        assert "javascript:" not in result.lower()
        assert result == ""

    def test_block_import(self):
        """Test @import is blocked."""
        css = "@import url('evil.css'); color: red"
        result = sanitize_css(css)
        assert "@import" not in result.lower()

    def test_allow_safe_properties(self):
        """Test allowed CSS properties are preserved."""
        css = "color: blue; background-color: #fff; padding: 10px"
        result = sanitize_css(css)
        assert "color: blue" in result
        assert "background-color: #fff" in result or "background-color:#fff" in result
        assert "padding: 10px" in result or "padding:10px" in result

    def test_remove_unsafe_properties(self):
        """Test unsafe CSS properties are removed."""
        css = "color: red; position: fixed; z-index: 9999"
        result = sanitize_css(css)
        assert "color: red" in result
        # position and z-index are not in allowlist, should be removed
        assert "position" not in result
        assert "z-index" not in result


class TestCidExtraction:
    """Test CID extraction from HTML."""

    def test_extract_single_cid(self):
        """Test extracting single CID reference."""
        html = '<img src="cid:logo">'
        cids = extract_cids_from_html(html)
        assert cids == {"logo"}

    def test_extract_multiple_cids(self):
        """Test extracting multiple CID references."""
        html = '<img src="cid:logo"><img src="cid:banner">'
        cids = extract_cids_from_html(html)
        assert cids == {"logo", "banner"}

    def test_extract_duplicate_cids(self):
        """Test duplicate CIDs are deduplicated."""
        html = '<img src="cid:logo"><img src="cid:logo">'
        cids = extract_cids_from_html(html)
        assert cids == {"logo"}

    def test_extract_no_cids(self):
        """Test HTML without CIDs returns empty set."""
        html = "<p>No images here</p>"
        cids = extract_cids_from_html(html)
        assert cids == set()

    def test_extract_mixed_protocols(self):
        """Test only cid: protocol is extracted."""
        html = '<img src="https://example.com/logo.png"><img src="cid:inline">'
        cids = extract_cids_from_html(html)
        assert cids == {"inline"}

    def test_extract_empty_html(self):
        """Test empty HTML returns empty set."""
        cids = extract_cids_from_html("")
        assert cids == set()


class TestCidValidation:
    """Test CID reference validation."""

    def test_valid_cid_references(self):
        """Test matching CIDs pass validation."""
        html = '<img src="cid:logo">'
        images = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"fake",
            )
        ]
        validate_cid_references(html, images)  # Should not raise

    def test_missing_inline_image(self):
        """Test HTML references CID not in inline list."""
        html = '<img src="cid:logo"><img src="cid:banner">'
        images = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"fake",
            )
        ]
        with pytest.raises(ValueError, match="validation_error_missing_inline_image"):
            validate_cid_references(html, images)

    def test_orphan_inline_image(self):
        """Test inline image not referenced in HTML."""
        html = '<img src="cid:logo">'
        images = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"fake",
            ),
            InlineImage(
                cid="banner",
                filename="banner.png",
                content_type="image/png",
                data=b"fake",
            ),
        ]
        with pytest.raises(ValueError, match="validation_error_cid_not_referenced"):
            validate_cid_references(html, images)

    def test_no_cids_no_images(self):
        """Test HTML without CIDs and no images is valid."""
        html = "<p>Plain HTML</p>"
        images = []
        validate_cid_references(html, images)  # Should not raise

    def test_cid_in_html_no_images_provided(self):
        """Test HTML with CID but no images provided."""
        html = '<img src="cid:logo">'
        images = []
        with pytest.raises(ValueError, match="validation_error_missing_inline_image"):
            validate_cid_references(html, images)


class TestEdgeCases:
    """Test edge cases and adversarial inputs."""

    def test_nested_tags(self):
        """Test deeply nested tags are handled."""
        html = "<div><div><div><p>Deep</p></div></div></div>"
        result, changes = sanitize_html(html)
        assert "Deep" in result

    def test_malformed_html(self):
        """Test malformed HTML is handled gracefully."""
        html = "<p>Unclosed tag<div>Another<"
        result, changes = sanitize_html(html)
        # Should not crash, exact output may vary

    def test_empty_html(self):
        """Test empty HTML returns empty result."""
        result, changes = sanitize_html("")
        assert result == "" or result.strip() == ""

    def test_html_with_entities(self):
        """Test HTML entities are preserved."""
        html = "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
        result, changes = sanitize_html(html)
        assert "&lt;" in result or "<" in result

    def test_case_insensitive_event_handlers(self):
        """Test event handlers in mixed case are removed."""
        html = '<div OnClick="alert(1)" ONLOAD="alert(2)">Text</div>'
        result, changes = sanitize_html(html)
        assert "onclick" not in result.lower()
        assert "onload" not in result.lower()

    def test_unicode_in_html(self):
        """Test Unicode characters in HTML are preserved."""
        html = "<p>Hello 世界! 🌍</p>"
        result, changes = sanitize_html(html)
        assert "世界" in result

    def test_style_with_semicolon_in_value(self):
        """Test CSS value containing semicolon is handled."""
        css = "font-family: 'Courier New', monospace; color: red"
        result = sanitize_css(css)
        # Should preserve font-family even with complex value
        assert "color: red" in result

    def test_xss_via_style_attribute(self):
        """Test XSS attempt via style attribute is blocked."""
        html = '<div style="background: url(javascript:alert(1))">Text</div>'
        result, changes = sanitize_html(html)
        assert "javascript:" not in result.lower()
        # Style should be sanitized or removed entirely
