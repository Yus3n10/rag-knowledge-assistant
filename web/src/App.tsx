import { useState, type FormEvent } from 'react'

import { ApiError, ask, login as loginRequest } from './api'
import type { AskResponse } from './types'
import Answer from './components/Answer'

// Token lives in React state only -- not localStorage, not a cookie. It
// disappears on refresh, which is the right tradeoff for a demo: nothing
// persists that a second person opening the same browser could reuse.
function App() {
  const [token, setToken] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loginPending, setLoginPending] = useState(false)

  const [question, setQuestion] = useState('')
  const [askPending, setAskPending] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResponse | null>(null)

  function returnToLogin(message: string | null) {
    setToken(null)
    setResult(null)
    setAskError(null)
    setLoginError(message)
  }

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const enteredUsername = String(form.get('username') ?? '')
    const password = String(form.get('password') ?? '')

    setLoginPending(true)
    setLoginError(null)
    try {
      const res = await loginRequest(enteredUsername, password)
      setToken(res.access_token)
      setUsername(enteredUsername)
    } catch (err) {
      setLoginError(err instanceof ApiError ? err.message : 'Network error -- could not reach the server.')
    } finally {
      setLoginPending(false)
    }
  }

  async function handleAsk(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!token) return

    setAskPending(true)
    setAskError(null)
    try {
      const res = await ask(token, question)
      setResult(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        returnToLogin('Your session expired -- please log in again.')
      } else {
        setAskError(err instanceof Error ? err.message : 'Network error -- could not reach the server.')
      }
    } finally {
      setAskPending(false)
    }
  }

  if (!token) {
    return (
      <main>
        <h1>OSHA RAG Assistant</h1>
        <form onSubmit={handleLogin}>
          <div>
            <label htmlFor="username">Username</label>
            <input id="username" name="username" autoComplete="username" />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" />
          </div>
          <button type="submit" disabled={loginPending}>
            {loginPending ? 'Logging in...' : 'Log in'}
          </button>
        </form>
        {loginError && <div role="alert">{loginError}</div>}
      </main>
    )
  }

  return (
    <main>
      <h1>OSHA RAG Assistant</h1>
      <p>
        Logged in as <strong>{username}</strong>
      </p>

      <form onSubmit={handleAsk}>
        <label htmlFor="question">Question</label>
        <input id="question" name="question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button type="submit" disabled={askPending}>
          Ask
        </button>
      </form>

      {askPending && <p role="status">Retrieving and generating -- this takes a few seconds.</p>}
      {askError && <div role="alert">{askError}</div>}

      {result && (
        <Answer
          answer={result.answer}
          citations={result.citations}
          retrieved={result.retrieved}
          ungroundedNumbers={result.ungrounded_numbers}
        />
      )}
    </main>
  )
}

export default App
