export type TripStatus =
  | 'intake'
  | 'needs_user_input'
  | 'researching'
  | 'drafting'
  | 'validating'
  | 'needs_approval'
  | 'ready'
  | 'booking_in_progress'
  | 'completed'
  | 'failed'

export type FindingSeverity = 'info' | 'warning' | 'blocking'

export type FindingCategory =
  | 'budget'
  | 'route'
  | 'visa'
  | 'availability'
  | 'safety'
  | 'missing_input'
  | 'source_quality'
  | 'policy'

export interface Money {
  amount: number
  currency: string
}

export interface Location {
  name: string
  country?: string | null
  area?: string | null
  latitude?: number | null
  longitude?: number | null
}

export interface SourceRef {
  source_id: string
  provider: string
  provider_ref?: string | null
  source_url?: string | null
  title: string
  reference: string
  retrieved_at: string
  expires_at?: string | null
  is_live: boolean
  is_mock: boolean
  source_type: string
  confidence: number
  attribution?: string | null
  license_notes?: string | null
  freshness_note: string
}

export interface CriticFinding {
  severity: FindingSeverity
  category: FindingCategory
  message: string
  suggested_fix?: string | null
  affected_plan_items: string[]
}

export interface ProviderMetadata {
  provider_name: string
  retrieved_at: string
  source_ref: SourceRef
  expires_at?: string | null
  normalized_currency?: string | null
  is_mock: boolean
}
