from __future__ import annotations

from datetime import timedelta

from travel_agent.app.providers.mock_common import combine_date_time, mock_metadata
from travel_agent.app.schemas.common import Money
from travel_agent.app.schemas.providers import FlightOption, FlightSearchRequest
from travel_agent.app.utils.ids import new_id

# 목적지별 1인 왕복 기준가(추천 옵션 기준).
_BASE_FARES = {
    "Fukuoka": 280_000,
    "후쿠오카": 280_000,
    "Sapporo": 520_000,
    "삿포로": 520_000,
}
_DEFAULT_FARE = 420_000


class MockFlightProvider:
    provider_name = "mock_flights"

    def search_flights(self, request: FlightSearchRequest) -> list[FlightOption]:
        base = _BASE_FARES.get(request.destination, _DEFAULT_FARE)
        travelers = max(request.travelers, 1)
        outbound_morning = request.outbound_departure_window == "morning"
        return_afternoon = request.return_departure_window == "afternoon"

        recommended_notes = ["추천 옵션 · 요청 조건을 반영했습니다."]
        if outbound_morning:
            recommended_notes.append("가는 편 오전 출발 조건을 반영했습니다.")
        if return_afternoon:
            recommended_notes.append("오는 편 오후 출발 조건을 반영했습니다.")
        recommended_notes.append("가격과 좌석 가능 여부는 예약 전 재확인이 필요합니다.")

        # [0] 추천: 요청한 시간대(오전/오후)를 반영하며 항상 첫 번째.
        return [
            self._build_option(
                request,
                travelers,
                airline="Mock Air",
                fare_per_person=base,
                out_hour=9 if outbound_morning else 11,
                out_minute=30,
                out_duration=timedelta(hours=2, minutes=5),
                ret_hour=15 if return_afternoon else 18,
                ret_minute=20,
                ret_duration=timedelta(hours=2, minutes=15),
                stops=0,
                refundable=False,
                reference_prefix="mock-flight-rec",
                notes=recommended_notes,
            ),
            # [1] 최저가: 이른 출발 + 1회 경유.
            self._build_option(
                request,
                travelers,
                airline="Budget Mock Air",
                fare_per_person=round(base * 0.82, -2),
                out_hour=6,
                out_minute=10,
                out_duration=timedelta(hours=4, minutes=40),
                ret_hour=21,
                ret_minute=30,
                ret_duration=timedelta(hours=4, minutes=55),
                stops=1,
                refundable=False,
                reference_prefix="mock-flight-low",
                notes=["최저가 옵션 · 1회 경유", "이동 시간이 길고 환불이 어렵습니다."],
            ),
            # [2] 직항 프리미엄: 환불 가능.
            self._build_option(
                request,
                travelers,
                airline="Premium Mock Air",
                fare_per_person=round(base * 1.35, -2),
                out_hour=10,
                out_minute=0,
                out_duration=timedelta(hours=1, minutes=55),
                ret_hour=16,
                ret_minute=0,
                ret_duration=timedelta(hours=2, minutes=5),
                stops=0,
                refundable=True,
                reference_prefix="mock-flight-prem",
                notes=["직항 · 환불 가능 · 프리미엄", "좌석 여유가 비교적 많습니다."],
            ),
        ]

    def _build_option(
        self,
        request: FlightSearchRequest,
        travelers: int,
        *,
        airline: str,
        fare_per_person: float,
        out_hour: int,
        out_minute: int,
        out_duration: timedelta,
        ret_hour: int,
        ret_minute: int,
        ret_duration: timedelta,
        stops: int,
        refundable: bool,
        reference_prefix: str,
        notes: list[str],
    ) -> FlightOption:
        depart = combine_date_time(request.departure_date, out_hour, out_minute)
        arrive = depart + out_duration
        if request.return_date is not None:
            return_depart = combine_date_time(request.return_date, ret_hour, ret_minute)
            return_arrive = return_depart + ret_duration
        else:
            return_depart = None
            return_arrive = None
        stop_label = "직항" if stops == 0 else f"{stops}회 경유"
        metadata = mock_metadata(
            self.provider_name, f"Mock flight ({airline}, {stop_label})", reference_prefix
        )
        return FlightOption(
            option_id=new_id("flt"),
            airline=airline,
            origin=request.origin,
            destination=request.destination,
            departure_time=depart,
            arrival_time=arrive,
            return_departure_time=return_depart,
            return_arrival_time=return_arrive,
            price=Money(amount=int(fare_per_person) * travelers, currency=request.currency),
            refundable=refundable,
            booking_required=True,
            metadata=metadata,
            notes=[*notes, f"경유: {stop_label}"],
        )
