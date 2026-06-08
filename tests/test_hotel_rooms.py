from __future__ import annotations

from travel_agent.app.connectors.accommodations.google_hotel_browser import (
    detect_bed_preference,
    match_room,
    parse_rooms,
)

TWIN_TEXT = (
    "체크인 체크아웃 2 1박 "
    "트윈룸 싱글 침대 2개 ₩201,000 사이트 방문 "
    "더블룸 더블 사이즈 침대 1개 ₩222,348 사이트 방문"
)
DOUBLE_ONLY_TEXT = (
    "더블룸 더블 사이즈 침대 1개 ₩222,348 사이트 방문 "
    "더블룸 더블 사이즈 침대 1개 · 조식 ₩259,406 사이트 방문"
)


def test_detect_bed_preference() -> None:
    assert detect_bed_preference("트윈베드 객실") == "twin"
    assert detect_bed_preference("twin room please") == "twin"
    assert detect_bed_preference("더블 침대 원해요") == "double"
    assert detect_bed_preference("조용한 곳") is None
    assert detect_bed_preference(None) is None


def test_parse_rooms_extracts_prices() -> None:
    rooms = parse_rooms(TWIN_TEXT)
    assert [room["price"] for room in rooms] == [201_000, 222_348]


def test_match_room_finds_twin() -> None:
    rooms = parse_rooms(TWIN_TEXT)
    twin = match_room(rooms, "twin")
    assert twin is not None
    assert twin["price"] == 201_000  # 트윈룸 가격


def test_double_only_hotel_does_not_match_twin() -> None:
    # 더블룸만 있는 호텔은 트윈으로 오매칭되면 안 된다(좁은 윈도우로 오염 방지).
    rooms = parse_rooms(DOUBLE_ONLY_TEXT)
    assert match_room(rooms, "twin") is None
    assert match_room(rooms, "double") is not None


def test_parse_rooms_detects_ota() -> None:
    text = (
        "트윈룸 싱글 침대 2개 부킹닷컴 ₩201,000 사이트 방문 "
        "더블룸 더블 사이즈 침대 1개 아고다 ₩222,348"
    )
    rooms = parse_rooms(text)

    assert rooms[0]["ota"] == "부킹닷컴"
    assert rooms[1]["ota"] == "아고다"
    twin = match_room(rooms, "twin")
    assert twin is not None
    assert twin["ota"] == "부킹닷컴"
