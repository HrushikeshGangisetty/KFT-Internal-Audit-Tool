const TOKEN_KEY = 'fcops.tokens'

export function getTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKEN_KEY) || 'null')
  } catch {
    return null
  }
}

export function setTokens(tokens) {
  if (tokens) localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens))
  else localStorage.removeItem(TOKEN_KEY)
}

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

async function refreshAccess() {
  const tokens = getTokens()
  if (!tokens?.refresh) return null
  const response = await fetch('/api/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: tokens.refresh }),
  })
  if (!response.ok) {
    setTokens(null)
    return null
  }
  const data = await response.json()
  const next = { ...tokens, access: data.access }
  setTokens(next)
  return next.access
}

export async function api(path, { method = 'GET', body, params, isForm } = {}) {
  const url = new URL(path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
  }

  const send = async (accessToken) => {
    const headers = {}
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`
    if (body && !isForm) headers['Content-Type'] = 'application/json'
    return fetch(url.toString().replace(window.location.origin, ''), {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    })
  }

  let response = await send(getTokens()?.access)
  if (response.status === 401) {
    const access = await refreshAccess()
    if (access) response = await send(access)
  }

  const text = await response.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }
  if (!response.ok) {
    throw new ApiError(messageFrom(payload, response.status), response.status, payload)
  }
  return payload
}

export async function login(username, password) {
  const response = await fetch('/api/auth/token/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) throw new ApiError('Incorrect username or password.', response.status)
  const tokens = await response.json()
  setTokens(tokens)
  return api('/api/users/me/')
}

export const listOf = (payload) => (Array.isArray(payload) ? payload : payload?.results ?? [])
