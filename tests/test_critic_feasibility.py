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


def test_far_excursion_daytrip_is_flagged() -> None:
    # 편도 3시간(180분) 왕복 = 이동만 5.5시간 → 당일치기 빠듯 플래그(후라노·비에이류).
    day = DayPlan(
        day=3,
        items=[
            _item("팜 토미타", time(13, 0), time(14, 30)),
            _item("청의 호수", time(15, 0), time(16, 0)),
        ],
        transfers=[
            _transfer(180, time(10, 0), time(13, 0)),  # 숙소→근교(편도 3h)
            _transfer(150, time(16, 0), time(18, 30)),  # 근교→숙소(귀가)
        ],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert any("3일차" in f and "당일치기" in f for f in itin.feasibility_flags)


def test_overnight_move_day_not_flagged_as_daytrip() -> None:
    # 다른 숙소로 자러 가는 1박 이동일(비슈케크→송쿨 유르트캠프)은 왕복 당일치기가 아니므로
    # 이동이 길어도(편도 3h+) '당일치기 빠듯' 플래그를 띄우지 않는다.
    day = DayPlan(
        day=3,
        items=[
            _item("숙소 부근(비슈케크 알라토광장 일대)", time(10, 0), time(10, 30), type_="숙소"),
            _item("부라나 탑", time(12, 0), time(13, 30)),
            _item("코치코르 마을", time(16, 0), time(17, 0)),
            _item("숙소 부근(송쿨 유르트캠프 일대)", time(20, 0), time(20, 30), type_="숙소"),
        ],
        transfers=[
            _transfer(150, time(10, 30), time(13, 0)),
            _transfer(180, time(17, 0), time(20, 0)),
        ],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("당일치기" in f for f in itin.feasibility_flags)


def test_close_excursion_not_flagged_as_daytrip() -> None:
    # 편도 50분 근교 왕복(오타루류) = 이동 적음 → 당일치기 무난, 플래그 없음.
    day = DayPlan(
        day=2,
        items=[
            _item("오타루 운하", time(11, 0), time(12, 30)),
            _item("사카이마치", time(13, 0), time(15, 0)),
        ],
        transfers=[
            _transfer(50, time(10, 0), time(10, 50)),
            _transfer(50, time(15, 0), time(15, 50)),
        ],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("당일치기" in f for f in itin.feasibility_flags)


def test_in_city_day_not_flagged_as_daytrip() -> None:
    # 시내 날: 짧은 이동(최장 30분)만 → 시외 근교가 아니라 판단 대상 아님.
    day = DayPlan(
        day=1,
        items=[
            _item("A", time(10, 0), time(11, 30)),
            _item("B", time(12, 0), time(13, 30)),
        ],
        transfers=[
            _transfer(30, time(11, 30), time(12, 0)),
            _transfer(25, time(13, 30), time(13, 55)),
        ],
    )
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("당일치기" in f for f in itin.feasibility_flags)


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


# --- 영업시간(type 기반) 결정적 플래그 ---


def test_market_in_evening_is_flagged() -> None:
    # 어시장을 저녁(20시) 시작 → 시장류는 오후 일찍 닫으므로 플래그.
    market = _item("니가타 수산시장", time(20, 0), time(21, 0), type_="수산시장")
    itin = _itin([DayPlan(day=1, items=[market])])
    PlanCriticAgent()._check_feasibility(itin)
    assert any("시장류" in f and "1일차" in f for f in itin.feasibility_flags)


def test_market_in_morning_is_ok() -> None:
    # 같은 시장을 오전(08시)에 가면 정상 — 플래그 없음.
    market = _item("니가타 수산시장", time(8, 0), time(9, 30), type_="수산시장")
    itin = _itin([DayPlan(day=2, items=[market])])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("시장류" in f for f in itin.feasibility_flags)


def test_museum_late_finish_is_flagged() -> None:
    # 미술관이 19시까지 → 대개 17~18시 마감이라 플래그.
    day = DayPlan(day=1, items=[_item("현대 미술관", time(16, 0), time(19, 0), type_="미술관")])
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert any("박물관·미술관" in f for f in itin.feasibility_flags)


def test_museum_daytime_is_ok() -> None:
    # 미술관이 17시 종료면 정상(마감 17:30 이내).
    day = DayPlan(day=1, items=[_item("현대 미술관", time(14, 0), time(17, 0), type_="미술관")])
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("박물관·미술관" in f for f in itin.feasibility_flags)


def test_non_market_non_museum_not_flagged() -> None:
    # 시장·박물관류가 아닌 곳은 저녁에 있어도 영업시간 플래그 없음(상점가는 저녁 OK).
    day = DayPlan(day=1, items=[_item("도톤보리 상점가", time(20, 0), time(21, 0), type_="상점가")])
    itin = _itin([day])
    PlanCriticAgent()._check_feasibility(itin)
    assert not any("시장류" in f or "박물관" in f for f in itin.feasibility_flags)
