from __future__ import annotations

import pytest

from travel_agent.app.llm.direct_answer import is_conversational_question


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("오타루 볼거 뭐있냐", True),
        ("삿포로 어때?", True),
        ("오타루 가볼만한 곳", True),
        ("삿포로 3박4일 여행 계획 짜줘", False),
        ("도쿄 7월 초중순 항공권 찾아줘", False),
        ("오사카 4박5일 숙소 추천해줘", False),
        ("다낭 가족여행 일정이랑 예산 짜줘", False),
        ("삿포로 스스키노 근처 4성급 호텔", False),
        ("방콕 맛집이랑 관광지 알려줘", False),
        ("", False),
    ],
)
def test_is_conversational_question(message: str, expected: bool) -> None:
    assert is_conversational_question(message) is expected
