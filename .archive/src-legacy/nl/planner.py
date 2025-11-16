"""Action Planner for Natural Language Commands.

Converts parsed intents into executable action plans via URG grounding.

NO LLM calls - pure deterministic planning logic.
"""

import os
import uuid
from dataclasses import dataclass, field

from ..graph.search import search
from .intents import Intent, parse_intent
from .ner_contacts import resolve_contacts


@dataclass
class ActionStep:
    """Single step in an action plan."""

    action: str  # e.g., "message.reply", "contact.email"
    graph_id: str  # URG resource ID
    resource: dict  # Full URG resource
    payload: dict  # Action-specific payload
    description: str  # Human-readable description


@dataclass
class Plan:
    """Executable action plan."""

    plan_id: str
    intent: Intent
    steps: list[ActionStep] = field(default_factory=list)
    requires_approval: bool = False
    risk_level: str = "low"  # low, medium, high
    preview: str = ""  # Human-readable summary
    metadata: dict = field(default_factory=dict)


# High-risk action patterns (from env or defaults)
def _get_high_risk_actions() -> set[str]:
    """Get high-risk actions from environment."""
    default = "delete,external_email,share_outside"
    actions_str = os.getenv("NL_HIGH_RISK_ACTIONS", default)
    return set(actions_str.split(","))


# Tenant domain list (for external email detection)
def _get_tenant_domains(tenant: str) -> set[str]:
    """Get known domains for tenant."""
    # In production, this would query tenant config
    # For now, return common internal domains
    return {"example.com", "company.com", "internal.com"}


def make_plan(command: str, tenant: str, user_id: str) -> Plan:
    """Generate executable plan from natural language command.

    Process:
    1. Parse intent from command
    2. Ground entities to URG via search
    3. Select resources and connectors
    4. Build ordered action steps
    5. Detect high-risk operations
    6. Generate human-readable preview

    Args:
        command: Natural language command
        tenant: Tenant ID
        user_id: User ID

    Returns:
        Plan object ready for execution

    Raises:
        ValueError: If command cannot be parsed or grounded
    """
    # Parse intent
    intent = parse_intent(command)

    if intent.verb == "unknown":
        raise ValueError(f"Could not parse command: {command}")

    # Create plan
    plan_id = f"nlp-{uuid.uuid4().hex[:8]}"
    plan = Plan(
        plan_id=plan_id,
        intent=intent,
        metadata={"tenant": tenant, "user_id": user_id},
    )

    # Build steps based on verb
    if intent.verb == "email":
        _plan_email(plan, tenant, user_id)
    elif intent.verb == "message":
        _plan_message(plan, tenant, user_id)
    elif intent.verb == "forward":
        _plan_forward(plan, tenant, user_id)
    elif intent.verb == "reply":
        _plan_reply(plan, tenant, user_id)
    elif intent.verb == "schedule":
        _plan_schedule(plan, tenant, user_id)
    elif intent.verb == "find":
        _plan_find(plan, tenant, user_id)
    elif intent.verb == "delete":
        _plan_delete(plan, tenant, user_id)
    elif intent.verb == "create":
        _plan_create(plan, tenant, user_id)
    elif intent.verb == "update":
        _plan_update(plan, tenant, user_id)
    else:
        raise ValueError(f"Unsupported verb: {intent.verb}")

    # Assess risk level
    _assess_risk(plan, tenant)

    # Generate preview
    _generate_preview(plan)

    return plan


def _plan_email(plan: Plan, tenant: str, user_id: str):
    """Plan email action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Resolve contacts from targets
    contacts = resolve_contacts(intent.targets, tenant)

    if not contacts:
        raise ValueError(f"Could not resolve any contacts from: {intent.targets}")

    # Extract email body/subject from artifacts
    subject = "Message from NL Command"
    body = ""

    if intent.artifacts:
        # First artifact is body/subject context
        body = intent.artifacts[0] if len(intent.artifacts) > 0 else ""

    for contact in contacts:
        # Create action step
        step = ActionStep(
            action="contact.email",
            graph_id=contact.graph_id or f"contact-{contact.email}",
            resource={
                "type": "contact",
                "title": contact.name,
                "participants": [contact.email],
                "source": contact.source,
            },
            payload={
                "to": [contact.email],  # Add 'to' field for risk assessment
                "subject": subject,
                "body": body,
            },
            description=f"Send email to {contact.name} ({contact.email})",
        )
        plan.steps.append(step)


def _plan_message(plan: Plan, tenant: str, user_id: str):
    """Plan messaging action (Teams/Slack).

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Determine source from constraints or default
    source = intent.constraints.get("source", "teams")

    # Resolve contacts
    contacts = resolve_contacts(intent.targets, tenant)

    if not contacts:
        raise ValueError(f"Could not resolve any contacts from: {intent.targets}")

    # Extract message body
    body = intent.artifacts[0] if intent.artifacts else ""

    for contact in contacts:
        step = ActionStep(
            action="contact.message",
            graph_id=contact.graph_id or f"contact-{contact.email}",
            resource={
                "type": "contact",
                "title": contact.name,
                "participants": [contact.email],
                "source": source,
            },
            payload={"body": body},
            description=f"Send message to {contact.name} via {source}",
        )
        plan.steps.append(step)


