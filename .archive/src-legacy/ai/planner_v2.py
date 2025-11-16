"""AI Orchestrator v0.1 Planner - Strict JSON schema with cost control.

Sprint 55 Week 3: Convert natural language to structured action plans.
"""

import json
import time
import uuid

from relay_ai.config import get_openai_client_and_limits
from relay_ai.schemas.ai_plan import PlannedAction, PlanResult
from relay_ai.telemetry.prom import record_ai_planner, record_ai_tokens


def plan_actions(nl_prompt: str) -> tuple[PlanResult, dict]:
    """Generate action plan from natural language with cost control.

    Args:
        nl_prompt: Natural language prompt

    Returns:
        Tuple of (PlanResult, meta_dict)
        meta_dict contains: model, duration, tokens_in, tokens_out

    Raises:
        ValueError: If API key missing or budget exceeded
    """
    start = time.perf_counter()

    try:
        # Get OpenAI client with cost limits
        client, max_output_tokens, model = get_openai_client_and_limits()

        # Build system prompt with available actions
        system_prompt = """You are an AI assistant that converts natural language into structured action plans.

Available actions:
- gmail.send: Send email via Gmail (provider: google)
  Required params: to (email), subject (string), text (string)
  Optional params: html (string), cc (list[email]), bcc (list[email])

- outlook.send: Send email via Outlook (provider: microsoft)
  Required params: to (email), subject (string), text (string)
  Optional params: html (string), cc (list[email]), bcc (list[email])

Your task:
1. Extract the user's intent
2. Determine which action(s) to execute
3. Extract all required parameters
4. Return structured JSON

Output format (strict JSON):
{
  "intent": "brief description",
  "confidence": 0.95,
  "actions": [
    {
      "provider": "google",
      "action": "gmail.send",
      "params": {
        "to": "user@example.com",
        "subject": "Subject here",
        "text": "Body text"
      },
      "client_request_id": null
    }
  ],
  "notes": "Optional notes or warnings"
}

Rules:
- Only use gmail.send or outlook.send
- Validate email addresses
- Extract all required params
- Set confidence based on information completeness
- Add notes if information is missing or ambiguous
"""

        # Call OpenAI with JSON mode
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User request: {nl_prompt}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=max_output_tokens,
        )

        # Extract response
        plan_json = json.loads(response.choices[0].message.content)
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens

        # Validate and parse plan
        if "actions" not in plan_json:
            raise ValueError("Plan missing 'actions' field")

        # Add client_request_id to each action if missing
        for action_data in plan_json["actions"]:
            if not action_data.get("client_request_id"):
                action_data["client_request_id"] = str(uuid.uuid4())

        # Build PlanResult
        plan = PlanResult(
            intent=plan_json.get("intent", "unknown"),
            confidence=plan_json.get("confidence", 0.5),
            actions=[PlannedAction(**action) for action in plan_json["actions"]],
            notes=plan_json.get("notes"),
        )

        # Record metrics
        duration = time.perf_counter() - start
        record_ai_planner(status="ok", duration_seconds=duration)
        record_ai_tokens(tokens_input=tokens_in, tokens_output=tokens_out)

        meta = {
            "model": model,
            "duration": duration,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

        return plan, meta

    except ValueError:
        # Configuration or validation error
        duration = time.perf_counter() - start
        record_ai_planner(status="error", duration_seconds=duration)
        raise

    except Exception as e:
        # Unexpected error
        duration = time.perf_counter() - start
        record_ai_planner(status="error", duration_seconds=duration)
        raise ValueError(f"Planning failed: {str(e)}") from e
