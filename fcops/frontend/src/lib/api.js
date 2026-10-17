// Session-cookie API client (WP2). The session cookie is HttpOnly and never
// touched here; unsafe methods carry the CSRF token in X-CSRFToken.

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

function messageFrom(payload, status) {
  if (!payload) return `Request failed (${status})`
  if (typeof payload === 'string') return payload
  if (payload.detail) {
    return Array.isArray(payload.detail) ? payload.detail.join(' ') : payload.detail
  }
  const parts = []
  for (const [key, value] of Object.entries(payload)) {
    parts.push(`${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
  }
  return parts.join(' · ') || `Request failed (${status})`
}

// Kept in memory only. Django rotates it on login, so it is dropped then.
let csrfToken = null

async function csrf() {
  if (!csrfToken) {
    const response = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
    csrfToken = (await response.json()).csrfToken
  }
  return csrfToken
}

const SAFE = ['GET', 'HEAD', 'OPTIONS']

export async function api(path, { method = 'GET', body, params, isForm, redirectOn401 = true } = {}) {
  const url = new URL(path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
  }
  const headers = {}
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  if (!SAFE.includes(method)) headers['X-CSRFToken'] = await csrf()

  const response = await fetch(url.pathname + url.search, {
    method,
    headers,
    credentials: 'same-origin',
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  })

  const text = await response.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }
  if (response.status === 401 && redirectOn401 && window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
  if (!response.ok) {
    throw new ApiError(messageFrom(payload, response.status), response.status, payload)
  }
  return payload
}

export async function login(username, password) {
  const me = await api('/api/auth/login/', {
    method: 'POST', body: { username, password }, redirectOn401: false,
  })
  csrfToken = null
  return me
}

export async function logout() {
  try {
    await api('/api/auth/logout/', { method: 'POST', redirectOn401: false })
  } finally {
    csrfToken = null
  }
}

export const currentUser = () => api('/api/auth/me/', { redirectOn401: false })

export const listOf = (payload) => (Array.isArray(payload) ? payload : payload?.results ?? [])