def _plan_forward(plan: Plan, tenant: str, user_id: str):
    """Plan forward action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Find message to forward
    source = intent.constraints.get("source")

    # Search for messages matching artifacts
    query = " ".join(intent.artifacts) if intent.artifacts else ""
    if not query:
        query = "latest"

    messages = search(
        query,
        tenant=tenant,
        type="message",
        source=source,
        limit=1,
    )

    if not messages:
        raise ValueError(f"Could not find message matching: {query}")

    message = messages[0]

    # Resolve forward targets
    contacts = resolve_contacts(intent.targets, tenant)

    if not contacts:
        raise ValueError(f"Could not resolve recipients: {intent.targets}")

    # Create forward step
    to_emails = [c.email for c in contacts]

    step = ActionStep(
        action="message.forward",
        graph_id=message.get("id", ""),
        resource=message,
        payload={"to": to_emails, "comment": ""},
        description=f"Forward message '{message.get('title', 'message')}' to {', '.join(to_emails)}",
    )
    plan.steps.append(step)


def _plan_reply(plan: Plan, tenant: str, user_id: str):
    """Plan reply action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Find message to reply to
    source = intent.constraints.get("source")

    # Build search query from artifacts and targets
    query_parts = []
    if intent.artifacts:
        query_parts.extend(intent.artifacts)
    if intent.targets:
        query_parts.extend(intent.targets)

    query = " ".join(query_parts) if query_parts else "latest"

    messages = search(
        query,
        tenant=tenant,
        type="message",
        source=source,
        limit=1,
    )

    if not messages:
        raise ValueError(f"Could not find message to reply to: {query}")

    message = messages[0]

    # Extract reply body (often in quoted text)
    body = ""
    for artifact in intent.artifacts:
        if artifact.startswith('"') or len(artifact) > 10:
            body = artifact
            break

    if not body:
        body = "Reply from NL Command"

    step = ActionStep(
        action="message.reply",
        graph_id=message.get("id", ""),
        resource=message,
        payload={"body": body},
        description=f"Reply to message from {message.get('title', 'sender')}",
    )
    plan.steps.append(step)


def _plan_schedule(plan: Plan, tenant: str, user_id: str):
    """Plan scheduling action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Resolve participants
    contacts = resolve_contacts(intent.targets, tenant)

    if not contacts:
        raise ValueError(f"Could not resolve meeting participants: {intent.targets}")

    # Extract meeting details
    subject = intent.artifacts[0] if intent.artifacts else "Meeting"
    time_constraint = intent.constraints.get("time", "")

    step = ActionStep(
        action="event.create",
        graph_id=f"event-new-{uuid.uuid4().hex[:8]}",
        resource={
            "type": "event",
            "title": subject,
            "source": "outlook",
        },
        payload={
            "subject": subject,
            "attendees": [c.email for c in contacts],
            "time": time_constraint,
        },
        description=f"Schedule meeting: {subject} with {', '.join(c.name for c in contacts)}",
    )
    plan.steps.append(step)


def _plan_find(plan: Plan, tenant: str, user_id: str):
    """Plan find/search action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Build query
    query_parts = []
    if intent.artifacts:
        query_parts.extend(intent.artifacts)
    if intent.targets:
        query_parts.extend(intent.targets)

    query = " ".join(query_parts)

    source = intent.constraints.get("source")
    type_filter = None

    # Infer type from artifacts
    for artifact in intent.artifacts:
        artifact_lower = artifact.lower()
        if "message" in artifact_lower or "email" in artifact_lower:
            type_filter = "message"
            break
        elif "file" in artifact_lower or "document" in artifact_lower:
            type_filter = "file"
            break

    # Execute search
    results = search(
        query,
        tenant=tenant,
        type=type_filter,
        source=source,
        limit=10,
    )

    # Create search result step (informational)
    step = ActionStep(
        action="search.execute",
        graph_id="search-result",
        resource={"type": "search", "query": query},
        payload={"results": results},
        description=f"Search for: {query} (found {len(results)} results)",
    )
    plan.steps.append(step)


