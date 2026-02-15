export interface LLMConfig {
  provider: string
  model: string | null
  /** @deprecated Use api_keys per provider instead */
  api_key?: string | null
  /** API key per provider (openai, anthropic, google). Used when creating games. */
  api_keys?: Record<string, string | null>
}

/** One vote in the current round: who voted for whom */
export interface VotePublic {
  voter_id: string
  voter_name: string
  target_id: string
  target_name: string
  reason: string
}

export interface PlayerPublic {
  id: string
  name: string
  alive: boolean
  role: string | null
}

export interface EventPublic {
  kind: string
  round_index: number
  phase: string
  message: string
  player_id: string | null
  target_id: string | null
}

export interface DiscussionMessagePublic {
  player_id: string
  player_name: string
  statement: string
  round_index: number
}

export interface GameStateResponse {
  game_id: string
  players: PlayerPublic[]
  round_index: number
  phase: string
  events: EventPublic[]
  discussion: DiscussionMessagePublic[]
  started: boolean
  winner: string | null
  waiting_for_human?: boolean
  current_actor_id?: string | null
  pending_human_vote_ids?: string[]
  pending_human_night_ids?: string[]
  human_player_ids?: string[]
  /** Votes this round: who each player voted for (and reason) */
  current_round_votes?: VotePublic[]
  /** True when game was created with spectate; roles and reasoning visible */
  spectate?: boolean
  /** Mafia night discussion (only when spectate) */
  spectator_mafia_discussion?: { player_id: string; player_name: string; statement: string; round_index: number }[]
  /** Night action reasoning: mafia/doctor/sheriff (only when spectate) */
  spectator_night_reasoning?: { role: string; player_name: string; target_name: string; reason: string }[]
}

export interface PlayerConfigInput {
  name: string
  provider?: string | null
  model?: string | null
  api_key?: string | null
  is_human?: boolean
}
