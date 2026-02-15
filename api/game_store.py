"""In-memory game store. Replace with DB later if needed."""

from typing import Any
from game.state import GameState

# game_id -> { state, llm_config, player_configs, human_player_ids, pending_night_actions, pending_votes, max_discussion_turns }
_store: dict[str, dict[str, Any]] = {}


def create(
    game_id: str,
    state: GameState,
    llm_config: dict[str, Any] | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    human_player_ids: set[str] | None = None,
    max_discussion_turns: int | None = None,
    custom_prompts: dict[str, str] | None = None,
    spectate: bool = False,
) -> None:
    _store[game_id] = {
        "state": state,
        "llm_config": llm_config or None,
        "player_configs": player_configs or None,
        "human_player_ids": human_player_ids or set(),
        "pending_night_actions": {},
        "pending_night_player_ids": [],
        "pending_votes": [],
        "max_discussion_turns": max_discussion_turns,
        "custom_prompts": custom_prompts or None,
        "spectate": spectate,
    }


def get(game_id: str) -> dict[str, Any] | None:
    return _store.get(game_id)


def update(game_id: str, state: GameState) -> None:
    if game_id in _store:
        _store[game_id]["state"] = state


def get_human_player_ids(game_id: str) -> set[str]:
    """Return set of player ids that are human for this game."""
    entry = _store.get(game_id)
    if not entry:
        return set()
    return entry.get("human_player_ids") or set()


def set_pending_night(game_id: str, actions: dict, pending_player_ids: list[str]) -> None:
    """Store partial night actions and list of human player ids still to submit."""
    if game_id in _store:
        _store[game_id]["pending_night_actions"] = dict(actions)
        _store[game_id]["pending_night_player_ids"] = list(pending_player_ids)


def get_pending_night(game_id: str) -> tuple[dict, list[str]]:
    """Return (actions_dict, pending_player_ids). actions_dict has mafia_target_id, doctor_target_id, sheriff_target_id."""
    entry = _store.get(game_id)
    if not entry:
        return {}, []
    return (
        entry.get("pending_night_actions") or {},
        entry.get("pending_night_player_ids") or [],
    )


def clear_pending_night(game_id: str) -> None:
    if game_id in _store:
        _store[game_id]["pending_night_actions"] = {}
        _store[game_id]["pending_night_player_ids"] = []


def set_pending_votes(game_id: str, votes: list[tuple[str, str, str]]) -> None:
    """Store votes collected so far this round (list of (voter_id, target_id, reason))."""
    if game_id in _store:
        _store[game_id]["pending_votes"] = list(votes)


def get_pending_votes(game_id: str) -> list[tuple[str, str, str]]:
    return _store.get(game_id, {}).get("pending_votes") or []


def clear_pending_votes(game_id: str) -> None:
    if game_id in _store:
        _store[game_id]["pending_votes"] = []


def delete(game_id: str) -> None:
    _store.pop(game_id, None)


def list_games() -> list[str]:
    return list(_store.keys())
