"""Test configuration for actions tests.

Sets required environment variables before test collection.
"""

import os
import sys

import pytest

# CRITICAL: Set MS_UPLOAD_CHUNK_SIZE_BYTES to valid value BEFORE any imports
# The microsoft_upload module validates this at import time, and pytest may
# inherit invalid values from parent processes or IDEs
# We MUST set it to a valid value (multiple of 320 KiB) instead of deleting it
# because other processes may have set it to an invalid value like 1
#
# NOTE: 4 MiB (4194304) is NOT a valid multiple of 320 KiB (327680)!
# Valid value: 13 * 320 KiB = 4259840 bytes (4.0625 MiB)
VALID_CHUNK_SIZE = str(13 * 320 * 1024)  # 4259840 bytes (4.0625 MiB)
os.environ["MS_UPLOAD_CHUNK_SIZE_BYTES"] = VALID_CHUNK_SIZE

# If the module was already imported with wrong value, remove it from cache
if "src.actions.adapters.microsoft_upload" in sys.modules:
    del sys.modules["src.actions.adapters.microsoft_upload"]


def pytest_configure(config):
    """pytest hook: Set environment variables before test collection begins.

    This runs VERY early in pytest lifecycle, before any test modules are imported.
    """
    os.environ["MS_UPLOAD_CHUNK_SIZE_BYTES"] = VALID_CHUNK_SIZE

    # Clear any cached imports with bad value
    if "src.actions.adapters.microsoft_upload" in sys.modules:
        del sys.modules["src.actions.adapters.microsoft_upload"]


@pytest.fixture(scope="session", autouse=True)
def _force_valid_chunk_size():
    """Force MS_UPLOAD_CHUNK_SIZE_BYTES to valid value for entire test session.

    This fixture runs before all tests and ensures the environment variable
    is set to a valid value (multiple of 320 KiB). This prevents import-time
    validation errors in microsoft_upload.py when the module is first loaded.

    Valid chunk size: 13 * 320 KiB = 4259840 bytes (4.0625 MiB)
    """
    # Ensure it's set at fixture setup time as well
    os.environ["MS_UPLOAD_CHUNK_SIZE_BYTES"] = VALID_CHUNK_SIZE

    # Clear any cached imports with bad value
    if "src.actions.adapters.microsoft_upload" in sys.modules:
        del sys.modules["src.actions.adapters.microsoft_upload"]

    yield
    # Don't clean up - other tests may depend on this
