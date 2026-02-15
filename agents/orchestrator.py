"""Orchestrator: run game phases using game engine and Pydantic AI agents."""

import dataclasses
import logging
import random
from typing import Any

from game.engine import (
    apply_night_actions,
    add_discussion_message,
    add_mafia_discussion_message,
    add_night_reasoning,
    append_discussion_speaker,
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
from game.state import GameState, NightActions
from game.rules import Role, Phase

from agents.llm_config import get_model_from_config
from agents.mafia_agent import (
    get_discussion_agent,
    get_vote_agent,
    get_night_action_agent,
    get_summarizer_agent,
)
from agents.prompts import (
    build_game_context,
    night_action_instructions,
    discussion_instructions,
    vote_instructions,
    summarizer_instructions,
)

logger = logging.getLogger(__name__)

# Type for llm_config: provider, model, optional api_key
LLMConfig = dict[str, Any]


def _player_id_to_index(player_id: str) -> int | None:
    """Extract player index from player_id (e.g. player_0 -> 0)."""
    if player_id.startswith("player_"):
        try:
            return int(player_id.split("_", 1)[1])
        except ValueError:
            pass
    return None


def _get_llm_config_for_player(
    player_id: str,
    player_configs: list[dict[str, Any]] | None,
    fallback_llm_config: LLMConfig | None,
) -> LLMConfig | None:
    """Resolve llm_config for a player: use player_configs[index] or fallback. Never returns config with api_key for logging."""
    if player_configs:
        idx = _player_id_to_index(player_id)
        if idx is not None and 0 <= idx < len(player_configs):
            return player_configs[idx].get("llm_config") or fallback_llm_config
    return fallback_llm_config


CustomPrompts = dict[str, str] | None


def _context_with_rules(state: GameState, custom_prompts: CustomPrompts) -> str:
    """Build game context; if custom_prompts has rules_summary, prepend it."""
    ctx = build_game_context(state)
    if custom_prompts and "rules_summary" in custom_prompts:
        ctx = custom_prompts["rules_summary"].strip() + "\n\n" + ctx
    return ctx


def _get_model(llm_config: LLMConfig | None) -> Any:
    if not llm_config:
        from agents.llm_config import ENV_DEFAULT_PROVIDER, ENV_DEFAULT_MODEL
        import os
        provider = os.environ.get(ENV_DEFAULT_PROVIDER, "openai")
        model_name = os.environ.get(ENV_DEFAULT_MODEL)
        return get_model_from_config(provider, model_name or "", api_key=None)
    return get_model_from_config(
        llm_config.get("provider", "openai"),
        llm_config.get("model", ""),
        llm_config.get("api_key"),
    )


def run_night(
    state: GameState,
    llm_config: LLMConfig | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    human_player_ids: set[str] | None = None,
    custom_prompts: CustomPrompts = None,
) -> tuple[GameState, dict[str, str | None], list[str]]:
    """
    Run night phase: collect mafia kill, doctor protect, sheriff check.
    Returns (new_state_or_unchanged, actions_dict, pending_human_night_ids).
    If any night role is human, state is unchanged, actions_dict has None for that role, and pending_human_night_ids lists them.
    When all AI, returns (new_state_after_apply, {}, []).
    """
    human = human_player_ids or set()
    alive = state.get_alive_players()
    alive_ids = [p.id for p in alive]

    mafia_players = state.get_players_by_role(Role.MAFIA)
    doctor_players = state.get_players_by_role(Role.DOCTOR)
    sheriff_players = state.get_players_by_role(Role.SHERIFF)

    mafia_target_id: str | None = None
    doctor_target_id: str | None = None
    sheriff_target_id: str | None = None
    pending_human: list[str] = []

    # When multiple mafia and all AI: run one round of mafia discussion, then first mafia chooses target
    state_after_mafia_discussion = state
    if len(mafia_players) > 1 and not any(m.id in human for m in mafia_players):
        for m in mafia_players:
            cfg = _get_llm_config_for_player(m.id, player_configs, llm_config)
            model = _get_model(cfg)
            ctx = _context_with_rules(state_after_mafia_discussion, custom_prompts)
            round_mafia_msgs = [msg for msg in state_after_mafia_discussion.mafia_discussion if msg.round_index == state_after_mafia_discussion.round_index]
            if round_mafia_msgs:
                ctx += "\n\nMafia discussion so far this night:\n" + "\n".join(f"  {msg.player_name}: {msg.statement}" for msg in round_mafia_msgs)
            inst = (
                "You are mafia. You are discussing with your mafia partners (they will see this) who to eliminate tonight. "
                "Give one short message (1-2 sentences) with your suggestion or opinion. Do not reveal your role to the rest of the game."
            )
            try:
                result = get_discussion_agent().run_sync(f"{ctx}\n\n{inst}", model=model)
                stmt = (result.output.statement if result.output else "").strip() or "I have no strong opinion."
                state_after_mafia_discussion = add_mafia_discussion_message(state_after_mafia_discussion, m.id, m.name, stmt)
            except Exception as e:
                logger.warning("Mafia discussion message failed for %s: %s", m.id, e)
                state_after_mafia_discussion = add_mafia_discussion_message(
                    state_after_mafia_discussion, m.id, m.name, "I defer to the group."
                )
        state = state_after_mafia_discussion

    if mafia_players:
        first_mafia = mafia_players[0]
        mafia_result = None
        if first_mafia.id in human:
            pending_human.append(first_mafia.id)
        else:
            cfg = _get_llm_config_for_player(first_mafia.id, player_configs, llm_config)
            model = _get_model(cfg)
            targets = [pid for pid in alive_ids if pid != first_mafia.id]
            if not targets:
                targets = alive_ids
            ctx = _context_with_rules(state, custom_prompts)
            round_mafia_msgs = [msg for msg in state.mafia_discussion if msg.round_index == state.round_index]
            if round_mafia_msgs:
                ctx += "\n\nMafia discussion this night:\n" + "\n".join(f"  {msg.player_name}: {msg.statement}" for msg in round_mafia_msgs)
            inst = night_action_instructions(
                "Mafia (choose who to eliminate)",
                targets,
                template=custom_prompts.get("night_action_instructions_template") if custom_prompts else None,
            )
            try:
                mafia_result = get_night_action_agent().run_sync(
                    f"{ctx}\n\n{inst}",
                    model=model,
                )
                if mafia_result.output and mafia_result.output.target_id in alive_ids:
                    mafia_target_id = mafia_result.output.target_id
            except Exception as e:
                logger.warning("Mafia night action failed: %s; picking random target", e)
                if targets:
                    mafia_target_id = random.choice(targets)
            # Single mafia: add one mafia_discussion message so spectate has content
            if len(mafia_players) == 1:
                target_name = (state.get_player(mafia_target_id).name if (mafia_target_id and state.get_player(mafia_target_id)) else mafia_target_id) if mafia_target_id else "someone"
                stmt = (mafia_result.output.private_reason if mafia_result and mafia_result.output and getattr(mafia_result.output, "private_reason", None) else None) or f"Eliminating {target_name}."
                state = add_mafia_discussion_message(state, first_mafia.id, first_mafia.name, stmt)
            # Night reasoning for spectate (mafia decision)
            if mafia_target_id and first_mafia.id not in human:
                target_name = state.get_player(mafia_target_id).name if state.get_player(mafia_target_id) else mafia_target_id
                reason = (mafia_result.output.private_reason if mafia_result and mafia_result.output and getattr(mafia_result.output, "private_reason", None) else None) or ""
                state = add_night_reasoning(state, state.round_index, "Mafia", first_mafia.id, first_mafia.name, mafia_target_id, target_name, reason)

    if doctor_players:
        doc = doctor_players[0]
        doc_result = None
        if doc.id in human:
            pending_human.append(doc.id)
        else:
            cfg = _get_llm_config_for_player(doc.id, player_configs, llm_config)
            model = _get_model(cfg)
            targets = [pid for pid in alive_ids if pid != doc.id]
            if not targets:
                targets = alive_ids
            ctx = _context_with_rules(state, custom_prompts)
            inst = night_action_instructions(
                "Doctor (choose who to protect)",
                targets,
                template=custom_prompts.get("night_action_instructions_template") if custom_prompts else None,
            )
            try:
                doc_result = get_night_action_agent().run_sync(
                    f"{ctx}\n\n{inst}",
                    model=model,
                )
                if doc_result.output and doc_result.output.target_id in alive_ids:
                    doctor_target_id = doc_result.output.target_id
            except Exception as e:
                logger.warning("Doctor night action failed: %s", e)
                if targets:
                    doctor_target_id = random.choice(targets)
            if doctor_target_id and doc.id not in human:
                target_name = state.get_player(doctor_target_id).name if state.get_player(doctor_target_id) else doctor_target_id
                reason = (doc_result.output.private_reason if doc_result and doc_result.output and getattr(doc_result.output, "private_reason", None) else None) or ""
                state = add_night_reasoning(state, state.round_index, "Doctor", doc.id, doc.name, doctor_target_id, target_name, reason)

    if sheriff_players:
        sher = sheriff_players[0]
        sher_result = None
        if sher.id in human:
            pending_human.append(sher.id)
        else:
            cfg = _get_llm_config_for_player(sher.id, player_configs, llm_config)
            model = _get_model(cfg)
            targets = [pid for pid in alive_ids if pid != sher.id]
            if targets:
                ctx = _context_with_rules(state, custom_prompts)
                inst = night_action_instructions(
                    "Sheriff (choose who to investigate)",
                    targets,
                    template=custom_prompts.get("night_action_instructions_template") if custom_prompts else None,
                )
                try:
                    sher_result = get_night_action_agent().run_sync(
                        f"{ctx}\n\n{inst}",
                        model=model,
                    )
                    if sher_result.output and sher_result.output.target_id in alive_ids:
                        sheriff_target_id = sher_result.output.target_id
                except Exception as e:
                    logger.warning("Sheriff night action failed: %s", e)
                    sheriff_target_id = random.choice(targets)
            if sheriff_target_id and sher.id not in human:
                target_name = state.get_player(sheriff_target_id).name if state.get_player(sheriff_target_id) else sheriff_target_id
                reason = (sher_result.output.private_reason if sher_result and sher_result.output and getattr(sher_result.output, "private_reason", None) else None) or ""
                state = add_night_reasoning(state, state.round_index, "Sheriff", sher.id, sher.name, sheriff_target_id, target_name, reason)

    if pending_human:
        actions_dict = {
            "mafia_target_id": mafia_target_id,
            "doctor_target_id": doctor_target_id,
            "sheriff_target_id": sheriff_target_id,
        }
        return (state, actions_dict, pending_human)

    actions = NightActions(
        mafia_target_id=mafia_target_id,
        doctor_target_id=doctor_target_id,
        sheriff_target_id=sheriff_target_id,
    )
    return (apply_night_actions(state, actions), {}, [])


def run_discussion_turn(
    state: GameState,
    llm_config: LLMConfig | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    human_player_ids: set[str] | None = None,
    max_discussion_turns: int | None = None,
    custom_prompts: CustomPrompts = None,
) -> tuple[GameState, str | None]:
    """Run one discussion turn. Returns (new_state, None) or (state, speaker_id) when speaker is human."""
    speaker = get_next_speaker(state)
    if not speaker:
        return (state, None)
    human = human_player_ids or set()
    if speaker.id in human:
        return (state, speaker.id)
    cfg = _get_llm_config_for_player(speaker.id, player_configs, llm_config)
    model = _get_model(cfg)
    ctx = _context_with_rules(state, custom_prompts)
    inst = discussion_instructions(
        speaker.name,
        speaker.role.value,
        template=custom_prompts.get("discussion_instructions_template") if custom_prompts else None,
    )
    request_another = False
    try:
        result = get_discussion_agent().run_sync(
            f"{ctx}\n\n{inst}",
            model=model,
        )
        if result.output:
            statement = result.output.statement or "I have nothing to add."
            request_another = getattr(result.output, "request_another_turn", False)
        else:
            statement = "I have nothing to add."
    except Exception as e:
        logger.warning("Discussion turn failed for %s: %s", speaker.id, e)
        statement = "I have nothing to add."
    new_state = add_discussion_message(state, speaker.id, speaker.name, statement)
    if request_another and max_discussion_turns is not None:
        round_messages = [m for m in new_state.discussion if m.round_index == new_state.round_index]
        if len(round_messages) < max_discussion_turns:
            new_state = append_discussion_speaker(new_state, speaker.id)
    return (new_state, None)


def run_vote_turn(
    state: GameState,
    votes_so_far: list[tuple[str, str, str]],
    llm_config: LLMConfig | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    human_player_ids: set[str] | None = None,
    custom_prompts: CustomPrompts = None,
) -> tuple[GameState, list[tuple[str, str, str]], list[str]]:
    """
    One voter per step. Returns (new_state, votes_so_far, pending_human_vote_ids).
    When all have voted, applies vote and returns (new_state, [], []).
    """
    human = human_player_ids or set()
    alive = state.get_alive_players()
    alive_ids = [p.id for p in alive]

    if vote_phase_done(state):
        return (apply_vote(state, votes_so_far), [], [])

    next_voter = get_next_voter(state)
    if not next_voter:
        return (apply_vote(state, votes_so_far), [], [])

    if next_voter.id in human:
        return (state, votes_so_far, [next_voter.id])

    # AI voter
    cfg = _get_llm_config_for_player(next_voter.id, player_configs, llm_config)
    model = _get_model(cfg)
    ctx = _context_with_rules(state, custom_prompts)
    valid_targets = [pid for pid in alive_ids if pid != next_voter.id] + ["abstain"]
    inst = vote_instructions(
        next_voter.role.value,
        valid_targets,
        template=custom_prompts.get("vote_instructions_template") if custom_prompts else None,
    )
    try:
        result = get_vote_agent().run_sync(
            f"{ctx}\n\n{inst}",
            model=model,
        )
        if result.output:
            pid = result.output.player_id
            reason = result.output.reason or ""
            if pid == "abstain":
                votes_new = votes_so_far + [(next_voter.id, "abstain", reason or "Abstain")]
            elif pid != next_voter.id and pid in alive_ids:
                votes_new = votes_so_far + [(next_voter.id, pid, reason)]
            else:
                votes_new = votes_so_far + [(next_voter.id, "abstain", reason or "Abstain")]
        else:
            votes_new = votes_so_far + [(next_voter.id, "abstain", "Abstain")]
    except Exception as e:
        logger.warning("Vote failed for %s: %s", next_voter.id, e)
        votes_new = votes_so_far + [(next_voter.id, "abstain", "Abstain")]

    state_advanced = advance_vote_order_index(state)
    if vote_phase_done(state_advanced):
        return (apply_vote(state_advanced, votes_new), [], [])
    return (state_advanced, votes_new, [])


def run_round_summary(
    state: GameState,
    llm_config: LLMConfig | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    custom_prompts: CustomPrompts = None,
) -> GameState:
    """Produce a neutral summary of the current round and append to state.round_summaries."""
    fallback = llm_config
    if player_configs and state.players:
        first_id = state.players[0].id
        fallback = _get_llm_config_for_player(first_id, player_configs, llm_config) or fallback
    model = _get_model(fallback)
    ctx = _context_with_rules(state, custom_prompts)
    inst = summarizer_instructions(
        override=custom_prompts.get("summarizer_instructions") if custom_prompts else None
    )
    try:
        result = get_summarizer_agent().run_sync(
            f"{ctx}\n\n{inst}",
            model=model,
        )
        summary = result.output.summary if result.output else "Round concluded."
    except Exception as e:
        logger.warning("Summarizer failed: %s", e)
        summary = "Round concluded."
    return dataclasses.replace(
        state,
        round_summaries=state.round_summaries + [summary],
    )


def step_game(
    state: GameState,
    llm_config: LLMConfig | None = None,
    player_configs: list[dict[str, Any]] | None = None,
    human_player_ids: set[str] | None = None,
    max_discussion_turns: int | None = None,
    custom_prompts: CustomPrompts = None,
    pending_votes: list[tuple[str, str, str]] | None = None,
) -> tuple[GameState, dict[str, Any] | None]:
    """
    Run one logical step. Returns (new_state, waiting_info).
    waiting_info is None when step advanced; else dict with waiting_for_human, current_actor_id, pending_human_night_ids, pending_human_vote_ids, and optional night_actions for storage.
    """
    human = human_player_ids or set()
    if is_game_over(state):
        return (state, None)
    if state.phase == Phase.NIGHT:
        new_state, actions_dict, pending_night_ids = run_night(
            state, llm_config, player_configs, human, custom_prompts=custom_prompts
        )
        if pending_night_ids:
            return (state, {
                "waiting_for_human": True,
                "current_actor_id": pending_night_ids[0] if pending_night_ids else None,
                "pending_human_night_ids": pending_night_ids,
                "pending_human_vote_ids": [],
                "night_actions": actions_dict,
            })
        return (new_state, None)
    if state.phase == Phase.DAY_DISCUSSION:
        if discussion_done(state, max_discussion_turns):
            state = next_phase(state)
            new_state, votes, pending_vote_ids = run_vote_turn(
                state, [], llm_config, player_configs, human, custom_prompts=custom_prompts
            )
            if pending_vote_ids:
                return (state, {
                    "waiting_for_human": True,
                    "current_actor_id": None,
                    "pending_human_night_ids": [],
                    "pending_human_vote_ids": pending_vote_ids,
                    "pending_votes": votes,
                })
            return (new_state, None)
        new_state, waiting_speaker = run_discussion_turn(
            state,
            llm_config,
            player_configs,
            human,
            max_discussion_turns=max_discussion_turns,
            custom_prompts=custom_prompts,
        )
        if waiting_speaker:
            return (state, {
                "waiting_for_human": True,
                "current_actor_id": waiting_speaker,
                "pending_human_night_ids": [],
                "pending_human_vote_ids": [],
            })
        return (new_state, None)
    if state.phase == Phase.DAY_VOTE:
        pending_votes = pending_votes or []
        new_state, votes, pending_vote_ids = run_vote_turn(
            state,
            pending_votes,
            llm_config,
            player_configs,
            human,
            custom_prompts=custom_prompts,
        )
        if pending_vote_ids:
            return (new_state, {
                "waiting_for_human": True,
                "current_actor_id": None,
                "pending_human_night_ids": [],
                "pending_human_vote_ids": pending_vote_ids,
                "pending_votes": votes,
            })
        # More AI voters to go: persist votes so API and client keep them
        if new_state.phase == Phase.DAY_VOTE and votes:
            return (new_state, {
                "waiting_for_human": False,
                "current_actor_id": None,
                "pending_human_night_ids": [],
                "pending_human_vote_ids": [],
                "pending_votes": votes,
            })
        return (new_state, None)
    return (state, None)
