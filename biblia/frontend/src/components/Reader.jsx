import React, { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { HIGHLIGHT_COLORS } from '../lib/constants'

function Dispute({ item }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="dispute">
      <button className="dispute-head" onClick={() => setOpen(!open)}>
        <span className="dispute-tag">Disputed</span>
        <span className="dispute-topic">{item.topic}</span>
        <span className="dispute-caret">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="dispute-body">
          <div className="dispute-q">{item.question}</div>
          {Object.entries(item.positions).map(([tradition, position]) => (
            <div className="position" key={tradition}>
              <div className="position-name">{tradition}</div>
              <div className="position-text">{position}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function NoteEditor({ initial = '', refLabel, onSave, onCancel, onDelete }) {
  const [body, setBody] = useState(initial)
  const ref = useRef(null)
  useEffect(() => { ref.current?.focus() }, [])
  return (
    <div className="note-editor">
      <div className="note-ref">Note on {refLabel}</div>
      <textarea ref={ref} value={body} rows={5}
                placeholder="What are you seeing here?"
                onChange={(e) => setBody(e.target.value)} />
      <div className="note-actions">
        {onDelete && (
          <button className="btn linkish danger" onClick={onDelete}>Delete</button>
        )}
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className="btn primary" disabled={!body.trim()}
                onClick={() => onSave(body)}>Save note</button>
      </div>
    </div>
  )
}

export default function Reader({
  passage, loading, error, onNavigate, searchResults,
  signedIn, onRequireAuth, onChanged,
  narratingVid, onNarrate, narratorBar,
}) {
  const [selected, setSelected] = useState(null)   // {start, end, ref}
  const [editingNote, setEditingNote] = useState(null)
  const verseRefs = useRef({})

  useEffect(() => { setSelected(null); setEditingNote(null) }, [passage?.ref])

  // Keep the verse being read in view.
  useEffect(() => {
    if (narratingVid == null) return
    verseRefs.current[narratingVid]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [narratingVid])

  if (loading) return <div className="pane reader"><span className="dots">Loading</span></div>
  if (error) return <div className="pane reader"><div className="err">{error}</div></div>

  if (searchResults) {
    return (
      <div className="pane reader">
        <div className="section-label">
          {searchResults.results.length} results for “{searchResults.query}”
        </div>
        <div className="results">
          {searchResults.results.map((r) => (
            <button className="result" key={r.ref} onClick={() => onNavigate(r.ref)}>
              <div>
                <span className="result-ref">{r.ref}</span>
                <span className="result-title">{r.title}</span>
              </div>
              <div className="result-preview">{r.preview}…</div>
            </button>
          ))}
          {!searchResults.results.length && (
            <div className="empty">Nothing matched. Try a reference, or different wording.</div>
          )}
        </div>
      </div>
    )
  }

  if (!passage) {
    return (
      <div className="pane reader">
        <div className="empty">
          <h3>Open a passage</h3>
          <p>Type a reference above — <em>Romans 8:28</em>, <em>Psalm 23</em>,
          <em> 1 Cor 13</em> — or search for a phrase or theme.</p>
        </div>
      </div>
    )
  }

  const comparisons = Object.entries(passage.comparisons || {})
  const highlightByVid = {}
  for (const h of passage.highlights || []) {
    for (let v = h.start_vid; v <= h.end_vid; v++) highlightByVid[v] = h
  }

  function requireAuth(fn) {
    return signedIn ? fn() : onRequireAuth()
  }

  function selectVerse(v, e) {
    if (e.shiftKey && selected) {
      const start = Math.min(selected.start, v.vid)
      const end = Math.max(selected.end, v.vid)
      setSelected({ start, end, ref: refFor(start, end) })
    } else {
      setSelected(selected?.start === v.vid && selected?.end === v.vid
        ? null
        : { start: v.vid, end: v.vid, ref: `${passage.book_name} ${v.chapter}:${v.verse}` })
    }
    setEditingNote(null)
  }

  function refFor(start, end) {
    const s = passage.verses.find((v) => v.vid === start)
    const e = passage.verses.find((v) => v.vid === end)
    if (!s || !e) return passage.ref
    return s.vid === e.vid
      ? `${passage.book_name} ${s.chapter}:${s.verse}`
      : `${passage.book_name} ${s.chapter}:${s.verse}-${e.chapter === s.chapter ? e.verse : `${e.chapter}:${e.verse}`}`
  }

  async function highlight(color) {
    await requireAuth(async () => {
      await api.createHighlight(selected.ref, color)
      setSelected(null)
      onChanged()
    })
  }

  async function removeHighlight(id) {
    await api.deleteHighlight(id)
    onChanged()
  }

  async function saveNote(body) {
    if (editingNote?.id) await api.updateNote(editingNote.id, body)
    else await api.createNote(editingNote.ref, body)
    setEditingNote(null)
    setSelected(null)
    onChanged()
  }

  async function toggleBookmark() {
    await requireAuth(async () => {
      await api.toggleBookmark(passage.ref)
      onChanged()
    })
  }

  return (
    <div className="pane reader">
      <div className="passage-head">
        <div className="passage-head-row">
          <h2 className="passage-ref">{passage.ref}</h2>
          <div className="passage-tools">
            <button className={`icon-btn ${passage.bookmarked ? 'on' : ''}`}
                    title={passage.bookmarked ? 'Remove bookmark' : 'Bookmark this passage'}
                    onClick={toggleBookmark}>
              {passage.bookmarked ? '★' : '☆'}
            </button>
          </div>
        </div>
        {passage.title && <div className="passage-title">{passage.title}</div>}
        <div className="passage-meta">{passage.translation} · {passage.genre}</div>
      </div>

      {narratorBar}

      <div className="verses">
        {passage.verses.map((v) => {
          const hl = highlightByVid[v.vid]
          const isSelected = selected && v.vid >= selected.start && v.vid <= selected.end
          return (
            <span
              key={v.vid}
              ref={(el) => { verseRefs.current[v.vid] = el }}
              className={[
                'verse',
                hl ? `hl hl-${hl.color}` : '',
                isSelected ? 'selected' : '',
                narratingVid === v.vid ? 'narrating' : '',
              ].join(' ').trim()}
              onClick={(e) => selectVerse(v, e)}
            >
              <span className="vnum">{v.verse}</span>
              {v.text}
            </span>
          )
        })}
      </div>

      {selected && !editingNote && (
        <div className="verse-actions">
          <span className="verse-actions-ref">{selected.ref}</span>
          <div className="swatches">
            {HIGHLIGHT_COLORS.map((c) => (
              <button key={c} className={`swatch sw-${c}`} title={`Highlight ${c}`}
                      onClick={() => highlight(c)} />
            ))}
          </div>
          <button className="btn" onClick={() =>
            requireAuth(() => setEditingNote({ ref: selected.ref, body: '' }))}>
            Add note
          </button>
          <button className="btn" onClick={() => onNarrate(selected.start)}>
            Read from here
          </button>
          <button className="btn linkish" onClick={() => setSelected(null)}>Done</button>
        </div>
      )}

      {editingNote && (
        <NoteEditor
          initial={editingNote.body}
          refLabel={editingNote.ref}
          onSave={saveNote}
          onCancel={() => setEditingNote(null)}
          onDelete={editingNote.id ? async () => {
            await api.deleteNote(editingNote.id)
            setEditingNote(null)
            onChanged()
          } : null}
        />
      )}

      {(passage.notes || []).length > 0 && (
        <>
          <div className="section-label">Your notes</div>
          {passage.notes.map((n) => (
            <div className="note-card" key={n.id}>
              <div className="note-card-head">
                <span className="note-card-ref">{n.ref}</span>
                <button className="btn linkish"
                        onClick={() => setEditingNote({ id: n.id, ref: n.ref, body: n.body })}>
                  Edit
                </button>
              </div>
              <div className="note-card-body">{n.body}</div>
            </div>
          ))}
        </>
      )}

      {(passage.highlights || []).length > 0 && (
        <>
          <div className="section-label">Highlights</div>
          <div className="chips">
            {passage.highlights.map((h) => (
              <button className={`chip hl-chip sw-${h.color}`} key={h.id}
                      title="Remove highlight"
                      onClick={() => removeHighlight(h.id)}>
                {h.ref} ✕
              </button>
            ))}
          </div>
        </>
      )}

      {comparisons.length > 0 && (
        <div className="compare-block">
          <div className="section-label">Other translations</div>
          {comparisons.map(([abbrev, verses]) =>
            verses.length ? (
              <div key={abbrev} style={{ marginBottom: 14 }}>
                <h4>{abbrev}</h4>
                <div className="compare-text">
                  {verses.map((v) => (
                    <span key={v.vid}>
                      <span className="vnum">{v.verse}</span>{v.text}{' '}
                    </span>
                  ))}
                </div>
              </div>
            ) : null
          )}
        </div>
      )}

      {passage.contested?.length > 0 &&
        passage.contested.map((c) => <Dispute item={c} key={c.topic} />)}

      {passage.cross_refs?.length > 0 && (
        <>
          <div className="section-label">Cross-references</div>
          <div className="chips">
            {passage.cross_refs.map((x) => (
              <button className="chip" key={x.ref} onClick={() => onNavigate(x.ref)}>
                {x.ref}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
