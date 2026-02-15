/**
 * Text-to-speech via Web Speech API. Speaks public game text only.
 */

const MAX_SPEECH_LENGTH = 500

function hasSpeech(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

let currentUtterance: SpeechSynthesisUtterance | null = null

export function cancelSpeech(): void {
  if (!hasSpeech()) return
  window.speechSynthesis.cancel()
  currentUtterance = null
}

/** Speak one utterance; does not cancel previous (queue if multiple). */
export function speak(text: string): Promise<void> {
  // #region agent log
  fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'tts.ts:speak', message: 'speak called', data: { hasSpeech: hasSpeech(), textLen: String(text).trim().slice(0, MAX_SPEECH_LENGTH).length }, timestamp: Date.now(), hypothesisId: 'H2' }) }).catch(() => {});
  // #endregion
  if (!hasSpeech()) return Promise.resolve()
  const sanitized = String(text).trim().slice(0, MAX_SPEECH_LENGTH)
  if (!sanitized) return Promise.resolve()

  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(sanitized)
    currentUtterance = u
    u.onend = () => {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'tts.ts:onend', message: 'utterance end', data: {}, timestamp: Date.now(), hypothesisId: 'H2' }) }).catch(() => {});
      // #endregion
      if (currentUtterance === u) currentUtterance = null
      resolve()
    }
    u.onerror = (ev) => {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/2372685e-ef1d-4263-bc80-214b73c64676', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'tts.ts:onerror', message: 'utterance error', data: { error: (ev as SpeechSynthesisErrorEvent).error }, timestamp: Date.now(), hypothesisId: 'H2' }) }).catch(() => {});
      // #endregion
      if (currentUtterance === u) currentUtterance = null
      resolve()
    }
    window.speechSynthesis.speak(u)
  })
}

export function isTtsSupported(): boolean {
  return hasSpeech()
}
