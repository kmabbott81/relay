"""
Template Registry System (Sprint 32)

Versioned templates with parameter schemas for safe workflow execution.
"""

from .loader import load_and_validate
from .registry import deprecate, get, list_templates, register
from .schemas import validate

__all__ = [
    "register",
    "get",
    "list_templates",
    "deprecate",
    "validate",
    "load_and_validate",
]
