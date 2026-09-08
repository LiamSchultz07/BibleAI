import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { rankVoices } from '../lib/narrator'

/** Sign in / create account. */
export function AuthPanel({ onAuthed, onClose }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const fn = mode === 'login' ? api.login : api.register
      const payload = mode === 'login'
        ? { email, password }
        : { email, password, display_name: name }
      const res = await fn(payload)
      onAuthed(res.token, res.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{mode === 'login' ? 'Sign in' : 'Create an account'}</h3>
        <p className="modal-sub">
          An account saves your notes, highlights and conversations. Reading and
          asking questions work without one.
        </p>
        <form onSubmit={submit}>
          {mode === 'register' && (
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)}
                     placeholder="What should we call you?" autoComplete="name" />
            </label>
          )}
          <label>
            Email
            <input type="email" required value={email} autoComplete="email"
                   onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Password
            <input type="password" required value={password}
                   autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
          {mode === 'register' && (
            <div className="hint">At least 10 characters.</div>
          )}
          {error && <div className="err">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn linkish"
                    onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}>
              {mode === 'login' ? 'Create an account' : 'I already have an account'}
            </button>
            <button className="btn primary" disabled={busy}>
              {busy ? '…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const VISIBILITY = [
  ['never', 'Never', 'Your notes stay a reading feature and are never sent to the model.'],
  ['on_request', 'When I ask', 'Included only when you ask about them — “what did I write here?”'],
  ['always', 'Always', 'Included whenever you are studying a passage you have written about.'],
]

/** Settings: notes privacy and narrator voice. */
export function SettingsPanel({ user, voices, onSave, onClose }) {
  const s = user?.settings || {}
  const [visibility, setVisibility] = useState(s.notes_visibility || 'on_request')
  const [voice, setVoice] = useState(s.narrator_voice || '')
  const [rate, setRate] = useState(s.narrator_rate ?? 0.95)
  const [busy, setBusy] = useState(false)
  const ranked = rankVoices(voices)

  async function save() {
    setBusy(true)
    try {
      const res = await api.updateSettings({
        notes_visibility: visibility,
        narrator_voice: voice,
        narrator_rate: Number(rate),
      })
      onSave(res.settings)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <h3>Settings</h3>

        <div className="setting-group">
          <div className="setting-title">Can the assistant read your notes?</div>
          <p className="modal-sub">
            Notes on scripture often hold things you would not say out loud. When
            included, they are sent to the model provider as part of your question.
          </p>
          {VISIBILITY.map(([value, label, desc]) => (
            <label className="radio" key={value}>
              <input type="radio" name="vis" value={value}
                     checked={visibility === value}
                     onChange={() => setVisibility(value)} />
              <span>
                <strong>{label}</strong>
                <span className="radio-desc">{desc}</span>
              </span>
            </label>
          ))}
        </div>

        <div className="setting-group">
          <div className="setting-title">Narrator</div>
          <label>
            Voice
            <select value={voice} onChange={(e) => setVoice(e.target.value)}>
              <option value="">System default</option>
              {ranked.map((v) => (
                <option key={v.name} value={v.name}>{v.name} ({v.lang})</option>
              ))}
            </select>
          </label>
          <label>
            Speed — {Number(rate).toFixed(2)}×
            <input type="range" min="0.6" max="1.6" step="0.05" value={rate}
                   onChange={(e) => setRate(e.target.value)} />
          </label>
        </div>

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={busy}>Save</button>
        </div>
      </div>
    </div>
  )
}

/** Saved notes, bookmarks, conversations and reading history. */
export function LibraryPanel({ onNavigate, onOpenConversation, onClose }) {
  const [tab, setTab] = useState('notes')
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    const fetcher = {
      notes: () => api.notes(q),
      bookmarks: api.bookmarks,
      conversations: api.conversations,
      history: api.history,
    }[tab]
    fetcher().then((d) => { if (alive) { setData(d); setLoading(false) } })
             .catch(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [tab, q])

  const TABS = [
    ['notes', 'Notes'], ['bookmarks', 'Bookmarks'],
    ['conversations', 'Conversations'], ['history', 'History'],
  ]

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide tall" onClick={(e) => e.stopPropagation()}>
        <div className="tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={`tab ${tab === id ? 'on' : ''}`}
                    onClick={() => setTab(id)}>{label}</button>
          ))}
          <button className="btn linkish close" onClick={onClose}>Close</button>
        </div>

        {tab === 'notes' && (
          <input className="lib-search" value={q} placeholder="Search your notes…"
                 onChange={(e) => setQ(e.target.value)} />
        )}

        <div className="lib-body">
          {loading && <span className="dots">Loading</span>}

          {!loading && tab === 'notes' && (
            (data.notes || []).length
              ? data.notes.map((n) => (
                  <button className="lib-item" key={n.id}
                          onClick={() => { onNavigate(n.ref); onClose() }}>
                    <div className="lib-ref">{n.ref}</div>
                    <div className="lib-text">{n.body}</div>
                  </button>
                ))
              : <div className="empty">No notes yet. Open a passage and write one.</div>
          )}

          {!loading && tab === 'bookmarks' && (
            (data.bookmarks || []).length
              ? data.bookmarks.map((b) => (
                  <button className="lib-item" key={b.id}
                          onClick={() => { onNavigate(b.ref); onClose() }}>
                    <div className="lib-ref">{b.ref}</div>
                    {b.label && <div className="lib-text">{b.label}</div>}
                  </button>
                ))
              : <div className="empty">Nothing bookmarked yet.</div>
          )}

          {!loading && tab === 'conversations' && (
            (data.conversations || []).length
              ? data.conversations.map((c) => (
                  <button className="lib-item" key={c.id}
                          onClick={() => { onOpenConversation(c); onClose() }}>
                    <div className="lib-ref">{c.anchor || 'No passage'}</div>
                    <div className="lib-text">{c.title}</div>
                    <div className="lib-meta">{c.message_count} messages</div>
                  </button>
                ))
              : <div className="empty">No saved conversations yet.</div>
          )}

          {!loading && tab === 'history' && (
            (data.history || []).length
              ? data.history.map((h) => (
                  <button className="lib-item" key={h.id}
                          onClick={() => { onNavigate(h.ref); onClose() }}>
                    <div className="lib-ref">{h.ref}</div>
                    <div className="lib-meta">{h.translation}</div>
                  </button>
                ))
              : <div className="empty">Nothing read yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}
