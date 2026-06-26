from __future__ import annotations

from datetime import time

from travel_agent.app.agents.critic import PlanCriticAgent
from travel_agent.app.schemas.common import Location, Money
from travel_agent.app.schemas.itinerary import (
    DayPlan,
    Itinerary,
    ItineraryItem,
    TransferSegment,
)
from travel_agent.app.utils.ids import new_id


def _item(title: str, start: time, end: time, *, type_: str = "관광지") -> ItineraryItem:
    return ItineraryItem(
        item_id=new_id("item"),
        title=title,
        type=type_,
        location=Location(name="도시"),
        start_time=start,
        end_time=end,
        estimated_cost=Money(amount=0, currency="KRW"),
    )


def _transfer(minutes: int, start: time, end: time) -> TransferSegment:
    return TransferSegment(
        item_id=new_id("xfer"),
        origin="A",
        destination="B",
        start_time=start,
        end_time=end,
        travel_minutes=minutes,
        mode="지하철",
    )


def _itin(days: list[DayPlan]) -> Itinerary:
    return Itinerary(days=days, summary="t", feasibility_flags=[])


def test_clean_itinerary_has_no_feasibility_flags() -> None:
    # 09~18시 사이 관광 3곳 + 짧은 이동: 모든 결정적 체크를 통과해야 한다(플래그 0).
    day = DayPlan(
        day=1,
        items=[
            _item("A", time(10, 0), time(11, 30)),
            _item("B", time(12, 0), time(13, 30)),
            _item("C", time(15, 0), time(17, 0)),
        ],
        transfers=[_transfer(20, time(11, 30), time(11, 50))],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert itin.feasibility_flags == []


def test_late_finish_is_flagged() -> None:
    # 마지막 관광이 23:30에 끝남 → 과late 종료 플래그.
    day = DayPlan(day=2, items=[_item("야경", time(21, 0), time(23, 30))])
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert any("2일차" in f and "너무 늦" in f for f in itin.feasibility_flags)


def test_overcrowded_day_is_flagged() -> None:
    # anchor(공항·숙소) 제외 관광 7곳 > 상한 6 → 과밀 플래그.
    items = [_item(f"P{i}", time(9, 0), time(9, 30)) for i in range(7)]
    # 공항/숙소 anchor는 곳수에서 제외되는지 확인용으로 추가(세지 않아야 함).
    items.append(_item("간사이공항", time(8, 0), time(8, 30), type_="공항"))
    day = DayPlan(day=3, items=items)
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    flags = itin.feasibility_flags
    assert any("3일차" in f and "과밀" in f for f in flags)
    assert any("관광 7곳" in f for f in flags)  # anchor는 안 세어 7곳


def test_unrealistic_time_budget_is_flagged() -> None:
    # 체류 합 900분(>840) → 시간 예산 비현실 플래그.
    day = DayPlan(
        day=4,
        items=[
            _item("A", time(9, 0), time(14, 0)),  # 300분
            _item("B", time(14, 0), time(19, 0)),  # 300분
            _item("C", time(19, 0), time(23, 59)),  # ~299분
        ],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert any("4일차" in f and "활동 가능 시간" in f for f in itin.feasibility_flags)


def test_feasibility_check_is_idempotent() -> None:
    # 두 번 돌려도 critic 플래그가 중복되지 않는다(매번 재계산·교체).
    day = DayPlan(day=1, items=[_item("야경", time(21, 0), time(23, 30))])
    itin = _itin([day])
    critic = PlanCriticAgent()
    critic._check_feasibility(itin)
    first = list(itin.feasibility_flags)
    critic._check_feasibility(itin)
    assert itin.feasibility_flags == first  # 중복 누적 없음


def test_non_critic_flags_are_preserved() -> None:
    # 다른 출처가 넣은 플래그([검증] 접두사 아님)는 보존된다.
    day = DayPlan(day=1, items=[_item("A", time(10, 0), time(11, 0))])
    itin = _itin([day])
    itin.feasibility_flags = ["날씨: 비 예보"]
    PlanCriticAgent()._check_feasibility(itin)
    assert "날씨: 비 예보" in itin.feasibility_flags
