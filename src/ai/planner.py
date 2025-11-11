"""AI Action Planner - Sprint 55 Week 3.

Converts natural language prompts into structured action plans.
Uses LLM to extract intent, parameters, and action sequences.

Pipeline test: Verifying GitHub → djp-workflow → Relay deployment flow.
"""

from typing import Any, Optional

from relay_ai.schemas.ai_plan import ActionPlan
from relay_ai.schemas.ai_plan import PlannedAction as ActionStep


class ActionPlanner:
    """Plans action sequences from natural language prompts."""

    def __init__(self):
        """Initialize planner with available actions."""
        from src.actions import get_executor

        self.executor = get_executor()
        self.available_actions = self.executor.list_actions()

    async def plan(self, prompt: str, context: Optional[dict[str, Any]] = None) -> ActionPlan:
        """Generate action plan from natural language prompt.

        Args:
            prompt: Natural language description of what to do
            context: Optional context (calendar, email history, etc.)

        Returns:
            Structured action plan with steps and parameters
        """
        # Build system prompt with available actions
        actions_description = self._format_available_actions()

        system_prompt = f"""You are an AI assistant that converts natural language requests into structured action plans.

Available actions:
{actions_description}

Your task:
1. Analyze the user's request
2. Determine which actions are needed
3. Extract parameters for each action
4. Return a structured JSON plan

Rules:
- Only use actions from the available list
- Extract all required parameters from the prompt
- If information is missing, note it in the explanation
- For email addresses, validate format
- For dates/times, use ISO 8601 format
- For multi-step workflows, specify dependencies

Output format (JSON):
{{
  "intent": "brief description of what user wants",
  "steps": [
    {{
      "action_id": "gmail.send",
      "description": "Send thank you email to John",
      "params": {{
        "to": "john@example.com",
        "subject": "Thank you for yesterday's meeting",
        "body": "<p>Hi John,...</p>"
      }},
      "depends_on": null
    }}
  ],
  "confidence": 0.95,
  "explanation": "Clear request with all required information"
}}
"""

        user_message = f"User request: {prompt}"

        if context:
            user_message += f"\n\nContext:\n{self._format_context(context)}"

        # Call LLM (using existing DJP infrastructure)
        plan_json = await self._call_llm(system_prompt, user_message)

        # Parse and validate
        plan = ActionPlan(
            prompt=prompt,
            intent=plan_json["intent"],
            steps=[ActionStep(**step) for step in plan_json["steps"]],
            confidence=plan_json["confidence"],
            explanation=plan_json["explanation"],
        )

        return plan

    def _format_available_actions(self) -> str:
        """Format available actions for LLM prompt."""
        lines = []
        for action in self.available_actions:
            lines.append(f"- {action['id']}: {action.get('description', 'No description')}")
            if action.get("parameters"):
                params = ", ".join(action["parameters"].get("required", []))
                lines.append(f"  Required: {params}")
        return "\n".join(lines)

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format context for LLM prompt."""
        lines = []
        if "calendar" in context:
            lines.append("Calendar availability:")
            for slot in context["calendar"].get("free_slots", []):
                lines.append(f"  - {slot}")

        if "email_history" in context:
            lines.append("\nRecent email threads:")
            for thread in context["email_history"]:
                lines.append(f"  - {thread.get('subject', 'No subject')}")

        return "\n".join(lines)

    async def _call_llm(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """Call LLM to generate plan.

        Uses existing DJP infrastructure for LLM calls.
        """
        import json
        import os

        # Check if we have OpenAI configured
        if not os.getenv("OPENAI_API_KEY"):
            # Mock mode for testing
            return {
                "intent": "send_email",
                "steps": [
                    {
                        "action_id": "gmail.send",
                        "description": "Send email (mock mode - no API key configured)",
                        "params": {
                            "to": "example@example.com",
                            "subject": "Test",
                            "body": "<p>Mock email body</p>",
                        },
                        "depends_on": None,
                    }
                ],
                "confidence": 0.5,
                "explanation": "Mock mode: No OpenAI API key configured. This is a placeholder plan.",
            }

        # Real LLM call using OpenAI
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for structured outputs
                max_tokens=1000,
            )

            plan_json = json.loads(response.choices[0].message.content)
            return plan_json

        except Exception as e:
            # Fallback to mock on error
            return {
                "intent": "error",
                "steps": [],
                "confidence": 0.0,
                "explanation": f"Error calling LLM: {str(e)}",
            }
