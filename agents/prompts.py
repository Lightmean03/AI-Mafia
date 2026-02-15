"""Prompt and context building for AI Mafia agents."""

from game.state import GameState
from game.rules import DISCUSSION_WINDOW_SIZE


RULES_SUMMARY = """
You are playing Mafia (Werewolf). There are two sides: Town (villagers, doctor, sheriff) and Mafia.
- At night: Mafia choose one player to eliminate. Doctor chooses one player to protect (saves from mafia kill). Sheriff checks one player and learns if they are mafia or town.
- By day: Everyone discusses, then votes to eliminate one player. Majority wins; ties mean no elimination.
- Town wins when all Mafia are dead. Mafia win when they outnumber or equal Town.
- You must never reveal your secret role in your public statements unless you are eliminated.
"""

DISCUSSION_INSTRUCTIONS_TEMPLATE = (
    "You are {player_name}, a {role_name}. "
    "Give one short statement (1-3 sentences) to the town. "
    "Do not reveal your role. Try to help your side win."
)
VOTE_INSTRUCTIONS_TEMPLATE = (
    "You are a {role_name}. You must cast a vote. "
    "Valid choices: {targets} (or 'abstain' to not vote for anyone). "
    "Provide the player_id you vote for (or 'abstain') and a short public reason (1-2 sentences)."
)
NIGHT_ACTION_INSTRUCTIONS_TEMPLATE = (
    "You are {role_name}. Choose exactly one target from the following player IDs: {targets}. "
    "Reply with the target's player_id only. You may add optional private_reason (for mafia)."
)
SUMMARIZER_INSTRUCTIONS = (
    "Summarize this round in 2-4 neutral sentences: who died (if anyone), who was voted out (if anyone), "
    "and the main discussion points. Do not reveal any player's secret role. "
    "Write in past tense, factual only."
)


def get_default_prompts() -> dict[str, str]:
    """Return default prompt texts for GET /settings/prompts. Keys match custom_prompts overlay."""
    return {
        "rules_summary": RULES_SUMMARY.strip(),
        "discussion_instructions_template": DISCUSSION_INSTRUCTIONS_TEMPLATE,
        "vote_instructions_template": VOTE_INSTRUCTIONS_TEMPLATE,
        "night_action_instructions_template": NIGHT_ACTION_INSTRUCTIONS_TEMPLATE,
        "summarizer_instructions": SUMMARIZER_INSTRUCTIONS,
    }


def build_game_context(state: GameState, include_secret_role: bool = False) -> str:
    """Build user-message context: round, phase, alive players, recent events and discussion."""
    lines = [
        f"Round {state.round_index + 1}. Phase: {state.phase.value}.",
        f"Alive players: {', '.join(p.name + ' (' + p.id + ')' for p in state.get_alive_players())}.",
    ]
    if state.round_summaries:
        lines.append("Previous rounds summary:")
        for i, s in enumerate(state.round_summaries[-3:], start=max(1, len(state.round_summaries) - 2)):
            lines.append(f"  Round {i}: {s}")
    recent_events = state.events[-15:]
    if recent_events:
        lines.append("Recent events:")
        for e in recent_events:
            lines.append(f"  - {e.message}")
    round_discussion = [m for m in state.discussion if m.round_index == state.round_index]
    window = round_discussion[-DISCUSSION_WINDOW_SIZE:]
    if window:
        lines.append("Discussion this round:")
        for m in window:
            lines.append(f"  {m.player_name}: {m.statement}")
    if include_secret_role:
        # Only for mafia private discussion; we don't put full role list here
        pass
    return "\n".join(lines)


def night_action_instructions(
    role_name: str,
    valid_target_ids: list[str],
    template: str | None = None,
) -> str:
    """Instructions for night phase: pick one valid target."""
    targets = ", ".join(valid_target_ids)
    t = template or NIGHT_ACTION_INSTRUCTIONS_TEMPLATE
    return t.format(role_name=role_name, targets=targets)


def discussion_instructions(
    player_name: str,
    role_name: str,
    template: str | None = None,
) -> str:
    """Instructions for day discussion: one short statement."""
    t = template or DISCUSSION_INSTRUCTIONS_TEMPLATE
    return t.format(player_name=player_name, role_name=role_name)


def vote_instructions(
    role_name: str,
    valid_target_ids: list[str],
    template: str | None = None,
) -> str:
    """Instructions for day vote: pick one to eliminate and give public reason."""
    targets = ", ".join(valid_target_ids)
    t = template or VOTE_INSTRUCTIONS_TEMPLATE
    return t.format(role_name=role_name, targets=targets)


def summarizer_instructions(override: str | None = None) -> str:
    """Instructions for round summarizer: neutral, no role reveals."""
    return override if override is not None else SUMMARIZER_INSTRUCTIONS
