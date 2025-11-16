"""Corpus loading and citation extraction for grounded mode."""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Try to import optional dependencies
try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

logger = logging.getLogger(__name__)


@dataclass
class Doc:
    """Document in the corpus."""

    id: str
    title: str
    text: str
    path: str


@dataclass
class Citation:
    """Citation extracted from text."""

    doc_id: str
    title: str
    snippet: str
    path: str


class CorpusManager:
    """Manages corpus loading and searching."""

    def __init__(self):
        self.docs: list[Doc] = []
        self.vectorizer: Optional[Any] = None
        self.doc_vectors: Optional[Any] = None
        self._doc_index: dict[str, Doc] = {}

    def load_corpus(self, corpus_path: str) -> list[Doc]:
        """
        Load all documents from a corpus directory.

        Args:
            corpus_path: Path to directory containing corpus files

        Returns:
            List of loaded documents
        """
        corpus_dir = Path(corpus_path)
        if not corpus_dir.exists() or not corpus_dir.is_dir():
            raise ValueError(f"Corpus path does not exist or is not a directory: {corpus_path}")

        docs = []
        supported_extensions = [".txt", ".md"]
        if HAS_PYPDF:
            supported_extensions.append(".pdf")

        for file_path in corpus_dir.rglob("*"):
            if file_path.suffix.lower() in supported_extensions:
                try:
                    doc = self._load_document(file_path)
                    if doc:
                        docs.append(doc)
                except Exception as e:
                    logger.warning(f"Failed to load document {file_path}: {e}")

        # Store docs and build index
        self.docs = docs
        self._doc_index = {doc.id: doc for doc in docs}

        # Build TF-IDF vectors if sklearn is available
        if HAS_SKLEARN and docs:
            self._build_tfidf_index()

        logger.info(f"Loaded {len(docs)} documents from corpus")
        return docs

    def _load_document(self, file_path: Path) -> Optional[Doc]:
        """Load a single document from file."""
        try:
            if file_path.suffix.lower() == ".pdf":
                if not HAS_PYPDF:
                    logger.warning(f"Skipping PDF {file_path}: pypdf not available")
                    return None
                text = self._extract_pdf_text(file_path)
            else:
                # Text/markdown files
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    text = f.read()

            # Skip empty files
            if not text.strip():
                logger.warning(f"Skipping empty file: {file_path}")
                return None

            # Generate document ID and title
            doc_id = str(file_path.relative_to(file_path.parent.parent)) if file_path.parent.parent else file_path.name
            title = self._extract_title(text, file_path.stem)

            return Doc(id=doc_id, title=title, text=text.strip(), path=str(file_path))

        except Exception as e:
            logger.error(f"Error loading document {file_path}: {e}")
            return None

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        if not HAS_PYPDF:
            return ""

        try:
            text_parts = []
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text.strip():
                        text_parts.append(text)
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting PDF text from {file_path}: {e}")
            return ""

    def _extract_title(self, text: str, fallback: str) -> str:
        """Extract title from document text."""
        lines = text.split("\n")

        # Look for markdown title
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            elif line.startswith("## "):
                return line[3:].strip()

        # Look for first non-empty line as title
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and len(line) < 100:  # Reasonable title length
                return line

        # Fallback to filename
        return fallback.replace("_", " ").replace("-", " ").title()

    def _build_tfidf_index(self):
        """Build TF-IDF index for semantic search."""
        if not self.docs or not HAS_SKLEARN:
            return

        try:
            # Create document texts for vectorization
            doc_texts = [doc.text for doc in self.docs]

            # Build TF-IDF vectors
            self.vectorizer = TfidfVectorizer(
                max_features=5000, stop_words="english", ngram_range=(1, 2), max_df=0.95, min_df=1
            )
            self.doc_vectors = self.vectorizer.fit_transform(doc_texts)
            logger.info(f"Built TF-IDF index with {self.doc_vectors.shape[1]} features")

        except Exception as e:
            logger.error(f"Error building TF-IDF index: {e}")
            self.vectorizer = None
            self.doc_vectors = None

    def search_corpus(self, query: str, k: int = 8) -> list[Doc]:
        """
        Search corpus for relevant documents.

        Args:
            query: Search query
            k: Number of documents to return

        Returns:
            List of relevant documents, ranked by relevance
        """
        if not self.docs:
            return []

        # Try semantic search first (TF-IDF)
        if self.vectorizer and self.doc_vectors is not None:
            return self._semantic_search(query, k)
        else:
            # Fallback to keyword search
            return self._keyword_search(query, k)

    def _semantic_search(self, query: str, k: int) -> list[Doc]:
        """Semantic search using TF-IDF cosine similarity."""
        try:
            # Vectorize query
            query_vector = self.vectorizer.transform([query])

            # Compute similarities
            similarities = cosine_similarity(query_vector, self.doc_vectors).flatten()

            # Get top-k most similar documents
            top_indices = np.argsort(similarities)[::-1][:k]

            # Filter out documents with very low similarity
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.01:  # Minimum similarity threshold
                    results.append(self.docs[idx])

            return results

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            # Fallback to keyword search
            return self._keyword_search(query, k)

    def _keyword_search(self, query: str, k: int) -> list[Doc]:
        """Simple keyword-based search."""
        query_words = set(query.lower().split())
        scored_docs = []

        for doc in self.docs:
            doc_words = set(doc.text.lower().split())
            title_words = set(doc.title.lower().split())

            # Calculate simple relevance score
            text_matches = len(query_words.intersection(doc_words))
            title_matches = len(query_words.intersection(title_words)) * 3  # Title matches weighted higher

            total_score = text_matches + title_matches
            if total_score > 0:
                scored_docs.append((total_score, doc))

        # Sort by score and return top-k
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_docs[:k]]

    def extract_citations(self, text: str, docs: list[Doc], top_n: int = 5) -> list[Citation]:
        """
        Extract citations from text based on corpus documents.

        Args:
            text: Text to extract citations from
            docs: Candidate documents for citations
            top_n: Maximum number of citations to return

        Returns:
            List of extracted citations
        """
        citations = []
        text_lower = text.lower()

        # Look for explicit citations (e.g., [Title], "Title", etc.)
        citation_patterns = [
            r"\[([^\]]+)\]",  # [Title]
            r'"([^"]+)"',  # "Title"
            r"according to ([^,.]+)",  # according to Source
            r"as noted in ([^,.]+)",  # as noted in Source
        ]

        found_titles = set()
        for pattern in citation_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                candidate_title = match.group(1).strip()
                if len(candidate_title) > 3:  # Skip very short matches
                    found_titles.add(candidate_title.lower())

        # Match found titles to documents
        for doc in docs:
            doc_title_lower = doc.title.lower()

            # Check if document title appears in found citations
            title_cited = False
            for found_title in found_titles:
                if found_title in doc_title_lower or doc_title_lower in found_title:
                    title_cited = True
                    break

            # Also check for direct mention of document title in text
            if doc_title_lower in text_lower:
                title_cited = True

            if title_cited:
                # Extract relevant snippet from document
                snippet = self._extract_relevant_snippet(text, doc.text, max_length=200)

                citations.append(Citation(doc_id=doc.id, title=doc.title, snippet=snippet, path=doc.path))

        # Limit to top_n citations
        return citations[:top_n]

    def _extract_relevant_snippet(self, query_text: str, doc_text: str, max_length: int = 200) -> str:
        """Extract relevant snippet from document based on query context."""
        query_words = set(query_text.lower().split())
        doc_sentences = doc_text.split(".")

        best_sentence = ""
        best_score = 0

        for sentence in doc_sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short sentences
                continue

            sentence_words = set(sentence.lower().split())
            overlap = len(query_words.intersection(sentence_words))

            if overlap > best_score:
                best_score = overlap
                best_sentence = sentence

        # If no good sentence found, use beginning of document
        if not best_sentence:
            best_sentence = doc_text[:max_length]

        # Truncate to max length
        if len(best_sentence) > max_length:
            best_sentence = best_sentence[:max_length].rsplit(" ", 1)[0] + "..."

        return best_sentence


