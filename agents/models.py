"""Pydantic models for structured LLM outputs in AI Mafia."""

from pydantic import BaseModel, Field


class VoteResponse(BaseModel):
    """Structured response for day vote."""

    player_id: str = Field(
        description="ID of the player you vote to eliminate, or 'abstain' to not vote for anyone (you must still give a reason)"
    )
    reason: str = Field(description="Short public reason for your vote (1-2 sentences)")


class NightActionResponse(BaseModel):
    """Structured response for night actions (mafia kill, doctor protect, sheriff check)."""

    target_id: str = Field(description="ID of the player you are targeting")
    private_reason: str | None = Field(
        default=None,
        description="Optional private reasoning (for mafia only, not shown to town)",
    )


class DiscussionResponse(BaseModel):
    """Structured response for day discussion statement."""

    statement: str = Field(
        description="Your short statement to the town (1-3 sentences). Do not reveal your role."
    )
    request_another_turn: bool = Field(
        default=False,
        description="If true, you request to speak again this round (granted only if under the round's turn cap).",
    )


class RoundSummary(BaseModel):
    """Neutral factual summary of a round for context compression."""

    summary: str = Field(
        description="Neutral summary of what happened this round: who died, who was voted out, "
        "key discussion points. Do not reveal any player's secret role."
    )
