"""Pydantic request/response models for the API."""

from pydantic import BaseModel, Field, field_validator, model_validator

# Validation constants (no magic numbers in validation)
MAX_PLAYER_NAME_LENGTH = 50
ALLOWED_PROVIDERS = ("openai", "anthropic", "google", "gemini")


class LLMConfigBody(BaseModel):
    """Optional LLM config when creating a game."""

    provider: str = Field(default="openai", description="openai, anthropic, google, gemini")
    model: str | None = Field(default=None, description="Model name, e.g. gpt-4o-mini")
    api_key: str | None = Field(default=None, description="API key; if omitted, server uses env")

    @field_validator("provider")
    @classmethod
    def provider_allowed(cls, v: str) -> str:
        if v not in ALLOWED_PROVIDERS:
            raise ValueError(f"provider must be one of {ALLOWED_PROVIDERS}")
        return v


class PlayerConfigRequest(BaseModel):
    """Per-player config at game creation: name, optional provider/model, and whether human."""

    name: str = Field(..., min_length=1, max_length=MAX_PLAYER_NAME_LENGTH)
    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    is_human: bool = Field(default=False, description="If true, this slot is a human player")


class HumanActionRequest(BaseModel):
    """Body for POST /games/{id}/action when submitting a human player's action."""

    player_id: str
    action_type: str = Field(..., pattern="^(discussion|vote|night_action)$")
    payload: dict = Field(..., description="For discussion: {statement}. For vote: {target_id, reason}. For night_action: {target_id}.")


class PlayerPublic(BaseModel):
    """Player as shown to clients: role only revealed when dead."""

    id: str
    name: str
    alive: bool
    role: str | None = Field(default=None, description="Only set when not alive (revealed on death)")


class EventPublic(BaseModel):
    kind: str
    round_index: int
    phase: str
    message: str
    player_id: str | None = None
    target_id: str | None = None


class DiscussionMessagePublic(BaseModel):
    player_id: str
    player_name: str
    statement: str
    round_index: int


class MafiaDiscussionMessagePublic(BaseModel):
    """One mafia night discussion message (only in spectate response)."""
    player_id: str
    player_name: str
    statement: str
    round_index: int


class NightReasoningPublic(BaseModel):
    """One night action reasoning (mafia/doctor/sheriff) for spectate."""
    role: str
    player_name: str
    target_name: str
    reason: str


class VotePublic(BaseModel):
    """One vote in the current round (who voted for whom)."""

    voter_id: str
    voter_name: str
    target_id: str
    target_name: str
    reason: str


class GameCreateRequest(BaseModel):
    """Body for POST /games."""

    num_players: int = Field(default=6, ge=4, le=15)
    num_mafia: int = Field(default=1, ge=1, le=4)
    num_doctor: int = Field(default=1, ge=0, le=4, description="Number of doctor roles (town)")
    num_sheriff: int = Field(default=1, ge=0, le=4, description="Number of sheriff roles (town)")
    custom_prompts: dict[str, str] | None = Field(
        default=None,
        description="Optional overlay of prompt texts (rules_summary, discussion_instructions_template, etc.). Omitted keys use server defaults.",
    )
    spectate: bool = Field(
        default=False,
        description="If true, the creator is spectating: no human slot, and game state will show all roles and reasoning/night dialogue.",
    )
    max_discussion_turns: int | None = Field(
        default=None,
        description="Max discussion turns per round (each player gets at least one; AIs can request more up to this cap). Defaults to num_players.",
        ge=1,
        le=100,
    )
    llm_config: LLMConfigBody | None = None
    players: list[PlayerConfigRequest] | None = Field(
        default=None,
        description="Per-player name and provider/model; length must equal num_players if set",
    )

    @model_validator(mode="after")
    def players_length_matches_num_players(self) -> "GameCreateRequest":
        if self.players is not None and len(self.players) != self.num_players:
            raise ValueError(f"players length ({len(self.players)}) must equal num_players ({self.num_players})")
        if self.max_discussion_turns is not None and self.max_discussion_turns < self.num_players:
            raise ValueError(f"max_discussion_turns ({self.max_discussion_turns}) must be >= num_players ({self.num_players})")
        town_size = self.num_players - self.num_mafia
        if self.num_doctor + self.num_sheriff > town_size:
            raise ValueError(
                f"num_doctor ({self.num_doctor}) + num_sheriff ({self.num_sheriff}) must be <= town size ({town_size})"
            )
        return self


