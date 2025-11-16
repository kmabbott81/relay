"""Natural Language Commanding System.

Turns plain English commands into safe, auditable, cross-connector action plans.

Sprint 39 - Pure deterministic parsing with no LLM calls.
"""

from .executor import ExecutionResult, execute_plan
from .intents import Intent, parse_intent
from .ner_contacts import Contact, resolve_contact
from .planner import Plan, make_plan

__all__ = [
    "Intent",
    "parse_intent",
    "Contact",
    "resolve_contact",
    "Plan",
    "make_plan",
    "execute_plan",
    "ExecutionResult",
]
