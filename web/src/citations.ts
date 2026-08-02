// Mirrors scripts/rag/ground.py CITATION_PATTERN / CITATION_ID. IDs contain
// parens inside the brackets (e.g. [1910.134(d)(3)(i)(A)]), so a naive
// \[(\w+)\] match fails -- see ground.py's comment for why.

export const CITATION_PATTERN = /\[([^[\]]+)\]/g

// OSHA citation ID shape: 4 digits, dot, digits, then zero or more
// parenthesised groups. Filters out literal brackets like [RESERVED] or
// [Table 1 - Assigned Protection Factors 5].
export const CITATION_ID = /^\d{4}\.\d+(?:\([^)]+\))*$/

export type AnswerSegment = { type: 'text'; value: string } | { type: 'citation'; id: string }

/** Split answer text into plain-text and citation segments, in order. */
export function splitAnswer(answer: string): AnswerSegment[] {
  const segments: AnswerSegment[] = []
  let lastIndex = 0

  for (const match of answer.matchAll(CITATION_PATTERN)) {
    const [full, id] = match
    const index = match.index ?? 0

    if (index > lastIndex) {
      segments.push({ type: 'text', value: answer.slice(lastIndex, index) })
    }
    segments.push(CITATION_ID.test(id) ? { type: 'citation', id } : { type: 'text', value: full })
    lastIndex = index + full.length
  }

  if (lastIndex < answer.length) {
    segments.push({ type: 'text', value: answer.slice(lastIndex) })
  }

  return segments
}