def _plan_delete(plan: Plan, tenant: str, user_id: str):
    """Plan delete action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Find resources to delete
    source = intent.constraints.get("source")
    query = " ".join(intent.artifacts) if intent.artifacts else ""

    results = search(
        query,
        tenant=tenant,
        source=source,
        limit=10,
    )

    if not results:
        raise ValueError(f"Could not find resources to delete: {query}")

    # Create delete steps
    for resource in results:
        step = ActionStep(
            action=f"{resource.get('type', 'resource')}.delete",
            graph_id=resource.get("id", ""),
            resource=resource,
            payload={},
            description=f"Delete {resource.get('type', 'resource')}: {resource.get('title', 'item')}",
        )
        plan.steps.append(step)


def _plan_create(plan: Plan, tenant: str, user_id: str):
    """Plan create action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Infer what to create from artifacts
    source = intent.constraints.get("source", "notion")
    title = intent.artifacts[0] if intent.artifacts else "New item"

    step = ActionStep(
        action="page.create",
        graph_id=f"page-new-{uuid.uuid4().hex[:8]}",
        resource={"type": "page", "source": source},
        payload={"title": title},
        description=f"Create new page in {source}: {title}",
    )
    plan.steps.append(step)


def _plan_update(plan: Plan, tenant: str, user_id: str):
    """Plan update action.

    Args:
        plan: Plan to populate
        tenant: Tenant ID
        user_id: User ID
    """
    intent = plan.intent

    # Find resource to update
    source = intent.constraints.get("source")
    query = " ".join(intent.artifacts[:1]) if intent.artifacts else ""

    results = search(
        query,
        tenant=tenant,
        source=source,
        limit=1,
    )

    if not results:
        raise ValueError(f"Could not find resource to update: {query}")

    resource = results[0]

    # Extract update payload from later artifacts
    update_value = intent.artifacts[1] if len(intent.artifacts) > 1 else ""

    step = ActionStep(
        action=f"{resource.get('type', 'resource')}.update",
        graph_id=resource.get("id", ""),
        resource=resource,
        payload={"update": update_value},
        description=f"Update {resource.get('type', 'resource')}: {resource.get('title', 'item')}",
    )
    plan.steps.append(step)


def _assess_risk(plan: Plan, tenant: str):
    """Assess risk level of plan and set approval requirement.

    Args:
        plan: Plan to assess
        tenant: Tenant ID
    """
    tenant_domains = _get_tenant_domains(tenant)

    risk_score = 0
    risk_reasons = []

    for step in plan.steps:
        # Check for high-risk actions
        if "delete" in step.action:
            risk_score += 50
            risk_reasons.append(f"Delete operation: {step.action}")

        # Check for external emails
        if "email" in step.action or "forward" in step.action:
            recipients = step.payload.get("to", [])
            if not isinstance(recipients, list):
                recipients = [recipients]

            for recipient in recipients:
                if "@" in str(recipient):
                    domain = str(recipient).split("@")[1]
                    if domain not in tenant_domains:
                        risk_score += 30
                        risk_reasons.append(f"External email: {recipient}")

        # Check for bulk operations
        pass  # Handled by step count

    # Bulk operations
    if len(plan.steps) > 10:
        risk_score += 20
        risk_reasons.append(f"Bulk operation: {len(plan.steps)} steps")

    # Set risk level
    if risk_score >= 50:
        plan.risk_level = "high"
        plan.requires_approval = True
    elif risk_score >= 20:
        plan.risk_level = "medium"
        plan.requires_approval = os.getenv("NL_APPROVE_MEDIUM", "false").lower() == "true"
    else:
        plan.risk_level = "low"
        plan.requires_approval = False

    plan.metadata["risk_score"] = risk_score
    plan.metadata["risk_reasons"] = risk_reasons


def _generate_preview(plan: Plan):
    """Generate human-readable preview of plan.

    Args:
        plan: Plan to preview
    """
    lines = []

    lines.append(f"Command: {plan.intent.original_command}")
    lines.append(f"Action: {plan.intent.verb}")
    lines.append(f"Risk Level: {plan.risk_level}")
    lines.append("")
    lines.append("Steps:")

    for i, step in enumerate(plan.steps, 1):
        lines.append(f"  {i}. {step.description}")

    if plan.requires_approval:
        lines.append("")
        lines.append("APPROVAL REQUIRED")
        risk_reasons = plan.metadata.get("risk_reasons", [])
        if risk_reasons:
            lines.append("Reasons:")
            for reason in risk_reasons:
                lines.append(f"  - {reason}")

    plan.preview = "\n".join(lines)
