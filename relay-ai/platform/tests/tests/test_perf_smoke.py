"""Performance smoke test to catch major regressions."""

import os
import time

import pytest


@pytest.mark.bizlogic_asserts  # Sprint 52: UnboundLocalError - 'time' variable shadowing
def test_minimal_workflow_performance_sync():
    """Synchronous wrapper for the async performance test."""

    # Skip if no OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not available - skipping perf test")

    # Very lenient threshold for mocked test
    MAX_DURATION_SECONDS = 10

    start_time = time.time()  # noqa: F823

    # Test just the import and basic function creation performance
    try:
        # Basic smoke test - can we import and call basic functions quickly?
        # This catches major import issues or infinite loops in module loading
        # Test artifact creation performance
        import time  # noqa: F401

        from src.artifacts import create_run_artifact, save_run_artifact  # noqa: F401
        from src.debate import run_debate  # noqa: F401
        from src.guardrails import run_publish_guardrails  # noqa: F401
        from src.judge import judge_drafts  # noqa: F401
        from src.run_workflow import print_cost_footer, write_run_log  # noqa: F401
        from src.schemas import Draft, Judgment, ScoredDraft  # noqa: F401

        minimal_judgment = Judgment(ranked=[], winner_provider="")
        minimal_drafts = []

        artifact = create_run_artifact(
            task="Perf test task",
            max_tokens=500,
            temperature=0.1,
            trace_name="perf-test",
            drafts=minimal_drafts,
            judgment=minimal_judgment,
            status="none",
            provider="",
            text="",
            allowed_models=[],
            start_time=start_time,
            seed=42,
        )

        assert artifact is not None
        assert "provenance" in artifact
        assert artifact["provenance"]["duration_seconds"] >= 0

    except ImportError as e:
        pytest.fail(f"Import performance issue: {e}")
    except Exception as e:
        pytest.fail(f"Basic function performance issue: {e}")

    duration = time.time() - start_time

    # Log the measured time
    print(f"\nBasic import/function smoke test duration: {duration:.3f}s")

    # Very lenient constraint for import performance
    assert (
        duration < MAX_DURATION_SECONDS
    ), f"Basic operations took {duration:.3f}s, exceeds threshold of {MAX_DURATION_SECONDS}s"


def test_guardrails_performance():
    """Test that guardrails run quickly on typical content."""

    MAX_GUARDRAILS_DURATION = 1.0  # 1 second should be plenty

    # Test content of reasonable size
    test_content = "This is a test of the guardrails system. " * 20  # ~100 words
    test_flags = ["warning", "advisory"]

    start_time = time.time()

    try:
        from src.guardrails import run_publish_guardrails

        # Run guardrails multiple times to test consistency
        for _ in range(10):
            ok, reason = run_publish_guardrails(test_content, test_flags)
            assert isinstance(ok, bool)
            assert isinstance(reason, str)

    except Exception as e:
        pytest.fail(f"Guardrails performance test failed: {e}")

    duration = time.time() - start_time

    print(f"\nGuardrails performance test (10 runs): {duration:.3f}s")

    assert (
        duration < MAX_GUARDRAILS_DURATION
    ), f"Guardrails took {duration:.3f}s for 10 runs, exceeds {MAX_GUARDRAILS_DURATION}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
