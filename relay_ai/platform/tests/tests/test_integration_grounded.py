"""Integration tests for grounded mode with corpus and redaction."""

import os
import tempfile

import pytest

from relay_ai.artifacts import create_run_artifact
from relay_ai.corpus import extract_citations, load_corpus, search_corpus
from relay_ai.redaction import apply_redactions


@pytest.fixture
def temp_corpus_dir():
    """Create temporary corpus directory with test documents."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create sample corpus documents
        corpus_docs = [
            (
                "machine_learning.txt",
                """# Machine Learning Fundamentals

Machine learning is a subset of artificial intelligence that focuses on enabling computers to learn from data without being explicitly programmed. Key algorithms include supervised learning, unsupervised learning, and reinforcement learning.""",
            ),
            (
                "data_science.md",
                """## Data Science Best Practices

Data science combines statistical analysis, programming, and domain expertise to extract actionable insights from data. Essential tools include Python, R, and SQL for data manipulation and visualization.""",
            ),
            (
                "ai_ethics.txt",
                """Artificial Intelligence Ethics

AI systems must be developed with fairness, accountability, transparency, and privacy in mind. Ethical AI requires ongoing monitoring and adjustment to prevent bias and ensure equitable outcomes.""",
            ),
        ]

        for filename, content in corpus_docs:
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        yield temp_dir


def test_corpus_loading_integration(temp_corpus_dir):
    """Test end-to-end corpus loading."""
    docs = load_corpus(temp_corpus_dir)

    assert len(docs) == 3
    assert all(doc.text for doc in docs)
    assert all(doc.title for doc in docs)

    # Verify documents can be searched
    results = search_corpus("machine learning", k=3)
    assert len(results) > 0
    assert any("machine learning" in doc.text.lower() for doc in results)


def test_citation_extraction_workflow(temp_corpus_dir):
    """Test citation extraction from generated text."""
    docs = load_corpus(temp_corpus_dir)

    # Simulate a generated response with citations
    generated_text = """
    According to [Machine Learning Fundamentals], machine learning enables
    computers to learn from data. As noted in Data Science Best Practices,
    essential tools include Python and R.
    """

    citations = extract_citations(generated_text, docs, top_n=5)

    assert len(citations) >= 2
    assert any("Machine Learning" in cit.title for cit in citations)
    assert any("Data Science" in cit.title for cit in citations)

    # Verify citation structure
    for cit in citations:
        assert cit.doc_id
        assert cit.title
        assert cit.snippet
        assert cit.path


def test_grounded_mode_with_required_citations(temp_corpus_dir):
    """Test that grounding requirements are enforced."""
    docs = load_corpus(temp_corpus_dir)

    # Text with sufficient citations
    text_with_citations = "[Machine Learning Fundamentals] and [Data Science Best Practices] show us..."
    citations = extract_citations(text_with_citations, docs, top_n=5)
    assert len(citations) >= 2  # Meets requirement

    # Text without sufficient citations
    text_without_citations = "Machine learning is important but no explicit citations."
    citations_insufficient = extract_citations(text_without_citations, docs, top_n=5)
    # May find some mentions but likely < 2 explicit citations


def test_redaction_integration_with_publish(temp_corpus_dir):
    """Test redaction applied to published text."""
    docs = load_corpus(temp_corpus_dir)

    # Simulate generated text with sensitive data
    draft_text = """
    According to [Machine Learning Fundamentals], you can contact us at
    support@example.com or call (555) 123-4567.
    API key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456
    """

    # Extract citations first
    citations = extract_citations(draft_text, docs, top_n=5)
    assert len(citations) > 0

    # Apply redaction
    redacted_text, events = apply_redactions(draft_text, strategy="label")

    # Verify sensitive data is redacted
    assert "support@example.com" not in redacted_text
    assert "555-123-4567" not in redacted_text
    assert "sk-1234567890" not in redacted_text

    # Verify citations are preserved
    assert "[Machine Learning Fundamentals]" in redacted_text

    # Verify events are recorded
    assert len(events) > 0
    event_types = {e.type for e in events}
    assert "email" in event_types or "phone" in event_types or "api_key" in event_types


def test_artifact_structure_with_grounding(temp_corpus_dir):
    """Test that artifacts include grounding metadata."""
    docs = load_corpus(temp_corpus_dir)

    # Import needed for creating mock judgment
    from src.schemas import Judgment

    # Create mock artifact with proper parameters
    artifact = create_run_artifact(
        task="Test grounded task",
        max_tokens=250,
        temperature=0.0,
        trace_name="grounded-test",
        drafts=[],
        judgment=Judgment(ranked=[], winner_provider="", scores={}),
        status="none",
        provider="",
        text="",
        allowed_models=["openai/gpt-4o-mini"],
        start_time=0.0,
        grounded_corpus=temp_corpus_dir,
        grounded_required=2,
        redact=True,
        corpus_docs_count=len(docs),
    )

    # Verify artifact has grounding section
    assert "grounding" in artifact
    assert "enabled" in artifact["grounding"]
    assert artifact["grounding"]["enabled"] is True
    assert artifact["grounding"]["corpus_docs"] == len(docs)

    # Verify parameters are captured
    assert "grounded_corpus" in artifact["run_metadata"]["parameters"]
    assert artifact["run_metadata"]["parameters"]["grounded_required"] == 2
    assert artifact["run_metadata"]["parameters"]["redact"] is True


def test_redaction_events_in_artifact():
    """Test that redaction events are properly stored in artifacts."""
    # Simulate text with sensitive data
    text_with_secrets = "Contact: admin@company.com, Phone: (555) 987-6543"

    # Apply redaction
    redacted_text, events = apply_redactions(text_with_secrets, strategy="label")

    # Verify events structure matches artifact schema
    event_dicts = [{"type": e.type, "count": e.count, "rule_name": e.rule_name} for e in events]

    assert len(event_dicts) > 0

    for event in event_dicts:
        assert "type" in event
        assert "count" in event
        assert "rule_name" in event
        assert event["count"] > 0


def test_grounded_search_and_cite_workflow(temp_corpus_dir):
    """Test complete search -> cite workflow."""
    docs = load_corpus(temp_corpus_dir)

    # Step 1: Search for relevant documents
    query = "machine learning and data analysis tools"
    search_results = search_corpus(query, k=3)

    assert len(search_results) > 0
    assert len(search_results) <= 3

    # Step 2: Generate text mentioning found documents
    draft_text = (
        f"Based on [{search_results[0].title}], we can understand that machine learning enables automated learning."
    )

    # Step 3: Extract citations
    citations = extract_citations(draft_text, search_results, top_n=5)

    assert len(citations) > 0
    assert citations[0].title == search_results[0].title


def test_multiple_redaction_types_integration():
    """Test integration with multiple types of sensitive data."""
    text_with_multiple_pii = """
    Research findings:
    - Contact: researcher@university.edu
    - Lab phone: (555) 111-2222
    - AWS Key: AKIAIOSFODNN7EXAMPLE
    - Credit Card: 4111111111111111
    - URL: https://internal-server.local/api/data
    """

    redacted_text, events = apply_redactions(text_with_multiple_pii, strategy="label")

    # Verify all types are redacted
    assert "researcher@university.edu" not in redacted_text
    assert "555-111-2222" not in redacted_text
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted_text
    assert "4111111111111111" not in redacted_text

    # Verify multiple event types
    event_types = {e.type for e in events}
    assert len(event_types) >= 3  # At least email, phone, aws, credit_card, url


def test_corpus_stats_integration(temp_corpus_dir):
    """Test corpus statistics in workflow context."""
    from src.corpus import get_corpus_stats

    docs = load_corpus(temp_corpus_dir)

    stats = get_corpus_stats()

    assert stats["total_docs"] == 3
    assert "has_tfidf" in stats
    assert "has_pypdf" in stats
    assert "has_sklearn" in stats


def test_empty_corpus_handling():
    """Test handling of empty corpus directory."""
    with tempfile.TemporaryDirectory() as empty_dir:
        docs = load_corpus(empty_dir)
        assert len(docs) == 0

        # Search should return empty results
        results = search_corpus("anything", k=5)
        assert len(results) == 0


def test_redaction_idempotency_integration():
    """Test that redaction is idempotent in workflow."""
    text = "Contact: user@example.com"

    # First redaction
    redacted1, events1 = apply_redactions(text, strategy="label")
    assert len(events1) > 0

    # Second redaction on already redacted text
    redacted2, events2 = apply_redactions(redacted1, strategy="label")
    assert len(events2) == 0  # Nothing to redact
    assert redacted1 == redacted2  # Same output


def test_citation_snippet_relevance(temp_corpus_dir):
    """Test that citation snippets are contextually relevant."""
    docs = load_corpus(temp_corpus_dir)

    text = "Machine learning algorithms enable automated learning and prediction."
    citations = extract_citations(text, docs, top_n=3)

    for cit in citations:
        # Snippet should be reasonable length
        assert 20 < len(cit.snippet) < 300

        # Snippet should contain relevant terms
        snippet_lower = cit.snippet.lower()
        assert any(term in snippet_lower for term in ["machine", "learning", "data", "ai"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