# Global corpus manager instance
_corpus_manager = CorpusManager()


def load_corpus(corpus_path: str) -> list[Doc]:
    """Load corpus documents from directory."""
    return _corpus_manager.load_corpus(corpus_path)


def search_corpus(query: str, k: int = 8) -> list[Doc]:
    """Search corpus for relevant documents."""
    return _corpus_manager.search_corpus(query, k)


def extract_citations(text: str, docs: list[Doc], top_n: int = 5) -> list[Citation]:
    """Extract citations from text based on corpus documents."""
    return _corpus_manager.extract_citations(text, docs, top_n)


def get_corpus_stats() -> dict[str, Any]:
    """Get statistics about loaded corpus."""
    return {
        "total_docs": len(_corpus_manager.docs),
        "has_tfidf": _corpus_manager.vectorizer is not None,
        "has_pypdf": HAS_PYPDF,
        "has_sklearn": HAS_SKLEARN,
    }


if __name__ == "__main__":
    # Test corpus loading
    import os
    import tempfile

    # Create test corpus
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
            with open(os.path.join(temp_dir, filename), "w") as f:
                f.write(content)

        # Test loading
        docs = load_corpus(temp_dir)
        print(f"Loaded {len(docs)} documents")

        # Test search
        results = search_corpus("artificial intelligence", k=3)
        print(f"Search results: {[doc.title for doc in results]}")

        # Test citation extraction
        test_text = "According to Machine Learning principles, we can see that [Data Science Overview] shows important insights."
        citations = extract_citations(test_text, docs)
        print(f"Citations: {[(c.title, c.snippet[:50]) for c in citations]}")

        # Print stats
        print(f"Corpus stats: {get_corpus_stats()}")
