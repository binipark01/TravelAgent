"""주요 여행 도시의 근교 당일치기(day-trip) 명소를 정리한다.

각 지역 관광청 공식 사이트 + Wikivoyage 'Go next' 정보를 바탕으로 큐레이션한
레퍼런스 데이터다. 이동시간·교통수단은 대략치이며 출처를 명시한다. 허브 도시
정규화는 현지교통 커넥터(resolve_city)를 재사용한다. 데이터가 없으면 None.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from travel_agent.app.connectors.routes.local_transport import resolve_city
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import (
    NearbyDestination,
    NearbyGuide,
    ProviderMetadata,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


@dataclass(frozen=True)
class _Spot:
    name: str
    travel_time: str
    transport: str
    highlights: list[str]
    best_for: str = ""


@dataclass(frozen=True)
class _Hub:
    hub: str
    summary: str
    source_url: str
    spots: list[_Spot] = field(default_factory=list)


_DATA: dict[str, _Hub] = {
    "삿포로": _Hub(
        "삿포로",
        "삿포로에서 기차·버스로 닿는 근교 당일치기. 운하 도시 오타루, 온천 노보리베츠, "
        "여름 꽃밭 비에이·후라노가 인기.",
        "https://www.visit-hokkaido.jp/ko/",
        [
            _Spot("오타루", "JR 쾌속 약 35분", "JR 쾌속 에어포트",
                  ["운하 야경", "오르골당", "스시·유리공예"], "반나절~하루"),
            _Spot("노보리베츠 온천", "특급+버스 약 90분", "JR 특급 + 도난버스",
                  ["지옥계곡", "온천", "다테 시대촌"], "하루"),
            _Spot("비에이·후라노", "JR 약 2시간", "JR(여름 라벤더 임시열차)",
                  ["라벤더밭(여름)", "청의 호수", "파노라마 로드"], "하루(여름 추천)"),
            _Spot("토야호(도야호)", "버스 약 2시간", "도난버스",
                  ["칼데라 호수", "온천", "여름 불꽃놀이"], "하루"),
            _Spot("아사히야마 동물원", "JR 특급 약 1.5시간", "JR 특급(아사히카와)",
                  ["펭귄 산책(겨울)", "행동전시 동물원"], "하루"),
            _Spot("조잔케이 온천", "버스 약 60분", "조테츠버스",
                  ["계곡 단풍", "온천 료칸"], "반나절"),
        ],
    ),
    "도쿄": _Hub(
        "도쿄",
        "도쿄 근교 당일치기. 온천·자연의 하코네, 대불의 가마쿠라, 세계유산 닛코가 대표.",
        "https://www.gotokyo.org/kr/",
        [
            _Spot("하코네", "로망스카 약 85분", "오다큐 로망스카(신주쿠발)",
                  ["오와쿠다니", "아시호수 해적선", "온천·미술관"], "하루"),
            _Spot("가마쿠라·에노시마", "JR 약 1시간", "JR 요코스카선",
                  ["대불", "쓰루가오카하치만구", "에노시마 해변"], "하루"),
            _Spot("닛코", "도부선 약 2시간", "도부 닛코선 특급",
                  ["도쇼구(세계유산)", "게곤 폭포", "주젠지 호수"], "하루"),
            _Spot("요코하마", "약 30분", "도큐·JR",
                  ["미나토미라이", "차이나타운", "아카렌가 창고"], "반나절~하루"),
            _Spot("가와고에", "약 1시간", "도부·세이부선",
                  ["에도 시대 거리", "과자 골목", "도키노카네"], "반나절"),
        ],
    ),
    "오사카": _Hub(
        "오사카",
        "오사카 근교 당일치기. 간사이는 교토·나라·고베·히메지가 모두 30~45분 거리.",
        "https://osaka-info.jp/ko/",
        [
            _Spot("교토", "신쾌속 약 30분", "JR 신쾌속/한큐",
                  ["후시미이나리", "기요미즈데라", "아라시야마"], "하루"),
            _Spot("나라", "약 45분", "긴테쓰/JR",
                  ["나라공원 사슴", "도다이지 대불", "가스가타이샤"], "반나절~하루"),
            _Spot("고베", "약 30분", "JR 신쾌속/한신",
                  ["하버랜드 야경", "기타노 이진칸", "고베규"], "하루"),
            _Spot("히메지", "신칸센 약 30분", "산요신칸센/JR",
                  ["히메지성(세계유산)", "고코엔 정원"], "반나절"),
        ],
    ),
    "후쿠오카": _Hub(
        "후쿠오카",
        "후쿠오카 근교 당일치기. 온천 마을 유후인·벳푸, 학문의 신 다자이후가 인기.",
        "https://www.crossroadfukuoka.jp/ko/",
        [
            _Spot("유후인", "고속버스 약 100분", "유후인노모리/고속버스",
                  ["긴린호수", "온천 료칸", "유노쓰보 거리"], "하루"),
            _Spot("벳푸", "특급 약 2시간", "JR 특급 소닉",
                  ["지옥온천 순례", "모래찜질"], "하루"),
            _Spot("다자이후", "니시테츠 약 40분", "니시테쓰 전철",
                  ["다자이후 텐만구", "규슈국립박물관"], "반나절"),
            _Spot("모지코 레트로", "JR 약 1.5시간", "JR 가고시마본선",
                  ["레트로 항구 거리", "간몬해협"], "반나절"),
        ],
    ),
    "오키나와": _Hub(
        "오키나와",
        "오키나와는 대중교통이 약해 근교는 렌터카가 사실상 필수. 북부 츄라우미가 대표.",
        "https://www.visitokinawa.jp/ko",
        [
            _Spot("츄라우미 수족관(모토부)", "렌터카 약 2시간", "렌터카",
                  ["고래상어 대수조", "에메랄드 비치"], "하루"),
            _Spot("코우리지마", "렌터카 약 1.5시간", "렌터카",
                  ["코우리 대교", "하트록 바위"], "반나절"),
            _Spot("아메리칸 빌리지(자탄)", "렌터카 약 40분", "렌터카/버스",
                  ["선셋 비치", "쇼핑·관람차"], "반나절"),
        ],
    ),
    "방콕": _Hub(
        "방콕",
        "방콕 근교 당일치기. 유네스코 유적 아유타야, 수상시장, 해변 도시 파타야.",
        "https://www.tourismthailand.org/",
        [
            _Spot("아유타야", "기차/밴 약 1.5시간", "기차 또는 밴",
                  ["왓 마하탓 불두", "고대 사원 유적"], "하루"),
            _Spot("담넌사두억 수상시장", "밴 약 1.5시간", "투어 밴",
                  ["수상시장 보트", "현지 먹거리"], "반나절(오전)"),
            _Spot("파타야", "버스 약 2시간", "고속버스",
                  ["해변", "산호섬(꼬란)", "야시장"], "하루~1박"),
        ],
    ),
    "다낭": _Hub(
        "다낭",
        "다낭 근교 당일치기. 등불의 호이안, 골든브리지 바나힐, 황성 도시 후에.",
        "https://danang.gov.vn/",
        [
            _Spot("호이안", "차량 약 45분", "택시/Grab/셔틀",
                  ["올드타운 등불", "내원교", "야시장"], "반나절~하루(야간 추천)"),
            _Spot("바나힐", "차량 약 45분", "택시/투어",
                  ["골든브리지", "케이블카", "프랑스 마을"], "하루"),
            _Spot("후에", "차량 약 2시간", "택시/기차/투어",
                  ["응우옌 왕조 황성", "티엔무 사원"], "하루"),
            _Spot("미선 유적", "차량 약 1시간", "투어/택시",
                  ["참파 왕국 유적(세계유산)"], "반나절"),
        ],
    ),
    "타이베이": _Hub(
        "타이베이",
        "타이베이 근교 당일치기. 홍등 골목 지우펀, 기암 예류, 천등의 핑시·스펀.",
        "https://www.travel.taipei/ko",
        [
            _Spot("지우펀", "버스 약 1시간", "기륭客運 버스",
                  ["홍등 골목", "찻집", "산비탈 야경"], "반나절~하루"),
            _Spot("예류 지질공원", "버스 약 1.5시간", "국광客運 버스",
                  ["여왕바위", "기암 해안"], "반나절"),
            _Spot("스펀·핑시", "기차 약 1.5시간", "핑시선 기차",
                  ["천등 날리기", "스펀 폭포"], "하루"),
            _Spot("단수이", "MRT 약 40분", "MRT 단수이선",
                  ["강변 노을", "라오제(옛 거리)"], "반나절"),
            _Spot("베이터우 온천", "MRT 약 30분", "MRT 신베이터우",
                  ["노천 온천", "지열곡"], "반나절"),
        ],
    ),
}


def _metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="nearby_day_trips",
        source_url=source_url,
        title="근교 당일치기(관광청·Wikivoyage 기준)",
        reference=f"nearby-{now.strftime('%Y%m%d')}",
        retrieved_at=now,
        expires_at=expires_in(24 * 30),
        is_live=False,
        is_mock=False,
        source_type="curated_reference",
        confidence=0.6,
        freshness_note="큐레이션 레퍼런스. 이동시간·운행은 변동 가능 — 방문 전 확인.",
    )
    return ProviderMetadata(
        provider_name="nearby_day_trips",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(24 * 30),
        normalized_currency=None,
        is_mock=False,
    )


def lookup_nearby(destination: str) -> NearbyGuide | None:
    city = resolve_city(destination)
    if city is None or city not in _DATA:
        return None
    hub = _DATA[city]
    return NearbyGuide(
        hub=hub.hub,
        summary=hub.summary,
        destinations=[
            NearbyDestination(
                name=spot.name,
                travel_time=spot.travel_time,
                transport=spot.transport,
                highlights=list(spot.highlights),
                best_for=spot.best_for or None,
                source_url=hub.source_url,
            )
            for spot in hub.spots
        ],
        source_url=hub.source_url,
        metadata=_metadata(hub.source_url),
    )
