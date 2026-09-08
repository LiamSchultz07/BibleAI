const BASE = '/api'
const TOKEN_KEY = 'biblia.token'

// The session token lives in localStorage so a refresh does not sign you out.
// Every request attaches it when present; the API treats its absence as
// "signed out" rather than as an error, so the whole reading experience works
// either way.
export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private browsing */ }
}

export function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function request(method, path, { params, body } = {}) {
  const qs = new URLSearchParams(
    Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)
  )
  const url = `${BASE}${path}${qs.toString() ? `?${qs}` : ''}`
  const res = await fetch(url, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...authHeaders(),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* non-JSON error body */ }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const get = (path, params) => request('GET', path, { params })

export const api = {
  health: () => get('/health'),
  translations: () => get('/translations'),
  books: () => get('/books'),
  passage: (ref, translation, compare = []) =>
    get('/passage', { ref, translation, compare: compare.join(',') }),
  search: (q, k = 10) => get('/search', { q, k }),
  contestedAll: () => get('/contested/all'),
  session: (id) => get(`/session/${id}`),

  // --- accounts
  register: (body) => request('POST', '/auth/register', { body }),
  login: (body) => request('POST', '/auth/login', { body }),
  me: () => get('/auth/me'),
  updateSettings: (body) => request('PATCH', '/settings', { body }),

  // --- personal study data
  notes: (q = '') => get('/notes', { q }),
  createNote: (ref, body) => request('POST', '/notes', { body: { ref, body } }),
  updateNote: (id, body) => request('PATCH', `/notes/${id}`, { body: { body } }),
  deleteNote: (id) => request('DELETE', `/notes/${id}`),

  highlights: () => get('/highlights'),
  createHighlight: (ref, color) => request('POST', '/highlights', { body: { ref, color } }),
  deleteHighlight: (id) => request('DELETE', `/highlights/${id}`),

  bookmarks: () => get('/bookmarks'),
  toggleBookmark: (ref, label = null) => request('POST', '/bookmarks', { body: { ref, label } }),

  history: () => get('/history'),
  conversations: () => get('/conversations'),
  deleteConversation: (id) => request('DELETE', `/conversations/${id}`),
}

/**
 * Stream a chat turn.
 *
 * The endpoint is a POST, so EventSource is unusable (it is GET-only) and the
 * SSE frames are parsed by hand off the response body. Frames can be split
 * across network chunks, so the buffer is only consumed up to the last
 * complete "\n\n" delimiter.
 */
export async function streamChat(body, { onMeta, onDelta, onError, onDone, signal }) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    let idx
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, idx)
      buf = buf.slice(idx + 2)

      let event = 'message'
      const dataLines = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
      }
      if (!dataLines.length) continue

      let payload
      try { payload = JSON.parse(dataLines.join('\n')) } catch { continue }

      if (event === 'meta') onMeta?.(payload)
      else if (event === 'delta') onDelta?.(payload.text)
      else if (event === 'error') onError?.(payload.error)
      else if (event === 'done') onDone?.()
    }
  }
  onDone?.()
}
