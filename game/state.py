"""Game state types for AI Mafia."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from game.rules import Phase, Role


@dataclass(frozen=True)
class Player:
    """A player in the game."""

    id: str
    name: str
    role: Role
    alive: bool = True


class EventKind(str, Enum):
    """Type of game event."""

    NIGHT_KILL = "night_kill"
    NIGHT_PROTECT = "night_protect"
    NIGHT_CHECK = "night_check"
    DISCUSSION = "discussion"
    VOTE = "vote"
    ELIMINATED = "eliminated"
    GAME_START = "game_start"
    PHASE_CHANGE = "phase_change"


@dataclass
class Event:
    """A single game event for history."""

    kind: EventKind
    round_index: int
    phase: Phase
    message: str
    player_id: Optional[str] = None
    target_id: Optional[str] = None
    extra: Optional[dict] = None


@dataclass
class DiscussionMessage:
    """One player's statement during day discussion."""

    player_id: str
    player_name: str
    statement: str
    round_index: int


@dataclass
class VoteRecord:
    """One player's vote during day vote."""

    voter_id: str
    target_id: str
    reason: str
    round_index: int


@dataclass
class MafiaDiscussionMessage:
    """One mafia player's message during night discussion (private to mafia)."""

    player_id: str
    player_name: str
    statement: str
    round_index: int


@dataclass
class NightReasoningRecord:
    """One night action's reasoning (mafia kill, doctor protect, sheriff investigate) for spectate."""

    round_index: int
    role: str
    player_id: str
    player_name: str
    target_id: str
    target_name: str
    reason: str


@dataclass
class NightActions:
    """Collected night actions for one round (before resolution)."""

    mafia_target_id: Optional[str] = None
    doctor_target_id: Optional[str] = None
    sheriff_target_id: Optional[str] = None


@dataclass
class GameState:
    """Full game state."""

    game_id: str
    players: list[Player] = field(default_factory=list)
    round_index: int = 0
    phase: Phase = Phase.NIGHT
    events: list[Event] = field(default_factory=list)
    discussion: list[DiscussionMessage] = field(default_factory=list)
    vote_records: list[VoteRecord] = field(default_factory=list)
    round_summaries: list[str] = field(default_factory=list)
    discussion_order_index: int = 0  # whose turn to speak in day_discussion
    discussion_order: list[str] = field(default_factory=list)  # order of speaker ids this round
    vote_order: list[str] = field(default_factory=list)  # order of voters this round (reverse of discussion)
    vote_order_index: int = 0  # next voter index in vote_order
    mafia_discussion: list[MafiaDiscussionMessage] = field(default_factory=list)  # night discussion between mafia (round_index per message)
    night_reasoning: list[NightReasoningRecord] = field(default_factory=list)  # night action reasoning for spectate
    game_seed: Optional[int] = None
    started: bool = False

    def get_alive_players(self) -> list[Player]:
        """Return list of alive players."""
        return [p for p in self.players if p.alive]

    def get_player(self, player_id: str) -> Optional[Player]:
        """Return player by id or None."""
        for p in self.players:
            if p.id == player_id:
                return p
        return None

    def get_players_by_role(self, role: Role) -> list[Player]:
        """Return alive players with the given role."""
        return [p for p in self.players if p.alive and p.role == role]
