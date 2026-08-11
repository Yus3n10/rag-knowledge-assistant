import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const askResponse = {
  answer: 'See [1910.147(e)(3)] for details.',
  citations: ['1910.147(e)(3)'],
  citation_report: { valid: ['1910.147(e)(3)'], not_retrieved: [], not_in_corpus: [] },
  ungrounded_numbers: [],
  retrieved: [
    {
      paragraph_id: '1910.147(e)(3)',
      distance: 0.166,
      heading_trail: '1910.147 > Release from lockout or tagout.',
      text: 'Each lockout or tagout device shall be removed by the employee who applied it.',
    },
  ],
  stats: { prompt_tokens: 10, completion_tokens: 5, latency_s: 8.2 },
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}


/** Routes by URL instead of call order. A sequence-based mock silently
 * mis-assigns responses the moment a component adds a request -- which is how
 * the corpus fetch broke every ask test at once. */
function routedFetch(routes: { login?: Response | Promise<Response> | Error; ask?: Response | Promise<Response> | Error }) {
  return vi.fn((url: string) => {
    if (String(url).includes('/corpus')) {
      return Promise.resolve(jsonResponse(200, { total: 0, paragraphs: [] }))
    }
    const hit = String(url).includes('/auth/login') ? routes.login : routes.ask
    if (hit instanceof Error) return Promise.reject(hit)
    return Promise.resolve(hit)
  })
}

const okLogin = () => jsonResponse(200, { access_token: 'tok123', token_type: 'bearer' })

function login(username = 'officer', password = 'officer-pass') {
  fireEvent.change(screen.getByLabelText(/username/i), { target: { value: username } })
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: /log in/i }))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('App', () => {
  it('successful login stores the token and shows the ask view', async () => {
    vi.stubGlobal('fetch', routedFetch({ login: okLogin() }))
    render(<App />)

    login()

    expect(await screen.findByText(/officer/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask/i })).toBeInTheDocument()
  })

  it('bad credentials show an error and stay on login', async () => {
    vi.stubGlobal('fetch', routedFetch({ login: jsonResponse(401, { detail: 'invalid username or password' }) }))
    render(<App />)

    login('viewer', 'wrong-pass')

    expect(await screen.findByText(/invalid username or password/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
  })

  it('a successful ask renders the answer', async () => {
    vi.stubGlobal('fetch', routedFetch({ login: okLogin(), ask: jsonResponse(200, askResponse) }))
    render(<App />)

    login()
    await screen.findByRole('button', { name: /ask/i })

    fireEvent.change(screen.getByLabelText(/ask about/i), { target: { value: 'Who may remove a lockout device?' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/See/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '[1910.147(e)(3)]' })).toBeInTheDocument()
  })

  it('shows a pending state while the ask request is in flight', async () => {
    let resolveAsk: (r: Response) => void = () => {}
    const askPromise = new Promise<Response>((resolve) => {
      resolveAsk = resolve
    })
    vi.stubGlobal('fetch', routedFetch({ login: okLogin(), ask: askPromise }))
    render(<App />)

    login()
    await screen.findByRole('button', { name: /ask/i })

    fireEvent.change(screen.getByLabelText(/ask about/i), { target: { value: 'Who may remove a lockout device?' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/searching 965 paragraphs/i)).toBeInTheDocument()

    resolveAsk(jsonResponse(200, askResponse))
    await waitFor(() => expect(screen.queryByText(/searching 965 paragraphs/i)).not.toBeInTheDocument())
  })

  it('a 401 on ask returns to login', async () => {
    vi.stubGlobal('fetch', routedFetch({ login: okLogin(), ask: jsonResponse(401, { detail: 'invalid or expired token' }) }))
    render(<App />)

    login()
    await screen.findByRole('button', { name: /ask/i })

    fireEvent.change(screen.getByLabelText(/ask about/i), { target: { value: 'Who may remove a lockout device?' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByLabelText(/username/i)).toBeInTheDocument()
  })

  it('a network error on ask shows a visible message, not a silent no-op', async () => {
    vi.stubGlobal('fetch', routedFetch({ login: okLogin(), ask: new TypeError('Failed to fetch') }))
    render(<App />)

    login()
    await screen.findByRole('button', { name: /ask/i })

    fireEvent.change(screen.getByLabelText(/ask about/i), { target: { value: 'Who may remove a lockout device?' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/failed to fetch|network/i)
  })
})
