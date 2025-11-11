"""Unit tests for corpus loading and citation extraction."""

import os
import tempfile

import pytest

from relay_ai.corpus import Citation, CorpusManager, Doc, extract_citations, get_corpus_stats, load_corpus, search_corpus


@pytest.fixture
def temp_corpus_dir():
    """Create a temporary directory with test documents."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test documents
        test_docs = [
            (
                "machine_learning.txt",
                "# Machine Learning\n\nMachine learning is a subset of artificial intelligence that enables computers to learn without being explicitly programmed.",
            ),
            (
                "data_science.md",
                "## Data Science Overview\n\nData science combines statistics, programming, and domain expertise to extract insights from data.",
            ),
            (
                "ai_ethics.txt",
                "Artificial Intelligence Ethics\n\nAI systems must be designed with fairness, accountability, and transparency in mind.",
            ),
        ]

        for filename, content in test_docs:
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        yield temp_dir


def test_load_corpus_basic(temp_corpus_dir):
    """Test basic corpus loading."""
    docs = load_corpus(temp_corpus_dir)

    assert len(docs) == 3
    assert all(isinstance(doc, Doc) for doc in docs)
    assert all(doc.text for doc in docs)
    assert all(doc.title for doc in docs)
    assert all(doc.id for doc in docs)
    assert all(doc.path for doc in docs)


def test_load_corpus_invalid_path():
    """Test loading from invalid path."""
    with pytest.raises(ValueError, match="does not exist"):
        load_corpus("/nonexistent/path")


def test_load_corpus_empty_dir():
    """Test loading from empty directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        docs = load_corpus(temp_dir)
        assert len(docs) == 0


def test_load_corpus_skip_empty_files(temp_corpus_dir):
    """Test that empty files are skipped."""
    # Create an empty file
    empty_file = os.path.join(temp_corpus_dir, "empty.txt")
    with open(empty_file, "w", encoding="utf-8") as f:
        f.write("")

    docs = load_corpus(temp_corpus_dir)
    # Should still be 3 (empty file skipped)
    assert len(docs) == 3


def test_title_extraction_markdown():
    """Test title extraction from markdown headers."""
    manager = CorpusManager()

    # Test markdown heading
    title = manager._extract_title("# My Title\n\nContent here", "fallback")
    assert title == "My Title"

    # Test h2 heading
    title = manager._extract_title("## Another Title\n\nContent", "fallback")
    assert title == "Another Title"

    # Test fallback
    title = manager._extract_title("No heading here\nJust content", "my_file")
    assert title == "No heading here"


def test_search_corpus_keyword(temp_corpus_dir):
    """Test keyword-based corpus search."""
    docs = load_corpus(temp_corpus_dir)

    # Search for "artificial intelligence"
    results = search_corpus("artificial intelligence", k=3)

    assert len(results) > 0
    assert len(results) <= 3
    assert all(isinstance(doc, Doc) for doc in results)

    # Results should be relevant
    result_text = " ".join([doc.text.lower() for doc in results])
    assert "artificial" in result_text or "intelligence" in result_text


def test_search_corpus_no_results():
    """Test search with no matching results."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create doc with specific content
        doc_path = os.path.join(temp_dir, "test.txt")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("Completely unrelated content about bananas.")

        load_corpus(temp_dir)
        results = search_corpus("quantum physics", k=5)

        # Should return empty or have low relevance
        assert len(results) == 0


def test_search_corpus_limit_k(temp_corpus_dir):
    """Test that search respects k parameter."""
    load_corpus(temp_corpus_dir)

    # Search with k=2
    results = search_corpus("data", k=2)
    assert len(results) <= 2


def test_extract_citations_explicit(temp_corpus_dir):
    """Test citation extraction with explicit citations."""
    docs = load_corpus(temp_corpus_dir)

    # Text with explicit citations
    text = "According to [Machine Learning] principles, and as noted in Data Science Overview, we can see insights."

    citations = extract_citations(text, docs, top_n=5)

    assert len(citations) > 0
    assert all(isinstance(cit, Citation) for cit in citations)
    assert any("Machine Learning" in cit.title for cit in citations)


def test_extract_citations_title_mention(temp_corpus_dir):
    """Test citation extraction with title mentions."""
    docs = load_corpus(temp_corpus_dir)

    # Text that mentions document titles
    text = "Machine Learning is important. Data Science Overview shows us key points."

    citations = extract_citations(text, docs, top_n=3)

    assert len(citations) > 0
    assert len(citations) <= 3


def test_extract_citations_no_matches(temp_corpus_dir):
    """Test citation extraction with no matching documents."""
    docs = load_corpus(temp_corpus_dir)

    # Text with no citations
    text = "This is completely unrelated text with no citations."

    citations = extract_citations(text, docs, top_n=5)

    # Should return empty or very few
    assert len(citations) == 0


def test_extract_citations_top_n_limit(temp_corpus_dir):
    """Test that citation extraction respects top_n parameter."""
    docs = load_corpus(temp_corpus_dir)

    # Text with multiple potential citations
    text = "[Machine Learning] and [Data Science Overview] and [Artificial Intelligence Ethics]"

    citations = extract_citations(text, docs, top_n=2)

    assert len(citations) <= 2


def test_get_corpus_stats(temp_corpus_dir):
    """Test corpus statistics."""
    load_corpus(temp_corpus_dir)

    stats = get_corpus_stats()

    assert isinstance(stats, dict)
    assert "total_docs" in stats
    assert stats["total_docs"] == 3
    assert "has_tfidf" in stats
    assert "has_pypdf" in stats
    assert "has_sklearn" in stats


def test_corpus_manager_instance_reuse():
    """Test that corpus manager maintains state across calls."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test document
        doc_path = os.path.join(temp_dir, "test.txt")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("Test content")

        # Load corpus
        docs1 = load_corpus(temp_dir)

        # Get stats (should reflect loaded corpus)
        stats = get_corpus_stats()
        assert stats["total_docs"] == 1

        # Search should work on previously loaded corpus
        results = search_corpus("test", k=5)
        assert len(results) > 0


def test_relevant_snippet_extraction(temp_corpus_dir):
    """Test that citations include relevant snippets."""
    docs = load_corpus(temp_corpus_dir)

    text = "According to [Machine Learning] research, learning without explicit programming is possible."
    citations = extract_citations(text, docs, top_n=5)

    for cit in citations:
        assert isinstance(cit.snippet, str)
        assert len(cit.snippet) > 0
        # Snippet should be reasonable length
        assert len(cit.snippet) <= 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
