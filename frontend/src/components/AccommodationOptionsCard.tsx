import type { AccommodationOption } from '../types/trip'
import { cleanDisplayText, formatMoney } from '../utils/format'
import { EmptyState } from './EmptyState'

export function AccommodationOptionsCard({ options }: { options: AccommodationOption[] }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">숙박</p>
          <h2>숙소 후보</h2>
        </div>
      </div>
      {options.length === 0 ? (
        <EmptyState message="아직 숙소 후보가 없습니다." />
      ) : (
        <div className="option-list">
          {options.map((option) => (
            <article className="option-card" key={option.option_id}>
              <div className="option-card-header">
                <h3>{cleanDisplayText(option.name)}</h3>
                <div className="option-badges">
                  <span className="small-badge">{hotelSourceLabel(option.metadata.provider_name)}</span>
                  <span
                    className={`small-badge source-kind-${option.metadata.source_ref.is_mock ? 'mock' : 'live'}`}
                  >
                    {option.metadata.source_ref.is_mock ? 'mock' : 'live'}
                  </span>
                  {option.rating && <span className="small-badge">★ {option.rating.toFixed(1)}</span>}
                  {option.star_rating && (
                    <span className="small-badge">{option.star_rating}성급</span>
                  )}
                </div>
              </div>
              <p>
                {cleanDisplayText(option.location.name)}
                {option.review_count ? ` · 리뷰 ${option.review_count.toLocaleString('ko-KR')}` : ''}
                {` · 출처: ${hotelSourceLabel(option.metadata.provider_name)}`}
              </p>
              {option.amenities && option.amenities.length > 0 && (
                <div className="amenity-chips">
                  {option.amenities.slice(0, 5).map((amenity) => (
                    <span className="amenity-chip" key={`${option.option_id}-${amenity}`}>
                      {cleanDisplayText(amenity)}
                    </span>
                  ))}
                </div>
              )}
              <p>1박 {formatMoney(option.nightly_price)}</p>
              <strong>총 {formatMoney(option.total_price)}</strong>
              <p className="fine-print">{cleanCancellationPolicy(option.cancellation_policy)}</p>
              {option.notes.length > 0 && (
                <ul className="option-note-list">
                  {option.notes.slice(0, 2).map((note) => (
                    <li key={`${option.option_id}-${note}`}>{cleanDisplayText(note)}</li>
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

function cleanCancellationPolicy(policy: string): string {
  if (/simulated/i.test(policy)) return '체크인 48시간 전까지 취소 조건 확인 필요'
  return cleanDisplayText(policy)
}

/** provider_name(naver_hotel/google_hotel)을 읽기 쉬운 출처명으로 바꾼다. */
function hotelSourceLabel(provider: string): string {
  if (provider === 'naver_hotel') return '네이버'
  if (provider === 'google_hotel') return '구글'
  return cleanDisplayText(provider)
}
