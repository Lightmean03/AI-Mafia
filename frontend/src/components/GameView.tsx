import { useState, useEffect, useRef } from 'react'
import type { GameStateResponse } from '../types'
import { getGame, stepGame, submitAction } from '../api'
import { speak, cancelSpeech, isTtsSupported } from '../tts'

const AUTO_ADVANCE_KEY = 'aimafia.autoAdvance'
const AUTO_ADVANCE_INTERVAL_KEY = 'aimafia.autoAdvanceInterval'
const TTS_ENABLED_KEY = 'aimafia.ttsEnabled'
const MIN_INTERVAL = 1
const MAX_INTERVAL = 300
const DEFAULT_INTERVAL = 10

function loadAutoAdvance(): boolean {
  try {
    const v = localStorage.getItem(AUTO_ADVANCE_KEY)
    return v === 'true'
  } catch {
    return false
  }
}

function loadAutoAdvanceInterval(): number {
  try {
    const v = localStorage.getItem(AUTO_ADVANCE_INTERVAL_KEY)
    if (v != null) {
      const n = parseInt(v, 10)
      if (n >= MIN_INTERVAL && n <= MAX_INTERVAL) return n
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_INTERVAL
}

function loadTtsEnabled(): boolean {
  try {
    return localStorage.getItem(TTS_ENABLED_KEY) === 'true'
  } catch {
    return false
  }
}

interface GameViewProps {
  gameId: string
  onBack: () => void
}

export function GameView({ gameId, onBack }: GameViewProps) {
  const [state, setState] = useState<GameStateResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [stepping, setStepping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoAdvanceEnabled, setAutoAdvanceEnabled] = useState(loadAutoAdvance)
  const [autoAdvanceIntervalSeconds, setAutoAdvanceIntervalSeconds] = useState(loadAutoAdvanceInterval)
  const [ttsEnabled, setTtsEnabled] = useState(loadTtsEnabled)
  const [countdownSeconds, setCountdownSeconds] = useState<number | null>(null)
  const stateRef = useRef(state)
  const autoAdvanceRef = useRef(autoAdvanceEnabled)
  const lastDiscussionLen = useRef(0)
  const lastEventsLen = useRef(0)
  const lastSpokenDiscussionLen = useRef(0)
  const lastSpokenEventsLen = useRef(0)
  const ttsInitialized = useRef(false)
  const [liveRegionMessage, setLiveRegionMessage] = useState('')
  stateRef.current = state
  autoAdvanceRef.current = autoAdvanceEnabled

  const refresh = async () => {
    try {
      const data = await getGame(gameId)
      setState(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load game')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [gameId])

  useEffect(() => {
    if (gameId && state) {
      document.title = `Game ${gameId.slice(0, 8)} — AI Mafia`
    }
    return () => {
      document.title = 'AI Mafia'
    }
  }, [gameId, state])

  const handleStep = async () => {
    if (!stateRef.current || stateRef.current.winner) return
    setStepping(true)
    try {
      const next = await stepGame(gameId)
      setState(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Step failed')
    } finally {
      setStepping(false)
    }
  }

  const intervalSec = Math.max(MIN_INTERVAL, Math.min(MAX_INTERVAL, autoAdvanceIntervalSeconds))

  useEffect(() => {
    if (!autoAdvanceEnabled || !state || state.winner || state.waiting_for_human || stepping) {
      setCountdownSeconds(null)
      return
    }
    setCountdownSeconds(intervalSec)
  }, [autoAdvanceEnabled, state?.winner, state?.waiting_for_human, stepping, state?.phase, state?.round_index, intervalSec])

  useEffect(() => {
    if (countdownSeconds == null || countdownSeconds <= 0) return
    const t = setInterval(() => {
      setCountdownSeconds((prev) => {
        if (prev == null || prev <= 1) return 0
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(t)
  }, [countdownSeconds])

  useEffect(() => {
    if (!autoAdvanceEnabled || !state || state.winner || state.waiting_for_human || stepping) {
      return
    }
    const ms = intervalSec * 1000
    const id = setTimeout(() => {
      const s = stateRef.current
      if (!autoAdvanceRef.current || !s || s.winner || s.waiting_for_human) return
      handleStep()
    }, ms)
    return () => clearTimeout(id)
  }, [autoAdvanceEnabled, intervalSec, state?.winner, state?.waiting_for_human, stepping, state?.phase, state?.round_index])

  useEffect(() => {
    if (!state) return
    const d = state.discussion.length
    const e = state.events.length
    // #region agent log
    fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'GameView.tsx:liveRegionEffect', message: 'liveRegion effect ran', data: { d, e, lastD: lastDiscussionLen.current, lastE: lastEventsLen.current, willUpdateD: d > lastDiscussionLen.current, willUpdateE: e > lastEventsLen.current }, timestamp: Date.now(), hypothesisId: 'H1' }) }).catch(() => {});
    // #endregion
    if (d > lastDiscussionLen.current) {
      setLiveRegionMessage('New discussion message.')
      const t = setTimeout(() => setLiveRegionMessage(''), 2000)
      lastDiscussionLen.current = d
      lastEventsLen.current = e
      return () => clearTimeout(t)
    }
    if (e > lastEventsLen.current) {
      setLiveRegionMessage('New event.')
      const t = setTimeout(() => setLiveRegionMessage(''), 2000)
      lastDiscussionLen.current = d
      lastEventsLen.current = e
      return () => clearTimeout(t)
    }
    lastDiscussionLen.current = d
    lastEventsLen.current = e
  }, [state?.discussion.length, state?.events.length])

  useEffect(() => {
    const hasState = !!state
    const hasTts = !!ttsEnabled && isTtsSupported()
    // #region agent log
    fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'GameView.tsx:ttsEffect', message: 'tts effect ran', data: { hasState, hasTts, ttsInit: ttsInitialized.current, dLen: state?.discussion?.length ?? 0, eLen: state?.events?.length ?? 0, prevD: lastSpokenDiscussionLen.current, prevE: lastSpokenEventsLen.current }, timestamp: Date.now(), hypothesisId: 'H1,H4,H5' }) }).catch(() => {});
    // #endregion
    if (!state || !ttsEnabled || !isTtsSupported()) return
    const d = state.discussion
    const e = state.events
    if (!ttsInitialized.current) {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'GameView.tsx:ttsInit', message: 'tts first run skip', data: { dLen: d.length, eLen: e.length }, timestamp: Date.now(), hypothesisId: 'H5' }) }).catch(() => {});
      // #endregion
      lastSpokenDiscussionLen.current = d.length
      lastSpokenEventsLen.current = e.length
      ttsInitialized.current = true
      return
    }
    const prevD = lastSpokenDiscussionLen.current
    const prevE = lastSpokenEventsLen.current
    lastSpokenDiscussionLen.current = d.length
    lastSpokenEventsLen.current = e.length
    const skip = d.length <= prevD && e.length <= prevE
    // #region agent log
    fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'GameView.tsx:ttsCheck', message: 'tts length check', data: { prevD, prevE, dLen: d.length, eLen: e.length, skip, willSpeakD: prevD < d.length, willSpeakE: prevE < e.length }, timestamp: Date.now(), hypothesisId: 'H1,H3' }) }).catch(() => {});
    // #endregion
    if (skip) return
    ;(async () => {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'GameView.tsx:ttsLoopStart', message: 'tts async loop start', data: { fromD: prevD, toD: d.length, fromE: prevE, toE: e.length }, timestamp: Date.now(), hypothesisId: 'H3' }) }).catch(() => {});
      // #endregion
      for (let i = prevD; i < d.length; i++) {
        await speak(`${d[i].player_name}: ${d[i].statement}`)
      }
      for (let j = prevE; j < e.length; j++) {
        await speak(e[j].message)
      }
    })()
  }, [state, ttsEnabled])

  useEffect(() => {
    if (!ttsEnabled) cancelSpeech()
  }, [ttsEnabled])

  useEffect(() => {
    return () => cancelSpeech()
  }, [])

  const humanIds = state?.human_player_ids ?? []
  const waiting = state?.waiting_for_human ?? false
  const currentActorId = state?.current_actor_id ?? null
  const pendingVoteIds = state?.pending_human_vote_ids ?? []
  const pendingNightIds = state?.pending_human_night_ids ?? []
  const alivePlayers = state?.players.filter((p) => p.alive) ?? []
  const voteTargetOptions = alivePlayers.map((p) => ({ id: p.id, name: p.name }))

  const handleHumanAction = async (
    playerId: string,
    actionType: 'discussion' | 'vote' | 'night_action',
    payload: Record<string, unknown>
  ) => {
    if (!state) return
    try {
      const next = await submitAction(gameId, playerId, actionType, payload)
      setState(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    }
  }

  if (loading) return <div className="card">Loading…</div>
  if (error) return <div className="card" role="alert" aria-live="assertive" style={{ color: 'var(--danger)' }}>{error}</div>
  if (!state) return null

  const leftColumn = (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--section-gap)' }}>
        <h2>Game {gameId.slice(0, 8)}</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button type="button" onClick={() => refresh()}>Refresh</button>
          <button type="button" onClick={onBack}>Back</button>
        </div>
      </div>
      {state.winner && (
        <div className={`winner-badge ${state.winner}`} style={{ marginBottom: 'var(--section-gap)' }}>
          {state.winner === 'town' ? 'Town wins!' : 'Mafia wins!'}
        </div>
      )}
      <div className="phase-badge">
        Round {state.round_index + 1} · {state.phase.replace('_', ' ')}
      </div>

      <section className="game-view-section">
        <h3>Players</h3>
        <div className="players-list">
          {state.players.map((p) => (
            <span key={p.id} className={`player-chip ${p.alive ? '' : 'dead'}`}>
              {p.name}
              {humanIds.includes(p.id) && <span className="human-badge" title="Human"> Human</span>}
              {p.role != null && ` (${p.role})`}
            </span>
          ))}
        </div>
      </section>

      <section className="game-view-section">
        <h3>Events</h3>
        <div className="events-log">
          {state.events.map((e, i) => (
            <p key={i}>{e.message}</p>
          ))}
        </div>
      </section>

      {!state.winner && waiting && (
        <section className="game-view-section" style={{ marginTop: 'var(--section-gap)' }}>
          <HumanActionForm
            state={state}
            currentActorId={currentActorId}
            pendingVoteIds={pendingVoteIds}
            pendingNightIds={pendingNightIds}
            voteTargetOptions={voteTargetOptions}
            onSubmit={handleHumanAction}
          />
        </section>
      )}

      {!state.winner && (
        <div className="game-controls" style={{ marginTop: 'var(--section-gap)', paddingTop: 'var(--section-gap)', borderTop: '1px solid var(--border)' }}>
          <div className="actions">
            {!waiting && (
              <button onClick={handleStep} disabled={stepping}>
                {stepping ? 'Running…' : 'Next step'}
              </button>
            )}
          </div>
          <div className="auto-advance" style={{ marginTop: '0.75rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <input
                type="checkbox"
                checked={autoAdvanceEnabled}
                onChange={(e) => {
                  const v = e.target.checked
                  setAutoAdvanceEnabled(v)
                  try {
                    localStorage.setItem(AUTO_ADVANCE_KEY, String(v))
                  } catch {
                    /* ignore */
                  }
                }}
                aria-label="Auto-advance"
              />
              Auto-advance
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span>Interval (s)</span>
              <input
                type="number"
                min={MIN_INTERVAL}
                max={MAX_INTERVAL}
                value={autoAdvanceIntervalSeconds}
                onChange={(e) => {
                  const v = Math.max(MIN_INTERVAL, Math.min(MAX_INTERVAL, Number(e.target.value) || MIN_INTERVAL))
                  setAutoAdvanceIntervalSeconds(v)
                  try {
                    localStorage.setItem(AUTO_ADVANCE_INTERVAL_KEY, String(v))
                  } catch {
                    /* ignore */
                  }
                }}
                style={{ width: '4rem' }}
                aria-label="Auto-advance interval seconds"
              />
            </label>
            {!waiting && countdownSeconds != null && countdownSeconds > 0 && (
              <span className="countdown" style={{ fontWeight: 600, color: 'var(--accent)' }}>
                Next step in {countdownSeconds}s
              </span>
            )}
            {waiting && (
              <span className="auto-advance-paused" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                Paused for human turn
              </span>
            )}
            {isTtsSupported() && (
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input
                  type="checkbox"
                  checked={ttsEnabled}
                  onChange={(e) => {
                    const v = e.target.checked
                    setTtsEnabled(v)
                    if (!v) cancelSpeech()
                    try {
                      localStorage.setItem(TTS_ENABLED_KEY, String(v))
                    } catch {
                      /* ignore */
                    }
                  }}
                  aria-label="Read aloud (TTS)"
                />
                Read aloud (TTS)
              </label>
            )}
          </div>
        </div>
      )}
    </>
  )

  const sidePanel = (
    <aside className="game-view-side-panel">
      <section className="game-view-section">
        <h3>Discussion</h3>
        <div className="discussion-log">
          {state.discussion.length > 0 ? (
            state.discussion.map((m, i) => (
              <div key={`discussion-${state.round_index}-${i}`} className="message">
                <strong>{m.player_name}:</strong> {m.statement}
              </div>
            ))
          ) : (
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: 0 }}>No discussion yet.</p>
          )}
        </div>
      </section>

      <section className="game-view-section">
        <h3>
          {state.phase === 'day_vote' ? 'Voting phase' : 'Votes this round'}
        </h3>
        {state.phase === 'day_vote' && (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: '0 0 0.5rem 0' }}>
            Each player votes in turn (or abstains). Everyone must cast a vote.
          </p>
        )}
        <div className="votes-log">
          {state.current_round_votes?.length ? (
            state.current_round_votes.map((v, i) => (
              <p key={`vote-${state.round_index}-${i}`}>
                <strong>{v.voter_name}</strong> → {v.target_name}
                {v.reason && <span style={{ color: 'var(--text-muted)' }}>: {v.reason}</span>}
              </p>
            ))
          ) : (
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: 0 }}>No votes yet.</p>
          )}
        </div>
      </section>

      {state.spectate && (
        <section className="game-view-section" style={{ marginTop: '1rem' }}>
          <h3>Night dialogue</h3>
          {(state.spectator_mafia_discussion && state.spectator_mafia_discussion.length > 0) || (state.spectator_night_reasoning && state.spectator_night_reasoning.length > 0) ? (
            <>
              {state.spectator_mafia_discussion && state.spectator_mafia_discussion.length > 0 && (
                <div className="discussion-log" style={{ marginBottom: '0.75rem' }}>
                  {state.spectator_mafia_discussion.map((msg, i) => (
                    <div key={`mafia-${i}`} className="message">
                      <strong>{msg.player_name}:</strong> {msg.statement}
                    </div>
                  ))}
                </div>
              )}
              {state.spectator_night_reasoning && state.spectator_night_reasoning.length > 0 && (
                <div className="votes-log">
                  {state.spectator_night_reasoning.map((r, i) => (
                    <p key={`reasoning-${i}`}>
                      <strong>{r.role} ({r.player_name}):</strong> {r.target_name}
                      {r.reason && <span style={{ color: 'var(--text-muted)' }}> — {r.reason}</span>}
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: 0 }}>No night dialogue yet.</p>
          )}
        </section>
      )}
    </aside>
  )

  return (
    <div className="card game-view">
      <div role="status" aria-live="polite" className="sr-only" aria-atomic="true">
        {liveRegionMessage}
      </div>
      <div style={{ display: 'flex', gap: 'var(--section-gap)', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 320px', minWidth: 0 }}>{leftColumn}</div>
        {sidePanel}
      </div>
    </div>
  )
}

interface HumanActionFormProps {
  state: GameStateResponse
  currentActorId: string | null
  pendingVoteIds: string[]
  pendingNightIds: string[]
  voteTargetOptions: { id: string; name: string }[]
  onSubmit: (playerId: string, actionType: 'discussion' | 'vote' | 'night_action', payload: Record<string, unknown>) => Promise<void>
}

function HumanActionForm({
  state,
  currentActorId,
  pendingVoteIds,
  pendingNightIds,
  voteTargetOptions,
  onSubmit,
}: HumanActionFormProps) {
  const [statement, setStatement] = useState('')
  const [votePlayerId, setVotePlayerId] = useState('')
  const [voteTargetId, setVoteTargetId] = useState('')
  const [voteReason, setVoteReason] = useState('')
  const [nightTargetId, setNightTargetId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const actor = currentActorId ? state.players.find((p) => p.id === currentActorId) : null
  const isDiscussion = state.phase === 'day_discussion' && currentActorId
  const isVote = state.phase === 'day_vote' && pendingVoteIds.length > 0
  const isNight = state.phase === 'night' && pendingNightIds.length > 0

  const handleDiscussionSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentActorId || !statement.trim()) return
    setSubmitting(true)
    try {
      await onSubmit(currentActorId, 'discussion', { statement: statement.trim().slice(0, 500) })
      setStatement('')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVoteSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const pid = votePlayerId || pendingVoteIds[0]
    if (!pid || !voteTargetId) return
    setSubmitting(true)
    try {
      await onSubmit(pid, 'vote', { target_id: voteTargetId, reason: voteReason.slice(0, 300) })
      setVoteTargetId('')
      setVoteReason('')
    } finally {
      setSubmitting(false)
    }
  }

  const handleNightSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const pid = currentActorId || pendingNightIds[0]
    if (!pid || !nightTargetId) return
    setSubmitting(true)
    try {
      await onSubmit(pid, 'night_action', { target_id: nightTargetId })
      setNightTargetId('')
    } finally {
      setSubmitting(false)
    }
  }

  if (isDiscussion && actor) {
    return (
      <div className="human-form" style={{ marginTop: '0.75rem', padding: '0.75rem', border: '1px solid var(--border)', borderRadius: '4px' }}>
        <p><strong>Your turn: {actor.name}</strong> (discussion)</p>
        <form onSubmit={handleDiscussionSubmit}>
          <label htmlFor="human-statement">Statement</label>
          <textarea
            id="human-statement"
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            rows={2}
            maxLength={500}
            placeholder="Your statement…"
            style={{ width: '100%', marginBottom: '0.5rem' }}
          />
          <button type="submit" disabled={submitting || !statement.trim()}>
            {submitting ? 'Submitting…' : 'Submit'}
          </button>
        </form>
      </div>
    )
  }

  if (isVote) {
    return (
      <div className="human-form" style={{ marginTop: '0.75rem', padding: '0.75rem', border: '1px solid var(--border)', borderRadius: '4px' }}>
        <p><strong>Vote (human)</strong></p>
        <form onSubmit={handleVoteSubmit}>
          {pendingVoteIds.length > 1 && (
            <div style={{ marginBottom: '0.5rem' }}>
              <label htmlFor="vote-as">Vote as </label>
              <select
                id="vote-as"
                value={votePlayerId}
                onChange={(e) => setVotePlayerId(e.target.value)}
                required
              >
                <option value="">Select player</option>
                {pendingVoteIds.map((id) => (
                  <option key={id} value={id}>{state.players.find((p) => p.id === id)?.name ?? id}</option>
                ))}
              </select>
            </div>
          )}
          {pendingVoteIds.length === 1 && (
            <input type="hidden" value={pendingVoteIds[0]} readOnly />
          )}
          <div style={{ marginBottom: '0.5rem' }}>
            <label htmlFor="vote-target">Vote for (or abstain) </label>
            <select
              id="vote-target"
              value={voteTargetId}
              onChange={(e) => setVoteTargetId(e.target.value)}
              required
            >
              <option value="">Select target</option>
              <option value="abstain">Abstain</option>
              {voteTargetOptions
                .filter((o) => o.id !== (votePlayerId || pendingVoteIds[0]))
                .map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
            </select>
          </div>
          <div style={{ marginBottom: '0.5rem' }}>
            <label htmlFor="vote-reason">Reason (optional)</label>
            <input
              id="vote-reason"
              type="text"
              value={voteReason}
              onChange={(e) => setVoteReason(e.target.value)}
              maxLength={300}
              placeholder="Reason…"
              style={{ width: '100%' }}
            />
          </div>
          <button type="submit" disabled={submitting || !voteTargetId || (pendingVoteIds.length > 1 && !votePlayerId)}>
            {submitting ? 'Submitting…' : 'Submit vote'}
          </button>
        </form>
      </div>
    )
  }

  if (isNight && (currentActorId || pendingNightIds[0])) {
    const pid = currentActorId || pendingNightIds[0]
    const actorName = state.players.find((p) => p.id === pid)?.name ?? pid
    const options = voteTargetOptions.filter((o) => o.id !== pid)
    return (
      <div className="human-form" style={{ marginTop: '0.75rem', padding: '0.75rem', border: '1px solid var(--border)', borderRadius: '4px' }}>
        <p><strong>Night action: {actorName}</strong></p>
        <form onSubmit={handleNightSubmit}>
          <label htmlFor="night-target">Target </label>
          <select
            id="night-target"
            value={nightTargetId}
            onChange={(e) => setNightTargetId(e.target.value)}
            required
          >
            <option value="">Select target</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
          <button type="submit" disabled={submitting || !nightTargetId}>
            {submitting ? 'Submitting…' : 'Submit'}
          </button>
        </form>
      </div>
    )
  }

  return null
}
