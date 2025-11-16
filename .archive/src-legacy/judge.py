"""Judge stage: evaluate and rank draft responses."""

import json

from agents import Agent

from .publish import create_sort_key
from .schemas import Draft, Judgment, ScoredDraft


async def judge_drafts(
    task: str,
    drafts: list[Draft],
    allowed_providers: list[str] = None,
    require_citations: int = 0,
    margin_threshold: int = None,
    seed: int = None,
) -> Judgment:
    """Judge and rank draft responses using a strict rubric."""

    if not drafts:
        return Judgment(ranked=[], winner_provider="")

    # Create judge agent
    citation_penalty = (
        f"\n    CITATION REQUIREMENT: Responses must include at least {require_citations} citations. Apply penalty to 'Factual Support' score if fewer citations are provided."
        if require_citations > 0
        else ""
    )

    judge_instructions = f"""
    You are a strict judge evaluating responses to this task: "{task}"

    Scoring rubric (0-10 total):
    - Task Fit (0-4): Directly answers the user's task and respects constraints (length, format)
    - Factual Support (0-4): Claims are supported by evidence/sources given
    - Clarity (0-2): Coherent, concise, free of fluff or hedging
{citation_penalty}
    DISQUALIFY (score = 0) if: policy concerns or obvious hallucinations.

    For each draft, provide a score and reasoning. Return JSON format:
    {{
        "evaluations": [
            {{
                "draft_index": 0,
                "score": 8.5,
                "reasons": "Strong task fit (4/4), good evidence (3/4), clear writing (1.5/2)",
                "subscores": {{"task_fit": 4, "support": 3, "clarity": 1.5}}
            }},
            {{
                "draft_index": 1,
                "score": 6.0,
                "reasons": "Adequate task fit (3/4), weak evidence (2/4), unclear (1/2)",
                "subscores": {{"task_fit": 3, "support": 2, "clarity": 1}}
            }}
        ]
    }}

    Be strict but fair. Quality matters more than style.
    """

    judge = Agent(model="gpt-4", instructions=judge_instructions)

    # Prepare drafts for evaluation
    drafts_text = ""
    for i, draft in enumerate(drafts):
        drafts_text += f"""
DRAFT {i} (Provider: {draft.provider}):
Answer: {draft.answer}
Evidence: {', '.join(draft.evidence) if draft.evidence else 'None provided'}
Confidence: {draft.confidence}
Safety Flags: {', '.join(draft.safety_flags) if draft.safety_flags else 'None'}

---
"""

    evaluation_prompt = f"""
    Task: {task}

    Please evaluate these drafts:
    {drafts_text}

    Provide your evaluation in the specified JSON format.
    """

    try:
        # Run judge evaluation with optional seed
        judge_params = {
            "messages": [{"role": "user", "content": evaluation_prompt}],
            "max_tokens": 2000,
            "temperature": 0.1,  # Low temperature for consistent judging
        }
        if seed is not None:
            judge_params["seed"] = seed

        response = await judge.run(**judge_params)

        # Parse judge response
        try:
            result = json.loads(response.last_message())
            evaluations = result.get("evaluations", [])
        except json.JSONDecodeError:
            print("Warning: Judge response was not valid JSON, using fallback scoring")
            evaluations = [
                {"draft_index": i, "score": 5.0, "reasons": "Fallback scoring due to parse error"}
                for i in range(len(drafts))
            ]

        # Create scored drafts
        scored_drafts = []
        for eval_data in evaluations:
            try:
                draft_idx = eval_data["draft_index"]
                if 0 <= draft_idx < len(drafts):
                    original_draft = drafts[draft_idx]

                    # Check citation requirement and disqualify if insufficient
                    if require_citations > 0:
                        citation_count = len(original_draft.evidence)
                        if citation_count < require_citations:
                            print(
                                f"Disqualifying {original_draft.provider}: {citation_count} citations < {require_citations} required"
                            )
                            scored_draft = ScoredDraft(
                                provider=original_draft.provider,
                                answer=original_draft.answer,
                                evidence=original_draft.evidence,
                                confidence=original_draft.confidence,
                                safety_flags=original_draft.safety_flags + ["disqualified_citations"],
                                score=0.0,  # Disqualified
                                reasons=f"DISQUALIFIED: Only {citation_count} citations, {require_citations} required",
                                subscores={"task_fit": 0, "support": 0, "clarity": 0},
                            )
                            scored_drafts.append(scored_draft)
                            continue

                    scored_draft = ScoredDraft(
                        provider=original_draft.provider,
                        answer=original_draft.answer,
                        evidence=original_draft.evidence,
                        confidence=original_draft.confidence,
                        safety_flags=original_draft.safety_flags,
                        score=eval_data.get("score", 0.0),
                        reasons=eval_data.get("reasons", ""),
                        subscores=eval_data.get("subscores", {}),
                    )
                    scored_drafts.append(scored_draft)
            except (KeyError, IndexError) as e:
                print(f"Warning: Skipping invalid evaluation entry: {e}")

        # Rank by score with deterministic tie-breakers (highest first)
        if allowed_providers is None:
            allowed_providers = []
        ranked = sorted(scored_drafts, key=lambda x: create_sort_key(x, allowed_providers))

        # Check for margin threshold short-circuit
        if margin_threshold and len(ranked) >= 2:
            top_score = ranked[0].score
            second_score = ranked[1].score
            margin = top_score - second_score

            if margin >= margin_threshold:
                print(f"Margin threshold met: {margin:.1f} >= {margin_threshold} - skipping second pass")

        # Determine winner
        winner_provider = ranked[0].provider if ranked else ""

        print(f"Judge ranked {len(ranked)} drafts")
        if ranked:
            print(f"Winner: {winner_provider} (score: {ranked[0].score})")
            if margin_threshold and len(ranked) >= 2:
                print(f"Score margin: {ranked[0].score - ranked[1].score:.1f}")

        return Judgment(ranked=ranked, winner_provider=winner_provider)

    except Exception as e:
        print(f"Error during judging: {e}")
        # Fallback: return drafts with default scores
        fallback_scored = [
            ScoredDraft(
                provider=draft.provider,
                answer=draft.answer,
                evidence=draft.evidence,
                confidence=draft.confidence,
                safety_flags=draft.safety_flags,
                score=5.0,
                reasons="Fallback scoring due to judge error",
                subscores={"task_fit": 2, "support": 2, "clarity": 1},
            )
            for draft in drafts
        ]

        return Judgment(ranked=fallback_scored, winner_provider=fallback_scored[0].provider if fallback_scored else "")
