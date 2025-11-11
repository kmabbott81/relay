"""Tests for template compilation caching."""

from pathlib import Path

from relay_ai.templates import (
    InputDef,
    TemplateDef,
    clear_template_cache,
    get_cache_stats,
    render_template,
)


def test_cache_miss_on_first_render():
    """First render should be a cache miss."""
    clear_template_cache()

    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hello {{name}}",
    )

    # First render - cache miss
    result = render_template(template, {"name": "Alice"})
    assert result == "Hello Alice"

    stats = get_cache_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_hit_on_second_render():
    """Second render with same template should be a cache hit."""
    clear_template_cache()

    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hello {{name}}",
    )

    # First render
    render_template(template, {"name": "Alice"})

    # Second render - should hit cache
    result = render_template(template, {"name": "Bob"})
    assert result == "Hello Bob"

    stats = get_cache_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 1


def test_cache_invalidated_on_body_change():
    """Changing template body should invalidate cache."""
    clear_template_cache()

    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hello {{name}}",
    )

    # First render
    render_template(template, {"name": "Alice"})

    # Change template body
    template.body = "Hi {{name}}"

    # Second render with changed body - should be cache miss
    result = render_template(template, {"name": "Bob"})
    assert result == "Hi Bob"

    stats = get_cache_stats()
    assert stats["misses"] == 2  # Two misses due to body change
    assert stats["hits"] == 0


def test_cache_independent_per_template():
    """Different templates should have independent cache entries."""
    clear_template_cache()

    template1 = TemplateDef(
        path=Path("test1.yaml"),
        name="Test1",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hello {{name}}",
    )

    template2 = TemplateDef(
        path=Path("test2.yaml"),
        name="Test2",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hi {{name}}",
    )

    # Render both templates
    render_template(template1, {"name": "Alice"})
    render_template(template2, {"name": "Bob"})

    stats = get_cache_stats()
    assert stats["misses"] == 2  # Both are cache misses
    assert stats["hits"] == 0

    # Render again - should hit cache for both
    render_template(template1, {"name": "Charlie"})
    render_template(template2, {"name": "Dave"})

    stats = get_cache_stats()
    assert stats["misses"] == 2
    assert stats["hits"] == 2


def test_clear_cache():
    """Clearing cache should reset all entries and stats."""
    clear_template_cache()

    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body="Hello {{name}}",
    )

    # Render to populate cache
    render_template(template, {"name": "Alice"})
    render_template(template, {"name": "Bob"})

    # Clear cache
    clear_template_cache()

    stats = get_cache_stats()
    assert stats["misses"] == 0
    assert stats["hits"] == 0

    # Render again - should be cache miss
    render_template(template, {"name": "Charlie"})

    stats = get_cache_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_with_complex_template():
    """Cache should work with complex templates."""
    clear_template_cache()

    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[
            InputDef(id="title", label="Title", type="string"),
            InputDef(id="items", label="Items", type="text"),
        ],
        body="""# {{title}}

{% for item in items.split('\\n') %}
- {{item}}
{% endfor %}""",
    )

    # First render
    result1 = render_template(template, {"title": "My List", "items": "Item 1\nItem 2\nItem 3"})
    assert "# My List" in result1
    assert "- Item 1" in result1

    # Second render - cache hit
    result2 = render_template(template, {"title": "Another List", "items": "A\nB"})
    assert "# Another List" in result2
    assert "- A" in result2

    stats = get_cache_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 1
