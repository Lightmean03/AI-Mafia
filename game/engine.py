"""Game engine: pure state transitions, no LLM."""

import copy
import math
import random
from typing import Optional

from game.rules import Phase, Role, PHASE_ORDER, NIGHT_ROLES
from game.state import (
    Event,
    EventKind,
    GameState,
    NightActions,
    NightReasoningRecord,
    Player,
    DiscussionMessage,
    MafiaDiscussionMessage,
    VoteRecord,
)


def _next_phase(current: Phase) -> Phase:
    """Return the phase that follows current in the cycle."""
    idx = PHASE_ORDER.index(current)
    return PHASE_ORDER[(idx + 1) % len(PHASE_ORDER)]


def _emit(state: GameState, event: Event) -> None:
    """Append event to state (mutates state)."""
    state.events.append(event)


def start_game(
    game_id: str,
    player_names: list[str],
    role_assignments: list[Role],
    seed: Optional[int] = None,
) -> GameState:
    """
    Create and start a new game. Shuffles discussion order with optional seed.
    """
    if len(player_names) != len(role_assignments):
        raise ValueError("player_names and role_assignments must have same length")

    rng = random.Random(seed)
    players: list[Player] = []
    for i, (name, role) in enumerate(zip(player_names, role_assignments)):
        players.append(
            Player(id=f"player_{i}", name=name, role=role, alive=True)
        )

    # Discussion order for the day phase (shuffle alive players each round, but we init once)
    state = GameState(game_id=game_id, players=players, game_seed=seed, started=True)
    _emit(
        state,
        Event(
            kind=EventKind.GAME_START,
            round_index=0,
            phase=Phase.NIGHT,
            message=f"Game started with {len(players)} players.",
        ),
    )
    return state


def apply_night_actions(
    state: GameState,
    actions: NightActions,
) -> GameState:
    """
    Resolve night: mafia kill (unless protected), doctor protect, sheriff check.
    Returns new state; does not mutate input.
    """
    state = copy.deepcopy(state)
    alive = state.get_alive_players()
    alive_ids = {p.id for p in alive}

    # Validate targets
    if actions.mafia_target_id and actions.mafia_target_id not in alive_ids:
        actions = NightActions(
            mafia_target_id=None,
            doctor_target_id=actions.doctor_target_id,
            sheriff_target_id=actions.sheriff_target_id,
        )
    if actions.doctor_target_id and actions.doctor_target_id not in alive_ids:
        actions = NightActions(
            mafia_target_id=actions.mafia_target_id,
            doctor_target_id=None,
            sheriff_target_id=actions.sheriff_target_id,
        )
    if actions.sheriff_target_id and actions.sheriff_target_id not in alive_ids:
        actions = NightActions(
            mafia_target_id=actions.mafia_target_id,
            doctor_target_id=actions.doctor_target_id,
            sheriff_target_id=None,
        )

    # Resolve kill: mafia kills target unless doctor protected them
    killed_id: Optional[str] = None
    if actions.mafia_target_id:
        protected = actions.doctor_target_id == actions.mafia_target_id
        if not protected:
            killed_id = actions.mafia_target_id
            _emit(
                state,
                Event(
                    kind=EventKind.NIGHT_KILL,
                    round_index=state.round_index,
                    phase=Phase.NIGHT,
                    message=f"Mafia eliminated a player.",
                    target_id=killed_id,
                ),
            )
        else:
            _emit(
                state,
                Event(
                    kind=EventKind.NIGHT_PROTECT,
                    round_index=state.round_index,
                    phase=Phase.NIGHT,
                    message="Doctor protected the mafia target; no one died.",
                ),
            )

    if actions.doctor_target_id and not killed_id:
        _emit(
            state,
            Event(
                kind=EventKind.NIGHT_PROTECT,
                round_index=state.round_index,
                phase=Phase.NIGHT,
                message="Doctor protected a player.",
                target_id=actions.doctor_target_id,
            ),
        )

    if actions.sheriff_target_id:
        target = state.get_player(actions.sheriff_target_id)
        alignment = "mafia" if target and target.role == Role.MAFIA else "town"
        _emit(
            state,
            Event(
                kind=EventKind.NIGHT_CHECK,
                round_index=state.round_index,
                phase=Phase.NIGHT,
                message=f"Sheriff investigated; result is {alignment}.",
                target_id=actions.sheriff_target_id,
                extra={"alignment": alignment},
            ),
        )

    # Apply death
    if killed_id:
        new_players: list[Player] = []
        for p in state.players:
            if p.id == killed_id:
                new_players.append(Player(id=p.id, name=p.name, role=p.role, alive=False))
            else:
                new_players.append(p)
        state.players = new_players

    # Advance to day discussion; fix discussion order for this round
    state.phase = Phase.DAY_DISCUSSION
    alive_after = state.get_alive_players()
    state.discussion_order_index = 0
    order = [p.id for p in alive_after]
    rng = random.Random((state.game_seed or 0) + state.round_index * 1000)
    rng.shuffle(order)
    state.discussion_order = order
    state.events.append(
        Event(
            kind=EventKind.PHASE_CHANGE,
            round_index=state.round_index,
            phase=Phase.DAY_DISCUSSION,
            message=f"Day {state.round_index + 1} – discussion phase.",
        )
    )
    return state


