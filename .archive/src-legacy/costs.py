"""Cost estimation and budget management for DJP workflows."""

from dataclasses import dataclass

# Price table per 1M tokens (input, output) - these are estimates
# Update these values based on current provider pricing
PRICING_TABLE = {
    "openai/gpt-4": (30.0, 60.0),
    "openai/gpt-4o": (5.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.6),
    "openai/o1-preview": (15.0, 60.0),
    "openai/o1-mini": (3.0, 12.0),
    "anthropic/claude-3-5-sonnet-20240620": (3.0, 15.0),
    "anthropic/claude-3-haiku-20240307": (0.25, 1.25),
    "google/gemini-1.5-pro": (3.5, 10.5),
    "google/gemini-1.5-flash": (0.075, 0.3),
}

# Default cost assumptions for projection
DEFAULT_TOKENS_PER_DRAFT = {
    "debate": {"input": 500, "output": 800},  # Per debater
    "judge": {"input": 2000, "output": 300},  # Judge evaluates all drafts
    "total_overhead": {"input": 200, "output": 100},  # System overhead
}


@dataclass
class CostProjection:
    """Container for cost projection results."""

    debate_cost: float
    judge_cost: float
    total_cost: float
    breakdown_by_provider: dict[str, float]
    total_tokens_projected: int


def get_provider_cost(provider: str, tokens_in: int, tokens_out: int) -> float:
    """
    Calculate cost for a specific provider and token usage.

    Args:
        provider: Provider/model identifier
        tokens_in: Input tokens
        tokens_out: Output tokens

    Returns:
        Cost in USD
    """
    if provider not in PRICING_TABLE:
        # Return 0 for unknown providers rather than failing
        return 0.0

    input_price, output_price = PRICING_TABLE[provider]

    # Convert per-1M-token prices to actual costs
    input_cost = (tokens_in / 1_000_000) * input_price
    output_cost = (tokens_out / 1_000_000) * output_price

    return input_cost + output_cost


def project_workflow_cost(
    max_debaters: int = 3,
    max_tokens: int = 1200,
    require_citations: int = 0,
    fastpath: bool = False,
    allowed_models: list = None,
) -> CostProjection:
    """
    Project the cost of a workflow run based on parameters.

    Args:
        max_debaters: Maximum number of debaters
        max_tokens: Maximum tokens per response
        require_citations: Number of required citations (affects complexity)
        fastpath: Whether fastpath mode is enabled
        allowed_models: List of allowed models

    Returns:
        CostProjection object with cost breakdown
    """
    if allowed_models is None:
        allowed_models = ["openai/gpt-4o", "openai/gpt-4o-mini"]

    # Use the most expensive model from allowed list for conservative estimate
    primary_provider = get_most_expensive_provider(allowed_models)

    # Estimate actual debaters (fastpath reduces this)
    actual_debaters = min(max_debaters, 2 if fastpath else max_debaters)

    # Base token estimates
    debate_tokens_in = DEFAULT_TOKENS_PER_DRAFT["debate"]["input"] * actual_debaters
    debate_tokens_out = min(max_tokens, DEFAULT_TOKENS_PER_DRAFT["debate"]["output"]) * actual_debaters

    # Judge tokens scale with number of drafts to evaluate
    judge_tokens_in = DEFAULT_TOKENS_PER_DRAFT["judge"]["input"] + (200 * actual_debaters)
    judge_tokens_out = DEFAULT_TOKENS_PER_DRAFT["judge"]["output"]

    # Citation requirements add complexity
    if require_citations > 0:
        citation_multiplier = 1.0 + (require_citations * 0.2)  # 20% more per required citation
        debate_tokens_in = int(debate_tokens_in * citation_multiplier)
        debate_tokens_out = int(debate_tokens_out * citation_multiplier)

    # Overhead tokens
    overhead_tokens_in = DEFAULT_TOKENS_PER_DRAFT["total_overhead"]["input"]
    overhead_tokens_out = DEFAULT_TOKENS_PER_DRAFT["total_overhead"]["output"]

    # Calculate costs
    debate_cost = get_provider_cost(primary_provider, debate_tokens_in, debate_tokens_out)
    judge_cost = get_provider_cost(primary_provider, judge_tokens_in, judge_tokens_out)
    overhead_cost = get_provider_cost(primary_provider, overhead_tokens_in, overhead_tokens_out)

    total_cost = debate_cost + judge_cost + overhead_cost
    total_tokens = (
        debate_tokens_in
        + debate_tokens_out
        + judge_tokens_in
        + judge_tokens_out
        + overhead_tokens_in
        + overhead_tokens_out
    )

    breakdown = {
        primary_provider: total_cost,
        "debate_stage": debate_cost,
        "judge_stage": judge_cost,
        "overhead": overhead_cost,
    }

    return CostProjection(
        debate_cost=debate_cost,
        judge_cost=judge_cost,
        total_cost=total_cost,
        breakdown_by_provider=breakdown,
        total_tokens_projected=total_tokens,
    )


