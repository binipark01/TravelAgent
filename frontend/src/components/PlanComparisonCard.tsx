import type { AccommodationOption, FlightOption } from '../types/trip'
import { cleanDisplayText, formatMoney } from '../utils/format'

interface Variant {
  label: string
  tag: string
  flight: FlightOption
  hotel: AccommodationOption
  total: number
}

function byFlightPrice(a: FlightOption, b: FlightOption): number {
  return (a.price.amount || 0) - (b.price.amount || 0)
}

function byHotelPrice(a: AccommodationOption, b: AccommodationOption): number {
  return (a.nightly_price.amount || 0) - (b.nightly_price.amount || 0)
}

function buildVariants(flights: FlightOption[], hotels: AccommodationOption[]): Variant[] {
  if (flights.length < 2 || hotels.length < 2) return []
  const f = [...flights].sort(byFlightPrice)
  const h = [...hotels].sort(byHotelPrice)
  const premiumHotel = [...hotels].sort(
    (a, b) => (b.rating ?? 0) - (a.rating ?? 0) || (b.nightly_price.amount || 0) - (a.nightly_price.amount || 0),
  )[0]
  const fMid = f[Math.floor((f.length - 1) / 2)]
  const hMid = h[Math.floor((h.length - 1) / 2)]
  const fTop = f[f.length - 1]
  const make = (label: string, tag: string, flight: FlightOption, hotel: AccommodationOption): Variant => ({
    label,
    tag,
    flight,
    hotel,
    total: (flight.price.amount || 0) + (hotel.total_price.amount || 0),
  })
  return [
    make('가성비', '최저가 조합', f[0], h[0]),
    make('밸런스', '중간 가격', fMid, hMid),
    make('프리미엄', '평점 우선', fTop, premiumHotel),
  ]
}

export function PlanComparisonCard({
  flights,
  hotels,
}: {
  flights: FlightOption[]
  hotels: AccommodationOption[]
}) {
  const variants = buildVariants(flights, hotels)
  if (variants.length === 0) return null
  const cheapest = Math.min(...variants.map((v) => v.total))

  return (
    <section className="card wide-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">비교</p>
          <h2>플랜 비교 (항공+숙소)</h2>
        </div>
      </div>
      <div className="plan-compare-grid">
        {variants.map((v) => (
          <div className={`plan-compare-col${v.total === cheapest ? ' best' : ''}`} key={v.label}>
            <div className="plan-compare-head">
              <strong>{v.label}</strong>
              <span className="small-badge">{v.tag}</span>
            </div>
            <p className="plan-compare-total">{formatMoney({ amount: v.total, currency: v.flight.price.currency })}</p>
            <p className="plan-compare-line">
              ✈️ {cleanDisplayText(v.flight.airline)} · {formatMoney(v.flight.price)}
            </p>
            <p className="plan-compare-line">
              🏨 {cleanDisplayText(v.hotel.name)}
              {v.hotel.rating ? ` ★${v.hotel.rating.toFixed(1)}` : ''}
            </p>
            <p className="plan-compare-sub">숙소 총 {formatMoney(v.hotel.total_price)}</p>
          </div>
        ))}
      </div>
      <p className="fine-print">항공 최저가 + 숙소 총액 기준 합계. 식비·현지교통은 예산 카드 참고.</p>
    </section>
  )
}