def add_mafia_discussion_message(
    state: GameState,
    player_id: str,
    player_name: str,
    statement: str,
) -> GameState:
    """Append one mafia night discussion message. Returns new state."""
    state = copy.deepcopy(state)
    state.mafia_discussion.append(
        MafiaDiscussionMessage(
            player_id=player_id,
            player_name=player_name,
            statement=statement,
            round_index=state.round_index,
        )
    )
    return state


def add_night_reasoning(
    state: GameState,
    round_index: int,
    role: str,
    player_id: str,
    player_name: str,
    target_id: str,
    target_name: str,
    reason: str,
) -> GameState:
    """Append one night action reasoning record (for spectate). Returns new state."""
    state = copy.deepcopy(state)
    state.night_reasoning.append(
        NightReasoningRecord(
            round_index=round_index,
            role=role,
            player_id=player_id,
            player_name=player_name,
            target_id=target_id,
            target_name=target_name,
            reason=reason or "",
        )
    )
    return state


def add_discussion_message(
    state: GameState,
    player_id: str,
    player_name: str,
    statement: str,
) -> GameState:
    """Append one discussion message and advance speaker. Returns new state."""
    state = copy.deepcopy(state)
    state.discussion.append(
        DiscussionMessage(
            player_id=player_id,
            player_name=player_name,
            statement=statement,
            round_index=state.round_index,
        )
    )
    current_idx = state.discussion_order_index
    state.discussion_order_index = current_idx + 1
    return state


def get_next_speaker(state: GameState) -> Optional[Player]:
    """Return the player who should speak next in discussion, or None if vote phase."""
    if state.phase != Phase.DAY_DISCUSSION:
        return None
    if not state.discussion_order:
        return None
    idx = state.discussion_order_index
    if idx >= len(state.discussion_order):
        return None
    next_id = state.discussion_order[idx]
    return state.get_player(next_id)


def append_discussion_speaker(state: GameState, player_id: str) -> GameState:
    """Append a player to the end of this round's discussion order (e.g. for 'request another turn'). Returns new state."""
    state = copy.deepcopy(state)
    state.discussion_order = list(state.discussion_order) + [player_id]
    return state


def discussion_done(state: GameState, max_discussion_turns: int | None = None) -> bool:
    """True when discussion phase is complete: queue exhausted or turn cap reached."""
    if not state.discussion_order:
        return True
    round_messages = [m for m in state.discussion if m.round_index == state.round_index]
    if max_discussion_turns is not None and len(round_messages) >= max_discussion_turns:
        return True
    return state.discussion_order_index >= len(state.discussion_order)


