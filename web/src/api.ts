// Thin fetch wrapper over api/main.py's /auth/login and /ask.

import type { AskResponse } from './types'

const BASE = '/api'

/** Thrown for any non-2xx HTTP response; `status` lets callers distinguish
 * 401 (bad credentials / expired token) from other failures. A rejected
 * fetch (network down, DNS failure, etc.) throws a plain TypeError instead --
 * callers should treat anything that isn't ApiError as a network error. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.detail ?? res.statusText
  } catch {
    return res.statusText || `HTTP ${res.status}`
  }
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return res.json()
}

export async function ask(token: string, question: string): Promise<AskResponse> {
  const res = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return res.json()
}
