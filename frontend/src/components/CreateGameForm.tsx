import { useState, useMemo, useEffect } from 'react'
import type { LLMConfig, PlayerConfigInput } from '../types'
import { createGame, getCustomPromptsFromStorage, getEnvKeys, listGames, type EnvKeysResponse } from '../api'
import { PROVIDERS, getModelsForProvider, PROVIDER_LABELS } from '../llmOptions'

const DEFAULT_MODEL_BY_PROVIDER: Record<string, string> = {
  openai: 'gpt-4o-mini',
  anthropic: 'claude-3-5-haiku-20241022',
  google: 'gemini-2.0-flash',
  ollama: 'llama3.2',
  ollama_cloud: 'llama3.2',
  grok: 'grok-2',
}

const MAX_NAME_LENGTH = 50

interface CreateGameFormProps {
  llmConfig: LLMConfig | null
  onCreated: (gameId: string) => void
}

function normalizeProvider(p: string | null | undefined): string {
  return p === 'gemini' ? 'google' : (p ?? 'openai')
}

function defaultPlayerConfig(i: number, llmConfig: LLMConfig | null): PlayerConfigInput {
  const provider = normalizeProvider(llmConfig?.provider)
  const models = getModelsForProvider(provider)
  const model = llmConfig?.model && models.includes(llmConfig.model) ? llmConfig.model : (models[0] ?? null)
  return {
    name: model ?? `Player ${i + 1}`,
    provider,
    model,
    api_key: null,
    is_human: false,
  }
}

