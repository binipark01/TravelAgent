import type { ApprovalRequest, BookingRecord } from './approval'
import type { BudgetEstimate } from './budget'
import type { CriticFinding, Location, Money, ProviderMetadata, SourceRef, TripStatus } from './common'
import type { Itinerary } from './itinerary'

export interface TripBrief {
  origin?: string | null
  destinations: string[]
  start_date?: string | null
  end_date?: string | null
  flexible_dates: boolean
  duration_days?: number | null
  travelers?: number | null
  budget_total?: number | null
  budget_per_person?: number | null
  currency: string
  travel_style?: string | null
  pace?: string | null
  accommodation_preference?: string | null
  transport_preference?: string | null
  accessibility_needs: string[]
  dietary_restrictions: string[]
  passport_country?: string | null
  visa_status_known: boolean
  must_include: string[]
  must_avoid: string[]
  missing_fields: string[]
  assumptions: string[]
}

export interface FlightOption {
  option_id: string
  airline: string
  origin: string
  destination: string
  departure_time: string
  arrival_time: string
  return_departure_time?: string | null
  return_arrival_time?: string | null
  price: Money
  refundable: boolean
  booking_required: boolean
  metadata: ProviderMetadata
  notes: string[]
}

export interface AccommodationOption {
  option_id: string
  name: string
  location: Location
  nightly_price: Money
  total_price: Money
  rating?: number | null
  star_rating?: number | null
  review_count?: number | null
  amenities?: string[]
  cancellation_policy: string
  metadata: ProviderMetadata
  notes: string[]
}

export interface POIOption {
  poi_id: string
  title: string
  type: string
  location: Location
  area: string
  estimated_cost: Money
  rating?: number | null
  review_count?: number | null
  opening_hours?: string | null
  recommended_duration_minutes: number
  booking_required: boolean
  metadata: ProviderMetadata
  notes: string[]
}

export interface TripPlanState {
  trip_id: string
  user_id?: string | null
  locale: string
  currency: string
  timezone: string
  raw_user_message: string
  raw_user_messages: string[]
  brief?: TripBrief | null
  user_profile_snapshot: Record<string, unknown>
  constraints: Record<string, unknown>
  missing_fields: string[]
  assumptions: string[]
  destination_candidates: string[]
  selected_destination?: string | null
  transport_options: FlightOption[]
  accommodation_options: AccommodationOption[]
  poi_candidates: POIOption[]
  activity_options: POIOption[]
  local_transport_options: Array<Record<string, unknown>>
  route_evidence_refs: string[]
  draft_itinerary?: Itinerary | null
  optimized_itinerary?: Itinerary | null
  budget?: BudgetEstimate | null
  visa_result?: VisaCheckResult | null
  local_transport?: LocalTransportPlan | null
  fx_info?: FxInfo | null
  safety_info?: SafetyInfo | null
  nearby_guide?: NearbyGuide | null
  stay_area_guide?: StayAreaGuide | null
  prep_checklist?: PrepChecklist | null
  transport_tickets?: TransportTicketGuide | null
  risk_findings: CriticFinding[]
  critic_findings: CriticFinding[]
  approval_requests: ApprovalRequest[]
  booking_records: BookingRecord[]
  source_refs: SourceRef[]
  evidence_refs: string[]
  assistant_message?: string | null
  clarification?: string | null
  status: TripStatus
}

export interface LocalTransportItem {
  category: string
  name: string
  detail?: string | null
  price?: string | null
  duration?: string | null
  source_url?: string | null
}

export interface LocalTransportPlan {
  city: string
  summary: string
  airport_transfers: LocalTransportItem[]
  transit_passes: LocalTransportItem[]
  tips: string[]
  source_url?: string | null
}

export interface BookingPlatform {
  name: string
  url: string
  covers: string
  note?: string | null
}

export interface RouteLink {
  label: string
  maps_url: string
  booking_url?: string | null
}

export interface PassSuggestion {
  name: string
  url: string
  note: string
}

export interface TransportTicketGuide {
  destination_country: string
  summary: string
  hub?: string | null
  hub_lat?: number | null
  hub_lng?: number | null
  platforms: BookingPlatform[]
  pass_suggestion?: PassSuggestion | null
  route_links: RouteLink[]
  source_note: string
}

export interface NearbyDestination {
  name: string
  travel_time: string
  transport: string
  highlights: string[]
  best_for?: string | null
  source_url?: string | null
}

export interface NearbyGuide {
  hub: string
  summary: string
  destinations: NearbyDestination[]
  source_url?: string | null
}

export interface StayArea {
  name: string
  vibe: string
  good_for: string[]
  note?: string | null
  source_url?: string | null
}

export interface StayAreaGuide {
  destination: string
  summary: string
  areas: StayArea[]
  source_url?: string | null
}

export interface PrepGroup {
  title: string
  items: string[]
}

export interface PrepChecklist {
  destination: string
  summary: string
  groups: PrepGroup[]
}

export interface EmergencyContact {
  label: string
  number: string
}

export interface SafetyInfo {
  destination_country: string
  summary: string
  emergency_contacts: EmergencyContact[]
  consular_call_center: string
  embassy_note?: string | null
  travel_advisory?: string | null
  insurance_tips: string[]
  local_cautions: string[]
  source_url?: string | null
}

export interface FxSample {
  local_label: string
  krw_label: string
}

export interface FxInfo {
  base_currency: string
  target_currency: string
  target_per_base: number
  base_per_target: number
  samples: FxSample[]
  budget_total_base?: number | null
  budget_total_target?: number | null
  budget_total_target_label?: string | null
  tips: string[]
  source_url?: string | null
}

export interface VisaCheckResult {
  destination_country: string
  summary: string
  requires_official_verification: boolean
  missing_required_info: string[]
  passport_country?: string | null
  visa_required?: boolean | null
  visa_free_days?: number | null
  entry_authorization?: string | null
  passport_validity_rule?: string | null
  details: string[]
  source_url?: string | null
}

export interface TripCreateRequest {
  message: string
  user_id?: string | null
  locale: string
  currency: string
  timezone: string
}

export interface TripMessageRequest {
  message: string
}

export interface TripSummaryResponse {
  trip_id: string
  status: TripStatus
  summary: string
  missing_fields: string[]
  questions: string[]
  state?: TripPlanState | null
}

export interface FinalPlanResponse {
  trip_id: string
  status: TripStatus
  summary: string
  assumptions: string[]
  missing_fields: string[]
  recommended_destination?: string | null
  transport_options: FlightOption[]
  accommodation_options: AccommodationOption[]
  itinerary?: Itinerary | null
  budget?: BudgetEstimate | null
  risk_findings: CriticFinding[]
  critic_findings: CriticFinding[]
  approval_requests: ApprovalRequest[]
  source_refs: SourceRef[]
  next_actions: string[]
}
