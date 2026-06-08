import type { POIOption } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'

export function RestaurantOptionsCard({ options }: { options: POIOption[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">맛집</p>
          <h2>식당 후보</h2>
        </div>
      </div>
      {options.length === 0 ? (
        <EmptyState message="아직 식당 후보가 없습니다." />
      ) : (
        <div className="option-list">
          {options.map((option) => (
            <article className="option-card" key={option.poi_id}>
              <div className="option-card-header">
                <h3>{cleanDisplayText(option.title)}</h3>
                <div className="option-badges">
                  <span
                    className={`small-badge source-kind-${
                      option.metadata.source_ref.is_mock ? 'mock' : 'live'
                    }`}
                  >
                    {option.metadata.source_ref.is_mock ? 'mock' : 'live'}
                  </span>
                  {option.rating != null && (
                    <span className="small-badge">★ {option.rating.toFixed(1)}</span>
                  )}
                </div>
              </div>
              {option.type && <p>{cleanDisplayText(option.type)}</p>}
              {option.notes.length > 0 && (
                <ul className="option-note-list">
                  {option.notes.slice(0, 2).map((note) => (
                    <li key={`${option.poi_id}-${note}`}>{cleanDisplayText(note)}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
