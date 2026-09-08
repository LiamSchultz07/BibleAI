import React, { useEffect, useRef, useState } from 'react'
import { api, streamChat } from '../lib/api'
import { chunkText } from '../lib/narrator'

const PROMPTS = [
  'What is Romans 8:28 actually promising?',
  'Why do translations of Romans 9 differ so much?',
  'What does Ecclesiastes mean by “vanity”?',
  'Is the millennium in Revelation 20 literal?',
  'What did “born again” mean to Nicodemus?',
]

export default function Chat({
  translation, compare, anchorRef, onNavigate, llmConfigured,
  signedIn, notesVisibility, resumeSession, onResumed,
  narrator, voice, rate,
}) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [error, setError] = useState(null)
  const endRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  // Reopen a saved conversation from the library.
  useEffect(() => {
    if (!resumeSession) return
    let alive = true
    api.session(resumeSession)
      .then((d) => {
        if (!alive) return
        setSessionId(d.session_id)
        setMessages(d.messages.map((m) => ({
          role: m.role, content: m.content, citations: m.citations,
        })))
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && onResumed?.())
    return () => { alive = false }
  }, [resumeSession, onResumed])

  async function send(text) {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput('')
    setError(null)
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', content: msg }, { role: 'assistant', content: '' }])

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await streamChat(
        {
          message: msg,
          session_id: sessionId,
          translation,
          compare,
          anchor_ref: anchorRef || null,
        },
        {
          signal: ctrl.signal,
          onMeta: (meta) => {
            setSessionId(meta.session_id)
            setMessages((m) => {
              const next = [...m]
              next[next.length - 1] = { ...next[next.length - 1], citations: meta }
              return next
            })
          },
          onDelta: (delta) => {
            setMessages((m) => {
              const next = [...m]
              const last = next[next.length - 1]
              next[next.length - 1] = { ...last, content: last.content + delta }
              return next
            })
          },
          onError: (e) => setError(e),
        }
      )
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setBusy(false)
      abortRef.current = null
    }
  }

  function speak(text) {
    narrator?.start(chunkText(text), { voice, rate })
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function newConversation() {
    narrator?.stop()
    setSessionId(null)
    setMessages([])
    setError(null)
  }

  return (
    <div className="pane chat">
      <div className="messages">
        {!llmConfigured && (
          <div className="notice">
            No model key is configured, so replies show the retrieval layer's raw
            output — the exact evidence a model would receive. Set{' '}
            <code>ANTHROPIC_API_KEY</code> and restart the API to enable conversation.
          </div>
        )}

        {messages.length === 0 && (
          <div className="empty">
            <h3>Ask about the text</h3>
            <p>
              Questions stay attached to the passage you have open, so follow-ups
              like “what does he mean by that?” work without repeating yourself.
            </p>
            <ul>
              {PROMPTS.map((p) => (
                <li key={p} onClick={() => send(p)}>{p}</li>
              ))}
            </ul>
            {signedIn && notesVisibility === 'on_request' && (
              <p className="hint" style={{ marginTop: 16 }}>
                Your notes stay private unless you ask for them — try
                “what did I write about this?”
              </p>
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <div className={`msg ${m.role}`} key={i}>
            <div className="msg-role">
              {m.role === 'user' ? 'You' : 'Biblia'}
              {m.role === 'assistant' && m.content && (
                <button className="btn linkish speak" title="Read this aloud"
                        onClick={() => speak(m.content)}>
                  ▶ listen
                </button>
              )}
            </div>
            <div className="msg-body">
              {m.content}
              {busy && i === messages.length - 1 && !m.content && (
                <span className="dots">Reading</span>
              )}
            </div>
            {m.citations?.used_notes?.length > 0 && (
              <div className="notes-used">
                Used your notes on {m.citations.used_notes.join(', ')}
              </div>
            )}
            {m.citations?.passages?.length > 0 && (
              <div className="msg-cites">
                {m.citations.passages.map((ref) => (
                  <button className="cite" key={ref} onClick={() => onNavigate(ref)}>{ref}</button>
                ))}
                {m.citations.related?.slice(0, 3).map((ref) => (
                  <button className="cite" key={ref} onClick={() => onNavigate(ref)}>{ref}</button>
                ))}
                {m.citations.contested?.length > 0 && (
                  <span className="dispute-tag">· disputed passage</span>
                )}
              </div>
            )}
          </div>
        ))}

        {error && <div className="err">{error}</div>}
        <div ref={endRef} />
      </div>

      <div className="composer">
        {messages.length > 0 && (
          <button className="btn linkish" onClick={newConversation} title="Start fresh">New</button>
        )}
        <textarea
          rows={1}
          value={input}
          placeholder={anchorRef ? `Ask about ${anchorRef}…` : 'Ask about a passage…'}
          onChange={(e) => {
            setInput(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
          }}
          onKeyDown={onKeyDown}
        />
        <button className="btn primary" onClick={() => send()} disabled={busy || !input.trim()}>
          {busy ? '…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
