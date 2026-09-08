import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken } from './lib/api'
import { useNarrator } from './lib/narrator'
import Reader from './components/Reader'
import Chat from './components/Chat'
import NarratorBar from './components/NarratorBar'
import { AuthPanel, LibraryPanel, SettingsPanel } from './components/Account'

export default function App() {
  const [translations, setTranslations] = useState([])
  const [translation, setTranslation] = useState('BSB')
  const [compareWith, setCompareWith] = useState('')
  const [query, setQuery] = useState('Romans 8:28-30')
  const [passage, setPassage] = useState(null)
  const [searchResults, setSearchResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)

  const [user, setUser] = useState(null)
  const [modal, setModal] = useState(null)  // 'auth' | 'settings' | 'library'
  const [resumeSession, setResumeSession] = useState(null)

  const narrator = useNarrator()

  // Narration queue: one entry per verse of the open passage.
  const queue = useMemo(
    () => (passage?.verses || []).map((v) => ({ text: v.text, vid: v.vid })),
    [passage]
  )
  const narratingVid =
    narrator.speaking && narrator.index >= 0 ? queue[narrator.index]?.vid ?? null : null

  // --- boot
  useEffect(() => {
    api.translations().then((d) => setTranslations(d.translations)).catch(() => {})
    api.health().then(setHealth).catch(() => {})
    if (getToken()) {
      api.me().then((d) => {
        setUser(d.user)
        if (d.user.settings?.default_translation) {
          setTranslation(d.user.settings.default_translation)
        }
      }).catch(() => setToken(null))
    }
    open('Romans 8:28-30')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const open = useCallback(async (ref, t = translation, c = compareWith) => {
    setLoading(true)
    setError(null)
    setSearchResults(null)
    narrator.stop()
    try {
      const data = await api.passage(ref, t, c ? [c] : [])
      setPassage(data)
      setQuery(data.ref)
    } catch (e) {
      setPassage(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translation, compareWith])

  /** Re-fetch the open passage without disturbing narration or scroll. */
  const refresh = useCallback(async () => {
    if (!passage) return
    try {
      const data = await api.passage(passage.ref, translation, compareWith ? [compareWith] : [])
      setPassage(data)
    } catch { /* leave the current view in place */ }
  }, [passage, translation, compareWith])

  async function submit(e) {
    e?.preventDefault()
    const q = query.trim()
    if (!q) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.passage(q, translation, compareWith ? [compareWith] : [])
      setPassage(data)
      setSearchResults(null)
      setQuery(data.ref)
    } catch {
      try {
        const res = await api.search(q, 12)
        setSearchResults(res)
        setPassage(null)
      } catch (e2) {
        setError(e2.message)
      }
    } finally {
      setLoading(false)
    }
  }

  function changeTranslation(t) {
    setTranslation(t)
    if (passage) open(passage.ref, t, compareWith)
  }

  function changeCompare(c) {
    setCompareWith(c)
    if (passage) open(passage.ref, translation, c)
  }

  function onAuthed(token, u) {
    setToken(token)
    setUser(u)
    setModal(null)
    refresh()
  }

  function signOut() {
    setToken(null)
    setUser(null)
    narrator.stop()
    refresh()
  }

  // --- narration
  const voiceObj = useMemo(() => {
    const name = user?.settings?.narrator_voice
    return name ? narrator.voices.find((v) => v.name === name) || null : null
  }, [user, narrator.voices])

  function narrate(fromVid) {
    const startIndex = fromVid ? Math.max(0, queue.findIndex((q) => q.vid === fromVid)) : 0
    narrator.start(queue, {
      startIndex,
      voice: voiceObj,
      rate: user?.settings?.narrator_rate ?? 0.95,
      pitch: user?.settings?.narrator_pitch ?? 1.0,
    })
  }

  const current = translations.find((t) => t.abbrev === translation)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Biblia
          <span>{health?.corpus?.translations ?? '—'} open translations</span>
        </div>

        <form className="refbox" onSubmit={submit}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Reference or search — “Psalm 23”, “fear not”, “grace”"
            spellCheck={false}
          />
          <button className="btn" type="submit">Open</button>
        </form>

        <select value={translation} onChange={(e) => changeTranslation(e.target.value)}>
          {translations.map((t) => (
            <option key={t.abbrev} value={t.abbrev}>{t.abbrev} — {t.name}</option>
          ))}
        </select>

        <select value={compareWith} onChange={(e) => changeCompare(e.target.value)}>
          <option value="">Compare…</option>
          {translations.filter((t) => t.abbrev !== translation).map((t) => (
            <option key={t.abbrev} value={t.abbrev}>vs {t.abbrev}</option>
          ))}
        </select>

        {user ? (
          <div className="account">
            <button className="btn" onClick={() => setModal('library')}>Library</button>
            <button className="btn" onClick={() => setModal('settings')}>Settings</button>
            <button className="btn linkish" onClick={signOut} title={user.email}>
              {user.display_name}
            </button>
          </div>
        ) : (
          <button className="btn primary" onClick={() => setModal('auth')}>Sign in</button>
        )}
      </header>

      {current?.philosophy && (
        <div className="translation-strip">
          <strong>{current.abbrev}</strong> {current.year} · {current.philosophy} · {current.license}
        </div>
      )}

      <div className="panes">
        <Reader
          passage={passage}
          searchResults={searchResults}
          loading={loading}
          error={error}
          onNavigate={(ref) => open(ref)}
          signedIn={!!user}
          onRequireAuth={() => setModal('auth')}
          onChanged={refresh}
          narratingVid={narratingVid}
          onNarrate={narrate}
          narratorBar={passage && (
            <NarratorBar
              supported={narrator.supported}
              speaking={narrator.speaking}
              paused={narrator.paused}
              error={narrator.error}
              position={narrator.index}
              total={queue.length}
              onPlay={() => narrate()}
              onPause={narrator.pause}
              onResume={narrator.resume}
              onStop={narrator.stop}
              onSkip={narrator.skip}
            />
          )}
        />
        <Chat
          translation={translation}
          compare={compareWith ? [compareWith] : []}
          anchorRef={passage?.ref}
          onNavigate={(ref) => open(ref)}
          llmConfigured={health?.llm?.configured ?? true}
          signedIn={!!user}
          notesVisibility={user?.settings?.notes_visibility}
          resumeSession={resumeSession}
          onResumed={() => setResumeSession(null)}
          narrator={narrator}
          voice={voiceObj}
          rate={user?.settings?.narrator_rate ?? 0.95}
        />
      </div>

      {modal === 'auth' && (
        <AuthPanel onAuthed={onAuthed} onClose={() => setModal(null)} />
      )}
      {modal === 'settings' && user && (
        <SettingsPanel
          user={user}
          voices={narrator.voices}
          onSave={(settings) => setUser({ ...user, settings })}
          onClose={() => setModal(null)}
        />
      )}
      {modal === 'library' && user && (
        <LibraryPanel
          onNavigate={(ref) => open(ref)}
          onOpenConversation={(c) => {
            setResumeSession(c.id)
            if (c.anchor) open(c.anchor)
          }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
