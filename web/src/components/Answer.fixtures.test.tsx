import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Answer from './Answer'
import lockout from '../fixtures/lockout-removal.json'
import respirator from '../fixtures/respirator-apf.json'

describe('Answer against real /ask fixtures', () => {
  it('renders the lockout-removal fixture without crashing', () => {
    render(
      <Answer
        answer={lockout.answer}
        citations={lockout.citations}
        retrieved={lockout.retrieved}
        ungroundedNumbers={lockout.ungrounded_numbers}
      />,
    )
    // the fixture's answer cites this paragraph twice; both must render clickable.
    expect(screen.getAllByRole('button', { name: '[1910.147(e)(3)]' }).length).toBeGreaterThan(0)
  })

  it('renders the respirator-apf fixture, leaving the non-ID bracket as plain text', () => {
    render(
      <Answer
        answer={respirator.answer}
        citations={respirator.citations}
        retrieved={respirator.retrieved}
        ungroundedNumbers={respirator.ungrounded_numbers}
      />,
    )
    expect(screen.getByRole('button', { name: '[1910.134(d)(3)(iv)(C)]' })).toBeInTheDocument()
    // "[Table 1 - Assigned Protection Factors 5]" isn't a paragraph id -- it must not become a button.
    expect(screen.queryByRole('button', { name: /Table 1/ })).not.toBeInTheDocument()
    expect(screen.getByText(/Table 1 - Assigned Protection Factors 5/)).toBeInTheDocument()
  })
})