def apply_vote(
    state: GameState,
    votes: list[tuple[str, str, str]],  # (voter_id, target_id, reason)
) -> GameState:
    """
    Apply day vote: count votes, eliminate majority target (or no one if tie).
    Returns new state.
    """
    state = copy.deepcopy(state)
    alive = state.get_alive_players()
    alive_ids = {p.id for p in alive}

    for voter_id, target_id, reason in votes:
        if voter_id not in alive_ids:
            continue
        # Record vote: either for a valid target (not self) or abstain
        if target_id == "abstain":
            state.vote_records.append(
                VoteRecord(
                    voter_id=voter_id,
                    target_id="abstain",
                    reason=reason,
                    round_index=state.round_index,
                )
            )
        elif target_id in alive_ids and voter_id != target_id:
            state.vote_records.append(
                VoteRecord(
                    voter_id=voter_id,
                    target_id=target_id,
                    reason=reason,
                    round_index=state.round_index,
                )
            )

    # Count votes (abstentions are not counted toward any player)
    from collections import Counter
    round_votes = [v for v in state.vote_records if v.round_index == state.round_index]
    if not round_votes:
        state.phase = Phase.NIGHT
        state.round_index += 1
        state.discussion_order_index = 0
        _emit(
            state,
            Event(
                kind=EventKind.PHASE_CHANGE,
                round_index=state.round_index,
                phase=Phase.NIGHT,
                message="No votes; night falls.",
            ),
        )
        return state

    counts = Counter(v.target_id for v in round_votes if v.target_id != "abstain")
    max_votes = max(counts.values()) if counts else 0
    tied = [tid for tid, c in counts.items() if c == max_votes]
    # Require at least 51% of alive players to vote for someone to eliminate
    threshold = math.ceil(0.51 * len(alive_ids))
    eliminated_id: Optional[str] = None
    if len(tied) == 1 and max_votes >= threshold:
        eliminated_id = tied[0]

    if eliminated_id:
        target = state.get_player(eliminated_id)
        name = target.name if target else eliminated_id
        _emit(
            state,
            Event(
                kind=EventKind.ELIMINATED,
                round_index=state.round_index,
                phase=Phase.DAY_VOTE,
                message=f"{name} was eliminated by vote.",
                player_id=eliminated_id,
                extra={"role": target.role.value if target else None},
            ),
        )
        new_players = []
        for p in state.players:
            if p.id == eliminated_id:
                new_players.append(Player(id=p.id, name=p.name, role=p.role, alive=False))
            else:
                new_players.append(p)
        state.players = new_players

    state.phase = Phase.NIGHT
    state.round_index += 1
    state.discussion_order_index = 0
    _emit(
        state,
        Event(
            kind=EventKind.PHASE_CHANGE,
            round_index=state.round_index,
            phase=Phase.NIGHT,
            message=f"Night {state.round_index + 1}.",
        ),
    )
    return state


def next_phase(state: GameState) -> GameState:
    """Advance to next phase (e.g. after discussion done). Returns new state."""
    state = copy.deepcopy(state)
    state.phase = _next_phase(state.phase)
    if state.phase == Phase.NIGHT:
        state.round_index += 1
    elif state.phase == Phase.DAY_VOTE:
        # Vote order = reverse of discussion order (last speaker votes last)
        state.vote_order = list(reversed(state.discussion_order))
        state.vote_order_index = 0
    return state


def get_next_voter(state: GameState) -> Optional[Player]:
    """Return the player who should vote next, or None if vote phase is done."""
    if state.phase != Phase.DAY_VOTE:
        return None
    if not state.vote_order:
        return None
    idx = state.vote_order_index
    if idx >= len(state.vote_order):
        return None
    next_id = state.vote_order[idx]
    return state.get_player(next_id)


def vote_phase_done(state: GameState) -> bool:
    """True when everyone in vote_order has voted (or no vote order)."""
    if not state.vote_order:
        return True
    return state.vote_order_index >= len(state.vote_order)


def advance_vote_order_index(state: GameState) -> GameState:
    """Increment vote_order_index after one voter has voted. Returns new state."""
    state = copy.deepcopy(state)
    state.vote_order_index = state.vote_order_index + 1
    return state


def is_game_over(state: GameState) -> bool:
    """True if mafia win or town win."""
    alive = state.get_alive_players()
    mafia_alive = sum(1 for p in alive if p.role == Role.MAFIA)
    town_alive = len(alive) - mafia_alive
    return mafia_alive == 0 or mafia_alive >= town_alive


def get_winner(state: GameState) -> Optional[str]:
    """Return 'mafia' or 'town' or None if game not over."""
    if not is_game_over(state):
        return None
    alive = state.get_alive_players()
    mafia_alive = sum(1 for p in alive if p.role == Role.MAFIA)
    return "mafia" if mafia_alive > 0 else "town"
