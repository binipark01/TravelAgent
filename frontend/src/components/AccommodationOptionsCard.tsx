import type { AccommodationOption } from '../types/trip'
import { cleanDisplayText, formatMoney } from '../utils/format'
import { EmptyState } from './EmptyState'
import { placeTriggerProps, useMapFocus } from './MapFocusContext'

const TAG_MARK = /[💰📍✅⚠️]|ℹ️/

export function AccommodationOptionsCard({ options }: { options: AccommodationOption[] }) {
  const focus = useMapFocus()
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
        <>
          <div className="hotel-list">
            {options.map((option) => {
              const advice = option.notes.find((note) => note.startsWith('💬'))
              const tagNote = option.notes.find(
                (note) => TAG_MARK.test(note) && !note.startsWith('💬'),
              )
              const chips = tagNote
                ? tagNote.split('·').map((part) => part.trim()).filter(Boolean)
                : []
              const url = option.metadata.source_ref.source_url
              const trig = placeTriggerProps(focus, {
                label: cleanDisplayText(option.name),
                area: option.location.area,
                lat: option.location.latitude,
                lng: option.location.longitude,
              })
              return (
                <article className="hotel-row" key={option.option_id}>
                  <div className={`hotel-row__head ${trig.className}`.trim()} {...trig.interactive}>
                    <span className="hotel-name">{cleanDisplayText(option.name)}</span>
                    <strong className="hotel-price">
                      {formatMoney(option.nightly_price)}
                      <span className="hotel-price__unit">/박</span>
                    </strong>
                  </div>
                  <div className="hotel-row__meta">
                    {option.rating != null && <span>★ {option.rating.toFixed(1)}</span>}
                    {option.star_rating != null && <span>{option.star_rating}성급</span>}
                    <span>{hotelSourceLabel(option.metadata.provider_name)}</span>
                    {option.review_count ? (
                      <span>리뷰 {option.review_count.toLocaleString('ko-KR')}</span>
                    ) : null}
                  </div>
                  {advice && <p className="opt-advice">{cleanDisplayText(advice)}</p>}
                  {option.amenities && option.amenities.length > 0 && (
                    <div className="amenity-chips">
                      {option.amenities.slice(0, 4).map((amenity) => (
                        <span className="amenity-chip" key={`${option.option_id}-${amenity}`}>
                          {cleanDisplayText(amenity)}
                        </span>
                      ))}
                    </div>
                  )}
                  {chips.length > 0 && (
                    <div className="hotel-tags">
                      {chips.map((chip) => (
                        <span className="flight-chip" key={`${option.option_id}-${chip}`}>
                          {chip}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="hotel-row__foot">
                    <span className="hotel-total">총 {formatMoney(option.total_price)}</span>
                    {url && (
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        예약 ↗
                      </a>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
          <p className="card-footnote">
            여행 날짜 기준 1박가(세금·수수료 포함) · 예약 전 객실·가격 재확인
          </p>
        </>
      )}
    </section>
  )
}

/** provider_name(naver_hotel/google_hotel)을 읽기 쉬운 출처명으로 바꾼다. */
function hotelSourceLabel(provider: string): string {
  if (provider === 'naver_hotel') return '네이버'
  if (provider === 'google_hotel') return '구글'
  return cleanDisplayText(provider)
}
