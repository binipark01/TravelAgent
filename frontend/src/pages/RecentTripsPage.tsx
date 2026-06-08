import { Link } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import { formatDateTime } from '../utils/format'
import { getRecentTrips } from '../utils/recentTrips'

export function RecentTripsPage() {
  const trips = getRecentTrips()

  return (
    <section className="card">
      <h1>최근 여행</h1>
      {trips.length === 0 ? (
        <EmptyState message="최근 작업한 여행이 없습니다." />
      ) : (
        <div className="option-list">
          {trips.map((trip) => (
            <Link className="recent-trip-row" to={`/trips/${trip.tripId}`} key={trip.tripId}>
              <strong>{trip.title}</strong>
              <span>{formatDateTime(trip.updatedAt)}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