def get_most_expensive_provider(providers: list) -> str:
    """
    Get the most expensive provider from a list for conservative estimates.

    Args:
        providers: List of provider/model identifiers

    Returns:
        Provider identifier with highest cost per token
    """
    if not providers:
        return "openai/gpt-4o"  # Default

    max_cost = 0
    most_expensive = providers[0]

    for provider in providers:
        if provider in PRICING_TABLE:
            # Use average of input/output pricing for comparison
            input_price, output_price = PRICING_TABLE[provider]
            avg_price = (input_price + output_price) / 2

            if avg_price > max_cost:
                max_cost = avg_price
                most_expensive = provider

    return most_expensive


def check_budget_limits(
    projected_cost: float, projected_tokens: int, budget_usd: float = None, budget_tokens: int = None
) -> tuple[bool, str, str]:
    """
    Check if projected usage fits within budget limits.

    Args:
        projected_cost: Projected cost in USD
        projected_tokens: Projected token usage
        budget_usd: Budget limit in USD (optional)
        budget_tokens: Budget limit in tokens (optional)

    Returns:
        Tuple of (within_budget, warning_message, error_message)
    """
    warnings = []
    errors = []

    # Check USD budget
    if budget_usd is not None:
        cost_ratio = projected_cost / budget_usd
        if cost_ratio > 1.0:
            errors.append(f"Projected cost ${projected_cost:.4f} exceeds budget ${budget_usd:.4f}")
        elif cost_ratio > 0.9:
            warnings.append(f"Projected cost ${projected_cost:.4f} is {cost_ratio:.1%} of budget ${budget_usd:.4f}")

    # Check token budget
    if budget_tokens is not None:
        token_ratio = projected_tokens / budget_tokens
        if token_ratio > 1.0:
            errors.append(f"Projected tokens {projected_tokens:,} exceeds budget {budget_tokens:,}")
        elif token_ratio > 0.9:
            warnings.append(f"Projected tokens {projected_tokens:,} is {token_ratio:.1%} of budget {budget_tokens:,}")

    within_budget = len(errors) == 0
    warning_msg = "; ".join(warnings) if warnings else ""
    error_msg = "; ".join(errors) if errors else ""

    return within_budget, warning_msg, error_msg


def format_cost_projection(projection: CostProjection) -> str:
    """
    Format a cost projection for display.

    Args:
        projection: CostProjection object

    Returns:
        Formatted string for console display
    """
    lines = [
        "Projected Cost Breakdown:",
        f"  Debate Stage:  ${projection.debate_cost:.4f}",
        f"  Judge Stage:   ${projection.judge_cost:.4f}",
        f"  Total Cost:    ${projection.total_cost:.4f}",
        f"  Total Tokens:  {projection.total_tokens_projected:,}",
        "",
        "Cost by Component:",
    ]

    for component, cost in projection.breakdown_by_provider.items():
        if component.endswith("_stage") or component == "overhead":
            lines.append(f"  {component.replace('_', ' ').title()}: ${cost:.4f}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test cost projection
    print("Testing cost projection...")

    # Test quick preset
    quick_projection = project_workflow_cost(
        max_debaters=2, max_tokens=800, fastpath=True, allowed_models=["openai/gpt-4o", "openai/gpt-4o-mini"]
    )

    print("\nQuick Preset Projection:")
    print(format_cost_projection(quick_projection))

    # Test budget checks
    within_budget, warning, error = check_budget_limits(
        quick_projection.total_cost,
        quick_projection.total_tokens_projected,
        budget_usd=0.001,  # Very low budget
        budget_tokens=5000,
    )

    print("\nBudget Check:")
    print(f"  Within Budget: {within_budget}")
    if warning:
        print(f"  Warning: {warning}")
    if error:
        print(f"  Error: {error}")