class GameStateResponse(BaseModel):
    """Public game state for GET /games/{id}."""

    game_id: str
    players: list[PlayerPublic]
    round_index: int
    phase: str
    events: list[EventPublic]
    discussion: list[DiscussionMessagePublic]
    started: bool
    winner: str | None = Field(default=None, description="mafia or town when game over")
    waiting_for_human: bool = Field(default=False, description="True when current actor is human and must submit via POST /action")
    current_actor_id: str | None = Field(default=None, description="Player id who must act when waiting_for_human")
    pending_human_vote_ids: list[str] = Field(default_factory=list, description="When vote phase, human player ids who have not yet voted")
    pending_human_night_ids: list[str] = Field(default_factory=list, description="When night phase waiting for human actions, player ids who have not yet submitted")
    human_player_ids: list[str] = Field(default_factory=list, description="Player ids that are human (for UI badge)")
    current_round_votes: list[VotePublic] = Field(default_factory=list, description="Votes this round: who each player voted for (and reason)")
    spectate: bool = Field(default=False, description="True when game was created with spectate; roles and reasoning visible.")
    spectator_mafia_discussion: list[MafiaDiscussionMessagePublic] = Field(
        default_factory=list,
        description="Mafia night discussion messages (only when spectate=True).",
    )
    spectator_night_reasoning: list[NightReasoningPublic] = Field(
        default_factory=list,
        description="Night action reasoning (mafia/doctor/sheriff) when spectate=True.",
    )


def game_state_to_public(
    state,
    waiting_for_human: bool = False,
    current_actor_id: str | None = None,
    pending_human_vote_ids: list[str] | None = None,
    pending_human_night_ids: list[str] | None = None,
    human_player_ids: list[str] | None = None,
    pending_votes: list[tuple[str, str, str]] | None = None,
    spectate: bool = False,
) -> GameStateResponse:
    """Build public response from GameState; hide roles of alive players unless spectate."""
    from game.rules import Phase
    players_public = []
    for p in state.players:
        role_str = p.role.value if (spectate or not p.alive) else None
        players_public.append(
            PlayerPublic(id=p.id, name=p.name, alive=p.alive, role=role_str)
        )
    events_public = [
        EventPublic(
            kind=e.kind.value,
            round_index=e.round_index,
            phase=e.phase.value,
            message=e.message,
            player_id=e.player_id,
            target_id=e.target_id,
        )
        for e in state.events
    ]
    discussion_public = [
        DiscussionMessagePublic(
            player_id=m.player_id,
            player_name=m.player_name,
            statement=m.statement,
            round_index=m.round_index,
        )
        for m in state.discussion
    ]
    winner = None
    if state.started:
        from game.engine import is_game_over, get_winner
        if is_game_over(state):
            winner = get_winner(state)

    # Current round votes: during day_vote use pending_votes; otherwise last round's vote_records
    id_to_name = {p.id: p.name for p in state.players}
    current_round_votes_public: list[VotePublic] = []
    if state.phase == Phase.DAY_VOTE and pending_votes:
        for voter_id, target_id, reason in pending_votes:
            target_name = "Abstain" if target_id == "abstain" else id_to_name.get(target_id, target_id)
            current_round_votes_public.append(
                VotePublic(
                    voter_id=voter_id,
                    voter_name=id_to_name.get(voter_id, voter_id),
                    target_id=target_id,
                    target_name=target_name,
                    reason=reason or "",
                )
            )
    else:
        # Show last round's votes (vote_records for previous round)
        round_to_show = state.round_index - 1 if state.phase != Phase.DAY_VOTE else state.round_index
        for v in state.vote_records:
            if v.round_index == round_to_show:
                target_name = "Abstain" if v.target_id == "abstain" else id_to_name.get(v.target_id, v.target_id)
                current_round_votes_public.append(
                    VotePublic(
                        voter_id=v.voter_id,
                        voter_name=id_to_name.get(v.voter_id, v.voter_id),
                        target_id=v.target_id,
                        target_name=target_name,
                        reason=v.reason or "",
                    )
                )

    spectator_mafia_discussion_public: list[MafiaDiscussionMessagePublic] = []
    if spectate and getattr(state, "mafia_discussion", None):
        spectator_mafia_discussion_public = [
            MafiaDiscussionMessagePublic(
                player_id=msg.player_id,
                player_name=msg.player_name,
                statement=msg.statement,
                round_index=msg.round_index,
            )
            for msg in state.mafia_discussion
        ]

    spectator_night_reasoning_public: list[NightReasoningPublic] = []
    if spectate and getattr(state, "night_reasoning", None):
        spectator_night_reasoning_public = [
            NightReasoningPublic(
                role=r.role,
                player_name=r.player_name,
                target_name=r.target_name,
                reason=r.reason or "",
            )
            for r in state.night_reasoning
        ]

    return GameStateResponse(
        game_id=state.game_id,
        players=players_public,
        round_index=state.round_index,
        phase=state.phase.value,
        events=events_public,
        discussion=discussion_public,
        started=state.started,
        winner=winner,
        waiting_for_human=waiting_for_human,
        current_actor_id=current_actor_id,
        pending_human_vote_ids=pending_human_vote_ids or [],
        pending_human_night_ids=pending_human_night_ids or [],
        human_player_ids=human_player_ids or [],
        current_round_votes=current_round_votes_public,
        spectate=spectate,
        spectator_mafia_discussion=spectator_mafia_discussion_public,
        spectator_night_reasoning=spectator_night_reasoning_public,
    )
