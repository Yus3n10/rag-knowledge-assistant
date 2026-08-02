// Mirrors api/main.py POST /ask response shape.

export interface RetrievedEntry {
  paragraph_id: string
  distance: number
  heading_trail: string
  text: string
}

export interface AskResponse {
  answer: string
  citations: string[]
  citation_report: {
    valid: string[]
    not_retrieved: string[]
    not_in_corpus: string[]
  }
  ungrounded_numbers: string[]
  retrieved: RetrievedEntry[]
  stats: {
    prompt_tokens: number
    completion_tokens: number
    latency_s: number
    load_duration_s?: number
  }
}
