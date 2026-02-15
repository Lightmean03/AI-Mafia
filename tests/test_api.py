"""API route tests."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from game.engine import start_game, apply_night_actions
from game.rules import Role, Phase
from game.state import NightActions
from api.game_store import (
    create as store_create,
    get as store_get,
    update as store_update,
    get_human_player_ids,
    set_pending_votes,
)


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_game():
    r = client.post("/games", json={"num_players": 5, "num_mafia": 1})
    assert r.status_code == 200
    data = r.json()
    assert "game_id" in data
    gid = data["game_id"]
    r2 = client.get(f"/games/{gid}")
    assert r2.status_code == 200
    state = r2.json()
    assert state["game_id"] == gid
    assert len(state["players"]) == 5
    assert state["phase"] == "night"
    assert state["started"] is True


def test_create_game_validation():
    r = client.post("/games", json={"num_players": 2})
    assert r.status_code == 422  # too few players
    r = client.post("/games", json={"num_players": 6, "num_mafia": 6})
    assert r.status_code == 422
    r = client.post("/games", json={"num_players": 6, "max_discussion_turns": 3})
    assert r.status_code == 422  # max_discussion_turns must be >= num_players


def test_get_game_404():
    r = client.get("/games/nonexistent-id")
    assert r.status_code == 404


def test_env_keys_returns_booleans_no_values():
    """GET /settings/env-keys returns only booleans and never key values."""
    r = client.get("/settings/env-keys")
    assert r.status_code == 200
    data = r.json()
    assert "openai" in data
    assert "anthropic" in data
    assert "google" in data
    for k, v in data.items():
        assert isinstance(v, bool), f"{k} should be bool, got {type(v)}"
    # Response must not contain any key-like strings (no actual keys)
    raw = r.text
    assert "sk-" not in raw
    assert "api_key" not in raw.lower() or "openai" in data  # key names ok, values not


def test_settings_prompts_returns_defaults():
    """GET /settings/prompts returns default prompt texts."""
    r = client.get("/settings/prompts")
    assert r.status_code == 200
    data = r.json()
    assert "rules_summary" in data
    assert "discussion_instructions_template" in data
    assert "vote_instructions_template" in data
    assert "night_action_instructions_template" in data
    assert "summarizer_instructions" in data
    for v in data.values():
        assert isinstance(v, str)


def test_create_game_num_doctor_num_sheriff():
    """Create game with num_doctor and num_sheriff; role counts are correct."""
    r = client.post(
        "/games",
        json={"num_players": 6, "num_mafia": 1, "num_doctor": 0, "num_sheriff": 1},
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    entry = store_get(gid)
    state = entry["state"]
    roles = [p.role for p in state.players]
    assert roles.count(Role.MAFIA) == 1
    assert roles.count(Role.DOCTOR) == 0
    assert roles.count(Role.SHERIFF) == 1
    assert roles.count(Role.VILLAGER) == 4

    r2 = client.post(
        "/games",
        json={"num_players": 6, "num_mafia": 1, "num_doctor": 2, "num_sheriff": 0},
    )
    assert r2.status_code == 200
    entry2 = store_get(r2.json()["game_id"])
    roles2 = [p.role for p in entry2["state"].players]
    assert roles2.count(Role.DOCTOR) == 2
    assert roles2.count(Role.SHERIFF) == 0


def test_step_game():
    """Step runs without error; we mock orchestrator to avoid LLM calls."""
    def mock_step(state, llm_config=None, player_configs=None, **kwargs):
        from game.engine import apply_night_actions
        from game.state import NightActions
        from game.rules import Phase
        if state.phase == Phase.NIGHT:
            alive = state.get_alive_players()
            target = alive[0].id if alive else None
            new_state = apply_night_actions(
                state, NightActions(mafia_target_id=target, doctor_target_id=None, sheriff_target_id=None)
            )
            return (new_state, None)
        return (state, None)

    with patch("api.main.step_game", side_effect=mock_step):
        r = client.post("/games", json={"num_players": 4, "num_mafia": 1})
        assert r.status_code == 200
        gid = r.json()["game_id"]
        r = client.post(f"/games/{gid}/step")
        assert r.status_code == 200
        data = r.json()
        assert data["game_id"] == gid
        assert data["phase"] in ("night", "day_discussion")


def test_create_game_with_per_player_config():
    """Create game with players list (names and optional is_human)."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "players": [
                {"name": "Alice", "is_human": False},
                {"name": "Bob", "is_human": True},
                {"name": "Carol", "is_human": False},
                {"name": "Dave", "is_human": False},
            ],
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    entry = store_get(gid)
    assert entry is not None
    human_ids = get_human_player_ids(gid)
    assert len(human_ids) == 1
    # Bob is player_1
    assert "player_1" in human_ids
    r2 = client.get(f"/games/{gid}")
    assert r2.status_code == 200
    state = r2.json()
    assert state["human_player_ids"] == ["player_1"]
    assert [p["name"] for p in state["players"]] == ["Alice", "Bob", "Carol", "Dave"]


