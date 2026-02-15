"""Pydantic AI agents for Mafia game: discussion, vote, night action, summarizer."""

from pydantic_ai import Agent

from agents.models import (
    VoteResponse,
    NightActionResponse,
    DiscussionResponse,
    RoundSummary,
)
from agents.prompts import RULES_SUMMARY


# Agents with structured output; model is passed at run() so we use defer_model_check.
# System prompts are minimal; orchestrator will pass full context in user message.

_discussion_agent = Agent(
    model=None,
    defer_model_check=True,
    output_type=DiscussionResponse,
    system_prompt=[
        RULES_SUMMARY,
        "You are a player in the game. When asked, give one short in-character statement. "
        "You may set request_another_turn to true if you want to speak again this round (e.g. to respond or add more).",
    ],
)

_vote_agent = Agent(
    model=None,
    defer_model_check=True,
    output_type=VoteResponse,
    system_prompt=[RULES_SUMMARY, "You are a player voting to eliminate someone. Reply with player_id and reason only."],
)

_night_action_agent = Agent(
    model=None,
    defer_model_check=True,
    output_type=NightActionResponse,
    system_prompt=[RULES_SUMMARY, "You are performing a night action. Choose one target by player_id."],
)

_summarizer_agent = Agent(
    model=None,
    defer_model_check=True,
    output_type=RoundSummary,
    system_prompt=[RULES_SUMMARY, "You summarize the round neutrally. Do not reveal roles."],
)


def get_discussion_agent() -> Agent[None, DiscussionResponse]:
    return _discussion_agent


def get_vote_agent() -> Agent[None, VoteResponse]:
    return _vote_agent


def get_night_action_agent() -> Agent[None, NightActionResponse]:
    return _night_action_agent


def get_summarizer_agent() -> Agent[None, RoundSummary]:
    return _summarizer_agent
