import type { POIOption } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'

interface Props {
  options: POIOption[]
  eyebrow?: string
  title?: string
}

export function RestaurantOptionsCard({ options, eyebrow = '맛집', title = '식당 후보' }: Props) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      {options.length === 0 ? (
        <EmptyState message={`아직 ${title}가 없습니다.`} />
      ) : (
        <div className="option-list">
          {options.map((option) => {
            const url = option.metadata.source_ref.source_url
            return (
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
                {url && (
                  <a className="option-link" href={url} target="_blank" rel="noopener noreferrer">
                    구글 지도에서 보기 ↗
                  </a>
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
