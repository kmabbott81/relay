"""Global pytest configuration and fixtures."""

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Force pytest-anyio to use asyncio backend only (no trio).

    Sprint 53 Phase B: Pin async tests to asyncio to avoid trio dependency.
    """
    return "asyncio"


@pytest.fixture(autouse=True)
def mock_auth_decorator():
    """Mock RBAC scope decorator for endpoint tests.

    Allows testing endpoints that require scopes without auth setup.
    Sprint 59: Required for /ai/jobs endpoint tests.
    """
    from unittest.mock import patch

    def noop_decorator(scopes):
        """No-op decorator that passes through the function unchanged."""

        def decorator(func):
            return func

        return decorator

    with patch("src.auth.security.require_scopes", noop_decorator):
        yield


@pytest.fixture(autouse=True)
def _enable_rbac_and_budgets(monkeypatch):
    """
    Auto-enable RBAC and budgets for all tests to ensure deterministic behavior.

    This fixture ensures that security and budget features are always enabled
    during test runs, preventing false negatives when feature flags default to
    false in development environments.

    Feature flags enabled:
    - FEATURE_RBAC_ENFORCE: true (enforce role-based access control)
    - FEATURE_BUDGETS: true (enforce per-tenant budget limits)

    Network features disabled:
    - CONNECTORS_NETWORK_ENABLED: false (avoid external API calls in tests)

    This fixture uses autouse=True so it applies to all tests automatically
    without requiring explicit declaration in each test function.
    """
    # Enable RBAC enforcement for all tests
    monkeypatch.setenv("FEATURE_RBAC_ENFORCE", "true")

    # Enable budget enforcement for all tests
    monkeypatch.setenv("FEATURE_BUDGETS", "true")

    # Disable network calls for connectors (tests use mocks)
    monkeypatch.setenv("CONNECTORS_NETWORK_ENABLED", "false")

    # Set default tenant for tests
    monkeypatch.setenv("DEFAULT_TENANT_ID", "test-tenant")

    # Use temporary database file for tests (in-memory doesn't work with multiple connections)
    import atexit
    import tempfile

    temp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
    temp_db.close()
    monkeypatch.setenv("METADATA_DB_PATH", temp_db.name)

    # Clean up temp file after test
    def cleanup():
        import os

        try:
            os.unlink(temp_db.name)
        except Exception:
            pass

    atexit.register(cleanup)

    # Disable audit logging to disk during tests (can log to memory/mock)
    monkeypatch.setenv("AUDIT_LOG_DIR", "/tmp/test-audit-logs")

    # Sprint 54: Set Redis URL for OAuth state tests
    monkeypatch.setenv("REDIS_URL", "redis://default:zhtagqDujRcWQzETQOgHYLYYtiVduGTe@crossover.proxy.rlwy.net:22070")

    # Reinitialize metadata database after setting env vars
    from src.metadata import init_metadata_db

    init_metadata_db()


# Sprint 25 fixtures for new tests


@pytest.fixture
def mock_openai_client():
    """
    Fixture for mocking OpenAI client.

    Provides a mock OpenAI client that can be used to test OpenAI adapter
    without making real API calls. The mock client has a configured
    chat.completions.create method that can be set up with side_effect
    or return_value in tests.

    Returns:
        Mock: Mocked OpenAI client instance

    Example:
        def test_example(mock_openai_client):
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="test"))]
            mock_openai_client.chat.completions.create.return_value = mock_response
    """
    from unittest.mock import Mock, patch

    with patch("src.agents.openai_adapter.OpenAI") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def temp_artifacts_dir(tmp_path):
    """
    Fixture for temporary artifact directory.

    Creates a temporary directory structure for workflow artifacts.
    Automatically cleaned up after test completion.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        Path: Path to temporary artifacts directory

    Example:
        def test_example(temp_artifacts_dir):
            output_file = temp_artifacts_dir / "workflow" / "result.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("content")
    """
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


@pytest.fixture
def mock_cost_logger(tmp_path):
    """
    Fixture for capturing cost events.

    Creates a temporary cost event logger that writes to a JSONL file.
    Useful for testing cost tracking without polluting actual logs.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        tuple: (CostTracker instance, Path to log file)

    Example:
        def test_example(mock_cost_logger):
            tracker, log_path = mock_cost_logger
            tracker.log_event("tenant", "workflow", "model", 100, 50, 0.001)
            assert log_path.exists()
    """
    from src.agents.openai_adapter import CostTracker

    cost_log_path = tmp_path / "cost_events.jsonl"
    tracker = CostTracker(cost_log_path)
    return tracker, cost_log_path


@pytest.fixture
def temp_cost_log(tmp_path):
    """
    Fixture for temporary cost log path.

    Provides a path for cost event logging in tests.
    File is automatically cleaned up after test.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        Path: Path to temporary cost log file

    Example:
        def test_example(temp_cost_log):
            adapter = OpenAIAdapter(cost_log_path=temp_cost_log)
            # Cost events will be logged to temp_cost_log
    """
    return tmp_path / "cost_events.jsonl"


@pytest.fixture
def mock_project_root(tmp_path):
    """
    Fixture for mocking project root with config files.

    Creates a temporary project structure with templates/examples
    directory containing mock workflow configuration files.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        Path: Path to temporary project root

    Example:
        def test_example(mock_project_root):
            config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
            assert config_path.exists()
    """
    import yaml

    # Create templates/examples directory
    templates_dir = tmp_path / "templates" / "examples"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Create mock config files
    weekly_config = {
        "workflow_name": "weekly_report",
        "description": "Generate weekly status report",
        "prompt_template": "Generate a weekly report for {start_date} to {end_date}:\n{context}",
        "parameters": {"model": "gpt-4o", "max_tokens": 2000, "temperature": 0.5},
    }

    meeting_config = {
        "workflow_name": "meeting_brief",
        "description": "Generate meeting brief",
        "prompt_template": "Summarize meeting: {meeting_title} on {meeting_date}\nAttendees: {attendees}\n\nTranscript:\n{transcript}",
        "parameters": {"model": "gpt-4o", "max_tokens": 1500, "temperature": 0.3},
    }

    inbox_config = {
        "workflow_name": "inbox_sweep",
        "description": "Process inbox and drive files",
        "prompt_template": "Process these files: {file_list}",
        "parameters": {"model": "gpt-4o-mini", "max_tokens": 1000, "temperature": 0.4},
    }

    with open(templates_dir / "weekly_report.yaml", "w", encoding="utf-8") as f:
        yaml.dump(weekly_config, f)

    with open(templates_dir / "meeting_brief.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meeting_config, f)

    with open(templates_dir / "inbox_sweep.yaml", "w", encoding="utf-8") as f:
        yaml.dump(inbox_config, f)

    return tmp_path


# Sprint 26 fixtures for storage lifecycle testing


@pytest.fixture
def fake_clock():
    """
    Fixture for controllable time in lifecycle tests.

    Provides a mock clock that can be used to simulate artifact aging
    without actually waiting. Returns a mutable dict with 'time' key
    that can be advanced during tests.

    Returns:
        dict: Dictionary with 'time' key containing current Unix timestamp

    Example:
        def test_example(fake_clock):
            fake_clock['time'] = time.time() - 10 * 86400  # 10 days ago
            # Artifacts will appear 10 days old
    """
    import time

    return {"time": time.time()}


@pytest.fixture
def temp_tier_paths(tmp_path, monkeypatch):
    """
    Fixture for temporary storage tier directories.

    Creates isolated hot/warm/cold storage directories for testing
    without interfering with actual storage. Automatically sets
    STORAGE_BASE_PATH environment variable.

    Args:
        tmp_path: pytest's built-in tmp_path fixture
        monkeypatch: pytest's monkeypatch fixture

    Returns:
        dict: Dictionary with tier names as keys, Path objects as values

    Example:
        def test_example(temp_tier_paths):
            hot_path = temp_tier_paths['hot']
            # Write test artifacts to hot_path
    """
    base_path = tmp_path / "artifacts"
    base_path.mkdir(parents=True, exist_ok=True)

    # Create tier directories
    tiers = {}
    for tier in ["hot", "warm", "cold"]:
        tier_path = base_path / tier
        tier_path.mkdir(parents=True, exist_ok=True)
        tiers[tier] = tier_path

    # Set environment variable
    monkeypatch.setenv("STORAGE_BASE_PATH", str(base_path))

    return tiers


@pytest.fixture
def lifecycle_env(tmp_path, monkeypatch, temp_tier_paths):
    """
    Fixture for lifecycle environment with configurable retention policies.

    Sets up complete lifecycle testing environment with temporary
    storage paths, log directory, and retention policy overrides.

    Args:
        tmp_path: pytest's built-in tmp_path fixture
        monkeypatch: pytest's monkeypatch fixture
        temp_tier_paths: temp_tier_paths fixture

    Returns:
        dict: Configuration dictionary with paths and retention days

    Example:
        def test_example(lifecycle_env):
            # Storage paths and retention policies configured
            assert lifecycle_env['hot_retention_days'] == 7
    """
    # Create log directory
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOG_DIR", str(log_dir))

    # Set retention policies (shorter for testing)
    monkeypatch.setenv("HOT_RETENTION_DAYS", "7")
    monkeypatch.setenv("WARM_RETENTION_DAYS", "30")
    monkeypatch.setenv("COLD_RETENTION_DAYS", "90")

    return {
        "storage_base": tmp_path / "artifacts",
        "log_dir": log_dir,
        "tier_paths": temp_tier_paths,
        "hot_retention_days": 7,
        "warm_retention_days": 30,
        "cold_retention_days": 90,
    }


# Sprint 31B fixtures for checkpoint approvals


@pytest.fixture(autouse=True)
def mock_workflow_map(monkeypatch):
    """
    Auto-mock workflow map for tests.

    Provides mock implementations of workflows to avoid requiring
    actual OpenAI API calls or real workflow implementations.
    """

    # Mock workflow functions (accept params dict as single positional arg)
    def mock_inbox_drive_sweep(params):
        return {"summary": f"Processed {params.get('inbox_items', 'items')}", "status": "completed"}

    def mock_weekly_report(params):
        return {"report": "Weekly status report", "priorities": params.get("user_priorities", "N/A")}

    def mock_meeting_transcript_brief(params):
        return {"brief": f"Meeting: {params.get('meeting_title', 'Untitled')}", "action_items": []}

    # Sprint 32: Import template adapter to include in mock map
    from src.workflows.adapter import template_adapter

    mock_map = {
        "inbox_drive_sweep": mock_inbox_drive_sweep,
        "weekly_report": mock_weekly_report,
        "meeting_transcript_brief": mock_meeting_transcript_brief,
        "template": template_adapter,  # Sprint 32: Template-based execution
    }

    # Patch WORKFLOW_MAP
    import src.workflows.adapter

    monkeypatch.setattr(src.workflows.adapter, "WORKFLOW_MAP", mock_map)


# Sprint 38B fixtures for URG (Unified Resource Graph) isolation


@pytest.fixture(autouse=True)
def clean_graph_env(tmp_path, monkeypatch):
    """
    Reset URG environment for each test.

    Provides complete isolation for graph index tests by:
    - Resetting the global index singleton
    - Isolating storage paths to tmp_path
    - Setting URG environment variables

    This fixture uses autouse=True so it applies to all tests automatically,
    ensuring no state bleeding between tests.
    """
    # Reset global index before each test
    from src.graph.index import reset_index

    reset_index()

    # Isolate storage path to tmp_path
    urg_path = tmp_path / "graph"
    urg_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("URG_STORE_PATH", str(urg_path))

    # Set URG configuration
    monkeypatch.setenv("URG_MAX_RESULTS", "200")
    monkeypatch.setenv("GRAPH_DEFAULT_TENANT", "test-tenant")

    yield

    # Cleanup after test
    reset_index()


# Sprint 54 fixtures for OAuth tests with FakeRedis


@pytest.fixture
def fake_redis():
    """Provide FakeRedis instance for OAuth token cache tests.

    FakeRedis supports set, get, setnx, expire, delete, setex, ping
    matching production Redis calls in OAuthTokenCache.
    """
    import fakeredis

    return fakeredis.FakeStrictRedis(decode_responses=True)


# Sprint 42 fixtures for network blocking (Issue #15)


@pytest.fixture(autouse=True, scope="session")
def _maybe_block_outbound_session():
    """
    Block outbound network connections at socket level during tests.

    Only affects test session; not runtime. Allows localhost and 127.0.0.1
    for Redis, databases, and other local services. Real external API calls
    are blocked to ensure fast, deterministic tests.

    Respects TEST_OFFLINE environment variable:
    - CI: Blocks by default (can opt-out with TEST_OFFLINE=false)
    - Local: Allows by default (can opt-in with TEST_OFFLINE=true)
    """
    from tests.utils.netblock import block_outbound, should_block_by_default

    if should_block_by_default():
        with block_outbound():
            yield
    else:
        yield


# Sprint 43 fixtures for Issue #14 (batch/parametrization speedups)


@pytest.fixture(scope="session")
def small_corpus():
    """Small corpus for fast tests (session-scoped to avoid reloads).

    Returns:
        list[str]: Small corpus of 4 items
    """
    from tests.utils.corpus_cache import load_small_corpus

    return load_small_corpus()


@pytest.fixture(scope="session")
def medium_corpus():
    """Medium corpus for representative tests (session-scoped to avoid reloads).

    Returns:
        list[str]: Medium corpus of ~250 items
    """
    from tests.utils.corpus_cache import load_medium_corpus

    return load_medium_corpus()


# Sprint 43 fixtures for Issue #13 (fixture scope/I-O reduction)


@pytest.fixture(scope="session")
def shared_tmpdir(tmp_path_factory):
    """Session-scoped temp workspace to avoid re-creating heavy dirs.

    Args:
        tmp_path_factory: pytest tmp_path_factory fixture

    Returns:
        Path: Session-wide temporary directory
    """
    d = tmp_path_factory.mktemp("shared-workspace")
    yield d
    # no cleanup needed; tmp_path_factory handles removal


@pytest.fixture(scope="session")
def small_dataset_cap():
    """Soft cap size for generated test data to keep PR suite fast.

    Use this fixture in parametrized tests to limit generated data size.
    Helps maintain CI PR suite <= 90s target.
    """
    return 500  # adjust as needed; PR suite should remain lightweight


def pytest_runtest_logreport(report):
    """Local developer hint: warn if an individual test exceeds threshold.

    Enable with HOTSPOT_WATCH=1 environment variable.
    Disabled on CI by default to avoid noise.
    Helps identify slow tests during local development.
    """
    import os

    if os.getenv("HOTSPOT_WATCH", "0") in {"1", "true", "yes"} and report.when == "call":
        duration = getattr(report, "duration", 0)
        if duration > 5.0:
            print(f"\n[hotspot] {report.nodeid} took {duration:.2f}s")


# ==============================================================================
# Sprint 52: Quarantine Markers - Auto-skip Hooks
# ==============================================================================
# These hooks automatically skip tests marked with specific markers unless
# opt-in environment variables are set. This allows CI to run a stable subset
# while developers can still run full suites locally.


def pytest_configure(config):
    """Configure pytest skip policies for quarantine markers."""
    import os

    # Allow running all tests with RELAY_RUN_ALL=1
    if os.getenv("RELAY_RUN_ALL", "0") in {"1", "true", "yes"}:
        return

    # Check for optional dependencies
    try:
        import streamlit  # noqa: F401

        has_streamlit = True
    except ImportError:
        has_streamlit = False

    # Store skip conditions in config
    config._relay_skip_streamlit = not has_streamlit
    config._relay_skip_ports = not os.getenv("RELAY_ALLOW_PORTS")
    config._relay_skip_artifacts = not os.getenv("RELAY_HAVE_ARTIFACTS")


def pytest_collection_modifyitems(config, items):
    """Apply skip markers based on environment and dependencies."""
    import pytest

    skip_streamlit = pytest.mark.skip(reason="streamlit not installed (install or set RELAY_RUN_ALL=1)")
    skip_ports = pytest.mark.skip(reason="port conflicts in CI (set RELAY_ALLOW_PORTS=1 or RELAY_RUN_ALL=1)")
    skip_artifacts = pytest.mark.skip(
        reason="test artifacts not available (set RELAY_HAVE_ARTIFACTS=1 or RELAY_RUN_ALL=1)"
    )

    for item in items:
        if getattr(config, "_relay_skip_streamlit", False) and "requires_streamlit" in item.keywords:
            item.add_marker(skip_streamlit)

        if getattr(config, "_relay_skip_ports", False) and "port_conflict" in item.keywords:
            item.add_marker(skip_ports)

        if getattr(config, "_relay_skip_artifacts", False) and "needs_artifacts" in item.keywords:
            item.add_marker(skip_artifacts)
