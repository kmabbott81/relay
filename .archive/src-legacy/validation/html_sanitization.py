"""HTML sanitization for Gmail rich email.

Sprint 54: Removes unsafe tags, attributes, and CSS from HTML email bodies.
"""

import re

import bleach
from bs4 import BeautifulSoup

# Allowed tags (from spec)
ALLOWED_TAGS = {
    "p",
    "div",
    "span",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "br",
    "hr",
    "blockquote",
    "pre",
    "code",
}

# Allowed attributes per tag
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "table": ["width", "align"],
    "td": ["width", "height", "align", "colspan", "rowspan"],
    "th": ["width", "height", "align", "colspan", "rowspan"],
    "*": ["class", "id", "style"],  # Allowed on any tag
}

# Allowed protocols in URLs
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "cid"]

# Allowed CSS properties (from spec)
ALLOWED_CSS_PROPERTIES = {
    "color",
    "background-color",
    "font-size",
    "font-family",
    "text-align",
    "padding",
    "margin",
    "border",
    "width",
    "height",
}

# Blocked CSS patterns (regex)
BLOCKED_CSS_PATTERNS = [
    r"expression\s*\(",  # IE expression() exploit
    r"url\s*\(\s*javascript:",  # javascript: in url()
    r"@import",  # CSS imports
    r"@font-face",  # Font loading
]


def sanitize_html(html: str) -> tuple[str, dict]:
    """Sanitize HTML email body.

    Removes:
    - Blocked tags (<script>, <iframe>, etc.)
    - Event handlers (onclick, onload, etc.)
    - Dangerous protocols (javascript:, data:)
    - Unsafe CSS (expression(), etc.)

    Args:
        html: Raw HTML string

    Returns:
        Tuple of (sanitized_html, changes_dict)
        where changes_dict contains counts of changes made
    """
    changes = {
        "tag_removed": 0,
        "attr_removed": 0,
        "script_blocked": 0,
        "style_sanitized": 0,
    }

    # Use bleach for initial sanitization
    cleaned = bleach.clean(
        html,
        tags=list(ALLOWED_TAGS),
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,  # Strip disallowed tags instead of escaping
    )

    # Count removed tags (approximate by comparing length)
    if len(cleaned) < len(html):
        changes["tag_removed"] = 1  # At least one tag removed

    # Parse with BeautifulSoup for additional sanitization
    soup = BeautifulSoup(cleaned, "html.parser")

    # Remove event handlers (onclick, onload, etc.)
    for tag in soup.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr.startswith("on"):
                del tag[attr]
                changes["attr_removed"] += 1

    # Sanitize href attributes (check for javascript:)
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("javascript:"):
            del tag["href"]
            changes["script_blocked"] += 1

    # Sanitize src attributes (check for data: protocol, allow cid:)
    for tag in soup.find_all("img", src=True):
        src = tag["src"]
        if src.startswith("data:") and not src.startswith("cid:"):
            del tag["src"]
            changes["script_blocked"] += 1

    # Sanitize inline styles
    for tag in soup.find_all(style=True):
        original_style = tag["style"]
        sanitized_style = sanitize_css(original_style)

        if sanitized_style != original_style:
            changes["style_sanitized"] += 1

        if sanitized_style:
            tag["style"] = sanitized_style
        else:
            del tag["style"]

    return str(soup), changes


def sanitize_css(css: str) -> str:
    """Sanitize inline CSS.

    Args:
        css: CSS string (e.g., "color: red; font-size: 14px")

    Returns:
        Sanitized CSS string
    """
    # Check for blocked patterns
    for pattern in BLOCKED_CSS_PATTERNS:
        if re.search(pattern, css, re.IGNORECASE):
            return ""  # Remove entire style if dangerous pattern found

    # Parse CSS properties
    properties = []
    for declaration in css.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue

        if ":" not in declaration:
            continue

        prop, value = declaration.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()

        # Only allow whitelisted properties
        if prop in ALLOWED_CSS_PROPERTIES:
            properties.append(f"{prop}: {value}")

    return "; ".join(properties)


def extract_cids_from_html(html: str) -> set[str]:
    """Extract all CID references from HTML.

    Parses <img src="cid:..."> tags and returns set of CID values.

    Args:
        html: HTML string

    Returns:
        Set of CID strings (without "cid:" prefix)
    """
    cids = set()

    if not html:
        return cids

    soup = BeautifulSoup(html, "html.parser")

    for img in soup.find_all("img", src=True):
        src = img["src"]
        if src.startswith("cid:"):
            cid = src[4:]  # Remove "cid:" prefix
            cids.add(cid)

    return cids


def validate_cid_references(html: str, inline_images: list) -> None:
    """Validate CID references match inline images.

    Args:
        html: HTML string
        inline_images: List of InlineImage objects

    Raises:
        ValueError: If CID mismatch found
    """
    if not inline_images:
        # If HTML contains cid: refs but no inline images provided
        cids_in_html = extract_cids_from_html(html)
        if cids_in_html:
            raise ValueError(
                f"validation_error_missing_inline_image: HTML references CIDs {cids_in_html} "
                "but no inline images provided"
            )
        return

    cids_in_html = extract_cids_from_html(html)
    provided_cids = {img.cid for img in inline_images}

    # Check for missing inline images
    missing = cids_in_html - provided_cids
    if missing:
        raise ValueError(
            f"validation_error_missing_inline_image: HTML references CIDs {missing} "
            "but they are not in inline images list"
        )

    # Check for orphan inline images (not referenced)
    orphans = provided_cids - cids_in_html
    if orphans:
        raise ValueError(
            f"validation_error_cid_not_referenced: Inline images with CIDs {orphans} " "are not referenced in HTML"
        )
