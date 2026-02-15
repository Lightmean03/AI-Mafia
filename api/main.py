"""FastAPI app: create, start, step, get game."""

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from game.engine import (
    start_game,
    is_game_over,
    add_discussion_message,
    apply_vote,
    apply_night_actions,
    get_next_speaker,
    advance_vote_order_index,
)
from game.state import NightActions
from game.rules import Role, Phase, MIN_PLAYERS
from api.game_store import (
    create as store_create,
    get as store_get,
    update as store_update,
    list_games,
    get_human_player_ids as store_get_human_ids,
    get_pending_night,
    set_pending_night,
    clear_pending_night,
    get_pending_votes,
    set_pending_votes,
    clear_pending_votes,
)
from api.models import (
    GameCreateRequest,
    GameStateResponse,
    game_state_to_public,
    HumanActionRequest,
)
from agents.orchestrator import step_game
from agents.prompts import get_default_prompts

app = FastAPI(title="AI Mafia API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default player names pool
DEFAULT_NAMES = [
    "Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Henry",
    "Ivy", "Jack", "Kate", "Leo", "Mia", "Noah", "Olivia",
]


def _assign_roles(num_players: int, num_mafia: int, num_doctor: int = 1, num_sheriff: int = 1) -> list[Role]:
    roles: list[Role] = []
    roles.extend([Role.MAFIA] * num_mafia)
    roles.extend([Role.DOCTOR] * num_doctor)
    roles.extend([Role.SHERIFF] * num_sheriff)
    town_remaining = num_players - num_mafia - num_doctor - num_sheriff
    roles.extend([Role.VILLAGER] * max(0, town_remaining))
    while len(roles) < num_players:
        roles.append(Role.VILLAGER)
    return roles[:num_players]


def _build_llm_config(provider: str | None, model: str | None, api_key: str | None) -> dict | None:
    """Build llm_config dict; never log or return api_key to client."""
    if provider is None and model is None and api_key is None:
        return None
    return {
        "provider": provider or "openai",
        "model": model,
        "api_key": api_key,
    }


def _response_with_waiting(game_id: str, state) -> GameStateResponse:
    """Build GameStateResponse with waiting_for_human flags from store and state."""
    entry = store_get(game_id)
    spectate = entry.get("spectate", False) if entry else False
    human_ids = store_get_human_ids(game_id)
    _, pending_night_ids = get_pending_night(game_id)
    pending_votes = get_pending_votes(game_id)
    alive = state.get_alive_players()

    human_ids_list = list(human_ids)

    if pending_night_ids:
        return game_state_to_public(
            state,
            waiting_for_human=True,
            current_actor_id=pending_night_ids[0] if pending_night_ids else None,
            pending_human_vote_ids=[],
            pending_human_night_ids=pending_night_ids,
            human_player_ids=human_ids_list,
            pending_votes=pending_votes,
            spectate=spectate,
        )

    if state.phase == Phase.DAY_VOTE and human_ids:
        voted_ids = {v[0] for v in pending_votes}
        pending_human_vote_ids = [p.id for p in alive if p.id in human_ids and p.id not in voted_ids]
        if pending_human_vote_ids:
            return game_state_to_public(
                state,
                waiting_for_human=True,
                current_actor_id=None,
                pending_human_vote_ids=pending_human_vote_ids,
                pending_human_night_ids=[],
                human_player_ids=human_ids_list,
                pending_votes=pending_votes,
                spectate=spectate,
            )

    if state.phase == Phase.DAY_DISCUSSION and human_ids:
        speaker = get_next_speaker(state)
        if speaker and speaker.id in human_ids:
            return game_state_to_public(
                state,
                waiting_for_human=True,
                current_actor_id=speaker.id,
                pending_human_vote_ids=[],
                pending_human_night_ids=[],
                human_player_ids=human_ids_list,
                pending_votes=pending_votes,
                spectate=spectate,
            )

    return game_state_to_public(state, human_player_ids=human_ids_list, pending_votes=pending_votes, spectate=spectate)


@app.post("/games", response_model=dict, tags=["Games"], summary="Create game")
def create_game(body: GameCreateRequest):
    """Create a new game. Returns game_id."""
    if body.num_players < MIN_PLAYERS:
        raise HTTPException(400, f"At least {MIN_PLAYERS} players required")
    if body.num_mafia >= body.num_players:
        raise HTTPException(400, "num_mafia must be less than num_players")
    game_id = str(uuid.uuid4())
    roles = _assign_roles(
        body.num_players,
        body.num_mafia,
        num_doctor=body.num_doctor,
        num_sheriff=body.num_sheriff,
    )

    if body.players is not None:
        names = [p.name for p in body.players]
        player_configs = [
            {
                "name": p.name,
                "llm_config": _build_llm_config(p.provider, p.model, p.api_key)
                or (body.llm_config and _build_llm_config(
                    body.llm_config.provider, body.llm_config.model, body.llm_config.api_key
                )),
            }
            for p in body.players
        ]
        llm_config = None
    else:
        names = DEFAULT_NAMES[: body.num_players]
        single = body.llm_config and _build_llm_config(
            body.llm_config.provider, body.llm_config.model, body.llm_config.api_key
        )
        llm_config = single
        player_configs = [
            {"name": names[i], "llm_config": single}
            for i in range(body.num_players)
        ]

    state = start_game(game_id, names, roles, seed=None)
    human_player_ids = set()
    if body.players is not None:
        for i, p in enumerate(body.players):
            if i < len(state.players) and getattr(p, "is_human", False):
                human_player_ids.add(state.players[i].id)
    max_discussion_turns = body.max_discussion_turns if body.max_discussion_turns is not None else body.num_players
    store_create(
        game_id,
        state,
        llm_config=llm_config,
        player_configs=player_configs,
        human_player_ids=human_player_ids,
        max_discussion_turns=max_discussion_turns,
        custom_prompts=body.custom_prompts,
        spectate=body.spectate,
    )
    return {"game_id": game_id}


@app.get("/games/{game_id}", response_model=GameStateResponse, tags=["Games"], summary="Get game state")
def get_game(game_id: str):
    """Get public game state."""
    entry = store_get(game_id)
    if not entry:
        raise HTTPException(404, "Game not found")
    return _response_with_waiting(game_id, entry["state"])


@app.post("/games/{game_id}/start", response_model=GameStateResponse, tags=["Games"], summary="Start game (no-op)")
def start_game_endpoint(game_id: str):
    """Mark game as started (already started on create). Returns current state."""
    entry = store_get(game_id)
    if not entry:
        raise HTTPException(404, "Game not found")
    return _response_with_waiting(game_id, entry["state"])


@app.post("/games/{game_id}/step", response_model=GameStateResponse, tags=["Games"], summary="Run one step")
def step_game_endpoint(game_id: str):
    """Run one step (night, one discussion turn, or vote). Returns new state or waiting_for_human."""
    entry = store_get(game_id)
    if not entry:
        raise HTTPException(404, "Game not found")
    state = entry["state"]
    if is_game_over(state):
        return game_state_to_public(state, pending_votes=[], spectate=entry.get("spectate", False))
    human_ids = store_get_human_ids(game_id)
    night_actions, pending_night_ids = get_pending_night(game_id)
    pending_votes = get_pending_votes(game_id)

    # Already waiting for human input: return current state with waiting flags
    if pending_night_ids:
        return _response_with_waiting(game_id, state)
    if state.phase == Phase.DAY_VOTE and pending_votes:
        alive = state.get_alive_players()
        voted_ids = {v[0] for v in pending_votes}
        if any(p.id in human_ids and p.id not in voted_ids for p in alive):
            return _response_with_waiting(game_id, state)

    llm_config = entry.get("llm_config")
    player_configs = entry.get("player_configs")
    max_discussion_turns = entry.get("max_discussion_turns")
    custom_prompts = entry.get("custom_prompts")
    new_state, waiting_info = step_game(
        state,
        llm_config=llm_config,
        player_configs=player_configs,
        human_player_ids=human_ids,
        max_discussion_turns=max_discussion_turns,
        custom_prompts=custom_prompts,
        pending_votes=pending_votes if state.phase == Phase.DAY_VOTE else None,
    )
    if waiting_info:
        if "night_actions" in waiting_info:
            set_pending_night(
                game_id,
                waiting_info["night_actions"],
                waiting_info["pending_human_night_ids"],
            )
        if "pending_votes" in waiting_info:
            set_pending_votes(game_id, waiting_info["pending_votes"])
            store_update(game_id, new_state)
            return _response_with_waiting(game_id, new_state)
        return _response_with_waiting(game_id, state)
    clear_pending_night(game_id)
    clear_pending_votes(game_id)
    store_update(game_id, new_state)
    return game_state_to_public(
        new_state,
        human_player_ids=list(store_get_human_ids(game_id)),
        pending_votes=[],
        spectate=entry.get("spectate", False),
    )


# Payload limits for human action (avoid abuse)
MAX_STATEMENT_LENGTH = 500
MAX_VOTE_REASON_LENGTH = 300


@app.post("/games/{game_id}/action", response_model=GameStateResponse, tags=["Games"], summary="Submit human action")
def submit_human_action(game_id: str, body: HumanActionRequest):
    """Submit an action for a human player (discussion statement, vote, or night action)."""
    entry = store_get(game_id)
    if not entry:
        raise HTTPException(404, "Game not found")
    state = entry["state"]
    if is_game_over(state):
        raise HTTPException(400, "Game is over")
    human_ids = store_get_human_ids(game_id)
    if body.player_id not in human_ids:
        raise HTTPException(403, "Player is not a human slot or cannot act for this player")

    alive = state.get_alive_players()
    alive_ids = {p.id for p in alive}

    if body.action_type == "discussion":
        if state.phase != Phase.DAY_DISCUSSION:
            raise HTTPException(400, "Discussion only in day_discussion phase")
        speaker = get_next_speaker(state)
        if not speaker or speaker.id != body.player_id:
            raise HTTPException(400, "Not your turn to speak")
        statement = (body.payload.get("statement") or "").strip()[:MAX_STATEMENT_LENGTH]
        if not statement:
            raise HTTPException(400, "statement is required and non-empty")
        player = state.get_player(body.player_id)
        name = player.name if player else body.player_id
        new_state = add_discussion_message(state, body.player_id, name, statement)
        store_update(game_id, new_state)
        return _response_with_waiting(game_id, new_state)

    if body.action_type == "vote":
        if state.phase != Phase.DAY_VOTE:
            raise HTTPException(400, "Vote only in day_vote phase")
        pending_votes = get_pending_votes(game_id)
        voted_ids = {v[0] for v in pending_votes}
        if body.player_id in voted_ids:
            raise HTTPException(400, "Already voted")
        target_id = body.payload.get("target_id")
        if not target_id:
            raise HTTPException(400, "target_id required (alive player or 'abstain')")
        if target_id != "abstain" and (target_id not in alive_ids or target_id == body.player_id):
            raise HTTPException(400, "Valid target_id required (alive, not self) or 'abstain'")
        reason = (body.payload.get("reason") or "").strip()[:MAX_VOTE_REASON_LENGTH]
        pending_votes = list(pending_votes) + [(body.player_id, target_id, reason)]
        set_pending_votes(game_id, pending_votes)
        state_advanced = advance_vote_order_index(state)
        store_update(game_id, state_advanced)
        voted_ids = {v[0] for v in pending_votes}
        pending_human = [p.id for p in alive if p.id in human_ids and p.id not in voted_ids]
        if not pending_human:
            new_state = apply_vote(state_advanced, pending_votes)
            clear_pending_votes(game_id)
            clear_pending_night(game_id)
            store_update(game_id, new_state)
            return game_state_to_public(
                new_state,
                human_player_ids=list(store_get_human_ids(game_id)),
                pending_votes=[],
                spectate=entry.get("spectate", False),
            )
        return _response_with_waiting(game_id, state_advanced)

    if body.action_type == "night_action":
        if state.phase != Phase.NIGHT:
            raise HTTPException(400, "Night action only in night phase")
        night_actions, pending_night_ids = get_pending_night(game_id)
        if body.player_id not in pending_night_ids:
            raise HTTPException(400, "Not waiting for your night action or already submitted")
        target_id = body.payload.get("target_id")
        if not target_id or target_id not in alive_ids:
            raise HTTPException(400, "Valid target_id required (alive player)")
        player = state.get_player(body.player_id)
        if not player:
            raise HTTPException(400, "Player not found")
        role_to_key = {Role.MAFIA: "mafia_target_id", Role.DOCTOR: "doctor_target_id", Role.SHERIFF: "sheriff_target_id"}
        key = role_to_key.get(player.role)
        if not key:
            raise HTTPException(400, "Your role has no night action")
        night_actions = dict(night_actions)
        night_actions[key] = target_id
        pending_night_ids = [pid for pid in pending_night_ids if pid != body.player_id]
        set_pending_night(game_id, night_actions, pending_night_ids)
        if not pending_night_ids:
            actions = NightActions(
                mafia_target_id=night_actions.get("mafia_target_id"),
                doctor_target_id=night_actions.get("doctor_target_id"),
                sheriff_target_id=night_actions.get("sheriff_target_id"),
            )
            new_state = apply_night_actions(state, actions)
            clear_pending_night(game_id)
            clear_pending_votes(game_id)
            store_update(game_id, new_state)
            return game_state_to_public(
                new_state,
                human_player_ids=list(store_get_human_ids(game_id)),
                pending_votes=[],
                spectate=entry.get("spectate", False),
            )
        return _response_with_waiting(game_id, state)

    raise HTTPException(400, "Invalid action_type")


@app.get("/games", response_model=list[str], tags=["Games"], summary="List game IDs")
def list_games_route():
    """List all game IDs."""
    return list_games()


@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/settings/prompts", response_model=dict, tags=["Settings"], summary="Get default prompts")
def get_prompts():
    """Return default prompt texts used by the game (rules, discussion, vote, night, summarizer)."""
    return get_default_prompts()


@app.get("/settings/env-keys", response_model=dict, tags=["Settings"], summary="Get env API key flags")
def get_env_keys():
    """Return which provider API keys are set in server env (no key values)."""
    import os
    from agents.llm_config import (
        ENV_OPENAI_API_KEY,
        ENV_ANTHROPIC_API_KEY,
        ENV_GOOGLE_API_KEY,
        ENV_XAI_API_KEY,
        ENV_OLLAMA_API_KEY,
    )
    return {
        "openai": bool(os.environ.get(ENV_OPENAI_API_KEY)),
        "anthropic": bool(os.environ.get(ENV_ANTHROPIC_API_KEY)),
        "google": bool(os.environ.get(ENV_GOOGLE_API_KEY)),
        "ollama": True,
        "ollama_cloud": bool(os.environ.get(ENV_OLLAMA_API_KEY)),
        "grok": bool(os.environ.get(ENV_XAI_API_KEY)),
    }
