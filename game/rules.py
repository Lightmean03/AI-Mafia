"""Game rules and constants for AI Mafia."""

from enum import Enum


class Role(str, Enum):
    """Player roles in the game."""

    VILLAGER = "villager"
    DOCTOR = "doctor"
    SHERIFF = "sheriff"
    MAFIA = "mafia"


class Phase(str, Enum):
    """Current game phase."""

    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"


# Order of phases within a round (night -> discussion -> vote -> next round night)
PHASE_ORDER = (Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.DAY_VOTE)

# Roles that act at night (in resolution order: mafia kill, then doctor protect, then sheriff sees result)
NIGHT_ROLES = (Role.MAFIA, Role.DOCTOR, Role.SHERIFF)

# Minimum players to start
MIN_PLAYERS = 4

# Default discussion message window size for context
DISCUSSION_WINDOW_SIZE = 20
