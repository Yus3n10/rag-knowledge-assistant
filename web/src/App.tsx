import { useState, type FormEvent } from 'react'

import { ApiError, ask, login as loginRequest } from './api'
import type { AskResponse } from './types'
import Answer from './components/Answer'
import './App.css'

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
      <main className="gate">
        <h1 className="gate-title">OSHA 29 CFR 1910</h1>
        <p className="gate-sub">
          Answers about general industry standards, with every claim traced back to the
          paragraph it came from.
        </p>
        <form onSubmit={handleLogin}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" autoComplete="username" />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" />
          </div>
          <button type="submit" className="gate-submit" disabled={loginPending}>
            {loginPending ? 'Logging in...' : 'Log in'}
          </button>
        </form>
        {loginError && <div className="failure" role="alert">{loginError}</div>}

        <div className="demo-keys">
          Two demo roles. The safety officer additionally sees lockout/tagout
          (<code>1910.147</code>); the viewer is refused it.
          <dl>
            <dt>viewer</dt>
            <dd>viewer-pass</dd>
            <dt>officer</dt>
            <dd>officer-pass</dd>
          </dl>
        </div>
      </main>
    )
  }

  return (
    <>
      <header className="masthead">
        <span className="masthead-mark">29 CFR 1910</span>
        <h1 className="masthead-title">Compliance reference</h1>
        <span className="masthead-spacer" />
        <span className="masthead-role">{username}</span>
        <button type="button" className="signout" onClick={() => returnToLogin(null)}>
          Sign out
        </button>
      </header>

      <main className="shell">
        <form onSubmit={handleAsk}>
          <label className="ask-label" htmlFor="question">
            Ask about 29 CFR 1910
          </label>
          <div className="ask-row">
            <input
              id="question"
              name="question"
              className="ask-input"
              placeholder="What training must an employer provide for PPE?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button type="submit" className="ask-submit" disabled={askPending}>
              Ask
            </button>
          </div>
          <p className="scope">
            Indexed: Subparts D and I, and <code>1910.147</code> lockout/tagout. 965 paragraphs.
            Questions outside that scope are declined rather than guessed at.
          </p>
        </form>

        {askPending && (
          <p className="pending" role="status">
            <span className="pending-pulse" aria-hidden="true" />
            Retrieving and generating -- this takes a few seconds. The first
            request after a quiet period also has to wake the server, which
            adds about a minute.
          </p>
        )}
        {askError && <div className="failure" role="alert">{askError}</div>}

        {!result && !askPending && !askError && (
          <p className="empty">
            Ask a question to see an answer with its sources. Every bracketed paragraph id
            opens the exact regulation text behind that claim, so you can check it rather
            than trust it.
          </p>
        )}

        {result && (
          <Answer
            answer={result.answer}
            citations={result.citations}
            retrieved={result.retrieved}
            ungroundedNumbers={result.ungrounded_numbers}
          />
        )}
      </main>
    </>
  )
}

export default App
