import { useState, useEffect } from 'react'
import type { LLMConfig } from '../types'
import { PROVIDERS, getModelsForProvider, PROVIDER_LABELS } from '../llmOptions'
import { getEnvKeys, getPrompts, PROMPTS_STORAGE_KEY, type EnvKeysResponse, type DefaultPromptsResponse } from '../api'
const PROMPT_KEYS = [
  'rules_summary',
  'discussion_instructions_template',
  'vote_instructions_template',
  'night_action_instructions_template',
  'summarizer_instructions',
] as const

interface SettingsProps {
  config: LLMConfig
  onSave: (config: LLMConfig) => void
  onClose: () => void
}

const DEFAULT_API_KEYS: Record<string, string> = {
  openai: '',
  anthropic: '',
  google: '',
  ollama: '',
  ollama_cloud: '',
  grok: '',
}

export function Settings({ config, onSave, onClose }: SettingsProps) {
  const [provider, setProvider] = useState(config.provider === 'gemini' ? 'google' : config.provider)
  const [model, setModel] = useState(config.model ?? '')
  const [apiKeys, setApiKeys] = useState<Record<string, string>>(() => {
    const base = { ...DEFAULT_API_KEYS }
    const fromConfig = config.api_keys ?? {}
    for (const k of Object.keys(fromConfig)) {
      if (k === 'gemini') base.google = fromConfig[k] != null ? fromConfig[k]! : ''
      else if (k in base) base[k] = fromConfig[k] != null ? fromConfig[k]! : ''
    }
    if (config.api_key) base[config.provider === 'gemini' ? 'google' : config.provider] = config.api_key
    return base
  })
  const [envKeys, setEnvKeys] = useState<EnvKeysResponse | null>(null)
  const [defaultPrompts, setDefaultPrompts] = useState<DefaultPromptsResponse | null>(null)
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [promptsOpen, setPromptsOpen] = useState(false)

  const models = getModelsForProvider(provider)

  useEffect(() => {
    setModel((m) => (models.includes(m) ? m : models[0] ?? ''))
  }, [provider])

  useEffect(() => {
    getEnvKeys().then(setEnvKeys).catch(() => setEnvKeys(null))
  }, [])

  useEffect(() => {
    getPrompts()
      .then((defaults) => {
        setDefaultPrompts(defaults)
        try {
          const raw = localStorage.getItem(PROMPTS_STORAGE_KEY)
          const stored: Record<string, string> = raw ? JSON.parse(raw) : {}
          const merged: Record<string, string> = {}
          for (const key of PROMPT_KEYS) {
            merged[key] = stored[key] ?? (defaults as Record<string, string>)[key] ?? ''
          }
          setPrompts(merged)
        } catch {
          const merged: Record<string, string> = {}
          for (const key of PROMPT_KEYS) {
            merged[key] = (defaults as Record<string, string>)[key] ?? ''
          }
          setPrompts(merged)
        }
      })
      .catch(() => setDefaultPrompts({}))
  }, [])

  const handleSave = () => {
    const api_keys: Record<string, string | null> = {}
    for (const p of PROVIDERS) {
      const v = apiKeys[p]?.trim()
      api_keys[p] = v || null
    }
    onSave({
      provider,
      model: model || null,
      api_key: apiKeys[provider]?.trim() || null,
      api_keys,
    })
    try {
      const toStore: Record<string, string> = {}
      for (const key of PROMPT_KEYS) {
        const v = prompts[key]?.trim() ?? ''
        toStore[key] = v
      }
      localStorage.setItem(PROMPTS_STORAGE_KEY, JSON.stringify(toStore))
    } catch {
      /* ignore */
    }
    onClose()
  }

  const handlePromptChange = (key: string, value: string) => {
    setPrompts((prev) => ({ ...prev, [key]: value }))
  }

  const resetPromptsToDefaults = () => {
    if (defaultPrompts) {
      const merged: Record<string, string> = {}
      for (const key of PROMPT_KEYS) {
        merged[key] = (defaultPrompts as Record<string, string>)[key] ?? ''
      }
      setPrompts(merged)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '28rem' }}>
        <h3>LLM Settings</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Default provider and model for new games. Set API keys per provider; leave empty to use server env defaults.
        </p>
        <div className="form-row">
          <label>Default provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {PROVIDERS.map((pr) => (
              <option key={pr} value={pr}>{PROVIDER_LABELS[pr] ?? pr}</option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>Default model</label>
          <select
            value={models.includes(model) ? model : (models[0] ?? '')}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <h4 style={{ margin: '1rem 0 0.5rem 0', fontSize: '0.9rem' }}>API keys (per provider)</h4>
        {PROVIDERS.map((pr) => {
          const formSet = (apiKeys[pr] ?? '').trim().length > 0
          const envSet = envKeys ? envKeys[pr as keyof typeof envKeys] === true : false
          const status = formSet ? 'set' : envSet ? 'set from server' : 'not set'
          return (
          <div key={pr} className="form-row">
            <label>
              {PROVIDER_LABELS[pr] ?? pr}
              <span style={{ color: 'var(--text-muted)', fontWeight: 'normal', marginLeft: '0.35rem' }}>
                ({status})
              </span>
            </label>
            <input
              type="password"
              value={apiKeys[pr] ?? ''}
              onChange={(e) => setApiKeys((prev) => ({ ...prev, [pr]: e.target.value }))}
              placeholder={pr === 'openai' ? 'Optional – use server default' : 'Optional'}
              autoComplete="off"
            />
          </div>
          )
        })}
        <h4 style={{ margin: '1rem 0 0.5rem 0', fontSize: '0.9rem' }}>
          <button
            type="button"
            onClick={() => setPromptsOpen((o) => !o)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0 }}
          >
            {promptsOpen ? '▼' : '▶'} Prompts (rules & instructions)
          </button>
        </h4>
        {promptsOpen && (
          <div style={{ marginBottom: '1rem' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
              Override prompt texts used by the game. Placeholders: {'{player_name}'}, {'{role_name}'}, {'{targets}'}. Saved in browser only; send with new games.
            </p>
            {PROMPT_KEYS.map((key) => (
              <div key={key} className="form-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                <label style={{ marginBottom: '0.25rem' }}>{key.replace(/_/g, ' ')}</label>
                <textarea
                  value={prompts[key] ?? ''}
                  onChange={(e) => handlePromptChange(key, e.target.value)}
                  rows={key === 'rules_summary' ? 5 : 3}
                  style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>
            ))}
            <button type="button" onClick={resetPromptsToDefaults} style={{ marginTop: '0.5rem' }}>
              Reset to server defaults
            </button>
          </div>
        )}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" onClick={handleSave}>Save</button>
        </div>
      </div>
    </div>
  )
}
