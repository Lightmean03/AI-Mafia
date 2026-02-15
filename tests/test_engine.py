"""Unit tests for the game engine."""

import pytest
from game.engine import (
    start_game,
    apply_night_actions,
    add_discussion_message,
    apply_vote,
    next_phase,
    is_game_over,
    get_winner,
    get_next_speaker,
    get_next_voter,
    vote_phase_done,
    advance_vote_order_index,
    discussion_done,
)
from game.rules import Role, Phase
from game.state import GameState, NightActions


def _make_simple_game(seed: int = 42) -> GameState:
    """5 players: 2 mafia, 1 doctor, 1 sheriff, 1 villager."""
    names = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    roles = [Role.VILLAGER, Role.MAFIA, Role.DOCTOR, Role.SHERIFF, Role.MAFIA]
    return start_game("g1", names, roles, seed=seed)


def test_start_game():
    state = start_game(
        "g1",
        ["A", "B", "C"],
        [Role.VILLAGER, Role.MAFIA, Role.VILLAGER],
        seed=1,
    )
    assert state.game_id == "g1"
    assert len(state.players) == 3
    assert state.started
    assert state.phase == Phase.NIGHT
    assert state.round_index == 0
    assert len(state.events) >= 1
    assert all(p.alive for p in state.players)


def test_start_game_mismatch_raises():
    with pytest.raises(ValueError):
        start_game("g1", ["A", "B"], [Role.MAFIA], seed=1)


def test_apply_night_actions_kill():
    state = _make_simple_game()
    # Mafia kill player_0 (Alice), no protect
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state2 = apply_night_actions(state, actions)
    assert state2.phase == Phase.DAY_DISCUSSION
    dead = [p for p in state2.players if not p.alive]
    assert len(dead) == 1
    assert dead[0].id == "player_0"
    assert len(state2.discussion_order) == 4  # 4 alive


def test_apply_night_actions_doctor_protects():
    state = _make_simple_game()
    # Mafia target player_0, doctor protects player_0
    actions = NightActions(mafia_target_id="player_0", doctor_target_id="player_0", sheriff_target_id=None)
    state2 = apply_night_actions(state, actions)
    assert all(p.alive for p in state2.players)
    assert state2.phase == Phase.DAY_DISCUSSION


def test_discussion_order_deterministic():
    state = _make_simple_game(seed=1)
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state2 = apply_night_actions(state, actions)
    order1 = list(state2.discussion_order)
    state_b = _make_simple_game(seed=1)
    state2_b = apply_night_actions(state_b, actions)
    order2 = list(state2_b.discussion_order)
    assert order1 == order2


def test_get_next_speaker_and_discussion_done():
    state = _make_simple_game()
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    speaker = get_next_speaker(state)
    assert speaker is not None
    assert not discussion_done(state)
    for _ in range(len(state.discussion_order)):
        state = add_discussion_message(state, speaker.id, speaker.name, "I have nothing to add.")
        speaker = get_next_speaker(state)
    assert discussion_done(state)
    assert get_next_speaker(state) is None


def test_apply_vote_eliminates():
    state = _make_simple_game()
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    # 4 alive; need 51% = ceil(2.04) = 3 votes to eliminate. Everyone votes for player_1 (Bob - mafia)
    alive = state.get_alive_players()
    votes = [(p.id, "player_1", "suspicious") for p in alive]
    state = apply_vote(state, votes)
    assert any(p.id == "player_1" and not p.alive for p in state.players)
    assert state.phase == Phase.NIGHT
    assert state.round_index == 1


def test_apply_vote_51_percent_threshold():
    """Elimination requires at least 51% of alive players voting for the same target."""
    state = _make_simple_game()
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    alive = state.get_alive_players()
    n_alive = len(alive)
    # 4 alive: threshold = ceil(0.51 * 4) = 3. Two votes (50%) -> no elimination
    votes_50 = [(alive[0].id, "player_1", "r1"), (alive[1].id, "player_1", "r2")]
    state_no_elim = apply_vote(state, votes_50)
    assert len(state_no_elim.get_alive_players()) == n_alive
    assert state_no_elim.phase == Phase.NIGHT
    # 3 votes (75%) -> player_1 eliminated (three *other* players vote for player_1; no self-vote)
    votes_75 = [(alive[i].id, "player_1", "r") for i in range(1, 4)]
    state_elim = apply_vote(state, votes_75)
    assert any(p.id == "player_1" and not p.alive for p in state_elim.players)


def test_is_game_over_mafia_win():
    state = start_game("g1", ["A", "B", "C"], [Role.VILLAGER, Role.MAFIA, Role.VILLAGER], seed=1)
    # Night 0: mafia kill player_0
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    assert state.phase == Phase.DAY_DISCUSSION
    state = next_phase(state)  # to DAY_VOTE
    state = apply_vote(state, [])  # no votes, advance to night round 1
    # Night 1: mafia kill player_2; only B (mafia) left
    actions2 = NightActions(mafia_target_id="player_2", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions2)
    assert is_game_over(state)
    assert get_winner(state) == "mafia"


def test_is_game_over_town_win():
    # 4 players: A, B (mafia), C, D. Night: mafia kills A. 3 alive; 51% = ceil(1.53)=2. All three vote B -> town wins.
    state = start_game(
        "g1",
        ["A", "B", "C", "D"],
        [Role.VILLAGER, Role.MAFIA, Role.VILLAGER, Role.VILLAGER],
        seed=1,
    )
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    alive = state.get_alive_players()
    # B is player_1; get two others to vote for B (B cannot vote for self, so we need C and D to vote B)
    votes = [(alive[1].id, "player_1", "r"), (alive[2].id, "player_1", "r")]
    state = apply_vote(state, votes)
    assert is_game_over(state)
    assert get_winner(state) == "town"


def test_get_winner_none_when_not_over():
    state = _make_simple_game()
    assert not is_game_over(state)
    assert get_winner(state) is None


def test_vote_order_reverse_of_discussion():
    """When entering DAY_VOTE via next_phase, vote_order is reverse of discussion_order."""
    state = _make_simple_game()
    actions = NightActions(mafia_target_id="player_0", doctor_target_id=None, sheriff_target_id=None)
    state = apply_night_actions(state, actions)
    assert state.phase == Phase.DAY_DISCUSSION
    discussion_order = list(state.discussion_order)
    state = next_phase(state)
    assert state.phase == Phase.DAY_VOTE
    assert state.vote_order == list(reversed(discussion_order))
    assert state.vote_order_index == 0
    assert not vote_phase_done(state)
    next_voter = get_next_voter(state)
    assert next_voter is not None
    assert next_voter.id == state.vote_order[0]
    state_adv = advance_vote_order_index(state)
    assert state_adv.vote_order_index == 1
    if len(state.vote_order) == 1:
        assert vote_phase_done(state_adv)
    else:
        next_voter2 = get_next_voter(state_adv)
        assert next_voter2 is not None
        assert next_voter2.id == state.vote_order[1]
