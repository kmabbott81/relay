"""
Tests for Classification Labels & Policy - Sprint 33B

Covers label hierarchy, access control, and export policies.
"""


from relay_ai.classify.labels import can_access, effective_label, parse_labels
from relay_ai.classify.policy import export_allowed, label_for_artifact


def test_parse_labels_default():
    """Test default label parsing."""
    labels = parse_labels()
    assert labels == ["Public", "Internal", "Confidential", "Restricted"]


def test_parse_labels_custom():
    """Test custom label parsing."""
    labels = parse_labels("Low,Medium,High")
    assert labels == ["Low", "Medium", "High"]


def test_can_access_same_level():
    """Test access at same clearance level."""
    assert can_access("Internal", "Internal") is True


def test_can_access_higher_clearance():
    """Test access with higher clearance."""
    assert can_access("Confidential", "Internal") is True
    assert can_access("Confidential", "Public") is True


def test_can_access_lower_clearance():
    """Test denial with lower clearance."""
    assert can_access("Internal", "Confidential") is False
    assert can_access("Public", "Internal") is False


def test_can_access_invalid_label():
    """Test denial with invalid label."""
    assert can_access("Invalid", "Internal") is False
    assert can_access("Internal", "Invalid") is False


def test_effective_label_requested():
    """Test effective label uses requested when valid."""
    assert effective_label("Confidential") == "Confidential"


def test_effective_label_fallback(monkeypatch):
    """Test effective label falls back to DEFAULT_LABEL."""
    monkeypatch.setenv("DEFAULT_LABEL", "Internal")
    assert effective_label(None) == "Internal"
    assert effective_label("Invalid") == "Internal"


def test_effective_label_ultimate_fallback():
    """Test ultimate fallback to first label."""
    # With invalid default
    assert effective_label(None, default="Invalid") == "Public"


def test_label_for_artifact_with_label():
    """Test label assignment from artifact metadata."""
    meta = {"label": "Confidential"}
    assert label_for_artifact(meta) == "Confidential"


def test_label_for_artifact_no_label(monkeypatch):
    """Test label assignment falls back to default."""
    monkeypatch.setenv("DEFAULT_LABEL", "Internal")
    meta = {}
    assert label_for_artifact(meta) == "Internal"


def test_export_allowed_with_clearance():
    """Test export allowed with sufficient clearance."""
    assert export_allowed("Internal", "Confidential", require_labels=True) is True


def test_export_allowed_insufficient_clearance():
    """Test export denied with insufficient clearance."""
    assert export_allowed("Confidential", "Internal", require_labels=True) is False


def test_export_allowed_unlabeled_required():
    """Test export denied for unlabeled when required."""
    assert export_allowed(None, "Confidential", require_labels=True) is False


def test_export_allowed_unlabeled_not_required():
    """Test export allowed for unlabeled when not required."""
    assert export_allowed(None, "Confidential", require_labels=False) is True


def test_export_allowed_exact_match():
    """Test export allowed at exact clearance level."""
    assert export_allowed("Restricted", "Restricted", require_labels=True) is True


def test_label_hierarchy_order():
    """Test label hierarchy is correctly ordered."""
    labels = parse_labels()

    # Verify total order
    for i, label1 in enumerate(labels):
        for j, label2 in enumerate(labels):
            if i >= j:
                # Higher or equal index = higher or equal clearance
                assert can_access(label1, label2) is True
            else:
                # Lower index = lower clearance
                assert can_access(label1, label2) is False
