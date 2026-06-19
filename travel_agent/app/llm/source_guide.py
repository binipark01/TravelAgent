"""목적지(국가/대륙)별로 '정보가 풍부한 권위 출처'를 골라 LLM 큐레이터에 알려준다.

구글지도·네이버만으로는 유럽·미주 등 비아시아권 여행정보가 부족하다. 지역마다 신뢰도 높은
현지 리뷰 사이트가 다르므로(일본 Tabelog, 중국 다중뎬핑, 태국 Wongnai, 유럽 TheFork·미슐랭,
미국 Yelp·Eater …), 큐레이터가 웹검색할 때 그 지역의 권위 출처를 우선 참고하게 힌트를 준다.

이건 '무엇을 추천할지'를 코드로 정하는 게 아니라 'LLM이 어디를 봐야 좋은지'를 알려주는
출처 지도다. 미등록 국가는 generic 폴백을 주고, LLM이 더 나은 출처를 찾으면 그걸 써도 된다.
국가 해석은 비자 커넥터의 resolve_country(도시→국가, LLM 폴백 포함)를 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.connectors.visa.entry_requirements import resolve_country


@dataclass(frozen=True)
class SourceHints:
    restaurant: str  # 현지 권위 맛집 리뷰
    activity: str  # 투어·액티비티·입장권 예매
    community: str  # 한국인 여행 정보 커뮤니티/블로그
    official: str  # 공식 관광청
    extra: str = ""  # 가이드북 등 부가


# resolve_country가 돌려주는 한국어 국가 키 -> 권위 출처.
_BY_COUNTRY: dict[str, SourceHints] = {
    "일본": SourceHints(
        "타베로그(Tabelog)·구글맵 리뷰",
        "클룩(Klook)·KKday",
        "네이버 블로그·일본여행 카페·트립닷컴",
        "일본정부관광국(JNTO)·지자체 관광사이트",
    ),
    "중국": SourceHints(
        "다중뎬핑(大众点评/Dianping)",
        "클룩·KKday",
        "네이버 블로그·중국여행 카페",
        "각 도시 문화관광국",
    ),
    "태국": SourceHints(
        "Wongnai·구글맵 리뷰",
        "클룩·KKday",
        "태사랑 카페·네이버 블로그·마이리얼트립",
        "태국관광청(TAT)",
    ),
    "베트남": SourceHints(
        "Foody·구글맵 리뷰",
        "클룩·KKday",
        "네이버 베트남여행 카페·마이리얼트립",
        "베트남 국가관광청",
    ),
    "대만": SourceHints(
        "구글맵 리뷰·아이펑(愛評)",
        "클룩·KKday",
        "네이버 블로그·대만여행 카페",
        "대만관광청",
    ),
    "홍콩": SourceHints(
        "OpenRice",
        "클룩·KKday",
        "네이버 블로그·트립닷컴",
        "홍콩관광청",
    ),
    "싱가포르": SourceHints(
        "OpenRice·구글맵 리뷰",
        "클룩·KKday",
        "네이버 블로그·마이리얼트립",
        "싱가포르관광청(STB)",
    ),
    "말레이시아": SourceHints(
        "구글맵 리뷰·OpenRice",
        "클룩·KKday",
        "네이버 블로그",
        "말레이시아관광청",
    ),
    "인도네시아": SourceHints(
        "구글맵 리뷰·Zomato",
        "클룩·KKday·GetYourGuide",
        "네이버 발리여행 카페·마이리얼트립",
        "인도네시아관광청(발리 등)",
    ),
    "필리핀": SourceHints(
        "구글맵 리뷰·Zomato",
        "클룩·KKday",
        "네이버 필리핀여행 카페",
        "필리핀관광부",
    ),
    "미국": SourceHints(
        "Yelp·Eater·구글맵 리뷰",
        "GetYourGuide·Viator",
        "마이리얼트립·네이버 블로그·Reddit(r/travel)",
        "각 주·도시 관광청(Visit California 등)",
    ),
    "캐나다": SourceHints(
        "Yelp·구글맵 리뷰",
        "GetYourGuide·Viator",
        "네이버 블로그·마이리얼트립",
        "Destination Canada·도시 관광청",
    ),
    "유럽(셰겐)": SourceHints(
        "TheFork·미슐랭 가이드·Le Fooding·구글맵 리뷰",
        "GetYourGuide·Tiqets·Viator",
        "유랑(네이버 카페)·네이버 블로그·마이리얼트립",
        "각국 관광청(france.fr·italia.it·spain.info 등)",
        "Rick Steves·Wikivoyage",
    ),
    "영국": SourceHints(
        "TheFork·미슐랭 가이드·TripAdvisor",
        "GetYourGuide·Viator",
        "유랑 카페·네이버 블로그·마이리얼트립",
        "VisitBritain·VisitLondon",
        "Wikivoyage",
    ),
    "호주": SourceHints(
        "구글맵 리뷰·Zomato",
        "GetYourGuide·클룩·Viator",
        "네이버 호주여행 카페·마이리얼트립",
        "Tourism Australia",
    ),
    "괌": SourceHints(
        "구글맵 리뷰·Yelp",
        "클룩·Viator",
        "네이버 괌여행 카페·마이리얼트립",
        "괌정부관광청(GVB)",
    ),
    "사이판": SourceHints(
        "구글맵 리뷰",
        "클룩·Viator",
        "네이버 사이판여행 카페",
        "마리아나관광청(MVA)",
    ),
}

# 어느 카테고리에도 안 잡히면(미등록 국가) 쓰는 일반 폴백.
_GENERIC = SourceHints(
    "그 나라의 대표 현지 맛집 리뷰 사이트 + 구글맵 리뷰",
    "GetYourGuide·Viator·클룩 중 그 지역에 강한 곳",
    "마이리얼트립·네이버 블로그·트립어드바이저",
    "해당 국가/도시 공식 관광청",
)


def hints_for(destination: str) -> SourceHints:
    country = resolve_country(destination)
    return _BY_COUNTRY.get(country or "", _GENERIC)


def source_hints_block(destination: str) -> str:
    """큐레이터 프롬프트에 끼워넣을 '권위 출처 우선' 안내 문구를 만든다."""
    hints = hints_for(destination)
    lines = [
        "추천을 모을 때 아래 '그 지역에서 신뢰도 높은 출처'를 우선 검색·교차확인하라. "
        "다만 여기 없어도 더 좋은 현지 출처를 찾으면 함께 써도 된다.",
        f"- 맛집 리뷰: {hints.restaurant}",
        f"- 투어·액티비티·입장권: {hints.activity}",
        f"- 한국인 여행정보: {hints.community}",
        f"- 공식: {hints.official}",
    ]
    if hints.extra:
        lines.append(f"- 가이드: {hints.extra}")
    return "\n".join(lines)
