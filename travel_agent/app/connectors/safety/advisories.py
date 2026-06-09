"""주요 여행지의 안전 정보(긴급연락처·영사콜센터·여행경보 안내·보험/주의사항).

큐레이션 레퍼런스다. 여행경보 단계는 수시 변동하므로 단정하지 않고 외교부
해외안전여행(0404.go.kr) 확인을 안내한다. 목적지→국가 매핑은 비자 커넥터를 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from travel_agent.app.connectors.visa.entry_requirements import resolve_country
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import (
    EmergencyContact,
    ProviderMetadata,
    SafetyInfo,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

_MOFA = "https://www.0404.go.kr"
_CONSULAR = "영사콜센터 +82-2-3210-0404 (24시간)"

# 공통 여행자보험 안내
_INSURANCE_TIPS = [
    "출국 전 여행자보험 가입 — 해외 의료비·휴대품 도난·항공 지연 보장 확인",
    "신용카드 자동 여행보험(출국 항공권 결제 시) 보장 범위도 함께 확인",
    "처방약은 영문 처방전과 함께 휴대, 비상약(지사제·해열제) 준비",
]


@dataclass(frozen=True)
class _CountrySafety:
    country: str
    summary: str
    contacts: list[tuple[str, str]]  # (label, number)
    embassy_note: str
    local_cautions: list[str] = field(default_factory=list)
    advisory: str | None = None


_DATA: dict[str, _CountrySafety] = {
    "일본": _CountrySafety(
        "일본", "치안이 양호하나 지진·태풍 등 자연재해 대비가 필요합니다.",
        [("경찰", "110"), ("구급·소방", "119")],
        "주일본 대한민국대사관(도쿄) 및 각지 총영사관. 긴급 시 영사콜센터 이용.",
        ["지진 시 머리 보호 후 탁자 밑 대피, 안내방송 확인",
         "여름철 태풍·폭우 교통 마비 가능 — 기상정보 확인"],
    ),
    "태국": _CountrySafety(
        "태국", "관광지 소매치기·바가지와 교통사고에 유의하세요.",
        [("경찰", "191"), ("구급", "1669"), ("관광경찰", "1155")],
        "주태국 대한민국대사관(방콕). 관광경찰(1155)은 영어 응대.",
        ["오토바이·뚝뚝 사고 빈번 — 헬멧 착용, 무면허 대여 금지",
         "택시는 미터기 사용 요구, 그랩(Grab) 권장",
         "왕실 모독은 중범죄 — 언행 주의"],
    ),
    "베트남": _CountrySafety(
        "베트남", "오토바이 교통과 길거리 소매치기에 특히 유의하세요.",
        [("경찰", "113"), ("구급", "115"), ("소방", "114")],
        "주베트남 대한민국대사관(하노이)·호치민 총영사관·다낭 출장소.",
        ["횡단 시 오토바이 물결 — 천천히 일정한 속도로 건너기",
         "가방은 앞으로, 휴대폰 노상 사용 시 날치기 주의",
         "택시는 비나선/마일린 또는 Grab 이용"],
    ),
    "대만": _CountrySafety(
        "대만", "치안은 양호하나 지진·태풍에 대비하세요.",
        [("경찰", "110"), ("구급·소방", "119")],
        "주타이베이 대한민국대표부.",
        ["지진 빈발 지역 — 숙소 대피 경로 확인", "여름 태풍 시즌 일정 유연하게"],
    ),
    "싱가포르": _CountrySafety(
        "싱가포르", "치안이 매우 좋으나 법규 위반 벌금이 매우 큽니다.",
        [("경찰", "999"), ("구급·소방", "995")],
        "주싱가포르 대한민국대사관.",
        ["껌 반입·흡연구역 외 흡연·무단횡단 등 벌금 큼", "지하철·공공장소 음식물 취식 금지"],
    ),
    "홍콩": _CountrySafety(
        "홍콩", "치안은 양호하나 시위·집회 발생 시 우회하세요.",
        [("긴급(경찰·구급·소방)", "999")],
        "주홍콩 대한민국총영사관.",
        ["대규모 집회 지역 접근 자제", "소매치기 주의(번화가)"],
    ),
    "필리핀": _CountrySafety(
        "필리핀", "일부 지역 치안 취약 — 야간 외출과 외진 곳을 피하세요.",
        [("긴급", "911")],
        "주필리핀 대한민국대사관(마닐라)·세부 분관.",
        ["택시·환전 사기 주의, 공항 환전 최소화",
         "민다나오 등 여행경보 지역 확인 필수",
         "야간 단독 이동 자제"],
        advisory="일부 지역에 여행경보(자제·제한)가 발령되어 있어 반드시 외교부 확인 필요.",
    ),
    "말레이시아": _CountrySafety(
        "말레이시아", "대체로 안전하나 소매치기와 일부 해상지역에 유의하세요.",
        [("경찰·구급", "999"), ("관광경찰", "+603-2149-6590")],
        "주말레이시아 대한민국대사관(쿠알라룸푸르).",
        ["번화가 오토바이 날치기 주의", "사바주 동부 해안은 여행경보 확인"],
    ),
    "인도네시아": _CountrySafety(
        "인도네시아", "발리 등 관광지 교통사고·소매치기에 유의하세요.",
        [("경찰", "110"), ("구급", "118"), ("통합긴급", "112")],
        "주인도네시아 대한민국대사관(자카르타).",
        ["오토바이 대여·운전 사고 빈번", "화산·지진 활동 지역 — 안내 확인", "환전은 공인 환전소만"],
    ),
    "미국": _CountrySafety(
        "미국", "총기·치안 취약 지역과 야간 우범지대를 피하세요.",
        [("긴급(경찰·구급·소방)", "911")],
        "주미국 대한민국대사관 및 각지 총영사관.",
        ["야간 우범지대 출입 자제", "차량 내 귀중품 방치 금지(차량털이)",
         "팁 문화 — 식당 15~20%"],
    ),
    "괌": _CountrySafety(
        "괌", "치안은 양호하나 물놀이 안전수칙을 지키세요.",
        [("긴급", "911")],
        "괌 영사 업무는 주하갓냐(주괌) 측 또는 영사콜센터.",
        ["이안류(역파도) 주의 — 지정 해변에서만 물놀이", "렌터카 도난 방지"],
    ),
    "사이판": _CountrySafety(
        "사이판", "치안은 양호하나 물놀이·렌터카 안전에 유의하세요.",
        [("긴급", "911")],
        "영사 업무는 영사콜센터 이용.",
        ["이안류 주의", "외진 해변 단독 물놀이 자제"],
    ),
    "유럽(셰겐)": _CountrySafety(
        "유럽(셰겐)", "주요 관광지·대중교통 소매치기가 매우 많습니다.",
        [("통합긴급", "112")],
        "각국 주재 대한민국대사관·총영사관.",
        ["지하철·관광명소 소매치기단 주의(가방 앞으로)",
         "기차역·공항 가방 분실 주의", "시위·파업 시 교통 차질"],
    ),
    "영국": _CountrySafety(
        "영국", "치안은 양호하나 번화가 소매치기에 유의하세요.",
        [("긴급(경찰·구급·소방)", "999"), ("통합긴급", "112")],
        "주영국 대한민국대사관(런던).",
        ["좌측통행 — 도로 횡단 시 우측 먼저 확인", "번화가 휴대폰 날치기 주의"],
    ),
    "중국": _CountrySafety(
        "중국", "치안은 보통이나 인파 밀집지·사기에 유의하세요.",
        [("경찰", "110"), ("구급", "120"), ("소방", "119")],
        "주중국 대한민국대사관(베이징) 및 각지 총영사관.",
        ["구글·카톡 등 제한 — VPN/현지 앱 사전 준비", "가짜 택시·환전 사기 주의"],
    ),
    "호주": _CountrySafety(
        "호주", "치안은 양호하나 자외선·해양 안전에 유의하세요.",
        [("긴급(경찰·구급·소방)", "000"), ("통합긴급", "112")],
        "주호주 대한민국대사관(캔버라)·시드니 총영사관.",
        ["강한 자외선 — 자외선차단 필수", "지정 해변(깃발 사이)에서만 수영"],
    ),
    "캐나다": _CountrySafety(
        "캐나다", "치안은 양호하나 일부 도심 우범지대를 피하세요.",
        [("긴급(경찰·구급·소방)", "911")],
        "주캐나다 대한민국대사관(오타와)·토론토/밴쿠버 총영사관.",
        ["겨울 혹한·도로 결빙 대비", "야생동물 출몰 지역 주의"],
    ),
}


def _metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="safety_advisory",
        source_url=source_url,
        title="안전 정보(외교부 해외안전여행 기준)",
        reference=f"safety-{now.strftime('%Y%m%d')}",
        retrieved_at=now,
        expires_at=expires_in(24 * 30),
        is_live=False,
        is_mock=False,
        source_type="curated_reference",
        confidence=0.6,
        freshness_note="큐레이션 레퍼런스. 여행경보는 수시 변동 — 출국 전 공식 확인.",
    )
    return ProviderMetadata(
        provider_name="safety_advisory",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(24 * 30),
        normalized_currency=None,
        is_mock=False,
    )


def lookup_safety_info(destination: str) -> SafetyInfo | None:
    country = resolve_country(destination)
    if country is None or country not in _DATA:
        return None
    data = _DATA[country]
    advisory = data.advisory or "현재 여행경보는 외교부 해외안전여행(0404.go.kr)에서 확인하세요."
    return SafetyInfo(
        destination_country=country,
        summary=data.summary,
        emergency_contacts=[
            EmergencyContact(label=label, number=number) for label, number in data.contacts
        ],
        consular_call_center=_CONSULAR,
        embassy_note=data.embassy_note,
        travel_advisory=advisory,
        insurance_tips=list(_INSURANCE_TIPS),
        local_cautions=list(data.local_cautions),
        source_url=_MOFA,
        metadata=_metadata(_MOFA),
    )