export function CreateGameForm({ llmConfig, onCreated }: CreateGameFormProps) {
  const [numPlayers, setNumPlayers] = useState(6)
  const [numMafia, setNumMafia] = useState(1)
  const [numDoctor, setNumDoctor] = useState(1)
  const [numSheriff, setNumSheriff] = useState(1)
  const [maxDiscussionTurns, setMaxDiscussionTurns] = useState(6)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [playerConfigs, setPlayerConfigs] = useState<PlayerConfigInput[]>(() =>
    Array.from({ length: 6 }, (_, i) => defaultPlayerConfig(i, llmConfig))
  )
  const [envKeys, setEnvKeys] = useState<EnvKeysResponse | null>(null)
  const [spectate, setSpectate] = useState(false)
  const [recentGameIds, setRecentGameIds] = useState<string[]>([])

  useEffect(() => {
    getEnvKeys().then(setEnvKeys).catch(() => setEnvKeys(null))
  }, [])
  useEffect(() => {
    listGames()
      .then((ids) => setRecentGameIds(ids.slice(0, 10)))
      .catch(() => setRecentGameIds([]))
  }, [])

  const townSize = numPlayers - numMafia
  useEffect(() => {
    if (maxDiscussionTurns < numPlayers) setMaxDiscussionTurns(numPlayers)
  }, [numPlayers, maxDiscussionTurns])
  useEffect(() => {
    if (townSize < 0) return
    const newDoctor = Math.min(numDoctor, townSize)
    const newSheriff = Math.min(numSheriff, townSize - newDoctor)
    if (newDoctor !== numDoctor) setNumDoctor(newDoctor)
    if (newSheriff !== numSheriff) setNumSheriff(newSheriff)
  }, [townSize, numDoctor, numSheriff])

  const playersConfig = useMemo(() => {
    const arr = playerConfigs.slice(0, numPlayers)
    while (arr.length < numPlayers) {
      arr.push(defaultPlayerConfig(arr.length, llmConfig))
    }
    return arr.slice(0, numPlayers)
  }, [numPlayers, playerConfigs, llmConfig])

  const updatePlayer = (index: number, patch: Partial<PlayerConfigInput>) => {
    setPlayerConfigs((prev) => {
      const next = [...prev]
      while (next.length <= index) next.push(defaultPlayerConfig(next.length, llmConfig))
      next[index] = { ...next[index], ...patch }
      return next
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const players: PlayerConfigInput[] = playersConfig.map((p, idx) => {
      const provider = p.provider || llmConfig?.provider || 'openai'
      const apiKey = p.api_key ?? llmConfig?.api_keys?.[provider] ?? llmConfig?.api_key ?? undefined
      return {
        name: p.name.trim().slice(0, MAX_NAME_LENGTH) || `Player ${idx + 1}`,
        provider: provider || undefined,
        model: p.model || undefined,
        api_key: apiKey || undefined,
        is_human: p.is_human ?? false,
      }
    })
    if (players.some((p) => !p.name.trim())) {
      setError('Every player needs a name')
      return
    }
    setLoading(true)
    try {
      const body: Parameters<typeof createGame>[0] = {
        num_players: numPlayers,
        num_mafia: numMafia,
        num_doctor: numDoctor,
        num_sheriff: numSheriff,
        max_discussion_turns: Math.max(numPlayers, maxDiscussionTurns),
        players,
        custom_prompts: getCustomPromptsFromStorage(),
        spectate: spectate || undefined,
      }
      if (!players.some((p) => p.provider || p.model)) {
        const defaultKey = llmConfig?.api_keys?.[llmConfig.provider] ?? llmConfig?.api_key
        if (llmConfig && (defaultKey || llmConfig.model)) {
          body.llm_config = {
            provider: llmConfig.provider,
            model: llmConfig.model ?? undefined,
            api_key: defaultKey ?? undefined,
          }
        }
      }
      const res = await createGame(body)
      onCreated(res.game_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      {recentGameIds.length > 0 && (
        <section style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '0.95rem' }}>Recent games</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
            {recentGameIds.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => onCreated(id)}
                style={{ fontSize: '0.85rem', padding: '0.35rem 0.6rem' }}
              >
                {id.slice(0, 8)}
              </button>
            ))}
          </div>
        </section>
      )}
    <form onSubmit={handleSubmit}>
      <h2>New game</h2>
      <div className="form-row">
        <label htmlFor="num-players">Players</label>
        <input
          id="num-players"
          type="number"
          min={4}
          max={15}
          value={numPlayers}
          onChange={(e) => setNumPlayers(Number(e.target.value))}
        />
      </div>
      <div className="form-row">
        <label htmlFor="num-mafia">Mafia</label>
        <input
          id="num-mafia"
          type="number"
          min={1}
          max={Math.min(4, numPlayers - 1)}
          value={numMafia}
          onChange={(e) => setNumMafia(Number(e.target.value))}
        />
      </div>
      <div className="form-row">
        <label htmlFor="num-doctor">Doctors</label>
        <input
          id="num-doctor"
          type="number"
          min={0}
          max={Math.min(4, townSize - numSheriff)}
          value={numDoctor}
          onChange={(e) => setNumDoctor(Math.max(0, Math.min(townSize - numSheriff, Number(e.target.value) || 0)))}
        />
      </div>
      <div className="form-row">
        <label htmlFor="num-sheriff">Sheriffs</label>
        <input
          id="num-sheriff"
          type="number"
          min={0}
          max={Math.min(4, townSize - numDoctor)}
          value={numSheriff}
          onChange={(e) => setNumSheriff(Math.max(0, Math.min(townSize - numDoctor, Number(e.target.value) || 0)))}
        />
      </div>
      <div className="form-row">
        <label htmlFor="max-discussion-turns">Max discussion turns per round</label>
        <input
          id="max-discussion-turns"
          type="number"
          min={numPlayers}
          max={100}
          value={maxDiscussionTurns}
          onChange={(e) => setMaxDiscussionTurns(Math.max(numPlayers, Number(e.target.value) || numPlayers))}
          title="Each player speaks at least once; AIs can request more turns up to this cap."
        />
      </div>
      <div className="form-row">
        <label htmlFor="spectate">I am spectating</label>
        <input
          id="spectate"
          type="checkbox"
          checked={spectate}
          onChange={(e) => setSpectate(e.target.checked)}
          title="Watch the game with all roles and reasoning visible; no human player slot."
        />
      </div>
      <h3 style={{ margin: '0.75rem 0 0.25rem 0', fontSize: '0.95rem' }}>Per-player</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '0.75rem' }}>
        {playersConfig.map((p, i) => {
          const provider = normalizeProvider(p.provider)
          const formKeySet = !!(llmConfig?.api_keys?.[provider]?.trim() ?? llmConfig?.api_key?.trim())
          const envKeySet = envKeys ? envKeys[provider as keyof EnvKeysResponse] === true : false
          const keyAvailable = formKeySet || envKeySet
          const defaultModel = DEFAULT_MODEL_BY_PROVIDER[provider] ?? 'gpt-4o-mini'
          return (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <div className="form-row" style={{ flexWrap: 'wrap', gap: '0.25rem', alignItems: 'center' }}>
              <label htmlFor={`player-provider-${i}`} aria-label={`Player ${i + 1} provider`}>
                P{i + 1}
              </label>
              <select
                id={`player-provider-${i}`}
                aria-label={`Player ${i + 1} provider`}
                value={provider}
                onChange={(e) => {
                  const pr = e.target.value || 'openai'
                  const models = getModelsForProvider(pr)
                  const newModel = models.includes(p.model ?? '') ? p.model : (models[0] ?? null)
                  const nameFromModel = p.name === (p.model ?? '') || !p.name.trim() || p.name === `Player ${i + 1}`
                  updatePlayer(i, {
                    provider: pr,
                    model: newModel,
                    name: nameFromModel ? (newModel ?? `Player ${i + 1}`) : p.name,
                  })
                }}
                style={{ width: '8rem' }}
              >
                {PROVIDERS.map((pr) => (
                  <option key={pr} value={pr}>{PROVIDER_LABELS[pr] ?? pr}</option>
                ))}
              </select>
              <select
                id={`player-model-${i}`}
                aria-label={`Player ${i + 1} model`}
                value={getModelsForProvider(provider).includes(p.model ?? '') ? (p.model ?? '') : (getModelsForProvider(provider)[0] ?? '')}
                onChange={(e) => {
                  const newModel = e.target.value || null
                  const nameFromModel = p.name === (p.model ?? '') || !p.name.trim() || p.name === `Player ${i + 1}`
                  updatePlayer(i, {
                    model: newModel,
                    name: nameFromModel ? (newModel ?? p.name) : p.name,
                  })
                }}
                style={{ width: '12rem' }}
              >
                {getModelsForProvider(provider).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <input
                id={`player-name-${i}`}
                type="text"
                placeholder="Name"
                maxLength={MAX_NAME_LENGTH}
                value={p.name}
                onChange={(e) => updatePlayer(i, { name: e.target.value })}
                style={{ width: '10rem' }}
              />
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <input
                  type="checkbox"
                  checked={p.is_human ?? false}
                  onChange={(e) => updatePlayer(i, { is_human: e.target.checked })}
                  aria-label={`Player ${i + 1} human`}
                />
                Human
              </label>
            </div>
            {!keyAvailable && (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0, marginLeft: '0.5rem' }}>
                No API key for {PROVIDER_LABELS[provider] ?? provider}. Requests for this player may fail. Set a key in Settings or server env, or the app may fall back to another provider&apos;s key (see README). Default model for this provider: {defaultModel}.
              </p>
            )}
          </div>
          )
        })}
      </div>
      {error && <p style={{ color: 'var(--danger)', marginBottom: '0.75rem' }}>{error}</p>}
      <div className="actions">
        <button type="submit" disabled={loading}>
          {loading ? 'Creating…' : 'Create game'}
        </button>
      </div>
    </form>
    </div>
  )
}
