import { useEffect, useMemo, useState } from 'react'

import { fetchCorpus } from '../api'
import type { CorpusParagraph } from '../types'
import './corpusmap.css'

interface CorpusMapProps {
  /** Paragraph ids pulled into context for the current question. */
  retrieved?: string[]
  /** Of those, the ones the answer actually cited. */
  cited?: string[]
}

/** Every indexed paragraph as one cell, in document order, grouped by subpart.
 *
 * This is the one place the system's scale is legible: a question lights ten
 * cells out of 937, in their real position in the code. It is the retrieval
 * step made visible rather than described, and it doubles as an honest
 * statement of scope -- three bands, not the whole CFR. */
function CorpusMap({ retrieved = [], cited = [] }: CorpusMapProps) {
  const [paragraphs, setParagraphs] = useState<CorpusParagraph[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchCorpus()
      .then((data) => !cancelled && setParagraphs(data.paragraphs))
      // A decorative-but-informative panel must never take the page down with
      // it: on failure it simply does not render.
      .catch(() => !cancelled && setFailed(true))
    return () => { cancelled = true }
  }, [])

  const retrievedSet = useMemo(() => new Set(retrieved), [retrieved])
  const citedSet = useMemo(() => new Set(cited), [cited])

  const bands = useMemo(() => {
    if (!paragraphs) return []
    const bySubpart = new Map<string, CorpusParagraph[]>()
    for (const p of paragraphs) {
      const list = bySubpart.get(p.subpart) ?? []
      list.push(p)
      bySubpart.set(p.subpart, list)
    }
    return [...bySubpart.entries()]
  }, [paragraphs])

  // Announce the count rather than 937 individual cells to a screen reader.
  const summary = retrieved.length
    ? `${retrieved.length} of ${paragraphs?.length ?? 0} paragraphs retrieved, ${cited.length} cited`
    : `${paragraphs?.length ?? 0} paragraphs indexed`

  if (failed || !paragraphs) return null

  return (
    <section className="corpusmap" aria-label={summary}>
      <p className="corpusmap-head">
        <span className="eyebrow">Corpus</span>
        <span className="corpusmap-legend">
          <span className="key key-cited" /> cited
          <span className="key key-retrieved" /> retrieved
          <span className="key key-idle" /> indexed
        </span>
      </p>

      <div className="corpusmap-bands" aria-hidden="true">
        {bands.map(([subpart, items]) => (
          <div className="band" key={subpart}>
            {/* "Subpart I" clips at this width; the letter alone is the
                part that identifies it and stays legible. */}
            <span className="band-label" title={subpart}>
              {subpart.replace(/^Subpart\s+/, '')}
            </span>
            <div className="band-cells">
              {items.map((p) => {
                const isCited = citedSet.has(p.id)
                const isRetrieved = retrievedSet.has(p.id)
                return (
                  <span
                    key={p.id}
                    title={p.id}
                    className={
                      'cell' +
                      (isCited ? ' cell-cited' : isRetrieved ? ' cell-retrieved' : '')
                    }
                  />
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default CorpusMap
