import type { RetrievedEntry } from '../types'
import { splitAnswer } from '../citations'
import Citation from './Citation'
import './citation.css'

interface AnswerProps {
  answer: string
  citations: string[]
  retrieved: RetrievedEntry[]
  ungroundedNumbers: string[]
}

/** Renders an /ask answer with inline clickable citations, a warning for
 * ungrounded numbers, and the retrieved-but-uncited paragraphs it did not
 * reference. */
function Answer({ answer, citations, retrieved, ungroundedNumbers }: AnswerProps) {
  const byId = new Map(retrieved.map((r) => [r.paragraph_id, r]))
  const segments = splitAnswer(answer)
  const uncited = retrieved.filter((r) => !citations.includes(r.paragraph_id))

  return (
    <div className="answer">
      <p className="answer-text">
        {segments.map((seg, i) =>
          seg.type === 'text' ? (
            <span key={i}>{seg.value}</span>
          ) : (
            <Citation key={i} id={seg.id} entry={byId.get(seg.id)} cited={citations.includes(seg.id)} />
          ),
        )}
      </p>

      {ungroundedNumbers.length > 0 && (
        <div className="ungrounded-warning" role="alert">
          The model stated numbers with no matching source: {ungroundedNumbers.join(', ')}
        </div>
      )}

      {uncited.length > 0 && (
        <div className="retrieved-uncited">
          <h3>Retrieved but not cited</h3>
          <ul>
            {uncited.map((r) => (
              <li key={r.paragraph_id}>
                <Citation id={r.paragraph_id} entry={r} cited={false} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default Answer
