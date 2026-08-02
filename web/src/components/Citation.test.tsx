import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Citation from './Citation'
import type { RetrievedEntry } from '../types'

const entry: RetrievedEntry = {
  paragraph_id: '1910.147(e)(3)',
  distance: 0.166,
  heading_trail: '1910.147 The control of hazardous energy (lockout/tagout). > Release from lockout or tagout.',
  text: 'Each lockout or tagout device shall be removed from each energy isolating device by the employee who applied the device.',
}

describe('Citation', () => {
  it('renders as a clickable element', () => {
    render(<Citation id={entry.paragraph_id} entry={entry} cited />)
    expect(screen.getByRole('button', { name: /1910\.147\(e\)\(3\)/ })).toBeInTheDocument()
  })

  it('reveals the source text on click', () => {
    render(<Citation id={entry.paragraph_id} entry={entry} cited />)
    expect(screen.queryByText(entry.text)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /1910\.147\(e\)\(3\)/ }))

    expect(screen.getByText(entry.text)).toBeInTheDocument()
    expect(screen.getByText(entry.heading_trail)).toBeInTheDocument()
  })

  it('hides the source text again on a second click', () => {
    render(<Citation id={entry.paragraph_id} entry={entry} cited />)
    const button = screen.getByRole('button', { name: /1910\.147\(e\)\(3\)/ })

    fireEvent.click(button)
    expect(screen.getByText(entry.text)).toBeInTheDocument()

    fireEvent.click(button)
    expect(screen.queryByText(entry.text)).not.toBeInTheDocument()
  })

  it('renders as unresolvable, without throwing, when no retrieved entry matches', () => {
    render(<Citation id="1910.999(z)" entry={undefined} cited />)
    const button = screen.getByRole('button', { name: /1910\.999\(z\)/ })

    fireEvent.click(button)

    expect(screen.getByText(/not retrieved/i)).toBeInTheDocument()
  })
})
