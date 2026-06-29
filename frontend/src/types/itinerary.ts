import type { Location, Money } from './common'

export interface ItineraryItem {
  item_id: string
  title: string
  type: string
  location: Location
  start_time: string
  end_time: string
  estimated_cost: Money
  booking_required: boolean
  source_refs: string[]
  notes: string[]
  feasibility_flags: string[]
}

export interface MealSuggestion {
  item_id: string
  meal_type: string
  title: string
  area: string
  start_time: string
  end_time: string
  estimated_cost: Money
  source_refs: string[]
  notes: string[]
  latitude?: number | null
  longitude?: number | null
}

export interface TransferSegment {
  item_id: string
  origin: string
  destination: string
  start_time: string
  end_time: string
  travel_minutes: number
  mode: string
  source_refs: string[]
  feasibility_flags: string[]
}

export interface FreeTimeBlock {
  item_id: string
  title: string
  start_time: string
  end_time: string
  notes: string[]
}

export interface DayPlan {
  day: number
  date?: string | null
  area?: string | null
  weather?: string | null
  items: ItineraryItem[]
  meals: MealSuggestion[]
  transfers: TransferSegment[]
  free_time: FreeTimeBlock[]
  notes: string[]
}

export interface Itinerary {
  days: DayPlan[]
  summary: string
  feasibility_flags: string[]
}
