"""Pydantic schemas for Debate → Judge → Publish workflow."""


from pydantic import BaseModel, Field


class Draft(BaseModel):
    """A draft response from a debater agent."""

    provider: str = Field(..., description="Provider/model that generated this draft")
    answer: str = Field(..., description="The main response text")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence or citations")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score from 0 to 1")
    safety_flags: list[str] = Field(default_factory=list, description="Any safety concerns flagged")


class ScoredDraft(Draft):
    """A draft with judge scoring information."""

    score: float = Field(default=0.0, ge=0.0, le=10.0, description="Judge score from 0 to 10")
    reasons: str = Field(default="", description="Judge's reasoning for the score")
    subscores: dict = Field(default_factory=dict, description="Detailed sub-scores: task_fit, support, clarity")


class Judgment(BaseModel):
    """Judge's final ranking and decision."""

    ranked: list[ScoredDraft] = Field(..., description="Drafts ranked from best to worst")
    winner_provider: str = Field(..., description="Provider of the highest-ranked draft")
