import React from 'react'

/**
 * Transport controls for narration.
 *
 * Deliberately quiet: it sits inline above the text rather than floating over
 * it, because this is a reading surface and a persistent overlay would compete
 * with the passage.
 */
export default function NarratorBar({
  supported, speaking, paused, position, total, error,
  onPlay, onPause, onResume, onStop, onSkip,
}) {
  if (!supported) {
    return (
      <div className="narrator unsupported">
        Narration needs the Web Speech API, which this browser does not provide.
      </div>
    )
  }

  if (error) {
    return <div className="narrator unsupported">{error}</div>
  }

  return (
    <div className={`narrator ${speaking ? 'on' : ''}`}>
      {!speaking ? (
        <button className="btn" onClick={onPlay} title="Read this passage aloud">
          ▶ Listen
        </button>
      ) : (
        <>
          <button className="icon-btn" onClick={() => onSkip(-1)} title="Previous verse">⏮</button>
          {paused
            ? <button className="icon-btn" onClick={onResume} title="Resume">▶</button>
            : <button className="icon-btn" onClick={onPause} title="Pause">⏸</button>}
          <button className="icon-btn" onClick={() => onSkip(1)} title="Next verse">⏭</button>
          <button className="icon-btn" onClick={onStop} title="Stop">■</button>
          <span className="narrator-pos">
            verse {position + 1} of {total}
          </span>
          <div className="narrator-track">
            <div className="narrator-fill"
                 style={{ width: `${total ? ((position + 1) / total) * 100 : 0}%` }} />
          </div>
        </>
      )}
    </div>
  )
}
