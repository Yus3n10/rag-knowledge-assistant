import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Answer from './Answer'
import type { RetrievedEntry } from '../types'

const retrieved: RetrievedEntry[] = [
  {
    paragraph_id: '1910.147(e)(3)',
    distance: 0.166,
    heading_trail: '1910.147 The control of hazardous energy (lockout/tagout). > Release from lockout or tagout.',
    text: 'Each lockout or tagout device shall be removed from each energy isolating device by the employee who applied the device.',
  },
  {
    paragraph_id: '1910.147(e)(3)(i)',
    distance: 0.164,
    heading_trail: '1910.147 The control of hazardous energy (lockout/tagout). > Release from lockout or tagout.',
    text: 'Verification by the employer that the authorized employee who applied the device is not at the facility;',
  },
]

describe('Answer', () => {
  it('renders without crashing when the answer has zero citations', () => {
    render(<Answer answer="No citations here." citations={[]} retrieved={[]} ungroundedNumbers={[]} />)
    expect(screen.getByText('No citations here.')).toBeInTheDocument()
  })

  it('shows a visible warning when ungroundedNumbers is non-empty', () => {
    render(
      <Answer
        answer="The limit is 50 ppm."
        citations={[]}
        retrieved={[]}
        ungroundedNumbers={['50']}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('50')
  })

  it('does not show a warning when ungroundedNumbers is empty', () => {
    render(<Answer answer="All grounded." citations={[]} retrieved={[]} ungroundedNumbers={[]} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('distinguishes cited paragraphs from merely-retrieved ones', () => {
    render(
      <Answer
        answer="See [1910.147(e)(3)] for details."
        citations={['1910.147(e)(3)']}
        retrieved={retrieved}
        ungroundedNumbers={[]}
      />,
    )
    // cited id appears inline in the answer text
    expect(screen.getByRole('button', { name: '[1910.147(e)(3)]' })).toBeInTheDocument()
    // the uncited retrieved paragraph is listed separately
    expect(screen.getByRole('button', { name: /1910\.147\(e\)\(3\)\(i\)/ })).toBeInTheDocument()
  })
})
