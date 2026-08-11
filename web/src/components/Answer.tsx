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
  // The model writes markdown lists. Rendering the source verbatim would show
  // literal asterisks, so promote just the list bullet -- not a markdown
  // parser, which would be a dependency for one character.
  const segments = splitAnswer(answer.replace(/^[ \t]*\* /gm, '• '))
  const uncited = retrieved.filter((r) => !citations.includes(r.paragraph_id))

  return (
    <div className="answer answer-section">
      <p className="answer-meta">
        <span>Answer</span>
        <span>
          {citations.length} cited &middot; {retrieved.length} retrieved
        </span>
      </p>

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
        <div className="failure ungrounded-warning" role="alert">
          These numbers appear in the answer but in none of the retrieved source text:{' '}
          {ungroundedNumbers.join(', ')}. Check them against the regulation before relying
          on them.
        </div>
      )}

      {uncited.length > 0 && (
        <div className="retrieved-uncited">
          <h3>Retrieved but not cited</h3>
          <p>
            Paragraphs the search pulled into context that the answer never referenced.
            When a claim is attributed to the wrong paragraph, the right one is usually here.
          </p>
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
