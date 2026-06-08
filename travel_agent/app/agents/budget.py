from __future__ import annotations

from travel_agent.app.schemas.budget import BudgetBreakdown, BudgetEstimate
from travel_agent.app.schemas.common import CriticFinding, FindingCategory, FindingSeverity
from travel_agent.app.schemas.trip import TripPlanState


class BudgetAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        travelers = brief.travelers if brief and brief.travelers else 1
        days = brief.duration_days if brief and brief.duration_days else 1
        # 실시간 검색된 후보 중 '최저가'를 기준으로 잡는다(정렬 순서와 무관하게).
        flight_prices = [
            option.price.amount for option in state.transport_options if option.price.amount
        ]
        flights = min(flight_prices) if flight_prices else 0
        hotel_totals = [
            option.total_price.amount
            for option in state.accommodation_options
            if option.total_price.amount
        ]
        accommodation = min(hotel_totals) if hotel_totals else 0
        has_live = bool(state.transport_options or state.accommodation_options)
        food = travelers * days * 60_000
        local_transport = travelers * days * 15_000
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
        state.budget = BudgetEstimate(
            total_estimated_cost=round(total, 2),
            per_person_estimated_cost=round(total / travelers, 2),
            breakdown=breakdown,
            currency=state.currency,
            confidence="medium" if has_live else "low",
            budget_warnings=warnings,
            assumptions=[
                "항공·숙박은 실시간 검색된 최저가 기준입니다."
                if has_live
                else "항공·숙박 실시간 가격을 가져오지 못했습니다.",
                f"식비 1인 1일 60,000 {state.currency}, 현지 교통 15,000 {state.currency} 가정.",
                "예비비 10%를 포함했습니다.",
            ],
        )
        return state
