import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Narration over the Web Speech API.
 *
 * Two decisions shape this hook.
 *
 * **One utterance per verse, not one per passage.** The obvious approach —
 * speak the whole chapter as a single utterance and use `onboundary` character
 * offsets to work out where you are — is unreliable: `onboundary` is not fired
 * at all by some engines, and the offsets it reports do not agree across
 * browsers. Queueing a separate utterance per verse gives exact, portable
 * verse-level position from `onstart`/`onend` alone. It also sidesteps the
 * long-standing Chrome bug where synthesis stops after roughly 15 seconds of
 * continuous speech, because no single utterance runs that long.
 *
 * **The queue is advanced by us, not by the engine.** Utterances are spoken one
 * at a time and the next is queued in the previous one's `onend`, so pausing,
 * skipping and stopping stay responsive instead of fighting a queue the engine
 * has already buffered.
 *
 * A cloud TTS provider would slot in behind the same interface: `speak` would
 * fetch and play audio per verse, and everything above this line stays put.
 */

const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
export const narrationSupported = !!synth

export function useNarrator({ onIndexChange } = {}) {
  const [voices, setVoices] = useState([])
  const [speaking, setSpeaking] = useState(false)
  const [paused, setPaused] = useState(false)
  const [index, setIndex] = useState(-1)
  const [error, setError] = useState(null)

  // Refs, not state: the onend callback closes over these and must see current
  // values without the hook re-subscribing on every render.
  const queueRef = useRef([])
  const indexRef = useRef(-1)
  const stoppedRef = useRef(true)
  const optsRef = useRef({ voice: null, rate: 0.95, pitch: 1.0 })
  const startedRef = useRef(false)
  const keepAliveRef = useRef(null)

  // Voices populate asynchronously, and in some browsers the first call
  // returns an empty list until `voiceschanged` fires.
  useEffect(() => {
    if (!synth) return
    const load = () => setVoices(synth.getVoices() || [])
    load()
    synth.addEventListener?.('voiceschanged', load)
    return () => synth.removeEventListener?.('voiceschanged', load)
  }, [])

  const setPosition = useCallback((i) => {
    indexRef.current = i
    setIndex(i)
    onIndexChange?.(i)
  }, [onIndexChange])

  const clearKeepAlive = () => {
    if (keepAliveRef.current) {
      clearInterval(keepAliveRef.current)
      keepAliveRef.current = null
    }
  }

  const stop = useCallback(() => {
    stoppedRef.current = true
    clearKeepAlive()
    try { synth?.cancel() } catch { /* engine already torn down */ }
    setSpeaking(false)
    setPaused(false)
    setPosition(-1)
  }, [setPosition])

  const speakAt = useCallback((i) => {
    if (!synth || stoppedRef.current) return
    const queue = queueRef.current
    if (i < 0 || i >= queue.length) {
      stop()
      return
    }
    setPosition(i)

    const u = new SpeechSynthesisUtterance(queue[i].text)
    const { voice, rate, pitch } = optsRef.current
    if (voice) u.voice = voice
    u.rate = rate
    u.pitch = pitch

    u.onstart = () => { startedRef.current = true }

    u.onend = () => {
      if (stoppedRef.current) return
      speakAt(indexRef.current + 1)
    }

    u.onerror = (e) => {
      // 'interrupted' and 'canceled' are the normal result of stop() and skip().
      if (e?.error === 'interrupted' || e?.error === 'canceled') return

      // If nothing has ever begun speaking, there is no working speech engine
      // behind the API — a browser with the interface present but no installed
      // voices (common on Linux without speech-dispatcher, and in headless
      // Chrome). Report it instead of racing through the queue firing an error
      // per verse and ending silently, which looks like the button did nothing.
      if (!startedRef.current) {
        setError('No speech voice is available in this browser.')
        stop()
        return
      }
      if (!stoppedRef.current) speakAt(indexRef.current + 1)
    }

    try {
      synth.speak(u)
    } catch {
      stop()
    }
  }, [setPosition, stop])

  const start = useCallback((items, opts = {}) => {
    if (!synth || !items?.length) return
    try { synth.cancel() } catch { /* nothing queued */ }

    queueRef.current = items
    optsRef.current = {
      voice: opts.voice ?? null,
      rate: Number(opts.rate) || 0.95,
      pitch: Number(opts.pitch) || 1.0,
    }
    stoppedRef.current = false
    startedRef.current = false
    setError(null)
    setSpeaking(true)
    setPaused(false)

    // Chrome suspends synthesis if the tab is backgrounded or after long runs;
    // a periodic resume while speaking keeps a long chapter going.
    clearKeepAlive()
    keepAliveRef.current = setInterval(() => {
      if (!stoppedRef.current && synth.speaking && !synth.paused) {
        try { synth.resume() } catch { /* ignore */ }
      }
    }, 8000)

    speakAt(opts.startIndex ?? 0)
  }, [speakAt])

  const pause = useCallback(() => {
    if (!synth || !synth.speaking) return
    try { synth.pause(); setPaused(true) } catch { /* ignore */ }
  }, [])

  const resume = useCallback(() => {
    if (!synth) return
    try { synth.resume(); setPaused(false) } catch { /* ignore */ }
  }, [])

  const skip = useCallback((delta) => {
    if (stoppedRef.current) return
    const next = Math.max(0, Math.min(queueRef.current.length - 1, indexRef.current + delta))
    try { synth.cancel() } catch { /* ignore */ }
    // cancel() fires onend for the current utterance; speak on the next tick so
    // the cancelled utterance's handler cannot advance past our target.
    setTimeout(() => speakAt(next), 0)
  }, [speakAt])

  // Speaking must not outlive the page.
  useEffect(() => () => {
    stoppedRef.current = true
    clearKeepAlive()
    try { synth?.cancel() } catch { /* ignore */ }
  }, [])

  return {
    supported: narrationSupported,
    voices, speaking, paused, index, error,
    start, stop, pause, resume, skip,
  }
}

/**
 * Pick sensible default voices, preferring natural-sounding English ones.
 * Browsers expose wildly different lists, so this only reorders — it never
 * hides anything the user might prefer.
 */
export function rankVoices(voices) {
  const preferred = /(natural|neural|enhanced|premium|siri|google|samantha|daniel|serena)/i
  return [...voices]
    .filter((v) => /^en(-|_|$)/i.test(v.lang))
    .sort((a, b) => {
      const score = (v) => (preferred.test(v.name) ? 1 : 0) + (v.localService ? 0 : 0.5)
      return score(b) - score(a) || a.name.localeCompare(b.name)
    })
}

/** Split an assistant reply into utterance-sized chunks for narration. */
export function chunkText(text, max = 220) {
  const sentences = String(text || '').replace(/\s+/g, ' ').match(/[^.!?]+[.!?]*/g) || []
  const out = []
  let buf = ''
  for (const s of sentences) {
    if ((buf + s).length > max && buf) {
      out.push({ text: buf.trim() })
      buf = ''
    }
    buf += s
  }
  if (buf.trim()) out.push({ text: buf.trim() })
  return out
}
