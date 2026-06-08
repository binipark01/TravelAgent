export interface LLMAnswerRequest {
  readonly message: string
  readonly locale: string
  readonly currency: string
  readonly timezone: string
}

export interface FlightFareCandidate {
  readonly provider: string
  readonly airline: string
  readonly outbound_departure: string
  readonly outbound_arrival: string
  readonly inbound_departure?: string | null
  readonly inbound_arrival?: string | null
  readonly outbound_duration?: string | null
  readonly inbound_duration?: string | null
  readonly price: string
  readonly stops?: string | null
  readonly source_url?: string | null
  readonly notes: readonly string[]
}

export interface FlightSourceAttempt {
  readonly domain?: string
  readonly agent_name?: string
  readonly provider: string
  readonly title: string
  readonly source_url?: string | null
  readonly status: string
  readonly summary: string
  readonly evidence: readonly string[]
  readonly options_found?: boolean
  readonly fare_options_found: boolean
  readonly fare_options?: readonly FlightFareCandidate[]
}

export interface DomainAgentRun {
  readonly agent_name: string
  readonly title: string
  readonly status: string
  readonly summary: string
  readonly evidence: readonly string[]
}

export interface LLMAnswerResponse {
  readonly answer: string
  readonly answer_kind?: 'answer' | 'blocked'
  readonly interpreted_request?: string | null
  readonly source_attempts?: readonly FlightSourceAttempt[]
  readonly blockers?: readonly string[]
  readonly agent_runs?: readonly DomainAgentRun[]
}
