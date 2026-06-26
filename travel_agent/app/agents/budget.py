from __future__ import annotations

from travel_agent.app.llm.advisor import estimate_daily_costs
from travel_agent.app.schemas.budget import BudgetBreakdown, BudgetEstimate
from travel_agent.app.schemas.common import CriticFinding, FindingCategory, FindingSeverity
from travel_agent.app.schemas.trip import TripPlanState

_DEFAULT_FOOD_PER_DAY = 60_000
_DEFAULT_TRANSPORT_PER_DAY = 15_000


class BudgetAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        travelers = brief.travelers if brief and brief.travelers else 1
        days = brief.duration_days if brief and brief.duration_days else 1
        # 실시간 검색된 후보 중 '최저가'를 기준으로 잡는다(정렬 순서와 무관하게).
        flight_prices = [
            option.price.amount for option in state.transport_options if option.price.amount
        ]
        # 표시 운임(메타서치 기준)을 그대로 쓴다. 1인/총액 기준이 소스마다 달라 인원 곱은
        # 하지 않고, assumptions에 '표시 운임 기준'임을 명시한다(과대계상 방지).
        flights = min(flight_prices) if flight_prices else 0
        hotel_totals = [
            option.total_price.amount
            for option in state.accommodation_options
            if option.total_price.amount
        ]
        accommodation = min(hotel_totals) if hotel_totals else 0
        has_live = bool(state.transport_options or state.accommodation_options)
        # 1인 1일 식비·현지교통: 도시 물가를 LLM이 추정(실패 시 기본값). 유럽/동남아 편차 반영.
        destination = state.primary_destination or ""
        daily = estimate_daily_costs(
            destination, travel_style=brief.travel_style if brief else None, currency=state.currency
        )
        food_per_day, transport_per_day = daily or (
            _DEFAULT_FOOD_PER_DAY,
            _DEFAULT_TRANSPORT_PER_DAY,
        )
        food = travelers * days * food_per_day
        local_transport = travelers * days * transport_per_day
        activities = (
            sum(
                item.estimated_cost.amount
                for day in (state.optimized_itinerary.days if state.optimized_itinerary else [])
                for item in day.items
            )
            * travelers
        )
        subtotal = flights + accommodation + food + local_transport + activities
        buffer = subtotal * 0.1
        total = subtotal + buffer
        breakdown = BudgetBreakdown(
            flights=flights,
            accommodation=accommodation,
            food=food,
            local_transport=local_transport,
            activities=activities,
            buffer=buffer,
        )
        if has_live:
            warnings: list[str] = [
                "항공·숙박은 실시간 검색 최저가, 식비·현지교통은 일 단위 평균 추정입니다."
            ]
        else:
            warnings = ["가격을 가져오지 못해 일 단위 평균만으로 추정했습니다."]
        if brief and brief.budget_total and total > brief.budget_total:
            over_by = total - brief.budget_total
            warnings.append(f"예상 비용이 예산을 {over_by:,.0f} {state.currency} 초과합니다.")
            severity = (
                FindingSeverity.blocking
                if total > brief.budget_total * 1.2
                else FindingSeverity.warning
            )
            state.critic_findings.append(
                CriticFinding(
                    severity=severity,
                    category=FindingCategory.budget,
                    message="예상 예산 초과가 감지되었습니다.",
                    suggested_fix=(
                        "저가 항공/숙소, 무료 일정 확대, 여행 기간 단축, 대체 목적지를 검토하세요."
                    ),
                )
            )
        # 항상 남기는 투명성 안내(증거 기반 플래너로서 가격은 재확인 대상임을 명시).
        state.critic_findings.append(
            CriticFinding(
                severity=FindingSeverity.info,
                category=FindingCategory.source_quality,
                message=(
                    "표시 가격은 실시간 검색 기준 추정치입니다. 예약 전 실제 가격을 확인하세요."
                    if has_live
                    else "가격 추정치입니다. 예약 전 실제 가격을 확인하세요."
                ),
                suggested_fix="항공·숙소 예약 사이트에서 최종 가격과 취소 규정을 확인하세요.",
            )
        )
        # 1인 1일 현지 경비(식비+교통+입장료) — 항공·숙박 제외한 '하루 쓸 돈'.
        on_ground = food + local_transport + activities
        per_day = round(on_ground / (travelers * days), 2) if travelers and days else None
        daily_note = (
            "도시 물가 기준 LLM 추정"
            if daily
            else f"기본값(식비 {_DEFAULT_FOOD_PER_DAY:,}·교통 {_DEFAULT_TRANSPORT_PER_DAY:,})"
        )
        state.budget = BudgetEstimate(
            total_estimated_cost=round(total, 2),
            per_person_estimated_cost=round(total / travelers, 2),
            per_day_estimated_cost=per_day,
            total_local_label=self._local_total(total, state),
            breakdown=breakdown,
            currency=state.currency,
            confidence="medium" if has_live else "low",
            budget_warnings=warnings,
            assumptions=[
                "항공·숙박은 검색 최저가(표시 운임 기준)입니다."
                if has_live
                else "항공·숙박 실시간 가격을 가져오지 못했습니다.",
                f"식비 1인 1일 {food_per_day:,} {state.currency}, 현지 교통 "
                f"{transport_per_day:,} {state.currency} ({daily_note}).",
                "예비비 10%를 포함했습니다.",
            ],
        )
        return state

    @staticmethod
    def _local_total(total_krw: float, state: TripPlanState) -> str | None:
        """총액을 현지 통화로 환산한 라벨(fx_info가 있을 때만)."""
        fx = state.fx_info
        if not fx or not fx.target_per_base or fx.target_currency == state.currency:
            return None
        local = total_krw * fx.target_per_base
        return f"약 {round(local):,} {fx.target_currency}"
