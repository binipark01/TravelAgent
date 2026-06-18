import type { POIOption } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'
import { placeTriggerProps, useMapFocus } from './MapFocusContext'

interface Props {
  options: POIOption[]
  eyebrow?: string
  title?: string
}

export function RestaurantOptionsCard({ options, eyebrow = '맛집', title = '식당 후보' }: Props) {
  const focus = useMapFocus()
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
        <>
          <ul className="poi-list">
            {options.map((option) => {
              const url = option.metadata.source_ref.source_url
              const trig = placeTriggerProps(focus, {
                label: cleanDisplayText(option.title),
                area: option.area || option.location.area,
                lat: option.location.latitude,
                lng: option.location.longitude,
              })
              return (
                <li className="poi-row" key={option.poi_id}>
                  <div className={`poi-row__main ${trig.className}`.trim()} {...trig.interactive}>
                    <span className="poi-name">{cleanDisplayText(option.title)}</span>
                    {option.type && <span className="poi-type">{cleanDisplayText(option.type)}</span>}
                  </div>
                  <div className="poi-row__meta">
                    {option.rating != null && (
                      <span className="poi-rating">★ {option.rating.toFixed(1)}</span>
                    )}
                    {url && (
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        지도 ↗
                      </a>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
          <p className="card-footnote">구글 지도 실시간 · 영업시간·예약은 방문 전 확인</p>
        </>
      )}
    </section>
  )
}
