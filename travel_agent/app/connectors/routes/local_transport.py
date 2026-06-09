"""주요 여행 도시의 현지 이동 안내(공항↔시내 교통 + 교통패스).

큐레이션 레퍼런스 데이터다. 요금/소요시간은 대략치이며 변동될 수 있어
'예매·탑승 전 재확인'을 전제로 한다. 도시가 데이터셋에 없으면 None을 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import (
    LocalTransportItem,
    LocalTransportPlan,
    ProviderMetadata,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


@dataclass(frozen=True)
class _CityTransport:
    city: str
    summary: str
    airport_transfers: list[dict]
    transit_passes: list[dict]
    tips: list[str] = field(default_factory=list)
    source_url: str | None = None


_DATA: dict[str, _CityTransport] = {
    "도쿄": _CityTransport(
        "도쿄",
        "나리타/하네다 공항철도로 도심 이동, 시내는 Suica IC카드 + 지하철이 기본.",
        [
            {"name": "케이세이 스카이라이너", "detail": "나리타공항→닛포리/우에노",
             "price": "약 2,580엔", "duration": "약 41분"},
            {"name": "나리타 익스프레스(N'EX)", "detail": "나리타공항→도쿄/신주쿠",
             "price": "약 3,070엔", "duration": "약 60분"},
            {"name": "게이큐선", "detail": "하네다공항→시나가와", "price": "약 330엔",
             "duration": "약 15분"},
        ],
        [
            {"name": "Suica / PASMO (IC카드)",
             "detail": "지하철·버스·편의점 충전식(모바일 Suica 가능)"},
            {"name": "도쿄 서브웨이 티켓", "detail": "외국인 전용 지하철 무제한",
             "price": "24h 800엔 / 48h 1,200엔 / 72h 1,500엔"},
            {"name": "JR패스(광역)", "detail": "신칸센·근교 포함 장거리 이동 시 검토"},
        ],
        ["도심은 JR패스보다 IC카드+지하철이 효율적", "택시는 비싸므로 지하철 우선"],
        "https://www.gotokyo.org/kr/",
    ),
    "오사카": _CityTransport(
        "오사카",
        "간사이공항에서 난카이/JR로 시내 진입, 관광은 오사카 주유패스가 가성비 좋음.",
        [
            {"name": "난카이 라피트(특급)", "detail": "간사이공항→난바", "price": "약 1,450엔",
             "duration": "약 38분"},
            {"name": "난카이 공항급행", "detail": "간사이공항→난바", "price": "약 970엔",
             "duration": "약 45분"},
            {"name": "JR 하루카(특급)", "detail": "간사이공항→신오사카/교토",
             "price": "약 2,400엔", "duration": "약 50분"},
        ],
        [
            {"name": "ICOCA (IC카드)", "detail": "간사이권 교통·편의점 충전식"},
            {"name": "오사카 주유패스", "detail": "지하철 무제한 + 40여 관광지 무료입장",
             "price": "1일 2,800엔 / 2일 3,600엔"},
            {"name": "간사이 스루패스", "detail": "오사카·교토·나라·고베 사철/버스 무제한"},
        ],
        ["오사카+교토+나라 묶으면 간사이 스루패스 검토", "USJ는 별도 티켓"],
        "https://osaka-info.jp/ko/",
    ),
    "삿포로": _CityTransport(
        "삿포로",
        "신치토세공항에서 JR 쾌속으로 삿포로역 진입, 시내는 지하철 1일권이 편리.",
        [
            {"name": "JR 쾌속 에어포트", "detail": "신치토세공항→삿포로역", "price": "약 1,150엔",
             "duration": "약 37분"},
            {"name": "공항 연락버스", "detail": "신치토세공항→삿포로 시내 주요 호텔",
             "price": "약 1,100엔", "duration": "약 70분"},
        ],
        [
            {"name": "SAPICA / Suica (IC카드)", "detail": "지하철·버스·노면전차"},
            {"name": "지하철 전용 1일 승차권", "detail": "주말·공휴일은 도니치카킷푸가 더 저렴",
             "price": "평일 830엔 / 주말 520엔"},
        ],
        ["겨울철 눈으로 버스 지연 잦음 — 지하철 위주", "근교(오타루)는 JR 이용"],
        "https://www.sapporo.travel/ko/",
    ),
    "후쿠오카": _CityTransport(
        "후쿠오카",
        "공항이 도심과 가까워 지하철 2정거장이면 하카타 도착. 시내 이동이 매우 편함.",
        [
            {"name": "공항선 지하철", "detail": "후쿠오카공항역→하카타/텐진", "price": "약 260엔",
             "duration": "약 5~11분"},
        ],
        [
            {"name": "nimoca / Suica (IC카드)", "detail": "지하철·버스"},
            {"name": "후쿠오카 투어리스트 시티패스", "detail": "지하철·버스·니시테츠 무제한",
             "price": "1일 약 1,500엔"},
        ],
        ["도심이 좁아 도보+지하철로 충분", "유후인·벳푸는 고속버스/특급열차"],
        "https://www.crossroadfukuoka.jp/ko/",
    ),
    "오키나와": _CityTransport(
        "오키나와",
        "대중교통이 약해 렌터카가 사실상 필수. 나하 시내만이면 유이레일로 충분.",
        [
            {"name": "유이레일(모노레일)", "detail": "나하공항→국제거리(겐초마에/마키시)",
             "price": "약 270엔~", "duration": "약 13분"},
            {"name": "렌터카", "detail": "공항 인근 영업소에서 픽업 — 북부/해변 이동에 필수"},
        ],
        [
            {"name": "유이레일 1일/2일권", "detail": "나하 시내 한정",
             "price": "1일 800엔 / 2일 1,400엔"},
            {"name": "OKICA", "detail": "오키나와 전용 IC카드(Suica 호환 제한적)"},
        ],
        ["츄라우미 수족관 등 북부는 렌터카 강력 권장", "국제운전면허증 지참"],
        "https://www.visitokinawa.jp/ko",
    ),
    "방콕": _CityTransport(
        "방콕",
        "수완나품은 공항철도(ARL), 시내는 BTS/MRT + Grab 조합이 가장 빠름.",
        [
            {"name": "ARL 공항철도", "detail": "수완나품공항→파야타이(BTS 환승)",
             "price": "약 45밧", "duration": "약 30분"},
            {"name": "Grab / 택시", "detail": "돈므앙공항은 A1버스 또는 Grab 권장"},
        ],
        [
            {"name": "Rabbit 카드", "detail": "BTS 스카이트레인 충전식"},
            {"name": "MRT 카드", "detail": "지하철 별도 시스템(BTS와 분리)"},
        ],
        ["출퇴근 시간 도로 정체 극심 — BTS/MRT 우선", "택시는 미터기 사용 요구"],
        "https://www.tourismthailand.org/",
    ),
    "다낭": _CityTransport(
        "다낭",
        "공항이 시내 한가운데라 매우 가까움. 대중교통은 약해 Grab/택시가 기본.",
        [
            {"name": "Grab / 택시", "detail": "다낭공항→시내 호텔", "price": "약 7~10만 동",
             "duration": "약 10분"},
        ],
        [
            {"name": "Grab(앱)", "detail": "차량/오토바이 호출 — 요금 투명, 현지 필수 앱"},
            {"name": "호이안행 셔틀/택시", "detail": "다낭↔호이안 약 40분, Grab/사설 셔틀"},
        ],
        ["바나힐·호이안은 차량 대절/그랩이 편함", "공항 환전보다 시내 금은방 환율 유리"],
        "https://danang.gov.vn/",
    ),
    "타이베이": _CityTransport(
        "타이베이",
        "타오위안공항은 공항 MRT로 타이베이역 직결, 시내는 EasyCard + 메트로.",
        [
            {"name": "공항 MRT(직달차)", "detail": "타오위안공항→타이베이역",
             "price": "약 150 NT$", "duration": "약 35분"},
        ],
        [
            {"name": "EasyCard(悠遊卡)", "detail": "메트로·버스·편의점·유바이크 충전식"},
            {"name": "타이베이 메트로 1일권", "detail": "지하철 무제한"},
        ],
        ["지룽·예류·진과스는 버스/기차 당일치기", "유바이크(공유자전거) 저렴"],
        "https://www.travel.taipei/ko",
    ),
    "싱가포르": _CityTransport(
        "싱가포르",
        "창이공항에서 MRT로 시내 진입, 도시 전체가 MRT로 촘촘히 연결됨.",
        [
            {"name": "MRT", "detail": "창이공항→시내(타나메라 환승)", "price": "약 2 SGD",
             "duration": "약 40분"},
            {"name": "택시 / Grab", "detail": "심야엔 MRT 미운행 — 택시/Grab"},
        ],
        [
            {"name": "EZ-Link / 창이 투어리스트 패스", "detail": "MRT·버스 충전식 또는 무제한권"},
            {"name": "컨택리스 카드", "detail": "해외 신용카드 태그로 바로 탑승 가능"},
        ],
        ["택시 기본요금 비쌈 — MRT 우선", "센토사는 모노레일/케이블카"],
        "https://www.visitsingapore.com/ko_kr/",
    ),
    "홍콩": _CityTransport(
        "홍콩",
        "에어포트 익스프레스로 센트럴 직결, 시내는 옥토퍼스 카드 하나로 모든 교통.",
        [
            {"name": "에어포트 익스프레스", "detail": "홍콩공항→센트럴/구룡",
             "price": "약 115 HKD", "duration": "약 24분"},
            {"name": "공항버스(A21 등)", "detail": "저렴하지만 느림", "price": "약 33 HKD"},
        ],
        [
            {"name": "옥토퍼스(Octopus) 카드", "detail": "MTR·버스·트램·페리·편의점 충전식"},
        ],
        ["트램(딩딩)·스타페리는 명물이자 저렴", "MTR이 가장 빠름"],
        "https://www.discoverhongkong.com/kr/",
    ),
}

# 도시 별칭(영문/한글) → 데이터 키
_ALIASES: dict[str, str] = {
    "tokyo": "도쿄", "도쿄": "도쿄",
    "osaka": "오사카", "오사카": "오사카",
    "sapporo": "삿포로", "삿포로": "삿포로",
    "fukuoka": "후쿠오카", "후쿠오카": "후쿠오카",
    "okinawa": "오키나와", "오키나와": "오키나와", "naha": "오키나와", "나하": "오키나와",
    "bangkok": "방콕", "방콕": "방콕",
    "da nang": "다낭", "danang": "다낭", "다낭": "다낭",
    "taipei": "타이베이", "타이베이": "타이베이", "타이페이": "타이베이",
    "singapore": "싱가포르", "싱가포르": "싱가포르",
    "hong kong": "홍콩", "hongkong": "홍콩", "홍콩": "홍콩",
}


def resolve_city(destination: str) -> str | None:
    if not destination:
        return None
    text = destination.split(",")[0].strip().lower()
    if text in _ALIASES:
        return _ALIASES[text]
    for alias, city in _ALIASES.items():
        if alias in text:
            return city
    return None


def _metadata(source_url: str | None) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="local_transport",
        source_url=source_url,
        title="현지 교통 안내(큐레이션)",
        reference=f"transit-{now.strftime('%Y%m%d')}",
        retrieved_at=now,
        expires_at=expires_in(24 * 30),
        is_live=False,
        is_mock=False,
        source_type="curated_reference",
        confidence=0.6,
        freshness_note="요금·소요시간은 대략치. 탑승 전 재확인 필요.",
    )
    return ProviderMetadata(
        provider_name="local_transport",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(24 * 30),
        normalized_currency=None,
        is_mock=False,
    )


def lookup_local_transport(destination: str) -> LocalTransportPlan | None:
    city = resolve_city(destination)
    if city is None or city not in _DATA:
        return None
    data = _DATA[city]
    return LocalTransportPlan(
        city=data.city,
        summary=data.summary,
        airport_transfers=[
            LocalTransportItem(category="airport", **item) for item in data.airport_transfers
        ],
        transit_passes=[
            LocalTransportItem(category="pass", **item) for item in data.transit_passes
        ],
        tips=list(data.tips),
        source_url=data.source_url,
        metadata=_metadata(data.source_url),
    )
