const LATEST_TRIP_KEY = 'travelAgent.latestTripId'
const RECENT_TRIPS_KEY = 'travelAgent.recentTrips'

export interface RecentTrip {
  tripId: string
  title: string
  updatedAt: string
}

export function getLatestTripId(): string | null {
  return window.localStorage.getItem(LATEST_TRIP_KEY)
}

export function saveLatestTrip(tripId: string, title = '최근 여행') {
  window.localStorage.setItem(LATEST_TRIP_KEY, tripId)
  const recentTrips = getRecentTrips()
  const next: RecentTrip = { tripId, title, updatedAt: new Date().toISOString() }
  const deduped = [next, ...recentTrips.filter((trip) => trip.tripId !== tripId)].slice(0, 8)
  window.localStorage.setItem(RECENT_TRIPS_KEY, JSON.stringify(deduped))
}

export function getRecentTrips(): RecentTrip[] {
  const raw = window.localStorage.getItem(RECENT_TRIPS_KEY)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
