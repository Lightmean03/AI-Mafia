const API_BASE = (import.meta as unknown as { env: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? ''

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!res.ok) {
    const text = await res.text()
    let message = `API ${res.status}: ${text}`
    try {
      const body = JSON.parse(text) as { detail?: string | unknown[] }
      if (body.detail !== undefined) {
        if (typeof body.detail === 'string') {
          message = body.detail
        } else if (Array.isArray(body.detail) && body.detail.length > 0) {
          const first = body.detail[0]
          message = typeof first === 'object' && first !== null && 'msg' in first
            ? String((first as { msg: unknown }).msg)
            : body.detail.map((e) => (typeof e === 'object' && e !== null && 'msg' in e ? (e as { msg: unknown }).msg : e)).join('; ')
        }
      }
    } catch {
      /* use fallback message */
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

/** Default prompt texts from server (keys match custom_prompts). */
export interface DefaultPromptsResponse {
  rules_summary?: string
  discussion_instructions_template?: string
  vote_instructions_template?: string
  night_action_instructions_template?: string
  summarizer_instructions?: string
}

export async function getPrompts(): Promise<DefaultPromptsResponse> {
  return fetchApi<DefaultPromptsResponse>('/settings/prompts')
}

export const PROMPTS_STORAGE_KEY = 'aimafia.prompts'

/** Read persisted custom prompts from localStorage (set in Settings). Sent with create game when present. */
export function getCustomPromptsFromStorage(): Record<string, string> | undefined {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(PROMPTS_STORAGE_KEY) : null
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as Record<string, string>
    const filtered: Record<string, string> = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'string' && v.trim()) filtered[k] = v.trim()
    }
    return Object.keys(filtered).length ? filtered : undefined
  } catch {
    return undefined
  }
}

export interface CreateGameBody {
  num_players?: number
  num_mafia?: number
  num_doctor?: number
  num_sheriff?: number
  max_discussion_turns?: number
  custom_prompts?: Record<string, string>
  spectate?: boolean
  llm_config?: { provider?: string; model?: string | null; api_key?: string | null }
  players?: import('./types').PlayerConfigInput[]
}

export async function createGame(body: CreateGameBody): Promise<{ game_id: string }> {
  return fetchApi('/games', { method: 'POST', body: JSON.stringify(body) })
}

export type HumanActionType = 'discussion' | 'vote' | 'night_action'

export async function submitAction(
  gameId: string,
  playerId: string,
  actionType: HumanActionType,
  payload: Record<string, unknown>
): Promise<import('./types').GameStateResponse> {
  return fetchApi(`/games/${gameId}/action`, {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, action_type: actionType, payload }),
  })
}

export async function getGame(gameId: string): Promise<import('./types').GameStateResponse> {
  return fetchApi(`/games/${gameId}`)
}

export async function startGame(gameId: string): Promise<import('./types').GameStateResponse> {
  return fetchApi(`/games/${gameId}/start`, { method: 'POST' })
}

export async function stepGame(gameId: string): Promise<import('./types').GameStateResponse> {
  return fetchApi(`/games/${gameId}/step`, { method: 'POST' })
}

export async function listGames(): Promise<string[]> {
  return fetchApi('/games')
}

/** Which provider API keys are set in server env (no values). */
export interface EnvKeysResponse {
  openai: boolean
  anthropic: boolean
  google: boolean
  ollama?: boolean
  ollama_cloud?: boolean
  grok?: boolean
}

export async function getEnvKeys(): Promise<EnvKeysResponse> {
  return fetchApi<EnvKeysResponse>('/settings/env-keys')
}
