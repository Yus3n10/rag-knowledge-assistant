import type { RetrievedEntry } from '../types'
import { splitAnswer } from '../citations'
import Citation from './Citation'
import './citation.css'

interface AnswerProps {
  answer: string
  citations: string[]
  retrieved: RetrievedEntry[]
  ungroundedNumbers: string[]
  refused?: boolean
}

/** Renders an /ask answer with inline clickable citations, a warning for
 * ungrounded numbers, and the retrieved-but-uncited paragraphs it did not
 * reference. */
function Answer({ answer, citations, retrieved, ungroundedNumbers, refused }: AnswerProps) {
  const byId = new Map(retrieved.map((r) => [r.paragraph_id, r]))
  // The model writes markdown lists. Rendering the source verbatim would show
  // literal asterisks, so promote just the list bullet -- not a markdown
  // parser, which would be a dependency for one character.
  const segments = splitAnswer(answer.replace(/^[ \t]*\* /gm, '• '))
  const uncited = retrieved.filter((r) => !citations.includes(r.paragraph_id))

  // A refusal is a correct outcome, not a failure -- the corpus is three
  // subparts, not all of OSHA. Showing the bare sentence made it read as the
  // tool breaking, so it gets its own state that names the boundary.
  if (refused) {
    return (
      <div className="answer-section outofscope">
        <p className="eyebrow">Outside the indexed corpus</p>
        <p className="outofscope-body">
          Nothing in the indexed text answers this, so the model declined rather
          than guessing. This is the intended behaviour: it only answers from
          Subparts D and I and <code>1910.147</code>, and says so when a question
          falls outside them.
        </p>
        <p className="outofscope-note">
          It still searched, and these paragraphs came closest:
        </p>
        <ul className="retrieved-uncited-list">
          {retrieved.slice(0, 5).map((r, i) => (
            <li key={r.paragraph_id} style={{ animationDelay: `${i * 40}ms` }}>
              <Citation id={r.paragraph_id} entry={r} cited={false} />
            </li>
          ))}
        </ul>
      </div>
    )
  }

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
