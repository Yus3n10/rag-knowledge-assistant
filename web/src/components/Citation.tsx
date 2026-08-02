import { useState } from 'react'

import type { RetrievedEntry } from '../types'
import './citation.css'

interface CitationProps {
  id: string
  entry?: RetrievedEntry
  cited: boolean
}

/** One clickable citation id. Expands inline to show the source paragraph
 * it points at, or a note that no retrieved paragraph matched. */
function Citation({ id, entry, cited }: CitationProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <span className={`citation ${cited ? 'citation-cited' : 'citation-uncited'}`}>
      <button type="button" className="citation-toggle" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
        [{id}]
      </button>
      {expanded && (
        <span className="citation-source">
          {entry ? (
            <>
              <span className="citation-heading">{entry.heading_trail}</span>
              <span className="citation-text">{entry.text}</span>
            </>
          ) : (
            <span className="citation-unresolvable">Source not retrieved for this citation.</span>
          )}
        </span>
      )}
    </span>
  )
}

export default Citation
