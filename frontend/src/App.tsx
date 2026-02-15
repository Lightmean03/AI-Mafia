import { useState } from 'react'
import './App.css'
import type { LLMConfig } from './types'
import { Settings } from './components/Settings'
import { CreateGameForm } from './components/CreateGameForm'
import { GameView } from './components/GameView'

const DEFAULT_LLM: LLMConfig = {
  provider: 'openai',
  model: null,
  api_key: null,
}

function App() {
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(DEFAULT_LLM)
  const [showSettings, setShowSettings] = useState(false)
  const [currentGameId, setCurrentGameId] = useState<string | null>(null)

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <img src="/logo.png" alt="" className="header-logo" aria-hidden="true" />
          <h1>AI Mafia</h1>
        </div>
        <button type="button" onClick={() => setShowSettings(true)}>Settings</button>
      </header>

      {showSettings && (
        <Settings
          config={llmConfig}
          onSave={setLlmConfig}
          onClose={() => setShowSettings(false)}
        />
      )}

      {currentGameId ? (
        <GameView
          gameId={currentGameId}
          onBack={() => setCurrentGameId(null)}
        />
      ) : (
        <CreateGameForm
          llmConfig={llmConfig}
          onCreated={setCurrentGameId}
        />
      )}
    </div>
  )
}

export default App
