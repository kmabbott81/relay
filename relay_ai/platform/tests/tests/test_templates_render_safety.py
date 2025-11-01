"""Tests for Jinja2 sandbox and render safety."""

from pathlib import Path

import pytest

from src.templates import InputDef, TemplateDef, TemplateRenderError, render_template, to_slug, to_title


def create_test_template(body: str, context: str = "markdown") -> TemplateDef:
    """Helper to create a minimal test template."""
    return TemplateDef(
        path=Path("test.yaml"),
        name="Test Template",
        version="1.0",
        description="Test",
        context=context,
        inputs=[
            InputDef(id="name", label="Name", type="string", default="World"),
            InputDef(id="value", label="Value", type="int", default=42),
        ],
        body=body,
    )


def test_basic_render():
    """Basic template rendering should work."""
    template = create_test_template("Hello {{name}}!")
    result = render_template(template, {"name": "Alice"})
    assert result == "Hello Alice!"


def test_safe_filters_work():
    """Safe filters should be available and work."""
    template = create_test_template("{{name|upper}} {{name|lower}} {{name|title}} {{name|length}} {{value|round}}")
    result = render_template(template, {"name": "test", "value": 42.7})
    assert "TEST" in result
    assert "test" in result
    assert "Test" in result
    assert "4" in result
    assert "43" in result


def test_custom_filters():
    """Custom filters (to_slug, to_title) should work."""
    template = create_test_template("{{name|to_slug}} {{name|to_title}}")
    result = render_template(template, {"name": "Hello World!"})
    assert "hello-world" in result
    assert "Hello World!" in result


def test_join_filter():
    """Join filter should work for lists."""
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[
            InputDef(
                id="items", label="Items", type="multiselect", default=[], validators={"choices": ["a", "b", "c", "d"]}
            )
        ],
        body="{{items|join(', ')}}",
    )

    result = render_template(template, {"items": ["a", "b", "c"]})
    assert result == "a, b, c"


def test_undefined_variable_fails():
    """Using undefined variable should fail with StrictUndefined."""
    template = create_test_template("Hello {{undefined_var}}!")

    with pytest.raises(TemplateRenderError) as exc_info:
        render_template(template, {"name": "Alice"})

    assert "undefined" in str(exc_info.value).lower() or "template" in str(exc_info.value).lower()


def test_html_context_autoescapes():
    """HTML context should autoescape dangerous characters."""
    template = create_test_template("<div>{{name}}</div>", context="html")
    result = render_template(template, {"name": "<script>alert('xss')</script>"})
    # Should be escaped
    assert "&lt;" in result or "script" not in result.lower() or result.count("<") == 2  # Only div tags


def test_docx_context_autoescapes():
    """DOCX context should autoescape dangerous characters."""
    template = create_test_template("Content: {{name}}", context="docx")
    result = render_template(template, {"name": "<tag>content</tag>"})
    # Should be escaped
    assert "&lt;" in result or "<tag>" not in result


def test_markdown_context_no_autoescape():
    """Markdown context should not autoescape by default."""
    template = create_test_template("# {{name}}", context="markdown")
    result = render_template(template, {"name": "**Bold**"})
    # Should not be escaped
    assert "**Bold**" in result


def test_explicit_escape_filter_markdown():
    """Explicit escape filter should work in markdown context."""
    template = create_test_template("{{name|e}}", context="markdown")
    result = render_template(template, {"name": "<script>"})
    assert "&lt;" in result


def test_sandbox_blocks_attr_access():
    """Sandbox should block access to dangerous attributes."""
    # Attempt to access __class__ or similar should be blocked
    template = create_test_template("{{name.__class__}}")

    with pytest.raises(TemplateRenderError):
        render_template(template, {"name": "test"})


def test_to_slug_function():
    """to_slug should create URL-safe slugs."""
    assert to_slug("Hello World") == "hello-world"
    assert to_slug("Test  Multiple   Spaces") == "test-multiple-spaces"
    assert to_slug("Special!@#$%Characters") == "specialcharacters"
    assert to_slug("  Leading and Trailing  ") == "leading-and-trailing"


def test_to_title_function():
    """to_title should title-case text."""
    assert to_title("hello world") == "Hello World"
    assert to_title("UPPERCASE") == "Uppercase"
    assert to_title("mixedCase") == "Mixedcase"
