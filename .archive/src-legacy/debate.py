"""Debate stage: multiple agents generate draft responses."""

import asyncio
import json

from agents import Agent

from .config import get_provider_api_keys
from .corpus import search_corpus
from .retries import RetryExhaustedError, api_retry
from .schemas import Draft


async def run_debate(
    task: str,
    max_tokens: int = 1200,
    temperature: float = 0.3,
    require_citations: int = 0,
    max_debaters: int = None,
    timeout_s: int = None,
    fastpath: bool = False,
    seed: int = None,
    max_cost_usd: float = None,
    corpus_docs: list = None,
    grounded_required: int = 0,
) -> list[Draft]:
    """Run debate with multiple agents to generate diverse draft responses."""

    # Get available API keys
    api_keys = get_provider_api_keys()

    # Instructions for debater agents
    citation_requirement = (
        f" IMPORTANT: Include at least {require_citations} specific citations or sources in your evidence list."
        if require_citations > 0
        else ""
    )

    # Add grounded mode instructions if corpus is provided
    grounded_instruction = ""
    corpus_context = ""
    if corpus_docs and grounded_required > 0:
        grounded_instruction = f" CRITICAL: You must include at least {grounded_required} citations from the provided context sources using [Title] format."

        # Search corpus for relevant documents
        relevant_docs = search_corpus(task, k=6) if corpus_docs else []
        if relevant_docs:
            corpus_context = "\n\nAVAILABLE CONTEXT SOURCES:\n"
            for _, doc in enumerate(relevant_docs, 1):
                # Truncate document text to fit in prompt
                doc_excerpt = doc.text[:500] + "..." if len(doc.text) > 500 else doc.text
                corpus_context += f"\n[{doc.title}]:\n{doc_excerpt}\n"

    instructions = f"""
    Solve the task. Provide an 'answer' (<= ~250 words unless told otherwise).
    List 2–5 'evidence' bullet points (citations, sources, or reasoning steps).{citation_requirement}{grounded_instruction}
    Give 'confidence' [0,1]. Add any 'safety_flags'.

    When citing provided sources, use the format [Source Title] and include a brief relevant snippet in your evidence.{corpus_context}

    Respond in JSON format:
    {{
        "answer": "your response here",
        "evidence": ["point 1", "point 2", "point 3"],
        "confidence": 0.8,
        "safety_flags": []
    }}
    """

    # Define debater agents
    debaters = []

    # OpenAI agents (always included if API key available)
    if api_keys["openai"]:
        debaters.extend(
            [
                {"agent": Agent(model="gpt-4", instructions=instructions), "provider": "openai/gpt-4.1"},
                {"agent": Agent(model="gpt-4o-mini", instructions=instructions), "provider": "openai/gpt-4o-mini"},
            ]
        )

    # Adaptive debater selection: prioritize cost-effective models
    # Non-OpenAI agents (conditional on fastpath, cost limits, and API keys)
    non_openai_limit = 0 if fastpath else 2  # Default limit for non-OpenAI debaters

    # If cost budget is tight, reduce non-OpenAI debaters
    if max_cost_usd is not None and max_cost_usd < 0.02:  # Very tight budget
        non_openai_limit = 0
        print(f"Cost budget ${max_cost_usd:.4f} is tight - using only OpenAI models")
    elif max_cost_usd is not None and max_cost_usd < 0.05:  # Moderate budget
        non_openai_limit = 1
        print(f"Cost budget ${max_cost_usd:.4f} is moderate - limiting non-OpenAI models")

    added_non_openai = 0

    if non_openai_limit > 0 and api_keys["anthropic"] and added_non_openai < non_openai_limit:
        try:
            debaters.append(
                {
                    "agent": Agent(model="anthropic/claude-3-5-sonnet-20240620", instructions=instructions),
                    "provider": "anthropic/claude-3-5-sonnet-20240620",
                }
            )
            added_non_openai += 1
        except Exception as e:
            print(f"Warning: Could not create Anthropic agent: {e}")

    if non_openai_limit > 0 and api_keys["google"] and added_non_openai < non_openai_limit:
        try:
            debaters.append(
                {
                    "agent": Agent(model="google/gemini-1.5-pro", instructions=instructions),
                    "provider": "google/gemini-1.5-pro",
                }
            )
            added_non_openai += 1
        except Exception as e:
            print(f"Warning: Could not create Google agent: {e}")

    # Apply max_debaters limit if specified
    if max_debaters is not None and max_debaters > 0:
        debaters = debaters[:max_debaters]

    if fastpath:
        print("Fast-path mode: using only OpenAI models")
    if max_debaters:
        print(f"Limited to {max_debaters} debaters")

    if not debaters:
        raise RuntimeError("No debater agents available. Check your API keys.")

    # Run all debaters in parallel
    async def run_single_debater(debater_info):
        """Run a single debater agent with retry logic."""

        @api_retry
        async def _run_agent_with_retry():
            agent = debater_info["agent"]
            provider = debater_info["provider"]

            # Run the agent with optional seed
            run_params = {
                "messages": [{"role": "user", "content": task}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if seed is not None:
                run_params["seed"] = seed

            return await agent.run(**run_params), provider

        try:
            response, provider = await _run_agent_with_retry()

            # Parse the JSON response
            try:
                result = json.loads(response.last_message())
                return Draft(
                    provider=provider,
                    answer=result.get("answer", ""),
                    evidence=result.get("evidence", []),
                    confidence=result.get("confidence", 0.0),
                    safety_flags=result.get("safety_flags", []),
                )
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return Draft(
                    provider=provider,
                    answer=response.last_message(),
                    evidence=[],
                    confidence=0.5,
                    safety_flags=["json_parse_error"],
                )

        except RetryExhaustedError as e:
            # Handle retry exhaustion with clear error message
            print(f"Warning: {provider} failed after retries: {e}")
            return Draft(
                provider=provider,
                answer="",
                evidence=[],
                confidence=0.0,
                safety_flags=["api_retry_exhausted", f"error_{e.attempt_count}_attempts"],
            )

        except Exception as e:
            print(f"Error running debater {debater_info['provider']}: {e}")
            return Draft(
                provider=debater_info["provider"],
                answer=f"Error: {str(e)}",
                evidence=[],
                confidence=0.0,
                safety_flags=["execution_error"],
            )

    # Execute all debaters concurrently with optional timeout
    print(f"Running debate with {len(debaters)} agents...")
    if timeout_s:
        print(f"Timeout: {timeout_s}s")
        try:
            drafts = await asyncio.wait_for(
                asyncio.gather(*[run_single_debater(d) for d in debaters]), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            print(f"Warning: Debate timed out after {timeout_s}s")
            # Return partial results or fallback
            drafts = []
    else:
        drafts = await asyncio.gather(*[run_single_debater(d) for d in debaters])

    # Filter out failed drafts
    valid_drafts = [d for d in drafts if d.answer and not d.answer.startswith("Error:")]

    print(f"Generated {len(valid_drafts)} valid drafts")
    return valid_drafts
