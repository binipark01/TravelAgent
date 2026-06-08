import type { FlightOption } from '../types/trip'
import { cleanDisplayText, formatFloatingDateTime, formatMoney } from '../utils/format'
import { EmptyState } from './EmptyState'

export function TransportOptionsCard({ options }: { options: FlightOption[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">이동</p>
          <h2>항공/이동 후보</h2>
        </div>
      </div>
      {options.length === 0 ? (
        <EmptyState message="아직 항공 후보가 없습니다." />
      ) : (
        <div className="option-list">
          {options.map((option, index) => (
            <article className="option-card" key={option.option_id}>
              <div className="option-card-header">
                <h3>{displayAirline(option.airline, index)}</h3>
                <strong>{formatMoney(option.price)}</strong>
              </div>
              <p className="route-line">
                {cleanDisplayText(option.origin)} → {cleanDisplayText(option.destination)}
              </p>
              <p>출발 {formatFloatingDateTime(option.departure_time)}</p>
              <p>도착 {formatFloatingDateTime(option.arrival_time)}</p>
              {option.return_departure_time && (
                <p>오는 편 출발 {formatFloatingDateTime(option.return_departure_time)}</p>
              )}
              {option.return_arrival_time && (
                <p>오는 편 도착 {formatFloatingDateTime(option.return_arrival_time)}</p>
              )}
              {option.notes.length > 0 && (
                <ul className="text-list compact">
                  {option.notes.map((note) => (
                    <li key={note}>{cleanDisplayText(note)}</li>
                  ))}
                </ul>
              )}
              {option.metadata.source_ref.source_url && (
                <a
                  className="option-link"
                  href={option.metadata.source_ref.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  예약 페이지에서 확인 ↗
                </a>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function displayAirline(airline: string, index: number): string {
  return /\bmock\b/i.test(airline) ? `항공 후보 ${index + 1}` : cleanDisplayText(airline)
}
