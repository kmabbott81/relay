"""
Temporary import redirect shim for src.* → relay_ai.platform.* migration.

This module installs a custom MetaPathFinder/Loader that intercepts
'from src.*' imports and redirects them to new locations without requiring
changes to 197+ source files.

Usage:
    from relay_ai.compat.import_redirect import install_src_redirect
    install_src_redirect()  # Call early in app startup or test setup

Cleanup:
    Remove this module after running codemod to rewrite all imports.

SHIM_REMOVE_PLAN:
    Timeline: Within 48 hours of merge to main

    Steps:
    1. Run codemod to rewrite imports:
       python tools/rewire_imports.py
       # Rewrites all "from src.*" → "from relay_ai.platform.*"

    2. Verify tests still pass:
       pytest -q  # Expect all green

    3. Remove shim and hooks:
       git rm relay_ai/compat/import_redirect.py
       git rm relay_ai/compat/__init__.py
       # Remove install_src_redirect() calls from:
       #   - relay_ai/platform/api/mvp.py
       #   - relay_ai/platform/tests/tests/conftest.py

    4. Commit and merge:
       git commit -m "refactor: remove import redirect shim after codemod"

    Dependencies:
    - tools/rewire_imports.py (create from pattern in user message)
    - Full test suite passing
    - No production traffic during codemod execution
"""

import importlib
import importlib.abc
import importlib.util
import sys
from typing import Optional


# Map old import paths to new locations
IMPORT_MAP = {
    "src.knowledge": "relay_ai.platform.api.knowledge",
    "src.stream": "relay_ai.platform.api.stream",
    "src.memory": "relay_ai.platform.security.memory",
    "src.monitoring": "relay_ai.platform.monitoring",
    "tests": "relay_ai.platform.tests.tests",  # Old tests/ → new relay_ai/platform/tests/tests/
}


def _resolve_new_path(fullname: str) -> Optional[str]:
    """Convert old src.* import path to new relay_ai.* path."""
    for old_prefix, new_prefix in IMPORT_MAP.items():
        if fullname == old_prefix or fullname.startswith(old_prefix + "."):
            # Replace prefix: "src.knowledge.api" → "relay_ai.platform.api.knowledge.api"
            return new_prefix + fullname[len(old_prefix) :]
    return None


class _SrcImportProxy(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """
    Custom import hook that intercepts src.* imports and redirects to relay_ai.*.

    Installed at head of sys.meta_path so catches imports before standard machinery.
    """

    def find_spec(self, fullname: str, path=None, target=None):
        """Intercept import and find real module at new location."""
        new_name = _resolve_new_path(fullname)
        if not new_name:
            return None

        try:
            real_spec = importlib.util.find_spec(new_name)
        except (ImportError, ModuleNotFoundError):
            return None

        if real_spec is None:
            return None

        # For packages, mark as such so Python knows it can have submodules
        submodule_search_locations = real_spec.submodule_search_locations if real_spec else None

        # Return a spec that uses us as the loader
        spec = importlib.util.spec_from_loader(
            fullname,
            self,
            origin=real_spec.origin,
            is_package=real_spec.submodule_search_locations is not None
        )
        if spec and real_spec and real_spec.submodule_search_locations:
            spec.submodule_search_locations = real_spec.submodule_search_locations
        return spec

    def create_module(self, spec):
        """Return None to use default module creation."""
        return None

    def exec_module(self, module):
        """
        Execute module by loading the real one and aliasing it.

        This ensures all subsequent imports of the old name get the same
        module instance as the new name.
        """
        new_name = _resolve_new_path(module.__name__)
        if not new_name:
            return

        # Import the real module at new location (this triggers any submodule loading)
        real_module = importlib.import_module(new_name)

        # Alias the old name to real module in sys.modules
        sys.modules[module.__name__] = real_module

        # Also ensure parent packages are aliased so nested imports work
        # E.g., if src.knowledge.rate_limit was redirected, ensure src.knowledge exists
        parts = module.__name__.split(".")
        for i in range(1, len(parts)):
            parent_name = ".".join(parts[:i])
            real_parent_name = _resolve_new_path(parent_name)
            if real_parent_name and real_parent_name not in sys.modules:
                try:
                    parent_mod = importlib.import_module(real_parent_name)
                    sys.modules[parent_name] = parent_mod
                except (ImportError, ModuleNotFoundError):
                    pass  # Parent might not exist yet


def install_src_redirect():
    """
    Install the src.* import redirect.

    Call this early in app startup (before imports fail).
    Safe to call multiple times (idempotent).
    """
    # Check if already installed
    for hook in sys.meta_path:
        if isinstance(hook, _SrcImportProxy):
            return  # Already installed

    # Insert at head of meta_path so we catch imports first
    sys.meta_path.insert(0, _SrcImportProxy())


# Auto-install on module load (safety net for when import_redirect is imported)
# This ensures the redirect is active even if someone forgets to call install_src_redirect()
install_src_redirect()