def test_action_discussion_wrong_phase():
    """POST /action with action_type discussion in night phase returns 400."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "players": [
                {"name": "A", "is_human": True},
                {"name": "B", "is_human": False},
                {"name": "C", "is_human": False},
                {"name": "D", "is_human": False},
            ],
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    r = client.post(
        f"/games/{gid}/action",
        json={"player_id": "player_0", "action_type": "discussion", "payload": {"statement": "Hello"}},
    )
    assert r.status_code == 400  # night phase, not discussion


def test_action_discussion_success():
    """POST /action with valid discussion statement advances and returns state."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "players": [
                {"name": "A", "is_human": True},
                {"name": "B", "is_human": False},
                {"name": "C", "is_human": False},
                {"name": "D", "is_human": False},
            ],
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    # Move to day_discussion with player_0 as first speaker (human)
    entry = store_get(gid)
    state = entry["state"]
    from game.engine import next_phase
    state = next_phase(state)
    assert state.phase == Phase.DAY_DISCUSSION
    state.discussion_order = [p.id for p in state.get_alive_players()]
    state.discussion_order_index = 0
    state.phase = Phase.DAY_DISCUSSION
    store_update(gid, state)
    r = client.post(
        f"/games/{gid}/action",
        json={"player_id": "player_0", "action_type": "discussion", "payload": {"statement": "I am town."}},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["discussion"]) >= 1
    assert data["discussion"][-1]["statement"] == "I am town."
    assert data["discussion"][-1]["player_id"] == "player_0"


def test_action_wrong_player():
    """POST /action with non-human player_id returns 403."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "players": [
                {"name": "A", "is_human": False},
                {"name": "B", "is_human": True},
                {"name": "C", "is_human": False},
                {"name": "D", "is_human": False},
            ],
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    entry = store_get(gid)
    state = entry["state"]
    from game.engine import next_phase
    state = next_phase(state)
    state.discussion_order = [p.id for p in state.get_alive_players()]
    state.discussion_order_index = 0
    state.phase = Phase.DAY_DISCUSSION
    store_update(gid, state)
    r = client.post(
        f"/games/{gid}/action",
        json={"player_id": "player_0", "action_type": "discussion", "payload": {"statement": "Hi"}},
    )
    assert r.status_code == 403  # player_0 is not human


def test_action_vote_success():
    """POST /action with vote in day_vote phase when human has not voted: accept and advance or return state."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "players": [
                {"name": "A", "is_human": True},
                {"name": "B", "is_human": False},
                {"name": "C", "is_human": False},
                {"name": "D", "is_human": False},
            ],
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    entry = store_get(gid)
    state = entry["state"]
    from game.engine import next_phase
    # Night -> day_discussion -> day_vote; set discussion_order so vote_order is set correctly
    state = next_phase(state)
    state.discussion_order = [p.id for p in state.get_alive_players()]
    state = next_phase(state)
    assert state.phase == Phase.DAY_VOTE
    assert len(state.vote_order) == 4
    store_update(gid, state)
    set_pending_votes(gid, [])
    r = client.post(
        f"/games/{gid}/action",
        json={
            "player_id": "player_0",
            "action_type": "vote",
            "payload": {"target_id": "player_1", "reason": "Suspicious."},
        },
    )
    assert r.status_code == 200
    data = r.json()
    # After human vote, only one voter so no majority; phase should advance to night.
    assert data["phase"] == "night"
    assert len(data.get("current_round_votes", [])) >= 1


def test_create_game_with_custom_prompts():
    """Create game with custom_prompts is accepted and stored."""
    r = client.post(
        "/games",
        json={
            "num_players": 4,
            "num_mafia": 1,
            "custom_prompts": {"rules_summary": "Custom rules here."},
        },
    )
    assert r.status_code == 200
    gid = r.json()["game_id"]
    entry = store_get(gid)
    assert entry.get("custom_prompts") is not None
    assert entry["custom_prompts"].get("rules_summary") == "Custom rules here."
